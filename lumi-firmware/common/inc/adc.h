#include <stdint.h>

/** 
  * ADC 개별 레지스터 구조체 (ADC1, ADC2, ADC3)
  */
typedef struct {
    volatile uint32_t SR;     // Status register (Offset: 0x00)
    volatile uint32_t CR1;    // Control register 1 (Offset: 0x04)
    volatile uint32_t CR2;    // Control register 2 (Offset: 0x08)
    volatile uint32_t SMPR1;  // Sample time register 1 (Offset: 0x0C)
    volatile uint32_t SMPR2;  // Sample time register 2 (Offset: 0x10)
    volatile uint32_t JOFR1;  // Injected channel data offset register 1 (Offset: 0x14)
    volatile uint32_t JOFR2;  // Injected channel data offset register 2 (Offset: 0x18)
    volatile uint32_t JOFR3;  // Injected channel data offset register 3 (Offset: 0x1C)
    volatile uint32_t JOFR4;  // Injected channel data offset register 4 (Offset: 0x20)
    volatile uint32_t HTR;    // Watchdog higher threshold register (Offset: 0x24)
    volatile uint32_t LTR;    // Watchdog lower threshold register (Offset: 0x28)
    volatile uint32_t SQR1;   // Regular sequence register 1 (Offset: 0x2C)
    volatile uint32_t SQR2;   // Regular sequence register 2 (Offset: 0x30)
    volatile uint32_t SQR3;   // Regular sequence register 3 (Offset: 0x34)
    volatile uint32_t JSQR;   // Injected sequence register (Offset: 0x38)
    volatile uint32_t JDR1;   // Injected data register 1 (Offset: 0x3C)
    volatile uint32_t JDR2;   // Injected data register 2 (Offset: 0x40)
    volatile uint32_t JDR3;   // Injected data register 3 (Offset: 0x44)
    volatile uint32_t JDR4;   // Injected data register 4 (Offset: 0x48)
    volatile uint32_t DR;     // Regular data register (Offset: 0x4C)
} ADC_x;

/** 
  * ADC 공통 레지스터 구조체 (Common registers)
  */
typedef struct {
    volatile uint32_t CSR;    // Common status register (Offset: 0x00)
    volatile uint32_t CCR;    // Common control register (Offset: 0x04)
    volatile uint32_t CDR;    // Common data register for dual/triple mode (Offset: 0x08)
} ADC_Common_TypeDef;

/* -------------------------------------------------------------------------- */
/*                                Base Addresses                              */
/* -------------------------------------------------------------------------- */
#define ADC_BASE       0x40012000UL

#define ADC1_BASE             (ADC_BASE + 0x0UL)   // 0x40012000
#define ADC2_BASE             (ADC_BASE + 0x100UL) // 0x40012100
#define ADC3_BASE             (ADC_BASE + 0x200UL) // 0x40012200
#define ADC_COMMON_BASE       (ADC_BASE + 0x300UL) // 0x40012300

/* -------------------------------------------------------------------------- */
/*                             Peripheral Pointers                            */
/* -------------------------------------------------------------------------- */
#define ADC1                  ((ADC_x *) ADC1_BASE)
#define ADC2                  ((ADC_x *) ADC2_BASE)
#define ADC3                  ((ADC_x *) ADC3_BASE)
#define ADC                   ((ADC_Common_TypeDef *) ADC_COMMON_BASE)