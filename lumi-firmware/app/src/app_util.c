#include "app_util.h"

void s_printf(const char *format, ...)
{
    INT8U _err;
    va_list args;

    if (OSRunning == OS_TRUE) {
        OSMutexPend(UartMutex, 0, &_err);
    }

    va_start(args, format);
    vprintf(format, args);
    va_end(args);
    
    if (OSRunning == OS_TRUE) {
        OSMutexPost(UartMutex);
    }    
}

void TimeDlyUntil(INT32U *p_last_wake_time, INT32U period_ticks)
{
    INT32U current_time;
    INT32U target_time;
    INT32U delay_ticks;

    // 1. 이번 루프에서 정확히 깨어났어야 했을 '절대 목표 시간' 계산
    target_time = *p_last_wake_time + period_ticks;
    
    // 2. 연산이 모두 끝난 지금의 '현재 시간' 확인
    current_time = OSTimeGet();

    // 3. 아직 목표 시간에 도달하지 않았다면 (정상 상황)
    if (target_time > current_time) {
        // 연산에 소요된 시간을 제외한 남은 시간 계산
        delay_ticks = target_time - current_time;
        
        // 다음 루프를 위해 기준점을 목표 시간으로 업데이트 (오차 누적 방지)
        *p_last_wake_time = target_time;
        
        // 남은 시간만큼만 딜레이 수행
        OSTimeDly(delay_ticks);
    } 
    else {
        // Task Overrun 발생. Task의 연산시간이 길어져 정해진 deadlne을 지키지 못함.
        // 대기 없이 다음 루프 주기를 현재 시간 기준으로 강제 리셋합니다.
        *p_last_wake_time = current_time;
        
        s_printf("[WARN] Task Overrun Detected!\r\n");
        ASSERT();
    }
}

void Print_All_Tasks_Info(void)
{
    OS_TCB  *p_tcb;
    uint32_t task_count = 0;

    // 1. 순회하는 도중 문맥 전환이 일어나지 않도록 스케줄러 잠금
    OSSchedLock();

    s_printf("\r\n--- Current Active Tasks List ---\r\n");

    // 2. uC/OS-II 커널의 TCB 시작점부터 탐색 시작
    p_tcb = OSTCBList; 

    while (p_tcb != (OS_TCB *)0) {
        task_count++;
        
        // 태스크의 우선순위(Prio) 출력
        s_printf("Task [%ld] - Priority: %d", task_count, p_tcb->OSTCBPrio);
        
        // 만약 특정 시스템 태스크이거나 사용자 태스크인 경우 구별 팁
        if (p_tcb->OSTCBPrio == OS_TASK_IDLE_PRIO) {
            s_printf(" (System Idle Task)\r\n");
        } else if (p_tcb->OSTCBPrio == 61) { // 질문자님의 타이머 태스크 우선순위
            s_printf(" (System Timer Task)\r\n");
        } else if (p_tcb->OSTCBPrio == 5) {
            s_printf(" (AppTaskStart)\r\n");
        } else {
            s_printf(" (User Task)\r\n");
        }

        // 다음 태스크로 이동
        p_tcb = p_tcb->OSTCBNext;
    }

    s_printf("Total Active Tasks Count: %ld\r\n", task_count);
    s_printf("---------------------------------\r\n");

    // 3. 조회가 끝났으므로 스케줄러 잠금 해제
    OSSchedUnlock();
}