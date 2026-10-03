
import { computed } from 'vue'
import { ElMessage } from 'element-plus'
import { ROLE_LABELS, useUserStore } from '@/store/user'

const userStore = useUserStore()

const ALL_OPTIONS = [
  { value: 'pingpong', short: '平台', label: 'PingPong 运营端（风控/合规全量视图）', tag: 'primary' },
  { value: 'merchant', short: '商户', label: '商户端（交易统计/黑名单查询/合规状态）', tag: 'success' },
  { value: 'regulator', short: '监管', label: '监管端（数据流转日志/合规报告/审计）', tag: 'warning' },
  { value: 'admin', short: '安全', label: '数据安全管理端（权限/预算/规则/审计）', tag: 'danger' }
]

// 视图切换规则：平台运营与数据安全管理员可切换全部角色视图；
// 商户/监管账号仅能使用本角色视图（前端视图切换不改变后端鉴权身份）
const options = computed(() => {
  const role = userStore.user?.role
  if (role === 'pingpong' || role === 'admin') return ALL_OPTIONS
  return ALL_OPTIONS.filter((item) => item.value === role)
})

function onChange(role) {
  userStore.switchRole(role)
  ElMessage.success(`已切换至「${ROLE_LABELS[role] || role}」视图`)
}
