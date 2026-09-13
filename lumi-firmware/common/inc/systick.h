#ifndef SYSTICK_H_INCLUDED
#define SYSTICK_H_INCLUDED

#include <stdint.h>

#define SYSTICK_BASE  (0xE000E010)
#define SYSTICK_CSR   (*(volatile uint32_t *) (SYSTICK_BASE + 0x00))
#define SYSTICK_RVR   (*(volatile uint32_t *) (SYSTICK_BASE + 0x04))
#define SYSTICK_CVR   (*(volatile uint32_t *) (SYSTICK_BASE + 0x08))
#define SYSTICK_CALIB (*(volatile uint32_t *) (SYSTICK_BASE + 0x0C))

void systick_enable(void);
//void systick_init(void);
void systick_disable(void);
//uint32_t get_tick(void);

//extern uint32_t ticks;

#endif
