<script setup>
// 관리자 계정 관리 — 목록·생성·삭제. 공개 회원가입 없음(관리자만 관리자를 만든다).
import { onMounted, reactive, ref } from 'vue'
import { useAuthStore } from '@/stores/auth'
import { createAdmin, deleteAdmin, getAdmins } from '@/services/api'

const auth = useAuthStore()
const list = ref([])
const form = reactive({ username: '', password: '' })
const msg = ref('')
const isErr = ref(false)
const busy = ref(false)

async function load() {
  list.value = await getAdmins()
}
onMounted(load)

function note(text, err = false) {
  msg.value = text
  isErr.value = err
}

async function save() {
  if (!form.username.trim()) return note('아이디를 입력하세요', true)
  if (form.password.length < 12) return note('비밀번호는 12자 이상이어야 합니다', true)
  busy.value = true
  try {
    const a = await createAdmin({ username: form.username.trim(), password: form.password })
    note(`'${a.username}' 관리자를 만들었습니다`)
    Object.assign(form, { username: '', password: '' })
    await load()
  } catch (e) {
    note(
      e.response?.status === 409
        ? '이미 존재하는 아이디입니다'
        : (e.response?.data?.detail ?? '생성에 실패했습니다'),
      true,
    )
  } finally {
    busy.value = false
  }
}

async function remove(a) {
  if (!confirm(`'${a.username}' 관리자를 삭제할까요?\n삭제 즉시 해당 계정의 로그인이 무효화됩니다.`)) return
  try {
    await deleteAdmin(a.id)
    note(`'${a.username}' 삭제 완료`)
    await load()
  } catch (e) {
    note(e.response?.data?.detail ?? '삭제할 수 없습니다', true)
  }
}
</script>

<template>
  <div class="two">
    <section class="card">
      <h3>관리자 계정</h3>
      <table>
        <thead>
          <tr><th>ID</th><th>아이디</th><th>생성일</th><th></th></tr>
        </thead>
        <tbody>
          <tr v-for="a in list" :key="a.id">
            <td class="mono">{{ a.id }}</td>
            <td>
              {{ a.username }}
              <span v-if="a.id === auth.user?.id" class="me-badge">나</span>
            </td>
            <td class="mono">{{ a.created_at ?? '—' }}</td>
            <td>
              <a
                v-if="a.id !== auth.user?.id"
                href="#"
                class="danger-link"
                @click.prevent="remove(a)"
              >삭제</a>
              <span v-else class="muted" title="자기 자신은 삭제할 수 없습니다">—</span>
            </td>
          </tr>
        </tbody>
      </table>
      <p class="muted small">
        자기 자신·마지막 관리자는 삭제할 수 없습니다. 삭제된 계정의 토큰은 즉시 무효화됩니다.
      </p>
    </section>

    <section class="card form">
      <h3>관리자 추가</h3>
      <p class="muted small">공개 회원가입은 없습니다 — 관리자만 새 관리자를 만들 수 있습니다.</p>
      <label>아이디
        <input v-model="form.username" placeholder="예) manager2" maxlength="50" />
      </label>
      <label>비밀번호 (12자 이상)
        <input v-model="form.password" type="password" autocomplete="new-password" />
      </label>
      <p v-if="msg" :class="isErr ? 'err' : 'ok-msg'">{{ msg }}</p>
      <div class="btns">
        <button :disabled="busy" @click="save">{{ busy ? '생성 중…' : '관리자 생성' }}</button>
      </div>
    </section>
  </div>
</template>

<style scoped>
.two {
  display: grid;
  grid-template-columns: 1.6fr 1fr;
  gap: 16px;
  align-items: start;
}
.me-badge {
  display: inline-block;
  margin-left: 6px;
  padding: 1px 7px;
  font-size: 10.5px;
  font-weight: 700;
  color: var(--ink);
  background: var(--amber-tint);
  border: 1px solid var(--amber-tint-line);
  border-radius: 999px;
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
@media (max-width: 900px) {
  .two {
    grid-template-columns: 1fr;
  }
}
</style>
