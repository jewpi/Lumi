#ifndef __RCC_H__
#define __RCC_H__

typedef struct RCC_TYPEDEF {
	uint32_t CR;
	uint32_t PLLCFGR;
	uint32_t CFGR;
} RCC_TypeDef;

#define RCC_BASE 0x40023800
#define RCC ((RCC_TypeDef *)RCC_BASE)

#define RCC_AHB1_CLOCK_RST (*(volatile uint32_t *)0x40023810)
#define RCC_APB1_CLOCK_RST (*(volatile uint32_t *)0x40023820)
#define RCC_APB2_CLOCK_RST (*(volatile uint32_t *)0x40023824)

#define RCC_AHB1_CLOCK_ER (*(volatile uint32_t *)0x40023830)
#define RCC_APB1_CLOCK_ER (*(volatile uint32_t *)0x40023840)
#define RCC_APB2_CLOCK_ER (*(volatile uint32_t *)0x40023844)

/* GPIO */
#define GPIOA_AHB1_CLOCK_ER_VAL (1 << 0)
#define GPIOB_AHB1_CLOCK_ER_VAL (1 << 1)
#define GPIOC_AHB1_CLOCK_ER_VAL (1 << 2)
#define GPIOD_AHB1_CLOCK_ER_VAL (1 << 3)
#define GPIOE_AHB1_CLOCK_ER_VAL (1 << 4)
#define GPIOF_AHB1_CLOCK_ER_VAL (1 << 5)
#define GPIOG_AHB1_CLOCK_ER_VAL (1 << 6)
#define GPIOH_AHB1_CLOCK_ER_VAL (1 << 7)
#define GPIOI_AHB1_CLOCK_ER_VAL (1 << 8)

/* DMA */
#define DMA1_AHB1_CLOCK_ER_VAL	(1 << 21)

/* APB1 */
#define TIM2_APB1_CLOCK_ER_VAL  (1 << 0)
#define TIM3_APB1_CLOCK_ER_VAL  (1 << 1)
#define TIM4_APB1_CLOCK_ER_VAL  (1 << 2)
#define TIM5_APB1_CLOCK_ER_VAL  (1 << 3)
#define UART3_APB1_CLOCK_ER_VAL (1 << 18)

/* APB2 */
#define TIM1_APB2_CLOCK_ER_VAL	 (1 << 0)
#define TIM8_APB2_CLOCK_ER_VAL   (1 << 1)
#define ADC1_APB2_CLOCK_ER_VAL	 (1 << 8)
#define SPI1_APB2_CLOCK_ER_VAL   (1 << 12)
#define SYSCFG_APB2_CLOCK_ER_VAL (1 << 14)
#define TIM9_APB2_CLOCK_ER_VAL   (1 << 16)

#endif
