import { defineStore } from 'pinia'

const MAX_LOG = 50

// pose 표본 간 속도로 '움직이는 중'을 판정한다. 0.1 m/s = 300ms에 3cm — 좌표가 소수
// 2자리(1cm)로 반올림돼 들어오므로 SLAM 지터로는 잘 넘지 않고, 사람 보행 속도(0.4~0.6)는
// 확실히 넘는 선이다.
const MOVING_MPS = 0.1
// 표본 하나가 튀어도 배지가 깜빡이지 않게 지수평활을 건다 (새 표본 40%).
const SPEED_SMOOTHING = 0.4
// 이보다 빠른 표본은 '이동'이 아니라 좌표가 튄 것으로 본다 — SLAM 재측위나 시뮬 순간이동은
// 몇 미터를 한 프레임에 건너뛰어서, 그대로 환산하면 보행 보조 로봇에 8 m/s 같은 값이 찍힌다.
const TELEPORT_MPS = 3.0

/** 로봇 + 현재 보행 세션 단일 저장소.
 *
 *  서버는 값을 지어내지 않는다 — 로봇이 안 보내면 telemetry의 해당 필드는 null로 온다.
 *  그래서 "null = 미수신"이 이 스토어 전체의 규칙이고, 화면은 그 상태를 그대로 표시한다.
 *  세션 요약은 telemetry.session으로 매 틱 갱신되고, 기체 이벤트(event)는 별도 WS
 *  메시지로 들어와 링버퍼에 쌓인다. */
export const useRobotStore = defineStore('robot', {
  state: () => ({
    connected: false,
    telemetry: null,     // {pos,status,battery,session,dest,obstacles,...}
    lidar: null,         // 스캔 미수신 구간에서는 null (마지막 스캔이 남지 않게)
    events: [],          // 최근 기체 이벤트 (최신순)
    alert: null,         // CRITICAL 기체 이벤트 → 경고 배너 (WEB-05)
    speed: 0,            // pose 변화로 추정한 이동 속도(m/s) — 로봇은 속도를 보내지 않는다
    posAt: 0,            // 직전 pos를 받은 시각(ms) — 속도 계산용
    /** 콘솔에서 명시적으로 켠 프론트 시뮬 로봇 (services/simRobot.js). null = 꺼짐.
     *
     *  절대 자동으로 켜지지 않는다. 목이 조용히 자리를 채워주면 '로봇 미연결'과 '정상 주행'이
     *  화면에서 똑같아져 브리지가 죽어도 알 수 없다 — 그게 S15P11C201-147에서 목을 통째로
     *  걷어낸 이유다. 시뮬은 사람이 콘솔에서 켠 동안만 살아 있다.
     *  시연용이라 화면에는 표식을 두지 않으므로, 켜져 있는지는 콘솔(lumi.sim.on())로만 안다. */
    sim: null,           // {x, y, heading} — 활성 지도와 같은 프레임(m, 도)
  }),
  getters: {
    simOn: (s) => s.sim !== null,
    /** 로봇 pose(POST /api/pose)가 TTL 이내일 때만 채워진다. null = 위치 미수신.
     *  시뮬이 켜져 있으면 그쪽이 이긴다 — 사용자가 방금 켠 것이기 때문이다.
     *  화면은 실 pose와 똑같이 그리지만, sim 표식은 값에 남겨 둔다(콘솔·devtools 확인용). */
    pos: (s) => {
      if (!s.sim) return s.telemetry?.pos ?? null
      return {
        mode: 'slam',
        sim: true,
        x: Number(s.sim.x.toFixed(2)),
        y: Number(s.sim.y.toFixed(2)),
        heading: ((Math.round(s.sim.heading) % 360) + 360) % 360,
      }
    },
    moving: (s) => s.speed >= MOVING_MPS,
    /** 화면에 띄우는 로봇 상태. telemetry.status는 '세션이 어디까지 왔나'라서, 세션 없이
     *  주행만 하는 지금 구성에서는 로봇이 복도를 달려도 STANDBY로 남는다. 위치 수신 여부와
     *  실제 이동 여부를 함께 봐서 화면에는 눈에 보이는 사실을 쓴다. */
    liveStatus(s) {
      if (s.telemetry?.status === 'EMERGENCY') return 'EMERGENCY'
      if (!this.pos) return 'OFFLINE'
      if (s.speed >= MOVING_MPS) return 'MOVING'
      return s.telemetry?.status === 'ARRIVED' ? 'ARRIVED' : 'IDLE'
    },
    battery: (s) => s.telemetry?.battery ?? null,      // 수신 창구가 생기기 전까지 항상 null
    dest: (s) => s.telemetry?.dest ?? null,
    obstacles: (s) => s.telemetry?.obstacles ?? [],
    // 실 비콘 스캔(POST /api/beacon-scan)만 실린다.
    // null = TTL(5초) 내 미수신, [] = 수신 중이나 감지된 비콘 없음. 이 둘을 구분해야
    // '로봇이 안 붙었다'와 '붙었는데 신호가 없다'를 화면에서 가려낼 수 있다.
    beacons: (s) => s.telemetry?.beacons ?? null,
    nearestBeaconNo: (s) => s.telemetry?.beacon_nearest_no ?? null,
    session: (s) => s.telemetry?.session ?? null,      // null이면 대기(동행 없음)
    mode: (s) => s.telemetry?.session?.mode ?? null,   // ASSIST|GUIDE
  },
  actions: {
    setConnected(v) {
      this.connected = v
      // 시뮬은 서버와 무관하게 돈다 — WS가 끊겼다고 시뮬 로봇까지 세우지 않는다
      if (!v && !this.sim) {
        this.lidar = null   // 끊긴 뒤 마지막 스캔이 지도에 남지 않게
        this.speed = 0      // 끊긴 로봇이 '이동중'으로 남지 않게
      }
    },
    applyTelemetry(msg) {
      // 시뮬 중에는 속도를 시뮬 루프가 직접 넣는다. 여기서 같이 계산하면 실 pos가 null이라
      // 매 틱 0으로 덮여, 시뮬이 아무리 달려도 화면에는 '정지'로 뜬다.
      if (!this.sim) this.trackSpeed(this.telemetry?.pos, msg?.pos)
      this.telemetry = msg
    },

    // ── 프론트 시뮬 로봇 (services/simRobot.js 전용) ──────────
    startSim(pose) {
      this.sim = { ...pose }
      this.speed = 0
    },
    updateSim(pose, speed) {
      this.sim = { ...pose }
      this.speed = speed
    },
    stopSim() {
      this.sim = null
      this.speed = 0
    },
    /** 연속한 두 pose 표본의 이동 거리 ÷ 경과로 속도를 낸다.
     *  pose가 끊기거나(pos=null) 비콘 존 좌표로 바뀌면 0으로 되돌린다 — 존 단위 위치는
     *  건물 반대편으로 튀어서, 그 도약을 속도로 환산하면 '전력질주'가 찍힌다. */
    trackSpeed(prev, next) {
      const now = Date.now()
      const elapsed = (now - this.posAt) / 1000
      this.posAt = now
      if (prev?.mode !== 'slam' || next?.mode !== 'slam' || elapsed <= 0) {
        this.speed = 0
        return
      }
      const sample = Math.hypot(next.x - prev.x, next.y - prev.y) / elapsed
      if (sample > TELEPORT_MPS) {
        // 도약은 평활에 섞지 않는다 — 한 번 섞이면 몇 초간 '이동중'으로 남는다
        this.speed = 0
        return
      }
      this.speed = this.speed * (1 - SPEED_SMOOTHING) + sample * SPEED_SMOOTHING
    },
    /** 서버는 미수신 틱에도 ranges=null인 스캔을 보낸다 — 그걸 받아 지도를 비운다 */
    applyLidar(msg) {
      this.lidar = msg?.ranges ? msg : null
    },
    applyEvent(msg) {
      this.events.unshift(msg)
      if (this.events.length > MAX_LOG) this.events.pop()
      if (msg.level === 'CRITICAL') this.alert = msg
    },
    dismissAlert() {
      this.alert = null
    },
  },
})
