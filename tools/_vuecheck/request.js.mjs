import axios from 'axios'
import { ElMessage, ElMessageBox } from 'element-plus'

// 统一请求封装：注入 JWT、统一解包 { code, message, data }、统一错误提示
const service = axios.create({
  baseURL: import.meta.env.VITE_API_BASE || '/api',
  timeout: 120000 // 联邦学习/密文比对等计算任务耗时较长
})

service.interceptors.request.use((config) => {
  const token = localStorage.getItem('fedshield_token')
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  config.headers['X-Request-Id'] = `req-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`
  return config
})

service.interceptors.response.use(
  (response) => {
    // 文件流（导出/下载）直接返回 Blob
    if (response.config.responseType === 'blob') {
      return response
    }
    const payload = response.data || {}
    if (payload.code === undefined) {
      return payload
    }
    if (payload.code !== 0) {
      ElMessage.error(payload.message || '请求失败')
      return Promise.reject(new Error(payload.message || '请求失败'))
    }
    return payload.data
  },
  (error) => {
    const status = error.response && error.response.status
    let payload = (error.response && error.response.data) || {}
    // 后端返回非 JSON（例如代理层 500 的 HTML 页面）时，给出可操作的提示
    if (typeof payload === 'string') {
      payload = {
        message:
          status === 500
            ? '后端未响应或内部异常（HTTP 500）：请确认后端已启动（python run.py），并查看后端控制台报错'
            : `请求失败（HTTP ${status}）`
      }
    }
    // 静默请求（如顶部状态栏的后台轮询）不弹提示，避免打扰用户
    if (error.config && error.config.silent) {
      return Promise.reject(error)
    }
    if (status === 401) {
      localStorage.removeItem('fedshield_token')
      localStorage.removeItem('fedshield_user')
      ElMessageBox.alert(
        payload.message || '登录状态已失效，请重新登录（令牌可能已过期或已加入黑名单）',
        '身份认证',
        { type: 'warning', confirmButtonText: '重新登录' }
      ).finally(() => {
        window.location.hash = '#/login'
      })
    } else if (status === 403) {
      ElMessage.error(payload.message || '权限不足：当前角色无该操作权限')
    } else if (status === 429) {
      ElMessage.error(payload.message || '触发异常行为熔断，账号已临时锁定')
    } else if (error.code === 'ECONNABORTED') {
      ElMessage.error('请求超时：隐私计算任务耗时较长，请稍后在任务管理中查看结果')
    } else {
      ElMessage.error(payload.message || error.message || '网络异常，请检查后端服务是否已启动')
    }
    return Promise.reject(error)
  }
)

export default service
