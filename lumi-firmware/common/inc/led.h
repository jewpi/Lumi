#ifndef __LED_H__
#define __LED_H__

#include "gpio.h"

// PA6, PA7 led
#define LED_PIN1 6
#define LED_PIN2 7

void led_setup(void);
void led_on(void);
void led_off(void);
void led_toggle(void);

#endif
