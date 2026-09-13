import { defineStore } from 'pinia'

import {
  ackAssistRequest,
  getActiveAssistRequest,
  resolveAssistRequest,
} from '@/services/api'

/** 관리자 개입 요청 — 로봇이 스스로 못 푸는 상황(치워야 하는 장애물 등) 단일 저장소.
 *
 *  기체 이벤트(robot.events)가 지나간 로그라면 이쪽은 지금 사람이 움직여야 하는
 *  건이라 피드가 아니라 전체 화면 팝업으로 뜬다. 서버가 미해결 요청을 한 번에 하나만
 *  두므로 여기도 배열이 아니라 단일 슬롯이다.
 *
 *  WS(assist_request)로 갱신되지만 그것만으로는 새로고침 때 사라진다 — 로봇은 여전히
 *  멈춰 있는데 화면만 멀쩡해 보이므로 진입 시 refresh()로 복원한다. */
export const useAssistStore = defineStore('assist', {
  state: () => ({
    active: null,   // {id, reason, detail, x, y, place, status, ts, acked_by, resolved_by,...}
    busy: false,
    error: '',
  }),
  getters: {
    // 아직 아무도 안 맡은 건만 화면을 덮는다. 출동 접수 뒤에는 상단 바로 내려가
    // 관리자가 이동하면서도 관제 화면을 볼 수 있게 한다.
    showModal: (s) => s.active?.status === 'OPEN',
    enRoute: (s) => s.active?.status === 'ACK',
    reason: (s) => s.active?.reason ?? null,
  },
  actions: {
    apply(msg) {
      // 이미 닫힌 예전 건의 방송이 뒤늦게 도착해도 지금 열린 요청을 지우지 않게 한다
      if (this.active && msg.id !== this.active.id && msg.status === 'RESOLVED') return
      this.active = msg.status === 'RESOLVED' ? null : msg
      this.error = ''
    },
    async refresh() {
      try {
        this.active = await getActiveAssistRequest()
      } catch {
        // 401은 api.js가 재로그인으로 유도한다. 그 밖의 실패는 다음 WS 방송으로 회복된다.
      }
    },
    reset() {
      this.active = null
      this.busy = false
      this.error = ''
    },
    ack() {
      return this._advance(ackAssistRequest)
    },
    resolve() {
      return this._advance(resolveAssistRequest)
    },
    async _advance(call) {
      if (!this.active || this.busy) return
      this.busy = true
      this.error = ''
      try {
        this.apply(await call(this.active.id))
      } catch (e) {
        // 409 = 다른 관제 화면이 먼저 처리했다 — 에러를 띄우는 대신 서버 상태로 맞춘다
        if (e?.response?.status === 409) await this.refresh()
        else this.error = e?.response?.data?.detail ?? '처리에 실패했습니다. 다시 시도해 주세요.'
      } finally {
        this.busy = false
      }
    },
  },
})
