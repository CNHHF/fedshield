
/**
 * 报告预览（对应设计文档图 22，Card 分区展示）
 *
 * 渲染策略：
 * - 后端 dataActivities / subjectRights 的字段可能随报告类型变化（不同法规关注点不同），
 *   因此优先使用后端返回的 columns 定义，其次由首行数据的键动态推断列，最后回退到常见字段，
 *   保证「字段缺失不报错、字段新增能展示」。
 * - conclusion 内部结构做多形态兼容（字符串数组 / 对象数组），避免出现 [object Object]。
 */
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { ArrowLeft, Download, Refresh } from '@element-plus/icons-vue'
import { complianceApi } from '@/api'
import { REPORT_STATUS, formatNumber, formatPercent, formatTime } from '@/utils/format'
import { downloadResponse } from '@/utils/download'
import StatCard from '@/components/StatCard.vue'

const route = useRoute()
const router = useRouter()

const loading = ref(false)
const downloading = ref(false)
const detail = ref(null)

/** 常见字段的中文表头与兜底列定义（键名对齐后端 compliance/report.py 的实际输出） */
const FIELD_LABELS = {
  dataType: '数据类型',
  type: '类型',
  name: '项目',
  targetRegion: '跨境目的地',
  destination: '跨境目的地',
  region: '地区',
  count: '笔数',
  txCount: '笔数',
  records: '记录数',
  amount: '金额(元)',
  cipher: '加密方式',
  encryption: '加密方式',
  level: '数据分级',
  compliance: '合规状态',
  partner: '接收方',
  purpose: '使用目的',
  right: '权利类型',
  requestType: '权利类型',
  requestCount: '请求数',
  received: '收到请求',
  responded: '已响应',
  responseRate: '响应率',
  avgHours: '平均响应时长(小时)',
  status: '状态',
  remark: '备注'
}

// 兜底列顺序与后端输出字段顺序一致（dataActivities / subjectRights）
const ACTIVITY_FALLBACK = ['dataType', 'destination', 'level', 'count', 'amount', 'cipher', 'compliance']
const SUBJECT_RIGHT_FALLBACK = ['requestType', 'received', 'responded', 'responseRate', 'status']

const dataActivities = computed(() => detail.value?.dataActivities ?? [])
const subjectRights = computed(() => detail.value?.subjectRights ?? [])
const conclusion = computed(() => detail.value?.conclusion ?? {})
const basicInfo = computed(() => detail.value?.basicInfo ?? {})

const conclusionIssues = computed(() => normalizeList(conclusion.value?.issues))
const conclusionSuggestions = computed(() => normalizeList(conclusion.value?.suggestions))

const periodText = computed(() => {
  const period = detail.value?.period
  const start = detail.value?.periodStart ?? period?.start ?? period?.[0]
  const end = detail.value?.periodEnd ?? period?.end ?? period?.[1]
  if (!start && !end) return '-'
  return `${formatTime(start, false)} ~ ${formatTime(end, false)}`
})

/** 基础信息中的额外字段（basicInfo 里除已展示项外的键值对） */
const basicExtra = computed(() => {
  const skip = ['createdBy', 'code', 'typeName', 'periodStart', 'periodEnd']
  return Object.entries(basicInfo.value || {})
    .filter(([key, value]) => !skip.includes(key) && value !== null && value !== undefined && value !== '')
    .slice(0, 6)
    .map(([key, value]) => ({ key, label: FIELD_LABELS[key] || key, value: textOf(value) }))
})

const activityColumns = computed(() =>
  buildColumns(dataActivities.value, detail.value?.activityColumns, ACTIVITY_FALLBACK)
)
const subjectRightColumns = computed(() =>
  buildColumns(subjectRights.value, detail.value?.subjectRightColumns, SUBJECT_RIGHT_FALLBACK)
)

/** 关键指标卡片：后端 metrics 为嵌套统计对象，逐项取数并做空值兜底 */
const metricCards = computed(() => {
  const metrics = detail.value?.metrics ?? {}
  const tx = metrics.transactions ?? {}
  const tasks = metrics.tasks ?? {}
  const audit = metrics.audit ?? {}
  const alerts = metrics.alerts ?? {}
  const transfer = metrics.transfer ?? {}
  const cards = []
  if (tx.count !== undefined) {
    cards.push({
      label: '跨境交易笔数',
      value: Number(tx.count || 0),
      unit: '笔',
      icon: 'Tickets',
      color: '#1f5fd8',
      sub: tx.amount !== undefined ? `金额合计 ${formatNumber(tx.amount, 2)} 元` : ''
    })
  }
  if (tasks.total !== undefined) {
    cards.push({
      label: '隐私计算任务',
      value: Number(tasks.total || 0),
      unit: '个',
      icon: 'Cpu',
      color: '#8b5cf6',
      sub: `已完成 ${Number(tasks.finished || 0)} 个`
    })
  }
  if (transfer.complianceRate !== undefined) {
    // 后端 complianceRate 为 0-1 小数，统一按百分比展示
    cards.push({
      label: '跨境传输合规通过率',
      value: formatPercent(transfer.complianceRate, 2),
      unit: '',
      icon: 'CircleCheck',
      color: '#14a37f',
      sub: `被阻断 ${Number(transfer.denied || 0)} 次`
    })
  }
  if (alerts.open !== undefined) {
    cards.push({
      label: '未闭环合规预警',
      value: Number(alerts.open || 0),
      unit: '条',
      icon: 'Warning',
      color: Number(alerts.high || 0) ? '#e5484d' : '#f5a623',
      sub: `高危 ${Number(alerts.high || 0)} 条`
    })
  }
  if (audit.total !== undefined) {
    cards.push({
      label: '审计日志',
      value: Number(audit.total || 0),
      unit: '条',
      icon: 'Files',
      color: '#0ea5e9',
      sub: ''
    })
  }
  return cards
})

function textOf(value) {
  if (value === null || value === undefined) return '-'
  if (typeof value === 'object') {
    // 兜底：对象类型字段序列化为可读文本，避免渲染成 [object Object]
    if (Array.isArray(value)) return value.map((item) => textOf(item)).join('、')
    return Object.entries(value)
      .map(([key, item]) => `${FIELD_LABELS[key] || key}：${textOf(item)}`)
      .join('；')
  }
  return String(value)
}

function cellText(value) {
  return textOf(value)
}

function normalizeList(value) {
  if (!value) return []
  if (Array.isArray(value)) return value.filter((item) => item !== null && item !== undefined)
  if (typeof value === 'string') return [value]
  return Object.values(value)
}

/** 依据后端列定义 / 首行数据键 / 兜底字段生成表格列 */
function buildColumns(rows, apiColumns, fallback) {
  if (Array.isArray(apiColumns) && apiColumns.length) {
    return apiColumns.map((item) => {
      if (typeof item === 'string') return { prop: item, label: FIELD_LABELS[item] || item }
      const prop = item.prop || item.key || item.field
      return { prop, label: item.label || FIELD_LABELS[prop] || prop, width: item.width }
    })
  }
  const first = rows?.[0]
  if (first && typeof first === 'object') {
    const keys = Object.keys(first)
    if (keys.length) {
      return keys.map((key) => ({ prop: key, label: FIELD_LABELS[key] || key }))
    }
  }
  return fallback.map((key) => ({ prop: key, label: FIELD_LABELS[key] || key }))
}

function statusOf(status) {
  return REPORT_STATUS[status] || { label: status || '未知', type: 'info' }
}

function issueTitle(item) {
  if (typeof item === 'string') return item
  return item?.title || item?.rule || item?.name || '合规问题'
}

function issueDesc(item) {
  if (typeof item === 'string') return ''
  const level = item?.level ? `风险等级：${item.level}。` : ''
  return `${level}${item?.detail || item?.message || item?.description || item?.rectification || ''}`
}

function issueAlertType(item) {
  const level = String((typeof item === 'object' ? item?.level : '') || '').toLowerCase()
  if (['high', 'p1', '严重', '高'].includes(level)) return 'error'
  if (['medium', 'p2', '中'].includes(level)) return 'warning'
  return 'info'
}

function goBack() {
  router.push('/compliance/reports')
}

async function onDownload() {
  const id = detail.value?.id || route.params.id
  if (!id) {
    ElMessage.warning('报告 ID 缺失，无法下载')
    return
  }
  downloading.value = true
  try {
    const response = await complianceApi.downloadReport(id)
    downloadResponse(response, `${detail.value?.code || 'compliance-report'}.md`)
    ElMessage.success('报告下载已开始')
  } catch (error) {
    // 请求拦截器已统一提示
  } finally {
    downloading.value = false
  }
}

async function load() {
  const id = route.params.id
  if (!id) {
    ElMessage.warning('缺少报告 ID，无法加载')
    return
  }
  loading.value = true
  try {
    detail.value = (await complianceApi.reportDetail(id)) ?? null
  } catch (error) {
    detail.value = null
  } finally {
    loading.value = false
  }
}

onMounted(load)
