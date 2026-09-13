#include <stdio.h>
#include <stdint.h>
#include "main_bl.h"
#include "system.h"
#include "flash.h"
//#include "systick.h"
#include "uart.h"
#include "spi.h"
#include "gpio.h"

#define APP_OFFSET (0x08010000)
#define VTOR (*(volatile uint32_t *)0xE000ED08)

#define RCC_BASE (0x40023800)
#define RCC_CSR (*(volatile uint32_t *)(RCC_BASE + 0x74))

#define RCC_CSR_PINRSTF (1 << 26)
#define RCC_CSR_SFTRSTF (1 << 28)
#define RCC_CSR_RMVF    (1 << 24)

void update_application(uint32_t app_address);
void crc_check_image(void);
void jump_to_application(uint32_t app_address);

void spi_rx_handler(SPI_x *SPIx, uint8_t data);
void spi_ovr_handler(SPI_x *SPIx, uint8_t data);

volatile uint8_t spi_recv_cplt_flag;
volatile uint16_t spi_recv_idx;
uint8_t spi_recv_buf[1024];			// parsing전 spi 수신 버퍼

void main_bl(void)
{
	flash_init();
	clock_config();
	gpio_init();
	//systick_enable();
	uart_init(UART3, 115200);

	// CP10(Bit 21:20)에 3(11)을 쓰고, CP11(Bit 23:22)에 3(11)을 써서 둘 다 Full Access로 만듦
	*(volatile uint32_t *)0xE000ED88 |= ((3UL << 20) | (3UL << 22));
	__asm__ volatile ("DSB");
	__asm__ volatile ("ISB");
	
	uint32_t reg = RCC_CSR;
	RCC_CSR |= RCC_CSR_RMVF;	// remove reset flag

	printf("\r\n\r\n");
	LOG_BOOT("STM32F407 Bootloader v1.0.0 Built: May 16 2026");

	if (reg & RCC_CSR_SFTRSTF) {
		LOG_BOOT("Reset Reason: Software Reset\r\n");
	
		LOG_INFO("Initializing SPI peripheral...");
		
		spi_init(SPI1, SPI_RECV_ONLY_SLAVE, 8, 1);
		spi_regist_rx_callback(spi_rx_handler);
		spi_regist_ovr_callback(spi_ovr_handler);
		
		LOG_OK("SPI1 Slave Receive Only mode initialized.");
		LOG_OK("SPI1 RXNE Interrupt Callback Function registed.");
		LOG_OK("SPI1 OVR Interrupt Callback Function registed.\r\n");

		update_application(APP_OFFSET);		// application image update
			
		LOG_INFO("Verifying complete image integrity (CRC)...");
		// 무결성 검사 시 flash cache에 남아있던 dummy 바이너리를 읽어오지 않도록 cache flush
		flash_cache_flush();
		crc_check_image();			// flash에 써진 이미지 무결성 검사
		LOG_OK("CRC Verification success! Firmware is valid.\r\n");

		spi_deinit(SPI1);
	}
	else if (reg & RCC_CSR_PINRSTF) {
		LOG_BOOT("Reset Reason: Normal Reset\r\n");
	}
	else {
		LOG_BOOT("Reset Reason: Else\r\n");
	}

	LOG_INFO("Disabling bootloader peripherals...");
	//systick_disable();

	LOG_OK("Ready to Jump. All systems are stable.");
	jump_to_application(APP_OFFSET);
}

void jump_to_application(uint32_t app_address)
{
	uint32_t app_end_stack = *(uint32_t *)app_address;
	void (*app_entry)(void) = (void (*)(void))(*(volatile uint32_t *)(app_address + 4));
	
	LOG_BOOT("Jumping to Application at 0x08010000...");

	// Application 위치로 Vector table 재설정
	__asm__ volatile ("cpsid i");
	VTOR = (uint32_t)app_address;
	__asm__ volatile ("ISB");
	__asm__ volatile ("cpsie i");

	// Application 스택 포인터 설정 후 점프
    __asm__ volatile ("msr msp, %0" :: "r"(app_end_stack));
    __asm__ volatile ("mov pc, %0"  :: "r"(app_entry));
}

uint16_t calculate_crc16(const uint8_t *data, uint32_t length) {
    uint16_t crc = 0xFFFF;
    for (uint32_t i = 0; i < length; i++) {
        crc ^= data[i];
        for (int j = 0; j < 8; j++) {
            if (crc & 0x0001) {
                crc = (uint16_t)((crc >> 1) ^ 0xA001);
            } else {
                crc >>= 1;
            }
        }
    }
    return crc;
}

void update_application(uint32_t app_address)
{
	uint8_t is_last_packet = 0, prev_packet_num = 63, packet_cnt = 0;
	uint8_t flash_write_num;
	uint8_t parsed_packet_num;
	uint16_t parsed_packet_crc;
	uint16_t flash_packet_header;
	static uint32_t flash_payload_buf[255] = { 0, };	// flash에 write할 바이너리 데이터 버퍼

	uint32_t current_flash_addr = app_address; 
    uint32_t total_received_bytes = 0;
    uint16_t total_packets = 0;

	LOG_OTA("Updating Application Binary Image...");

	gpio_set_mode(GPIOD, 4, GPIO_MODE_OUTPUT);
	gpio_set_ospeed(GPIOD, 4, GPIO_OSPEED_VH);
	gpio_set_pupd(GPIOD, 4, GPIO_PUPD_NONE);

	// Application flash sector erase (0x0801 0000)
	flash_unlock();
	LOG_OK("Flash unlocked.");

	if (flash_erase(4) < 0) {
		LOG_ERROR("Flash Erase Failed.");
	}
	LOG_OK("Flash sector 4 erased.\r\n");

	while (!is_last_packet) {
		// 1. 버퍼 인덱스 0 초기화 후 수신가능 신호 전달
		spi_recv_idx = 0;
		spi_recv_cplt_flag = 0;

		gpio_write_pin(GPIOD, 4, 1);

		// 2. 1024 bytes 패킷 수신 후 버퍼에 저장
		while (!spi_recv_cplt_flag) {
			__asm__ volatile ("WFI");
		}

		// 2.5. 필요한 데이터들 파싱 (패킷 번호, 마지막 패킷 여부, 유효 데이터 길이, CRC)
		//		패킷 번호 			  -> 패킷 순서가 다를 경우 예외 처리 (1부터 시작)
		//		마지막 패킷 여부 데이터 -> 5번 루프 탈출조건
		//		유효 데이터 길이 	   -> 4번 반복문 반복 횟수 (flash_write_num)
		//		CRC 				 -> 3번 무결성 검사에서 대조
		flash_packet_header = (uint16_t)((spi_recv_buf[0] << 8) | spi_recv_buf[1]);
		parsed_packet_num = (uint8_t)((flash_packet_header & (0x3F << 10)) >> 10);
		is_last_packet = (uint8_t)((flash_packet_header & (1 << 8)) >> 8);
		flash_write_num = (uint8_t)(flash_packet_header & (0xFF));

		// 8bit 배열을 32bit pointer로 casting
		volatile uint32_t *raw_payload_32 = (volatile uint32_t *)&spi_recv_buf[2];

		for (int i= 0; i < flash_write_num; i++) {
			flash_payload_buf[i] = raw_payload_32[i];
		}

		parsed_packet_crc = *(uint16_t *)&spi_recv_buf[1022];
		//parsed_packet_crc = (uint16_t)((spi_recv_buf[1022] << 8) | spi_recv_buf[1023]);

		//printf("%d %d %d %x\r\n", parsed_packet_num, is_last_packet, flash_write_num, parsed_packet_crc);

		// 3. 패킷 무결성 검사 (패킷 순서, CRC 검사 확인 후 필요하다면 패킷 재전송 요청)
		if (parsed_packet_num == (prev_packet_num + 1) % 64) {
			prev_packet_num = parsed_packet_num;
		}
		else {
			uart_write(UART3, "[ERROR] Packet Unordered Error.\r\n");
			while (1);
		}

		if (parsed_packet_crc == calculate_crc16(spi_recv_buf, 1022)) {
			printf("[ OK ] %d Packet CRC Verification success! Packet is valid.\r\n", ++packet_cnt);
		}
		else {
			uart_write(UART3, "[ERROR] Packet CRC Verification failed.\r\n");
			printf("<%d %d>\r\n", parsed_packet_crc, calculate_crc16(spi_recv_buf, 1022));
			while (1);
		}

		// 4. 4 bytes 씩 최대 255번 flash에 write (flash write하는 동안 interrupt off)
		__asm__ volatile ("cpsid i");

		for (uint8_t i = 0; i < flash_write_num; i++) {
			flash_write_word(current_flash_addr + (4 * i), flash_payload_buf[i]);
		}

		__asm__ volatile ("cpsie i");

		current_flash_addr += (flash_write_num * 4);
		total_received_bytes += (flash_write_num * 4);
		total_packets++;

		// 5. 모든 바이너리를 flash에 쓸 동안 1 ~ 4 반복

		// 1024 bytes 패킷을 flash에 쓸 때마다 ok 로그 메세지 출력
		LOG_OK("%d Packet programmed.", packet_cnt);
	}

	flash_lock();
	LOG_OK("Flash locked.");
	LOG_OTA("Update Complete. (Total: %ld Bytes / %d Packets)\r\n", total_received_bytes, total_packets);
}

void crc_check_image(void)
{
	//Delay(2000);
	LOG_INFO("Calculated CRC32: 0x... | Expected CRC32: 0x...");
}

void spi_rx_handler(SPI_x *SPIx, uint8_t data)
{
	if (SPIx == SPI1) {
		if (spi_recv_idx == 0) {
			// 수신가능 신호 off
			gpio_write_pin(GPIOD, 4, 0);
		}

		if (spi_recv_idx < 1024) {
			spi_recv_buf[spi_recv_idx++] = data;
		}

		if (spi_recv_idx == 1024) {
			spi_recv_cplt_flag = 1;
		}
	}
}

void spi_ovr_handler(SPI_x *SPIx, uint8_t data)
{
	if (SPIx == SPI1) {
		uart_write(UART3, "[ERROR] SPI Over Run Interrupt Occured.\r\n");
		while (1);
	}
}