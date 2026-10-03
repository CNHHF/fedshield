
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { engineApi } from '@/api'
import ChartBox from '@/components/ChartBox.vue'
import StatCard from '@/components/StatCard.vue'
import { useAppStore } from '@/store/app'
import {
  CHART_COLORS,
  RISK_LEVEL,
  TASK_STATUS,
  TASK_TYPE,
  baseChartOption,
  dictOf,
  formatDuration,
  formatNumber,
  formatPercent,
  formatTime
} from '@/utils/format'
import { downloadResponse, exportCsv } from '@/utils/download'

const route = useRoute()
const router = useRouter()
const appStore = useAppStore()

const loading = ref(false)
const exporting = ref(false)
const finishedTasks = ref([])
const selectedId = ref('')
const result = ref({})
// 列表接口拿到的任务摘要，作为详情接口缺字段时的兜底展示来源
const taskMeta = ref({})

const taskId = computed(() => selectedId.value || route.params.id || '')

/**
 * 结果体兼容处理：
 * - 任务详情接口把结果摘要放在 data.result 中；
 * - 三大场景计算接口直接返回扁平结构。
 * 统一取出「含指标的那一层」，避免出现 undefined.xxx。
 */
const payload = computed(() => {
  const data = result.value || {}
  if (data.metrics || data.rounds) return data
  if (data.result && typeof data.result === 'object') return data.result
  return data
})

const metric = computed(() => payload.value.metrics || payload.value || {})

const riskDistribution = computed(() => payload.value.riskDistribution ?? metric.value.riskDistribution ?? [])

const riskTotal = computed(() => riskDistribution.value.reduce((sum, item) => sum + Number(item?.value ?? 0), 0))

const rounds = computed(() => payload.value.rounds ?? [])

const traffic = computed(() => payload.value.traffic ?? {})

const baseline = computed(() => payload.value.baseline ?? {})

const resource = computed(() => {
  const item = result.value?.resource || payload.value.resource || {}
  return {
    cpuSec: item.cpuSec ?? 0,
    // 后端不同模块对内存字段命名不完全一致（resource.memoryMb / resource.memMb），做兼容取值
    memoryMb: item.memoryMb ?? item.memMb ?? 0,
    elapsedMs: item.elapsedMs ?? result.value?.durationMs ?? 0
  }
})

const params = computed(() => result.value?.params || payload.value.params || {})

const cipherText = computed(() => {
  if (params.value.cipher) return params.value.cipher
  if (payload.value.homomorphic?.scheme) return payload.value.homomorphic.scheme
  return TASK_TYPE[taskMeta.value.type]?.tech || '-'
})

const iterations = computed(() => {
  const value = params.value.iterations ?? rounds.value.length
  return value ? `${value} 轮` : '-'
})

const partnerCodes = computed(() => {
  const list = taskMeta.value.partners || payload.value.partners || []
  return Array.isArray(list) ? list : []
})

const chainTxId = computed(() => payload.value.chainTxId || result.value?.chainTxId || '')

const baselineRule = computed(
  () =>
    baseline.value.operatingRule ||
    `各建模方式均按漏检率 ≤ ${formatPercent(metric.value.missRateStandard || 0.07, 0)} 红线反推告警阈值后对比`
)

// 基线对比三行：联合建模（本次结果）、单地区本地建模、明文集中建模
const baselineRows = computed(() => {
  const rows = [
    {
      name: '联合建模（横向联邦 + 差分隐私 + 同态聚合）',
      auc: metric.value.auc,
      missRate: metric.value.missRate,
      precision: metric.value.precision,
      alertVolume: metric.value.alertVolume,
      note: '本次任务实际结果，原始数据不出各参与方节点'
    }
  ]
  const local = baseline.value.localOnly
  if (local) {
    rows.push({
      name: '单地区本地建模',
      auc: local.auc,
      missRate: local.missRate,
      precision: local.precision,
      alertVolume: local.alertVolume,
      note: local.note || '不进行跨地域协作，缺少其他地区风险成因特征'
    })
  }
  const plain = baseline.value.plaintext
  if (plain) {
    rows.push({
      name: '明文集中建模（效果上限参考）',
      auc: plain.auc,
      missRate: plain.missRate,
      precision: plain.precision,
      alertVolume: plain.alertVolume,
      note: plain.note || '不加密、不加噪，仅作为效果上限参考'
    })
  }
  return rows
})

const riskPieOption = computed(() => {
  const colors = { 高风险: RISK_LEVEL.high.color, 中风险: RISK_LEVEL.medium.color, 低风险: RISK_LEVEL.low.color }
  return baseChartOption({
    tooltip: { trigger: 'item', formatter: '{b}：{c} 条（{d}%）' },
    legend: { bottom: 0, icon: 'circle', itemWidth: 10, itemHeight: 10 },
    series: [
      {
        name: '风险分布',
        type: 'pie',
        radius: ['45%', '68%'],
        center: ['50%', '46%'],
        avoidLabelOverlap: true,
        label: { formatter: '{b}\n{d}%', fontSize: 12 },
        data: riskDistribution.value.map((item) => ({
          name: item?.name || '未分类',
          value: Number(item?.value ?? 0),
          itemStyle: { color: colors[item?.name] || CHART_COLORS[6] }
        }))
      }
    ]
  })
})

const roundsOption = computed(() =>
  baseChartOption({
    tooltip: { trigger: 'axis' },
    legend: { data: ['训练损失 Loss', '评测 AUC'], right: 10, top: 4 },
    xAxis: {
      type: 'category',
      name: '轮次',
      boundaryGap: false,
      data: rounds.value.map((item) => `第 ${item?.round ?? '-'} 轮`)
    },
    yAxis: [
      { type: 'value', name: 'Loss', scale: true, axisLabel: { formatter: (value) => Number(value).toFixed(2) } },
      { type: 'value', name: 'AUC', min: 0.5, max: 1, axisLabel: { formatter: (value) => Number(value).toFixed(2) } }
    ],
    series: [
      {
        name: '训练损失 Loss',
        type: 'line',
        smooth: true,
        symbolSize: 6,
        yAxisIndex: 0,
        areaStyle: { opacity: 0.08 },
        data: rounds.value.map((item) => item?.loss ?? null)
      },
      {
        name: '评测 AUC',
        type: 'line',
        smooth: true,
        symbolSize: 6,
        yAxisIndex: 1,
        data: rounds.value.map((item) => item?.auc ?? null)
      }
    ]
  })
)

const trafficOption = computed(() =>
  baseChartOption({
    tooltip: {
      trigger: 'axis',
      axisPointer: { type: 'shadow' },
      valueFormatter: (value) => `${formatNumber(value, 2)} KB`
    },
    legend: { show: false },
    grid: { left: 46, right: 22, top: 30, bottom: 30, containLabel: true },
    xAxis: { type: 'category', data: ['参数传输量'] },
    yAxis: { type: 'value', name: 'KB' },
    series: [
      {
        name: '优化前（float32 全量）',
        type: 'bar',
        barWidth: 46,
        itemStyle: { color: CHART_COLORS[0], borderRadius: [4, 4, 0, 0] },
        label: { show: true, position: 'top', formatter: (item) => `${formatNumber(item.value, 2)} KB` },
        data: [Number(traffic.value.rawKb ?? 0)]
      },
      {
        name: `优化后（量化+剪枝，目标 ${formatNumber(traffic.value.target ?? 70, 0)}%）`,
        type: 'bar',
        barWidth: 46,
        itemStyle: { color: CHART_COLORS[1], borderRadius: [4, 4, 0, 0] },
        label: { show: true, position: 'top', formatter: (item) => `${formatNumber(item.value, 2)} KB` },
        data: [Number(traffic.value.optimizedKb ?? 0)]
      }
    ]
  })
)

const hasData = computed(() => Object.keys(result.value || {}).length > 0)

function statusOf(status) {
  return dictOf(TASK_STATUS, status || 'finished', '已完成')
}

function typeLabel(task) {
  if (task?.typeName) return task.typeName
  if (TASK_TYPE[task?.type]) return TASK_TYPE[task.type].label
  return appStore.taskTypeName(task?.type) || task?.type || '-'
}

// StatCard 的数值属性只接受数字或字符串，缺失指标返回 null 以免渲染出误导性的 0
function numberOrNull(value, precision = 2) {
  if (value === null || value === undefined || value === '') return null
  const num = Number(value)
  return Number.isNaN(num) ? null : Number(num.toFixed(precision))
}

function percentOrNull(value, precision = 1) {
  if (value === null || value === undefined || value === '') return null
  const num = Number(value)
  return Number.isNaN(num) ? null : `${(num * 100).toFixed(precision)}%`
}

/** 拉取已完成任务，供顶部「切换任务」下拉使用 */
async function loadFinishedTasks() {
  try {
    const data = await engineApi.tasks({ status: 'finished', page: 1, size: 100 })
    // 列表接口返回分页对象；若后端直接返回数组也兼容
    finishedTasks.value = Array.isArray(data) ? data : data?.list ?? []
  } catch (error) {
    finishedTasks.value = []
  }
  return finishedTasks.value
}

async function loadResult(id) {
  loading.value = true
  try {
    // 先取任务详情（含参数与资源消耗），再取计算结果：详情里的 result 摘要作为兜底
    const detail = await engineApi.taskDetail(id)
    taskMeta.value = detail || {}
    const data = await engineApi.taskResult(id)
    result.value = data && Object.keys(data).length ? data : detail?.result || {}
  } catch (error) {
    result.value = {}
  } finally {
    loading.value = false
  }
}

async function load() {
  loading.value = true
  try {
    const list = await loadFinishedTasks()
    // 路由参数优先；无参数时默认展示最近完成的一个任务
    const routeId = route.params.id ? String(route.params.id) : ''
    const target = routeId || (list.length ? String(list[0].id) : '')
    selectedId.value = target
    const summary = list.find((item) => String(item.id) === target)
    taskMeta.value = summary || {}
  } finally {
    loading.value = false
  }
  if (taskId.value) {
    await loadResult(taskId.value)
  } else {
    result.value = {}
    taskMeta.value = {}
  }
}

function handleTaskChange(id) {
  if (!id) {
    result.value = {}
    return
  }
  // 切换任务时同步路由，便于结果页被分享或刷新后仍定位到同一任务
  router.replace(`/engine/result/${id}`).catch(() => {})
  loadResult(id)
}

function goAllResults() {
  ElMessage.info('完整结果集含脱敏样本预览与逐轮明细，可在任务管理页导出加密审计日志后查看')
  router.push('/engine/tasks')
}

async function handleExport() {
  if (!taskId.value) {
    ElMessage.warning('请先选择要导出的任务')
    return
  }
  exporting.value = true
  try {
    const response = await engineApi.exportTask(taskId.value)
    downloadResponse(response, `fedshield-计算结果-${taskMeta.value.code || taskId.value}.csv`)
    ElMessage.success('计算结果导出已开始下载')
  } catch (error) {
    // 导出接口不可用时退化为前端导出基线对比表，保证用户仍能拿到核心结论
    exportCsv(
      baselineRows.value,
      [
        { prop: 'name', label: '建模方式' },
        { prop: (row) => formatNumber(row.auc, 4), label: 'AUC' },
        { prop: (row) => formatPercent(row.missRate, 2), label: '漏检率' },
        { prop: (row) => formatPercent(row.precision, 2), label: '精确率' },
        { prop: (row) => formatPercent(row.alertVolume, 2), label: '告警量' },
        { prop: 'note', label: '说明' }
      ],
      `fedshield-基线对比-${taskId.value}.csv`
    )
    ElMessage.warning('服务端导出不可用，已改为导出前端基线对比表')
  } finally {
    exporting.value = false
  }
}

onMounted(async () => {
  try {
    await appStore.loadMeta()
  } catch (error) {
    // 节点名称为展示增强项，失败不阻塞结果加载
  }
  load()
})
