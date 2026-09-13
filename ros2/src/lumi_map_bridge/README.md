# lumi_map_bridge

Pushes the YDLidar `/scan`, the SLAM pose from TF, and Cartographer's `/map`
from the Raspberry Pi to the Lumi web API over HTTPS.

The browser cannot subscribe to DDS directly — the web app is served from
`http://localhost:8000` while the robot lives on the local network behind a
FastDDS discovery server — so the Pi pushes instead, the same way
`lumi_beacon`'s `beacon_web_bridge` does. The backend fans the payloads out to
browsers over its WebSocket.

```
/scan  ->  POST /api/lidar    5 Hz    polar array, front end draws the points
TF     ->  POST /api/pose     5 Hz    x / y / heading, front end draws the robot
/map   ->  POST /api/map      0.5 Hz  PNG background + map.yaml metadata
```

## Running

Start it alongside the SLAM stack, on the Pi:

```bash
ros2 launch lumi_map_bridge map_web_bridge.launch.py
```

The launch file sets `ROS_DOMAIN_ID=10` and `ROS_DISCOVERY_SERVER=127.0.0.1:11811`
to match `lumi_slam_bringup/launch/cartographer_bringup.launch.py`. **Running the
node without those set silently receives nothing**, because the SLAM stack is
only reachable through the discovery server.

Bring the endpoints up one at a time as the backend implements them:

```bash
ros2 launch lumi_map_bridge map_web_bridge.launch.py send_pose:=false send_map:=false
```

Check the map rendering without a backend — this writes the PNG to disk:

```bash
ros2 launch lumi_map_bridge map_web_bridge.launch.py preview_path:=/tmp/map.png
```

## Parameters

| Parameter | Default | Notes |
| --- | --- | --- |
| `lidar_url` | `http://localhost:8000/api/lidar` | |
| `pose_url` | `http://localhost:8000/api/pose` | |
| `map_url` | `http://localhost:8000/api/map` | |
| `robot_id` | `1` | Sent on `/api/pose` and `/api/map` |
| `send_lidar` / `send_pose` / `send_map` | `true` | Enable each stream |
| `lidar_period_sec` | `0.2` | 5 Hz; the LiDAR itself runs at 10 Hz |
| `pose_period_sec` | `0.2` | 5 Hz |
| `map_period_sec` | `2.0` | Cartographer republishes `/map` at 1 Hz |
| `lidar_bins` | `360` | Slots in the polar array; the API allows up to 1440 |
| `lidar_angle_offset_deg` | `0.0` | Rotates the sweep. 0 is correct here: `base_link -> laser_frame` has no rotation |
| `map_scan_overlay` | `false` | Draw the scan into the PNG. Off: the front end overlays live scan itself |
| `map_pose_marker` | `false` | Draw the robot into the PNG. Off for the same reason |
| `map_crop_to_known` | `true` | Trim the unexplored border. Near no-op under `cartographer_occupancy_grid_node`, which already publishes a tight grid; kept for back ends that publish a fixed canvas |
| `map_scale` | `1` | Nearest-neighbour upscale. `width`/`height`/`resolution` are reported in PNG-pixel terms, so the front end never sees this |
| `map_send_mode` | `base64` | `base64` (JSON) or `multipart` (form upload) |
| `map_skip_unchanged` | `true` | Skip the POST when the PNG is byte-identical |
| `occupied_threshold` | `50` | Occupancy value treated as a wall |
| `map_transient_local` | `true` | Cartographer latches `/map`; set false for a volatile publisher |
| `preview_path` | `""` | Also write the PNG here |
| `stats_period_sec` | `10.0` | Log the delivered rate per stream; 0 disables |
| `request_timeout_sec` | `3.0` | |

Posts are fired on a worker thread and a new one is skipped while the previous
request of that kind is still in flight, so a slow or unreachable backend never
blocks the ROS executor or lets requests pile up.

Each stream holds its own keep-alive `requests.Session`. This matters more than
it looks: a fresh connection per POST costs a full TLS handshake, measured at
**~300 ms** to the deployed server versus **~19 ms** on a reused connection.
Combined with the one-in-flight rule that alone caps a stream near 3 Hz, so
5 Hz is unreachable without connection reuse.

`stats_period_sec` makes the rate verifiable on the robot:

```
[5.0s] lidar 5.00Hz (25 ok) | pose 5.00Hz (25 ok) | map 0.50Hz (1 ok, 9 skipped)
```

`skipped` counts ticks that sent nothing — no data yet, TF missing, an unchanged
map, or a previous request still in flight. A high `skipped` count next to a low
rate means the backend is too slow for the configured period, not that data is
missing.

## Backend contract

Sizes are measured against a live Cartographer session: a 24.4 x 16.1 m canvas
(487 x 321 cells at 0.05 m) that was about 39% explored.

### `POST {lidar_url}` — 5 Hz, ~2.4 KB

```json
{
  "ranges": [1.23, null, 3.45, null],
  "range_max": 12.0,
  "ts": "2026-07-28T03:10:35.810Z"
}
```

`ranges` has `lidar_bins` (360) slots. **Index 0 is the robot's forward
direction and the array runs counter-clockwise**, so index 90 is 90 degrees to
the left. This matches ROS directly — `/scan` reports `angle_min = -pi` with a
positive `angle_increment`, i.e. already counter-clockwise, so no index
reversal is applied.

Empty slots are `null`, never `0.0`: a zero would render as an obstacle
touching the robot. A slot is null when the beam failed (the driver reports
`0.0`, since `invalid_range_is_inf` is false), when it fell outside
`range_min`/`range_max`, or when no beam landed in that slot at all.

**Expect 200-260 of the 360 slots to be filled.** The X4-Pro emits 430 beams
per sweep at 0.84 degree spacing, of which roughly half return a valid reading
indoors, so gaps are normal rather than a fault. Where several beams share a
slot the nearest wins, so obstacles are never hidden by a farther reading.
The sweep spans 360.84 degrees, slightly over a full turn; the overhang wraps
onto slot 0.

### `POST {pose_url}` — 5 Hz, ~94 B

```json
{
  "robot_id": 1,
  "x": -0.054,
  "y": -0.107,
  "heading": 358.03,
  "ts": "2026-07-28T03:10:35.810Z"
}
```

`x`/`y` are raw SLAM map-frame metres — no coordinate conversion is applied.
`heading` is degrees in `[0, 360)`, counter-clockwise, from the `map ->
base_link` transform.

**Nothing is sent while that transform is unavailable**, which is normal for the
first seconds of a run before Cartographer publishes `map -> odom`. The stream
simply starts late rather than sending nulls.

### `POST {map_url}` — 0.5 Hz, ~12 KB JSON (9 KB PNG)

```json
{
  "robot_id": 1,
  "ts": "2026-07-28T03:10:36.993Z",
  "width": 487,
  "height": 321,
  "resolution": 0.05,
  "origin": [-12.1617, -12.2095, 0.0],
  "image_format": "png",
  "image_base64": "iVBORw0KGgo..."
}
```

`width`/`height` are **PNG pixels** and `resolution` is **metres per PNG
pixel**, so the four metadata fields carry `map.yaml` semantics exactly and the
front end never has to know about `map_scale`.

`origin` is `[x, y, theta]`: the **bottom-left** corner of the image in
map-frame metres. **theta is 0** — verified against the live map, whose origin
quaternion is exactly identity, as it always is for Cartographer 2D. The node
logs a warning if it ever sees a non-zero theta.

`origin`, `width` and `height` **change between messages**: Cartographer grows
its grid as new area is explored, so a front end must not cache them.

Row 0 of the PNG is the **top**, while `origin` describes the bottom-left
corner, so converting a map point to a PNG pixel is:

```js
const col = Math.floor((x - origin[0]) / resolution);
const row = height - 1 - Math.floor((y - origin[1]) / resolution);
```

The PNG is the **background only** — three greys, no robot and no scan drawn
in. Those come from `/api/pose` and `/api/lidar` at ten times the rate; baking
a 0.5 Hz snapshot of them into the image would both double-draw and defeat
`map_skip_unchanged`. Set `map_pose_marker` / `map_scan_overlay` to true only
for standalone debugging.

| Pixel | Meaning |
| --- | --- |
| `#FFFFFF` white | free |
| `#000000` black | occupied |
| `#7F7F7F` grey | unknown |

`robot_id` and `ts` are extra beyond the four fields the web team asked for;
ignore them or add them to the schema. With `map_send_mode:=multipart` the
metadata arrives as form values and the PNG as the `image` file part instead of
`image_base64`; scalar fields are plain strings, `origin` is a JSON string
needing a second parse, and a null field arrives as an empty string.

### Not implemented: `X-Device-Key`

Deferred at the web team's request until after integration testing, so an
auth failure cannot be confused with a data problem. Adding it later is a
`headers=` argument on the three POST calls in `map_web_bridge.py`.

## Bandwidth

| Stream | Rate | Size | Throughput |
| --- | --- | --- | --- |
| `/api/lidar` | 5 Hz | 2.4 KB | 12 KB/s |
| `/api/pose` | 5 Hz | 94 B | 0.5 KB/s |
| `/api/map` | 0.5 Hz | 12 KB | 6 KB/s |
| | | | **~19 KB/s** |

The map was 39% explored when measured. A fully explored floor should be
budgeted at roughly 2-3x the PNG size; the backend's 10 MB limit is not a
concern either way.

Sending the occupancy grid as a raw JSON int array instead would be **593 KB per
message** (162,855 cells) — 59x the PNG — which is why the PNG path was chosen.

## Tests

```bash
cd src/lumi_map_bridge && PYTHONPATH=.:$PYTHONPATH python3 -m pytest test/ -q
```

`map_encode.py` holds the pure conversion helpers (grid orientation, polar
binning, scan filtering, TF application, pixel mapping, PNG encoding) so they
are testable without a ROS graph; `map_web_bridge.py` is the node wiring.

## Endpoint status

Last checked against the deployed server:

| Endpoint | Status |
| --- | --- |
| `POST /api/lidar` | **working** — 5.00 Hz sustained, 0 failures. Server-side readback shows 360 slots, ~249 filled, no zeros |
| `POST /api/pose` | **working** — 5.00 Hz sustained, 0 failures. `GET` echoes the robot's pose with `source: "robot"` |
| `POST /api/map` | **404** — not implemented on the backend yet |

The earlier nginx 403 on `/api/lidar` and `/api/detections` has been resolved.

Notes from integration testing:

* **Do not try to verify the publish rate from the server.** The stored `ts` is
  truncated to whole seconds, so 5 Hz and 1 Hz look identical through
  `GET /api/lidar`. `GET /api/pose`'s `count` is also incremented by the
  simulator, not just robot traffic. Use the robot's `stats_period_sec` log.
* A simulator writes to the same pose store and shows up as `source: "mock"`.
  It does not fight the robot: over a 20 s window with the bridge running the
  `source` flipped exactly once, from a stale mock record to `robot`, and stayed.
  A `mock` value with a growing `age_ms` just means the bridge is not running.
* `/api/lidar/` (trailing slash) redirects to `http://localhost:8000/api/lidar`
  — plain **http**, not https. The reverse proxy is missing `X-Forwarded-Proto`.
  Harmless for this bridge, which posts to the exact path, but it would bite a
  browser calling a trailing-slash API path.

## Verifying on the Pi

`ros2 topic list`, `ros2 topic echo /scan` and `ros2 run tf2_ros tf2_echo map
base_link` all come up empty on this Pi — the Fast DDS discovery server does not
hand CLI tools the full graph. **This does not mean SLAM is down.** Endpoint
matching works fine, which is why the bridge receives data normally. Verify by
running the bridge against a local receiver rather than by using the CLI.
