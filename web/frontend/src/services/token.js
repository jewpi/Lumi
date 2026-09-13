/** JWT 보관 (localStorage) — api.js / ws.js / 스토어 / 라우터가 순환 import 없이 공유.
 *  XSS에 노출되는 저장소이므로 화면에 admin 입력을 v-html로 뿌리지 않는다(Vue 기본 이스케이프 유지). */
const KEY = 'lumi_token'

export const getToken = () => localStorage.getItem(KEY)
export const setToken = (t) => localStorage.setItem(KEY, t)
export const clearToken = () => localStorage.removeItem(KEY)
