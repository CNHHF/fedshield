
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { Files, MagicStick, Refresh, Select, VideoPlay } from '@element-plus/icons-vue'
import request from '@/api/request'
import ChartBox from '@/components/ChartBox.vue'
import StatCard from '@/components/StatCard.vue'
import { baseChartOption, formatAmount, formatDuration, formatPercent, formatTime } from '@/utils/format'

/** 统一审核结论口径（与后端 review.DECISION_LABELS 一致） */
const DECISION_LABELS = { approve: '通过', reject: '拒绝', manual: '转人工' }
const DECISION_TAG = { approve: 'success', reject: 'danger', manual: 'warning' }
/** 统一风险标签体系（与后端 review.RISK_TAGS 一致） */
const RISK_LABELS = { high: '高风险', medium: '中风险', low: '低风险' }
const RISK_TAG = { high: 'danger', medium: 'warning', low: 'success' }
/** 风险等级筛选项 */
const RISK_LEVELS = [
  { value: 'high', label: '高风险' },
  { value: 'medium', label: '中风险' },
  { value: 'low', label: '低风险' }
]
/** 分歧类型字典（none 表示一致） */
const DIFF_TYPES = [
  { value: 'false_negative', label: '漏放（AI 通过→人工拒绝）' },
  { value: 'false_positive', label: '误拦（AI 拒绝→人工通过）' },
  { value: 'both_manual', label: '均转人工' }
]
const DIFF_LABELS = {
  none: '一致',
  false_negative: '漏放',
  false_positive: '误拦',
  both_manual: '均转人工'
}
/** 规则权重中文说明（与后端规则引擎字段名一一对应） */
const RULE_LABELS = [
  { key: 'sanctionHit', label: '命中制裁清单', desc: 'OFAC / 联合国制裁清单命中，强证据' },
  { key: 'highRiskRegion', label: '高风险地区', desc: '交易目的地属高风险国家或地区' },
  { key: 'amountAnomaly', label: '金额异常', desc: '单笔金额显著高于同层级商户均值' },
  { key: 'velocity', label: '拆分交易', desc: '1 小时内多笔交易，存在化整为零特征' },
  { key: 'identityMismatch', label: '身份不一致', desc: 'KYC 身份信息与结算账户不一致' },
  { key: 'newMerchant', label: '新商户', desc: '商户入驻时间过短，历史数据不足' },
  { key: 'nightTrade', label: '夜间交易', desc: '夜间交易占比偏高，行为异常' }
]
/** 优化前后对比指标方向：up 表示越大越好，down 表示越小越好 */
const COMPARE_METRICS = [
  { key: 'agreementRate', label: '核心一致性', dir: 'up', percent: true },
  { key: 'overallAlignmentRate', label: '总体协同率', dir: 'up', percent: true },
  { key: 'automationRate', label: '自动化率', dir: 'up', percent: true },
  { key: 'manualTransferRate', label: '转人工比例', dir: 'down', percent: true },
  { key: 'kappa', label: "Cohen's Kappa", dir: 'up', percent: false },
  { key: 'falseNegativeCount', label: '漏放笔数', dir: 'down', percent: false },
  { key: 'falsePositiveCount', label: '误拦笔数', dir: 'down', percent: false }
]

const loading = ref(false)
const running = ref(false)
const optimizing = ref(false)
const applying = ref(false)

const batchCount = ref(20)
const batchFilter = ref('all')
const batches = ref([])
const policy = ref({})
const standards = ref({})
const metrics = ref({})
const optimizations = ref([])
const optimizeResult = ref(null)
const drawerVisible = ref(false)
const current = ref(null)

const query = reactive({
  batchCode: 'all',
  agreed: 'all',
  diffType: 'all',
  riskLevel: 'all',
  page: 1,
  size: 10
})
const records = reactive({ list: [], total: 0, page: 1, size: 10 })

/* ---------------- 取值兜底工具（接口缺字段时不出现 undefined 报错） ---------------- */

function valueOf(source, key, fallback = 0) {
  const value = (source || {})[key]
  return value === null || value === undefined ? fallback : value
}

function percentValue(rate, precision = 1) {
  return Number((Number(rate || 0) * 100).toFixed(precision))
}

function cellValue(aiKey, humanKey) {
  const matrix = metrics.value.confusionMatrix || {}
  const row = matrix[aiKey] || {}
  return Number(row[humanKey] || 0)
}

function decisionLabel(key) {
  return DECISION_LABELS[key] || key || '-'
}

function decisionTagType(key) {
  return DECISION_TAG[key] || 'info'
}

function riskLabel(key) {
  return RISK_LABELS[key] || key || '-'
}

/** 风险等级 → 标签色：未知取值回退为 info，避免空标签 */
function riskTagType(key) {
  return RISK_TAG[key] || 'info'
}

function diffLabel(key) {
  return DIFF_LABELS[key] || key || '-'
}

function diffTagType(key) {
  if (key === 'false_negative') return 'danger'
  if (key === 'false_positive') return 'warning'
  return 'info'
}

function severityLabel(key) {
  if (key === 'high') return '高'
  if (key === 'medium') return '中'
  if (key === 'low') return '低'
  return '-'
}

function confidencePercent(confidence) {
  return Math.max(0, Math.min(100, Math.round(Number(confidence || 0) * 100)))
}

function confidenceColor(confidence) {
  const value = Number(confidence || 0)
  if (value >= 0.8) return '#14a37f'
  if (value >= 0.6) return '#1f5fd8'
  return '#f5a623'
}

function scorePercent(score) {
  return Math.max(0, Math.min(100, Math.round(Number(score || 0) * 100)))
}

function scoreColor(score) {
  const value = Number(score || 0)
  if (value >= 0.72) return '#e5484d'
  if (value >= 0.35) return '#f5a623'
  return '#14a37f'
}

function configOf(row, key) {
  const value = ((row || {}).config || {})[key]
  return value === null || value === undefined ? '-' : value
}

/* ---------------- 计算属性 ---------------- */

const efficiency = computed(() => metrics.value.efficiency || {})

const matrixCols = computed(() =>
  Object.keys(DECISION_LABELS).map((key) => ({ key, label: DECISION_LABELS[key] }))
)

const matrixRows = computed(() =>
  Object.keys(DECISION_LABELS).map((key) => ({ aiKey: key, aiLabel: DECISION_LABELS[key] }))
)

const riskOption = computed(() => {
  const byRisk = metrics.value.byRiskLevel || {}
  // 仅在存在评估结果的风险等级上出柱，避免空数据时显示成「0%」的假数据
  const levels = ['high', 'medium', 'low'].filter((level) => byRisk[level])
  const labels = levels.map((level) => RISK_LABELS[level])
  const rates = levels.map((level) => percentValue(valueOf(byRisk[level], 'agreementRate')))
  const totals = levels.map((level) => Number(valueOf(byRisk[level], 'total')))
  return baseChartOption({
    tooltip: {
      trigger: 'axis',
      axisPointer: { type: 'shadow' },
      formatter: (params) => {
        const list = params || []
        if (!list.length) return ''
        const index = list[0].dataIndex
        return `${labels[index]}<br/>一致率：<b>${rates[index]}%</b><br/>AI 自主决策样本：${totals[index]} 笔`
      }
    },
    legend: { show: false },
    grid: { left: 12, right: 24, top: 24, bottom: 6, containLabel: true },
    xAxis: { type: 'category', data: labels, axisTick: { show: false } },
    yAxis: {
      type: 'value',
      name: '一致率(%)',
      min: 0,
      max: 100,
      axisLabel: { formatter: '{value}%' },
      splitLine: { lineStyle: { type: 'dashed' } }
    },
    series: [
      {
        name: '一致率',
        type: 'bar',
        barMaxWidth: 44,
        itemStyle: { borderRadius: [6, 6, 0, 0] },
        label: { show: true, position: 'top', formatter: '{c}%', fontSize: 12 },
        data: rates
      }
    ]
  })
})

const confidenceOption = computed(() => {
  const buckets = Array.isArray(metrics.value.byConfidence) ? metrics.value.byConfidence : []
  const ranges = buckets.map((item) => item?.range || '-')
  const rates = buckets.map((item) => percentValue(valueOf(item, 'agreementRate')))
  const totals = buckets.map((item) => Number(valueOf(item, 'total')))
  return baseChartOption({
    tooltip: { trigger: 'axis', axisPointer: { type: 'cross' } },
    legend: { show: true, right: 10, top: 4 },
    grid: { left: 12, right: 24, top: 40, bottom: 6, containLabel: true },
    xAxis: {
      type: 'category',
      name: '置信度区间',
      data: ranges,
      axisTick: { show: false },
      axisLabel: { fontSize: 11 }
    },
    yAxis: [
      {
        type: 'value',
        name: '一致率(%)',
        min: 0,
        max: 100,
        axisLabel: { formatter: '{value}%' },
        splitLine: { lineStyle: { type: 'dashed' } }
      },
      {
        type: 'value',
        name: '样本量',
        minInterval: 1,
        splitLine: { show: false },
        axisLabel: { formatter: '{value}' }
      }
    ],
    series: [
      {
        name: '一致率',
        type: 'bar',
        yAxisIndex: 0,
        barMaxWidth: 40,
        itemStyle: { color: '#1f5fd8', borderRadius: [6, 6, 0, 0] },
        label: { show: true, position: 'top', formatter: '{c}%', fontSize: 11 },
        data: rates
      },
      {
        name: '样本量',
        type: 'line',
        yAxisIndex: 1,
        smooth: true,
        symbolSize: 7,
        itemStyle: { color: '#f5a623' },
        lineStyle: { width: 2 },
        data: totals
      }
    ]
  })
})

const weightRows = computed(() => {
  const weights = policy.value.ruleWeights || {}
  return RULE_LABELS.map((item) => ({
    key: item.key,
    label: item.label,
    desc: item.desc,
    weight: weights[item.key] === undefined ? '-' : weights[item.key]
  }))
})

const optimizePoints = computed(() => {
  const points = (optimizeResult.value || {}).points
  return Array.isArray(points) ? points.filter((item) => !!item) : []
})

const optimizeCandidates = computed(() => {
  const list = (optimizeResult.value || {}).candidates
  return Array.isArray(list) ? list : []
})

/** 是否可应用优化策略：只有存在更优策略（improved=true）时才允许应用 */
const canApply = computed(() => !!optimizeResult.value && optimizeResult.value.improved === true)

const compareRows = computed(() => {
  const result = optimizeResult.value
  if (!result) return []
  const before = result.beforeMetrics || {}
  const after = result.afterMetrics || {}
  return COMPARE_METRICS.map((item) => {
    const beforeValue = Number(valueOf(before, item.key))
    const afterValue = Number(valueOf(after, item.key))
    const beforeText = item.percent ? formatPercent(beforeValue) : String(beforeValue)
    const afterText = item.percent ? formatPercent(afterValue) : String(afterValue)
    const diff = Number((afterValue - beforeValue).toFixed(6))
    let trend = 'same'
    if (diff > 0) trend = 'up'
    if (diff < 0) trend = 'down'
    const better = trend === 'same' ? true : item.dir === 'up' ? trend === 'up' : trend === 'down'
    return { key: item.key, label: item.label, beforeText, afterText, trend, better }
  })
})

/** 特征向量中文标注（用于抽屉中的样本复盘） */
const FEATURE_LABELS = [
  { key: 'code', label: '交易编号' },
  { key: 'name', label: '商户编码' },
  { key: 'amount', label: '交易金额' },
  { key: 'destRegion', label: '目的地' },
  { key: 'merchantAge', label: '商户账龄（月）' },
  { key: 'identityMatch', label: '身份一致性' },
  { key: 'nightRatio', label: '夜间交易占比' },
  { key: 'sanctionHit', label: '制裁清单命中' },
  { key: 'historyDeclines', label: '历史拒付笔数' },
  { key: 'velocity1h', label: '1 小时交易笔数' }
]

const featureRows = computed(() => {
  const features = (current.value || {}).features || {}
  return FEATURE_LABELS.map((item) => {
    const raw = features[item.key]
    let value = '-'
    if (raw !== undefined && raw !== null && raw !== '') {
      if (item.key === 'amount') value = formatAmount(raw)
      else if (typeof raw === 'boolean') value = raw ? '一致 / 命中' : '否'
      else value = String(raw)
    }
    return { label: item.label, value }
  })
})

/* ---------------- 数据加载 ---------------- */

async function loadBatches() {
  try {
    const data = await request.get('/ops/review/batches')
    batches.value = Array.isArray(data) ? data : []
  } catch (error) {
    batches.value = []
  }
}

async function loadPolicy() {
  try {
    const data = await request.get('/ops/review/policy')
    policy.value = (data && data.policy) || {}
    standards.value = (data && data.standards) || {}
  } catch (error) {
    policy.value = {}
    standards.value = {}
  }
}

async function loadConsistency() {
  try {
    const data = await request.get('/ops/review/consistency', {
      params: { batchCode: batchFilter.value || 'all' }
    })
    metrics.value = data || {}
  } catch (error) {
    metrics.value = {}
  }
}

async function loadRecords() {
  loading.value = true
  try {
    const data = await request.get('/ops/review/records', {
      params: {
        batchCode: query.batchCode || 'all',
        agreed: query.agreed || 'all',
        diffType: query.diffType || 'all',
        riskLevel: query.riskLevel || 'all',
        page: query.page,
        size: query.size
      }
    })
    const payload = data || {}
    records.list = Array.isArray(payload.list) ? payload.list : []
    records.total = Number(payload.total || 0)
    records.page = Number(payload.page || query.page)
    records.size = Number(payload.size || query.size)
  } catch (error) {
    records.list = []
    records.total = 0
  } finally {
    loading.value = false
  }
}

async function loadOptimizations() {
  try {
    const data = await request.get('/ops/review/optimizations')
    optimizations.value = Array.isArray(data) ? data : []
  } catch (error) {
    optimizations.value = []
  }
}

/** 刷新全部：批次、策略、一致性指标、记录、优化记录、标准 */
async function refreshAll() {
  loading.value = true
  try {
    await Promise.all([loadBatches(), loadPolicy(), loadConsistency(), loadOptimizations()])
    await loadRecords()
  } finally {
    loading.value = false
  }
}

/* ---------------- 交互事件 ---------------- */

async function handleRunBatch() {
  const count = Math.max(4, Math.min(60, Number(batchCount.value || 20)))
  running.value = true
  try {
    const data = await request.post('/ops/review/batch', { count })
    const payload = data || {}
    const batchCode = payload.batchCode || ''
    const rate = formatPercent(valueOf((payload.metrics || {}), 'agreementRate'))
    ElMessage.success(
      `审核批次 ${batchCode || '已完成'} 共 ${payload.count || count} 笔：一致性 ${rate}，正在刷新评估结果`
    )
    if (batchCode) {
      batchFilter.value = batchCode
      query.batchCode = batchCode
      query.page = 1
    }
    optimizeResult.value = null
    await refreshAll()
  } finally {
    running.value = false
  }
}

async function handleBatchChange() {
  query.batchCode = batchFilter.value
  query.page = 1
  loading.value = true
  try {
    await loadConsistency()
    await loadRecords()
  } finally {
    loading.value = false
  }
}

function handleFilterChange() {
  query.page = 1
  loadRecords()
}

function handlePageChange(page) {
  query.page = Number(page || 1)
  loadRecords()
}

function handleSizeChange(size) {
  query.size = Number(size || 10)
  query.page = 1
  loadRecords()
}

async function handleOptimize() {
  optimizing.value = true
  try {
    const data = await request.post('/ops/review/optimize', { batchCode: batchFilter.value || 'all' })
    optimizeResult.value = data || {}
    if (optimizeResult.value.improved) {
      ElMessage.success('已生成优化建议：存在综合得分更优的候选策略，可点击「应用优化策略」生效')
    } else {
      ElMessage.info('已完成候选策略复盘：当前策略在一致性 / 自动化率 / 漏放率目标下已是最优')
    }
    await loadOptimizations()
  } finally {
    optimizing.value = false
  }
}

async function handleApply() {
  if (!canApply.value) {
    ElMessage.warning('当前没有更优策略（improved = false），无需应用优化策略')
    return
  }
  applying.value = true
  try {
    const data = await request.post('/ops/review/apply', {})
    const payload = data || {}
    policy.value = payload.policy || policy.value
    const record = payload.record || {}
    ElMessage.success(
      `优化策略已应用${record.code ? `（${record.code}）` : ''}：通过阈值 ${policy.value.approveThreshold ?? '-'}、` +
        `拒绝阈值 ${policy.value.rejectThreshold ?? '-'}、置信度门槛 ${policy.value.confidenceFloor ?? '-'}，` +
        '后续审核批次将使用新策略'
    )
    await Promise.all([loadPolicy(), loadOptimizations()])
    optimizeResult.value = null
  } finally {
    applying.value = false
  }
}

function openDrawer(row) {
  current.value = row || null
  drawerVisible.value = true
}

onMounted(() => {
  refreshAll()
})
