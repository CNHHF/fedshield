
import { computed, onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { engineApi } from '@/api'
import { useAppStore } from '@/store/app'
import { TASK_STATUS, TASK_TYPE, dictOf, formatTime } from '@/utils/format'
import { downloadResponse } from '@/utils/download'

const router = useRouter()
const appStore = useAppStore()

const loading = ref(false)
const exporting = ref(false)
// 记录正在执行状态流转的任务 id，用于只抖动当前行的按钮 loading
const actingId = ref(null)
const tasks = ref([])
const total = ref(0)

const query = reactive({
  status: '',
  type: '',
  keyword: '',
  page: 1,
  size: 10
})

// 任务类型下拉：优先用后端字典，后端未返回时退回本地字典，保证页面永远有可选项
const typeOptions = computed(() => {
  const remote = (appStore.taskTypes || []).map((item) => ({
    value: item.code,
    label: item.name || TASK_TYPE[item.code]?.label || item.code
  }))
  if (remote.length) return remote
  return Object.entries(TASK_TYPE).map(([value, meta]) => ({ value, label: meta.label }))
})

// 状态下拉：不提供「已取消」筛选（取消属终态，历史记录仍会在列表全量中出现）
const statusOptions = computed(() =>
  Object.entries(TASK_STATUS)
    .filter(([value]) => value !== 'canceled')
    .map(([value, meta]) => ({ value, label: meta.label }))
)

function statusOf(status) {
  return dictOf(TASK_STATUS, status, '未知')
}

function typeLabel(row) {
  if (row.typeName) return row.typeName
  if (TASK_TYPE[row.type]) return TASK_TYPE[row.type].label
  return appStore.taskTypeName(row.type) || row.type || '-'
}

function nodeName(code) {
  return appStore.nodeName(code) || code
}

// 进度兜底并夹紧到 0~100，避免后端返回 null 或超过 100 时 el-progress 报错
function progressOf(row) {
  const value = Number(row.progress ?? 0)
  if (Number.isNaN(value)) return 0
  return Math.min(100, Math.max(0, Math.round(value)))
}

async function load() {
  loading.value = true
  try {
    const data = await engineApi.tasks({
      page: query.page,
      size: query.size,
      status: query.status || undefined,
      type: query.type || undefined,
      keyword: query.keyword || undefined
    })
    // 后端可能返回数组或分页对象，两种形态都做兼容，避免 undefined.xxx
    tasks.value = Array.isArray(data) ? data : data?.list ?? []
    total.value = Array.isArray(data) ? data.length : data?.total ?? tasks.value.length
  } catch (error) {
    // 请求层的拦截器已弹出错误提示，这里只需保证列表回到可用状态
    tasks.value = []
    total.value = 0
  } finally {
    loading.value = false
  }
}

function handleSearch() {
  query.page = 1
  load()
}

function handleSizeChange() {
  query.page = 1
  load()
}

// 分页组件清空页号时会传 undefined，这里做保护避免带非法页码请求
function handlePageChange(page) {
  if (!page) return
  load()
}

function goResult(row) {
  router.push(`/engine/result/${row.id}`)
}

/** 通用状态流转：调用后端接口 → 提示 → 重新拉取列表，保证表格状态与后端一致 */
async function runAction(id, action, successText) {
  actingId.value = id
  try {
    await action()
    ElMessage.success(successText)
    await load()
    return true
  } catch (error) {
    return false
  } finally {
    actingId.value = null
  }
}

function handleStart(row) {
  runAction(row.id, () => engineApi.startTask(row.id), `任务 ${row.code || ''} 已启动，正在建立加密计算通道`)
}

function handlePause(row) {
  runAction(row.id, () => engineApi.pauseTask(row.id), `任务 ${row.code || ''} 已暂停`)
}

function handleRerun(row) {
  runAction(row.id, () => engineApi.rerunTask(row.id), `任务 ${row.code || ''} 已提交重新计算`)
}

async function handleCancel(row) {
  try {
    await ElMessageBox.confirm(
      `取消后任务 ${row.code || ''} 的密文会话将立即终止，已消耗的隐私预算不予退回，是否继续？`,
      '取消任务确认',
      { type: 'warning', confirmButtonText: '确认取消', cancelButtonText: '返回' }
    )
  } catch (error) {
    return // 用户主动放弃，不做任何请求
  }
  runAction(row.id, () => engineApi.cancelTask(row.id), `任务 ${row.code || ''} 已取消`)
}

/** 导出加密审计日志 CSV：engineApi.exportTask 以任务 id 为参数，row 为空时取列表首条任务 */
async function handleExport(row) {
  const targetId = row?.id ?? tasks.value[0]?.id
  if (!targetId) {
    ElMessage.warning('暂无可导出的任务记录')
    return
  }
  exporting.value = true
  try {
    const response = await engineApi.exportTask(targetId)
    downloadResponse(response, `fedshield-任务记录-${row?.code || targetId}.csv`)
    ElMessage.success('任务记录导出已开始下载')
  } catch (error) {
    ElMessage.error('导出失败，请稍后重试')
  } finally {
    exporting.value = false
  }
}

onMounted(async () => {
  // 节点名称用于表格「合作节点」列的可读展示，元数据失败不影响任务列表本身
  try {
    await appStore.loadMeta()
  } catch (error) {
    // 忽略：列表仍可用任务自带的 partners 编码展示
  }
  load()
})
