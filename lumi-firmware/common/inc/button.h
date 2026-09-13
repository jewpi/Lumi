#ifndef __BUTTON_H__
#define __BUTTON_H__

//#define AHB1_CLOCK_ER (*(volatile uint32_t *)0x40023830)
//#define GPIOE_AHB1_CLOCK_ER_VAL (1 << 4)

void button_setup(void);
int get_button_state(void);

#endif
