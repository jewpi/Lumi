<script setup>
import { computed } from 'vue'
import { useRobotStore } from '@/stores/robot'

const robot = useRobotStore()

// 가까운 순으로 — dist가 없는 관측(거리 추정 실패)은 뒤로 민다.
const list = computed(() =>
  [...(robot.beacons ?? [])].sort((a, b) => (a.dist ?? Infinity) - (b.dist ?? Infinity)),
)

// RSSI를 막대 길이로. -90dBm 이하 0%, -50dBm 이상 100% — 실내 BLE의 통상 범위다.
const strength = (rssi) => Math.max(0, Math.min(100, ((rssi + 90) / 40) * 100))
</script>

<template>
  <section class="card beacon-card">
    <h3>
      비콘 수신 <small>(BLE)</small>
      <span class="state" :data-on="robot.beacons !== null">
        {{ robot.beacons === null ? '끊김' : '수신 중' }}
      </span>
    </h3>

    <!-- 목이 값을 만들지 않으므로 아래 두 상태가 곧 로봇 연결 상태의 답이다 -->
    <p v-if="robot.beacons === null" class="muted">
      스캔 미수신 — 로봇이 보내지 않거나 5초 이상 끊겼습니다
    </p>
    <p v-else-if="!list.length" class="muted">수신 중 — 잡히는 비콘 없음</p>

    <ul v-else class="blist">
      <li v-for="b in list" :key="b.no" :data-near="b.no === robot.nearestBeaconNo">
        <span class="no mono">B-{{ b.no }}</span>
        <b class="place">{{ b.place ?? '미등록' }}</b>
        <span class="bar"><i :style="{ width: `${strength(b.rssi)}%` }"></i></span>
        <span class="val mono">{{ b.rssi }}dBm</span>
        <span class="val mono dist">{{ b.dist == null ? '—' : `${b.dist}m` }}</span>
      </li>
    </ul>
  </section>
</template>

<style scoped>
.beacon-card h3 {
  display: flex;
  align-items: center;
  gap: 7px;
}
.state {
  margin-left: auto;
  font-size: 10.5px;
  font-weight: 600;
  padding: 1px 8px;
  border-radius: 999px;
  background: var(--neutral-tint);
  color: var(--muted);
}
.state[data-on='true'] {
  background: var(--amber-tint);
  color: var(--amber-deep);
}

.blist {
  list-style: none;
  margin: 0;
  padding: 0;
}
.blist li {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 7px 2px;
  border-bottom: 1px solid var(--line-row);
}
.blist li:last-child {
  border-bottom: 0;
}
/* 최근접 비콘 = 로봇이 있다고 판단한 존 */
.blist li[data-near='true'] {
  background: var(--amber-tint);
  margin: 0 -20px;
  padding: 7px 20px;
}
.no {
  font-size: 11px;
  color: var(--muted);
  flex: none;
}
.place {
  font-size: 13px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.bar {
  margin-left: auto;
  width: 52px;
  height: 5px;
  flex: none;
  background: var(--neutral-tint);
  border-radius: 999px;
  overflow: hidden;
}
.bar i {
  display: block;
  height: 100%;
  background: var(--amber);
}
.val {
  font-size: 11px;
  color: var(--sub);
  flex: none;
}
.dist {
  width: 44px;
  text-align: right;
}
</style>
