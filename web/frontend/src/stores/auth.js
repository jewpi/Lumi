/** 관리자 인증 상태 — 토큰은 localStorage(services/token.js), 사용자 정보는 /api/auth/me */
import { defineStore } from 'pinia'

import { getMe, login as apiLogin } from '@/services/api'
import { clearToken, getToken, setToken } from '@/services/token'
import { startRobotSocket, stopRobotSocket } from '@/services/ws'

export const useAuthStore = defineStore('auth', {
  state: () => ({
    token: getToken(),   // 새로고침 시 localStorage에서 복원
    user: null,          // { id, username } — fetchMe()로 채움
  }),
  getters: {
    isAuthed: (s) => !!s.token,
  },
  actions: {
    async login(username, password) {
      const { access_token } = await apiLogin(username, password)
      setToken(access_token)
      this.token = access_token
      this.user = await getMe()
      startRobotSocket()   // 로그인 후에만 텔레메트리 수신 시작
    },

    /** 새로고침 시 사용자 복원. 만료 토큰이면 인터셉터가 auth:expired를 발행한다. */
    async fetchMe() {
      try {
        this.user = await getMe()
        return true
      } catch {
        return false
      }
    },

    logout() {
      clearToken()
      this.token = null
      this.user = null
      stopRobotSocket()
    },
  },
})
