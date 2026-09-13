/** 프론트 시뮬 로봇 — 콘솔에서 켜고 방향키로 모는 데모용 로봇 (S15P11C201-149·150).
 *
 *  왜 콘솔인가: 서버는 로봇 값을 지어내지 않는다(S15P11C201-147). 목이 자동으로 자리를
 *  채워주면 '로봇 미연결'과 '정상 주행'이 화면에서 똑같아져, 시연 중 브리지가 죽어도
 *  알 방법이 없기 때문이다. 그래서 이 시뮬은 자동으로 켜지지 않는다.
 *
 *  두 가지 모드가 있다:
 *    local (기본) — 이 브라우저에서만. 백엔드가 없어도 되고 서버에 흔적도 안 남는다.
 *    live         — 위에 더해 POST /api/pose로도 쏜다. 실 로봇이 쓰는 바로 그 인그레스라
 *                   접속한 다른 대시보드에도 실시간으로 뜬다.
 *
 *  두 모드 모두 **조종 중인 이 화면은 시뮬을 우선**한다(stores/robot.js의 pos getter).
 *  서버는 실 브리지 좌표를 막지 않으므로, live 중에 실 로봇이 같이 쏘면 서버에 남는 값은
 *  둘이 섞인다 — 그래도 조종 화면은 흔들리지 않는다. 막지 않는 이유는 서버가 실 데이터를
 *  차단하면 그 사이 브리지가 죽어도 아무도 모르기 때문이다.
 *
 *  시연 화면에는 시뮬 표식을 두지 않는다(제품 화면 그대로 보여주기 위함). 따라서 지금
 *  보이는 로봇이 진짜인지 시뮬인지 구분할 수 있는 곳은 **이 콘솔뿐**이다 — `lumi.sim.on()`.
 *
 *  좌표계는 실 pose와 같다 — 활성 SLAM 맵의 map 프레임(m), heading은 +x축 기준 반시계
 *  각도(도). 맵이 없어 도면으로 폴백한 경우 도면 좌표를 쓴다. 덕분에 MapPanel은 진짜
 *  로봇과 완전히 같은 변환으로 시뮬을 그린다.
 */
import { API_BASE } from '@/services/api'
import { useFloorplanStore } from '@/stores/floorplan'
import { useMapStore } from '@/stores/map'
import { useRobotStore } from '@/stores/robot'

const LINEAR_MPS = 1.0      // 전·후진 속도 — 보행 속도(0.4~0.6)보다 빠르게, 시연 중 넓은
                            // 도면을 가로지르는 데 걸리는 시간을 줄이려고 올린 값이다
const TURN_DPS = 120        // 회전 속도(도/초)
const MARGIN_M = 0.3        // 지도 경계에서 이만큼 안쪽까지만 — 마커가 잘려 사라지지 않게
const SEND_MS = 200         // live 모드 전송 주기 — 실 브리지 권장치(5Hz)와 같게
const WARN_MS = 5_000       // 전송 실패 로그 최소 간격 — 콘솔을 도배하지 않게

const STEP_MS = 50          // 적분 주기(20Hz) — 지도 마커가 부드럽게 움직이기 충분하다

// 키를 누르고 있는 동안 계속 움직인다(keydown 자동반복에 의존하면 뚝뚝 끊긴다)
const HELD = new Set()
// requestAnimationFrame이 아니라 setInterval을 쓴다: rAF는 탭이 백그라운드로 가면 아예
// 멈춘다. live 모드에서 그러면 전송이 끊겨 접속한 모든 대시보드가 2초(TTL) 뒤 '미수신'이
// 된다 — 조종하던 사람이 잠깐 다른 창을 봤을 뿐인데 로봇이 죽은 것처럼 보인다.
let timer = null
let lastAt = 0
let lastSendAt = 0

// 시뮬의 진짜 상태는 여기 있다. 두 모드 모두 이 값을 스토어에 복사해 화면을 그린다 —
// live 모드에서 텔레메트리로 되돌아온 값을 그리면, 실 브리지가 동시에 쏘는 동안 로봇이
// 시뮬 위치와 실 위치 사이를 튄다. 서버는 실 좌표를 계속 받고(막지 않는다), 화면에서만
// 시뮬을 우선한다.
let pose = null             // {x, y, heading}
let live = false
let inFlight = false        // 응답이 늦을 때 요청이 쌓이지 않게
let lastWarnAt = 0

/** 지도(맵 우선, 없으면 도면)의 좌표 범위. 시뮬을 띄울 지도가 없으면 null */
function bounds() {
  const m = useMapStore().active
  if (m) {
    const [ox, oy] = m.origin
    return {
      minX: ox, minY: oy,
      maxX: ox + m.width * m.resolution,
      maxY: oy + m.height * m.resolution,
      label: 'SLAM 맵',
    }
  }
  const p = useFloorplanStore().active
  if (p) {
    return {
      minX: 0, minY: 0,
      maxX: p.width_px / p.px_per_m,
      maxY: p.height_px / p.px_per_m,
      label: p.name ?? '도면',
    }
  }
  return null
}

function clamp(v, lo, hi) {
  return Math.min(Math.max(v, lo), hi)
}

function onKeyDown(e) {
  // 입력창에 타이핑 중이면 가로채지 않는다 (장소명·비밀번호 입력 등)
  const tag = e.target?.tagName
  if (tag === 'INPUT' || tag === 'TEXTAREA' || e.target?.isContentEditable) return
  if (!e.key.startsWith('Arrow')) return
  HELD.add(e.key)
  e.preventDefault()   // 방향키로 페이지가 스크롤되지 않게
}

function onKeyUp(e) {
  HELD.delete(e.key)
}

/** 창 밖을 클릭했다 돌아오면 keyup을 놓쳐 키가 눌린 채로 남는다 — 포커스 잃으면 전부 뗀다 */
function onBlur() {
  HELD.clear()
}

/** 실 브리지와 같은 경로로 pose를 올린다. 실패해도 시뮬은 계속 돈다 —
 *  백엔드가 잠깐 끊겼다고 조작이 멈추면 시연 중에 더 곤란하다.
 *
 *  `sim: true`를 실어 서버가 시뮬임을 알게 한다. 그동안 서버는 실 브리지 좌표를 막아,
 *  로봇이 시뮬 위치와 실 위치 사이를 튀지 않게 한다(backend routers/pose.py). */
function sendPose() {
  if (inFlight) return
  inFlight = true
  fetch(`${API_BASE}/api/pose`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      x: Number(pose.x.toFixed(2)),
      y: Number(pose.y.toFixed(2)),
      heading: Math.round(pose.heading),
      sim: true,
    }),
  })
    .catch((err) => {
      const now = Date.now()
      if (now - lastWarnAt > WARN_MS) {
        lastWarnAt = now
        console.warn('[lumi.sim] pose 전송 실패 — 백엔드를 확인하세요.', err?.message ?? err)
      }
    })
    .finally(() => {
      inFlight = false
    })
}

function tick() {
  if (!pose) return
  const now = performance.now()
  // 탭이 백그라운드로 밀리면 브라우저가 타이머를 1초까지 늦춘다 — 그 간격을 그대로
  // 적분하면 복귀 순간 로봇이 몇 미터 튄다. 한 걸음을 0.1초로 묶어 둔다.
  const dt = lastAt ? Math.min((now - lastAt) / 1000, 0.1) : 0
  lastAt = now
  if (!dt) return

  const drive = (HELD.has('ArrowUp') ? 1 : 0) - (HELD.has('ArrowDown') ? 1 : 0)
  const turn = (HELD.has('ArrowLeft') ? 1 : 0) - (HELD.has('ArrowRight') ? 1 : 0)

  pose.heading += turn * TURN_DPS * dt
  if (drive) {
    const rad = (pose.heading * Math.PI) / 180
    pose.x += Math.cos(rad) * LINEAR_MPS * drive * dt
    pose.y += Math.sin(rad) * LINEAR_MPS * drive * dt
    const b = bounds()
    if (b) {
      pose.x = clamp(pose.x, b.minX + MARGIN_M, b.maxX - MARGIN_M)
      pose.y = clamp(pose.y, b.minY + MARGIN_M, b.maxY - MARGIN_M)
    }
  }

  // 이 화면은 항상 시뮬을 그린다 (스토어 pos getter가 sim을 우선한다)
  useRobotStore().updateSim(pose, drive ? LINEAR_MPS : 0)

  if (live) {
    // 서 있어도 계속 보낸다 — 멈추면 TTL(2초)이 지나 다른 화면에서 로봇이 사라진다.
    // 적분용 dt가 아니라 실제 경과로 재야 백그라운드에서도 전송이 이어진다.
    if (now - lastSendAt >= SEND_MS) {
      lastSendAt = now
      sendPose()
    }
  }
}

function attach() {
  window.addEventListener('keydown', onKeyDown)
  window.addEventListener('keyup', onKeyUp)
  window.addEventListener('blur', onBlur)
  lastAt = 0
  lastSendAt = 0        // 켜자마자 한 번 보내 화면에 바로 뜨게
  timer = setInterval(tick, STEP_MS)
}

function detach() {
  window.removeEventListener('keydown', onKeyDown)
  window.removeEventListener('keyup', onKeyUp)
  window.removeEventListener('blur', onBlur)
  clearInterval(timer)
  timer = null
  HELD.clear()
}

/** 인자를 위치형(x, y, deg)과 옵션 객체 양쪽으로 받는다 */
function parseArgs(args) {
  if (args.length && typeof args[0] === 'object' && args[0] !== null) {
    const o = args[0]
    return { x: o.x, y: o.y, heading: o.heading ?? 0, live: !!o.live }
  }
  const [x, y, heading = 0] = args
  return { x, y, heading, live: false }
}

/** 시뮬 시작. 좌표를 생략하면 지도 한가운데에서 시작한다.
 *
 *  @example lumi.sim()                                  이 브라우저에서만
 *  @example lumi.sim(41.6, 24.5, 0)                     좌표·방향 지정
 *  @example lumi.sim({ live: true })                    모든 대시보드에 실시간
 *  @example lumi.sim({ live: true, x: 41.6, y: 24.5 })
 */
export function startSim(...args) {
  const opts = parseArgs(args)
  const robot = useRobotStore()
  const b = bounds()
  if (!b) {
    console.warn('[lumi.sim] 표시할 지도가 없습니다 — 로봇이 SLAM 맵을 보내거나 도면을 등록해야 합니다.')
    return false
  }

  const wasRunning = pose !== null

  pose = {
    x: clamp(opts.x ?? (b.minX + b.maxX) / 2, b.minX + MARGIN_M, b.maxX - MARGIN_M),
    y: clamp(opts.y ?? (b.minY + b.maxY) / 2, b.minY + MARGIN_M, b.maxY - MARGIN_M),
    heading: opts.heading,
  }
  live = opts.live

  // 두 모드 모두 이 화면은 시뮬을 그린다 — 실 pose가 들어와도 시뮬이 이긴다
  robot.startSim(pose)
  if (robot.telemetry?.pos && !robot.telemetry.pos.sim) {
    console.warn('[lumi.sim] 실 로봇 pose를 수신 중입니다 — 이 화면은 시뮬을 우선합니다. 끄면 되돌아옵니다.')
  }
  if (!wasRunning) attach()

  const where = `(${pose.x.toFixed(2)}, ${pose.y.toFixed(2)}) heading ${pose.heading}°`
  console.log(
    `%c🤖 시뮬 로봇 ON · ${live ? 'LIVE' : 'LOCAL'}%c  ${
      live
        ? 'POST /api/pose로 전송 — 다른 대시보드에도 뜹니다 (서버는 실 좌표도 계속 받습니다)'
        : '이 브라우저에서만 — 서버에는 아무것도 보내지 않습니다'
    }\n` +
      `   지도: ${b.label} · 시작 ${where}\n` +
      `   ↑ 전진 · ↓ 후진 · ← 좌회전 · → 우회전  (누르고 있으면 계속)\n` +
      `   상태 확인: lumi.sim.on()  ·  끄기: lumi.sim.stop()`,
    'font-weight:bold;color:#b45309',
    'color:inherit',
  )
  return true
}

export function stopSim() {
  if (!pose) return false
  const wasLive = live
  detach()
  pose = null
  live = false
  useRobotStore().stopSim()
  console.log(
    `%c🤖 시뮬 로봇 OFF%c  ${
      wasLive
        ? '전송을 멈췄습니다 — 이 화면은 곧바로, 다른 화면은 2초(POSE_TTL) 뒤 실 pose로 돌아갑니다'
        : '다시 실 로봇 pose만 표시합니다'
    }`,
    'font-weight:bold',
    'color:inherit',
  )
  return true
}

/** 지금 화면의 로봇이 시뮬인지 — 화면에 표식이 없으므로 이게 유일한 확인 수단이다.
 *    false    실 로봇(또는 미수신)
 *    'local'  이 탭에서 조종 중, 이 화면에만 보임
 *    'live'   이 탭에서 조종 중, 모든 대시보드에 전송 중
 *    'remote' 다른 탭·PC의 시뮬을 받아 그리는 중 (서버가 pos.sim으로 알려준다)
 *  마지막 항목 덕분에 조종하지 않는 관제 화면에서도 진짜인지 확인할 수 있다. */
export function simState() {
  if (pose) return live ? 'live' : 'local'
  return useRobotStore().telemetry?.pos?.sim ? 'remote' : false
}

/** 시뮬이 지금 있다고 믿는 위치. live 모드에서는 화면이 텔레메트리를 그리므로,
 *  전송이 막혔는지(화면은 미수신인데 pose는 움직임) 가려내는 데 쓴다. */
export function simPose() {
  return pose ? { ...pose, live } : null
}

/** 콘솔 전용 진입점 — UI에는 어떤 버튼도 두지 않는다(운영자가 실수로 켜지 않게) */
export function installSimConsole() {
  const sim = (...args) => startSim(...args)
  sim.stop = stopSim
  sim.on = simState
  sim.pose = simPose
  sim.help = () => {
    console.log(
      'lumi.sim()                      지도 한가운데에서 시작 (이 브라우저에서만)\n' +
        'lumi.sim(x, y)                  좌표 지정 (m, 활성 지도 프레임)\n' +
        'lumi.sim(x, y, deg)             방향까지 지정 (+x축 기준 반시계)\n' +
        'lumi.sim({ live: true })        POST /api/pose로 전송 — 모든 대시보드에 실시간\n' +
        'lumi.sim({ live: true, x, y })  좌표까지 지정해서 실시간\n' +
        'lumi.sim.on()                   false | "local" | "live" | "remote" (화면에는 표식이 없다)\n' +
        'lumi.sim.stop()                 끄기\n' +
        '\n↑ 전진 · ↓ 후진 · ← 좌회전 · → 우회전',
    )
  }
  window.lumi = { ...(window.lumi ?? {}), sim }
}
