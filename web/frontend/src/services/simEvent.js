/** 콘솔 전용 이벤트·경고창 시뮬 — 시연에서 "이런 일이 있었다"를 재현한다 (S15P11C201-156).
 *
 *  로봇이 아직 이 두 채널(POST /api/events · /api/assist-requests)을 쏘지 않아, 발표 중에는
 *  기체 이벤트 피드가 비어 있고 개입 요청 팝업은 한 번도 뜨지 않는다. 관제 화면에서 제일
 *  중요한 장면 — 충돌·이동불가가 감지되면 관리자가 확인하고 출동한다 — 을 말로만 설명해야
 *  하는 상태라, 그 장면을 콘솔에서 만들어낼 수 있게 한 것이 이 파일이다.
 *
 *  시뮬 로봇(simRobot.js)과 다른 점이 하나 있다: 여기에는 local 모드가 없다.
 *  경고창의 '출동합니다 → 상황 해결'은 서버가 들고 있는 상태(assist_requests 행 + 로봇 정지
 *  잠금)를 넘기는 동작이라, 프론트에서 지어낸 요청으로는 그 버튼이 동작하지 않는다. 그래서
 *  이 파일은 실 로봇이 쓰는 바로 그 인그레스로 POST 한다 — 저장·방송·정지 잠금·해결까지
 *  전부 실제 경로를 탄다. 접속한 다른 대시보드에도 똑같이 뜨고, 기체 이벤트 페이지에도
 *  기록으로 남는다(= 발표 중 새로고침해도 사라지지 않는다).
 *
 *  화면에는 진입점을 두지 않는다 — 이유는 simRobot.js 머리말과 같다.
 */
import { API_BASE, getEvents } from '@/services/api'
import { useAssistStore } from '@/stores/assist'
import { useRobotStore } from '@/stores/robot'

import { ASSIST_REASON, EVENT_CODE, assistReasonLabel, eventLabel } from '@/labels'

const HEAD = 'font-weight:bold;color:#b45309'   // simRobot 로그와 같은 앰버
const PLAIN = 'color:inherit'

// 이벤트 한 줄이 피드에 뜬 뒤 팝업이 덮기까지의 간격. 발표자가 "여기 이벤트가 올라왔고"를
// 말할 시간은 되면서, 관객이 딴 데를 보기 전에 팝업이 뜨는 길이다.
const SCENE_GAP_MS = 2_600

/** 서버 타임스탬프와 같은 표기(UTC ISO8601 초 단위) — 피드가 시각을 그대로 파싱한다.
 *  toISOString()의 밀리초를 남기면 DB에 남는 형식만 이 채널에서 달라진다(timeutil.now_iso). */
function isoAgo(secondsAgo = 0) {
  return new Date(Date.now() - secondsAgo * 1000)
    .toISOString()
    .replace(/\.\d{3}Z$/, 'Z')
}

/** 로봇 브리지와 같은 경로로 POST 한다. api.js(axios)가 아니라 fetch를 쓰는 이유는
 *  simRobot.sendPose와 같다 — 인그레스는 관리자 토큰이 필요 없는 머신 채널이라,
 *  토큰을 붙이는 인스턴스로 보내면 실 로봇과 다른 요청이 된다. */
async function post(path, body) {
  const res = await fetch(`${API_BASE}${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  if (!res.ok) {
    const detail = await res.text().catch(() => '')
    throw new Error(`${res.status} ${res.statusText} ${detail}`.trim())
  }
  return { data: await res.json(), status: res.status }
}

/** 지금 화면이 그리고 있는 로봇 위치. 시뮬(local·live)이 켜져 있으면 그 좌표가 나온다 —
 *  팝업의 '발생 위치'가 지도 위 마커와 같은 자리를 가리켜야 시연에서 말이 된다.
 *  아무것도 없으면 null을 돌려 서버가 마지막 실 pose로 채우게 둔다(assist.raise_request). */
function herePos() {
  const pos = useRobotStore().pos
  if (pos?.x == null || pos?.y == null) return null
  return { x: pos.x, y: pos.y }
}

// ── 기체 이벤트 (피드 한 줄) ─────────────────────────────

/** 기체 이벤트 한 건을 올린다 — POST /api/events.
 *
 *  @example lumi.event('IMPACT')
 *  @example lumi.event('IMPACT', { msg: '우측 범퍼 충격' })
 *  @example lumi.event('LOW_BATTERY', { ago: 600 })   10분 전 일로 기록
 */
export async function raiseEvent(code, opts = {}) {
  if (!EVENT_CODE[code]) {
    console.warn(`[lumi.event] 모르는 코드: ${code} — ${Object.keys(EVENT_CODE).join(' / ')}`)
    return null
  }
  const body = {
    code,
    ...(opts.level && { level: opts.level }),
    ...(opts.msg && { msg: opts.msg }),
    ts: opts.ts ?? isoAgo(opts.ago ?? 0),
  }
  try {
    const { data } = await post('/api/events', body)
    if (!opts.quiet) {
      console.log(
        `%c📋 이벤트 기록%c  ${eventLabel(data.code)} · ${data.level} — ${data.msg}`,
        HEAD, PLAIN,
      )
    }
    return data
  } catch (e) {
    console.warn('[lumi.event] 전송 실패 — 백엔드를 확인하세요.', e?.message ?? e)
    return null
  }
}

// 발표 전에 채워 두는 지난 이력 — "오늘 이런 일들이 있었다"를 한 화면으로 보여주는 용도다.
// 충돌(IMPACT) → 그로 인한 비상 정지, 그리고 이동불가(구동 구속)까지 두 사건을 시간 순으로
// 깔고, 사이사이에 평범한 경고를 섞어 로그처럼 읽히게 했다.
// 오래된 것부터 나열한다 — 그래야 피드(unshift)와 이력 페이지(id desc) 양쪽에서 최신이 위로 간다.
const SEED = [
  { ago: 52 * 60, code: 'COMM_LOST', level: 'WARNING',
    msg: '관제 서버 통신 9초 두절 — 자동 재연결' },
  { ago: 41 * 60, code: 'IMPACT', level: 'CRITICAL',
    msg: '우측 범퍼 충격 — 복도에 적치된 카트와 접촉' },
  { ago: 40 * 60, code: 'EMERGENCY_STOP', level: 'CRITICAL',
    msg: '충격 직후 비상 정지 — 보행자 대기, 관리자 출동 후 적치물 이동' },
  { ago: 28 * 60, code: 'LOW_BATTERY', level: 'WARNING',
    msg: '배터리 19% — 충전 스테이션 복귀 권장' },
  { ago: 16 * 60, code: 'EMERGENCY_STOP', level: 'CRITICAL',
    msg: '구동륜 구속으로 이동 불가 — 출입문 단차에 걸림' },
  { ago: 15 * 60, code: 'IMPACT', level: 'CRITICAL',
    msg: '단차 이탈 시도 중 좌측 충격 — 관리자 현장 조치 후 보행 재개' },
]

/** 지난 이력 채워 넣기 — 발표 시작 전에 한 번 부른다.
 *
 *  이미 넣어 둔 이력이 보이면 아무것도 하지 않는다. 리허설 때마다 새로고침하며 다시
 *  부르게 되는데, 그때마다 같은 줄이 쌓이면 피드가 같은 문장으로 도배된다. */
export async function seedEvents(opts = {}) {
  if (!opts.force) {
    try {
      const recent = await getEvents({ limit: 100 })
      const seeded = new Set(SEED.map((s) => s.msg))
      if (recent.some((e) => seeded.has(e.msg))) {
        console.log(
          `%c📋 이벤트 이력 — 이미 들어가 있습니다%c  다시 넣으려면 lumi.event.seed({ force: true })`,
          HEAD, PLAIN,
        )
        return 0
      }
    } catch {
      // 조회에 실패해도(로그인 만료 등) 넣는 것 자체는 인그레스라 된다 — 중복 검사만 건너뛴다
    }
  }

  let n = 0
  for (const row of SEED) {
    // 순서대로 하나씩 — 서버가 받은 순서가 곧 이력의 순서(id)라, 병렬로 쏘면 시각과
    // 목록 순서가 어긋나 최신 줄이 중간에 끼어 보인다
    if (await raiseEvent(row.code, { ...row, quiet: true })) n += 1
  }
  console.log(
    `%c📋 이벤트 이력 ${n}건 기록%c  최근 1시간 — 충돌 2건 · 이동불가 1건 · 경고 2건\n` +
      `   피드와 [기체 이벤트] 페이지에서 확인 · CRITICAL 배너는 '확인'으로 닫으면 됩니다`,
    HEAD, PLAIN,
  )
  return n
}

// ── 관리자 개입 요청 (전체 화면 경고창) ────────────────────

/** 경고창을 띄운다 — POST /api/assist-requests.
 *  서버가 로봇을 정지로 잠그고 모든 관제 화면에 팝업을 띄운다. '상황 해결'까지 남는다.
 *
 *  @example lumi.assist()                        기본값(통행 불가)
 *  @example lumi.assist('robot_stuck')
 *  @example lumi.assist('path_blocked', { detail: '복도에 적치된 카트가 통로를 막았습니다' })
 */
export async function raiseAssist(reason = 'path_blocked', opts = {}) {
  if (!ASSIST_REASON[reason]) {
    console.warn(`[lumi.assist] 모르는 사유: ${reason} — ${Object.keys(ASSIST_REASON).join(' / ')}`)
    return null
  }
  const here = herePos()
  const body = {
    reason,
    ...(opts.detail && { detail: opts.detail }),
    ...(opts.x != null && opts.y != null
      ? { x: opts.x, y: opts.y }
      : (here ?? {})),
  }
  try {
    const { data, status } = await post('/api/assist-requests', body)
    if (status === 200) {
      console.warn(
        `[lumi.assist] 이미 열린 요청이 있어 그대로 둡니다 (#${data.id} ${assistReasonLabel(data.reason)}, ${data.status}).\n` +
          '   미해결 요청은 한 번에 하나뿐입니다 — 닫으려면 화면에서 [상황 해결] 또는 lumi.assist.clear()',
      )
      return data
    }
    console.log(
      `%c🚨 경고창 발생%c  ${assistReasonLabel(data.reason)} — ${data.detail}\n` +
        `   위치: ${data.place ? `${data.place} 부근 ` : ''}${
          data.x == null ? '(좌표 미상)' : `(${data.x.toFixed(1)}, ${data.y.toFixed(1)})`
        } · 로봇 정지 잠금\n` +
        `   화면에서 [출동합니다] → [상황 해결]  ·  콘솔로 닫기: lumi.assist.clear()`,
      HEAD, PLAIN,
    )
    return data
  } catch (e) {
    console.warn('[lumi.assist] 전송 실패 — 백엔드를 확인하세요.', e?.message ?? e)
    return null
  }
}

/** 열린 요청을 해결 처리해 초기 상태로 되돌린다 — 리허설을 다시 돌릴 때 쓴다.
 *  화면의 [상황 해결]과 같은 API라 로봇 정지 잠금도 같이 풀린다(관리자 토큰 필요). */
export async function clearAssist() {
  const assist = useAssistStore()
  if (!assist.active) await assist.refresh()
  if (!assist.active) {
    console.log('[lumi.assist] 열려 있는 개입 요청이 없습니다.')
    return false
  }
  const id = assist.active.id
  await assist.resolve()
  if (assist.error) {
    console.warn(`[lumi.assist] 해결 처리 실패 — ${assist.error}`)
    return false
  }
  console.log(`%c🚨 개입 요청 #${id} 해결%c  로봇 정지 해제`, HEAD, PLAIN)
  return true
}

// ── 시연 시나리오 ──────────────────────────────────────
// 이벤트 한 줄 → (잠시 뒤) 경고창. 실제 순서도 이렇다: 기체가 이상을 먼저 기록하고,
// 스스로 못 푼다는 판단이 서면 그때 사람을 부른다.

/** 충돌 — 복도 적치물과 부딪혀 멈춘 상황. IMPACT 기록 후 통행 불가 경고창. */
export async function playCollision() {
  console.log(
    `%c🎬 시나리오: 충돌%c  IMPACT 이벤트 → ${SCENE_GAP_MS / 1000}초 뒤 경고창(통행 불가)`,
    HEAD, PLAIN,
  )
  await raiseEvent('IMPACT', {
    level: 'CRITICAL',
    msg: '전방 충격 감지 — 복도 적치물과 접촉, 즉시 정지',
  })
  await new Promise((r) => setTimeout(r, SCENE_GAP_MS))
  return raiseAssist('path_blocked', {
    detail: '적치물과 충돌 후 정지했습니다 — 우회로가 없어 진행할 수 없습니다',
  })
}

/** 이동불가 — 단차·구속으로 로봇이 못 움직이는 상황. 비상 정지 기록 후 기동 불가 경고창. */
export async function playStuck() {
  console.log(
    `%c🎬 시나리오: 이동불가%c  EMERGENCY_STOP 이벤트 → ${SCENE_GAP_MS / 1000}초 뒤 경고창(로봇 기동 불가)`,
    HEAD, PLAIN,
  )
  await raiseEvent('EMERGENCY_STOP', {
    level: 'CRITICAL',
    msg: '구동륜 구속 — 출입문 단차에 걸려 전·후진 불가',
  })
  await new Promise((r) => setTimeout(r, SCENE_GAP_MS))
  return raiseAssist('robot_stuck', {
    detail: '단차에 걸려 스스로 빠져나오지 못합니다 — 보행자가 손잡이를 잡은 채 대기 중입니다',
  })
}

// ── 콘솔 진입점 ────────────────────────────────────────

function help() {
  console.log(
    '시연 시나리오 (이벤트 → 경고창)\n' +
      '  lumi.scene.collision()          충돌: 적치물과 충격 → 통행 불가 경고창\n' +
      '  lumi.scene.stuck()              이동불가: 단차 구속 → 기동 불가 경고창\n' +
      '\n이벤트 (피드·[기체 이벤트] 페이지)\n' +
      '  lumi.event.seed()               지난 1시간 이력 채우기 (발표 전 1회)\n' +
      '  lumi.event(code, {msg, level, ago})   한 건 직접 기록\n' +
      `  코드: ${Object.keys(EVENT_CODE).join(' / ')}\n` +
      '\n경고창 (관리자 개입 요청)\n' +
      '  lumi.assist(reason, {detail})   경고창 띄우기 (기본 path_blocked)\n' +
      '  lumi.assist.clear()             열린 요청 해결 — 리허설 초기화\n' +
      `  사유: ${Object.keys(ASSIST_REASON).join(' / ')}\n` +
      '\n로봇 위치 시뮬은 lumi.sim.help()',
  )
}

/** 콘솔 전용 진입점 — UI에는 어떤 버튼도 두지 않는다(운영자가 실수로 띄우지 않게) */
export function installEventConsole() {
  const event = (code, opts) => raiseEvent(code, opts)
  event.seed = seedEvents
  event.codes = () => Object.keys(EVENT_CODE)

  const assist = (reason, opts) => raiseAssist(reason, opts)
  assist.clear = clearAssist
  assist.reasons = () => Object.keys(ASSIST_REASON)

  const scene = {
    collision: playCollision,
    stuck: playStuck,
    help,
  }

  window.lumi = { ...(window.lumi ?? {}), event, assist, scene, help }
}
