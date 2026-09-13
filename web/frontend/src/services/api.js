/** REST API 클라이언트 (Axios) — 명세서 6.2 + 안내견 ERD + 관리자 인증(JWT Bearer) */
import axios from 'axios'

import { clearToken, getToken } from './token'

// dev: 백엔드 직결(:8000, CORS) · prod: ""(same-origin, nginx가 /api 프록시)
export const API_BASE = import.meta.env.VITE_API_BASE ?? 'http://localhost:8000'

const api = axios.create({ baseURL: API_BASE })

// 모든 요청에 관리자 토큰 부착 — 이 인스턴스 하나만 쓰므로 이 지점이 유일한 부착점
api.interceptors.request.use((config) => {
  const t = getToken()
  if (t) config.headers.Authorization = `Bearer ${t}`
  return config
})

// 401 → 세션 만료 처리. 로그인 요청 자체는 제외해 LoginView가 실패 메시지를 표시하게 한다.
api.interceptors.response.use(
  (r) => r,
  (err) => {
    const url = err.config?.url ?? ''
    if (err.response?.status === 401 && url !== '/api/auth/login') {
      clearToken()
      window.dispatchEvent(new CustomEvent('auth:expired')) // main.js가 로그아웃+이동 처리
    }
    return Promise.reject(err)
  },
)

// 인증 — OAuth2PasswordRequestForm은 form-urlencoded(username/password 필드)를 요구한다
export const login = (username, password) =>
  api.post('/api/auth/login', new URLSearchParams({ username, password })).then((r) => r.data)
export const getMe = () => api.get('/api/auth/me').then((r) => r.data)

// 관리자 계정 관리 (ADMINS)
export const getAdmins = () => api.get('/api/admins').then((r) => r.data)
export const createAdmin = (body) => api.post('/api/admins', body).then((r) => r.data)
export const deleteAdmin = (id) => api.delete(`/api/admins/${id}`)

// 도면 (FLOORPLANS)
export const getActiveFloorplan = () => api.get('/api/floorplans/active').then((r) => r.data)
export const uploadFloorplan = (file, name, pxPerM) => {
  const fd = new FormData()
  fd.append('file', file)
  fd.append('name', name)
  fd.append('px_per_m', pxPerM)
  return api.post('/api/floorplans', fd).then((r) => r.data)
}

// SLAM 맵 (MAPS) — 로봇이 보낸 occupancy grid. 도면과 달리 pose와 같은 map 프레임이라
// 좌표를 맞출 필요가 없다. 활성 맵이 없으면 null.
export const getActiveMap = () => api.get('/api/map').then((r) => r.data)

// 장소
export const getPlaces = () => api.get('/api/places').then((r) => r.data)
export const createPlace = (body) => api.post('/api/places', body).then((r) => r.data)
export const updatePlace = (id, body) => api.put(`/api/places/${id}`, body).then((r) => r.data)
export const deletePlace = (id) => api.delete(`/api/places/${id}`)

// 비콘
export const getBeacons = () => api.get('/api/beacons').then((r) => r.data)

// 세션은 화면에서 조회하지 않는다 — 진행 중 세션은 telemetry.session으로 매 틱 실려 오고,
// 이력 화면은 없앴다. 서버에는 조회 API가 남아 있어 필요하면 Swagger로 확인한다.

// 관리자 개입 요청 (ASSIST_REQUESTS) — 로봇이 스스로 못 푸는 상황. 전체 화면 팝업의 원본.
// 생성은 로봇·AI 인그레스(POST /api/assist-requests)라 대시보드에는 조회·처리만 있다.
export const getActiveAssistRequest = () =>
  api.get('/api/assist-requests/active').then((r) => r.data)
export const ackAssistRequest = (id) =>
  api.post(`/api/assist-requests/${id}/ack`).then((r) => r.data)
export const resolveAssistRequest = (id) =>
  api.post(`/api/assist-requests/${id}/resolve`).then((r) => r.data)

// 기체 이벤트 이력 — 생성은 로봇 인그레스(POST /api/events)라 대시보드에는 조회만 있다
export const getEvents = (params) => api.get('/api/events', { params }).then((r) => r.data)
