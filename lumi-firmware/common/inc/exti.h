#ifndef __EXTI_H__
#define __EXTI_H__

#include <stdint.h>

typedef struct EXTI_TYPEDEF {
	uint32_t IMR;
	uint32_t EMR;
	uint32_t RTSR;
	uint32_t FTSR;
	uint32_t SWIER;
	uint32_t PR;
} EXTI_TypeDef;

#define EXTI_BASE  0x40013c00
#define EXTI ((EXTI_TypeDef *)EXTI_BASE)

#define EXTI_CR1 (*(volatile uint32_t *)0x40013808)	// EXTI0 ~ EXTI3
#define EXTI_CR2 (*(volatile uint32_t *)0x4001380c)	// EXTI4 ~ EXTI7
#define EXTI_CR3 (*(volatile uint32_t *)0x40013810)	// EXTI8 ~ EXTI11
#define EXTI_CR4 (*(volatile uint32_t *)0x40013814)	// EXTI12 ~ EXTI15

#define EXTI_CR_A 0
#define EXTI_CR_B 1
#define EXTI_CR_C 2
#define EXTI_CR_D 3
#define EXTI_CR_E 4
#define EXTI_CR_F 5
#define EXTI_CR_G 6
#define EXTI_CR_H 7
#define EXTI_CR_I 8


typedef struct
{
    volatile uint32_t MEMRMP;       // 0x00: Memory remap register
    volatile uint32_t PMC;          // 0x04: Peripheral mode configuration register
    
    /* 
     * 0x08 ~ 0x14: External interrupt configuration registers
     * EXTICR[0]은 EXTICR1, EXTICR[1]은 EXTICR2 ... EXTICR[3]은 EXTICR4에 대응됩니다.
     */
    volatile uint32_t EXTICR[4];    // 0x08, 0x0C, 0x10, 0x14: EXTI configuration registers
    
    /* 
     * 0x18 ~ 0x1C: Reserved (예약된 공간)
     * 0x14 번지(4바이트 크기) 다음 주소는 0x18입니다. 
     * 목표 레지스터인 CMPCR이 0x20에 있으므로, 중간의 8바이트 공간을 채워줍니다.
     */
    uint32_t RESERVED[2];           // 0x18, 0x1C: Reserved padding
    
    volatile uint32_t CMPCR;        // 0x20: Compensation cell control register
} SYSCFG_TypeDef;

#define SYSCFG_BASE          ((uint32_t)0x40013800)
#define SYSCFG               ((SYSCFG_TypeDef *) SYSCFG_BASE)

#endif
