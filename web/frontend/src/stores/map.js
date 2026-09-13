/** 활성 SLAM 맵 상태 — MapPanel(지도)·App(설정 유도 배너)이 공유.
 *
 *  도면(floorplan)과의 관계: 둘 다 있으면 맵이 이긴다. 맵은 pose와 같은 map 프레임에서
 *  나와 정합이 이미 보장돼 있고, 도면은 사람이 축척·원점을 손으로 맞춰야 하기 때문이다.
 *  맵이 없을 때만 도면으로 폴백한다(MapPanel.view 참고). */
import { defineStore } from 'pinia'

import { getActiveMap } from '@/services/api'

// 로봇이 주행하며 맵을 다시 보내면 width·height·origin이 통째로 바뀐다. mount 때 한 번만
// 받아두면 새 맵이 와도 옛 geometry로 좌표를 계산해 로봇이 엉뚱한 곳에 찍힌다 —
// 맵은 자주 바뀌지 않으므로 느슨한 주기로 폴링한다(응답은 작은 JSON).
const POLL_MS = 20_000
let timer = null

export const useMapStore = defineStore('map', {
  state: () => ({
    active: null,   // MapOut | null — 로봇이 보낸 활성 맵
    loaded: false,  // 최초 조회 완료 여부 (배너 깜빡임 방지)
  }),
  actions: {
    /** keepOnError: 폴링 중 일시적 통신 실패로 지도를 지우지 않기 위한 옵션.
     *  최초 조회에서는 false여서 '맵 없음' 상태가 정상적으로 잡힌다. */
    async refresh({ keepOnError = false } = {}) {
      try {
        const next = await getActiveMap()
        // id가 그대로면 갈아끼우지 않는다 — 같은 내용으로 교체해도 computed가 새 객체를
        // 만들어 불필요한 재렌더가 폴링 주기마다 일어난다.
        if ((next?.id ?? null) !== (this.active?.id ?? null)) this.active = next ?? null
      } catch {
        if (!keepOnError) this.active = null
      } finally {
        this.loaded = true
      }
    },
    startPolling() {
      if (timer) return
      timer = setInterval(() => this.refresh({ keepOnError: true }), POLL_MS)
    },
    stopPolling() {
      clearInterval(timer)
      timer = null
    },
    reset() {
      this.stopPolling()
      this.active = null
      this.loaded = false
    },
  },
})
