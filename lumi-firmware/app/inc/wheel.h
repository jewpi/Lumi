#ifndef __WHEEL_H__
#define __WHEEL_H__

#include <stdint.h>

void wheel_left_init();
void wheel_right_init();

void wheel_left_forward();
void wheel_left_backward();

void wheel_right_forward();
void wheel_right_backward();

void wheel_left_stop();
void wheel_right_stop();

#endif