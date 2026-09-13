# 보행 동행 대시보드 (Vue 3)

저시력자용 AI 실내 안전 동행 로봇 프론트엔드. Vue 3 + Vite + Pinia + Vue Router + Axios.

핵심: 로봇 관제가 아니라 **보행 동행** 관점 — 누가 어떤 모드로 걷는 중인지(세션),
로봇이 지금 어디에서 무엇을 보고 있는지를 실시간으로 보여준다.

> 화면에 뜨는 로봇 값은 전부 로봇이 실제로 보낸 것이다. 서버에 목(mock) 생성부가 없으므로
> **미수신은 화면에서 '미수신'으로 보인다** — 위치가 없으면 지도에 로봇을 그리지 않고,
> 라이다가 끊기면 스캔을 지우고, 사유를 지도 아래 안내로 띄운다.

> 범위: **Phase 1(재프레임) + Phase 2(세션) + Phase 3(인증)**. 다중 로봇은 유보.

## 실행

백엔드를 먼저 켠다 → [web/backend/README.md](../backend/README.md)

```
cd web/frontend
npm install
npm run dev        # http://localhost:5173
```

## 구조

```
src/
├─ main.js              # 앱 부팅 + WS 수신 시작
├─ App.vue              # 상단바 + 연결 배지 + 기체 CRITICAL 경고 배너 + 개입 요청 알림
├─ labels.js            # 도메인 값(event code/mode/status/reason) → 한글 매핑
├─ router/index.js      # 대시보드 / 장소·비콘 / 기체 이벤트 / 관리자 (+ 미지정 경로는 대시보드로)
├─ stores/robot.js      # 로봇 + 현재 세션 단일 저장소 (telemetry, lidar, events[]) — null = 미수신
├─ stores/assist.js     # 관리자 개입 요청 단일 슬롯 (미해결 1건 + 출동/해결 동작)
├─ services/
│  ├─ ws.js             # WebSocket + 지수 백오프 재연결 (telemetry/lidar/event/assist_request)
│  ├─ api.js            # Axios — sessions/assist-requests/robots/places/beacons/events/floorplans
│  └─ simRobot.js       # 콘솔 전용 시뮬 로봇(lumi.sim) — 방향키 조종. 아래 "시뮬 로봇" 참고
├─ components/
│  ├─ MapPanel.vue          # 실내 지도 — SLAM 맵(없으면 도면) + 로봇·목적지·비콘·라이다 오버레이
│  ├─ SessionPanel.vue      # 현재 동행 세션(모드·경과) + 로봇 송신값(위치·방향·속도·라이다)
│  ├─ BeaconPanel.vue       # 비콘 수신 상태 + 감지 목록 (번호·장소·RSSI·거리)
│  ├─ EventFeed.vue         # 기체 이벤트 실시간 피드 (code + level + msg)
│  ├─ AssistAlert.vue       # 관리자 개입 요청 — 전체 화면 팝업(미접수) / 상단 바(출동 중)
│  └─ CameraPanel.vue       # Jetson→서버 JPEG WebSocket 카메라 + 자동 재연결
└─ views/
   ├─ DashboardView.vue     # 카메라·비콘 / 지도·위치 / 세션·이벤트피드 3컬럼
   ├─ PlacesView.vue        # 장소·비콘 조회 + 도면 업로드
   ├─ EventsView.vue        # 기체 이벤트 이력
   └─ AdminsView.vue        # 관리자 계정 관리
```

데이터 흐름: `FastAPI /ws → services/ws.js → stores/robot.js → 컴포넌트 자동 갱신`

카메라 흐름: `Jetson /ws/camera/ingest/1 → FastAPI 중계 → /ws/camera/view/1 → CameraPanel.vue`.
운영 빌드는 `VITE_CAMERA_WS_URL=/ws/camera/view/1`을 사용하며 관리자 JWT로 시청 연결을 인증한다.

## 시뮬 로봇 (콘솔 전용, S15P11C201-149·150)

로봇 없이 지도 위에서 로봇을 움직여 보고 싶을 때 쓴다. **브라우저 콘솔에서만** 켤 수 있고,
UI에는 진입점이 없다.

```js
lumi.sim()                      // 이 브라우저에서만, 지도 한가운데에서 시작
lumi.sim(3, 0)                  // 좌표 지정 (m, 활성 지도와 같은 프레임)
lumi.sim(3, 0, 90)              // 방향까지 지정 (+x축 기준 반시계, 도)
lumi.sim({ live: true })        // 실시간 연동 — 접속한 모든 대시보드에 뜬다
lumi.sim({ live: true, x: 41.6, y: 24.5, heading: 0 })
lumi.sim.on()                   // false | "local" | "live" | "remote" — 화면에는 표식이 없다
lumi.sim.pose()                 // 시뮬이 믿는 현재 좌표 (전송이 막혔는지 가려낼 때)
lumi.sim.stop()                 // 끄기
lumi.sim.help()                 // 사용법
```

**↑ 전진 · ↓ 후진 · ← 좌회전 · → 우회전** (누르고 있으면 계속). 0.6 m/s · 120°/s로 움직이고
지도 밖으로는 나가지 않는다. 입력창에 타이핑 중일 때는 방향키를 가로채지 않는다.

### 두 가지 모드

| | `local` (기본) | `live` |
|---|---|---|
| 보이는 범위 | 이 브라우저만 | + 접속한 **모든** 대시보드 |
| 서버 | 아무것도 안 보냄 | `POST /api/pose` 5Hz — 실 로봇이 쓰는 그 인그레스 |
| 백엔드 | 없어도 됨 | 떠 있어야 함 |
| 조종 화면 지연 | 즉시 | 즉시 (시뮬을 우선하므로) |
| 끄면 | 즉시 원상복구 | 이 화면은 즉시, 다른 화면은 2초(`POSE_TTL`) 뒤 |

`live`는 브라우저가 ROS 브리지 자리에 들어가는 것이다 — pose 인그레스가 무인증 머신 채널이고
CORS가 열려 있어 그대로 쏠 수 있다.

**두 모드 모두 조종 중인 화면은 시뮬을 우선한다**(`stores/robot.js`의 `pos` getter). 실 로봇이
동시에 pose를 쏘고 있어도 이 화면의 로봇은 흔들리지 않는다. 서버는 실 좌표를 **막지 않는다** —
막으면 그 사이 브리지가 죽어도 아무도 모르기 때문이다. 그래서 live 중에 실 로봇이 같이 쏘면
서버에 남는 값은 둘이 섞이고, 조종하지 않는 다른 대시보드에서는 로봇이 두 위치를 오갈 수 있다.

서버 쪽 확인은 `GET /api/pose`의 `source`로 한다: `robot` | `sim` | `null`(미수신).
조종하지 않는 대시보드에서는 `lumi.sim.on()`이 `"remote"`를 돌려준다.

### 알아둘 점

- **화면에는 시뮬 표식이 없다** — 시연에서 제품 화면을 그대로 보여주기 위해서다. 지도 마커·헤더
  배지·세션 카드 전부 실 로봇과 동일하게 그려진다.
  → **지금 보이는 로봇이 진짜인지 시뮬인지는 콘솔에서만 알 수 있다** (`lumi.sim.on()`).
- 조종 탭을 백그라운드로 보내도 전송은 이어진다(브라우저가 타이머를 ~1Hz로 늦추지만 끊기진
  않는다). `requestAnimationFrame`을 쓰지 않는 이유가 이것 — rAF는 백그라운드에서 아예 멈춰
  잠깐 다른 창을 봤을 뿐인데 모든 대시보드가 '미수신'으로 바뀐다.
- `local` 모드에서는 실 pose를 수신 중이어도 시뮬이 이 화면을 덮는다(콘솔에 경고).

> 자동으로 켜지지 않는 이유: 서버가 목으로 자리를 채우면 '로봇 미연결'과 '정상 주행'이 화면에서
> 똑같아져 브리지가 죽어도 알 수 없다(S15P11C201-147). 이 시뮬은 사람이 콘솔에서 켠 동안만
> 살아 있고, 끄면 곧바로 "미수신"이 다시 드러난다.

## 확인 방법

로봇 없이도 인그레스를 직접 호출해 화면을 확인할 수 있다(전부 무인증 머신 채널).

1. 로그인 직후 대시보드는 **동행 세션 없음 · 위치 미수신** 상태다 — 지도에 로봇이 없다.
   이게 로봇이 안 붙었을 때의 정상 화면이다.
2. `POST /api/pose {"x":.., "y":.., "heading":..}`를 5Hz로 보내면 지도에 로봇이 나타나고
   상태가 **이동중**으로 바뀐다(좌표가 안 변하면 정지). 멈추면 2초 뒤 사라진다(TTL).
   `POST /api/lidar`도 같은 방식으로 스캔이 켜지고 꺼진다.
3. 세션은 로봇이 연다 — `POST /api/sessions {"mode":"ASSIST"}`(손잡이 파지)
   → "현재 동행 세션"에 모드·경과가 붙는다.
   `POST /api/sessions/active/end`(손잡이 놓음)로 닫는다. 이력 화면은 없고 DB에만 남는다.
4. `POST /api/events {"code":"IMPACT"}` → 기체 이벤트 피드에 항목 추가,
   `CRITICAL`이면 상단에 경고 배너.
5. `POST /api/assist-requests` → **화면 전체가 어두워지며 "관리자 개입 필요" 팝업**,
   로봇 상태가 "비상 정지"로 바뀐다.
   "출동합니다" → 팝업이 상단 바로 내려가고 관제 화면을 다시 볼 수 있다(상태는 계속 정지).
   "상황 해결" → 바가 사라지고 상태가 풀린다. 새로고침해도 미해결이면 팝업이 복원된다.
6. 백엔드를 끄면 상단 "연결 끊김" → 다시 켜면 자동 재연결
```
