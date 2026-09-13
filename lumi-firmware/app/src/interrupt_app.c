#include <stdint.h>
#include "timer.h"
#include "exti.h"
#include "spi.h"
#include "dma.h"
#include "includes.h"

uint8_t button_flag;
uint8_t target_rpm_update_flag;
uint8_t uart_idle_flag;

// volatile uint32_t enc_pulse_edge_cnt = 0;
// volatile int32_t enc_pos_cnt = 0;
volatile int32_t target_rpm = 0;

extern void (*spi_rx_callback)(SPI_x *spi, uint8_t data);
extern void (*spi_ovr_callback)(SPI_x *spi, uint8_t data);

extern OS_EVENT *g_cmd_vel_sem;
extern OS_EVENT *HCSR04DurationMbox;
extern OS_EVENT *ButtonSem;

#define ENCODER_A_INPUT_GPIO_Port GPIOC
#define ENCODER_A_INPUT_Pin 7

#define ENCODER_B_INPUT_GPIO_Port GPIOC
#define ENCODER_B_INPUT_Pin 9

extern uint8_t g_cmd_vel_buffer[8];
volatile uint32_t rx_count = 0;

void isr_tim4(void)
{
	OSIntEnter();

	if (TIM4->SR & (1 << 2)) {
		TIM4->SR &= ~(1 << 2);

		OSMboxPost(HCSR04DurationMbox, (void *)TIM4->CCR2);
	}

	OSIntExit();
}

void isr_exti4(void)
{
	INT8U err;

	OSIntEnter();

	EXTI->PR |= 1 << 4;
	button_flag = 1;

	OSSemPost(ButtonSem);

	//OSFlagPost(MissileEventFlags, FLAG_PROP_OK, OS_FLAG_SET, &err);
	//SoftwareReset();

	OSIntExit();
}

void isr_spi1(void)
{
	uint32_t sr = SPI1->SR;
	uint8_t recv_data;

	OSIntEnter();

	if (sr & SPI_SR_RX_NOTEMPTY) {
		recv_data = (uint8_t)SPI1->DR;
		
		if (spi_rx_callback) {
			spi_rx_callback(SPI1, recv_data);
		}
	}

	if (sr & SPI_SR_OVR) {
		recv_data = (uint8_t)SPI1->DR;
		(void)SPI1->SR;

		if (spi_ovr_callback) {
			spi_ovr_callback(SPI1, recv_data);
		}
	}

	OSIntExit();
}

void isr_dma1_stream1(void)
{
    OSIntEnter();

    // TCIF1(완료) 또는 TEIF1(에러) 플래그가 감지된 경우 처리
    if (DMA1->LISR & (DMA_LISR_TCIF1 | DMA_LISR_TEIF1))
    {
        // 정상 수신 여부 확인
        uint8_t is_tc = (DMA1->LISR & DMA_LISR_TCIF1) ? 1 : 0;

        // 1. 모든 플래그 클리어
        DMA1->LIFCR = (DMA_LIFCR_CTCIF1 | DMA_LIFCR_CHTIF1 | 
                       DMA_LIFCR_CTEIF1 | DMA_LIFCR_CDMEIF1 | DMA_LIFCR_CFEIF1);

        // 2. DMA 비활성화 및 정지 대기
        DMA1->S[1].CR &= ~DMA_SxCR_EN;
        while (DMA1->S[1].CR & DMA_SxCR_EN); 

        // 3. 정확한 패킷 수신 크기 복구
        DMA1->S[1].NDTR = sizeof(g_cmd_vel_buffer);

        // 4. DMA Stream 재활성화
        DMA1->S[1].CR |= DMA_SxCR_EN;

        // 5. 에러 없이 정상 완료(TC)된 경우에만 태스크 신호 전달
        if (is_tc && (g_cmd_vel_sem != NULL)) {
            OSSemPost(g_cmd_vel_sem);
        }
    }

    OSIntExit();
}

// void isr_dma1_stream1(void)
// {
//     OSIntEnter();

//     if (DMA1->LISR & DMA_LISR_TCIF1)
//     {
// 		//led_toggle();
//         // 1. 인터럽트 플래그 클리어
//         DMA1->LIFCR = (DMA_LIFCR_CTCIF1 | DMA_LIFCR_CHTIF1 | 
//                        DMA_LIFCR_CTEIF1 | DMA_LIFCR_CDMEIF1 | DMA_LIFCR_CFEIF1);

//         // 2. DMA Stream 비활성화 및 완전히 꺼질 때까지 대기
//         DMA1->S[1].CR &= ~DMA_SxCR_EN;
//         while (DMA1->S[1].CR & DMA_SxCR_EN); 

//         // 3. NDTR 재설정 (EN이 꺼진 상태에서만 값이 변경됨)
//         DMA1->S[1].NDTR = sizeof(g_cmd_vel_buffer);

//         // 4. DMA Stream 재활성화
//         DMA1->S[1].CR |= DMA_SxCR_EN;

//         // 5. Task 깨우기
//         if (g_cmd_vel_sem != NULL) {
//             OSSemPost(g_cmd_vel_sem);
//         }
//     }

//     OSIntExit();
// }

// void isr_uart3(void)
// {
//     volatile uint32_t reg;

//     OSIntEnter();

//     reg = UART3->SR;

// 	// IDLE 인터럽트
// 	if (reg & UART_SR_IDLE && UART3->CR1 & UART_CR1_IDLEIE) {
// 		// IDLE 인터럽트 플래그 clear
// 		volatile uint32_t dummy = UART3->SR;
// 		dummy = UART3->DR;
// 		(void)dummy;

// 		uint16_t current_ndtr = DMA1->S[1].NDTR;
// 		uint16_t packet_size = sizeof(g_cmd_vel_buffer);

// 		uart_idle_flag = 1;

// 		// DMA의 circular 설정으로 NDTR 레지스터가 reload 되어 있을 수 있음.
// 		if (current_ndtr == 0 || current_ndtr == packet_size) {
// 			// 데이터 파싱
// 			//parse_cmd_vel_packet(g_cmd_vel_buffer);
// 			memcpy(&linear_x, &g_cmd_vel_buffer[0], sizeof(float));
// 			memcpy(&angular_z, &g_cmd_vel_buffer[4], sizeof(float));

// 			rx_count++;

// 			// 라즈베리파이로부터 cmd_vel 수신 시 ComputeTargetRpmTask wake up
// 			if (g_cmd_vel_sem != NULL) {
// 				OSSemPost(g_cmd_vel_sem);
// 			}
// 		}
// 		else {
// 			// 데이터 유실이 발생한 경우 DMA 카운터 리셋
// 			DMA1->S[1].CR &= ~DMA_SxCR_EN;
// 			while (DMA1->S[1].CR & DMA_SxCR_EN);

// 			DMA1->S[1].NDTR = packet_size;

// 			DMA1->S[1].CR |= DMA_SxCR_EN;
// 		}
// 	}

	
//     OSIntExit();
// }