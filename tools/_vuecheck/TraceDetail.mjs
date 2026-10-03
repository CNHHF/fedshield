
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { lineageApi } from '@/api'
import DataLevelTag from '@/components/DataLevelTag.vue'
import { formatNumber, formatTime } from '@/utils/format'
import { downloadResponse, exportCsv } from '@/utils/download'

/* ---------------- 字典 ---------------- */
const OPERATIONS = [
  { value: 'query', label: '查询' },
  { value: 'update', label: '修改' },
  { value: 'delete', label: '删除' },
  { value: 'export', label: '导出' }
]

const DATA_TYPES = [
  { value: 'user', label: '用户数据' },
  { value: 'transaction', label: '交易数据' },
  { value: 'list', label: '清单数据' }
]

/* ---------------- 状态 ---------------- */
const loading = ref(false)

const query = reactive({
  keyword: '',
  operation: '',
  dataType: ''
})

const detail = reactive({ basic: null, timeline: [], compliance: [] })

const audit = reactive({ list: [], total: 0, page: 1, size: 10 })

const compliancePassed = computed(() => detail.compliance.filter((item) => item?.passed).length)

/* ---------------- 展示辅助 ---------------- */
function dataTypeLabel(type) {
  if (!type) return '-'
  const hit = DATA_TYPES.find((item) => item.value === type)
  return hit ? hit.label : type
}

function operationLabel(operation) {
  if (!operation) return '-'
  const hit = OPERATIONS.find((item) => item.value === operation)
  return hit ? hit.label : operation
}

function isPassed(result) {
  const text = String(result ?? '').toLowerCase()
  return text === 'success' || text === 'pass' || text === 'passed' || text === '通过' || text === '成功'
}

function resultLabel(result) {
  if (result === undefined || result === null || result === '') return '-'
  if (isPassed(result)) return '成功'
  return String(result).toLowerCase() === 'failed' || String(result) === '失败' ? '失败' : String(result)
}

function shortSign(signature) {
  if (!signature) return '-'
  const text = String(signature)
  return text.length > 24 ? `${text.slice(0, 24)}…` : text
}

/* ---------------- 数据加载 ---------------- */
function buildAuditParams() {
  const params = { page: audit.page, size: audit.size }
  if (query.dataType) params.dataType = query.dataType
  if (query.operation) params.operation = query.operation
  // 后端区分 dataId 与名称检索：形如 data-xxxx 的输入按 ID 精确查询，其余按 ID 模糊匹配
  if (query.keyword) params.dataId = query.keyword.trim()
  return params
}

/** 加载审计记录（分页） */
async function loadAudit() {
  loading.value = true
  try {
    const data = await lineageApi.audit(buildAuditParams())
    audit.list = data?.list ?? []
    audit.total = data?.total ?? 0
  } finally {
    loading.value = false
  }
}

/** 加载溯源详情；无关键字时清空详情，仅展示审计记录 */
async function loadTrace() {
  const dataId = query.keyword.trim()
  if (!dataId) {
    detail.basic = null
    detail.timeline = []
    detail.compliance = []
    return
  }
  loading.value = true
  try {
    const data = await lineageApi.trace(dataId)
    detail.basic = data?.basic ?? null
    detail.timeline = data?.timeline ?? []
    detail.compliance = data?.compliance ?? []
    if (!detail.basic) {
      ElMessage.warning(`未查询到数据「${dataId}」的溯源详情，可尝试使用完整数据ID`)
    }
  } catch (error) {
    detail.basic = null
    detail.timeline = []
    detail.compliance = []
  } finally {
    loading.value = false
  }
}

async function handleSearch() {
  audit.page = 1
  await Promise.all([loadAudit(), loadTrace()])
}

function handleReset() {
  query.keyword = ''
  query.operation = ''
  query.dataType = ''
  audit.page = 1
  detail.basic = null
  detail.timeline = []
  detail.compliance = []
  loadAudit()
}

function handlePageChange(page) {
  audit.page = page
  loadAudit()
}

function handleSizeChange(size) {
  audit.size = size
  audit.page = 1
  loadAudit()
}

/* ---------------- 导出 ---------------- */
const AUDIT_COLUMNS = [
  { prop: 'ts', label: '时间', format: (value) => formatTime(value) },
  { prop: 'operator', label: '操作人' },
  { prop: 'role', label: '角色' },
  { prop: 'operation', label: '操作类型', format: (value) => operationLabel(value) },
  { prop: 'dataId', label: '数据ID' },
  { prop: 'dataType', label: '数据类型', format: (value) => dataTypeLabel(value) },
  { prop: 'node', label: '节点' },
  { prop: 'result', label: '结果', format: (value) => resultLabel(value) },
  { prop: 'riskScore', label: '风险分' },
  { prop: 'signature', label: '防篡改签名' }
]

/** 把接口数据映射为 CSV 列（含中文表头） */
function toCsvRows(list) {
  return list.map((row) => {
    const mapped = {}
    AUDIT_COLUMNS.forEach((column) => {
      const value = row?.[column.prop]
      mapped[column.prop] = column.format ? column.format(value) : value ?? ''
    })
    return mapped
  })
}

function csvColumns() {
  return AUDIT_COLUMNS.map((column) => ({ prop: column.prop, label: column.label }))
}

/** 导出溯源记录：优先调用后端导出接口，失败时用前端 CSV 兜底 */
async function handleExportAudit() {
  try {
    const response = await lineageApi.exportAudit(buildAuditParams())
    downloadResponse(response, '溯源审计记录.csv')
    ElMessage.success('溯源记录已开始下载')
    return
  } catch (error) {
    // 后端导出接口异常时走前端兜底导出
  }
  if (!audit.list.length) {
    ElMessage.warning('暂无可导出的审计记录')
    return
  }
  exportCsv(toCsvRows(audit.list), csvColumns(), `溯源审计记录-${Date.now()}.csv`)
  ElMessage.success('已使用当前页数据在前端导出 CSV')
}

/** 导出详情：基本信息 + 流转路径 + 合规检查结论，前端生成 CSV */
function handleExportDetail() {
  const rows = []
  const push = (label, value) => rows.push({ label, value })

  push('【基本信息】', '')
  push('数据ID', detail.basic?.dataId || '-')
  push('数据名称', detail.basic?.name || '-')
  push('数据分类', dataTypeLabel(detail.basic?.type))
  push('数据分级', detail.basic?.level || '-')
  push('创建时间', formatTime(detail.basic?.createdAt))
  push('修改时间', formatTime(detail.basic?.updatedAt))
  push('归属主体', detail.basic?.owner || '-')

  push('【流转路径】', '')
  if (detail.timeline.length) {
    detail.timeline.forEach((item, index) => {
      push(`节点${index + 1}`, `${formatTime(item?.ts)} | ${item?.node || '-'} | ${item?.action || '-'} | 操作人：${item?.operator || '-'} | ${item?.detail || ''}`)
    })
  } else {
    push('流转路径', '暂无数据')
  }

  push('【合规检查结果】', '')
  if (detail.compliance.length) {
    detail.compliance.forEach((item) => {
      push(item?.label || '合规项', `${item?.passed ? '通过' : '未通过'}（依据：${item?.standard || '-'}）`)
    })
  } else {
    push('合规检查', '暂无数据')
  }

  exportCsv(rows, [{ prop: 'label', label: '项目' }, { prop: 'value', label: '内容' }], `溯源详情-${detail.basic?.dataId || 'data'}.csv`)
  ElMessage.success('溯源详情已导出')
}

onMounted(() => {
  loadAudit()
})
