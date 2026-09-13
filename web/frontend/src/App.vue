<script setup>
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import AssistAlert from '@/components/AssistAlert.vue'
import { useRobotStore } from '@/stores/robot'
import { useAssistStore } from '@/stores/assist'
import { useAuthStore } from '@/stores/auth'
import { useFloorplanStore } from '@/stores/floorplan'
import { useMapStore } from '@/stores/map'
import { useThemeStore } from '@/stores/theme'
import { LIVE_STATUS } from '@/labels'
import logoSvg from '@/assets/logo.svg?raw'

const robot = useRobotStore()
const assist = useAssistStore()
const auth = useAuthStore()
const floorplan = useFloorplanStore()
const mapStore = useMapStore()
const theme = useThemeStore()
const route = useRoute()
const router = useRouter()

// 로그인 화면에서는 관제 크롬(헤더·경고 배너)을 숨긴다
const onLoginPage = computed(() => route.name === 'login')

// 첫 설정 유도 — 로그인 상태 && 표시할 지도가 하나도 없을 때만 안내한다.
// 로봇이 SLAM 맵을 보냈으면 도면은 없어도 관제가 되므로 배너를 띄우지 않는다.
watch(
  () => auth.isAuthed,
  (authed) => {
    if (authed) {
      floorplan.refresh()
      mapStore.refresh()
      // 미해결 개입 요청 복원 — WS 방송은 재전송되지 않아 새로고침하면 팝업만 사라진다
      assist.refresh()
    } else {
      floorplan.reset()
      mapStore.reset()
      assist.reset()
    }
  },
  { immediate: true },
)
const showSetupBanner = computed(
  () =>
    auth.isAuthed &&
    floorplan.loaded &&
    mapStore.loaded &&
    !floorplan.active &&
    !mapStore.active &&
    !onLoginPage.value &&
    route.name !== 'places', // 등록 페이지에서는 배너 대신 폼이 보이므로 생략
)

function logout() {
  auth.logout()
  router.push({ name: 'login' })
}

// ── 모바일 메뉴 ──────────────────────────────
// 좁은 화면에서는 탭 4개와 계정 정보가 상단바에 다 들어가지 않는다. 줄여서 우겨넣는 대신
// 슬라이드 다운 패널로 내리고, 상단바에는 브랜드와 기체 정보만 남긴다 — 관제 화면에서
// 항상 보여야 하는 건 로봇이 어떤 상태인지지 어느 메뉴가 있는지가 아니다.
const menuOpen = ref(false)

// 메뉴로 이동하면 닫는다 — 열린 채로 남으면 이동한 화면 위를 패널이 덮는다
watch(() => route.fullPath, () => (menuOpen.value = false))

function onKeydown(e) {
  if (e.key === 'Escape') menuOpen.value = false
}

// ── 시계 ──────────────────────────────
const time = ref('--:--:--')
let timer
onMounted(() => {
  const z = (n) => String(n).padStart(2, '0')
  const tick = () => {
    const d = new Date()
    time.value = `${z(d.getHours())}:${z(d.getMinutes())}:${z(d.getSeconds())}`
  }
  tick()
  timer = setInterval(tick, 1000)
  window.addEventListener('keydown', onKeydown)
})
onUnmounted(() => {
  clearInterval(timer)
  window.removeEventListener('keydown', onKeydown)
})

// ── 로봇 상태 ──────────────────────────────
const status = computed(() => LIVE_STATUS[robot.liveStatus] ?? { label: '—', tone: 'muted' })
const statusLabel = computed(() => status.value.label)
const statusTone = computed(() => status.value.tone)

// ── 배터리 ──────────────────────────────
const batteryPct = computed(() =>
  robot.battery == null ? null : Math.max(0, Math.min(100, Math.round(robot.battery))),
)
const batteryLow = computed(() => batteryPct.value != null && batteryPct.value <= 20)

// 로봇은 1대다(백엔드 robots도 1행) — 고를 게 없으므로 선택 드롭다운을 두지 않는다.
// 있지도 않은 기체를 목록에 세워 두면 시연 중 "저건 뭐냐"는 질문만 남는다.
const ROBOT_ID = 'LUMI-01'
</script>

<template>
  <header v-if="!onLoginPage" class="topbar" :class="{ 'menu-open': menuOpen }">
    <div class="brand">
      <span class="logo" role="img" aria-label="Lumi 로고" v-html="logoSvg"></span>
      <span class="wordmark">Lumi</span>
      <span class="tag">CONTROL</span>
    </div>

    <!-- 모바일 전용 토글 (데스크톱에서는 숨김) -->
    <button
      class="hamburger"
      type="button"
      aria-controls="topbar-menu"
      :aria-expanded="menuOpen"
      :aria-label="menuOpen ? '메뉴 닫기' : '메뉴 열기'"
      @click="menuOpen = !menuOpen"
    >
      <i></i><i></i><i></i>
    </button>

    <div class="spacer"></div>

    <span class="clock mono">{{ time }}</span>
    <span class="divider"></span>

    <!-- 기체 정보 — 기체명·배터리·연결·위치. 좁은 화면에서도 접지 않고 둘째 줄에 항상
         남긴다(메뉴 안에 숨기면 로봇이 끊긴 걸 메뉴를 열어야 알게 된다).
         데스크톱에서는 display:contents로 상단바 flex에 그대로 풀린다. -->
    <div class="machine">
      <!-- 로봇 (단일 기체) -->
      <span class="robot-id">
        <i class="dot" :class="statusTone"></i>
        <span class="rid">{{ ROBOT_ID }}</span>
      </span>

      <!-- 배터리 -->
      <span class="pill batt">
        <template v-if="batteryPct != null">
          <span class="batt-shell">
            <i
              class="batt-fill"
              :style="{ width: batteryPct + '%', background: batteryLow ? 'var(--danger)' : 'var(--amber)' }"
            ></i>
          </span>
          <b>{{ batteryPct }}%</b>
        </template>
        <b v-else>—</b>
      </span>

      <!-- 통신/연결 -->
      <span class="pill comms" :class="{ off: !robot.connected }">
        <span class="bars" v-if="robot.connected">
          <i style="height: 5px"></i><i style="height: 8px"></i><i style="height: 11px"></i
          ><i style="height: 14px; background: var(--field)"></i>
        </span>
        <i v-else class="dot danger"></i>
        {{ robot.connected ? '연결됨' : '연결 끊김' }}
      </span>

      <!-- 로봇 상태(위치) -->
      <span class="pill mode-pill" :class="statusTone">
        <i class="dot" :class="statusTone"></i>{{ statusLabel }}
      </span>
    </div>

    <!-- 내비 + 계정 — 모바일에서는 이 래퍼가 슬라이드 다운 패널이 되고,
         데스크톱에서는 display:contents로 풀려 예전과 같은 한 줄이 된다 -->
    <div id="topbar-menu" class="menu">
      <nav class="tabs">
        <RouterLink to="/">대시보드</RouterLink>
        <RouterLink to="/places">장소·비콘</RouterLink>
        <RouterLink to="/events">기체 이벤트</RouterLink>
        <RouterLink to="/admins">관리자</RouterLink>
      </nav>

      <!-- 관리자 -->
      <span class="user">
        <span class="avatar">{{ (auth.user?.username ?? '?').slice(0, 1).toUpperCase() }}</span>
        {{ auth.user?.username ?? '—' }}

        <!-- 테마 — 지금 상태가 아니라 '누르면 가는 곳'을 그린다(다크면 해, 라이트면 달) -->
        <button
          class="theme-btn"
          type="button"
          :title="theme.isDark ? '라이트 모드로' : '다크 모드로'"
          :aria-label="theme.isDark ? '라이트 모드로 전환' : '다크 모드로 전환'"
          @click="theme.toggle()"
        >
          <svg
            v-if="theme.isDark"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            stroke-width="2"
            stroke-linecap="round"
            aria-hidden="true"
          >
            <circle cx="12" cy="12" r="4" />
            <path
              d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"
            />
          </svg>
          <svg v-else viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
            <path d="M20.5 14.8A8.6 8.6 0 0 1 9.2 3.5a8.6 8.6 0 1 0 11.3 11.3Z" />
          </svg>
        </button>

        <button class="logout-btn" title="로그아웃" @click="logout">로그아웃</button>
      </span>
    </div>
  </header>

  <!-- 관리자 개입 요청 — 사람이 현장에 가야 풀리는 상황. 전체 화면 팝업(미접수) / 상단 바(출동 중) -->
  <AssistAlert v-if="!onLoginPage" />

  <!-- 기체 CRITICAL 이벤트 비상 경고 (WEB-05) — 보행 개입과 별개 -->
  <div v-if="robot.alert && !onLoginPage" class="alert">
    <strong>⚠ {{ robot.alert.code }}</strong>
    <span>{{ robot.alert.msg }} · {{ robot.alert.ts }}</span>
    <button @click="robot.dismissAlert()">확인</button>
  </div>

  <!-- 첫 설정 유도 — 표시할 지도가 없을 때만 (로봇 SLAM 맵도, 업로드 도면도 없음) -->
  <div v-if="showSetupBanner" class="setup-banner">
    <strong>표시할 지도가 없습니다.</strong>
    <span>로봇이 SLAM 맵을 전송하면 자동으로 활성화됩니다. 연동 전이라면 기관 도면을 업로드해 임시로 사용할 수 있습니다.</span>
    <RouterLink class="setup-cta" to="/places">도면 등록하기</RouterLink>
  </div>

  <main>
    <RouterView />
  </main>
</template>

<style scoped>
.topbar {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px 12px;
  padding: 0 20px;
  min-height: 56px;
  background: var(--card);
  border-bottom: 1px solid var(--line);
  position: relative;
  z-index: 5;
}

/* .machine / .menu는 모바일 레이아웃을 위한 래퍼일 뿐이라 데스크톱에서는 상자를 없앤다 —
   자식이 그대로 상단바의 flex 아이템이 되므로 DOM을 묶기 전과 같은 한 줄이 나온다.
   대신 DOM 순서가 모바일 기준(계정이 메뉴 안)이라, 데스크톱 배치는 order로 되돌린다. */
.machine,
.menu {
  display: contents;
}
.brand {
  order: 1;
}
.tabs {
  order: 2;
}
.spacer {
  order: 3;
}
.clock {
  order: 4;
}
.divider {
  order: 5;
}
.machine > * {
  order: 6;
}
.user {
  order: 7;
}

/* 브랜드 */
.brand {
  display: flex;
  align-items: center;
  gap: 9px;
  flex: none;
}
.logo {
  width: 30px;
  height: 30px;
  color: var(--ink); /* currentColor → 라인아트 색. 다크 표면에선 color만 바꾸면 됨 */
  flex: none;
  display: block;
}
.logo :deep(svg) {
  width: 100%;
  height: 100%;
  display: block;
}
.wordmark {
  font-size: 18px;
  font-weight: 700;
  letter-spacing: -0.01em;
}
.tag {
  font-family: var(--font-mono);
  font-size: 9.5px;
  color: var(--muted);
  letter-spacing: 0.12em;
  border-left: 1px solid var(--line);
  padding-left: 9px;
}

/* 탭 */
.tabs {
  display: flex;
  align-items: center;
  height: 56px;
  margin-left: 4px;
}
.tabs a {
  display: flex;
  align-items: center;
  height: 56px;
  padding: 0 14px;
  font-size: 13.5px;
  font-weight: 500;
  color: var(--sub);
  text-decoration: none;
  border-bottom: 2.5px solid transparent;
  white-space: nowrap;
}
.tabs a:hover {
  color: var(--ink);
}
.tabs a.router-link-exact-active {
  color: var(--ink);
  font-weight: 700;
  border-bottom-color: var(--amber);
}

.spacer {
  flex: 1;
}
.clock {
  font-size: 12.5px;
  color: var(--sub);
  white-space: nowrap;
}
.divider {
  width: 1px;
  height: 22px;
  background: var(--line);
}

/* 상태 점 */
.dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  display: inline-block;
  flex: none;
}
.dot.amber {
  background: var(--amber);
}
.dot.ok {
  background: var(--ok);
}
.dot.muted {
  background: var(--muted);
}
.dot.danger {
  background: var(--danger);
}

/* 공용 pill */
.pill {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  border: 1px solid var(--line);
  border-radius: 999px;
  padding: 5px 11px;
  font-size: 11.5px;
  background: var(--surface);
  white-space: nowrap;
  flex: none;
}

/* 로봇 (단일 기체) */
.robot-id {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  flex: none;
  border: 1.5px solid var(--ink);
  border-radius: 999px;
  padding: 5px 12px;
  font-size: 12px;
  font-weight: 700;
  background: var(--surface);
  color: var(--ink);
}
.robot-id .rid {
  font-family: var(--font-mono);
}

/* 배터리 */
.batt {
  gap: 7px;
}
.batt-shell {
  width: 25px;
  height: 10px;
  border: 1.5px solid var(--ink);
  border-radius: 2.5px;
  position: relative;
  display: inline-block;
}
.batt-fill {
  position: absolute;
  top: 1.5px;
  left: 1.5px;
  bottom: 1.5px;
  display: block;
  border-radius: 1px;
}
.batt b {
  font-family: var(--font-mono);
}

/* 통신 */
.bars {
  display: inline-flex;
  align-items: flex-end;
  gap: 1.5px;
}
.bars i {
  width: 3px;
  display: block;
  background: var(--ink);
}
.comms.off {
  border-color: var(--danger);
  color: var(--danger);
  font-weight: 700;
}

/* 로봇 상태 pill */
.mode-pill {
  font-weight: 700;
  background: var(--neutral-tint);
  border-color: var(--neutral-line);
}
.mode-pill.amber {
  background: var(--amber-tint);
  border-color: var(--amber-tint-line);
}
.mode-pill.danger {
  background: var(--danger-tint);
  border-color: var(--danger-line);
}
.mode-pill.ok {
  background: var(--ok-tint);
  border-color: var(--ok-line);
}

/* 관리자 */
.user {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  font-size: 12px;
  color: var(--sub);
  white-space: nowrap;
  flex: none;
}
.avatar {
  width: 28px;
  height: 28px;
  border-radius: 50%;
  background: var(--ink);
  color: var(--on-ink);
  display: inline-flex;
  align-items: center;
  justify-content: center;
  font-size: 12px;
  font-weight: 700;
}
.logout-btn {
  font: inherit;
  font-size: 11px;
  padding: 4px 10px;
  border: 1px solid var(--line);
  border-radius: 999px;
  background: var(--surface);
  color: var(--sub);
  cursor: pointer;
}
.logout-btn:hover {
  color: var(--ink);
  border-color: var(--ink);
}

/* 테마 토글 */
.theme-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  padding: 0;
  flex: none;
  border: 1px solid var(--line);
  border-radius: 999px;
  background: var(--surface);
  color: var(--sub);
}
.theme-btn:hover {
  background: var(--surface);
  color: var(--ink);
  border-color: var(--ink);
}
.theme-btn svg {
  width: 15px;
  height: 15px;
  display: block;
}

/* 햄버거 — 모바일에서만 나타난다. 전역 button 스타일(검은 배경)을 되돌린다. */
.hamburger {
  display: none;
  order: 2;
  flex-direction: column;
  justify-content: center;
  gap: 4px;
  width: 40px;
  height: 40px;
  padding: 0;
  flex: none;
  border: 1px solid var(--line);
  border-radius: 9px;
  background: var(--surface);
}
.hamburger:hover {
  background: var(--surface);
  border-color: var(--ink);
}
.hamburger i {
  display: block;
  width: 17px;
  height: 2px;
  margin: 0 auto;
  border-radius: 2px;
  background: var(--ink);
  transition:
    transform 0.2s ease,
    opacity 0.15s ease;
}
/* 열리면 X로 — 가운데 줄을 지우고 위·아래를 가운데(±6px = 높이 2 + gap 4)로 모아 교차 */
.topbar.menu-open .hamburger i:nth-child(1) {
  transform: translateY(6px) rotate(45deg);
}
.topbar.menu-open .hamburger i:nth-child(2) {
  opacity: 0;
}
.topbar.menu-open .hamburger i:nth-child(3) {
  transform: translateY(-6px) rotate(-45deg);
}

/* ── 모바일 상단바 ────────────────────────────
   1행: 브랜드 + 햄버거 · 2행: 기체 정보 · 메뉴는 슬라이드 다운 패널.
   기준은 1200px — 실측한 데스크톱 한 줄이 1100px이고, 배터리가 '—'에서 '100%'로 바뀌면
   45px쯤 더 든다. 여유를 두지 않으면 배터리 값이 들어오는 순간 상단바가 두 줄로 접힌다.
   대시보드 1컬럼 전환(DashboardView)도 같은 값을 쓴다 — '좁은 화면' 기준은 하나만 둔다. */
@media (max-width: 1200px) {
  .topbar {
    gap: 0;
    padding: 0 14px;
    min-height: 0;
  }
  /* 시계는 뺀다 — 휴대폰은 상태표시줄에 시계가 이미 있어 같은 정보를 두 번 쓰는 셈이다 */
  .clock,
  .divider,
  .spacer {
    display: none;
  }

  .brand {
    height: 52px;
  }
  .hamburger {
    display: flex;
    margin-left: auto;
  }

  /* 기체 정보 — 항상 보이는 둘째 줄. 배터리가 100%까지 차거나 '연결 끊김'으로 길어지면
     줄바꿈 대신 가로로 밀어 본다(줄이 늘면 지도가 그만큼 아래로 내려간다). */
  .machine {
    display: flex;
    order: 3;
    flex-basis: 100%;
    align-items: center;
    gap: 6px;
    padding-bottom: 9px;
    overflow-x: auto;
    scrollbar-width: none;
  }
  .machine::-webkit-scrollbar {
    display: none;
  }
  .robot-id,
  .pill {
    font-size: 11px;
    padding: 4px 9px;
  }

  /* 슬라이드 다운 패널 — 덮지 않고 상단바 셋째 줄로 들어가 아래 내용을 밀어낸다.
     흐름 안에 있어서 화면이 짧아도(가로 모드 등) 패널이 잘리지 않고 페이지가 늘어난다.

     상단바 좌우 패딩(14px) 밖까지 줄이 이어져야 목록처럼 읽힌다 — flex-basis를 패딩만큼
     키우고 음수 마진으로 되밀어, 테두리 상자만 화면 끝까지 뻗게 한다. */
  .menu {
    display: block;
    order: 4;
    flex-basis: calc(100% + 28px);
    margin: 0 -14px;
    max-height: 0;
    overflow: hidden;
    /* 닫힌 뒤에 visibility를 꺼야 접힌 패널의 링크로 탭 포커스가 들어가지 않는다 */
    visibility: hidden;
    transition:
      max-height 0.24s ease,
      visibility 0s linear 0.24s;
  }
  /* 실제 높이는 260px 남짓(4행 + 계정행)이다. 상한을 그보다 훨씬 크게 잡으면 눈에 보이는
     움직임이 중간에 끝나고 나머지 시간이 빈 채로 흘러 뚝 끊겨 보인다. */
  .topbar.menu-open .menu {
    max-height: 380px;
    visibility: visible;
    transition:
      max-height 0.24s ease,
      visibility 0s;
  }

  .menu .tabs {
    display: block;
    height: auto;
    margin: 0;
  }
  .menu .tabs a {
    height: auto;
    padding: 14px 18px;
    font-size: 15px;
    color: var(--ink);
    border-bottom: 1px solid var(--line-row);
    /* 밑줄 강조는 가로 탭에서나 읽히는 표시다 — 세로 목록에서는 왼쪽 띠로 바꾼다 */
    border-left: 3px solid transparent;
  }
  /* 기체 정보 줄과 가르는 선. 패널 자체가 아니라 첫 행에 둔다 — 패널에 두면 접힌 높이가
     0이어도 테두리는 남아, 메뉴를 닫아도 선 하나가 떠 있는다. */
  .menu .tabs a:first-child {
    border-top: 1px solid var(--line);
  }
  .menu .tabs a.router-link-exact-active {
    background: var(--amber-tint);
    border-bottom-color: var(--line-row);
    border-left-color: var(--amber);
  }
  .menu .user {
    display: flex;
    padding: 13px 18px;
    font-size: 13px;
  }
  /* 계정 행: 이름은 왼쪽, 테마·로그아웃은 오른쪽으로 붙인다 */
  .menu .user .theme-btn {
    margin-left: auto;
  }
  .menu .user .logout-btn {
    margin-left: 0;
  }

  .setup-banner {
    padding: 10px 14px;
    font-size: 12.5px;
  }
}

/* 첫 설정 유도 배너 */
.setup-banner {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
  padding: 10px 20px;
  background: var(--amber-tint);
  border-bottom: 1px solid var(--amber-tint-line);
  font-size: 13px;
  color: var(--ink);
}
.setup-cta {
  margin-left: auto;
  padding: 6px 14px;
  background: var(--ink);
  color: var(--on-ink);
  border-radius: 999px;
  font-size: 12px;
  font-weight: 700;
  text-decoration: none;
  white-space: nowrap;
}
.setup-cta:hover {
  background: var(--ink-strong);
}
</style>
