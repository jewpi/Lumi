#include "gpio.h"
#include "rcc.h"
#include "exti.h"
#include "nvic.h"

void gpio_init(void)
{
    RCC_AHB1_CLOCK_ER |= (GPIOA_AHB1_CLOCK_ER_VAL | GPIOB_AHB1_CLOCK_ER_VAL | \
                          GPIOC_AHB1_CLOCK_ER_VAL | GPIOD_AHB1_CLOCK_ER_VAL | \
                          GPIOE_AHB1_CLOCK_ER_VAL | GPIOF_AHB1_CLOCK_ER_VAL | \
                          GPIOG_AHB1_CLOCK_ER_VAL | GPIOH_AHB1_CLOCK_ER_VAL | \
                          GPIOI_AHB1_CLOCK_ER_VAL);
    
    // RCC 레지스터 동기화
    // 해당 레지스터 값을 load 하여 peripheral write 동작이 완료되었음을 보장
    (void)RCC_AHB1_CLOCK_ER; 
}

void gpio_write_pin(GPIO_Port *gpiox, uint8_t pin, uint8_t pin_state)
{
    if (pin_state == HIGH) {
        gpiox->BSRR = (1 << pin);
    }
    else {
        gpiox->BSRR = (1 << (pin + 16));
    }
}

uint8_t gpio_read_pin(GPIO_Port *gpiox, uint8_t pin)
{
    return (uint8_t)((gpiox->IDR >> pin) & 1);
}

void gpio_set_mode(GPIO_Port *gpiox, uint8_t pin, uint8_t mode)
{
    uint32_t reg = gpiox->MODE;
    reg &= ~(0x03 << (pin * 2));
    reg |= (mode << (pin * 2));
    gpiox->MODE = reg;
}

void gpio_set_ospeed(GPIO_Port *gpiox, uint8_t pin, uint8_t ospeed)
{
    uint32_t reg = gpiox->OSPEED;
    reg &= ~(0x03 << (pin * 2));
    reg |= (ospeed << (pin * 2));
    gpiox->OSPEED = reg;
}

void gpio_set_pupd(GPIO_Port *gpiox, uint8_t pin, uint8_t pupd)
{
    uint32_t reg = gpiox->PUPD;
    reg &= ~(0x03 << (pin * 2));
    reg |= (pupd << (pin * 2));
    gpiox->PUPD = reg;
}

void gpio_set_af(GPIO_Port *gpiox, uint8_t pin, uint8_t af_num)
{
    uint32_t reg;

    if (pin < 8) {
        reg = gpiox->AFRL & (~(0x0f << (pin * 4)));
        gpiox->AFRL = reg | (af_num << (pin * 4));
    }
    else {
        reg = gpiox->AFRH & (~(0x0f << ((pin - 8) * 4)));
        gpiox->AFRH = reg | (af_num << ((pin - 8) * 4));
    }
}

void gpio_set_exti(GPIO_Port *gpiox, uint8_t pin, uint8_t edge)
{
    // NVIC_EXTIx_IRQN 변수는 0으로 안전하게 초기화해 둡니다.
    uint8_t EXTI_CR_X = 0;
    uint8_t NVIC_EXTIx_IRQN = 0; 

    // 1. set input mode
    gpio_set_mode(gpiox, pin, GPIO_MODE_INPUT);
    
    // 2. set pull-up
    gpio_set_pupd(gpiox, pin, GPIO_PUPD_PU);
        
    // 3. SYSCFG controller clock on
    RCC_APB2_CLOCK_ER |= SYSCFG_APB2_CLOCK_ER_VAL; 

    // Port index 매핑 (GPIOA = 0, GPIOB = 1, ... GPIOI = 8)
    if (gpiox == GPIOA) EXTI_CR_X = 0;
    else if (gpiox == GPIOB) EXTI_CR_X = 1;
    else if (gpiox == GPIOC) EXTI_CR_X = 2;
    else if (gpiox == GPIOD) EXTI_CR_X = 3;
    else if (gpiox == GPIOE) EXTI_CR_X = 4;
    else if (gpiox == GPIOF) EXTI_CR_X = 5;
    else if (gpiox == GPIOG) EXTI_CR_X = 6;
    else if (gpiox == GPIOH) EXTI_CR_X = 7;
    else if (gpiox == GPIOI) EXTI_CR_X = 8;

    // 4. 핀 번호에 따른 NVIC IRQ 채널 매핑 (10~15번 핀 예외 처리 추가)
    if (pin == 0) NVIC_EXTIx_IRQN = NVIC_EXTI0_IRQN;
    else if (pin == 1) NVIC_EXTIx_IRQN = NVIC_EXTI1_IRQN;
    else if (pin == 2) NVIC_EXTIx_IRQN = NVIC_EXTI2_IRQN;
    else if (pin == 3) NVIC_EXTIx_IRQN = NVIC_EXTI3_IRQN;
    else if (pin == 4) NVIC_EXTIx_IRQN = NVIC_EXTI4_IRQN;
    else if (pin >= 5 && pin <= 9) NVIC_EXTIx_IRQN = NVIC_EXTI9_5_IRQN;
    else if (pin >= 10 && pin <= 15) NVIC_EXTIx_IRQN = NVIC_EXTI15_10_IRQN; // 누락된 분기 추가!

    // 5. SYSCFG EXTICR 설정 (기존 비트 클리어 후 대입 구조로 수정)
    // 핀 번호에 따라 EXTICR[0] ~ EXTICR[3] 중 하나가 선택됩니다.
    uint8_t exticr_idx = pin / 4;
    uint8_t shift_val = (pin % 4) * 4;

    // 해당 4비트 영역을 0xF로 먼저 클리어(지우기) 해준 뒤, EXTI_CR_X 값을 씁니다.
    SYSCFG->EXTICR[exticr_idx] &= ~(0xF << shift_val);
    SYSCFG->EXTICR[exticr_idx] |= (EXTI_CR_X << shift_val);

    // 6. NVIC 활성화 및 우선순위 설정
    nvic_irq_enable(NVIC_EXTIx_IRQN);
    nvic_irq_setprio(NVIC_EXTIx_IRQN, 6);

    // 7. EXTI 인터럽트 라인 마스크 해제
    EXTI->IMR |= 1 << pin;
    EXTI->EMR |= 1 << pin;

    // 8. 기존 설정되어 있을 수 있는 트리거 비트 초기화 후 새로 설정
    EXTI->RTSR &= ~(1 << pin);
    EXTI->FTSR &= ~(1 << pin);

    if (edge == GPIO_EXTI_RISING) {
        EXTI->RTSR |= 1 << pin;
    }
    else if (edge == GPIO_EXTI_FALLING) {
        EXTI->FTSR |= 1 << pin;
    }
    else if (edge == GPIO_EXTI_BOTH) {
        EXTI->RTSR |= 1 << pin;
        EXTI->FTSR |= 1 << pin;
    }
}