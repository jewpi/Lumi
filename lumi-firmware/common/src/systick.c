#include "systick.h"
#include "system.h"

// bootloader에서 사용하는 systick 함수
// app에서는 uCOS-II에서 제공하는 API를 사용하여 systick 설정
void systick_enable(void)
{
	SYSTICK_RVR = (CPU_FREQ / 1000) - 1;
	SYSTICK_CVR = 0;
	SYSTICK_CSR |= 0x07;
}

void systick_disable(void)
{
	SYSTICK_CSR &= ~((1 << 1) | (1 << 0));
}

// uint32_t get_tick(void)
// {
// 	return ticks;
// }
