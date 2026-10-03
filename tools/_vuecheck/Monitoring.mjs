
/**
 * 智能风控与异常监测（赛题 A16 建设范围二）
 *
 * 数据来源（接口契约见 backend/api/ops.py「② 智能风控与异常监测」）：
 * - GET  /ops/monitoring/rules           规则与统一处置口径
 * - POST /ops/monitoring/detect          执行异常检测（落库并返回汇总）
 * - GET  /ops/monitoring/alerts          实时预警分页列表（等级/动作/状态筛选）
 * - POST /ops/monitoring/alerts/:id/handle  人工确认处置
 * - GET  /ops/monitoring/summary         汇总（含账户/商户风险 Top10）
 *
 * 说明：不使用 src/api/index.js（保持该文件不变），直接经 request 统一封装调用，
 * 以便复用鉴权、统一解包与错误提示；所有返回值均做空值兜底。
 */
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { Cpu, Refresh, RefreshLeft, Search } from '@element-plus/icons-vue'
import request from '@/api/request'
import ChartBox from '@/components/ChartBox.vue'
import StatCard from '@/components/StatCard.vue'
import { baseChartOption, formatAmount, formatTime } from '@/utils/format'

const loading = ref(false)
const detecting = ref(false)
const handling = ref(false)
const updatedAt = ref('')
const scanned = ref(0)

/** 检测参数：默认扫描 600 笔最新交易，与后端 20~2000 的取值区间保持一致 */
const detectForm = reactive({ limit: 600 })

/** 风控汇总（字段与 engine/monitoring.summarize_alerts 对齐，全部做空值兜底） */
const summary = reactive({
  total: 0,
  high: 0,
  medium: 0,
  low: 0,
  amountAtRisk: 0,
  byRule: [],
  byAction: [],
  autoHandledRate: 0,
  manualPendingRate: 0,
  accountRisk: []
})

const rules = ref([])
const actions = ref([])

const query = reactive({ riskLevel: 'all', action: 'all', status: 'all', page: 1, size: 10 })
const alerts = ref([])
const total = ref(0)

const evidenceVisible = ref(false)
const currentAlert = ref(null)
const handleVisible = ref(false)
const handleForm = reactive({ id: null, code: '', ruleName: '', actionLabel: '', action: '' })

const RISK_OPTIONS = [
  { label: '全部等级', value: 'all' },
  { label: '高危', value: 'high' },
  { label: '中危', value: 'medium' },
  { label: '低危', value: 'low' }
]

const STATUS_OPTIONS = [
  { label: '全部状态', value: 'all' },
  { label: '已自动处置', value: 'handled' },
  { label: '待人工确认', value: 'pending' },
  { label: '人工已确认', value: 'confirmed' }
]

/** 状态字典：handled/pending 由自动处置写入，confirmed 由人工确认写入 */
const STATUS_MAP = {
  handled: { label: '已自动处置', type: 'success' },
  pending: { label: '待人工确认', type: 'warning' },
  confirmed: { label: '人工已确认', type: 'success' },
  closed: { label: '已闭环', type: 'info' }
}

/** 处置动作配色：与 engine/monitoring.ACTIONS 口径一致 */
const ACTION_TYPES = { pass: 'success', verify: 'primary', manual: 'warning', block: 'danger' }
const ACTION_LABELS = { pass: '自动放行', verify: '二次验证', manual: '转人工复核', block: '自动拦截' }
const RISK_META = {
  high: { label: '高危', type: 'danger', color: '#e5484d' },
  medium: { label: '中危', type: 'warning', color: '#f5a623' },
  low: { label: '低危', type: 'success', color: '#14a37f' }
}

function riskMeta(level) {
  return RISK_META[level] || { label: level || '-', type: 'info', color: '#94a3b8' }
}

function riskLabel(level) {
  return RISK_META[level]?.label || level || '-'
}

function riskTagType(level) {
  return RISK_META[level]?.type || 'info'
}

function scoreColor(level) {
  return RISK_META[level]?.color || '#94a3b8'
}

function actionTagType(code) {
  return ACTION_TYPES[code] || 'info'
}

function actionLabel(code) {
  return ACTION_LABELS[code] || code || '-'
}

function statusOf(status) {
  return STATUS_MAP[status] || { label: status || '-', type: 'info' }
}

/** 风险分（0~1）转 el-progress 百分比（0~100 整数） */
function scorePercent(score) {
  const value = Number(score || 0) * 100
  return Math.max(0, Math.min(100, Math.round(value)))
}

/** 由分数反推等级（用于账户风险 Top10 的进度条配色） */
function levelOfScore(score) {
  const value = Number(score || 0)
  if (value >= 0.7) return 'high'
  if (value >= 0.4) return 'medium'
  return value > 0 ? 'low' : ''
}

/** 比率转百分比文本；后端可能返回 null，统一兜底为占位符 */
function percentText(value) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return '-'
  return `${(Number(value) * 100).toFixed(1)}%`
}

/* ---------------- KPI ---------------- */

const kpiCards = computed(() => [
  {
    label: '预警总数',
    value: Number(summary.total || 0),
    unit: '条',
    icon: 'Warning',
    color: '#1f5fd8',
    sub: `命中 ${(summary.byRule || []).length} 类检测规则`
  },
  {
    label: '高危预警',
    value: Number(summary.high || 0),
    unit: '条',
    icon: 'CircleCloseFilled',
    color: '#e5484d',
    sub: '风险分 ≥ 0.70，优先处置'
  },
  {
    label: '中危预警',
    value: Number(summary.medium || 0),
    unit: '条',
    icon: 'WarningFilled',
    color: '#f5a623',
    sub: '0.40 ≤ 风险分 < 0.70'
  },
  {
    label: '低危预警',
    value: Number(summary.low || 0),
    unit: '条',
    icon: 'InfoFilled',
    color: '#14a37f',
    sub: '风险分 < 0.40，持续监测'
  },
  {
    label: '涉险金额',
    value: Number(((summary.amountAtRisk || 0) / 10000).toFixed(2)),
    unit: '万元',
    precision: 2,
    icon: 'Money',
    color: '#8b5cf6',
    sub: '命中规则交易的金额合计'
  },
  {
    label: '自动化处置率',
    value: Number(((summary.autoHandledRate || 0) * 100).toFixed(1)),
    unit: '%',
    precision: 1,
    icon: 'MagicStick',
    color: '#0ea5e9',
    sub: '自动放行 + 自动拦截占比'
  },
  {
    label: '待人工比例',
    value: Number(((summary.manualPendingRate || 0) * 100).toFixed(1)),
    unit: '%',
    precision: 1,
    icon: 'UserFilled',
    color: '#e5484d',
    sub: '转人工复核预警占比'
  }
])

/* ---------------- 图表 ---------------- */

/** 命中规则分布：横轴规则名、纵轴预警数量 */
const byRuleOption = computed(() => {
  const rows = summary.byRule || []
  return baseChartOption({
    tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
    legend: { show: false },
    grid: { left: 20, right: 24, top: 30, bottom: 8, containLabel: true },
    xAxis: {
      type: 'category',
      data: rows.map((item) => item.ruleName || item.ruleCode || '-'),
      axisLabel: { interval: 0, fontSize: 11, rotate: rows.length > 4 ? 16 : 0 }
    },
    yAxis: { type: 'value', name: '预警数', minInterval: 1 },
    series: [
      {
        name: '命中预警数',
        type: 'bar',
        barMaxWidth: 36,
        itemStyle: { borderRadius: [4, 4, 0, 0] },
        label: { show: true, position: 'top', fontSize: 11 },
        data: rows.map((item) => Number(item.count || 0))
      }
    ]
  })
})

/** 处置动作分布：环形饼图（自动放行 / 二次验证 / 转人工复核 / 自动拦截） */
const byActionOption = computed(() => {
  const rows = summary.byAction || []
  const actionColor = { 自动放行: '#14a37f', 二次验证: '#1f5fd8', 转人工复核: '#f5a623', 自动拦截: '#e5484d' }
  return baseChartOption({
    tooltip: { trigger: 'item', formatter: '{b}：{c} 条（{d}%）' },
    legend: { bottom: 0, left: 'center', icon: 'circle', itemWidth: 10, itemHeight: 10, textStyle: { fontSize: 12 } },
    series: [
      {
        name: '处置动作分布',
        type: 'pie',
        radius: ['46%', '68%'],
        center: ['50%', '45%'],
        avoidLabelOverlap: true,
        itemStyle: { borderColor: '#fff', borderWidth: 2 },
        label: { formatter: '{b}\n{c} 条', fontSize: 11 },
        data: rows.map((item) => ({
          name: item.action || '未标注',
          value: Number(item.count || 0),
          itemStyle: { color: actionColor[item.action] }
        }))
      }
    ]
  })
})

const accountRisk = computed(() =>
  (summary.accountRisk || [])
    .slice()
    .sort((prev, next) => Number(next.maxScore || 0) - Number(prev.maxScore || 0))
)

/* ---------------- 数据加载 ---------------- */

/** 汇总兜底：直接覆盖 KPI，不依赖接口字段完整（total 为 0 时后端仅返回 4 个字段） */
function applySummary(payload) {
  const data = payload || {}
  Object.assign(summary, {
    total: Number(data.total || 0),
    high: Number(data.high || 0),
    medium: Number(data.medium || 0),
    low: Number(data.low || 0),
    amountAtRisk: Number(data.amountAtRisk || 0),
    byRule: data.byRule || [],
    byAction: data.byAction || [],
    autoHandledRate: Number(data.autoHandledRate || 0),
    manualPendingRate: Number(data.manualPendingRate || 0),
    accountRisk: data.accountRisk || []
  })
  updatedAt.value = formatTime(new Date())
}

async function loadRules() {
  const payload = await request.get('/ops/monitoring/rules')
  rules.value = payload?.rules || []
  actions.value = payload?.actions || []
}

async function loadSummary() {
  applySummary(await request.get('/ops/monitoring/summary'))
}

async function loadAlerts() {
  const payload = await request.get('/ops/monitoring/alerts', {
    params: {
      riskLevel: query.riskLevel,
      action: query.action,
      status: query.status,
      page: query.page,
      size: query.size
    }
  })
  alerts.value = payload?.list || []
  total.value = Number(payload?.total || 0)
}

async function loadAll() {
  loading.value = true
  try {
    // 三个接口相互独立，任一失败不影响其余数据的展示
    await Promise.all([loadRules(), loadSummary(), loadAlerts()])
  } catch (error) {
    // 错误提示已由请求层统一处理，这里仅保证页面渲染不中断
  } finally {
    loading.value = false
  }
}

/** 执行异常检测：后端基于交易数据生成预警并落库 */
async function runDetect() {
  detecting.value = true
  try {
    const payload = await request.post('/ops/monitoring/detect', { limit: detectForm.limit })
    const scannedCount = Number(payload?.scanned || 0)
    const detectedSummary = payload?.summary || {}
    const alertCount = Number(detectedSummary.total || (payload?.alerts || []).length)
    scanned.value = scannedCount
    applySummary(detectedSummary)
    ElMessage.success(`扫描 ${scannedCount} 笔 / 生成预警 ${alertCount} 条`)
    query.page = 1
    // 再拉取落库后的汇总与列表，保证页面与数据库口径一致
    await Promise.all([loadSummary(), loadAlerts()])
  } catch (error) {
    // 检测失败（如无交易数据）已由请求层提示，保持页面原状
  } finally {
    detecting.value = false
  }
}

function handleSearch() {
  query.page = 1
  loadAlerts().catch(() => {})
}

function handleSizeChange() {
  query.page = 1
  loadAlerts().catch(() => {})
}

function resetQuery() {
  query.riskLevel = 'all'
  query.action = 'all'
  query.status = 'all'
  handleSearch()
}

/* ---------------- 证据与处置 ---------------- */

function openEvidence(row) {
  currentAlert.value = row || null
  evidenceVisible.value = true
}

function openHandle(row) {
  if (!row?.id) {
    ElMessage.warning('该预警缺少主键，无法确认处置')
    return
  }
  handleForm.id = row.id
  handleForm.code = row.code || ''
  handleForm.ruleName = row.ruleName || ''
  handleForm.actionLabel = row.actionLabel || actionLabel(row.action)
  handleForm.action = row.action || actions.value[0]?.code || 'manual'
  handleVisible.value = true
}

async function submitHandle() {
  if (!handleForm.id) return
  if (!handleForm.action) {
    ElMessage.warning('请选择处置动作')
    return
  }
  handling.value = true
  try {
    await request.post(`/ops/monitoring/alerts/${handleForm.id}/handle`, {
      status: 'confirmed',
      action: handleForm.action
    })
    ElMessage.success('处置结果已确认')
    handleVisible.value = false
    await Promise.all([loadAlerts(), loadSummary()])
  } catch (error) {
    // 失败提示由请求层统一处理
  } finally {
    handling.value = false
  }
}

onMounted(loadAll)
