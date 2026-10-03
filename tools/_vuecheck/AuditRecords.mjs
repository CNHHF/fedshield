
import { onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { auditApi } from '@/api'
import StatCard from '@/components/StatCard.vue'
import { formatNumber, formatTime } from '@/utils/format'

/* ---------------- 字典 ---------------- */
const ACTIONS = [
  { value: 'login', label: '登录认证' },
  { value: 'query', label: '数据查询' },
  { value: 'export', label: '数据导出' },
  { value: 'compute', label: '发起计算' },
  { value: 'grant', label: '授权变更' },
  { value: 'rule', label: '规则调整' },
  { value: 'verify', label: '链上校验' }
]

/* ---------------- 状态 ---------------- */
const loading = ref(false)
const chainLoading = ref(false)
const verifying = ref(false)

const stats = reactive({ txTotal: 0, blockHeight: 0, tps: 0, retentionYears: 0, regulatorNodes: [] })

const logQuery = reactive({ actor: '', action: '', range: [], result: '' })
const logs = reactive({ list: [], total: 0, page: 1, size: 10 })

const chain = reactive({ list: [], total: 0, page: 1, size: 10 })

const verifyResult = ref(null)
/* 行展开时缓存的完整载荷：key 为交易ID */
const payloadCache = reactive({})

const regulatorNodes = ref([])

/* ---------------- 展示辅助 ---------------- */
function actionLabel(action) {
  if (!action) return '-'
  const hit = ACTIONS.find((item) => item.value === action)
  return hit ? hit.label : action
}

function resultType(result) {
  const text = String(result ?? '').toLowerCase()
  if (text === 'success' || text === 'ok' || text === '通过') return 'success'
  if (text === 'blocked' || text === '阻断') return 'warning'
  if (!text) return 'info'
  return 'danger'
}

function resultLabel(result) {
  if (!result) return '-'
  const text = String(result).toLowerCase()
  if (text === 'success' || text === 'ok') return '成功'
  if (text === 'blocked') return '已阻断'
  if (text === 'failed') return '失败'
  return String(result)
}

/** 防篡改签名仅展示前 12 位 */
function shortSignature(signature) {
  if (!signature) return '-'
  const text = String(signature)
  return text.length > 12 ? `${text.slice(0, 12)}…` : text
}

function nodeName(item) {
  if (typeof item === 'string') return item
  return item?.name || item?.code || '-'
}

function nodeRegion(item) {
  if (typeof item === 'string') return '监管查询节点'
  return item?.region || item?.org || '监管查询节点'
}

function nodeStatus(item) {
  if (typeof item === 'string') return ''
  return item?.status || ''
}

function payloadText(row) {
  const payload = payloadCache[row?.txId] ?? row?.payload ?? null
  if (payload === null || payload === undefined) return '载荷未返回，点击此行将按交易ID查询完整存证内容'
  if (typeof payload === 'string') {
    try {
      return JSON.stringify(JSON.parse(payload), null, 2)
    } catch (error) {
      return payload
    }
  }
  try {
    return JSON.stringify(payload, null, 2)
  } catch (error) {
    return String(payload)
  }
}

/* ---------------- 数据加载 ---------------- */
/** 存证统计与监管节点 */
async function loadStats() {
  try {
    const data = await auditApi.stats()
    stats.txTotal = data?.txTotal ?? 0
    stats.blockHeight = data?.blockHeight ?? 0
    stats.tps = data?.tps ?? 0
    stats.retentionYears = data?.retentionYears ?? 0
    regulatorNodes.value = data?.regulatorNodes ?? []
  } catch (error) {
    regulatorNodes.value = []
  }
}

function buildLogParams() {
  const params = { page: logs.page, size: logs.size }
  if (logQuery.actor) params.actor = logQuery.actor.trim()
  if (logQuery.action) params.action = logQuery.action
  if (logQuery.result) params.result = logQuery.result
  if (Array.isArray(logQuery.range) && logQuery.range.length === 2) {
    params.start = logQuery.range[0]
    params.end = logQuery.range[1]
  }
  return params
}

/** 审计日志检索 */
async function loadLogs() {
  loading.value = true
  try {
    const data = await auditApi.logs(buildLogParams())
    logs.list = data?.list ?? []
    logs.total = data?.total ?? 0
  } finally {
    loading.value = false
  }
}

/** 联盟链区块列表 */
async function loadChain() {
  chainLoading.value = true
  try {
    const data = await auditApi.chain({ page: chain.page, size: chain.size })
    chain.list = data?.list ?? []
    chain.total = data?.total ?? 0
  } finally {
    chainLoading.value = false
  }
}

/** 初始化加载：统计 + 日志 + 区块 */
async function load() {
  loading.value = true
  try {
    await Promise.all([loadStats(), loadLogs(), loadChain()])
  } finally {
    loading.value = false
  }
}

function handleLogSearch() {
  logs.page = 1
  loadLogs()
}

function handleLogReset() {
  logQuery.actor = ''
  logQuery.action = ''
  logQuery.range = []
  logQuery.result = ''
  logs.page = 1
  loadLogs()
}

function handleLogPageChange(page) {
  logs.page = page
  loadLogs()
}

function handleLogSizeChange(size) {
  logs.size = size
  logs.page = 1
  loadLogs()
}

function handleChainPageChange(page) {
  chain.page = page
  loadChain()
}

function handleChainSizeChange(size) {
  chain.size = size
  chain.page = 1
  loadChain()
}

/** 展开区块行时按交易ID拉取完整 payload */
async function handleExpandChange(row, expandedRows) {
  const isExpanded = Array.isArray(expandedRows) ? expandedRows.includes(row) : Boolean(expandedRows)
  const txId = row?.txId
  if (!isExpanded || !txId || payloadCache[txId]) return
  try {
    const data = await auditApi.chainDetail(txId)
    payloadCache[txId] = data?.payload ?? {}
  } catch (error) {
    payloadCache[txId] = { message: '该交易ID未查询到完整存证载荷' }
  }
}

/* ---------------- 链完整性校验 ---------------- */
async function handleVerifyChain() {
  verifying.value = true
  try {
    const data = await auditApi.verifyChain()
    verifyResult.value = {
      valid: Boolean(data?.valid),
      blocks: data?.blocks ?? 0,
      brokenAt: data?.brokenAt ?? null,
      checkedAt: data?.checkedAt
    }
    if (verifyResult.value.valid) {
      ElMessage.success(`链完整性校验通过，共校验 ${verifyResult.value.blocks} 个区块`)
    } else {
      ElMessage.error(`链完整性校验失败，断裂位置：${verifyResult.value.brokenAt || '未知'}`)
    }
  } finally {
    verifying.value = false
  }
}

/* ---------------- 载荷复制 ---------------- */
async function handleCopyPayload(row) {
  const text = payloadText(row)
  try {
    if (navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(text)
    } else {
      const area = document.createElement('textarea')
      area.value = text
      document.body.appendChild(area)
      area.select()
      document.execCommand('copy')
      document.body.removeChild(area)
    }
    ElMessage.success('载荷 JSON 已复制到剪贴板')
  } catch (error) {
    ElMessage.warning('当前浏览器环境不支持自动复制，请手动选择文本复制')
  }
}

onMounted(load)
