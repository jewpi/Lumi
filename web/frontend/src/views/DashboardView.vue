<script setup>
/** 관제 대시보드 — 보는 화면이지 조작 화면이 아니다.
 *
 *  세션 개시·종료 버튼은 두지 않는다: 동행은 보행자가 손잡이를 잡을 때 시작되고 놓을 때
 *  끝나므로, 그 신호를 보내는 쪽은 로봇(POST /api/sessions, source=voice)이다. 관제사가
 *  원격으로 남의 동행을 열고 닫으면 실제 손잡이 상태와 화면이 어긋난다.
 *
 *  구성은 2컬럼(40:60)이다. 왼쪽은 로봇이 지금 무엇을 보고 듣는지(카메라·비콘), 오른쪽은
 *  그 결과 로봇이 어디에 있고 무슨 일이 있었는지(지도·기체 이벤트). 로봇 상태 요약은
 *  헤더 배지(배터리·연결·상태)가 이미 상시 표시하므로 본문에서 반복하지 않는다. */
import BeaconPanel from '@/components/BeaconPanel.vue'
import MapPanel from '@/components/MapPanel.vue'
import EventFeed from '@/components/EventFeed.vue'
import CameraPanel from '@/components/CameraPanel.vue'
import { useRobotStore } from '@/stores/robot'

const robot = useRobotStore()
</script>

<template>
  <section v-if="!robot.telemetry" class="card muted">텔레메트리 수신 대기 중…</section>

  <div v-else class="dash2">
    <!-- 좌(40%): 로봇이 지금 감지하는 것 -->
    <div class="col">
      <CameraPanel />
      <BeaconPanel />
    </div>

    <!-- 우(60%): 위치와 이력 -->
    <div class="col">
      <MapPanel />
      <EventFeed />
    </div>
  </div>
</template>

<style scoped>
/* minmax(0, …)로 잡아야 지도 SVG·이벤트 긴 문구가 트랙을 밀어내지 않고 40:60이 유지된다 */
.dash2 {
  display: grid;
  grid-template-columns: minmax(0, 40fr) minmax(0, 60fr);
  gap: 16px;
  align-items: start;
}
.col {
  display: flex;
  flex-direction: column;
  gap: 16px;
  min-width: 0;
}
/* 1200px은 상단바가 햄버거로 바뀌는 지점과 같다 (App.vue) — 좁은 화면 기준은 하나만 둔다 */
@media (max-width: 1200px) {
  .dash2 {
    grid-template-columns: 1fr;
  }
}
@media (max-width: 720px) {
  .dash2,
  .col {
    gap: 12px;
  }
}
</style>
