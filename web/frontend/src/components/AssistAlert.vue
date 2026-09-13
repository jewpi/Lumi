<script setup>
/** 관리자 개입 요청 알림 (WEB · S15P11C201-141).
 *
 *  로봇이 스스로 우회할 수 없는 장애물을 만나면 보행자는 손잡이를 잡은 채 그 자리에 선다.
 *  피드에 한 줄 더 쌓이는 것으로는 관리자가 놓치므로, 화면 전체를 덮어 다른 조작을 막고
 *  출동 여부부터 결정하게 한다.
 *
 *  출동 접수(ACK) 뒤에는 팝업을 상단 바로 내린다 — 관리자가 현장으로 이동하는 동안에도
 *  지도·카메라로 상황을 계속 봐야 하기 때문이다. 로봇은 해결(RESOLVE) 전까지 정지 상태다.
 */
import { computed, onUnmounted, ref, watch } from 'vue'
import { useAssistStore } from '@/stores/assist'
import { assistReasonIcon, assistReasonLabel } from '@/labels'

const assist = useAssistStore()

// ── 경과 시간 — 관리자가 얼마나 세워 뒀는지가 긴급도다 ──────────
const now = ref(Date.now())
let timer
watch(
  () => assist.active != null,
  (open) => {
    clearInterval(timer)
    if (!open) return
    now.value = Date.now()
    timer = setInterval(() => (now.value = Date.now()), 1000)
  },
  { immediate: true },
)
onUnmounted(() => clearInterval(timer))

const elapsed = computed(() => {
  const ts = assist.active?.ts
  if (!ts) return '00:00'
  const sec = Math.max(0, Math.floor((now.value - new Date(ts).getTime()) / 1000))
  const m = String(Math.floor(sec / 60)).padStart(2, '0')
  const s = String(sec % 60).padStart(2, '0')
  return `${m}:${s}`
})

// ── 표시값 ──────────────────────────────
const coords = computed(() => {
  const a = assist.active
  if (a?.x == null || a?.y == null) return null
  return `(${a.x.toFixed(1)}, ${a.y.toFixed(1)})`
})
const placeText = computed(() => {
  const a = assist.active
  if (!a) return '—'
  return a.place ? `${a.place} 부근` : (coords.value ?? '위치 미상')
})

// 팝업이 떠 있는 동안 뒤 페이지가 스크롤되지 않게 한다 (덮개가 뚫린 것처럼 보이는 것 방지)
watch(
  () => assist.showModal,
  (open) => {
    document.body.style.overflow = open ? 'hidden' : ''
  },
)
onUnmounted(() => {
  document.body.style.overflow = ''
})

// 팝업이 뜨는 즉시 기본 동작(출동)에 포커스를 준다 — 키보드만으로도 바로 접수할 수 있게
const ackBtn = ref(null)
watch(
  () => assist.showModal,
  async (open) => {
    if (!open) return
    await Promise.resolve()
    ackBtn.value?.focus()
  },
)
</script>

<template>
  <!-- 출동 접수 전 — 화면 전체를 덮는다 -->
  <div v-if="assist.showModal" class="scrim">
    <section
      class="popup"
      role="alertdialog"
      aria-modal="true"
      aria-labelledby="assist-title"
      aria-describedby="assist-detail"
    >
      <header class="head">
        <span class="ico" aria-hidden="true">{{ assistReasonIcon(assist.reason) }}</span>
        <div class="head-text">
          <b id="assist-title">관리자 개입 필요</b>
          <span class="reason">{{ assistReasonLabel(assist.reason) }}</span>
        </div>
        <span class="timer mono" :title="'발생 후 경과'">{{ elapsed }}</span>
      </header>

      <div class="body">
        <p id="assist-detail" class="detail">{{ assist.active.detail }}</p>

        <dl class="facts">
          <div>
            <dt>발생 위치</dt>
            <dd>
              {{ placeText }}
              <span v-if="assist.active.place && coords" class="mono sub">{{ coords }}</span>
            </dd>
          </div>
          <div>
            <dt>로봇</dt>
            <dd class="stop">정지 · 대기 중</dd>
          </div>
        </dl>

        <p class="guide">
          보행자가 손잡이를 잡은 채 기다리고 있습니다. 현장에서 장애물을 제거한 뒤
          <b>상황 해결</b>을 눌러야 보행이 재개됩니다.
        </p>
        <p v-if="assist.error" class="err" role="alert">{{ assist.error }}</p>
      </div>

      <!-- 선택지는 '출동' 하나뿐이다 — 화면에서 바로 닫을 수 있으면 현장에 아무도 가지 않은 채
           로봇만 다시 걷게 만들 수 있다. 해결은 출동 바에서만 누른다. -->
      <footer class="actions">
        <button ref="ackBtn" class="go" :disabled="assist.busy" @click="assist.ack()">
          출동합니다
        </button>
      </footer>
    </section>
  </div>

  <!-- 출동 접수 후 — 이동 중에도 관제 화면을 볼 수 있게 상단 바로 내린다.
       아직 해결되지 않았다는 걸 점·진행선 애니메이션으로 계속 알린다 (조용한 배너는 잊힌다) -->
  <div v-else-if="assist.enRoute" class="enroute" role="status">
    <span class="ico" aria-hidden="true">{{ assistReasonIcon(assist.reason) }}</span>
    <b>
      출동 중<span class="dots" aria-hidden="true"><i></i><i></i><i></i></span>
    </b>
    <span class="what">{{ assistReasonLabel(assist.reason) }}</span>
    <span class="who">{{ assist.active.acked_by ?? '관리자' }} · {{ placeText }}</span>
    <span class="timer mono">{{ elapsed }}</span>
    <span class="hold">로봇 정지 중 · 조치 대기</span>
    <p v-if="assist.error" class="err" role="alert">{{ assist.error }}</p>
    <button class="go" :disabled="assist.busy" @click="assist.resolve()">
      {{ assist.busy ? '처리 중…' : '상황 해결' }}
    </button>
  </div>
</template>

<style scoped>
/* ── 전체 화면 덮개 ───────────────────────── */
.scrim {
  position: fixed;
  inset: 0;
  z-index: 100; /* 헤더(z-index 5)·로봇 메뉴(20) 위 */
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 24px;
  background: rgba(23, 22, 20, 0.74);
  backdrop-filter: blur(3px);
  animation: fade 160ms ease-out;
}
@keyframes fade {
  from {
    opacity: 0;
  }
}

.popup {
  width: min(560px, 100%);
  max-height: 100%;
  overflow: auto;
  background: var(--card);
  border-radius: 14px;
  box-shadow: 0 24px 64px rgba(0, 0, 0, 0.42);
  animation: rise 200ms cubic-bezier(0.2, 0.9, 0.3, 1);
}
@keyframes rise {
  from {
    opacity: 0;
    transform: translateY(14px) scale(0.98);
  }
}

/* ── 헤더 (경고 톤) ───────────────────────── */
.head {
  display: flex;
  align-items: center;
  gap: 14px;
  padding: 18px 24px;
  background: var(--danger);
  /* 진한 빨강 위 글자는 두 테마 모두 흰색이 맞다 — --on-ink는 다크에서 어두워지므로 못 쓴다 */
  color: #fff;
  border-radius: 14px 14px 0 0;
}
.head .ico {
  font-size: 28px;
  line-height: 1;
  animation: pulse 1.4s ease-in-out infinite;
}
@keyframes pulse {
  50% {
    opacity: 0.45;
  }
}
.head-text {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
}
.head-text b {
  font-size: 19px;
  letter-spacing: -0.01em;
}
.reason {
  font-size: 12.5px;
  opacity: 0.85;
}
.timer {
  margin-left: auto;
  font-size: 20px;
  font-weight: 700;
  font-variant-numeric: tabular-nums;
}

/* ── 본문 ────────────────────────────────── */
.body {
  padding: 20px 24px 4px;
}
.detail {
  margin: 0 0 16px;
  font-size: 15.5px;
  font-weight: 600;
  line-height: 1.5;
}
.facts {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
  gap: 12px;
  margin: 0 0 16px;
  padding: 14px 16px;
  background: var(--paper);
  border: 1px solid var(--line);
  border-radius: 9px;
}
.facts div {
  display: flex;
  flex-direction: column;
  gap: 3px;
  min-width: 0;
}
.facts dt {
  font-size: 11px;
  color: var(--muted);
}
.facts dd {
  margin: 0;
  font-size: 14px;
  font-weight: 600;
}
.facts .sub {
  display: block;
  font-size: 11.5px;
  font-weight: 400;
  color: var(--muted);
}
.facts .stop {
  color: var(--danger-text);
}
.guide {
  margin: 0;
  padding: 11px 14px;
  background: var(--amber-tint);
  border: 1px solid var(--amber-tint-line);
  border-radius: 8px;
  font-size: 12.5px;
  line-height: 1.6;
  color: var(--amber-deep);
}
.err {
  margin: 10px 0 0;
  font-size: 12.5px;
  color: var(--danger-text);
}

/* ── 동작 ────────────────────────────────── */
.actions {
  display: flex;
  gap: 10px;
  padding: 18px 24px 22px;
}
.actions button {
  flex: 1;
  padding: 12px 16px;
  font-size: 14px;
  font-weight: 700;
  border-radius: 9px;
}
.go {
  background: var(--danger);
  border-color: var(--danger);
  color: #fff;
}
.go:hover:not(:disabled) {
  background: var(--danger-strong);
}
.go:focus-visible {
  outline: 3px solid var(--amber);
  outline-offset: 2px;
}
/* ── 출동 중 바 ───────────────────────────── */
.enroute {
  position: relative;
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
  padding: 9px 20px;
  background: var(--danger-tint);
  border-bottom: 1px solid var(--danger-line);
  color: var(--danger-text);
  font-size: 13px;
}
/* 미해결 상태를 알리는 은은한 점멸 — 멈춰 있는 배너는 배경으로 묻힌다.
   아래쪽(경계선)에서 차오르는 그라데이션이라 위쪽 글자 대비는 그대로 유지된다. */
.enroute::after {
  content: '';
  position: absolute;
  inset: 0;
  background: linear-gradient(to top, var(--danger) 0%, transparent 45%);
  opacity: 0;
  pointer-events: none;
  animation: throb 1.9s ease-in-out infinite;
}
@keyframes throb {
  50% {
    opacity: 0.16;
  }
}
/* 내용은 그라데이션 위로 — ::after가 절대배치라 그냥 두면 글자를 덮는다 */
.enroute > * {
  position: relative;
  z-index: 1;
}

/* 로딩 점 — "아직 진행 중"을 문장이 아니라 움직임으로 알린다 */
.dots {
  display: inline-flex;
  align-items: flex-end;
  gap: 2.5px;
  margin-left: 4px;
  padding-bottom: 2px;
}
.dots i {
  width: 3.5px;
  height: 3.5px;
  border-radius: 50%;
  background: currentColor;
  animation: blink 1.3s ease-in-out infinite;
}
.dots i:nth-child(2) {
  animation-delay: 0.18s;
}
.dots i:nth-child(3) {
  animation-delay: 0.36s;
}
@keyframes blink {
  0%,
  65%,
  100% {
    opacity: 0.25;
    transform: translateY(0);
  }
  30% {
    opacity: 1;
    transform: translateY(-2.5px);
  }
}

.enroute .what {
  font-weight: 600;
}
.enroute .who {
  color: var(--sub);
  font-size: 12px;
}
.enroute .hold {
  font-weight: 700;
  font-size: 12px;
  color: var(--danger-text);
}
.enroute .timer {
  font-size: 13px;
  margin-left: 0;
  color: var(--danger-text);
}
.enroute .err {
  margin: 0;
  font-size: 12px;
}
.enroute .go {
  margin-left: auto;
  padding: 6px 14px;
  font-size: 12px;
  font-weight: 700;
  border-radius: 999px;
}

/* 움직임에 민감한 사용자 — 경고는 색·문구로 남기고 애니메이션만 끈다 */
@media (prefers-reduced-motion: reduce) {
  .scrim,
  .popup,
  .head .ico,
  .enroute::after,
  .dots i {
    animation: none;
  }
  /* 점멸만 끄고 붉은 그라데이션 자체는 남긴다 — 경고 신호가 사라지면 안 된다 */
  .enroute::after {
    opacity: 0.12;
  }
}
</style>
