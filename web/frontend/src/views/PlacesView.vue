<script setup>
// SCR-03: 장소 CRUD(WEB-08) + 도면 업로드 — 관리자 전용(전체 로그인 게이트)
import { computed, onMounted, reactive, ref } from 'vue'
import { useFloorplanStore } from '@/stores/floorplan'
import {
  createPlace,
  deletePlace,
  getBeacons,
  getPlaces,
  updatePlace,
  uploadFloorplan,
} from '@/services/api'

const floorplan = useFloorplanStore()
const places = ref([])
const beacons = ref([])
const activePlan = computed(() => floorplan.active)

// ── 장소 폼 ──────────────────────────────
const editing = ref(null) // null=신규, id=수정
const form = reactive({ name: '', x: null, y: null })
const placeMsg = ref('')

// ── 도면 업로드 폼 ────────────────────────
const fileInput = ref(null)
const planName = ref('')
const pxPerM = ref(25)
const uploading = ref(false)
const uploadMsg = ref('')
const uploadErr = ref(false)

async function load() {
  ;[places.value, beacons.value] = await Promise.all([getPlaces(), getBeacons()])
  if (!floorplan.loaded) floorplan.refresh()
}
onMounted(load)

function edit(p) {
  editing.value = p.id
  Object.assign(form, { name: p.name, x: p.x, y: p.y })
}
function reset() {
  editing.value = null
  Object.assign(form, { name: '', x: null, y: null })
  placeMsg.value = ''
}

const numOrNull = (v) => (v === '' || v == null ? null : Number(v))

async function save() {
  if (!form.name.trim()) return
  const body = { name: form.name.trim(), x: numOrNull(form.x), y: numOrNull(form.y) }
  try {
    if (editing.value) await updatePlace(editing.value, body)
    else await createPlace(body)
    reset()
    await load()
  } catch (e) {
    placeMsg.value = e.response?.data?.detail ?? '저장에 실패했습니다'
  }
}

async function remove(p) {
  if (!confirm(`'${p.name}' 장소를 삭제할까요?`)) return
  try {
    await deletePlace(p.id)
    if (editing.value === p.id) reset()
    await load()
  } catch (e) {
    alert(e.response?.data?.detail ?? '삭제할 수 없습니다')
  }
}

async function doUpload() {
  const file = fileInput.value?.files?.[0]
  if (!file) {
    uploadErr.value = true
    uploadMsg.value = '업로드할 도면 파일을 선택하세요'
    return
  }
  if (!planName.value.trim()) {
    uploadErr.value = true
    uploadMsg.value = '도면 이름을 입력하세요 (예: 본관 2층)'
    return
  }
  uploading.value = true
  uploadMsg.value = ''
  uploadErr.value = false
  try {
    const fp = await uploadFloorplan(file, planName.value.trim(), Number(pxPerM.value))
    floorplan.setActive(fp) // 지도·배너에 즉시 반영
    uploadMsg.value = `'${fp.name}' 등록 완료 — ${fp.width_px}×${fp.height_px}px · 1m=${fp.px_per_m}px. 지도에 즉시 적용됩니다.`
    fileInput.value.value = ''
    planName.value = ''
  } catch (e) {
    uploadErr.value = true
    uploadMsg.value = e.response?.data?.detail ?? '업로드에 실패했습니다'
  } finally {
    uploading.value = false
  }
}
</script>

<template>
  <div class="two">
    <div class="col">
      <section class="card">
        <h3>장소 목록</h3>
        <table>
          <thead>
            <tr><th>ID</th><th>이름</th><th>x (m)</th><th>y (m)</th><th></th></tr>
          </thead>
          <tbody>
            <tr v-for="p in places" :key="p.id">
              <td class="mono">{{ p.id }}</td>
              <td>{{ p.name }}</td>
              <td class="mono">{{ p.x ?? '—' }}</td>
              <td class="mono">{{ p.y ?? '—' }}</td>
              <td class="row-actions">
                <a href="#" @click.prevent="edit(p)">수정</a>
                <a href="#" class="danger-link" @click.prevent="remove(p)">삭제</a>
              </td>
            </tr>
          </tbody>
        </table>
        <p v-if="!places.length" class="muted">등록된 장소가 없습니다</p>
      </section>

      <section class="card">
        <h3>비콘-장소 매핑</h3>
        <table>
          <thead>
            <tr><th>비콘 No</th><th>장소</th></tr>
          </thead>
          <tbody>
            <tr v-for="b in beacons" :key="b.no">
              <td class="mono">{{ b.no }}</td>
              <td>{{ b.place ?? '(미지정)' }}</td>
            </tr>
          </tbody>
        </table>
      </section>
    </div>

    <div class="col">
      <section class="card form">
        <h3>{{ editing ? '장소 수정' : '장소 등록' }}</h3>
        <label>장소명
          <input v-model="form.name" placeholder="예) 입구" />
        </label>
        <label>x 좌표 (m, 도면 좌측 하단 원점)
          <input v-model="form.x" type="number" step="0.1" min="0" placeholder="예) 34.0" />
        </label>
        <label>y 좌표 (m)
          <input v-model="form.y" type="number" step="0.1" min="0" placeholder="예) 19.0" />
        </label>
        <p v-if="placeMsg" class="err">{{ placeMsg }}</p>
        <div class="btns">
          <button @click="save">{{ editing ? '저장' : '등록' }}</button>
          <button v-if="editing" class="ghost" @click="reset">취소</button>
        </div>
      </section>

      <section class="card form">
        <h3>도면 업로드</h3>
        <p class="muted small">
          현재 도면:
          <template v-if="activePlan">
            <b>{{ activePlan.name }}</b>
            ({{ activePlan.width_px }}×{{ activePlan.height_px }}px · 1m={{ activePlan.px_per_m }}px)
          </template>
          <template v-else><b>미등록</b> — 등록 전까지 지도는 빈 상태로 표시됩니다</template>
        </p>
        <label>도면 이미지 (PNG/JPEG/WebP, 최대 10MB)
          <input ref="fileInput" type="file" accept="image/png,image/jpeg,image/webp" />
        </label>
        <label>도면 이름 — 지도 헤더에 표시됩니다
          <input v-model="planName" placeholder="예) 본관 2층" maxlength="80" />
        </label>
        <label>축척 px/m — 도면에서 1m가 몇 픽셀인지
          <input v-model="pxPerM" type="number" step="0.1" min="0.1" max="1000" />
        </label>
        <p class="muted small">
          ⚠ 새 도면의 축척·원점이 기존과 다르면 이미 등록된 장소 좌표는 새 도면 위에서
          다시 맞춰야 합니다(자동 정렬 없음). 원점은 좌측 하단 기준입니다.
        </p>
        <p v-if="uploadMsg" :class="uploadErr ? 'err' : 'ok-msg'">{{ uploadMsg }}</p>
        <div class="btns">
          <button :disabled="uploading" @click="doUpload">
            {{ uploading ? '업로드 중…' : '업로드 후 활성화' }}
          </button>
        </div>
      </section>
    </div>
  </div>
</template>

<style scoped>
.two {
  display: grid;
  grid-template-columns: 1.6fr 1fr;
  gap: 16px;
  align-items: start;
}
.col {
  display: flex;
  flex-direction: column;
  gap: 16px;
  min-width: 0;
}
.row-actions {
  white-space: nowrap;
}
.row-actions a {
  margin-right: 10px;
}
.danger-link {
  color: var(--danger);
}
.form label {
  display: flex;
  flex-direction: column;
  gap: 4px;
  font-size: 12px;
  color: var(--sub);
  margin-bottom: 10px;
}
.form input {
  font: inherit;
  padding: 7px 10px;
  border: 1px solid var(--field);
  border-radius: 6px;
}
.small {
  font-size: 12px;
  line-height: 1.5;
}
.err {
  font-size: 12px;
  color: var(--danger);
  margin: 0 0 10px;
}
.ok-msg {
  font-size: 12px;
  color: var(--ok, #3f6f2f);
  margin: 0 0 10px;
}
.btns {
  display: flex;
  gap: 8px;
}
.ghost {
  background: var(--surface);
  color: var(--ink);
  border-color: var(--field);
}
.ghost:hover {
  background: var(--paper);
  border-color: var(--ink);
}
@media (max-width: 900px) {
  .two {
    grid-template-columns: 1fr;
  }
}
</style>
