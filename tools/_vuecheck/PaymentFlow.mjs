
/**
 * 支付智能处理（赛题 A16 · 建设范围一）
 *
 * 接口契约（backend/api/ops.py 的「① 支付智能处理」段落）：
 * - GET  /api/ops/payment/channels        通道池 + 受限目的地 + 重试策略 + 路由权重
 * - POST /api/ops/payment/route-preview   路由预演（候选打分明细与排除原因）
 * - POST /api/ops/payment/process         批量处理（接入→风控→路由→处理→重试→补偿）
 * - GET  /api/ops/payment/orders          订单分页（状态/通道/风险等级/关键字筛选）
 * - GET  /api/ops/payment/orders/<code>   订单详情（含 chain 链路定义）
 * - GET  /api/ops/payment/summary         链路指标（成功率/直通率/重试率/补偿率/拦截率）
 *
 * 项目当前 api 封装（src/api/index.js）尚未包含 ops 接口，为避免改动既有文件，
 * 本页直接使用 axios 实例 request 调用，响应拦截器已统一解包 { code, message, data }。
 */
import { computed, onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
// 仅导入需要以组件对象形式绑定的图标（其余图标在 main.js 已全量全局注册，模板中可直接写标签名）
import { MagicStick, Refresh, RefreshLeft, Search, VideoPlay } from '@element-plus/icons-vue'
import request from '@/api/request'
import ChartBox from '@/components/ChartBox.vue'
import StatCard from '@/components/StatCard.vue'
import { CHART_COLORS, RISK_LEVEL, baseChartOption, formatDuration, formatNumber, formatPercent, formatTime } from '@/utils/format'

const router = useRouter()

/* ---------------- 字典与常量 ---------------- */

/** 订单状态字典（与 backend/models.py PaymentOrder.status 注释一致） */
const ORDER_STATUS = {
  received: { label: '已接入', type: 'info' },
  risk_checked: { label: '风控通过', type: 'primary' },
  routed: { label: '已路由', type: 'primary' },
  processing: { label: '处理中', type: 'primary' },
  success: { label: '支付成功', type: 'success' },
  retrying: { label: '重试后成功', type: 'success' },
  failed: { label: '处理失败', type: 'danger' },
  compensated: { label: '已自动补偿', type: 'warning' },
  blocked: { label: '风控拦截', type: 'danger' },
  manual: { label: '转人工审核', type: 'warning' }
}

const ORDER_STATUS_OPTIONS = Object.entries(ORDER_STATUS).map(([value, meta]) => ({ value, label: meta.label }))

/** 通道健康状态字典 */
const CHANNEL_STATUS = {
  available: { label: '可用', type: 'success' },
  degraded: { label: '降级', type: 'warning' },
  down: { label: '已下线', type: 'danger' }
}

const RISK_OPTIONS = [
  { value: 'low', label: '低风险' },
  { value: 'medium', label: '中风险' },
  { value: 'high', label: '高风险' }
]

/** 地区中文名（后端以地区编码返回，前端做可读映射） */
const REGION_LABEL = {
  GLOBAL: '全球 GLOBAL',
  EU: '欧盟 EU',
  US: '美国 US',
  SEA: '东南亚 SEA',
  ME: '中东 ME',
  AF: '非洲 AF',
  CN: '中国 CN',
  IR: '伊朗 IR',
  KP: '朝鲜 KP',
  SY: '叙利亚 SY',
  CU: '古巴 CU'
}

const CURRENCY_FALLBACK = ['USD', 'EUR', 'CNY', 'SGD']
const DEST_FALLBACK = ['EU', 'US', 'SEA', 'ME', 'AF', 'CN']

/** 链路步骤兜底定义（订单详情接口返回 chain 时优先使用后端定义） */
const CHAIN_FALLBACK = [
  { stage: '接入', label: '交易接入' },
  { stage: '风控', label: 'AI 风控前置' },
  { stage: '路由', label: '智能路由' },
  { stage: '处理', label: '通道处理' },
  { stage: '重试', label: '失败重试' },
  { stage: '补偿', label: '自动补偿' }
]

/** 链路步骤说明（用于 el-steps 的 description） */
const CHAIN_DESC = {
  接入: '统一接单入口，落地订单',
  风控: '风险评分 → 拦截 / 转人工 / 放行',
  路由: '成本·成功率·时效·合规多目标打分',
  处理: '提交清算并跟踪回执',
  重试: '指数退避 + 自动切换备用通道',
  补偿: '改道重发或原路退回'
}

/** 事件阶段 → 链路步骤下标（把事件流映射到 el-steps 的进度） */
const STAGE_INDEX = {
  接入: 0,
  风控: 1,
  处置: 1,
  路由: 2,
  处理: 3,
  成功: 3,
  失败: 3,
  重试: 4,
  补偿: 5
}

/** 已进入终态的订单状态 */
const TERMINAL_STATUSES = ['success', 'retrying', 'failed', 'compensated', 'blocked', 'manual']

/** 路由评分权重元数据（权重值以后端 /payment/channels 返回为准） */
const WEIGHT_META = [
  { key: 'cost', label: '成本', color: '#1f5fd8', desc: '通道费率越低得分越高（按费率 / 1.5% 归一化）' },
  { key: 'success', label: '成功率', color: '#14a37f', desc: '以通道历史清算成功率直接计分' },
  { key: 'latency', label: '时效', color: '#f5a623', desc: '平均到账时延越低得分越高（按时延 / 4000ms 归一化）' },
  { key: 'compliance', label: '合规', color: '#8b5cf6', desc: '合规能力评分：降级通道扣分、高风险订单加权' }
]

const DEFAULT_WEIGHTS = { cost: 0.4, success: 0.3, latency: 0.2, compliance: 0.1 }

/** 评分分解的展示顺序与配色（与后端 breakdown 的键一致） */
const BREAKDOWN_META = [
  { key: 'cost', label: '成本', color: '#1f5fd8' },
  { key: 'success', label: '成功率', color: '#14a37f' },
  { key: 'latency', label: '时效', color: '#f5a623' },
  { key: 'compliance', label: '合规', color: '#8b5cf6' }
]

/* ---------------- 响应式状态 ---------------- */

const loading = ref(false)
const processing = ref(false)
const previewLoading = ref(false)
const detailLoading = ref(false)
const detailVisible = ref(false)

const channels = ref([])
const restricted = ref([])
const retryPolicy = ref({ maxRetry: 2, backoffMs: [200, 600] })
const weights = ref({ ...DEFAULT_WEIGHTS })
const weightSource = ref('default')

const summary = ref({})
const orders = ref([])
const total = ref(0)
const lastBatch = ref(null)
const previewResult = ref(null)
const detail = ref(null)

const processForm = reactive({ count: 12, injectFailureRate: 0.25 })
const previewForm = reactive({ amount: 200000, currency: 'USD', destRegion: 'EU', riskLevel: 'low' })
const query = reactive({ status: '', channel: '', riskLevel: '', keyword: '', page: 1, size: 10 })

/* ---------------- 计算属性 ---------------- */

const currencyOptions = computed(() => {
  const set = new Set()
  channels.value.forEach((item) => (item.currencies || []).forEach((code) => set.add(code)))
  const list = Array.from(set)
  return list.length ? list : CURRENCY_FALLBACK
})

const destOptions = computed(() => {
  const list = []
  channels.value.forEach((item) => {
    ;(item.destinations || []).forEach((code) => {
      if (!list.some((exist) => exist.value === code)) list.push({ value: code, label: destLabel(code) })
    })
  })
  // 受限目的地由后端返回，追加到选项末尾，便于演示「合规前置直接排除」
  ;(restricted.value || []).forEach((code) => {
    if (!list.some((exist) => exist.value === code)) list.push({ value: code, label: `${destLabel(code)}（受限）` })
  })
  if (list.length) return list
  return DEST_FALLBACK.map((code) => ({ value: code, label: destLabel(code) }))
})

const weightItems = computed(() =>
  WEIGHT_META.map((item) => {
    const value = Number(weights.value?.[item.key] ?? DEFAULT_WEIGHTS[item.key]) || 0
    return { ...item, value }
  })
)

const eligibleCount = computed(() =>
  (previewResult.value?.candidates || []).filter((item) => item.eligible).length
)

/** 预演结论说明：选中通道的关键指标 + 被排除通道数量 */
const selectedDesc = computed(() => {
  const result = previewResult.value
  if (!result) return ''
  const candidates = result.candidates || []
  if (!result.selected) {
    const excluded = candidates.filter((item) => !item.eligible)
    const reasons = excluded.slice(0, 3).map((item) => `${item.name || item.code}：${item.reason || '不满足准入条件'}`)
    return `共 ${candidates.length} 条候选全部被排除（币种 / 目的地 / 限额 / 合规限制）。示例：${reasons.join('；') || '无候选通道'}`
  }
  const selected = candidates.find((item) => item.code === result.selected) || {}
  return `按「${weightItems.value.map((item) => `${item.label}${formatPercent(item.value, 0)}`).join(' + ')}」加权，` +
    `该通道综合得分 ${scoreText(selected.score)}，费率 ${formatPercent(selected.feeRate || 0, 2)}、` +
    `历史成功率 ${formatPercent(selected.successRate || 0, 1)}、平均到账 ${formatNumber(selected.avgLatencyMs || 0)} ms；` +
    `另有 ${candidates.filter((item) => !item.eligible).length} 条候选因准入条件被排除。`
})

const chainSteps = computed(() => {
  const chain = detail.value?.chain
  return Array.isArray(chain) && chain.length ? chain : CHAIN_FALLBACK
})

const events = computed(() => (Array.isArray(detail.value?.events) ? detail.value.events : []))

/** 处置结论：把订单状态翻译成一句可读的业务结论 */
const conclusion = computed(() => {
  const order = detail.value || {}
  const status = order.status || ''
  const attempts = Number(order.attempts || 0)
  const reason = order.failureReason || ''
  if (status === 'blocked') {
    return {
      type: 'error',
      title: '处置结论：风控前置拦截，未进入支付链路',
      desc: `风险评分 ${riskText(order.riskScore)}（${riskLabel(order.riskLevel)}）超过拦截阈值，订单被直接拒绝并上链存证，未占用通道资源。${reason ? `处置原因：${reason}。` : ''}`
    }
  }
  if (status === 'manual') {
    return {
      type: 'warning',
      title: '处置结论：转人工合规审核',
      desc: `风险评分 ${riskText(order.riskScore)}（${riskLabel(order.riskLevel)}）超过人工复核阈值，订单已转人工合规岗处理，等待人工放行或拒绝。`
    }
  }
  if (status === 'compensated') {
    return {
      type: 'error',
      title: '处置结论：重试耗尽 → 已触发自动补偿',
      desc: `共尝试 ${attempts} 次（最多重试 ${retryPolicy.value?.maxRetry ?? 2} 次），最终失败原因「${reason || '处理失败'}」；系统已生成补偿单，按「改道重发 / 原路退回」完成兜底，无需人工介入。`
    }
  }
  if (status === 'failed') {
    return {
      type: 'error',
      title: '处置结论：处理失败（已进入补偿流程）',
      desc: `失败原因「${reason || '无可用通道'}」，路由阶段未找到满足币种 / 目的地 / 限额 / 合规要求的通道，订单未提交清算。`
    }
  }
  if (status === 'success' || status === 'retrying') {
    return {
      type: 'success',
      title: status === 'retrying' ? '处置结论：失败重试后成功' : '处置结论：一次直通成功',
      desc: `经「${order.channelName || order.channel || '最优通道'}」清算成功，共尝试 ${attempts} 次，链路耗时 ${formatDuration(order.durationMs || 0)}，路由综合得分 ${scoreText(order.routeScore)}。`
    }
  }
  return {
    type: 'info',
    title: '处置结论：链路处理中',
    desc: `订单当前状态「${statusOf(status).label}」，尚未进入终态，可刷新列表查看最新进度。`
  }
})

/* ---------------- 图表配置 ---------------- */

/** 柱状图：通道路由分布（数量 + 金额） */
const channelOption = computed(() => {
  const list = Array.isArray(summary.value.channelDistribution) ? summary.value.channelDistribution : []
  return baseChartOption({
    tooltip: {
      trigger: 'axis',
      axisPointer: { type: 'shadow' },
      formatter: (params) => {
        const first = Array.isArray(params) ? params[0] : params
        if (!first) return ''
        const bucket = list[first.dataIndex] || {}
        return `${first.name}<br/>承接订单：<b>${formatNumber(bucket.count || 0)}</b> 笔<br/>承接金额：<b>${formatNumber(bucket.amount || 0, 2)}</b>`
      }
    },
    legend: { show: false },
    xAxis: {
      type: 'category',
      data: list.map((item) => item.code || '-'),
      axisLabel: { interval: 0, fontSize: 11, rotate: list.length > 4 ? 20 : 0 }
    },
    yAxis: { type: 'value', name: '订单数', nameTextStyle: { fontSize: 11 } },
    series: [
      {
        name: '承接订单',
        type: 'bar',
        barMaxWidth: 36,
        itemStyle: { borderRadius: [4, 4, 0, 0], color: CHART_COLORS[0] },
        label: { show: true, position: 'top', fontSize: 11 },
        data: list.map((item) => Number(item.count || 0))
      }
    ]
  })
})

/** 环形饼图：订单状态分布
 *  优先使用后端返回的逐状态计数 statusDistribution（精确到 10 个状态）；
 *  若后端未提供该字段，则退化为 4 个合并桶，保证图表始终可渲染。
 */
const STATUS_LABELS = {
  received: '已接入',
  risk_checked: '风控已校验',
  routed: '已路由',
  processing: '处理中',
  success: '成功',
  retrying: '重试后成功',
  failed: '失败',
  compensated: '已自动补偿',
  blocked: '风控拦截',
  manual: '转人工审核'
}
const STATUS_COLORS = {
  success: '#14a37f',
  retrying: '#0ea5e9',
  compensated: '#8b5cf6',
  failed: '#e5484d',
  blocked: '#e5484d',
  manual: '#f5a623'
}

const statusPieOption = computed(() => {
  const distribution = Array.isArray(summary.value.statusDistribution) ? summary.value.statusDistribution : []
  let list = distribution
    .filter((item) => Number(item.count || 0) > 0)
    .map((item) => ({
      name: `${STATUS_LABELS[item.status] || item.status}（${item.status}）`,
      value: Number(item.count || 0),
      itemStyle: STATUS_COLORS[item.status] ? { color: STATUS_COLORS[item.status] } : undefined
    }))

  if (!list.length) {
    list = [
      { name: '成功（含重试后成功）', value: Number(summary.value.successCount || 0) },
      { name: '失败 / 已自动补偿', value: Number(summary.value.failedCount || 0) },
      { name: '风控拦截', value: Number(summary.value.blockedCount || 0) },
      { name: '转人工审核', value: Number(summary.value.manualCount || 0) }
    ].filter((item) => item.value > 0)
  }

  return {
    color: ['#14a37f', '#0ea5e9', '#8b5cf6', '#e5484d', '#f5a623', '#1f5fd8', '#64748b'],
    tooltip: { trigger: 'item', formatter: '{b}：{c} 笔（{d}%）' },
    legend: { bottom: 0, icon: 'circle', itemWidth: 10, itemHeight: 10, textStyle: { fontSize: 12 } },
    series: [
      {
        type: 'pie',
        radius: ['46%', '68%'],
        center: ['50%', '44%'],
        avoidLabelOverlap: true,
        itemStyle: { borderColor: '#fff', borderWidth: 2 },
        label: { formatter: '{b}\n{c} 笔', fontSize: 11 },
        data: list
      }
    ]
  }
})

/* ---------------- 展示辅助函数 ---------------- */

function destLabel(code) {
  if (!code) return '-'
  return REGION_LABEL[code] || code
}

function isRestricted(code) {
  return (restricted.value || []).includes(code)
}

function statusOf(status) {
  return ORDER_STATUS[status] || { label: status || '未知', type: 'info' }
}

function channelStatusOf(status) {
  return CHANNEL_STATUS[status] || { label: status || '未知', type: 'info' }
}

function riskLabel(level) {
  return RISK_LEVEL[level]?.label || level || '未评级'
}

function riskColor(row) {
  return RISK_LEVEL[row?.riskLevel]?.color || '#1f5fd8'
}

function riskText(score) {
  const value = Number(score || 0)
  return value.toFixed(3)
}

/** 百分比数值（StatCard 用 number + precision 展示，避免字符串拼接） */
function percentValue(rate) {
  return Number(((Number(rate || 0) * 100).toFixed(1)))
}

function scoreText(score) {
  return Number(score || 0).toFixed(4)
}

function scorePercent(score) {
  const value = Number(score || 0) * 100
  return Math.min(100, Math.max(0, Number(value.toFixed(1))))
}

function riskPercent(row) {
  const value = Number(row?.riskScore || 0) * 100
  return Math.min(100, Math.max(0, Math.round(value)))
}

/** el-slider 提示文案：故障注入概率 */
function failureTip(value) {
  return `故障注入 ${formatPercent(value || 0, 0)}`
}

/** 评分分解：把 breakdown 转为 4 条小进度条 */
function breakdownItems(row) {
  const breakdown = row?.breakdown || {}
  return BREAKDOWN_META.map((item) => {
    const value = Number(breakdown[item.key] ?? 0)
    return {
      key: item.key,
      label: item.label,
      color: item.color,
      percent: Math.min(100, Math.max(0, Number((value * 100).toFixed(1)))),
      text: value.toFixed(3)
    }
  })
}

/** 预演表格行高亮：选中通道（row-class-name 必须返回字符串） */
function previewRowClass({ row }) {
  return previewResult.value?.selected && row?.code === previewResult.value.selected
    ? 'fs-flow__row--selected'
    : ''
}

/** 事件着色：优先使用后端写入的 level，其次按阶段推断 */
function eventType(item) {
  const level = item?.level
  if (level === 'danger') return 'danger'
  if (level === 'warning') return 'warning'
  const stage = item?.stage || ''
  if (stage === '成功') return 'success'
  if (stage === '失败' || stage === '补偿') return 'danger'
  if (stage === '重试') return 'warning'
  if (stage === '处置') return ['blocked', 'manual'].includes(detail.value?.status) ? 'danger' : 'warning'
  return 'primary'
}

function chainDesc(stage) {
  return CHAIN_DESC[stage] || ''
}

/**
 * 链路步骤状态：把订单状态 + 事件流映射为 el-step 的 status
 * - 风控拦截 / 转人工：链路终止在「风控」步骤（红色）
 * - 已发生的步骤标绿；非终态订单的最后一步标为进行中
 * - 重试 / 补偿只有真实发生时才点亮，避免「未发生也显示已完成」
 */
function stepStatusOf(index) {
  const order = detail.value || {}
  const status = order.status || 'received'
  const occurred = new Set()
  events.value.forEach((item) => {
    const value = STAGE_INDEX[item?.stage]
    if (value !== undefined) occurred.add(value)
  })
  const reached = occurred.size ? Math.max(...occurred) : 0

  if (status === 'blocked' || status === 'manual') {
    if (index === 0) return 'finish'
    return index === 1 ? 'error' : 'wait'
  }
  if (index === 5 && status === 'compensated') return 'error'
  if (!occurred.has(index)) return index > reached ? 'wait' : 'finish'
  if (status === 'failed' && index === reached) return 'error'
  if (!TERMINAL_STATUSES.includes(status) && index === reached) return 'process'
  return 'finish'
}

/* ---------------- 数据加载 ---------------- */

/** 通道池 + 受限目的地 + 重试策略 + 路由权重 */
async function loadChannels() {
  try {
    const data = await request.get('/ops/payment/channels')
    channels.value = data?.channels ?? []
    restricted.value = data?.restricted ?? []
    if (data?.retryPolicy) retryPolicy.value = data.retryPolicy
    if (data?.weights) {
      weights.value = data.weights
      weightSource.value = 'server'
    }
  } catch (error) {
    // 拦截器已提示错误，这里退化为空通道池，页面其余部分仍可用
    channels.value = []
    restricted.value = []
  }
}

/** 链路指标 */
async function loadSummary() {
  try {
    const data = await request.get('/ops/payment/summary')
    summary.value = data || {}
  } catch (error) {
    summary.value = {}
  }
}

/** 订单分页列表 */
async function loadOrders() {
  try {
    const data = await request.get('/ops/payment/orders', {
      params: {
        page: query.page,
        size: query.size,
        status: query.status || undefined,
        channel: query.channel || undefined,
        riskLevel: query.riskLevel || undefined,
        keyword: query.keyword || undefined
      }
    })
    orders.value = data?.list ?? []
    total.value = Number(data?.total || 0)
  } catch (error) {
    orders.value = []
    total.value = 0
  }
}

async function loadAll() {
  loading.value = true
  try {
    // 三个接口互不依赖，并发拉取；单个失败由各自的 catch 兜底
    await Promise.all([loadChannels(), loadSummary(), loadOrders()])
  } finally {
    loading.value = false
  }
}

/* ---------------- 交互 ---------------- */

function handleSearch() {
  query.page = 1
  loadOrders()
}

function handleReset() {
  query.status = ''
  query.channel = ''
  query.riskLevel = ''
  query.keyword = ''
  query.page = 1
  loadOrders()
}

function handleSizeChange() {
  query.page = 1
  loadOrders()
}

// 分页组件清空页号时会传 undefined，这里做保护避免带非法页码请求
function handlePageChange(page) {
  if (!page) return
  loadOrders()
}

/** 批量处理：接入 → 风控 → 智能路由 → 处理 → 重试 → 补偿 */
async function handleProcess() {
  processing.value = true
  try {
    const count = Math.min(50, Math.max(1, Number(processForm.count || 1)))
    const data = await request.post(
      '/ops/payment/process',
      {
        count,
        injectFailureRate: Number(processForm.injectFailureRate || 0)
      },
      { silent: false }
    )
    const batchSummary = data?.summary || {}
    const created = data?.orders ?? []
    lastBatch.value = batchSummary
    ElMessage.success(
      `本次处理 ${formatNumber(created.length || batchSummary.total || 0)} 笔：` +
        `成功 ${formatNumber(batchSummary.successCount || 0)} 笔、` +
        `失败/补偿 ${formatNumber(batchSummary.failedCount || 0)} 笔、` +
        `风控拦截 ${formatNumber(batchSummary.blockedCount || 0)} 笔、` +
        `转人工 ${formatNumber(batchSummary.manualCount || 0)} 笔`
    )
    query.page = 1
    await Promise.all([loadOrders(), loadSummary()])
  } catch (error) {
    // 接口层已弹出失败提示，这里只需保证按钮 loading 复位
  } finally {
    processing.value = false
  }
}

/** 路由预演 */
async function handlePreview() {
  previewLoading.value = true
  try {
    const data = await request.post(
      '/ops/payment/route-preview',
      {
        amount: Number(previewForm.amount || 0),
        currency: previewForm.currency,
        destRegion: previewForm.destRegion,
        riskLevel: previewForm.riskLevel
      },
      { silent: false }
    )
    previewResult.value = data || null
    if (!data?.selected) {
      ElMessage.warning('本次预演没有可用通道：全部候选均被排除，请在表格中查看排除原因')
    }
  } catch (error) {
    previewResult.value = null
  } finally {
    previewLoading.value = false
  }
}

/** 打开订单全链路跟踪抽屉 */
async function openDetail(row) {
  if (!row?.code) {
    ElMessage.warning('订单号缺失，无法查看链路详情')
    return
  }
  detailVisible.value = true
  detailLoading.value = true
  detail.value = row // 先用列表行兜底渲染，避免抽屉出现空白
  try {
    const data = await request.get(`/ops/payment/orders/${encodeURIComponent(row.code)}`)
    detail.value = data || row
  } catch (error) {
    // 详情接口失败时保留列表行数据，链路事件仍可展示
  } finally {
    detailLoading.value = false
  }
}

function goChannels() {
  router.push('/ops/channels')
}

onMounted(() => {
  loadAll()
})
