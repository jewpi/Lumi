<script setup>
import { ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { useAuthStore } from '@/stores/auth'

const auth = useAuthStore()
const route = useRoute()
const router = useRouter()

const username = ref('')
const password = ref('')
const error = ref('')
const busy = ref(false)

async function submit() {
  if (busy.value) return
  busy.value = true
  error.value = ''
  try {
    await auth.login(username.value.trim(), password.value)
    const back = typeof route.query.redirect === 'string' ? route.query.redirect : '/'
    router.push(back)
  } catch (e) {
    const status = e.response?.status
    if (status === 401) error.value = '아이디 또는 비밀번호가 올바르지 않습니다'
    else if (status === 429) error.value = e.response.data?.detail ?? '로그인 시도가 너무 많습니다. 잠시 후 다시 시도하세요.'
    else error.value = '로그인에 실패했습니다. 서버 상태를 확인하세요.'
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <div class="login-wrap">
    <form class="login-card" @submit.prevent="submit">
      <div class="brand">
        <span class="wordmark">Lumi</span>
        <span class="tag mono">CONTROL</span>
      </div>
      <h2>관리자 로그인</h2>
      <p class="hint">기관 관리자 계정으로 로그인해야 관제·도면 관리를 이용할 수 있습니다</p>

      <label>
        아이디
        <input v-model.trim="username" autocomplete="username" required autofocus />
      </label>
      <label>
        비밀번호
        <input v-model="password" type="password" autocomplete="current-password" required />
      </label>

      <p v-if="error" class="err" role="alert">{{ error }}</p>

      <button type="submit" :disabled="busy">{{ busy ? '로그인 중…' : '로그인' }}</button>
    </form>
  </div>
</template>

<style scoped>
.login-wrap {
  min-height: calc(100vh - 40px);
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 20px;
}
.login-card {
  width: 340px;
  background: var(--card);
  border: 1px solid var(--line);
  border-radius: 14px;
  padding: 28px 26px 26px;
  box-shadow: 0 10px 30px rgba(23, 22, 20, 0.08);
}
.brand {
  display: flex;
  align-items: baseline;
  gap: 8px;
  margin-bottom: 14px;
}
.wordmark {
  font-size: 20px;
  font-weight: 700;
  letter-spacing: -0.01em;
}
.tag {
  font-size: 9.5px;
  color: var(--muted);
  letter-spacing: 0.12em;
  border-left: 1px solid var(--line);
  padding-left: 8px;
}
h2 {
  margin: 0 0 4px;
  font-size: 17px;
}
.hint {
  margin: 0 0 18px;
  font-size: 12px;
  color: var(--sub);
  line-height: 1.5;
}
label {
  display: flex;
  flex-direction: column;
  gap: 5px;
  font-size: 12px;
  color: var(--sub);
  margin-bottom: 12px;
}
input {
  font: inherit;
  padding: 9px 11px;
  border: 1px solid var(--field);
  border-radius: 7px;
  background: var(--surface);
}
input:focus {
  outline: none;
  border-color: var(--amber);
  box-shadow: 0 0 0 3px var(--amber-tint);
}
.err {
  margin: 0 0 12px;
  font-size: 12px;
  color: var(--danger);
}
button {
  width: 100%;
  padding: 10px 0;
  font: inherit;
  font-weight: 700;
  color: var(--on-ink);
  background: var(--ink);
  border: 1px solid var(--ink);
  border-radius: 8px;
  cursor: pointer;
}
button:hover:not(:disabled) {
  background: var(--ink-strong);
}
button:disabled {
  opacity: 0.6;
  cursor: default;
}
</style>
