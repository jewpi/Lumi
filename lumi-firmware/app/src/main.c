#include "includes.h"
#include "app_util.h"

__attribute__((aligned(8)))
static OS_STK AppTaskStartStk[APP_CFG_STARTUP_TASK_STK_SIZE];

__attribute__((aligned(8)))
static OS_STK ComputeTargetRpmTaskStk[COMPUTE_TARGET_RPM_TASK_STK_SIZE];

__attribute__((aligned(8)))
static OS_STK AppTaskGuidanceStk[APP_CFG_GUIDANCE_TASK_STK_SIZE];

__attribute__((aligned(8)))
static OS_STK AppTaskImuStk[APP_CFG_IMU_TASK_STK_SIZE];

__attribute__((aligned(8)))
static OS_STK UltrasonicSensorStk[APP_CFG_ULTRASONIC_SENSOR_TASK_STK_SIZE];

__attribute__((aligned(8)))
static OS_STK OTATrigTaskStk[OTA_TRIG_TASK_STK_SIZE];

__attribute__((aligned(8)))
static OS_STK BatteryCheckTaskStk[BATTERY_CHECK_TASK_STK_SIZE];

__attribute__((aligned(8)))
static OS_STK AppTaskCommStk[APP_CFG_COMM_TASK_STK_SIZE];

static void AppTaskStart(void *p_arg);
static void ComputeTargetRpmTask(void *p_arg);
static void MotorSpeedControlTask(void *p_arg);
static void UpdateWheelOdometry(void *p_arg);
static void UltrasonicSensorTask(void *p_arg);
static void OTATrigTask(void *p_arg);
static void BatteryCheckTask(void *p_arg);
static void AppTaskComm(void *p_arg);

OS_TMR *my_timer;
OS_EVENT *g_cmd_vel_sem;
OS_EVENT *UartMutex = NULL;
OS_EVENT *WheelOdometryMbox;
OS_EVENT *HCSR04DurationMbox;
OS_EVENT *ButtonSem;

// 50ms 제어 주기에 맞춘 dt 설정
#define DT 0.05f

#define P_GAIN_FAST 8.5f
#define I_GAIN_FAST 6.0f
#define D_GAIN_FAST 0.2f

#define P_GAIN_SLOW 6.0f
#define I_GAIN_SLOW 4.0f
#define D_GAIN_SLOW 0.0f

//extern volatile uint32_t enc_pulse_edge_cnt; // EXTI 인터럽트에서 증가하는 펄스 수
volatile int32_t enc_pos_cnt;

volatile float left_wheel_distance;

extern volatile uint32_t echo_duration;
extern uint8_t target_rpm_update_flag;

extern volatile uint32_t rx_count;
uint8_t g_cmd_vel_buffer[8];

float linear_x;
float angular_z;

//void spi_rx_handler(SPI_x *SPIx, uint8_t data);
void HCSR04_sensor_init(void);
void ADC1_bat_check_init(void);

void BSP_Init(void)
{	
	led_setup();
	button_setup();

	// 왼쪽 모터 PWM 출력
	timer_init(TIM1, 8400 - 1, 1000 - 1);		// 168000000 2000hz
	timer_start_PWM(TIM1, 1, GPIOE, 9, 0);

	// 오른쪽 모터 PWM 출력
	timer_init(TIM8, 8400 - 1, 1000 - 1);
	timer_start_PWM(TIM8, 4, GPIOC, 9, 0);

	// 왼쪽 모터 encoder 타이머 설정
	timer3_encoder_init();

	// 오른쪽 모터 encoder 타이머 설정
	timer5_encoder_init();

	// 양쪽 바퀴 초기화
	wheel_left_init();
	wheel_right_init();

	// 초음파 센서 초기화
	HCSR04_sensor_init();

	// rp4 --> STM cmd_vel DMA 수신 설정
	uart3_dma_rx_init(g_cmd_vel_buffer, sizeof(g_cmd_vel_buffer));
	uart3_dma_tx_init();

	// 배터리 전압 체크를 위한 ADC 초기화
	ADC1_bat_check_init();
}

void main(void)
{
	OSInit();

	OSTaskCreate((void (*)(void *)) AppTaskStart, \
				 (void *) 0, \
				 (OS_STK *) &AppTaskStartStk[APP_CFG_STARTUP_TASK_STK_SIZE - 1], \
				 (INT8U) APP_CFG_STARTUP_TASK_PRIO);


	OSStart();
}

static void AppTaskStart(void *p_arg)
{
	INT8U err;
	(void)p_arg;

	s_printf("AppTaskStart\r\n");

	// 시스템에서 사용되는 peripherals init
	BSP_Init();

	// wheel_left_forward();
	// wheel_right_forward();
	// while(1);

	// Systick 인터럽트 최하위 우선순위 부여후 실행
	// OSStart 이후에 호출되어야 함.
	// task들 생성하기 전에 먼저 켜도 되는건가?
	OS_CPU_SysTickInitFreq(CPU_FREQ);
	
	g_cmd_vel_sem = OSSemCreate(0);
	UartMutex = OSMutexCreate(3u, &err);
	//MissileEventFlags = OSFlagCreate(0x00, &err);
	WheelOdometryMbox = OSMboxCreate((void *)0);
	HCSR04DurationMbox = OSMboxCreate((void *)0);
	ButtonSem = OSSemCreate(0);

	OSTaskCreateExt((void (*)(void *)) ComputeTargetRpmTask,
                    (void *) 0,
                    (OS_STK *) &ComputeTargetRpmTaskStk[COMPUTE_TARGET_RPM_TASK_STK_SIZE - 1],
                    (INT8U)    COMPUTE_TARGET_RPM_TASK_PRIO,
                    (INT16U)   COMPUTE_TARGET_RPM_TASK_PRIO, // ID는 보통 우선순위와 동일하게 부여합니다.
                    (OS_STK *) &ComputeTargetRpmTaskStk[0],     // 스택 바닥(최하위) 주소
                    (INT32U)   COMPUTE_TARGET_RPM_TASK_STK_SIZE,
                    (void *)   0,
                    (INT16U)  (OS_TASK_OPT_STK_CHK | OS_TASK_OPT_STK_CLR | OS_TASK_OPT_SAVE_FP)); // ★ FPU 백업 옵션 추가

	/* 1. Motor Speed Control Task 생성 (FPU 지원) */
    OSTaskCreateExt((void (*)(void *)) MotorSpeedControlTask,
                    (void *) 0,
                    (OS_STK *) &AppTaskGuidanceStk[APP_CFG_GUIDANCE_TASK_STK_SIZE - 1],
                    (INT8U)    APP_CFG_GUIDANCE_TASK_PRIO,
                    (INT16U)   APP_CFG_GUIDANCE_TASK_PRIO, // ID는 보통 우선순위와 동일하게 부여합니다.
                    (OS_STK *) &AppTaskGuidanceStk[0],     // 스택 바닥(최하위) 주소
                    (INT32U)   APP_CFG_GUIDANCE_TASK_STK_SIZE,
                    (void *)   0,
                    (INT16U)  (OS_TASK_OPT_STK_CHK | OS_TASK_OPT_STK_CLR | OS_TASK_OPT_SAVE_FP)); // ★ FPU 백업 옵션 추가

    /* 2. IMU Task 생성 (FPU 지원) */
    OSTaskCreateExt((void (*)(void *)) UpdateWheelOdometry,
                    (void *) 0,
                    (OS_STK *) &AppTaskImuStk[APP_CFG_IMU_TASK_STK_SIZE - 1],
                    (INT8U)    APP_CFG_IMU_TASK_PRIO,
                    (INT16U)   APP_CFG_IMU_TASK_PRIO,
                    (OS_STK *) &AppTaskImuStk[0],
                    (INT32U)   APP_CFG_IMU_TASK_STK_SIZE,
                    (void *)   0,
                    (INT16U)  (OS_TASK_OPT_STK_CHK | OS_TASK_OPT_STK_CLR | OS_TASK_OPT_SAVE_FP)); // ★ FPU 백업 옵션 추가

	/* 2. IMU Task 생성 (FPU 지원) */
    OSTaskCreateExt((void (*)(void *)) UltrasonicSensorTask,
                    (void *) 0,
                    (OS_STK *) &UltrasonicSensorStk[APP_CFG_ULTRASONIC_SENSOR_TASK_STK_SIZE - 1],
                    (INT8U)    APP_CFG_ULTRASONIC_SENSOR_TASK_PRIO,
                    (INT16U)   APP_CFG_ULTRASONIC_SENSOR_TASK_PRIO,
                    (OS_STK *) &UltrasonicSensorStk[0],
                    (INT32U)   APP_CFG_ULTRASONIC_SENSOR_TASK_STK_SIZE,
                    (void *)   0,
                    (INT16U)  (OS_TASK_OPT_STK_CHK | OS_TASK_OPT_STK_CLR | OS_TASK_OPT_SAVE_FP)); // ★ FPU 백업 옵션 추가

	OSTaskCreateExt((void (*)(void *)) OTATrigTask,
                	(void *) 0,
                	(OS_STK *) &OTATrigTaskStk[OTA_TRIG_TASK_STK_SIZE - 1],
                	(INT8U)    OTA_TRIG_TASK_PRIO,
                	(INT16U)   OTA_TRIG_TASK_PRIO,
                	(OS_STK *) &OTATrigTaskStk[0],
                	(INT32U)   OTA_TRIG_TASK_STK_SIZE,
                	(void *)   0,
                	(INT16U)  (OS_TASK_OPT_STK_CHK | OS_TASK_OPT_STK_CLR | OS_TASK_OPT_SAVE_FP));
	
	OSTaskCreateExt((void (*)(void *)) BatteryCheckTask,
                    (void *) 0,
                    (OS_STK *) &BatteryCheckTaskStk[BATTERY_CHECK_TASK_STK_SIZE - 1],
                    (INT8U)    APP_CFG_BATTERY_CHECK_TASK_PRIO,
                    (INT16U)   APP_CFG_BATTERY_CHECK_TASK_PRIO,
                    (OS_STK *) &BatteryCheckTaskStk[0],
                    (INT32U)   BATTERY_CHECK_TASK_STK_SIZE,
                    (void *)   0,
                    (INT16U)  (OS_TASK_OPT_STK_CHK | OS_TASK_OPT_STK_CLR | OS_TASK_OPT_SAVE_FP)); // ★ FPU 백업 옵션 추가


    /* 3. Communication Task 생성 (FPU 지원) */
    OSTaskCreateExt((void (*)(void *)) AppTaskComm,
                    (void *) 0,
                    (OS_STK *) &AppTaskCommStk[APP_CFG_COMM_TASK_STK_SIZE - 1],
                    (INT8U)    APP_CFG_COMM_TASK_PRIO,
                    (INT16U)   APP_CFG_COMM_TASK_PRIO,
                    (OS_STK *) &AppTaskCommStk[0],
                    (INT32U)   APP_CFG_COMM_TASK_STK_SIZE,
                    (void *)   0,
                    (INT16U)  (OS_TASK_OPT_STK_CHK | OS_TASK_OPT_STK_CLR | OS_TASK_OPT_SAVE_FP)); // ★ FPU 백업 옵션 추가
				 
	s_printf("uC/OS-II RTOS Initialization complete. Deleting Start Task...\r\n");
	OSTaskDel(OS_PRIO_SELF);
}

#define WHEEL_RADIUS 0.075f		// 6인치(15cm) 바퀴
#define WHEEL_TREAD  0.400f
#define PI			 3.141592f

float target_rpm_left;
float target_rpm_right;

static void ComputeTargetRpmTask(void *p_arg)
{
	(void)p_arg;
	INT8U err;

	float local_v, local_w;
	float v_left, v_right;

#if OS_CRITICAL_METHOD == 3
	OS_CPU_SR cpu_sr = 0;
#endif

	while (1) {
		OSSemPend(g_cmd_vel_sem, 0, &err);

		if (err == OS_ERR_NONE) {
			OS_ENTER_CRITICAL();
			// local_v = linear_x;
			// local_w = angular_z;
			memcpy(&local_v, &g_cmd_vel_buffer[0], sizeof(float));
        	memcpy(&local_w, &g_cmd_vel_buffer[4], sizeof(float));
			OS_EXIT_CRITICAL();

			//s_printf("%f %f\r\n", local_v, local_w);
			//s_printf("RAW: %02X %02X %02X %02X | VAL: %f\r\n", g_cmd_vel_buffer[0], g_cmd_vel_buffer[1], g_cmd_vel_buffer[2], g_cmd_vel_buffer[3], local_v);
			
			// 양쪽 바퀴의 목표 속도 계산 (m/s)
			v_left = local_v - (local_w * WHEEL_TREAD / 2.0f);
			v_right = local_v + (local_w * WHEEL_TREAD / 2.0f);

			// 양쪽 바퀴의 목표 속도를 목표 rpm으로 변환 후 부호에 맞게 모터 방향 설정
			OS_ENTER_CRITICAL();
			target_rpm_left = (v_left * 60.0f) / (2 * PI * WHEEL_RADIUS);
			if (target_rpm_left < 0.0f) {
				target_rpm_left *= -1;
				wheel_left_backward();
			}
			else {
				wheel_left_forward();
			}

			target_rpm_right = (v_right * 60.0f) / (2 * PI * WHEEL_RADIUS);
			if (target_rpm_right < 0.0f) {
				target_rpm_right *= -1;
				wheel_right_backward();
			}
			else {
				wheel_right_forward();
			}
			OS_EXIT_CRITICAL();
		}
	}
}

typedef struct {
    // 하드웨어 설정
    TIM_x *enc_timer;      		 // 엔코더 타이머
    volatile uint32_t *ccr_reg;  // PWM output레지스터
    
    // 제어 한 주기 당 발생한 펄스를 계산하기 위한 변수
    uint16_t last_cnt;

    volatile float current_rpm;
    volatile float target_rpm;
    
    // PID 변수
    float realError;
    float errorGap;
    float accError;
    float pControl, iControl, dControl;
} MotorController;

MotorController left_motor = {
	.enc_timer = TIM3,
	.ccr_reg = &(TIM1->CCR1),
	.last_cnt = 0,
	.current_rpm = 0.0f,
	.target_rpm = 0.0f,
	.realError = 0.0f
};

MotorController right_motor = {
	.enc_timer = TIM5,
	.ccr_reg = &(TIM8->CCR4),
	.last_cnt = 0,
	.current_rpm = 0.0f,
	.target_rpm = 0.0f,
	.realError = 0.0f
};

typedef struct {
    int16_t left_diff;
    int16_t right_diff;
} WheelDiffData;

static WheelDiffData g_wheel_data;

volatile int32_t enc_pos_left;

static int16_t update_encoder_diff(MotorController *motor)
{
	uint16_t current_cnt = (uint16_t)(motor->enc_timer->CNT);
	int16_t diff = (int16_t)(current_cnt - motor->last_cnt);	// 16비트 언더/오버플로우 자동보정
	motor->last_cnt = current_cnt;

	return diff;
}

// #define RPM_STEP        20.0f  // 테이블 간격 (20 RPM)
// #define MAX_RPM_INDEX   2      // (TABLE_SIZE - 2) -> 0, 20, 40, 80일 때 (4-2 = 2)

// static const float rpm_table[] = {0.0f, 20.0f, 40.0f, 80.0f};
// static const float ccr_table[] = {0.0f, 43.0f, 70.0f, 230.0f};

// static float get_feed_forward(float target_rpm)
// {
//     // 속도 크기(절댓값) 사용
//     float abs_rpm = (target_rpm < 0.0f) ? -target_rpm : target_rpm;

//     // 1. 하한/상한 예외 처리
//     if (abs_rpm <= rpm_table[0]) return 0.0f;
    
//     if (abs_rpm >= rpm_table[TABLE_SIZE - 1]) {
//         return ccr_table[TABLE_SIZE - 1]; // 무조건 양수 CCR 반환
//     }

//     // 2. O(1) 인덱스 계산
//     int idx = (int)(abs_rpm / RPM_STEP);
//     if (idx > MAX_RPM_INDEX) {
//         idx = MAX_RPM_INDEX;
//     }

//     // 3. 1차 선형 보간 (Linear Interpolation)
//     float rpm_low  = rpm_table[idx];
//     float rpm_high = rpm_table[idx + 1];
//     float ccr_low  = ccr_table[idx];
//     float ccr_high = ccr_table[idx + 1];

//     float ratio = (abs_rpm - rpm_low) / (rpm_high - rpm_low);
//     float ff_ccr = ccr_low + ratio * (ccr_high - ccr_low);

//     return ff_ccr;
// }

static uint16_t update_motor_pid(MotorController *motor, int16_t diff)
{
	uint32_t pulse_cnt = (diff < 0) ? -diff : diff;
	motor->current_rpm = (float)pulse_cnt * 0.30303f;	// (60 * pulse_cnt) / (0.05 * 11 * 90 * 4)

	if (motor->target_rpm == 0.0f) {
		motor->accError = 0.0f;
		motor->realError = 0.0f;
		motor->errorGap = 0.0f;

		motor->pControl = motor->iControl = motor->dControl = 0.0f;
	}
	else {
		motor->errorGap = motor->target_rpm - motor->current_rpm - motor->realError;
		motor->realError = motor->target_rpm - motor->current_rpm;
		motor->accError += motor->realError * DT;

		// I항 Anti-Windup
		// if (motor->accError > 30.0f) {
		// 	motor->accError = 30.0f;
		// }
		// else if (motor->accError < -30.0f) {
		// 	motor->accError = -30.0f;
		// }

		float contorl_diff = fabsf(motor->target_rpm - motor->current_rpm);

		float p_gain = (contorl_diff <= 30.0f) ? P_GAIN_SLOW : P_GAIN_FAST;
		float i_gain = (contorl_diff <= 30.0f) ? I_GAIN_SLOW : I_GAIN_FAST;
		float d_gain = (contorl_diff <= 30.0f) ? D_GAIN_SLOW : D_GAIN_FAST;

		motor->pControl = p_gain * motor->realError;
		motor->iControl = i_gain * motor->accError;
		motor->dControl = d_gain * (motor->errorGap / DT);
	}

	float output = motor->pControl + motor->iControl + motor->dControl;

	if (output < 0.0f) {
		output = 0.0f;
	}
	if (output > 999.0f) {
		output = 999.0f;
	}

	return (uint16_t)output;
}

static void MotorSpeedControlTask(void *p_arg)
{
	INT32U last_wake_time;
	(void)p_arg;

#if OS_CRITICAL_METHOD == 3
	OS_CPU_SR cpu_sr = 0;
#endif

	left_motor.last_cnt = (uint16_t)left_motor.enc_timer->CNT;
    right_motor.last_cnt = (uint16_t)right_motor.enc_timer->CNT;

	// debugging
	// wheel_left_forward();
	// wheel_right_forward();

	last_wake_time = OSTimeGet();

	while (1) {
		// 각 바퀴의 목표 속도 설정
		// target_rpm_left 변수는 상위 로직에서 절댓값 처리 후 모터 방향을 설정해야 함.
		OS_ENTER_CRITICAL();
		left_motor.target_rpm = target_rpm_left;
		right_motor.target_rpm = target_rpm_right;
		// left_motor.target_rpm = linear_x;		// debugging
		// right_motor.target_rpm = angular_z;
		OS_EXIT_CRITICAL();

		// 각 바퀴가 한 주기 동안 움직이며 발생한 펄스 측정
		int16_t left_diff = update_encoder_diff(&left_motor);
		int16_t right_diff = update_encoder_diff(&right_motor);

		// encoder 펄스 누적
		OS_ENTER_CRITICAL();
		enc_pos_left += left_diff;
		OS_EXIT_CRITICAL();

		// 한 주기 동안 발생한 펄스를 통해 속도 PID 제어
		uint16_t left_ccr_output = update_motor_pid(&left_motor, left_diff);
		uint16_t right_ccr_output =  update_motor_pid(&right_motor, right_diff);

		*(left_motor.ccr_reg) = left_ccr_output;
		*(right_motor.ccr_reg) = right_ccr_output;

		// Wheel Odometry 연산을 위해 UpdateWheelOdometry 태스크로 데이터 전송 및 동기화
		g_wheel_data.left_diff = left_diff;
		g_wheel_data.right_diff = right_diff;
		OSMboxPost(WheelOdometryMbox, (void *)&g_wheel_data);

		// 50ms 주기로 제어
		TimeDlyUntil(&last_wake_time, 50);
	}
}

// 라즈베리파이 시리얼 전송용 구조체 정의 (바이트 정렬)
typedef struct __attribute__((packed)) {
	uint8_t header1;
	uint8_t header2;
    uint32_t timestamp;        // 시간 정보 (ms)
    float    pos_x;            // 누적 X (m)
    float    pos_y;            // 누적 Y (m)
    float    theta;            // 누적 각도 (rad)
    float    linear_vel_x;     // 현재 선속도 (m/s)
    float    angular_vel_z;    // 현재 각속도 (rad/s)
	uint8_t  checksum;         // 검증용 XOR 체크섬
} OdomPacket_T;

OdomPacket_T tx_odom_packet;   // 라즈베리파이로 보낼 전송 버퍼

float robot_theta = 0.0f;
float robot_x = 0.0f;
float robot_y = 0.0f;
#define ROBOT_WHEEL_BASE 0.400f

// odometry 패킷의 체크섬 검사
static uint8_t calculate_checksum(const uint8_t *pData, uint16_t length) {
    uint8_t checksum = 0;
    for (uint16_t i = 0; i < length; i++) {
        checksum ^= pData[i];
    }
    return checksum;
}

void update_robot_odometry(float left_delta, float right_delta)
{
#if OS_CRITICAL_METHOD == 3
	OS_CPU_SR cpu_sr = 0;
#endif

	// 50ms 동안 정면 방향으로 몇 m 앞으로 전진했는지
	// 50ms 동안의 이전 위치 벡터로 부터 몇 라디안 기울어 졌는지
	float delta_s = (right_delta + left_delta) / 2.0f;
    float delta_theta = (right_delta - left_delta) / ROBOT_WHEEL_BASE;

	// 한 주기가 50ms 이므로 그 기간동안 직진한걸로 간주하는 효과를 감쇄
	float middle_theta = robot_theta + (delta_theta / 2.0f);

	OS_ENTER_CRITICAL();

    // 1. [Pose] 위치 누적 연산
    robot_x += delta_s * cosf(middle_theta);
    robot_y += delta_s * sinf(middle_theta);
    robot_theta += delta_theta;
    
    // 각도 정규화 (-PI ~ +PI)
    if (robot_theta > 3.141592f)  robot_theta -= 2.0f * 3.141592f;
    if (robot_theta < -3.141592f) robot_theta += 2.0f * 3.141592f;

	OS_EXIT_CRITICAL();

    // 2. [Twist] 실시간 속도 연산
    float current_linear_vel = delta_s / DT;
    float current_angular_vel = delta_theta / DT;

    // 3. [전송 패킷 패킹] 라즈베리파이로 보낼 데이터 최종 취합
	// 차동구동 로봇이므로 linear.y=0, linear.z=0, angular.x=0, angular.y=0
	tx_odom_packet.header1       = 0xAA;
    tx_odom_packet.header2       = 0x55;
    tx_odom_packet.timestamp     = OSTimeGet(); // 또는 OSTimeGet()
    tx_odom_packet.pos_x         = robot_x;
    tx_odom_packet.pos_y         = robot_y;
    tx_odom_packet.theta         = robot_theta;
    tx_odom_packet.linear_vel_x  = current_linear_vel;
    tx_odom_packet.angular_vel_z = current_angular_vel;

	// 헤더부터 angular_vel_z까지의 영역만 체크섬 계산 (checksum 필드 제외)
    uint16_t data_len = sizeof(OdomPacket_T) - sizeof(uint8_t);
    tx_odom_packet.checksum = calculate_checksum((uint8_t *)&tx_odom_packet, data_len);

	uart3_dma_send_packet((uint8_t *)&tx_odom_packet, sizeof(OdomPacket_T));
}

static void UpdateWheelOdometry(void *p_arg)
{
	INT8U err;
	//INT32U last_wake_time;
	WheelDiffData *pDiff;

	int16_t left_encoder_delta;	// 50ms 동안의 엔코더 펄스 벡터
	int16_t right_encoder_delta;

	float left_wheel_turns;
	float right_wheel_turns;

	float left_wheel_delta;
	float right_wheel_delta;

	(void)p_arg;	

#if OS_CRITICAL_METHOD == 3
	OS_CPU_SR cpu_sr = 0;
#endif

	//last_wake_time = OSTimeGet();

	/* 50ms 주기로 휠 오도메트리 데이터 출력 */
	while (1) {
		// encoder_diff 변수 값을 받기 위해 waiting
		// 오른쪽 바퀴 pid제어 코드도 완성되면 구조체 포인터로 양쪽 diff 변수를 받아야 함
		pDiff = (WheelDiffData *)OSMboxPend(WheelOdometryMbox, 0, &err);

		if (err == OS_ERR_NONE && pDiff != NULL) {
			left_encoder_delta = -pDiff->left_diff;
			right_encoder_delta = -pDiff->right_diff;

			left_wheel_turns = (float)left_encoder_delta / 3960.0f;				// 11 * 4 * 90
			left_wheel_delta = left_wheel_turns * 2.0f * PI * WHEEL_RADIUS;		// 2*pi*r

			right_wheel_turns = (float)right_encoder_delta / 3960.0f;
			right_wheel_delta = right_wheel_turns * 2.0f * PI * WHEEL_RADIUS;

			OS_ENTER_CRITICAL();
			left_wheel_distance += left_wheel_delta;
			OS_EXIT_CRITICAL();

			update_robot_odometry(left_wheel_delta, right_wheel_delta);
		}

		// mailbox pend API가 blocking 해주므로 Delay가 필요없음
		//TimeDlyUntil(&last_wake_time, 100);
	}
}

void delay_us(uint32_t us)
{
	uint32_t start_val = TIM2->CNT;

	while ((uint32_t)(TIM2->CNT - start_val) < us);
}

#define FILTER_SIZE 5

float apply_median_filter(float new_val) {
    static float buf[FILTER_SIZE] = {0.0f};
    static int idx = 0;
    
    buf[idx] = new_val;
    idx = (idx + 1) % FILTER_SIZE;

    // 버퍼 복사 후 정렬
    float temp[FILTER_SIZE];
    for(int i = 0; i < FILTER_SIZE; i++) temp[i] = buf[i];

    // 단순 버블 정렬 (크기가 작으므로 충분히 빠름)
    for(int i = 0; i < FILTER_SIZE - 1; i++) {
        for(int j = 0; j < FILTER_SIZE - i - 1; j++) {
            if(temp[j] > temp[j+1]) {
                float t = temp[j];
                temp[j] = temp[j+1];
                temp[j+1] = t;
            }
        }
    }

    // 중앙값 반환
    return temp[FILTER_SIZE / 2];
}

void HCSR04_sensor_init(void)
{
	// trig pin setup
	gpio_set_mode(GPIOD, 11, GPIO_MODE_OUTPUT);
	gpio_set_ospeed(GPIOD, 11, GPIO_OSPEED_VH);
	gpio_write_pin(GPIOD, 11, 0);

	// echo pin setup. TIM4_CH1
	gpio_set_mode(GPIOD, 12, GPIO_MODE_AF);
	gpio_set_af(GPIOD, 12, TIM3_5_PIN_AF);

	timer_init(TIM4, 84 - 1, 0xFFFF);

	// echo 신호의 길이를 재기 위한 TIM4 PWM Input Mode 설정
	// TIM4의 채널1과 채널2를 모두 TI1(ch1핀)에 연결하여 같은 신호가 두 채널에 보이게 설정
	// 채널1 : rising edge에서 CNT 레지스터 초기화
	// 채널2 : falling edge에서 CNT 레지스터 값 캡처
	TIM4->CCMR1 &= ~((3 << 0) | (3 << 8));
	TIM4->CCMR1 |= (1 << 0) | (2 << 8);		// CC1S = 01, CC2S = 10

	// CC1E(0), CC1P(1), CC1NP(3), CC2E(4), CC2P(5), CC2NP(7) 비트 영역 초기화
	// 채널1을 rising edge를 감지하도록 설정, 채널2를 falling edge를 감지하도록 설정
	TIM4->CCER &= ~((1 << 0) | (1 << 1) | (1 << 3) | (1 << 4) | (1 << 5) | (1 << 7));
	TIM4->CCER |= (1 << 0) | (1 << 4) | (1 << 5);

	// 채널1의 rising edge 트리거가 발생했을 때 CNT를 초기화 하도록 설정
	TIM4->SMCR &= ~((7 << 0) | (7 << 4));
	TIM4->SMCR |= (4 << 0) | (5 << 4);		// SMS = 100, TS = 101

	// 채널2의 falling edge에서 인터럽트가 발생하도록 설정
	TIM4->DIER |= (1 << 2);		// CC2IE set

	// TIM4 인터럽트 활성화
	nvic_irq_enable(NVIC_TIM4_IRQN);
	nvic_irq_setprio(NVIC_TIM4_IRQN, 6);

	// TIM4 카운트 시작
	//TIM4->EGR |= (1 << 0);  // Update Generation (설정값 즉시 반영)
	//TIM4->SR  &= ~(1 << 0); // EGR로 인해 발생하는 UIF(Update Interrupt Flag) 클리어
	//timer_init(TIM4, 84 - 1, 0xFFFF);
	timer_start(TIM4);

	// us delay를 위한 타이머
	timer_init(TIM2, 84 - 1, 0xFFFF);
	timer_start(TIM2);
}

static void UltrasonicSensorTask(void *p_arg)
{
	INT8U err;
	INT32U last_wake_time;
	(void)p_arg;

	uint32_t duration;
	float distance_cm, filtered_distance;
	float prev_valid_dist = 0.0f;

#if OS_CRITICAL_METHOD == 3
	OS_CPU_SR cpu_sr = 0;
#endif

	gpio_set_mode(GPIOE, 0, GPIO_MODE_OUTPUT);
	gpio_write_pin(GPIOE, 0, 0);

	last_wake_time = OSTimeGet();

	while (1) {
		// Mail box flush
		(void)OSMboxAccept(HCSR04DurationMbox);

		// Trig pin 활성화
		OS_ENTER_CRITICAL();

		gpio_write_pin(GPIOD, 11, 1);
		delay_us(10);
		gpio_write_pin(GPIOD, 11, 0);

		OS_EXIT_CRITICAL();

		// Echo pin 으로 들어오는 duration 측정
		duration = (uint32_t)OSMboxPend(HCSR04DurationMbox, 100, &err);

		if (err == OS_ERR_NONE) {
			distance_cm = (float)duration / 58.0f;

			if (distance_cm < 2.0f || distance_cm > 100.0f) {
				filtered_distance = prev_valid_dist;
			}
			else {
				filtered_distance = apply_median_filter(distance_cm);
				prev_valid_dist = distance_cm;
			}

			if (filtered_distance < 30.f) {
				gpio_write_pin(GPIOE, 0, 1);
			}
			else {
				gpio_write_pin(GPIOE, 0, 0);
			}

			//s_printf("%f, %f\r\n", filtered_distance, distance_cm);
		}
		else if (err == OS_ERR_TIMEOUT) {
			//s_printf("No Detected\r\n");
		}

		TimeDlyUntil(&last_wake_time, 200);
	}
}

// 1초 이상 신호를 주어야 소프트웨어 리셋이 걸리도록 구현
static void OTATrigTask(void *p_arg)
{
	INT8U err;
	(void)p_arg;

	while (1) {
		OSSemPend(ButtonSem, 0, &err);

    	OSTimeDly(1000);

    	if (gpio_read_pin(GPIOE, 4) == 0)
    	{
       		SoftwareReset();
    	}
	}
}

#define LOW_BAT_THRESHOLD 10.5f

// PB0 ADC1 Channel 8 Init
void ADC1_bat_check_init(void)
{
	RCC_APB2_CLOCK_ER |= ADC1_APB2_CLOCK_ER_VAL;

	gpio_set_mode(GPIOB, 0, GPIO_MODE_ANALOG);

	// ADC1의 클록을 PCLK2 / 4(84M / 4)로 설정
	ADC->CCR &= ~(3U << 16);
	ADC->CCR |= (1U << 16);

	// ADC1을 12bit resolution, scan mode disable로 설정
	ADC1->CR1 &= ~(3U << 24);
	ADC1->CR1 &= ~(1U << 8);

	// ADC1을 right 정렬, single conversion mode로 설정
	ADC1->CR2 &= ~(1U << 11);
	ADC1->CR2 &= ~(1U << 1);

	// ADC1 채널8의 sampling time을 84 cycle로 설정
	ADC1->SMPR2 &= ~(7U << (8 * 3));
	ADC1->SMPR2 |= (4U << (8 * 3));

	// 변환 순서 및 개수 설정 (1개 변환, Channel 8)
	ADC1->SQR1 &= ~(0xFU << 20);
	ADC1->SQR3 &= ~(0x1FU << 0);
	ADC1->SQR3 |= (8U << 0);

	// ADC1 on
	ADC1->CR2 |= (1U << 0);
}

uint16_t battery_read_raw(void)
{
	// Analog to Digital 변환 시작
	ADC1->CR2 |= (1U << 30);

	// 변환 완료 대기
	while (!(ADC1->SR & (1U << 1)));

	return (uint16_t)(ADC1->DR);
}

static void BatteryCheckTask(void *p_arg)
{
	(void)p_arg;
	uint16_t adc_raw;
	float battery_voltage;

	while (1) {
		adc_raw = battery_read_raw();

		battery_voltage = ((float)adc_raw / 4095.0f) * 3.3f * 4.0f;

		if (battery_voltage < LOW_BAT_THRESHOLD) {
			// 부저 on
		}
		else {
			// 부저 off
		}

		OSTimeDly(1000);
	}
}

static void AppTaskComm(void *p_arg)
{
    //INT32U last_wake_time;
    (void)p_arg;
	//rx_count = 0;
    //last_wake_time = OSTimeGet();

    while (1) {
		led_toggle();
		//s_printf("rpm : %f\r\n", current_rpm);
		//s_printf("distance : %f\r\n", left_wheel_distance);

		//s_printf("target rpm : %d\r\n", target_rpm);
		// if (uart_idle_flag) {
		// 	uart_idle_flag = 0;

		// 	s_printf("linear_x : %f\r\nangular_z : %f\r\n\r\n", linear_x, angular_z);
		// }
		//s_printf("%d\r\n", rx_count);
		
		// s_printf("left  rpm : %f %d\r\n", left_motor.current_rpm, *(left_motor.ccr_reg));
		// s_printf("right rpm : %f %d\r\n\r\n", right_motor.current_rpm, *(right_motor.ccr_reg));

		OSTimeDly(500);
    }
}