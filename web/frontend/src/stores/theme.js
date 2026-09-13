/** 라이트/다크 테마 — 실제 색은 assets/main.css의 :root / :root[data-theme='dark']에 있고,
 *  여기서는 <html data-theme>만 바꾼다.
 *
 *  첫 값은 index.html의 인라인 스크립트가 이미 정해 뒀다(첫 페인트 전에 실행돼야 흰 화면이
 *  번쩍이지 않기 때문). 그래서 이 스토어는 판단을 다시 하지 않고 그 결과를 읽어 온다 —
 *  같은 규칙을 두 곳에 적으면 언젠가 한쪽만 고쳐진다.
 *
 *  사용자가 한 번 고르면 localStorage에 남고, 그 뒤로는 OS 설정이 바뀌어도 따르지 않는다.
 *  관제 화면을 어느 쪽으로 볼지는 시연자가 정하는 편이 낫다. */
import { defineStore } from 'pinia'

export const THEME_KEY = 'lumi_theme'

export const useThemeStore = defineStore('theme', {
  state: () => ({
    theme: document.documentElement.dataset.theme === 'dark' ? 'dark' : 'light',
  }),
  getters: {
    isDark: (s) => s.theme === 'dark',
  },
  actions: {
    set(theme) {
      this.theme = theme
      document.documentElement.dataset.theme = theme
      try {
        localStorage.setItem(THEME_KEY, theme)
      } catch {
        // 시크릿 모드 등에서 저장이 막혀도 이번 세션의 전환 자체는 막지 않는다
      }
    },
    toggle() {
      this.set(this.isDark ? 'light' : 'dark')
    },
  },
})
