<script setup>
/** 기체 이벤트 피드 — 로봇이 POST /api/events로 올린 것만 쌓인다.
 *  서버가 만들어내는 이벤트는 없으므로, 비어 있다 = 로봇이 아직 아무것도 안 보냈다. */
import { useRobotStore } from '@/stores/robot'
import { eventIcon, eventLabel } from '@/labels'

const robot = useRobotStore()

function hhmmss(ts) {
  return new Date(ts).toLocaleTimeString('ko-KR', { hour12: false })
}
</script>

<template>
  <section class="card feed-card">
    <h3>기체 이벤트 <small>(충격·낙하·배터리·통신)</small></h3>
    <p v-if="!robot.events.length" class="muted">
      아직 수신된 이벤트 없음 — 로봇이 이상을 감지하면 여기에 실시간으로 쌓입니다.
    </p>
    <ul v-else class="feed">
      <li v-for="e in robot.events" :key="e.id ?? e.ts" :data-level="e.level">
        <div class="row1">
          <span class="ico">{{ eventIcon(e.code) }}</span>
          <b>{{ eventLabel(e.code) }}</b>
          <span class="lv" :data-level="e.level">{{ e.level }}</span>
          <span class="ts mono">{{ hhmmss(e.ts) }}</span>
        </div>
        <div class="detail">{{ e.msg }}</div>
      </li>
    </ul>
  </section>
</template>

<style scoped>
.feed-card {
  display: flex;
  flex-direction: column;
  min-height: 0;
}
.feed {
  list-style: none;
  margin: 0;
  padding: 0;
  overflow: auto;
  max-height: 340px;
}
.feed li {
  padding: 9px 2px;
  border-bottom: 1px solid var(--line-row);
}
/* CRITICAL은 줄 전체를 물들여 스크롤 중에도 눈에 걸리게 한다 */
.feed li[data-level='CRITICAL'] {
  background: var(--danger-row);
  margin: 0 -20px;
  padding: 9px 20px;
}
.row1 {
  display: flex;
  align-items: center;
  gap: 7px;
}
.ico {
  font-size: 14px;
}
.lv {
  font-size: 10.5px;
  padding: 1px 7px;
  border-radius: 999px;
  background: var(--neutral-tint);
  color: var(--sub);
  font-weight: 600;
}
.lv[data-level='CRITICAL'] {
  background: var(--danger-tint);
  color: var(--danger-text);
}
.lv[data-level='WARNING'] {
  background: var(--amber-tint);
  color: var(--amber-deep);
}
.ts {
  margin-left: auto;
  font-size: 11px;
  color: var(--muted);
}
.detail {
  font-size: 12.5px;
  color: var(--sub);
  margin-top: 3px;
}
</style>
