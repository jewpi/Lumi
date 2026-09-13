#ifndef __SYSTEM_H__
#define __SYSTEM_H__

#include <stdint.h>

#define CPU_FREQ (168000000)

#define PCLK1 (CPU_FREQ / 4)
#define PCLK1_TIM (PCLK1 * 2)

#define PCLK2 (CPU_FREQ / 2)
#define PCLK2_TIM (PCLK2 * 2)

#define MAX_DELAY (0xFFFFFFFFU)

#define DMB() __asm__ volatile ("DMB");
#define WFI() __asm__ volatile ("WFI");

void clock_config(void);
void flash_init(void);
void Delay(uint32_t tick);
void SoftwareReset(void);

#endif
