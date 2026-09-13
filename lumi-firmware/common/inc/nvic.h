#ifndef __NVIC_H__
#define __NVIC_H__

#define NVIC_ISER_BASE (0xE000E100)
#define NVIC_ICER_BASE (0xE000E180)
#define NVIC_IPRI_BASE (0xE000E400)
#define SCB_SHPRI_BASE (0xE000ED18)

#define NVIC_SYSTICK_IRQN      (-1)
#define NVIC_EXTI0_IRQN        (6)
#define NVIC_EXTI1_IRQN        (7)
#define NVIC_EXTI2_IRQN        (8)
#define NVIC_EXTI3_IRQN        (9)
#define NVIC_EXTI4_IRQN        (10)
#define NVIC_DMA1_STREAM1_IRQN (12)
#define NVIC_EXTI9_5_IRQN  	   (23)
#define NVIC_EXTI15_10_IRQN    (40)
#define NVIC_TIM2_IRQN         (28)
#define NVIC_TIM4_IRQN         (30)
#define NVIC_SPI1_IRQN         (35)
#define NVIC_UART3_IRQN		   (39)

static inline void nvic_irq_enable(uint8_t n)
{
	int i = n / 32;
	volatile uint32_t *nvic_iser = (volatile uint32_t *)(NVIC_ISER_BASE + 4 * i);

	*nvic_iser |= 1 << (n % 32);
}

static inline void nvic_irq_disable(uint8_t n)
{
	int i = n / 32;
	volatile uint32_t *nvic_icer = (volatile uint32_t *)(NVIC_ICER_BASE + 4 * i);

	*nvic_icer |= 1 << (n % 32);
}

static inline void nvic_irq_setprio(uint8_t n, uint8_t prio)
{
	volatile uint8_t *nvic_ipri = (volatile uint8_t *)(NVIC_IPRI_BASE + n);

	*nvic_ipri = (uint8_t)(prio << 4);
}

#endif
