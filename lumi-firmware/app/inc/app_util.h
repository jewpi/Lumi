#ifndef __APP_UTIL_H__
#define __APP_UTIL_H__

#include "includes.h"
#include <stdarg.h>

void s_printf(const char *format, ...);
void TimeDlyUntil(INT32U *p_last_wake_time, INT32U period_ticks);
void Print_All_Tasks_Info(void);

#define ASSERT() for(;;);

#endif