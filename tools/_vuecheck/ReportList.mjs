
/**
 * 报告记录管理（对应设计文档图 21）
 *
 * 交互说明：
 * - 筛选条件变更后自动回到第 1 页重新查询，避免停留在越界页码导致表格空白；
 * - 下载走 Blob 流，文件名优先取响应头 Content-Disposition（downloadResponse 已实现）；
 * - 导出列表接口同样返回 CSV 流，导出过程中禁用按钮防重复点击。
 */
import { onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { DocumentAdd, Download, Refresh, RefreshLeft, Search } from '@element-plus/icons-vue'
import { complianceApi } from '@/api'
import { useAppStore } from '@/store/app'
import { REPORT_STATUS, formatTime } from '@/utils/format'
import { downloadResponse } from '@/utils/download'

const router = useRouter()
const appStore = useAppStore()

const loading = ref(false)
const exporting = ref(false)
const downloadingId = ref(null)
const regeneratingId = ref(null)
const list = ref([])
const total = ref(0)

const query = reactive({
  status: '',
  type: '',
  range: [],
  page: 1,
  size: 10
})

const reportTypes = ref([])

function statusOf(status) {
  if (REPORT_STATUS[status]) return REPORT_STATUS[status]
  return { label: status || '未知', type: 'info' }
}

function sizeText(sizeKb) {
  const value = Number(sizeKb || 0)
  if (!value) return '-'
  if (value >= 1024) return `${(value / 1024).toFixed(2)} MB`
  return `${value} KB`
}

function goCreate() {
  router.push('/compliance/reports/create')
}

function goPreview(row) {
  if (!row?.id) {
    ElMessage.warning('该报告缺少 ID，无法预览')
    return
  }
  router.push(`/compliance/reports/${row.id}`)
}

/** 筛选变化后回到第 1 页 */
function onSearch() {
  query.page = 1
  load()
}

function onSizeChange() {
  query.page = 1
  load()
}

function onResetQuery() {
  query.status = ''
  query.type = ''
  query.range = []
  query.page = 1
  load()
}

async function onDownload(row) {
  downloadingId.value = row.id
  try {
    const response = await complianceApi.downloadReport(row.id)
    downloadResponse(response, `${row.code || 'compliance-report'}.md`)
    ElMessage.success('报告下载已开始')
  } catch (error) {
    // 请求拦截器已统一提示
  } finally {
    downloadingId.value = null
  }
}

async function onRegenerate(row) {
  regeneratingId.value = row.id
  try {
    await complianceApi.regenerateReport(row.id)
    ElMessage.success('已提交重新生成，稍后刷新查看最新状态')
    await load()
  } catch (error) {
    // 请求拦截器已统一提示
  } finally {
    regeneratingId.value = null
  }
}

async function onExport() {
  exporting.value = true
  try {
    const response = await complianceApi.exportReports()
    downloadResponse(response, 'compliance-reports.csv')
    ElMessage.success('报告列表导出已开始')
  } catch (error) {
    // 请求拦截器已统一提示
  } finally {
    exporting.value = false
  }
}

async function load() {
  loading.value = true
  try {
    const params = { page: query.page, size: query.size }
    if (query.status) params.status = query.status
    if (query.type) params.type = query.type
    const [start, end] = query.range ?? []
    if (start) params.start = start
    if (end) params.end = end
    const data = await complianceApi.reports(params)
    // 兼容数组与分页对象两种返回形态
    list.value = Array.isArray(data) ? data : data?.list ?? []
    total.value = Array.isArray(data) ? data.length : Number(data?.total ?? 0)
  } catch (error) {
    list.value = []
    total.value = 0
  } finally {
    loading.value = false
  }
}

async function loadTypes() {
  try {
    await appStore.loadMeta()
    reportTypes.value = appStore.reportTypes ?? []
  } catch (error) {
    reportTypes.value = []
  }
}

onMounted(() => {
  loadTypes()
  load()
})
