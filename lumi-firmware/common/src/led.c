#include <stdint.h>
#include "gpio.h"
#include "led.h"
#include "rcc.h"

void led_setup(void)
{
	RCC_AHB1_CLOCK_ER |= GPIOA_AHB1_CLOCK_ER_VAL;

	// set output mode
	GPIOA->MODE &= ~(0x03 << (LED_PIN1 * 2));
	GPIOA->MODE |= GPIO_MODE_OUTPUT << (LED_PIN1 * 2);

	GPIOA->MODE &= ~(0x03 << (LED_PIN2 * 2));
    GPIOA->MODE |= GPIO_MODE_OUTPUT << (LED_PIN2 * 2);

	// set pull-up mode
	// HIGH : led off
	// LOW  : led on
	GPIOA->PUPD &= ~(0x03 << (LED_PIN1 * 2));
	GPIOA->PUPD |= GPIO_PUPD_PU << (LED_PIN1 * 2);

	GPIOA->PUPD &= ~(0x03 << (LED_PIN2 * 2));
    GPIOA->PUPD |= GPIO_PUPD_PU << (LED_PIN2 * 2);
}

void led_on(void)
{
	GPIOA->BSRR |= 1 << (LED_PIN1 + 16);
	GPIOA->BSRR |= 1 << (LED_PIN2 + 16);
}

void led_off(void)
{
	GPIOA->BSRR |= 1 << LED_PIN1;
	GPIOA->BSRR |= 1 << LED_PIN2;
}

void led_toggle(void)
{
	if ((GPIOA->ODR & (1 << LED_PIN1)) == (1 << LED_PIN1))
		led_on();
	else
		led_off();
}
