#ifndef __TIMER_H__
#define __TIMER_H__

#include <stdint.h>
#include "gpio.h"

typedef struct TIM_X {
    uint32_t CR1;       // 0x00
    uint32_t CR2;       // 0x04
    uint32_t SMCR;      // 0x08
    uint32_t DIER;      // 0x0C
    uint32_t SR;        // 0x10
    uint32_t EGR;       // 0x14
    uint32_t CCMR1;     // 0x18
    uint32_t CCMR2;     // 0x1C
    uint32_t CCER;      // 0x20
    uint32_t CNT;       // 0x24
    uint32_t PSC;       // 0x28
    uint32_t ARR;       // 0x2C
    uint32_t RCR;       // 0x30
    uint32_t CCR1;      // 0x34
    uint32_t CCR2;      // 0x38
    uint32_t CCR3;      // 0x3C
    uint32_t CCR4;      // 0x40
    uint32_t BDTR;      // 0x44
    uint32_t DCR;       // 0x48
    uint32_t DMAR;      // 0x4C
} TIM_x;

#define TIM1_BASE 0x40010000
#define TIM2_BASE 0x40000000
#define TIM3_BASE 0x40000400
#define TIM4_BASE 0x40000800
#define TIM5_BASE 0x40000C00
#define TIM6_BASE 0x40001000
#define TIM7_BASE 0x40001400
#define TIM8_BASE 0x40010400
#define TIM9_BASE 0x40014000
#define TIM10_BASE 0x40014400
#define TIM11_BASE 0x40014800

#define TIM1 ((TIM_x *)TIM1_BASE)
#define TIM2 ((TIM_x *)TIM2_BASE)
#define TIM3 ((TIM_x *)TIM3_BASE)
#define TIM4 ((TIM_x *)TIM4_BASE)
#define TIM5 ((TIM_x *)TIM5_BASE)
#define TIM6 ((TIM_x *)TIM6_BASE)
#define TIM7 ((TIM_x *)TIM7_BASE)
#define TIM8 ((TIM_x *)TIM8_BASE)
#define TIM9 ((TIM_x *)TIM9_BASE)
#define TIM10 ((TIM_x *)TIM10_BASE)
#define TIM11 ((TIM_x *)TIM11_BASE)

#define TIM2_UI_FLAG_CLEAR() TIM2->SR &= ~(1 << 0)

// TIM alternate function
#define TIM1_2_PIN_AF (1)
#define TIM3_5_PIN_AF (2)
#define TIM8_11_PIN_AF (3)

/* TIM register setting */
#define TIM_DIER_UIE 	     (1 << 0)	// Update Interrupt Enable
#define TIM_SR_UIF           (1 << 0)	// Update Interrupt Flag
#define TIM_EGR_UG			 (1 << 0)	// Update Generation
#define TIM_CR1_COUNT_ENABLE (1 << 0)
#define TIM_CR1_ONE_PULSE    (1 << 3)
#define TIM_CR1_ARPE         (1 << 7)   // ARR Preload Enable

/* TIM interface prototypes */
void timer_init(TIM_x *tim, uint16_t psc, uint32_t arr);
void timer_start(TIM_x *tim);
void timer_start_IT(TIM_x *tim);
void timer_start_PWM(TIM_x *tim, uint8_t channel, GPIO_Port *gpiox, uint8_t pin, uint32_t duty);
void timer_stop(TIM_x *tim);
void timer_deinit(TIM_x *tim);
void timer3_encoder_init(void);
void timer5_encoder_init(void);

#endif
