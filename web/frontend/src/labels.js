/** 안내견 도메인 값 → 한글 표시 매핑 (컴포넌트 공용) */

/** 기체 이상 이벤트 — 로봇이 POST /api/events로 올린다 (서버가 만들지 않는다) */
export const EVENT_CODE = {
  IMPACT: { label: '충격 감지', icon: '💥' },
  FALL: { label: '낙하 감지', icon: '⬇' },
  EMERGENCY_STOP: { label: '비상 정지', icon: '⛔' },
  LOW_BATTERY: { label: '배터리 부족', icon: '🔋' },
  COMM_LOST: { label: '통신 두절', icon: '📡' },
}

/** 관리자 개입 요청 사유 — 로봇이 스스로 못 푸는 상황(사람이 현장에 가야 풀린다).
 *  기록으로만 남는 기체 이벤트와 달리 전체 화면 팝업으로 뜨고, 해결해야 닫힌다. */
export const ASSIST_REASON = {
  path_blocked: { label: '통행 불가', icon: '⛔' },
  repeated_brake: { label: '반복 정지', icon: '↺' },
  drop_hazard: { label: '낙하 위험', icon: '⚠' },
  robot_stuck: { label: '로봇 기동 불가', icon: '✖' },
  help_requested: { label: '보행자 도움 요청', icon: '🙋' },
}

/** 화면에 띄우는 로봇 상태 (stores/robot.liveStatus).
 *  세션 상태(WALKING/ARRIVED)만으로는 세션 없이 주행만 하는 상황을 표현할 수 없어,
 *  위치 수신 여부와 실제 이동 여부를 합쳐 판정한 값을 쓴다. */
export const LIVE_STATUS = {
  MOVING: { label: '이동중', tone: 'amber' },
  IDLE: { label: '정지', tone: 'muted' },
  ARRIVED: { label: '도착', tone: 'ok' },
  EMERGENCY: { label: '비상 정지', tone: 'danger' },
  OFFLINE: { label: '위치 미수신', tone: 'muted' },
}

export const MODE = {
  ASSIST: '자유 동행',
  GUIDE: '목적지 안내',
}

export const assistReasonLabel = (r) => ASSIST_REASON[r]?.label ?? r
export const assistReasonIcon = (r) => ASSIST_REASON[r]?.icon ?? '⚠'
export const eventLabel = (c) => EVENT_CODE[c]?.label ?? c
export const eventIcon = (c) => EVENT_CODE[c]?.icon ?? '•'
