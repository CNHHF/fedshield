
/**
 * 支付通道池与路由权重说明（赛题 A16 · 建设范围一：通道选择能力）
 *
 * 数据来源：GET /api/ops/payment/channels
 *   { channels: [...], restricted: [...], retryPolicy: { maxRetry, backoffMs }, weights: { cost, success, latency, compliance } }
 *
 * 项目当前 api 封装（src/api/index.js）尚未包含 ops 接口，为避免改动既有文件，
 * 本页直接使用 axios 实例 request 调用，响应拦截器已统一解包 { code, message, data }。
 */
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { Refresh } from '@element-plus/icons-vue'
import request from '@/api/request'
import { formatNumber, formatPercent } from '@/utils/format'

const router = useRouter()

/** 通道健康状态字典（与 backend/models.py PaymentChannel.status 一致） */
const CHANNEL_STATUS = {
  available: { label: '可用', type: 'success' },
  degraded: { label: '降级', type: 'warning' },
  down: { label: '已下线', type: 'danger' }
}

/** 地区中文名映射（后端以地区编码返回） */
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

/** 权重维度元数据（权重值以后端返回为准，后端缺省时用引擎默认值） */
const WEIGHT_META = [
  { key: 'cost', label: '成本权重', color: '#1f5fd8', desc: '通道费率越低得分越高' },
  { key: 'success', label: '成功率权重', color: '#14a37f', desc: '历史清算成功率' },
  { key: 'latency', label: '时效权重', color: '#f5a623', desc: '平均到账时延越低越好' },
  { key: 'compliance', label: '合规权重', color: '#8b5cf6', desc: '牌照与数据合规能力' }
]

const DEFAULT_WEIGHTS = { cost: 0.4, success: 0.3, latency: 0.2, compliance: 0.1 }

const loading = ref(false)
const channels = ref([])
const restricted = ref([])
const retryPolicy = ref({ maxRetry: 2, backoffMs: [200, 600] })
const weights = ref({ ...DEFAULT_WEIGHTS })
const weightSource = ref('default')

const availableCount = computed(() => channels.value.filter((item) => item.status === 'available').length)
const degradedCount = computed(() => channels.value.filter((item) => item.status === 'degraded').length)
const downCount = computed(() => channels.value.filter((item) => item.status === 'down').length)

const retryMax = computed(() => {
  const value = Number(retryPolicy.value?.maxRetry ?? 2)
  return Number.isFinite(value) && value > 0 ? value : 2
})

const backoffText = computed(() => {
  const list = Array.isArray(retryPolicy.value?.backoffMs) ? retryPolicy.value.backoffMs : [200, 600]
  const text = list.filter((item) => Number(item) > 0).map((item) => `${formatNumber(item)}ms`)
  return text.length ? text.join(' → ') : '200ms → 600ms'
})

const weightItems = computed(() =>
  WEIGHT_META.map((item) => {
    const value = Number(weights.value?.[item.key] ?? DEFAULT_WEIGHTS[item.key]) || 0
    return { ...item, value, percent: Math.min(100, Math.max(0, Number((value * 100).toFixed(1)))) }
  })
)

/** 评分公式文案（权重全部取自接口，避免前后端口径漂移） */
const weightFormula = computed(() => {
  const part = weightItems.value
    .map((item) => `${formatPercent(item.value, 0)} × ${item.label.replace('权重', '得分')}`)
    .join(' + ')
  return `综合得分 = ${part}`
})

/** 重试链路时间线（由 maxRetry / backoffMs 动态推导，保证与后端策略一致） */
const retryTimeline = computed(() => {
  const max = retryMax.value
  const backoff = Array.isArray(retryPolicy.value?.backoffMs) ? retryPolicy.value.backoffMs : [200, 600]
  const list = [{ title: '第 1 次尝试：智能路由选中的主通道提交清算', type: 'primary' }]
  for (let index = 0; index < max; index += 1) {
    const wait = backoff[Math.min(index, backoff.length - 1)]
    list.push({ title: `第 ${index + 1} 次尝试失败：分类判定失败原因并写入事件流`, type: 'danger' })
    list.push({
      title: `${formatNumber(wait ?? 200)}ms 指数退避后切换备用通道（已排除失败通道）`,
      type: 'warning'
    })
    list.push({ title: `第 ${index + 2} 次尝试：备用通道提交清算`, type: 'primary' })
  }
  list.push({ title: `重试 ${max} 次仍失败 → 触发自动补偿（改道重发 / 原路退回）`, type: 'danger' })
  return list
})

function destLabel(code) {
  if (!code) return '-'
  return REGION_LABEL[code] || code
}

function isRestricted(code) {
  return (restricted.value || []).includes(code)
}

function channelStatusOf(status) {
  return CHANNEL_STATUS[status] || { label: status || '未知', type: 'info' }
}

function ratePercent(rate) {
  const value = Number(rate || 0) * 100
  return Math.min(100, Math.max(0, Number(value.toFixed(1))))
}

/** 成功率配色：< 95% 危险，< 98% 预警，其余正常 */
function rateColor(rate) {
  const value = Number(rate || 0)
  if (value < 0.95) return '#e5484d'
  if (value < 0.98) return '#f5a623'
  return '#14a37f'
}

/** 时延配色：≥ 3000ms 危险，≥ 2000ms 预警 */
function latencyClass(latency) {
  const value = Number(latency || 0)
  if (value >= 3000) return 'fs-channels__latency--danger'
  if (value >= 2000) return 'fs-channels__latency--warning'
  return ''
}

async function loadChannels() {
  loading.value = true
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
    // 请求层已弹出错误提示，这里保证页面回到可用（空）状态
    channels.value = []
    restricted.value = []
  } finally {
    loading.value = false
  }
}

function goFlow() {
  router.push('/ops/payment')
}

onMounted(() => {
  loadChannels()
})
