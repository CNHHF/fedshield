/** 通用格式化与状态字典工具 */

/** 时间格式化：支持 ISO 字符串、时间戳 */
export function formatTime(value, withSeconds = true) {
  if (!value) return '-'
  const date = typeof value === 'number' ? new Date(value) : new Date(String(value).replace(' ', 'T'))
  if (Number.isNaN(date.getTime())) return String(value)
  const pad = (n) => String(n).padStart(2, '0')
  const base = `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())} ${pad(date.getHours())}:${pad(
    date.getMinutes()
  )}`
  return withSeconds ? `${base}:${pad(date.getSeconds())}` : base
}

export function formatDate(value) {
  return formatTime(value, false).slice(0, 10)
}

/** 数字千分位 + 指定小数位 */
export function formatNumber(value, precision = 0) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return '-'
  return Number(value).toLocaleString('zh-CN', {
    minimumFractionDigits: precision,
    maximumFractionDigits: precision
  })
}

/** 金额格式化（自动万元/亿元） */
export function formatAmount(value) {
  const num = Number(value || 0)
  if (Math.abs(num) >= 1e8) return `${(num / 1e8).toFixed(2)} 亿元`
  if (Math.abs(num) >= 1e4) return `${(num / 1e4).toFixed(2)} 万元`
  return `${num.toFixed(2)} 元`
}

/** 耗时格式化 */
export function formatDuration(ms) {
  const value = Number(ms || 0)
  if (value < 1000) return `${value.toFixed(0)} ms`
  if (value < 60000) return `${(value / 1000).toFixed(2)} s`
  return `${(value / 60000).toFixed(2)} min`
}

/** 百分比 */
export function formatPercent(value, precision = 1) {
  return `${(Number(value || 0) * 100).toFixed(precision)}%`
}

/* ---------------- 状态字典 ---------------- */

export const TASK_STATUS = {
  pending: { label: '待启动', type: 'info' },
  running: { label: '运行中', type: 'primary' },
  paused: { label: '已暂停', type: 'warning' },
  finished: { label: '已完成', type: 'success' },
  failed: { label: '执行失败', type: 'danger' },
  canceled: { label: '已取消', type: 'info' }
}

export const TASK_TYPE = {
  federated: { label: '联邦学习建模', tech: '联邦学习 + 差分隐私' },
  homomorphic: { label: '同态加密计算', tech: 'Paillier 半同态加密' },
  oblivious: { label: '隐匿查询', tech: '密文域比对 / OPRF' },
  statistics: { label: '联合统计', tech: '同态求和 + 差分隐私' },
  psi: { label: '隐私求交集', tech: 'RSA 盲签名 PSI' }
}

export const GRANT_STATUS = {
  active: { label: '生效中', type: 'success' },
  pending: { label: '待审核', type: 'warning' },
  expired: { label: '已过期', type: 'info' },
  revoked: { label: '已撤销', type: 'danger' }
}

export const REPORT_STATUS = {
  generated: { label: '已生成', type: 'success' },
  generating: { label: '生成中', type: 'primary' },
  failed: { label: '失败', type: 'danger' }
}

export const ALERT_LEVEL = {
  high: { label: '高危', type: 'danger' },
  medium: { label: '中度', type: 'warning' },
  low: { label: '轻度', type: 'info' }
}

export const RISK_LEVEL = {
  high: { label: '高风险', color: '#e5484d' },
  medium: { label: '中风险', color: '#f5a623' },
  low: { label: '低风险', color: '#14a37f' }
}

/** 取字典项，带兜底 */
export function dictOf(dict, key, fallbackLabel = '-') {
  return dict[key] || { label: fallbackLabel, type: 'info' }
}

/** 统一的 ECharts 主题色板 */
export const CHART_COLORS = ['#1f5fd8', '#14a37f', '#f5a623', '#8b5cf6', '#e5484d', '#0ea5e9', '#64748b']

/** ECharts 通用基础配置 */
export function baseChartOption(extra = {}) {
  return {
    color: CHART_COLORS,
    tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
    grid: { left: 46, right: 22, top: 38, bottom: 34, containLabel: true },
    legend: { right: 10, top: 4, icon: 'roundRect', itemWidth: 10, itemHeight: 10, textStyle: { fontSize: 12 } },
    ...extra
  }
}
