import './assets/main.css'

import { createApp } from 'vue'
import { createPinia } from 'pinia'

import App from './App.vue'
import router from './router'
import { installEventConsole } from './services/simEvent'
import { installSimConsole } from './services/simRobot'
import { startRobotSocket } from './services/ws'
import { useAuthStore } from './stores/auth'

const app = createApp(App)

const pinia = createPinia()
app.use(pinia)
app.use(router)

const auth = useAuthStore(pinia)

// REST 401 / WS 1008(토큰 만료·무효) → 강제 로그아웃 후 로그인 화면으로.
// 리스너를 여기(main)에 두어 api.js/ws.js ↔ 라우터 간 순환 import를 피한다.
window.addEventListener('auth:expired', () => {
  auth.logout()
  if (router.currentRoute.value.name !== 'login') router.push({ name: 'login' })
})

app.mount('#app')

// 콘솔 전용 시뮬 로봇(lumi.sim). 켜기 전에는 아무 동작도 하지 않는다 —
// 화면에 진입점을 두지 않는 이유는 services/simRobot.js 머리말 참고.
installSimConsole()
// 시연용 이벤트·경고창(lumi.event · lumi.assist · lumi.scene). 부를 때만 실 인그레스로 나간다.
installEventConsole()

if (auth.isAuthed) {
  auth.fetchMe()      // 새로고침 시 사용자 복원 (만료면 401 → auth:expired가 정리)
  startRobotSocket()  // 텔레메트리 수신 — 로그인 상태에서만 (pinia 설치 이후 호출)
}
