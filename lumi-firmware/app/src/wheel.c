#include "wheel.h"
#include "gpio.h"

extern volatile int32_t target_rpm;

void wheel_left_init()
{
    // Moter Driver IN1 (PB6)
    gpio_set_mode(GPIOB, 6, GPIO_MODE_OUTPUT);
	gpio_set_ospeed(GPIOB, 6, GPIO_OSPEED_VH);
	gpio_write_pin(GPIOB, 6, 0);

    // Moter Driver IN2 (PB8)
	gpio_set_mode(GPIOB, 8, GPIO_MODE_OUTPUT);
	gpio_set_ospeed(GPIOB, 8, GPIO_OSPEED_VH);
	gpio_write_pin(GPIOB, 8, 0);
}

void wheel_right_init()
{
    // Moter Driver IN1 (PB6)
    gpio_set_mode(GPIOB, 7, GPIO_MODE_OUTPUT);
	gpio_set_ospeed(GPIOB, 7, GPIO_OSPEED_VH);
	gpio_write_pin(GPIOB, 7, 0);

    // Moter Driver IN2 (PB8)
	gpio_set_mode(GPIOB, 9, GPIO_MODE_OUTPUT);
	gpio_set_ospeed(GPIOB, 9, GPIO_OSPEED_VH);
	gpio_write_pin(GPIOB, 9, 0);
}

void wheel_left_forward()
{
    gpio_write_pin(GPIOB, 6, HIGH);
    gpio_write_pin(GPIOB, 8, LOW);
}

void wheel_left_backward()
{
    gpio_write_pin(GPIOB, 6, LOW);
    gpio_write_pin(GPIOB, 8, HIGH);
}

void wheel_right_forward()
{
    gpio_write_pin(GPIOB, 7, HIGH);
    gpio_write_pin(GPIOB, 9, LOW);
}

void wheel_right_backward()
{
    gpio_write_pin(GPIOB, 7, LOW);
    gpio_write_pin(GPIOB, 9, HIGH);
}

void wheel_left_stop()
{
    gpio_write_pin(GPIOB, 6, HIGH);
    gpio_write_pin(GPIOB, 8, HIGH);
}

void wheel_right_stop()
{
    gpio_write_pin(GPIOB, 7, HIGH);
    gpio_write_pin(GPIOB, 9, HIGH);
}