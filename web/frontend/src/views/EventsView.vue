<script setup>
import { onMounted, ref } from 'vue'
import { getEvents } from '@/services/api'

const level = ref('')
const events = ref([])
const loading = ref(false)

async function load() {
  loading.value = true
  try {
    events.value = await getEvents({ limit: 100, ...(level.value && { level: level.value }) })
  } finally {
    loading.value = false
  }
}

onMounted(load)
</script>

<template>
  <!-- 기체 이상 이벤트 (IMPACT/FALL/EMERGENCY_STOP/LOW_BATTERY/COMM_LOST) — 정상 보행 개입은 세션 이력에서 -->
  <section class="card">
    <div class="row">
      <h3>기체 이벤트</h3>
      <select v-model="level" @change="load">
        <option value="">전체 레벨</option>
        <option>INFO</option>
        <option>WARNING</option>
        <option>CRITICAL</option>
      </select>
      <button :disabled="loading" @click="load">새로고침</button>
    </div>

    <table>
      <thead>
        <tr><th>시각</th><th>레벨</th><th>코드</th><th>메시지</th><th>세션</th></tr>
      </thead>
      <tbody>
        <tr v-for="e in events" :key="e.id">
          <td class="mono">{{ e.ts }}</td>
          <td><span class="badge" :data-level="e.level">{{ e.level }}</span></td>
          <td>{{ e.code }}</td>
          <td>{{ e.msg }}</td>
          <td class="mono">{{ e.session_id ?? '—' }}</td>
        </tr>
      </tbody>
    </table>
    <p v-if="!events.length" class="muted">기록된 기체 이벤트가 없습니다</p>
  </section>
</template>
