import { createRouter, createWebHashHistory } from 'vue-router'
import { useUserStore } from '@/store/user'
import { routes } from './routes'

const router = createRouter({
  // hash 模式：构建产物可直接由 Flask 静态托管，无需服务端 rewrite 配置
  history: createWebHashHistory(),
  routes,
  scrollBehavior: () => ({ top: 0 })
})

router.beforeEach((to, from, next) => {
  const userStore = useUserStore()
  document.title = to.meta?.title ? `${to.meta.title} · FedShield` : 'FedShield 隐私计算平台'

  if (to.meta?.public) {
    if (to.path === '/login' && userStore.isLoggedIn) {
      next('/console')
      return
    }
    next()
    return
  }

  if (!userStore.isLoggedIn) {
    next({ path: '/login', query: { redirect: to.fullPath } })
    return
  }

  if (to.meta?.permission && !userStore.hasPermission(to.meta.permission)) {
    next('/console')
    return
  }
  next()
})

export default router
