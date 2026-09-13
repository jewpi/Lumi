#ifndef  INCLUDES_H
#define  INCLUDES_H

#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <math.h>
#include <string.h>
#include "gpio.h"
#include "system.h"
#include "nvic.h"
#include "systick.h"
#include "timer.h"
#include "led.h"
#include "uart.h"
#include "button.h"
#include "spi.h"
#include "flash.h"
#include "wheel.h"
#include "adc.h"
#include "rcc.h"

#include  <ucos_ii.h>  // uCOS-II 코어 헤더
#include  <os_cpu.h>   // 포팅 아키텍처 헤더
#include  <os_cfg.h>   // OS 기능 설정 헤더
#include  <app_cfg.h>  // 애플리케이션 설정 헤더


extern OS_TMR *my_timer;
extern OS_EVENT *UartMutex;
extern OS_FLAG_GRP *MissileEventFlags;

#define FLAG_IMU_OK  (1u << 0)	// 관성 센서 정상
#define FLAG_COMM_OK (1u << 1)	// 지상 제어소와 통신 정상 및 발상 명령 수신
#define FLAG_PROP_OK (1u << 2)	// 추진체 압력 정상

#endif