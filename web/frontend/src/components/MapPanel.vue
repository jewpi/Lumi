<script setup>
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { useRobotStore } from '@/stores/robot'
import { useFloorplanStore } from '@/stores/floorplan'
import { useMapStore } from '@/stores/map'
import { API_BASE, getBeacons, getPlaces } from '@/services/api'

const robot = useRobotStore()
const floorplan = useFloorplanStore()
const mapStore = useMapStore()

// 마커 크기는 픽셀이 아니라 미터로 잡는다 — 도면(25px/m)과 SLAM 맵(20px/m)은 viewBox
// 크기가 크게 다르므로, px로 고정하면 한쪽에서 점처럼 작거나 화면을 덮어버린다.
//
// 기준은 복도다. '본관 2층' 도면에서 재보니 복도 폭이 1.76~2.0m라, 마커 전체가 그 안에
// 들어와야 로봇이 어느 쪽 벽에 붙어 있는지가 읽힌다.
//
// robot 0.6은 지름 1.2m — 실제 기체보다 크지만, 도면 전체(66m)를 한 화면에 놓고 볼 때
// 실물 크기로는 점이 돼 버려서 눈에 보이는 쪽을 택한 값이다.
// pulse는 scale(1.6)까지 커지므로 최대 지름이 복도(1.76m)를 넘지 않게 역산했다(1.70m) —
// 이보다 키우면 후광이 양쪽 벽을 덮어 로봇이 어디에 붙어 있는지 다시 안 보인다.
// heading은 로봇 반경(0.6)보다 충분히 길어야 화살표가 원 밖으로 나온다.
const M = {
  robot: 0.6, pulse: 0.53, heading: 0.95, beacon: 0.36,
  dest: 0.36, label: 0.64, font: 0.6,
}

/** 지도 배경 + 좌표 변환의 단일 진입점. SLAM 맵이 있으면 그걸 쓰고, 없을 때만 도면으로
 *  폴백한다 — 맵은 pose와 같은 map 프레임이라 정합이 보장되지만, 도면은 사람이 축척·
 *  원점을 손으로 맞춰야 하기 때문. 둘 다 없으면 null(빈 상태). */
const view = computed(() => {
  const m = mapStore.active
  if (m) {
    const [ox, oy, yaw] = m.origin
    const cos = Math.cos(yaw)
    const sin = Math.sin(yaw)
    const pxPerM = 1 / m.resolution
    return {
      source: 'slam',
      w: m.width,
      h: m.height,
      pxPerM,
      href: `${API_BASE}${m.image_url}`,
      name: 'SLAM 맵',
      meta: `1셀 ${m.resolution}m · ${(m.width * m.resolution).toFixed(1)}×${(m.height * m.resolution).toFixed(1)}m`,
      /** map 프레임(m) → 이미지 px. 원점 평행이동 후 -yaw 회전(yaw=0이면 항등),
       *  마지막에 y를 뒤집는다 — ROS 셀 y는 위로 증가하는데 이미지 행은 아래로 내려간다.
       *  뒤집기가 (h - cy)인 이유: SVG는 연속 좌표계라 cy=0이 이미지 아래 '모서리'(y=h),
       *  cy=h가 위 모서리(y=0)로 정확히 맞는다. 배열 인덱싱에서 쓰는 (h - 1 - cy)를
       *  여기 쓰면 1px(=resolution m)만큼 위로 밀린다. */
      toPx(x, y) {
        const dx = x - ox
        const dy = y - oy
        const cx = dx * cos + dy * sin
        const cy = -dx * sin + dy * cos
        return { x: cx * pxPerM, y: m.height - cy * pxPerM }
      },
    }
  }
  const p = floorplan.active
  if (p) {
    return {
      source: 'plan',
      w: p.width_px,
      h: p.height_px,
      pxPerM: p.px_per_m,
      // dev: :8000 직결 · prod: same-origin(nginx /api 프록시). 공개 uuid URL이라 헤더 불필요.
      href: `${API_BASE}${p.image_url}`,
      name: p.name,
      meta: `축척 1m = ${p.px_per_m}px`,
      toPx: (x, y) => ({ x: x * p.px_per_m, y: p.height_px - y * p.px_per_m }),
    }
  }
  return null
})

const places = ref([])
const beacons = ref([])
const showLidar = ref(true)

onMounted(async () => {
  if (!mapStore.loaded) mapStore.refresh()
  if (!floorplan.loaded) floorplan.refresh()
  // 로봇이 주행하며 맵을 넓혀 보내면 geometry가 바뀐다 — 지도를 띄워둔 동안만 폴링한다.
  mapStore.startPolling()
  ;[places.value, beacons.value] = await Promise.all([getPlaces(), getBeacons()])
})
onUnmounted(() => mapStore.stopPolling())

const toPx = (x, y) => view.value.toPx(x, y)

/** 지도 밖으로 나간 마커인지. 장소·비콘 좌표는 도면 기준으로 등록돼 있어서 SLAM 맵
 *  위에서는 대부분 범위를 벗어난다 — 엉뚱한 자리에 그리는 대신 숨기고 안내를 띄운다. */
function onMap(p) {
  const v = view.value
  return !!p && p.x >= 0 && p.x <= v.w && p.y >= 0 && p.y <= v.h
}

const beaconPins = computed(() => {
  if (!view.value) return []
  return beacons.value
    .filter((b) => b.x != null)
    .map((b) => ({ ...b, px: toPx(b.x, b.y) }))
})
// 도면 기준으로 등록된 좌표라 SLAM 맵 위에서는 범위를 벗어나는 게 많다 — 엉뚱한 자리에
// 그리는 대신 조용히 뺀다(비콘 수신 상태는 BeaconPanel이 따로 보여준다).
const visibleBeacons = computed(() => beaconPins.value.filter((b) => onMap(b.px)))
// 스캔에 잡힌 번호. 서버는 비콘을 만들지 않으므로 여기 있음 = 지금 잡히는 중이다.
const detectedNos = computed(() => new Set((robot.beacons ?? []).map((b) => b.no)))

// 로봇 화면 좌표: slam = 연속 좌표, beacon = 매핑된 장소 좌표로 근사.
// pos가 없으면(위치 미수신) 아무것도 그리지 않는다 — 마지막 위치를 붙잡아 두면
// 로봇이 끊긴 뒤에도 그 자리에 서 있는 것처럼 보인다.
const robotPx = computed(() => {
  const pos = robot.pos
  if (!view.value || !pos) return null
  if (pos.mode === 'slam') return toPx(pos.x, pos.y)
  const b = beacons.value.find((b) => b.no === pos.beacon_no)
  return b && b.x != null ? toPx(b.x, b.y) : null
})

// 실 pose인데 맵 범위를 벗어난 경우 — 프레임 불일치(뒤집힘·origin 누락)나 로봇이 맵
// 밖으로 나간 상황. 잘려서 안 보이는 것과 구분되게 사유를 표시한다.
const robotOffMap = computed(() => !!robotPx.value && !onMap(robotPx.value))

// 진행 방향 표시선 끝점. 화면 좌표에서 각도를 돌리지 않고 map 프레임에서 끝점을 구한 뒤
// toPx에 통과시킨다 — 그래야 origin yaw가 0이 아닐 때도 회전이 자동으로 따라온다.
const headingTip = computed(() => {
  const pos = robot.pos
  if (!robotPx.value || pos?.mode !== 'slam') return null
  const a = (pos.heading * Math.PI) / 180
  return toPx(pos.x + M.heading * Math.cos(a), pos.y + M.heading * Math.sin(a))
})

const destPx = computed(() => {
  if (!view.value || !robot.dest) return null
  const p = places.value.find((p) => p.id === robot.dest.id)
  if (!p || p.x == null) return null
  const px = toPx(p.x, p.y)
  return onMap(px) ? px : null
})

/** 지도 아래 안내는 하나만 남긴다 — 좌표가 어긋나 로봇이 화면 밖에 찍히는 경우.
 *  이건 잘려서 안 보이는 것과 구분이 안 돼 조용히 빼면 '지도가 고장 났나'로 읽힌다.
 *  로봇 미수신은 헤더 배지와 위 머리말의 '로봇 미수신' 태그에 이미 나오므로 여기서
 *  반복하지 않는다. */
const notices = computed(() => {
  if (!robotOffMap.value) return []
  return [{
    key: 'off',
    level: 'warn',
    text: '로봇이 맵 범위를 벗어났습니다 — 좌표계가 어긋났거나(origin·상하반전) 로봇이 맵 밖으로 이동했습니다.',
  }]
})

// 라이다 스캔 → 지도 좌표 오버레이 (heading이 필요해서 slam 모드에서만).
// 스캔은 로봇 위치를 기준으로 뻗으므로 pos가 없으면 그릴 수 없다.
const lidarPath = computed(() => {
  const scan = robot.lidar
  const pos = robot.pos
  if (!view.value || !showLidar.value || !scan || pos?.mode !== 'slam') return ''
  const n = scan.ranges.length
  let d = ''
  scan.ranges.forEach((r, i) => {
    if (r == null || r <= 0) return
    const a = ((pos.heading + (i * 360) / n) * Math.PI) / 180
    const p = toPx(pos.x + r * Math.cos(a), pos.y + r * Math.sin(a))
    d += `M${p.x.toFixed(1)} ${p.y.toFixed(1)}l0 .1`
  })
  return d
})
</script>

<template>
  <section class="card map-card">
    <div class="map-head">
      <h3>실내 지도 — {{ view ? view.name : '지도 없음' }}</h3>
      <!-- 지도의 출처와 로봇 연결 상태는 다른 축이다 — 맵은 한 번 받으면 남지만
           pose는 5Hz로 계속 들어와야 하므로, 맵이 떠 있어도 로봇은 끊길 수 있다. -->
      <span v-if="view" class="src-tag" :class="view.source">
        {{ view.source === 'slam' ? 'SLAM' : '도면' }}
      </span>
      <span v-if="view" class="link-tag" :class="{ live: !!robot.pos }">
        {{ robot.pos ? '로봇 연결' : '로봇 미수신' }}
      </span>
      <span v-if="view" class="muted">{{ view.meta }}</span>
      <label v-if="view" class="toggle"><input type="checkbox" v-model="showLidar" /> 라이다 표시</label>
    </div>

    <div v-if="!view" class="map-empty">
      <p class="empty-title">표시할 지도가 없습니다</p>
      <p class="muted">
        로봇이 SLAM 맵을 전송하면 자동으로 표시됩니다. 로봇 연동 전이라면 기관 도면을
        업로드하고 이름·축척을 설정해 임시로 사용할 수 있습니다.
      </p>
      <RouterLink class="empty-cta" to="/places">도면 등록하기</RouterLink>
    </div>

    <div v-else class="map-body">
      <!-- --u = 1m당 픽셀. 마커 크기·선 두께를 미터로 잡아 도면과 맵 어느 쪽에서도
           같은 물리 크기로 보이게 한다 (viewBox 크기가 서로 크게 다르기 때문). -->
      <svg
        :viewBox="`0 0 ${view.w} ${view.h}`"
        :style="{ '--u': `${view.pxPerM}px` }"
        role="img"
        aria-label="관제 지도"
      >
        <image
          :href="view.href" :width="view.w" :height="view.h"
          :class="{ crisp: view.source === 'slam' }"
        />

        <!-- 비콘 (핵심 위치) — 지도 범위 안에 드는 것만. 채워진 것 = 지금 잡히는 비콘 -->
        <g v-for="b in visibleBeacons" :key="b.no">
          <circle
            :cx="b.px.x" :cy="b.px.y" :r="M.beacon * view.pxPerM"
            class="beacon"
            :class="{ detected: detectedNos.has(b.no), nearest: b.no === robot.nearestBeaconNo }"
          />
          <text
            :x="b.px.x" :y="b.px.y - M.label * view.pxPerM"
            class="beacon-label" :class="{ detected: detectedNos.has(b.no) }"
          >
            {{ b.place ?? `B-${b.no}` }}
          </text>
        </g>

        <!-- 목적지 -->
        <rect
          v-if="destPx"
          :x="destPx.x - M.dest * view.pxPerM" :y="destPx.y - M.dest * view.pxPerM"
          :width="M.dest * 2 * view.pxPerM" :height="M.dest * 2 * view.pxPerM"
          :transform="`rotate(45 ${destPx.x} ${destPx.y})`" class="dest"
        />

        <!-- 라이다 포인트 (지도 좌표로 변환) -->
        <path v-if="lidarPath" :d="lidarPath" class="lidar" />

        <!-- 로봇 -->
        <g v-if="robotPx">
          <circle :cx="robotPx.x" :cy="robotPx.y" :r="M.pulse * view.pxPerM" class="robot-pulse" />
          <line
            v-if="headingTip"
            :x1="robotPx.x" :y1="robotPx.y" :x2="headingTip.x" :y2="headingTip.y" class="robot-heading"
          />
          <circle :cx="robotPx.x" :cy="robotPx.y" :r="M.robot * view.pxPerM" class="robot" />
          <!-- 라벨은 펄스 최대 반경(0.74m) 바로 바깥에 둔다 — 마커를 줄인 만큼 같이 당기지
               않으면 이름만 허공에 떠 로봇과 안 붙어 보인다 -->
          <text :x="robotPx.x" :y="robotPx.y + M.label * 1.6 * view.pxPerM" class="robot-label">
            LUMI-01
          </text>
        </g>
      </svg>
    </div>

    <div v-if="view" class="legend muted">
      <span><i class="lg robot-lg"></i>로봇</span>
      <span><i class="lg dest-lg"></i>목적지</span>
      <span><i class="lg beacon-lg"></i>비콘</span>
      <span><i class="lg beacon-on-lg"></i>비콘 감지</span>
      <span><i class="lg lidar-lg"></i>라이다</span>
      <span v-if="robot.pos?.mode === 'beacon'" class="mode-note">
        비콘 모드 — 위치는 존 단위 근사, 라이다 오버레이 없음
      </span>
    </div>

    <!-- 좌표가 어긋나 로봇이 화면 밖에 찍힌 경우에만 뜬다 (평소에는 비어 있다) -->
    <ul v-if="notices.length" class="notices">
      <li v-for="n in notices" :key="n.key" :class="n.level">
        {{ n.text }}
      </li>
    </ul>
  </section>
</template>

<style scoped>
.map-card {
  padding: 0;
  overflow: hidden;
}
.map-head {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 12px 16px;
  border-bottom: 1px solid var(--line-soft);
}
.map-head h3 {
  margin: 0;
  flex: none;
}
.toggle {
  margin-left: auto;
  font-size: 13px;
  color: var(--sub);
  display: flex;
  align-items: center;
  gap: 5px;
  cursor: pointer;
}
/* 지도 래스터(SLAM 맵·도면)는 백엔드가 주는 밝은 이미지라 다크 모드에서도 밝다.
   그 위에 얹히는 마커까지 테마를 따라가면 잉크가 밝아져 흰 지도 위에서 사라진다 —
   토큰을 이 서브트리에서만 라이트 값으로 되돌려 고정한다(아래 마커 규칙은 그대로 둔다). */
.map-body svg {
  --ink: #171614;
  --sub: #6e6a62;
  --amber: #e8a23c;
  --amber-deep: #9a6a15;
  --amber-tint: #fbf1de;
  display: block;
  width: 100%;
  height: auto;
}
/* SLAM 맵은 셀 하나가 1px이라(463×190) 화면 폭으로 늘리면 크게 확대된다.
   보간을 끄면 RViz처럼 셀 경계가 살아 벽·미탐색 영역이 뭉개지지 않는다. */
.crisp {
  image-rendering: pixelated;
}
.src-tag {
  flex: none;
  padding: 2px 8px;
  border-radius: 999px;
  font-size: 12px;
  font-weight: 700;
  border: 1px solid var(--line);
  color: var(--sub);
}
.src-tag.slam {
  border-color: var(--amber);
  color: var(--amber);
}
.link-tag {
  flex: none;
  padding: 2px 8px;
  border-radius: 999px;
  font-size: 12px;
  font-weight: 700;
  border: 1px solid var(--line);
  color: var(--sub);
}
.link-tag.live {
  border-color: var(--link-live);
  color: var(--link-live);
}
.notices {
  margin: 0;
  padding: 8px 16px;
  list-style: none;
  border-top: 1px solid var(--line-soft);
  font-size: 13px;
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.notices li {
  color: var(--sub);
  padding-left: 14px;
  position: relative;
}
/* 경고는 색이 아니라 표식으로도 구분되게 — 색만으로 구분하면 색약 사용자가 놓친다 */
.notices li::before {
  content: '·';
  position: absolute;
  left: 2px;
  font-weight: 700;
}
.notices li.warn {
  color: var(--warn-text);
}
.notices li.warn::before {
  content: '!';
}
.map-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 6px;
  min-height: 320px;
  padding: 32px 20px;
  text-align: center;
  border: 2px dashed var(--line);
  border-radius: 10px;
  margin: 16px;
}
.empty-title {
  margin: 0;
  font-size: 15px;
  font-weight: 700;
}
.empty-cta {
  margin-top: 10px;
  padding: 8px 18px;
  background: var(--ink);
  color: var(--on-ink);
  border-radius: 8px;
  font-size: 13px;
  font-weight: 700;
  text-decoration: none;
}
.empty-cta:hover {
  background: var(--ink-strong);
}
/* 선 두께·글자 크기도 미터 기준 — --u(1m당 px)를 곱한다. SVG에서 CSS px는 user unit과
   같으므로 viewBox가 463px든 1500px든 실제 굵기가 같게 보인다. */
.beacon {
  fill: #fff;
  stroke: var(--sub);
  stroke-width: calc(var(--u) * 0.12);
}
/* 스캔에 잡힌 비콘만 채운다 — 등록돼 있지만 안 잡히는 것과 한눈에 구분된다 */
.beacon.detected {
  fill: var(--amber-tint);
  stroke: var(--amber);
}
.beacon.nearest {
  fill: var(--amber);
  stroke: var(--amber-deep);
  stroke-width: calc(var(--u) * 0.16);
}
.beacon-label {
  fill: var(--sub);
  font-size: calc(var(--u) * 0.6);
  font-weight: 600;
  text-anchor: middle;
}
.beacon-label.detected {
  fill: var(--amber-deep);
}
.dest {
  fill: var(--amber);
  stroke: var(--ink);
  stroke-width: calc(var(--u) * 0.12);
}
.lidar {
  fill: none;
  stroke: #2563eb;
  stroke-width: calc(var(--u) * 0.16);
  stroke-linecap: round;
  opacity: 0.75;
}
.robot {
  fill: var(--amber);
  stroke: var(--ink);
  stroke-width: calc(var(--u) * 0.16);
}
.robot-heading {
  stroke: var(--ink);
  stroke-width: calc(var(--u) * 0.16);
  stroke-linecap: round;
}
.robot-pulse {
  fill: rgba(232, 162, 60, 0.35);
  animation: pulse 2s ease-out infinite;
  transform-origin: center;
  transform-box: fill-box;
}
@keyframes pulse {
  0% {
    transform: scale(0.55);
    opacity: 0.9;
  }
  70%,
  100% {
    transform: scale(1.6);
    opacity: 0;
  }
}
.robot-label {
  fill: var(--ink);
  font-size: calc(var(--u) * 0.6);
  font-weight: 700;
  text-anchor: middle;
  paint-order: stroke;
  stroke: rgba(255, 255, 255, 0.85);
  stroke-width: calc(var(--u) * 0.16);
}
.legend {
  display: flex;
  flex-wrap: wrap;
  gap: 6px 18px;
  padding: 10px 16px;
  border-top: 1px solid var(--line-soft);
}
.legend span {
  display: inline-flex;
  align-items: center;
  gap: 6px;
}
/* 범례 표식은 지도 위 마커와 같은 색이어야 뜻이 통한다 — 카드가 어두워져도 함께 고정 */
.lg {
  --ink: #171614;
  --sub: #6e6a62;
  --amber: #e8a23c;
  --amber-deep: #9a6a15;
  width: 12px;
  height: 12px;
  display: inline-block;
  border-radius: 50%;
}
.robot-lg {
  background: var(--amber);
  border: 2px solid var(--ink);
}
.dest-lg {
  background: var(--amber);
  border: 2px solid var(--ink);
  border-radius: 2px;
  transform: rotate(45deg);
}
.beacon-lg {
  background: #fff;
  border: 2.5px solid var(--sub);
}
.beacon-on-lg {
  background: var(--amber);
  border: 2.5px solid var(--amber-deep);
}
.lidar-lg {
  background: #2563eb;
}
.mode-note {
  margin-left: auto;
}

/* 모바일 — 머리말이 한 줄에 안 들어가 라이다 토글이 화면 밖으로 밀려났었다.
   제목을 한 줄 차지하게 두고 태그·축척·토글을 아랫줄로 흘린다. */
@media (max-width: 720px) {
  .map-head {
    flex-wrap: wrap;
    gap: 7px 8px;
    padding: 11px 13px;
  }
  .map-head h3 {
    flex-basis: 100%;
  }
  .legend {
    padding: 9px 13px;
    gap: 5px 12px;
  }
  .notices {
    padding: 8px 13px;
  }
  .map-empty {
    margin: 12px;
    min-height: 220px;
    padding: 24px 16px;
  }
}
</style>
