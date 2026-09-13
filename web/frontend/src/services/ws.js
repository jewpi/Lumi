/** 표준 WebSocket 클라이언트 + 지수 백오프 자동 재연결 (WEB-06)
 *  재연결 간격: 1s → 2s → 4s → 8s → 최대 10s. 연결 성공 시 초기화.
 *
 *  인증: new WebSocket(url, ["bearer", <JWT>]) — 토큰이 Sec-WebSocket-Protocol 헤더로
 *  전달되어 URL/액세스 로그에 남지 않는다. 서버가 1008로 닫으면(토큰 만료·무효)
 *  재접속 루프 대신 auth:expired를 발행해 재로그인으로 유도한다. */
import { useAssistStore } from '@/stores/assist'
import { useRobotStore } from '@/stores/robot'

import { getToken } from './token'

const WS_URL = import.meta.env.VITE_WS_URL ?? 'ws://localhost:8000/ws'
const BASE_DELAY = 1_000
const MAX_DELAY = 10_000

let ws = null
let retries = 0
let timer = null
let stopped = false

export function startRobotSocket() {
  stopped = false
  retries = 0
  connect()
}

export function stopRobotSocket() {
  stopped = true
  clearTimeout(timer)
  ws?.close()
  ws = null
}

function connect() {
  const robot = useRobotStore()
  const assist = useAssistStore()
  const token = getToken()   // 재연결마다 최신 토큰을 다시 읽는다
  if (!token) return         // 미로그인 — 로그인 성공 시 startRobotSocket()이 다시 호출된다

  ws = new WebSocket(WS_URL, ['bearer', token])

  ws.onopen = () => {
    retries = 0
    robot.setConnected(true)
    // 끊겨 있는 동안 열리거나 닫힌 개입 요청을 따라잡는다 — 방송은 재전송되지 않는다
    assist.refresh()
  }

  ws.onmessage = (e) => {
    const msg = JSON.parse(e.data)
    if (msg.type === 'telemetry') robot.applyTelemetry(msg)
    else if (msg.type === 'lidar') robot.applyLidar(msg)
    else if (msg.type === 'event') robot.applyEvent(msg)
    else if (msg.type === 'assist_request') assist.apply(msg)
  }

  ws.onclose = (e) => {
    robot.setConnected(false)
    if (e.code === 1008) {   // 인증 실패/만료 — 재접속해도 소용없다
      window.dispatchEvent(new CustomEvent('auth:expired'))
      return
    }
    if (!stopped) scheduleReconnect()
  }
}

function scheduleReconnect() {
  const delay = Math.min(BASE_DELAY * 2 ** retries, MAX_DELAY)
  retries += 1
  clearTimeout(timer)
  timer = setTimeout(connect, delay)
}
