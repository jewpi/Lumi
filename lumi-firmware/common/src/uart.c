#include <stdint.h>
#include "uart.h"
#include "gpio.h"
#include "system.h"
#include "rcc.h"
#include "nvic.h"
#include "dma.h"

// PB10, PB11
#define UART3_TX_PIN (10)
#define UART3_RX_PIN (11)

// TX : PB10
// RX : PB11
static void uart3_pin_setup(void)
{
	uint32_t reg;

	RCC_AHB1_CLOCK_ER |= GPIOB_AHB1_CLOCK_ER_VAL;

	// set alternate function mode
	reg = GPIOB->MODE & ~(0x03 << (UART3_RX_PIN * 2));
	GPIOB->MODE = reg | 0x02 << (UART3_RX_PIN * 2);

	reg = GPIOB->MODE & ~(0x03 << (UART3_TX_PIN * 2));
	GPIOB->MODE = reg | 0x02 << (UART3_TX_PIN * 2);

	// select AF7(USART1..3)
	reg = GPIOB->AFRH & ~(0X0F << ((UART3_RX_PIN - 8) * 4));
	GPIOB->AFRH = reg | (UART3_PIN_AF << ((UART3_RX_PIN - 8) * 4));

	reg = GPIOB->AFRH & ~(0X0F << ((UART3_TX_PIN - 8) * 4));
	GPIOB->AFRH = reg | (UART3_PIN_AF << ((UART3_TX_PIN - 8) * 4));
}

void uart_init(UART_x *uart, uint32_t bitrate)
{
	uart3_pin_setup();

	RCC_APB1_CLOCK_ER |= UART3_APB1_CLOCK_ER_VAL;

	uart->CR1 |= UART_CR1_TX_ENABLE;		// transmit enable
	uart->BRR = PCLK1 / bitrate;			// bitrate setting
	uart->CR1 &= ~UART_CR1_WORD_LEN;		// select 8bits len
	uart->CR1 &= ~UART_CR1_PARITY_ENABLED;	// parity disable
	uart->CR2 &= ~UART_CR2_STOPBITS;		// select 1 stop bit
	uart->CR1 |= UART_CR1_UART_ENABLE;		// uart enable
}

void uart3_dma_rx_init(uint8_t *rx_dma_buffer, uint16_t packet_size)
{
    RCC_AHB1_CLOCK_ER |= DMA1_AHB1_CLOCK_ER_VAL;

    // 1. DMA1 Stream 1 비활성화 및 해제 대기
    DMA1->S[1].CR &= ~DMA_SxCR_EN;
    while (DMA1->S[1].CR & DMA_SxCR_EN);

    // 2. DMA mem/peripheral 주소 및 버퍼 크기 지정
    DMA1->S[1].PAR = (uint32_t)&(UART3->DR);
    DMA1->S[1].M0AR = (uint32_t)rx_dma_buffer;
    DMA1->S[1].NDTR = packet_size;

    // 3. DMA Stream 설정 
    // - Channel 4 선택
    // - Memory Address Increment (MINC)
    // - Transfer Complete Interrupt Enable (TCIE) 추가
    // - Normal Mode (CIRC 비트 제거)
    DMA1->S[1].CR = 0;
    DMA1->S[1].CR |= (4 << DMA_SxCR_CHSEL_Pos);
    DMA1->S[1].CR |= DMA_SxCR_MINC;
    DMA1->S[1].CR |= (DMA_SxCR_TCIE | DMA_SxCR_TEIE); // DMA Transfer Complete 인터럽트 허용

    // 4. DMA Stream 활성화
    DMA1->S[1].CR |= DMA_SxCR_EN;

    // 5. UART3 설정 (IDLEIE 제거, RX 및 DMA 수신만 활성화)
    UART3->CR1 |= UART_CR1_RX_ENABLE;
    UART3->CR3 |= UART_CR3_DMAR;
    // UART3->CR1 |= UART_CR1_IDLEIE; // IDLE 인터럽트는 불필요하므로 제거

    // 6. NVIC 설정 (UART3 IRQ 대신 DMA1 Stream 1 IRQ 등록)
    // DMA1 Stream 1 IRQ 번호(일반적으로 NVIC_DMA1_STREAM1_IRQN)로 변경해 주세요.
    nvic_irq_enable(NVIC_DMA1_STREAM1_IRQN);
    nvic_irq_setprio(NVIC_DMA1_STREAM1_IRQN, 6);
}

// void uart3_dma_rx_init(uint8_t *rx_dma_buffer, uint16_t packet_size)
// {
// 	RCC_AHB1_CLOCK_ER |= DMA1_AHB1_CLOCK_ER_VAL;

// 	// DMA1 Stream 1 비활성화
// 	DMA1->S[1].CR &= ~DMA_SxCR_EN;
// 	while (DMA1->S[1].CR & DMA_SxCR_EN);

// 	// DMA mem/peripheral 주소 및 버퍼 크기 지정
// 	DMA1->S[1].PAR = (uint32_t)&(UART3->DR);
// 	DMA1->S[1].M0AR = (uint32_t)rx_dma_buffer;
// 	DMA1->S[1].NDTR = packet_size;

// 	// DMA Stream 설정 (Channel 4, Memory Increment, Circular Mode)
// 	DMA1->S[1].CR = 0;
// 	DMA1->S[1].CR |= (4 << DMA_SxCR_CHSEL_Pos);
// 	DMA1->S[1].CR |= DMA_SxCR_MINC;
// 	DMA1->S[1].CR |= DMA_SxCR_CIRC;

// 	// DMA Stream 활성화
// 	DMA1->S[1].CR |= DMA_SxCR_EN;

// 	// UART 추가 설정 (RX 활성화, DMA 수신 연동, IDLE 인터럽트)
// 	UART3->CR1 |= UART_CR1_RX_ENABLE;
// 	UART3->CR3 |= UART_CR3_DMAR;
// 	UART3->CR1 |= UART_CR1_IDLEIE;

// 	nvic_irq_enable(NVIC_UART3_IRQN);
// 	nvic_irq_setprio(NVIC_UART3_IRQN, 6);
// }

void uart3_dma_tx_init(void)
{
    // 1. DMA1 클럭 활성화 (이미 RX에서 켰겠지만 안전하게 재확인)
    RCC_AHB1_CLOCK_ER |= DMA1_AHB1_CLOCK_ER_VAL;

    // 2. DMA1 Stream 3 비활성화
    DMA1->S[3].CR &= ~DMA_SxCR_EN;
    while (DMA1->S[3].CR & DMA_SxCR_EN);

    // 3. DMA Peripheral 주소 설정 (UART3 데이터 레지스터)
    DMA1->S[3].PAR = (uint32_t)&(UART3->DR);

    // 4. DMA Stream 3 기본 설정 (Channel 4, Memory Increment, Dir: Memory-to-Peripheral)
    DMA1->S[3].CR = 0;
    DMA1->S[3].CR |= (4 << DMA_SxCR_CHSEL_Pos);      // Channel 4 선택
    DMA1->S[3].CR |= DMA_SxCR_MINC;                  // Memory 주소 자동 증가
    DMA1->S[3].CR |= (1 << DMA_SxCR_DIR_Pos);        // 방향: Memory -> Peripheral (01)
    
    // ※ 송신은 Circular 모드를 켜지 않습니다 (Normal 모드 유지)

    // 5. UART3 TX 활성화 및 UART3 DMA 송신(DMAT) 연동
    UART3->CR1 |= UART_CR1_TX_ENABLE; // (1 << 3) 또는 USART_CR1_TE
    UART3->CR3 |= UART_CR3_DMAT;      // DMA Transmitter Enable (1 << 7)
}

void uart3_dma_send_packet(uint8_t *tx_buffer, uint16_t length)
{
    // 1. 이전 DMA 송신이 아직 끝나지 않았다면 Skip (충돌 방지)
    if (DMA1->S[3].CR & DMA_SxCR_EN) {
        return;
    }

    // 2. 이전 전송 완료 플래그(TCIF) Clear (DMA1 Stream 3용 인터럽트/이벤트 플래그)
    // DMA1->LIFCR 의 Stream 3 TCIF 비트 클리어 (Bit 27)
    DMA1->LIFCR = (1 << 27); 

    // 3. 전송할 데이터 메모리 주소 및 길이 지정
    DMA1->S[3].M0AR = (uint32_t)tx_buffer;
    DMA1->S[3].NDTR = length;

    // 4. DMA Stream 3 활성화 (송신 시작!)
    DMA1->S[3].CR |= DMA_SxCR_EN;
}

void uart_recv_it_onoff(UART_x *uart, uint8_t enable)
{
	if (enable) {
		uart->CR1 |= (UART_CR1_RX_ENABLE | UART_CR1_RXNEIE);
		__asm__ volatile ("DMB");

		nvic_irq_enable(NVIC_UART3_IRQN);
		nvic_irq_setprio(NVIC_UART3_IRQN, 6);
	}
	else {
		nvic_irq_disable(NVIC_UART3_IRQN);
		
		uart->CR1 &= ~(UART_CR1_RX_ENABLE | UART_CR1_RXNEIE);
		__asm__ volatile ("DMB");
	}
}

void uart_write(UART_x *uart, const char *data)
{
	const char *p = data;
	volatile uint32_t reg;

	while (*p) {
		do {
			reg = uart->SR;
		} while ((reg & UART_SR_TXE) == 0);

		uart->DR = *p;
		p++;
	}
}

void uart_deinit(UART_x *uart)
{
	;
}

/* printf stub function */
int _write(int fd, char *ptr, int len)
{
	for (int i = 0; i < len; ++i) {
		while (!(UART3->SR & UART_SR_TXE));

		UART3->DR = (uint8_t)ptr[i];
	}

	return len;
}