# 보행 동행 API 서버 (FastAPI)

저시력자용 AI 실내 안전 **동행** 로봇의 API 서버. 명세서 v0.3 + 안내견 ERD 반영.

핵심 개념: 로봇을 목적지로 파견하는 자율주행이 아니라, **보행자가 손잡이를 잡고 걸으면 로봇이
동행하며 위험 시 햅틱·음성·제동으로 개입**한다.

- WebSocket `/ws` — 텔레메트리(300ms, 세션 요약 포함)·라이다·기체 이벤트·개입 요청 실시간 push
- WebSocket `/ws/camera/ingest/{robot_id}` → `/ws/camera/view/{robot_id}` — Jetson JPEG 영상 중계
- REST `/api/*` — 세션·개입 요청·장소·비콘·이벤트·도면 (SQLite 저장)
- **관리자 인증(Phase 3)**: JWT Bearer 헤더 방식 **전체 로그인 게이트** — 로그인 외 모든
  브라우저向 API(읽기 포함)와 `/ws`는 관리자 토큰 필수. 도면 업로드는 하드닝된 관리자 전용.
- **목(mock) 생성부 없음(S15P11C201-147)** — 위치·라이다·탐지·비콘·기체 이벤트는 전부 로봇이
  보내는 실데이터다. 서버가 만드는 값은 하나도 없으므로 **미수신 채널은 null로 방송**되고,
  대시보드가 그 상태를 그대로 표시한다. 서버가 주인인 상태는 세션과 정지 잠금뿐(`app/robot/state.py`).

> 서버가 값을 지어내지 않는 이유: 목이 채워 주면 '로봇이 안 붙었다'와 '붙어서 잘 돈다'가
> 화면에서 똑같이 보인다. 시연 중 브리지가 죽어도 알 방법이 없어진다.

> 다중 로봇(robots는 1행만)과 브리지/AI 인그레스(pose·detections·lidar·beacon-scan·events)의
> 디바이스 키 인증은 후속.

## 실행

```
cd web/backend
python -m venv venv
venv\Scripts\activate          # Git Bash: source venv/Scripts/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000 --env-file .env
```

- **인증 환경변수 필수** — `web/backend/.env`(비커밋, 템플릿 `.env.example`) 한 파일을
  **로컬 uvicorn(`--env-file`)과 docker compose(backend `env_file:`)가 공유**한다.
  최소 `SECRET_KEY`, 최초 1회 `ADMIN_PASSWORD`:

  | 변수 | 필수 | 설명 |
  |---|---|---|
  | `SECRET_KEY` | ✅ | JWT 서명 키. 없으면 부팅 거부. 생성: `python -c "import secrets;print(secrets.token_urlsafe(48))"` |
  | `ADMIN_USERNAME` | – | 최초 시드 계정명 (기본 `admin`) |
  | `ADMIN_PASSWORD` | 최초 1회 | admins 테이블이 비어 있을 때만 시드에 사용 (12자 이상). 기존 계정을 덮어쓰지 않음 |
  | `ACCESS_TOKEN_EXPIRE_MINUTES` | – | 토큰 만료(분), 기본 480 |
  | `UPLOAD_DIR` | – | 도면 저장 경로 (기본 `media/floorplans`, 도커는 `/data/uploads` 볼륨) |
  | `MAX_UPLOAD_BYTES` / `MAX_IMAGE_PIXELS` | – | 업로드 상한 (기본 10MB / 4천만 px) |

- 로그인: `POST /api/auth/login` (form-urlencoded `username`/`password`) → `{access_token}` →
  이후 요청에 `Authorization: Bearer <token>`. Swagger의 **Authorize** 버튼도 동일.
- Swagger: http://localhost:8000/docs · WebSocket: `ws://localhost:8000/ws`
  (WS 인증은 서브프로토콜 — `new WebSocket(url, ["bearer", <token>])`, 실패 시 1008로 닫힘)
- DB `robot.db`는 첫 실행 시 자동 생성·시드 (git 미추적). **기존 테이블 스키마 변경 시 삭제 후 재실행**
  (admins/floorplans는 `IF NOT EXISTS` 추가라 기존 DB에 그대로 붙는다)
- 측위 방식 전환: `$env:POSITIONING_MODE="beacon"` (slam 기본) — 세션 mode(ASSIST/GUIDE)와 무관.
  어느 모드든 실 수신이 없으면 `pos`는 null이다(서버가 대신 만들지 않는다).
- 테스트: `python -m pytest tests/ -q` (인증 게이트·업로드 하드닝·pose·세션/이벤트/카메라 인그레스·WS 회귀 122건)

## 데이터 모델 (ERD)

`robots` · `places` · `beacons` · `walk_sessions` · `assist_requests` · `events`

> 보행자(pedestrians) 테이블·API는 제거했다(S15P11C201-147) — 개인 프로필을 등록·관리할
> 화면도, 그 값을 쓰는 로직도 없어 빈 스키마만 남아 있었다. 세션에는 사람 식별 정보를
> 싣지 않고 **동행이 열려 있다는 사실과 모드**만 남긴다.

- **walk_sessions**: mode `ASSIST`(자유 동행) / `GUIDE`(목적지 안내), status `WALKING/ARRIVED/ENDED/CANCELED`,
  source `voice/dashboard`. GUIDE만 `place_id`. 관리자 귀속(`admin_id`) 컬럼은 제거했다 —
  세션을 여는 주체가 로봇뿐이라 채울 수 있는 경로가 없다.
  **개시·종료는 로봇만 한다** — 동행은 손잡이를 잡을 때 시작되고 놓을 때 끝나므로 그 사실을
  아는 쪽은 로봇이다. 관제 화면에 개시 버튼을 두면 실제 손잡이 상태와 화면이 어긋난다.
- **assist_requests**: **관리자 개입 요청** — 로봇이 스스로 못 푸는 상황(치워야 하는 장애물 등).
  reason `path_blocked/repeated_brake/drop_hazard/robot_stuck/help_requested`,
  status `OPEN`(대응 대기) → `ACK`(출동 중) → `RESOLVED`(해결). 자세한 내용은 아래 절 참고.
- **events**: 기체 이상(IMPACT/FALL/EMERGENCY_STOP/LOW_BATTERY/COMM_LOST) + robot_id/session_id.
  로봇이 `POST /api/events`로 올린다.

> 시드는 실제 설비만 넣는다 — 장소 5곳·비콘 4개·기체 1대. 세션 시드는 두지 않는다:
> 아무도 걷지 않았는데 이력이 있으면 지어낸 기록과 실제 기록이 화면에서 구분되지 않는다.

## WebSocket 메시지

| type | 주기 | 내용 |
|---|---|---|
| `telemetry` | 300ms | pos, status(STANDBY/WALKING/ARRIVED/EMERGENCY), battery, **session**(요약), dest, path, obstacles, beacons·beacon_nearest_no(스캔 수신 중일 때만) |
| `lidar` | 300ms | 라이다 스캔. 미수신 구간에는 `ranges: null` |
| `event` | 발생 시 | 기체 이상 (로봇이 올린 것만) |
| `assist_request` | 발생·상태 변경 시 | **관리자 개입 요청** — 대시보드가 전체 화면 팝업으로 띄운다 |

세션은 telemetry.session에 매 틱 실려 접속 즉시 복원된다(별도 session 타입 없음).

**수신이 없으면 비어서 나간다** — 서버에는 폴백할 목 값이 없다:

| 필드 | 출처 | 미수신일 때 |
|---|---|---|
| `pos` | `POST /api/pose` (slam 모드) / `POST /api/beacon-scan` (beacon 모드) | `null` — 지도에 로봇을 그리지 않는다 |
| `obstacles` | `POST /api/detections` | `[]` |
| `beacons`·`beacon_nearest_no` | `POST /api/beacon-scan` | 필드 자체가 빠진다 |
| `lidar.ranges` | `POST /api/lidar` | `null` — 지도에서 스캔이 지워진다 |
| `battery` | 아직 수신 창구 없음 | 항상 `null`(헤더에 `—`) |
| `path` | 로봇이 들고 있다(하드코딩 주행 경로) | 항상 `null` |

`beacons`는 **필드 없음 = 로봇 미수신**이고, 빈 배열은 "수신 중이나 잡히는 비콘 없음"이다.
대시보드가 이 둘을 구분해 표시한다. `beacon_nearest_no`는 로봇이 판정한 최근접 번호로,
측위 모드와 무관하게 함께 실린다(slam 모드에서도 존 표시가 가능하도록).

### 카메라 WebSocket

Jetson은 EC2가 로봇 사설망으로 접속할 수 없으므로 `wss://<host>/ws/camera/ingest/1`에
아웃바운드로 연결한다. 이 머신 인그레스는 EC2 네트워크 계층에서 보호하므로 별도 디바이스
키를 요구하지 않는다. 관리자 시청 채널 `/ws/camera/view/1`은 기존 JWT 서브프로토콜 인증을 쓴다.

연결 후 선택적으로 `camera_init` JSON을 1회 보내고, 이후 JPEG 한 장을 binary 메시지 하나로 보낸다.

```json
{"type":"camera_init","camera_id":"front","format":"jpeg","width":640,"height":480,"fps":10,"quality":70}
```

- 권장: JPEG 640×480, 10 FPS, quality 70
- 최대 프레임 크기: `CAMERA_MAX_FRAME_BYTES`(기본 300KB), 초과 시 close 1009
- JPEG가 아닌 binary 또는 잘못된 metadata는 close 1003
- 느린 화면에는 밀린 프레임을 쌓지 않고 가장 최신 프레임만 전달

## REST API

| Method | Path | 설명 |
|---|---|---|
| GET | /api/sessions | 세션 이력 (`status`, `limit`) — 대시보드에는 이력 화면이 없다(Swagger·운영 점검용) |
| GET | /api/sessions/active | 진행 중 세션 (없으면 null) |
| GET | /api/sessions/{id} | 세션 상세 |
| POST | /api/sessions | **세션 시작 (내부용)** — 손잡이 파지. `{mode, place_id?}`, GUIDE는 place_id 필수 |
| POST | /api/sessions/active/end | **세션 종료 (내부용)** — 손잡이 놓음 (`?status=ENDED\|CANCELED`) |
| POST | /api/assist-requests | **관리자 개입 요청 발생 (내부용)** — 아래 "관리자 개입 요청" 참고 |
| GET | /api/assist-requests | 개입 요청 이력 (`status`, `limit`) |
| GET | /api/assist-requests/active | 미해결 요청 (없으면 null) — 새로고침 시 팝업 복원용 |
| POST | /api/assist-requests/{id}/ack | 출동 접수 (누가 맡았는지 기록, 로봇은 계속 정지) |
| POST | /api/assist-requests/{id}/resolve | 현장 조치 완료 → 요청 종료 + **보행 재개** |
| GET | /api/robots | 로봇 목록 |
| GET/POST/PUT/DELETE | /api/places | 장소 CRUD |
| GET/PUT | /api/beacons | 비콘 목록·매핑 |
| GET | /api/destinations | GUIDE 목적지 후보 장소 |
| GET | /api/events | 기체 이벤트 이력 (`level`, `session_id`, 기간) |
| POST | /api/events | **기체 이벤트 수신 (내부용)** — 아래 "기체 이벤트 인그레스" 참고 |
| POST | /api/auth/login | **공개** — 관리자 로그인(form) → JWT. 5회 연속 실패 시 5분 잠금 |
| GET | /api/auth/me | 내 관리자 정보 (프론트 새로고침 복원용) |
| GET/POST/DELETE | /api/admins | 관리자 목록·생성·삭제 (기존 관리자만, 비번 12자 이상, 자기 자신·마지막 관리자 삭제 불가) |
| POST | /api/floorplans | 도면 업로드(multipart `file`+`name`(표시명)+`px_per_m`) → 즉시 활성. PNG/JPEG/WebP만, 10MB·픽셀 상한, 실디코드 검증, uuid 파일명 |
| GET | /api/floorplans, /active | 도면 이력·활성 도면 geometry(width/height/px_per_m + image_url) |
| GET | /api/floorplans/image/{filename} | **공개** — 활성 도면 이미지 서빙 (uuid 파일명이라 열거 불가, nosniff) |
| POST/GET | /api/pose | **로봇 SLAM 위치 수신 (내부용, 5Hz)** — 아래 "로봇 pose 인그레스" 참고 |
| POST | /api/detections, /api/lidar | AI·라이다 수신 (내부용 — 디바이스 키 인증은 후속) |
| POST/GET | /api/beacon-scan | BLE 비콘 스캔 수신 (내부용 — 번호→장소명은 서버가 해석) |

위 표에서 "공개" 표기가 없는 모든 `/api/*`와 `/ws`는 관리자 토큰 필수(전체 로그인 게이트).

## 로봇 pose 인그레스 (5Hz)

ROS 브리지가 SLAM 추정 위치를 `POST /api/pose`로 보내면, TTL 이내인 동안 텔레메트리
`pos`로 방송된다. **이 값이 위치의 유일한 출처다** — 끊기면 `pos`는 null이 되고 지도에서
로봇이 사라진다(마지막 위치를 붙잡아 두면 끊긴 걸 알 수 없다).

```json
{"robot_id": 1, "ts": "2026-07-28T01:30:15.123Z", "x": 33.5, "y": 18.02, "heading": 271}
```

| 필드 | 필수 | 설명 |
|---|---|---|
| `x`, `y` | ✅ | 활성 SLAM 맵과 같은 map 프레임(m). 맵이 없어 도면으로 폴백한 경우에만 도면 좌표로 해석된다 |
| `heading` | ✅ | +x축 기준 **반시계 각도(도)**. ROS yaw(rad)는 브리지가 변환해 보낸다 |
| `robot_id` | – | 기본 1 |
| `ts` | – | UTC ISO8601. 생략 시 서버 수신 시각 |
| `sim` | – | 시연용 시뮬(프론트 `lumi.sim`)이 보낸 좌표. **실 브리지는 보내지 않는다**(기본 false) |

- **무인증**(머신 인그레스) — ROS 쪽에 관리자 토큰을 심지 않는다. 디바이스 키는 후속.
- 서버가 `heading`을 0~360으로 정규화하고 좌표를 소수 2자리로 반올림한다 —
  브리지가 -180~180으로 보내든 누적각으로 보내든 대시보드가 받는 형식은 하나로 고정된다.
- **TTL `POSE_TTL`(기본 2초, 5Hz 기준 10프레임)** 을 넘겨 끊기면 `pos`가 비워진다.
- 스키마 불일치(필드 누락·`NaN`/`inf`)는 **422**로 즉시 거절하고, 직전 정상 위치는 유지한다.
- 측위 모드가 `beacon`(`POSITIONING_MODE=beacon`)이면 비콘 pos가 우선이라 pose는 `pos`를 덮지 않는다.
- **`sim` 플래그(S15P11C201-150)는 표시일 뿐 게이트가 아니다** — 시연용 시뮬이 쏘는 동안에도
  실 브리지 좌표를 그대로 받는다. 서버가 실 데이터를 막으면 막힌 사이에 브리지가 죽어도
  아무도 모르기 때문이다. 서버에 남는 값은 '마지막에 도착한 것'이고, 어느 쪽이었는지는
  `GET /api/pose`의 `source`(`robot` | `sim` | `null`)로 드러난다.
  시뮬을 조종하는 화면이 흔들리지 않는 건 **프론트가 시뮬을 우선**하기 때문이다
  (web/frontend/src/stores/robot.js).

### 수신율 검증

`GET /api/pose`는 지금 무엇이 방송되는지(`source`: `robot` 또는 미수신 시 `null`), 마지막
수신 후 경과(`age_ms`), 기동 후 누적 수신 횟수(`count`)를 돌려준다. `tools/pose_rate_check.py`가
이 `count` 차이로 실측 Hz를 잰다(폴링 샘플링이 아니라 정확한 값).

```
python tools/pose_rate_check.py watch --seconds 10 --expect-hz 5   # 실 브리지 수신율 관측
python tools/pose_rate_check.py send  --hz 5 --seconds 10          # 로봇 없이 서버만 확인
python tools/pose_rate_check.py watch --url http://localhost:8000
```

표준 라이브러리만 쓰므로 로봇의 라즈베리파이에서도 그대로 돌아간다. `--expect-hz`를 주면
±10%를 벗어날 때 종료 코드 1이라 CI·검수에 그대로 걸 수 있다.

> 윈도우에서 `--url http://localhost:8000`을 쓰면 요청마다 2초씩 멈춘다(`::1` 먼저 시도 →
> IPv4 폴백). 기본값인 `127.0.0.1`을 그대로 쓸 것.

## 기체 이벤트 인그레스

로봇이 자기 몸 상태의 이상을 올리는 경로. 저장 후 즉시 방송되고, `CRITICAL`은 대시보드
상단에 경고 배너로 뜬다. 개입 요청과 달리 **로봇을 멈추지 않는다** — 이쪽은 기록이고,
사람이 현장에 가야 풀리는 상황은 `POST /api/assist-requests`로 올린다.

```
POST /api/events                 # 로봇 (무인증 인그레스)
{"code": "IMPACT", "msg": "복도 기둥에 접촉했습니다"}
```

| 필드 | 필수 | 설명 |
|---|---|---|
| `code` | ✅ | `IMPACT` / `FALL` / `EMERGENCY_STOP` / `LOW_BATTERY` / `COMM_LOST` |
| `level` | – | `INFO`/`WARNING`/`CRITICAL`. 생략 시 code별 기본값 |
| `msg` | – | 관리자에게 보일 한 줄. 생략 시 code별 기본 문구 |
| `robot_id`, `ts` | – | 기본 1 / UTC ISO8601(생략 시 서버 수신 시각) |

- `session_id`는 **서버가 채운다** — 진행 중인 세션이 있으면 그 번호가 붙는다. 로봇이
  walk_sessions PK를 알 필요가 없고, 알게 하면 세션이 바뀔 때마다 내려보내는 경로가 하나 더 생긴다.
- `level`·`msg`를 로봇이 보내면 그쪽이 이긴다 — 현장에서 아는 게 더 정확하다.

데모 트리거 (로봇 없이 피드 확인):

```
curl -X POST http://localhost:8000/api/events -H "Content-Type: application/json" -d "{\"code\":\"IMPACT\"}"
```

## 관리자 개입 요청 (assist_requests)

기체 이벤트가 **지나간 일의 기록**이라면, 이쪽은 로봇이 스스로 풀 수 없어 **사람이 현장에
가야만 풀리는 상황**이다. 진행 방향을 막은 적치물이 대표적이다.
피드 한 줄로는 관리자가 놓치므로 대시보드가 **화면 전체를 덮는 팝업**으로 띄운다.

```
POST /api/assist-requests        # 로봇·AI (무인증 인그레스)
{"reason": "path_blocked", "detail": "복도 적치물로 통과 불가", "x": 33.5, "y": 18.0}
```

| 필드 | 필수 | 설명 |
|---|---|---|
| `reason` | – | `path_blocked`(기본) / `repeated_brake` / `drop_hazard` / `robot_stuck` / `help_requested` |
| `detail` | – | 관리자에게 보일 문장. 생략 시 reason별 기본 문구 |
| `x`, `y` | – | 발생 위치(m). 생략 시 **마지막으로 받은 pose**로 채운다. 위치조차 미수신이면 좌표 없이 열린다 |
| `robot_id`, `ts` | – | 기본 1 / UTC ISO8601(생략 시 서버 수신 시각) |

- **요청이 열려 있는 동안 로봇 상태는 `EMERGENCY`로 방송**된다. 보행자는 손잡이를 잡은 채
  기다리는 상태이므로, **`resolve`를 눌러야** 상태가 풀린다.
  `ack`(출동 접수)는 누가 가고 있는지만 알린다 — 장애물이 그대로인데 로봇을 보내면
  보행자를 다시 그 장애물로 데려가게 된다.
- **멱등** — 미해결 요청이 이미 있으면 새로 만들지 않고 기존 건을 `200`으로 돌려준다(신규는 `201`).
  로봇이 매 프레임 재전송하거나 통신 재시도를 해도 팝업이 쌓이지 않는다.
- 관제 화면이 여러 대여도 `ack`/`resolve`는 **먼저 누른 쪽만** 통과한다(늦은 쪽은 `409`).
- 서버 재기동 시 미해결 요청은 `RESOLVED`로 정리한다 — 로봇 정지 상태는 풀렸는데 팝업만 남는
  상황을 막는다(진행 중 세션 정리와 같은 이유).

데모 트리거 (로봇 없이 팝업 확인):

```
curl -X POST http://localhost:8000/api/assist-requests -H "Content-Type: application/json" -d "{\"reason\":\"path_blocked\",\"detail\":\"복도에 적치물이 놓여 통과할 수 없습니다\"}"
```

## 지도 좌표계 · 핵심 위치

- **도면은 관리자가 업로드해야 표시된다** (기본 도면 폴백 없음 — 미등록이면 지도는 빈 상태 +
  설정 유도 배너). 참고용 GTC동 2F 원본은 `docs/floorplan-2f.png` (1663×946px, 25px/m,
  외부 시설 마스킹판) — 데모 시 이 파일을 이름 "GTC동 2F", 축척 25로 업로드하면 된다.
- 원점 = 좌측 하단, m, **임시 축척 25px/m** (TBD #4 실측 시 도면 업로드 시 축척만 다시 지정)
- 복도: 좌측 가로 y=10.95, 우측 가로 y=12.0, 세로(화장실 방면) x=33.5, **상단 복도 y=25.3**(우측 블록 북쪽)
- **핵심 위치(비콘)**: 입구(34.0, 19.0)=B-1, 화장실(41.6, 24.5)=B-2, 지원실(57.0, 25.3)=B-3, 상담실(59.6, 12.2)=B-4.
  2반(대강의실-5, 20.6, 10.95)은 출발/대기 지점(비콘 없음).
- **지원실은 학생 출입 불가** → 비콘·목적지는 지원실 북쪽 문 **바깥(상단 복도)**.
- 목적지·비콘·지도 마커는 DB 시드에서 나오므로 위치 변경은 `database.py` SEED만 고치고 robot.db 재생성.
- 도면 좌표와 로봇이 보내는 SLAM map 프레임은 서로 다르다 — 로봇이 맵(`POST /api/map`)을
  올리면 대시보드가 그 맵 위에 그리고, 없을 때만 업로드 도면으로 폴백한다.

## 구조

```
app/
├─ main.py            # lifespan(SECRET_KEY 검증·admin 시드·DB·미완 세션 정리 + 300ms 루프), 게이트, /ws(인증)
│                     # apply_ingress()가 텔레메트리 골격에 실수신값(pose·탐지·비콘)을 싣는다
├─ config.py          # 측위·주기·TTL·DB 경로 + SECRET_KEY·토큰 만료·UPLOAD_DIR 등
├─ database.py        # SQLite 스키마·시드(설비만)·쿼리 헬퍼 (admins·floorplans 포함)
├─ auth.py            # pwdlib(Argon2id)+PyJWT(HS256)+OAuth2PasswordBearer, 로그인 스로틀
├─ schemas.py         # Pydantic 모델 (Token/Admin/Floorplan 포함)
├─ ws.py              # WebSocket 방송부 (서브프로토콜 accept) + 동기 라우터용 방송 예약(enqueue/flush)
├─ assist.py          # 관리자 개입 요청 — 생성(멱등)·로봇 정지/재개·상태 전이
├─ store.py           # 최신값+TTL 보관 (pose·AI 탐지·라이다·비콘) + 수신 횟수/경과
├─ timeutil.py        # now_iso() — 서버가 찍는 타임스탬프 한 형식
├─ robot/state.py     # 로봇 상태 (세션 + 정지 잠금). 값을 생성하지 않는다
└─ routers/           # sessions / assist_requests / robots
                      # / places / beacons / destinations / events / auth / admins
                      # / floorplans(+image) / pose / detections / lidar / beacon_scan
                      # / assist_ingress / event_ingress / session_ingress / map_ingress
                      # — __init__.py에서 보호/공개/인그레스 3그룹
tests/                # pytest — 인증 게이트·로그인·업로드 하드닝·pose/이벤트 인그레스·WS 회귀
tools/                # 운영 점검 스크립트 (pose_rate_check.py — 5Hz 수신율)
```
