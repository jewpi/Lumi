#include "button.h"
#include "gpio.h"
#include "nvic.h"
#include "exti.h"
#include "rcc.h"

#define BUTTON_PIN (4)

void button_setup(void)
{
	RCC_AHB1_CLOCK_ER |= GPIOE_AHB1_CLOCK_ER_VAL;

	// set input mode
	GPIOE->MODE &= ~(0x03 << (BUTTON_PIN * 2));
	GPIOE->MODE |= GPIO_MODE_INPUT << (BUTTON_PIN * 2);

	// set pull-up
	GPIOE->PUPD &= ~(0x03 << (BUTTON_PIN * 2));
	GPIOE->PUPD |= GPIO_PUPD_PU << (BUTTON_PIN * 2);
		
	// EXTI4 interrupt enable
	RCC_APB2_CLOCK_ER |= SYSCFG_APB2_CLOCK_ER_VAL;		// SYSCFG controller clock on
	//EXTI_CR2 &= ~(0xf);
	//EXTI_CR2 |= (0x4);
	EXTI_CR2 |= EXTI_CR_E << ((BUTTON_PIN % 4) * 4);      // EXTI4에 GPIO PORT E 연결
	nvic_irq_enable(NVIC_EXTI4_IRQN);
	nvic_irq_setprio(NVIC_EXTI4_IRQN, 6);

	// interrupt activate at falling edge
	EXTI->IMR |= 1 << BUTTON_PIN;
	EXTI->EMR |= 1 << BUTTON_PIN;
	EXTI->FTSR |= 1 << BUTTON_PIN;
}

// board에 user key가 pull-up 되어 있다.
// HIGH : button not pressed
// LOW  : button pressed
int get_button_state(void)
{
	return !((GPIOE->IDR & (1 << BUTTON_PIN)) >> BUTTON_PIN);
}
