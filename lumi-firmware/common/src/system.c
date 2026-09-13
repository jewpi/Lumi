#include <stdint.h>
#include <sys/stat.h>
#include <sys/types.h>
#include "system.h"
#include "systick.h"
#include "rcc.h"

#define AIRCR (*(volatile uint32_t *)0xE000ED0C)
#define SCB_SHPR3 (*(volatile uint32_t *)0xE000ED20)

/*** RCC ***/
#define RCC_CR_PLLRDY               (1 << 25)
#define RCC_CR_PLLON                (1 << 24)
#define RCC_CR_HSERDY               (1 << 17)
#define RCC_CR_HSEON                (1 << 16)
#define RCC_CR_HSIRDY               (1 << 1)
#define RCC_CR_HSION                (1 << 0)

#define RCC_CFGR_SW_HSI             0x0
#define RCC_CFGR_SW_HSE             0x1
#define RCC_CFGR_SW_PLL             0x2

#define RCC_PLLCFGR_PLLSRC_HSE       (1 << 22)	// select HSE

#define PRESCALER_SYSCLK_TO_AHB_NONE 0
#define PRESCALER_SYSCLK_TO_AHB_2    8
#define PRESCALER_SYSCLK_TO_AHB_4    9

#define PRESCALER_AHB_TO_APB_NONE    0
#define PRESCALER_AHB_TO_APB_2	     4
#define PRESCALER_AHB_TO_APB_4	     5

#define PLL_FULL_MASK (0x0F437FFF)
#define PLLM 8
#define PLLN 336
#define PLLP 2
#define PLLQ 7
#define PLLR 0

void clock_config(void)
{
	uint32_t reg32;
	
	// HSI On
	RCC->CR |= RCC_CR_HSION;
	DMB();
	while ((RCC->CR & RCC_CR_HSIRDY) == 0);

	// Select SYSCLK with HSI
	reg32 = RCC->CFGR;
	reg32 &= ~((1 << 1) | (1 << 0));
	RCC->CFGR = (reg32 | RCC_CFGR_SW_HSI);
	DMB();

	// HSE On
	RCC->CR |= RCC_CR_HSEON;
	DMB();
	while ((RCC->CR & RCC_CR_HSERDY) == 0);

	// SYSCLK to AHB clock prescale
	reg32 = RCC->CFGR;
	reg32 &= ~0xF0;
	RCC->CFGR = (reg32 | (PRESCALER_SYSCLK_TO_AHB_NONE << 4));
	DMB();

	// AHB to APB1 clock prescale (1/4)
	reg32 = RCC->CFGR;
	reg32 &= ~0x1C00;	// PPRE1 clear
	RCC->CFGR = (reg32 | (PRESCALER_AHB_TO_APB_4 << 10));
	DMB();

	// AHB to APB2 clock prescale (1/2)
	reg32 = RCC->CFGR;
	reg32 &= ~(0x07 << 13);	// PPRE2 clear
	RCC->CFGR = (reg32 | (PRESCALER_AHB_TO_APB_2 << 13));
	DMB();

	// PLL config
	// PLL Source Mux에서 HSE를 input으로 설정
	// PLL_OUT_FREQ = PLL_SRC_FREQ(HSE) / M * N / P
	reg32 = RCC->PLLCFGR;
	reg32 &= ~PLL_FULL_MASK;
	RCC->PLLCFGR = reg32 | RCC_PLLCFGR_PLLSRC_HSE | PLLM | (PLLN << 6) | (((PLLP >> 1) -1) << 16) | (PLLQ << 24);
	DMB();

	// PLL On
	RCC->CR |= RCC_CR_PLLON;
	DMB();
	while ((RCC->CR & RCC_CR_PLLRDY) == 0);

	// Select SYSCLK with PLL
	// System Clock Mux에서 PLLCLK 선택
	reg32 = RCC->CFGR;
	reg32 &= ~((1 << 1) | (1 << 0));
	RCC->CFGR = (reg32 | RCC_CFGR_SW_PLL);
	DMB();
	while ((RCC->CFGR & ((1 << 1) | (1 << 0))) != RCC_CFGR_SW_PLL);

	// HSI Off
    RCC->CR &= ~RCC_CR_HSION;
    DMB();
}

// void Delay(uint32_t delay)
// {
// 	uint32_t tick_start = get_tick();
// 	uint32_t wait = delay;

// 	if (wait < MAX_DELAY) {
// 		wait += 1;
// 	}

// 	while ((get_tick() - tick_start) < wait);
// }

void SoftwareReset(void)
{
	AIRCR = (0x05fa << 16) | (1 << 2);
	for (;;) {
		// wait until reset
	}
}

// // uCOS-II를 포팅하기 위해 Systick, PendSV exception의 우선순위를 최하위로 설정
// // Systick handler에서 PendSV를 pending 시킨 후 완전히 종료된 이후에 PendSV handler가 수행됨을 보장
// void SysTick_And_PendSV_Prio_Init(void) {
//     // STM32F407 가용 4비트 기준 최하위 우선순위 값 = 0xF0 (상위 4비트에 15 주입)
//     uint32_t prio_val = 0xF0UL; 

//     // SHPR3 레지스터의 PendSV 영역과 SysTick 영역에 최하위 우선순위(0xF0)를 각각 기입
//     uint32_t reg_tmp = SCB_SHPR3;
    
//     reg_tmp &= ~(0xFF000000UL); // SysTick 필드 클리어
//     reg_tmp |=  (prio_val << 24UL);
    
//     reg_tmp &= ~(0x00FF0000UL); // PendSV 필드 클리어
//     reg_tmp |=  (prio_val << 16UL);
    
//     SCB_SHPR3 = reg_tmp;
// }

/* 시스템 콜 더미(Dummy) 함수들
 * 표준 라이브러리(Newlib)가 요구하는 최소한의 환경을 제공하여 링커 경고를 제거
 */
int _isatty(int file) {
    return 1; // 모든 출력 대상을 터미널(tty)로 간주
}

int _fstat(int file, struct stat *st) {
    return 0;
}

int _lseek(int file, int ptr, int dir) {
    return 0; // 파일 포인터 이동 기능 없음
}

int _read(int file, char *ptr, int len) {
    return 0; // 입력 기능은 일단 0바이트 읽기로 처리
}

int _close(int file) {
    return -1; // 파일을 닫을 수 없음
}

// 경고를 없애기 위한 Stub 함수 구현
pid_t _getpid(void) {
    return 1;
}

int _kill(int pid, int sig) {
    (void)pid; (void)sig; // 사용하지 않는 변수 경고 방지
    return -1;
}