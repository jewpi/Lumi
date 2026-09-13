#include <stdint.h>
#include "timer.h"
#include "nvic.h"
#include "rcc.h"

static void timer_reset(TIM_x *tim)
{
	if (tim == TIM1) {
		RCC_APB2_CLOCK_RST |= TIM1_APB2_CLOCK_ER_VAL;
		__asm__ volatile ("DMB");
		RCC_APB2_CLOCK_RST &= ~TIM1_APB2_CLOCK_ER_VAL;
	}

	if (tim == TIM2) {
		RCC_APB1_CLOCK_RST |= TIM2_APB1_CLOCK_ER_VAL;
		__asm__ volatile ("DMB");
		RCC_APB1_CLOCK_RST &= ~TIM2_APB1_CLOCK_ER_VAL;
	}

	if (tim == TIM3) {
		RCC_APB1_CLOCK_RST |= TIM3_APB1_CLOCK_ER_VAL;
		__asm__ volatile ("DMB");
		RCC_APB1_CLOCK_RST &= ~TIM3_APB1_CLOCK_ER_VAL;
	}

	if (tim == TIM4) {
		RCC_APB1_CLOCK_RST |= TIM4_APB1_CLOCK_ER_VAL;
		__asm__ volatile ("DMB");
		RCC_APB1_CLOCK_RST &= ~TIM4_APB1_CLOCK_ER_VAL;
	}

	if (tim == TIM5) {
		RCC_APB1_CLOCK_RST |= TIM5_APB1_CLOCK_ER_VAL;
		__asm__ volatile ("DMB");
		RCC_APB1_CLOCK_RST &= ~TIM5_APB1_CLOCK_ER_VAL;
	}

	if (tim == TIM8) {
		RCC_APB2_CLOCK_RST |= TIM8_APB2_CLOCK_ER_VAL;
		__asm__ volatile ("DMB");
		RCC_APB2_CLOCK_RST &= ~TIM8_APB2_CLOCK_ER_VAL;
	}

	if (tim == TIM9) {
		RCC_APB2_CLOCK_RST |= TIM9_APB2_CLOCK_ER_VAL;
		__asm__ volatile ("DMB");
		RCC_APB2_CLOCK_RST &= ~TIM9_APB2_CLOCK_ER_VAL;
	}
}

static void timer_enable_clock(TIM_x *tim)
{
	if (tim == TIM1) {
		timer_reset(tim);
		RCC_APB2_CLOCK_ER |= TIM1_APB2_CLOCK_ER_VAL;
	}

	if (tim == TIM2) {
		timer_reset(tim);
		RCC_APB1_CLOCK_ER |= TIM2_APB1_CLOCK_ER_VAL;
	}

	if (tim == TIM3) {
		timer_reset(tim);
		RCC_APB1_CLOCK_ER |= TIM3_APB1_CLOCK_ER_VAL;
	}

	if (tim == TIM4) {
		timer_reset(tim);
		RCC_APB1_CLOCK_ER |= TIM4_APB1_CLOCK_ER_VAL;
	}

	if (tim == TIM5) {
		timer_reset(tim);
		RCC_APB1_CLOCK_ER |= TIM5_APB1_CLOCK_ER_VAL;
	}

	if (tim == TIM8) {
		timer_reset(tim);
		RCC_APB2_CLOCK_ER |= TIM8_APB2_CLOCK_ER_VAL;
	}

	if (tim == TIM9) {
		timer_reset(tim);
		RCC_APB2_CLOCK_ER |= TIM9_APB2_CLOCK_ER_VAL;
	}

	__asm__ volatile ("DMB");
}

static void timer_enable_interrupt(TIM_x *tim)
{
	if (tim == TIM2) {
		nvic_irq_enable(NVIC_TIM2_IRQN);
    	nvic_irq_setprio(NVIC_TIM2_IRQN, 6);
	}

	tim->DIER |= TIM_DIER_UIE;
}

static void timer_pwm_channel_config(TIM_x *tim, uint8_t channel, uint32_t duty)
{
	if (duty > tim->ARR) {
		duty = tim->ARR;
	}

	if (channel == 1) {
		// Output Compare disable (CCER)
		tim->CCER &= ~(1 << 0);
		__asm__ volatile ("DMB");
		
		// channel Output 설정, PWM mode 1, CCR Preload Enable (CCMR)
		tim->CCMR1 &= ~(0x3 << 0);
		tim->CCMR1 |= (0x6 << 4);
		tim->CCMR1 |= (1 << 3);

		// Active High, Output Enable (CCER)
		tim->CCER &= ~(1 << 1);
		tim->CCER |= (1 << 0);

		// Set Initial Duty (CCR)
		tim->CCR1 = duty;
	}
	else if (channel == 2) {
		// Output Compare disable (CCER)
		tim->CCER &= ~(1 << 4);
		__asm__ volatile ("DMB");

		// channel Output 설정, PWM mode 1, CCR Preload Enable (CCMR)
		tim->CCMR1 &= ~(0x3 << 8);
		tim->CCMR1 |= (0x6 << 12);
		tim->CCMR1 |= (1 << 11);

		// Active High, Output Enable (CCER)
		tim->CCER &= ~(1 << 5);
		tim->CCER |= (1 << 4);

		// Set Initial Duty (CCR)
		tim->CCR2 = duty;
	}
	else if (channel == 3) {
		// Output Compare disable (CCER)
		tim->CCER &= ~(1 << 8);
		__asm__ volatile ("DMB");

		// channel Output 설정, PWM mode 1, CCR Preload Enable (CCMR)
		tim->CCMR2 &= ~(0x3 << 0);
		tim->CCMR2 |= (0x6 << 4);
		tim->CCMR2 |= (1 << 3);

		// Active High, Output Enable (CCER)
		tim->CCER &= ~(1 << 9);
		tim->CCER |= (1 << 8);

		// Set Initial Duty (CCR)
		tim->CCR3 = duty;
	}
	else if (channel == 4) {
		// Output Compare disable (CCER)
		tim->CCER &= ~(1 << 12);
		__asm__ volatile ("DMB");

		// channel Output 설정, PWM mode 1, CCR Preload Enable (CCMR)
		tim->CCMR2 &= ~(0x3 << 8);
		tim->CCMR2 |= (0x6 << 12);
		tim->CCMR2 |= (1 << 11);

		// Active High, Output Enable (CCER)
		tim->CCER &= ~(1 << 13);
		tim->CCER |= (1 << 12);

		// Set Initial Duty (CCR)
		tim->CCR4 = duty;
	}
}

void timer_init(TIM_x *tim, uint16_t psc, uint32_t arr)
{
	timer_enable_clock(tim);

	tim->CR1 = 0;   // disable timer counter
	tim->PSC = psc;
	tim->ARR = arr;

	/* PSC, ARR 설정을 즉시 하드웨어에 반영 */
	tim->EGR |= TIM_EGR_UG;
	tim->SR &= ~TIM_SR_UIF;

    __asm__ volatile ("DMB");
}

void timer_start(TIM_x *tim)
{
	tim->CR1 |= TIM_CR1_COUNT_ENABLE;
	__asm__ volatile ("DMB");
}

void timer_start_IT(TIM_x *tim)
{
	timer_enable_interrupt(tim);

    tim->CR1 |= TIM_CR1_COUNT_ENABLE;
    __asm__ volatile ("DMB");
}

void timer_start_PWM(TIM_x *tim, uint8_t channel, GPIO_Port *gpiox, uint8_t pin, uint32_t duty)
{
	uint8_t af_num;

    // 1. GPIO mode, ospeed, pull-down 설정
	gpio_set_mode(gpiox, pin, GPIO_MODE_AF);
	gpio_set_ospeed(gpiox, pin, GPIO_OSPEED_VH);
	gpio_set_pupd(gpiox, pin, GPIO_PUPD_PD);
    
    // 2. 해당 핀의 AF 번호 설정 (데이터시트 기반)
	if (tim == TIM1 || tim == TIM2) af_num = TIM1_2_PIN_AF;
	else if (tim == TIM3 || tim == TIM4 || tim == TIM5) af_num = TIM3_5_PIN_AF;
	else af_num = TIM8_11_PIN_AF;

	gpio_set_af(gpiox, pin, af_num);

    // 3. 타이머 채널별 PWM 설정 (CCMR, CCER 등)
    timer_pwm_channel_config(tim, channel, duty);

	// 고급 타이머(TIM1, TIM8)를 위한 MOE 설정
    // 고급 타이머는 메인 출력을 명시적으로 켜줘야 핀으로 신호가 나감.
    if (tim == TIM1 || tim == TIM8) {
        tim->BDTR |= (1 << 15); // MOE (Main Output Enable)
    }

    // 설정값 즉시 반영 (Update Generation)
    tim->EGR |= (1 << 0); // UG 비트: PSC, ARR, CCR 설정을 그림자 레지스터로 즉시 복사

    // 4. 타이머 시작 (ARPE bit를 켜서 ARR값을 버퍼에 저장해 놨다가 다음 루프때 적용)
    tim->CR1 |= TIM_CR1_COUNT_ENABLE | TIM_CR1_ARPE;
	__asm__ volatile ("DMB");
}

void timer_stop(TIM_x *tim)
{
	;
}

void timer_deinit(TIM_x *tim)
{
	;
}

void timer3_encoder_init(void)
{
	// GPIO mode, pull-up, AF 설정
	gpio_set_mode(GPIOC, 6, GPIO_MODE_AF);
	gpio_set_pupd(GPIOC, 6, GPIO_PUPD_PU);
    
	gpio_set_mode(GPIOC, 7, GPIO_MODE_AF);
	gpio_set_pupd(GPIOC, 7, GPIO_PUPD_PU);

	gpio_set_af(GPIOC, 6, TIM3_5_PIN_AF);
	gpio_set_af(GPIOC, 7, TIM3_5_PIN_AF);

	// TIM3 clock enable
	timer_enable_clock(TIM3);

	TIM3->CR1 = 0;   // disable timer counter

	// Encoder Mode 3 설정 (4체배 방식)
	TIM3->SMCR &= ~(0x07);
	TIM3->SMCR |= (3 << 0);

	// channel 1핀과 channel 2핀을 각각 TI1, TI2에 매핑
	TIM3->CCMR1 &= ~((3 << 0) | (3 << 8));
	TIM3->CCMR1 |= ((1 << 0) | (1 << 8));

	// Polarity를 default edge 값으로 설정 (rising edge)
	TIM3->CCER &= ~((1 << 1) | (1 << 3) | (1 << 5) | (1 << 7));

	TIM3->ARR = 0xFFFF;

	// TIM3 구동 시작
	TIM3->CR1 |= (1 << 0);
}

void timer5_encoder_init(void)
{
	// GPIO mode, pull-up, AF 설정
	gpio_set_mode(GPIOA, 0, GPIO_MODE_AF);
	gpio_set_pupd(GPIOA, 0, GPIO_PUPD_PU);
    
	gpio_set_mode(GPIOA, 1, GPIO_MODE_AF);
	gpio_set_pupd(GPIOA, 1, GPIO_PUPD_PU);

	gpio_set_af(GPIOA, 0, TIM3_5_PIN_AF);
	gpio_set_af(GPIOA, 1, TIM3_5_PIN_AF);

	// TIM5 clock enable
	timer_enable_clock(TIM5);

	TIM5->CR1 = 0;   // disable timer counter

	// Encoder Mode 3 설정 (4체배 방식)
	TIM5->SMCR &= ~(0x07);
	TIM5->SMCR |= (3 << 0);

	// channel 1핀과 channel 2핀을 각각 TI1, TI2에 매핑
	TIM5->CCMR1 &= ~((3 << 0) | (3 << 8));
	TIM5->CCMR1 |= ((1 << 0) | (1 << 8));

	// Polarity를 default edge 값으로 설정 (rising edge)
	TIM5->CCER &= ~((1 << 1) | (1 << 3) | (1 << 5) | (1 << 7));

	TIM5->ARR = 0xFFFF;

	// TIM5 구동 시작
	TIM5->CR1 |= (1 << 0);
}