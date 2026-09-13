<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'

import { getToken } from '@/services/token'

const CAMERA_WS_URL =
  import.meta.env.VITE_CAMERA_WS_URL ?? 'ws://localhost:8000/ws/camera/view/1'
const BASE_DELAY = 1_000
const MAX_DELAY = 10_000
const STALE_AFTER_MS = 3_000

const imageUrl = ref(null)
const socketConnected = ref(false)
const cameraConnected = ref(false)
const metadata = ref(null)

let socket = null
let reconnectTimer = null
let staleTimer = null
let retries = 0
let stopped = false
let lastFrameAt = 0

const statusText = computed(() => {
  if (cameraConnected.value) return 'LIVE'
  if (socketConnected.value) return '카메라 대기'
  return '재연결 중'
})

const streamInfo = computed(() => {
  const meta = metadata.value
  if (!meta) return null
  return `${meta.width}×${meta.height} · ${meta.fps} FPS`
})

function replaceFrame(buffer) {
  const nextUrl = URL.createObjectURL(new Blob([buffer], { type: 'image/jpeg' }))
  const previousUrl = imageUrl.value
  imageUrl.value = nextUrl
  if (previousUrl) requestAnimationFrame(() => URL.revokeObjectURL(previousUrl))

  lastFrameAt = Date.now()
  cameraConnected.value = true
}

function connect() {
  const token = getToken()
  if (!token || stopped) return

  socket = new WebSocket(CAMERA_WS_URL, ['bearer', token])
  socket.binaryType = 'arraybuffer'

  socket.onopen = () => {
    retries = 0
    socketConnected.value = true
  }

  socket.onmessage = (event) => {
    if (typeof event.data === 'string') {
      const message = JSON.parse(event.data)
      if (message.type === 'camera_status') {
        cameraConnected.value =
          message.online && message.last_frame_age_ms != null && lastFrameAt > 0
        metadata.value = message.metadata
      }
      return
    }
    replaceFrame(event.data)
  }

  socket.onclose = (event) => {
    socket = null
    socketConnected.value = false
    cameraConnected.value = false

    if (event.code === 1008) {
      window.dispatchEvent(new CustomEvent('auth:expired'))
      return
    }
    scheduleReconnect()
  }

  socket.onerror = () => socket?.close()
}

function scheduleReconnect() {
  if (stopped) return
  const delay = Math.min(BASE_DELAY * 2 ** retries, MAX_DELAY)
  retries += 1
  clearTimeout(reconnectTimer)
  reconnectTimer = setTimeout(connect, delay)
}

onMounted(() => {
  stopped = false
  connect()
  staleTimer = setInterval(() => {
    if (lastFrameAt > 0 && Date.now() - lastFrameAt > STALE_AFTER_MS) {
      cameraConnected.value = false
    }
  }, 1_000)
})

onBeforeUnmount(() => {
  stopped = true
  clearTimeout(reconnectTimer)
  clearInterval(staleTimer)
  socket?.close()
  if (imageUrl.value) URL.revokeObjectURL(imageUrl.value)
})
</script>

<template>
  <section class="card">
    <div class="camera-header">
      <h3>카메라 · 전방</h3>
      <span class="camera-status" :class="{ live: cameraConnected }">{{ statusText }}</span>
    </div>

    <div class="camera-frame">
      <img v-if="imageUrl" :src="imageUrl" alt="로봇 전방 카메라" />
      <div v-if="!cameraConnected" class="camera-overlay">
        <p>{{ socketConnected ? '로봇 카메라 수신 대기 중' : '카메라 서버 연결 중' }}</p>
        <span v-if="streamInfo">{{ streamInfo }}</span>
      </div>
    </div>
  </section>
</template>

<style scoped>
.camera-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.camera-header h3 {
  margin: 0;
}
.camera-status {
  padding: 3px 8px;
  border-radius: 999px;
  background: var(--chip-bg);
  color: var(--chip-text);
  font-size: 10.5px;
  font-weight: 700;
}
.camera-status.live {
  background: var(--live-tint);
  color: var(--live-text);
}
/* 프레임과 그 위 오버레이는 두 테마에서 다 어둡다 — 영상이 들어갈 자리라 밝히지 않는다 */
.camera-frame {
  position: relative;
  overflow: hidden;
  aspect-ratio: 4 / 3;
  margin-top: 12px;
  border-radius: 8px;
  background: #2b2925;
}
.camera-frame img {
  width: 100%;
  height: 100%;
  display: block;
  object-fit: contain;
}
.camera-overlay {
  position: absolute;
  inset: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 5px;
  background: rgba(43, 41, 37, 0.78);
  color: #ddd8ce;
}
.camera-overlay p {
  margin: 0;
  font-size: 13px;
  font-weight: 600;
}
.camera-overlay span {
  color: #aaa49a;
  font-size: 11px;
}
</style>
