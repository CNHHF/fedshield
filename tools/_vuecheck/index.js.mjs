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
      next('/brain')
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
    // 权限不足时回到智能大脑展板（所有角色均可访问）
    next('/brain')
    return
  }
  next()
})

export default router
