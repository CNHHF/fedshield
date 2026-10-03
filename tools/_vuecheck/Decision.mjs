
/**
 * 运营决策支撑（赛题 A16 建设范围五）
 *
 * 数据来源（接口契约见 backend/api/ops.py「⑤ 运营决策支撑」与 dashboard 接口）：
 * - GET /ops/overview        一体化总览：支付 / 审核一致性 / 异常监测核心指标 + 建议条数
 * - GET /ops/decisions       指标监控 + 策略评估指标 + 决策建议（advice）
 * - GET /dashboard/flow-trend 数据流转趋势（可选数据源，不可用时降级为示意曲线并标注）
 *
 * 说明：不使用 src/api/index.js（保持该文件不变），直接经 request 统一封装调用；
 * 所有接口返回值均做空值兜底，指标缺失时展示「-」而不是抛出异常。
 */
import { computed, onMounted, reactive, ref } from 'vue'
import { MagicStick, Refresh } from '@element-plus/icons-vue'
import request from '@/api/request'
import ChartBox from '@/components/ChartBox.vue'
import StatCard from '@/components/StatCard.vue'
import { baseChartOption, formatDuration } from '@/utils/format'

const loading = ref(false)
const trendLoading = ref(false)
const advice = ref([])
const generatedAt = ref('')
const trendFallback = ref(false)

/** 决策指标（字段与 /ops/decisions 的 metrics 对齐） */
const metrics = reactive({
  review: {},
  payment: {},
  monitoring: {}
})

/** 一体化总览（字段与 /ops/overview 对齐） */
const overview = reactive({
  payment: {},
  consistency: {},
  monitoring: {},
  adviceCount: 0,
  generatedAt: ''
})

/** 趋势数据：{ dates: [], series: [{ name, data }] } */
const trend = reactive({ dates: [], series: [] })

const PRIORITY_ORDER = { P0: 0, P1: 1, P2: 2 }
const PRIORITY_TYPES = { P0: 'danger', P1: 'warning', P2: 'primary' }
const STATUS_TYPES = { 达标: 'success', 关注: 'warning', 预警: 'danger' }

function priorityType(priority) {
  return PRIORITY_TYPES[priority] || 'info'
}

function statusTagType(status) {
  return STATUS_TYPES[status] || 'info'
}

function priorityCount(priority) {
  return advice.value.filter((item) => item.priority === priority).length
}

/** 数值兜底：null / undefined / 非数字统一返回 0 */
function num(value) {
  const parsed = Number(value)
  return Number.isFinite(parsed) ? parsed : 0
}

/** 比率转百分比文本（缺失时展示占位符，避免把「无数据」误读为 0%） */
function percentText(value) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return '-'
  return `${(Number(value) * 100).toFixed(1)}%`
}

function durationText(value) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return '-'
  return formatDuration(Number(value))
}

/* ---------------- 一体化总览 ---------------- */

const overviewKpis = computed(() => {
  const pay = overview.payment || {}
  const con = overview.consistency || {}
  const mon = overview.monitoring || {}
  return [
    {
      label: '支付成功率',
      value: Number((num(pay.successRate) * 100).toFixed(1)),
      unit: '%',
      precision: 1,
      icon: 'CreditCard',
      color: '#1f5fd8',
      sub: `订单总量 ${num(pay.total)} 笔 · 直通率 ${percentText(pay.straightThroughRate)}`
    },
    {
      label: '审核一致率',
      value: Number((num(con.agreementRate) * 100).toFixed(1)),
      unit: '%',
      precision: 1,
      icon: 'DocumentChecked',
      color: '#14a37f',
      sub: `Kappa ${num(con.kappa).toFixed(2)} · 漏放 ${num(con.falseNegativeCount)} 笔`
    },
    {
      label: 'AI 审核自动化率',
      value: Number((num(con.automationRate) * 100).toFixed(1)),
      unit: '%',
      precision: 1,
      icon: 'MagicStick',
      color: '#8b5cf6',
      sub: `转人工比例 ${percentText(con.manualTransferRate)}`
    },
    {
      label: '异常自动处置率',
      value: Number((num(mon.autoHandledRate) * 100).toFixed(1)),
      unit: '%',
      precision: 1,
      icon: 'Warning',
      color: '#f5a623',
      sub: `预警 ${num(mon.total)} 条 · 高危 ${num(mon.high)} 条`
    }
  ]
})

/** 三组能力明细（与建设范围一一对应） */
const overviewGroups = computed(() => {
  const pay = overview.payment || {}
  const con = overview.consistency || {}
  const mon = overview.monitoring || {}
  return [
    {
      title: '① 支付智能处理',
      hint: `订单总量 ${num(pay.total)} 笔`,
      items: [
        { label: '订单总量', value: `${num(pay.total)} 笔` },
        { label: '支付成功率', value: percentText(pay.successRate) },
        { label: '一次直通率', value: percentText(pay.straightThroughRate) },
        { label: '平均处理耗时', value: durationText(pay.avgDurationMs) },
        { label: '自动补偿率', value: percentText(pay.compensationRate) }
      ]
    },
    {
      title: '③④ 审核一致性与自动化',
      hint: `审核样本 ${num(con.total)} 笔`,
      items: [
        { label: 'AI 与人工一致率', value: percentText(con.agreementRate) },
        { label: 'AI 自动化率', value: percentText(con.automationRate) },
        { label: 'Kappa 一致性系数', value: num(con.kappa).toFixed(2) },
        { label: '漏放笔数', value: `${num(con.falseNegativeCount)} 笔` }
      ]
    },
    {
      title: '② 智能风控与异常监测',
      hint: `预警总量 ${num(mon.total)} 条`,
      items: [
        { label: '预警总数', value: `${num(mon.total)} 条` },
        { label: '高危预警', value: `${num(mon.high)} 条` },
        { label: '自动化处置率', value: percentText(mon.autoHandledRate) },
        { label: '待人工比例', value: percentText(mon.manualPendingRate) }
      ]
    }
  ]
})

/* ---------------- 策略评估（雷达图） ---------------- */

/**
 * 指标归一化（0~100）：
 * - 正向指标（一致率、自动化率、成功率、直通率、自动处置率）直接取百分比；
 * - 反向指标（补偿率）取「1 - 补偿率」的百分比，越高代表控制越好。
 */
const radarIndicators = computed(() => {
  const review = metrics.review || {}
  const pay = metrics.payment || {}
  const mon = metrics.monitoring || {}
  const detail = overview.payment || {}
  const straightThrough = detail.straightThroughRate ?? pay.successRate
  return {
    current: [
      clamp(num(review.agreementRate) * 100),
      clamp(num(review.automationRate) * 100),
      clamp(num(pay.successRate) * 100),
      clamp(num(straightThrough) * 100),
      clamp(num(mon.autoHandledRate) * 100),
      clamp((1 - num(pay.compensationRate)) * 100)
    ],
    target: [95, 60, 95, 85, 70, 98]
  }
})

function clamp(value) {
  return Math.max(0, Math.min(100, Number(value.toFixed(1))))
}

const radarOption = computed(() => {
  const data = radarIndicators.value
  return baseChartOption({
    tooltip: { trigger: 'item' },
    legend: { top: 0, right: 10, icon: 'roundRect', itemWidth: 10, itemHeight: 10, textStyle: { fontSize: 12 } },
    radar: {
      center: ['50%', '56%'],
      radius: '62%',
      indicator: [
        { name: '审核一致率', max: 100 },
        { name: 'AI 自动化率', max: 100 },
        { name: '支付成功率', max: 100 },
        { name: '支付直通率', max: 100 },
        { name: '异常自动处置率', max: 100 },
        { name: '补偿率控制', max: 100 }
      ],
      axisName: { color: '#5c6b7f', fontSize: 11 },
      splitLine: { lineStyle: { color: '#e4e8ef' } },
      splitArea: { areaStyle: { color: ['#ffffff', '#f7f9fc'] } }
    },
    series: [
      {
        type: 'radar',
        symbolSize: 4,
        data: [
          {
            name: '当前策略',
            value: data.current,
            areaStyle: { opacity: 0.22 },
            lineStyle: { width: 2 }
          },
          {
            name: '目标基线',
            value: data.target,
            areaStyle: { opacity: 0.06 },
            lineStyle: { width: 1.5, type: 'dashed' }
          }
        ]
      }
    ]
  })
})

/* ---------------- 趋势研判 ---------------- */

const trendOption = computed(() => {
  const series = trend.series || []
  return baseChartOption({
    tooltip: { trigger: 'axis' },
    legend: { top: 0, right: 10, icon: 'roundRect', itemWidth: 10, itemHeight: 10, textStyle: { fontSize: 12 } },
    grid: { left: 20, right: 24, top: 40, bottom: 8, containLabel: true },
    xAxis: { type: 'category', boundaryGap: false, data: trend.dates || [] },
    yAxis: { type: 'value', minInterval: 1 },
    series: series.map((item, index) => ({
      name: item.name || `序列${index + 1}`,
      type: 'line',
      smooth: true,
      showSymbol: false,
      lineStyle: { width: 2 },
      areaStyle: index === 0 ? { opacity: 0.12 } : undefined,
      data: item.data || []
    }))
  })
})

/** 趋势研判结论：基于当前指标给出可执行判断 */
const trendConclusions = computed(() => {
  const review = metrics.review || {}
  const pay = metrics.payment || {}
  const mon = metrics.monitoring || {}
  const successRate = num(pay.successRate)
  const manualRate = num(review.manualTransferRate)
  const agreementRate = num(review.agreementRate)
  const compensationRate = num(pay.compensationRate)
  const autoHandledRate = num(mon.autoHandledRate)
  const highCount = num(mon.high)
  const list = []

  list.push(
    successRate >= 0.95
      ? { tag: '支付', type: 'success', text: `支付成功率 ${percentText(pay.successRate)}，链路运行稳定；平均处理耗时 ${durationText(pay.avgDurationMs)}。` }
      : { tag: '支付', type: 'warning', text: `支付成功率 ${percentText(pay.successRate)}，低于 95% 目标，建议排查通道路由与重试策略。` }
  )

  list.push(
    manualRate > 0.3
      ? { tag: '审核', type: 'warning', text: `转人工比例 ${percentText(review.manualTransferRate)} 偏高、AI 自动化率 ${percentText(review.automationRate)}，建议优先优化审核阈值与置信度门槛。` }
      : { tag: '审核', type: 'success', text: `转人工比例 ${percentText(review.manualTransferRate)} 处于合理区间，AI 自动化率 ${percentText(review.automationRate)}。` }
  )

  list.push(
    agreementRate >= 0.95
      ? { tag: '一致性', type: 'success', text: `AI 与人工一致率 ${percentText(review.agreementRate)}、Kappa ${num(review.kappa).toFixed(2)}，审核口径对齐良好。` }
      : { tag: '一致性', type: 'warning', text: `一致率 ${percentText(review.agreementRate)} 未达 95% 目标，建议执行差异回流与策略优化。` }
  )

  list.push(
    compensationRate > 0.02
      ? { tag: '通道', type: 'warning', text: `自动补偿率 ${percentText(pay.compensationRate)} 超过 2% 阈值，建议下调降级通道路由权重。` }
      : { tag: '通道', type: 'success', text: `自动补偿率 ${percentText(pay.compensationRate)} 在阈值内，通道质量可控。` }
  )

  list.push(
    highCount > 0
      ? { tag: '风控', type: 'warning', text: `存在 ${highCount} 条高危预警，自动处置率 ${percentText(mon.autoHandledRate)}，建议按「自动处置 + 人工确认」在 30 分钟内闭环。` }
      : { tag: '风控', type: 'success', text: `当前无高危预警，异常自动处置率 ${percentText(mon.autoHandledRate)}。` }
  )
  return list
})

/** 一句话研判结论（趋势卡片标题下方的高亮提示） */
const trendHeadline = computed(() => {
  const review = metrics.review || {}
  const pay = metrics.payment || {}
  const successRate = num(pay.successRate)
  const manualRate = num(review.manualTransferRate)
  const parts = []
  parts.push(successRate >= 0.95 ? '支付成功率稳定' : `支付成功率 ${percentText(pay.successRate)} 承压`)
  if (manualRate > 0.3) {
    parts.push(`转人工比例偏高（${percentText(review.manualTransferRate)}）`)
    parts.push('建议优先优化审核阈值')
  } else if (num(metrics.monitoring?.high) > 0) {
    parts.push('高危预警需及时处置')
    parts.push('建议强化异常监测人工确认闭环')
  } else {
    parts.push('各项指标处于目标区间')
    parts.push('建议保持当前策略并按周抽检')
  }
  return `${parts.join('、')}。`
})

/** 趋势接口不可用时的示意曲线（基于现有指标构造，并在卡片上标注「示意图」） */
function buildFallbackTrend() {
  const days = 14
  const labels = []
  const today = new Date()
  for (let index = days - 1; index >= 0; index -= 1) {
    const date = new Date(today.getTime() - index * 86400000)
    const month = String(date.getMonth() + 1).padStart(2, '0')
    const day = String(date.getDate()).padStart(2, '0')
    labels.push(`${month}-${day}`)
  }
  const base = Math.max(30, num(metrics.payment.total) + 60)
  const alertBase = Math.max(2, Math.round(num(metrics.monitoring.total) / 4))
  return {
    dates: labels,
    series: [
      { name: '跨境交易笔数（示意）', data: labels.map((_, index) => Math.round(base + Math.sin(index / 2) * base * 0.1 + index)) },
      { name: '异常预警条数（示意）', data: labels.map((_, index) => alertBase + (index % 4)) }
    ]
  }
}

/* ---------------- 数据加载 ---------------- */

async function loadOverview() {
  const payload = (await request.get('/ops/overview')) || {}
  Object.assign(overview, {
    payment: payload.payment || {},
    consistency: payload.consistency || {},
    monitoring: payload.monitoring || {},
    adviceCount: num(payload.adviceCount),
    generatedAt: payload.generatedAt || ''
  })
}

async function loadDecisions() {
  const payload = (await request.get('/ops/decisions')) || {}
  const raw = Array.isArray(payload.advice) ? payload.advice : []
  // 按优先级排序，P0 置顶；同优先级保持后端返回顺序
  advice.value = raw
    .slice()
    .sort((prev, next) => (PRIORITY_ORDER[prev.priority] ?? 9) - (PRIORITY_ORDER[next.priority] ?? 9))
  const data = payload.metrics || {}
  Object.assign(metrics, {
    review: data.review || {},
    payment: data.payment || {},
    monitoring: data.monitoring || {}
  })
  generatedAt.value = payload.generatedAt || ''
}

/** 趋势数据为可选增强项：失败时静默降级为示意曲线，不打断决策看板 */
async function loadTrend() {
  trendLoading.value = true
  try {
    const payload = await request.get('/dashboard/flow-trend', { params: { days: 30 }, silent: true })
    const dates = payload?.dates || []
    const series = payload?.series || []
    if (!dates.length || !series.length) {
      throw new Error('趋势数据为空')
    }
    trendFallback.value = false
    Object.assign(trend, { dates, series })
  } catch (error) {
    trendFallback.value = true
    Object.assign(trend, buildFallbackTrend())
  } finally {
    trendLoading.value = false
  }
}

async function loadAll() {
  loading.value = true
  try {
    await Promise.all([loadOverview(), loadDecisions()])
  } catch (error) {
    // 错误提示已由请求层统一处理，这里仅保证页面渲染不中断
  } finally {
    loading.value = false
  }
}

/* ---------------- 指标监控表 ---------------- */

const pct1 = (value) => `${value.toFixed(1)}%`
const pct2 = (value) => `${value.toFixed(2)}%`
const countText = (value) => `${value.toFixed(0)} 笔`
const num2 = (value) => value.toFixed(2)
const msText = (value) => `${value.toFixed(0)} ms`

/**
 * 生成一行监控指标
 * direction = 'up'：越大越好（目标为下限）；'down'：越小越好（目标为上限）
 * warn：未达标但仍在可接受区间时的「关注」临界值
 */
function buildRow(name, group, value, target, targetText, direction, warn, formatter) {
  const current = num(value)
  const reached = direction === 'up' ? current >= target : current <= target
  const watched = direction === 'up' ? current >= warn : current <= warn
  return {
    name,
    group,
    current,
    display: formatter(current),
    targetText,
    status: reached ? '达标' : watched ? '关注' : '预警'
  }
}

const monitorRows = computed(() => {
  const review = metrics.review || {}
  const pay = metrics.payment || {}
  const mon = metrics.monitoring || {}
  const detail = overview.payment || {}
  const straightThrough = detail.straightThroughRate ?? pay.successRate
  const avgDuration = pay.avgDurationMs ?? detail.avgDurationMs
  return [
    buildRow('审核一致率', '审核一致性', num(review.agreementRate) * 100, 95, '≥ 95%', 'up', 90, pct1),
    buildRow('AI 审核自动化率', '审核一致性', num(review.automationRate) * 100, 60, '≥ 60%', 'up', 45, pct1),
    buildRow('Kappa 一致性系数', '审核一致性', num(review.kappa), 0.75, '≥ 0.75', 'up', 0.6, num2),
    buildRow('漏放笔数', '审核一致性', num(review.falseNegativeCount), 0, '≤ 0 笔', 'down', 3, countText),
    buildRow('支付成功率', '支付智能处理', num(pay.successRate) * 100, 95, '≥ 95%', 'up', 90, pct1),
    buildRow('支付一次直通率', '支付智能处理', num(straightThrough) * 100, 85, '≥ 85%', 'up', 75, pct1),
    buildRow('平均处理耗时', '支付智能处理', num(avgDuration), 800, '≤ 800 ms', 'down', 1500, msText),
    buildRow('自动补偿率', '支付智能处理', num(pay.compensationRate) * 100, 2, '≤ 2%', 'down', 4, pct2),
    buildRow('异常自动处置率', '智能风控', num(mon.autoHandledRate) * 100, 70, '≥ 70%', 'up', 50, pct1),
    buildRow('高危预警数', '智能风控', num(mon.high), 5, '≤ 5 条', 'down', 10, countText)
  ]
})

onMounted(async () => {
  await loadAll()
  // 总览指标就绪后再加载趋势，保证降级示意曲线有可用的指标基线
  await loadTrend()
})
