import { defineStore } from 'pinia'
import { authApi } from '@/api'

// 角色 → 权限点映射（与后端 backend/api/deps.py 的 PERMISSION_MATRIX 保持一致）
const ROLE_PERMISSIONS = {
  pingpong: [
    'engine:task:create', 'engine:task:manage', 'engine:query:oblivious', 'engine:stats:joint',
    'compliance:rule:manage', 'compliance:report:create', 'compliance:report:view',
    'authz:grant:manage', 'authz:grant:view', 'budget:manage', 'lineage:view',
    'audit:view', 'audit:chain:verify'
  ],
  merchant: [
    'engine:query:oblivious', 'engine:stats:joint', 'compliance:report:create',
    'compliance:report:view', 'authz:grant:view', 'lineage:view'
  ],
  regulator: [
    'engine:stats:joint', 'compliance:report:view', 'authz:grant:view', 'lineage:view',
    'audit:view', 'audit:chain:verify'
  ],
  admin: [
    'engine:task:create', 'engine:task:manage', 'engine:query:oblivious', 'engine:stats:joint',
    'compliance:rule:manage', 'compliance:report:create', 'compliance:report:view',
    'authz:grant:manage', 'authz:grant:view', 'budget:manage', 'lineage:view',
    'audit:view', 'audit:chain:verify'
  ]
}

export const ROLE_LABELS = {
  pingpong: 'PingPong 运营端',
  merchant: '商户端',
  regulator: '监管端',
  admin: '数据安全管理端'
}

export const useUserStore = defineStore('user', {
  state: () => ({
    token: localStorage.getItem('fedshield_token') || '',
    user: JSON.parse(localStorage.getItem('fedshield_user') || 'null'),
    permissions: JSON.parse(localStorage.getItem('fedshield_permissions') || '[]'),
    activeRole: localStorage.getItem('fedshield_role') || 'pingpong'
  }),

  getters: {
    isLoggedIn: (state) => Boolean(state.token),
    role: (state) => state.user?.role || state.activeRole,
    displayName: (state) => state.user?.displayName || state.user?.username || '未登录',
    org: (state) => state.user?.org || ''
  },

  actions: {
    async login(payload) {
      const data = await authApi.login(payload)
      this.token = data.token
      this.user = data.user
      this.permissions = data.permissions || ROLE_PERMISSIONS[data.user.role] || []
      this.activeRole = payload.role || data.user.role
      localStorage.setItem('fedshield_token', this.token)
      localStorage.setItem('fedshield_user', JSON.stringify(this.user))
      localStorage.setItem('fedshield_permissions', JSON.stringify(this.permissions))
      localStorage.setItem('fedshield_role', this.activeRole)
      return data
    },

    async logout() {
      try {
        await authApi.logout()
      } catch (error) {
        // 令牌已失效时忽略后端异常，前端仍然清理本地状态
      }
      this.reset()
    },

    /** 控制台的角色切换器：仅切换视图视角，不改变后端鉴权身份 */
    switchRole(role) {
      this.activeRole = role
      localStorage.setItem('fedshield_role', role)
    },

    hasPermission(permission) {
      if (!permission) return true
      const list = this.permissions.length ? this.permissions : ROLE_PERMISSIONS[this.role] || []
      return list.includes(permission)
    },

    reset() {
      this.token = ''
      this.user = null
      this.permissions = []
      localStorage.removeItem('fedshield_token')
      localStorage.removeItem('fedshield_user')
      localStorage.removeItem('fedshield_permissions')
    }
  }
})
