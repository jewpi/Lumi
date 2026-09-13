import { createRouter, createWebHistory } from 'vue-router'

import { getToken } from '@/services/token'

const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes: [
    { path: '/login', name: 'login', component: () => import('@/views/LoginView.vue'), meta: { public: true } },
    { path: '/', name: 'dashboard', component: () => import('@/views/DashboardView.vue') },
    { path: '/places', name: 'places', component: () => import('@/views/PlacesView.vue') },
    { path: '/events', name: 'events', component: () => import('@/views/EventsView.vue') },
    { path: '/admins', name: 'admins', component: () => import('@/views/AdminsView.vue') },
    // 없어진 화면(구 /pedestrians)을 북마크해 둔 사람이 헤더만 뜨는 빈 페이지를 보지 않게
    { path: '/:pathMatch(.*)*', redirect: '/' },
  ],
})

// 전체 로그인 게이트 — 공개 라우트(/login) 외에는 토큰 필수.
// 토큰의 실제 유효성은 백엔드가 판정하고, 만료 시 401/1008 → auth:expired로 정리된다.
router.beforeEach((to) => {
  const authed = !!getToken()
  if (!to.meta.public && !authed) {
    return { name: 'login', query: to.fullPath === '/' ? {} : { redirect: to.fullPath } }
  }
  if (to.name === 'login' && authed) return { path: '/' }
})

export default router
