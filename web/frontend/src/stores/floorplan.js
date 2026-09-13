/** 활성 도면 상태 — MapPanel(지도)·App(설정 유도 배너)·PlacesView(업로드)가 공유.
 *  기본 도면 폴백은 없다: active가 null이면 지도는 빈 상태 + 배너로 등록을 유도한다. */
import { defineStore } from 'pinia'

import { getActiveFloorplan } from '@/services/api'

export const useFloorplanStore = defineStore('floorplan', {
  state: () => ({
    active: null,   // Floorplan | null — 등록된 활성 도면
    loaded: false,  // 최초 조회 완료 여부 (배너 깜빡임 방지)
  }),
  actions: {
    async refresh() {
      try {
        this.active = await getActiveFloorplan()
      } catch {
        this.active = null
      } finally {
        this.loaded = true
      }
    },
    /** 업로드 직후 응답으로 바로 반영 (재조회 없이) */
    setActive(fp) {
      this.active = fp
      this.loaded = true
    },
    reset() {
      this.active = null
      this.loaded = false
    },
  },
})
