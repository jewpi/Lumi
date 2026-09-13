/*
*********************************************************************************************************
*                                            EXAMPLE CODE
*
*               This file is provided as an example on how to use Micrium products.
*
*               Please feel free to use any application code labeled as 'EXAMPLE CODE' in
*               your application products.  Example code may be used as is, in whole or in
*               part, or may be used as a reference only. This file can be modified as
*               required to meet the end-product requirements.
*
*********************************************************************************************************
*/

/*
*********************************************************************************************************
*
*                                      APPLICATION CONFIGURATION
*
*                                            EXAMPLE CODE
*
* Filename : app_cfg.h
*********************************************************************************************************
*/

#ifndef  _APP_CFG_H_
#define  _APP_CFG_H_


/*
*********************************************************************************************************
*                                            INCLUDE FILES
*********************************************************************************************************
*/

#include  <stdarg.h>
#include  <stdio.h>


/*
*********************************************************************************************************
*                                       MODULE ENABLE / DISABLE
*********************************************************************************************************
*/


/*
*********************************************************************************************************
*                                           TASK PRIORITIES
*********************************************************************************************************
*/

#define  APP_CFG_STARTUP_TASK_PRIO          3u

#define COMPUTE_TARGET_RPM_TASK_PRIO        10u
#define APP_CFG_GUIDANCE_TASK_PRIO          11u
#define APP_CFG_IMU_TASK_PRIO               12u
#define APP_CFG_ULTRASONIC_SENSOR_TASK_PRIO 13u
#define OTA_TRIG_TASK_PRIO                  20u
#define APP_CFG_BATTERY_CHECK_TASK_PRIO     21u
#define APP_CFG_COMM_TASK_PRIO              14U

#define  OS_TASK_TMR_PRIO                  (OS_LOWEST_PRIO - 2u)


/*
*********************************************************************************************************
*                                          TASK STACK SIZES
*                             Size of the task stacks (# of OS_STK entries)
*********************************************************************************************************
*/

#define  APP_CFG_STARTUP_TASK_STK_SIZE          256u

#define COMPUTE_TARGET_RPM_TASK_STK_SIZE        4096u
#define APP_CFG_GUIDANCE_TASK_STK_SIZE          4096u
#define APP_CFG_IMU_TASK_STK_SIZE               4096u
#define APP_CFG_ULTRASONIC_SENSOR_TASK_STK_SIZE 4096u
#define OTA_TRIG_TASK_STK_SIZE                  1024u
#define BATTERY_CHECK_TASK_STK_SIZE             2048u
#define APP_CFG_COMM_TASK_STK_SIZE              1024u


/*
*********************************************************************************************************
*                                     TRACE / DEBUG CONFIGURATION
*********************************************************************************************************
*/

#ifndef  TRACE_LEVEL_OFF
#define  TRACE_LEVEL_OFF                    0u
#endif

#ifndef  TRACE_LEVEL_INFO
#define  TRACE_LEVEL_INFO                   1u
#endif

#ifndef  TRACE_LEVEL_DBG
#define  TRACE_LEVEL_DBG                    2u
#endif

#define  APP_TRACE_LEVEL                   TRACE_LEVEL_OFF
#define  APP_TRACE                         printf

#define  APP_TRACE_INFO(x)    ((APP_TRACE_LEVEL >= TRACE_LEVEL_INFO)  ? (void)(APP_TRACE x) : (void)0)
#define  APP_TRACE_DBG(x)     ((APP_TRACE_LEVEL >= TRACE_LEVEL_DBG)   ? (void)(APP_TRACE x) : (void)0)



/*
*********************************************************************************************************
* KERNEL-AWARE INTERRUPT PRIORITY BOUNDARY
*********************************************************************************************************
*/
#ifndef  CPU_CFG_KA_IPL_BOUNDARY
#define  CPU_CFG_KA_IPL_BOUNDARY              5u
#endif


#define  CPU_CFG_NVIC_PRIO_BITS        4u



/*
*********************************************************************************************************
* TRACE FUNCTION STUBBING (os_trace.h 삭제에 따른 완전한 더미 매크로 정의)
*********************************************************************************************************
*/
#ifndef OS_TRACE_H
#define OS_TRACE_H

/* os_core.c 관련 트레이스 */
#define OS_TRACE_EVENT_NAME_SET(pevent, pname)
#define OS_TRACE_ISR_ENTER()
#define OS_TRACE_ISR_EXIT_TO_SCHEDULER()
#define OS_TRACE_ISR_EXIT()
#define OS_TRACE_TICK_INCREMENT(time)
#define OS_TRACE_TASK_READY(ptcb)
#define OS_TRACE_TASK_SUSPENDED(ptcb)

/* os_flag.c 관련 트레이스 */
#define OS_TRACE_FLAG_CREATE(pgrp, pname)
#define OS_TRACE_FLAG_DEL_ENTER(pgrp, opt)
#define OS_TRACE_FLAG_DEL_EXIT(err)
#define OS_TRACE_FLAG_PEND_ENTER(pgrp, flags, timeout, wait_type)
#define OS_TRACE_FLAG_PEND_EXIT(err)
#define OS_TRACE_FLAG_POST_ENTER(pgrp, flags, opt)
#define OS_TRACE_FLAG_POST_EXIT(err)

/* os_mbox.c 관련 트레이스 */
#define OS_TRACE_MBOX_CREATE(pevent, pname)
#define OS_TRACE_MBOX_DEL_ENTER(pevent, opt)
#define OS_TRACE_MBOX_DEL_EXIT(err)
#define OS_TRACE_MBOX_PEND_ENTER(pevent, timeout)
#define OS_TRACE_MBOX_PEND_EXIT(err)
#define OS_TRACE_MBOX_POST_ENTER(pevent)
#define OS_TRACE_MBOX_POST_EXIT(err)
#define OS_TRACE_MBOX_POST_OPT_ENTER(pevent, opt)
#define OS_TRACE_MBOX_POST_OPT_EXIT(err)

/* os_mem.c 관련 트레이스 */
#define OS_TRACE_MEM_CREATE(pmem)
#define OS_TRACE_MEM_GET_ENTER(pmem)
#define OS_TRACE_MEM_GET_EXIT(err)
#define OS_TRACE_MEM_PUT_ENTER(pmem, pblk)
#define OS_TRACE_MEM_PUT_EXIT(err)

/* os_mutex.c 관련 트레이스 */
#define OS_TRACE_MUTEX_CREATE(pevent, pname)
#define OS_TRACE_MUTEX_DEL_ENTER(pevent, opt)
#define OS_TRACE_MUTEX_DEL_EXIT(err)
#define OS_TRACE_MUTEX_TASK_PRIO_DISINHERIT(ptcb, prio)
#define OS_TRACE_MUTEX_PEND_ENTER(pevent, timeout)
#define OS_TRACE_MUTEX_PEND_EXIT(err)
#define OS_TRACE_MUTEX_TASK_PRIO_INHERIT(ptcb, pcp)
#define OS_TRACE_MUTEX_POST_ENTER(pevent)
#define OS_TRACE_MUTEX_POST_EXIT(err)

/* os_q.c 관련 트레이스 */
#define OS_TRACE_Q_CREATE(pevent, pname)
#define OS_TRACE_Q_DEL_ENTER(pevent, opt)
#define OS_TRACE_Q_DEL_EXIT(err)
#define OS_TRACE_Q_PEND_ENTER(pevent, timeout)
#define OS_TRACE_Q_PEND_EXIT(err)
#define OS_TRACE_Q_POST_ENTER(pevent)
#define OS_TRACE_Q_POST_EXIT(err)
#define OS_TRACE_Q_POST_FRONT_ENTER(pevent)
#define OS_TRACE_Q_POST_FRONT_EXIT(err)
#define OS_TRACE_Q_POST_OPT_ENTER(pevent, opt)
#define OS_TRACE_Q_POST_OPT_EXIT(err)

/* os_sem.c 관련 트레이스 */
#define OS_TRACE_SEM_CREATE(pevent, pname)
#define OS_TRACE_SEM_DEL_ENTER(pevent, opt)
#define OS_TRACE_SEM_DEL_EXIT(err)
#define OS_TRACE_SEM_PEND_ENTER(pevent, timeout)
#define OS_TRACE_SEM_PEND_EXIT(err)
#define OS_TRACE_SEM_POST_ENTER(pevent)
#define OS_TRACE_SEM_POST_EXIT(err)

/* os_task.c 관련 트레이스 */
#define OS_TRACE_TASK_CREATE(ptcb)
#define OS_TRACE_TASK_CREATE_FAILED(ptcb)
#define OS_TRACE_TASK_NAME_SET(ptcb)
#define OS_TRACE_TASK_RESUME(ptcb)
#define OS_TRACE_TASK_SUSPEND(ptcb)

/* os_time.c 관련 트레이스 */
#define OS_TRACE_TASK_DLY(ticks)

/* os_tmr.c 관련 트레이스 */
#define OS_TRACE_TMR_CREATE(ptmr, pname)
#define OS_TRACE_TMR_DEL_ENTER(ptmr)
#define OS_TRACE_TMR_DEL_EXIT(err)
#define OS_TRACE_TMR_START_ENTER(ptmr)
#define OS_TRACE_TMR_START_EXIT(err)
#define OS_TRACE_TMR_STOP_ENTER(ptmr)
#define OS_TRACE_TMR_STOP_EXIT(err)
#define OS_TRACE_TMR_EXPIRED(ptmr)

/* os_cpu_c.c 관련 트레이스 */
#define OS_TRACE_TASK_SWITCHED_IN(ptcb)

#endif

void OSTaskSwHook(void);

// 커널 코어 엔진이 조건 없이 무조건 호출하는 필수 훅 함수들의 빈 껍데기 선언
typedef struct os_tcb OS_TCB;


/*
*********************************************************************************************************
*                                             MODULE END
*********************************************************************************************************
*/

#endif                                                          /* End of module include.              */
