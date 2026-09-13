#ifndef __GPIO_H__
#define __GPIO_H__

#include <stdint.h>

typedef struct GPIO_PORT {
	uint32_t MODE;
	uint32_t OTYPE;
	uint32_t OSPEED;
	uint32_t PUPD;
	uint32_t IDR;
	uint32_t ODR;
	uint32_t BSRR;
	uint32_t LCKR;
	uint32_t AFRL;
	uint32_t AFRH;
} GPIO_Port;

#define GPIOA_BASE 0x40020000
#define GPIOB_BASE 0x40020400
#define GPIOC_BASE 0x40020800
#define GPIOD_BASE 0x40020C00
#define GPIOE_BASE 0x40021000
#define GPIOF_BASE 0x40021400
#define GPIOG_BASE 0x40021800
#define GPIOH_BASE 0x40021C00
#define GPIOI_BASE 0x40022000
#define GPIOJ_BASE 0x40022400
#define GPIOK_BASE 0x40022800

#define GPIOA ((GPIO_Port *)GPIOA_BASE)
#define GPIOB ((GPIO_Port *)GPIOB_BASE)
#define GPIOC ((GPIO_Port *)GPIOC_BASE)
#define GPIOD ((GPIO_Port *)GPIOD_BASE)
#define GPIOE ((GPIO_Port *)GPIOE_BASE)
#define GPIOF ((GPIO_Port *)GPIOF_BASE)
#define GPIOG ((GPIO_Port *)GPIOG_BASE)
#define GPIOH ((GPIO_Port *)GPIOH_BASE)
#define GPIOI ((GPIO_Port *)GPIOI_BASE)
#define GPIOJ ((GPIO_Port *)GPIOJ_BASE)
#define GPIOK ((GPIO_Port *)GPIOK_BASE)

//GPIO_Port *GPIOA =  (GPIO_Port *)GPIOA_BASE;
//GPIO_Port *GPIOB =  (GPIO_Port *)GPIOB_BASE

/* GPIO Mode */
#define GPIO_MODE_INPUT  0x00
#define GPIO_MODE_OUTPUT 0x01
#define GPIO_MODE_AF     0x02
#define GPIO_MODE_ANALOG 0x03

/* GPIO Output Speed */
#define GPIO_OSPEED_L  0x00
#define GPIO_OSPEED_M  0x01
#define GPIO_OSPEED_H  0x02
#define GPIO_OSPEED_VH 0x03

/* GPIO Pull-up / Pull-down */
#define GPIO_PUPD_NONE 0x00
#define GPIO_PUPD_PU   0x01
#define GPIO_PUPD_PD   0x02

#define GPIO_EXTI_RISING  0
#define GPIO_EXTI_FALLING 1
#define GPIO_EXTI_BOTH	  2

#define HIGH 1
#define LOW 0

/* GPIO interface prototypes */
void gpio_init(void);
void gpio_write_pin(GPIO_Port *gpiox, uint8_t pin, uint8_t pin_state);
uint8_t gpio_read_pin(GPIO_Port *gpiox, uint8_t pin);
void gpio_set_mode(GPIO_Port *gpiox, uint8_t pin, uint8_t mode);
void gpio_set_ospeed(GPIO_Port *gpiox, uint8_t pin, uint8_t ospeed);
void gpio_set_pupd(GPIO_Port *gpiox, uint8_t pin, uint8_t pupd);
void gpio_set_af(GPIO_Port *gpiox, uint8_t pin, uint8_t af_num);
void gpio_set_exti(GPIO_Port *gpiox, uint8_t pin, uint8_t edge);

#endif
