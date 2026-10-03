<template>
  <div class="fs-page">
    <div class="fs-page__header">
      <div>
        <h2 class="fs-page__title">计算任务管理</h2>
        <p class="fs-page__subtitle">
          管理跨境隐私计算任务的全生命周期：创建、启动、暂停、取消与结果导出。
          所有任务的加密算法调用与参数流转都会写入审计日志并落链存证。
        </p>
      </div>
    </div>

    <div class="fs-card">
      <div class="fs-card__body">
        <!-- 筛选区：状态 / 类型 / 关键字，三个条件由后端统一过滤，避免前端二次筛选造成分页错乱 -->
        <div class="fs-toolbar">
          <el-select v-model="query.status" placeholder="任务状态" clearable style="width: 140px" @change="handleSearch">
            <el-option v-for="item in statusOptions" :key="item.value" :label="item.label" :value="item.value" />
          </el-select>

          <el-select v-model="query.type" placeholder="任务类型" clearable style="width: 160px" @change="handleSearch">
            <el-option v-for="item in typeOptions" :key="item.value" :label="item.label" :value="item.value" />
          </el-select>

          <el-input
            v-model="query.keyword"
            placeholder="任务名称 / 任务ID"
            clearable
            style="width: 220px"
            @keyup.enter="handleSearch"
            @clear="handleSearch"
          >
            <template #prefix>
              <el-icon><Search /></el-icon>
            </template>
          </el-input>

          <el-button type="primary" @click="handleSearch">
            <el-icon><Search /></el-icon>
            <span>查询</span>
          </el-button>

          <el-button @click="load">
            <el-icon><Refresh /></el-icon>
            <span>刷新</span>
          </el-button>

          <div class="fs-toolbar__right">
            <!-- 无选中任务时禁用导出，避免把「全部任务」误当成单任务审计日志导出 -->
            <el-button :disabled="!tasks.length" :loading="exporting" @click="handleExport(null)">
              <el-icon><Download /></el-icon>
              <span>导出任务记录</span>
            </el-button>
            <el-button type="primary" @click="router.push('/engine/create')">
              <el-icon><Plus /></el-icon>
              <span>新建计算任务</span>
            </el-button>
          </div>
        </div>

        <el-table v-loading="loading" :data="tasks" border stripe style="width: 100%">
          <el-table-column prop="code" label="任务ID" width="150" fixed>
            <template #default="{ row }">
              <span class="fs-mono">{{ row.code || '-' }}</span>
            </template>
          </el-table-column>

          <el-table-column prop="name" label="任务名称" min-width="200" show-overflow-tooltip>
            <template #default="{ row }">
              <span>{{ row.name || '-' }}</span>
            </template>
          </el-table-column>

          <el-table-column label="类型" width="140">
            <template #default="{ row }">
              <el-tag size="small" effect="plain">{{ typeLabel(row) }}</el-tag>
            </template>
          </el-table-column>

          <el-table-column label="合作节点" min-width="220">
            <template #default="{ row }">
              <!-- partners 为节点编码数组，后端可能返回空数组，统一做兜底 -->
              <template v-if="(row.partners || []).length">
                <el-tag
                  v-for="code in row.partners || []"
                  :key="code"
                  size="small"
                  type="info"
                  effect="plain"
                  style="margin: 2px 4px 2px 0"
                >
                  {{ nodeName(code) }}
                </el-tag>
              </template>
              <span v-else class="fs-muted">未指定</span>
            </template>
          </el-table-column>

          <el-table-column label="创建时间" width="170">
            <template #default="{ row }">
              <span>{{ formatTime(row.createdAt) }}</span>
            </template>
          </el-table-column>

          <el-table-column label="状态" width="110">
            <template #default="{ row }">
              <el-tag size="small" :type="statusOf(row.status).type">{{ statusOf(row.status).label }}</el-tag>
            </template>
          </el-table-column>

          <el-table-column label="进度" width="160">
            <template #default="{ row }">
              <el-progress
                :percentage="progressOf(row)"
                :stroke-width="10"
                :status="row.status === 'failed' ? 'exception' : row.status === 'finished' ? 'success' : undefined"
              />
            </template>
          </el-table-column>

          <el-table-column label="操作" width="250" fixed="right">
            <template #default="{ row }">
              <!-- 按任务状态渲染可用操作，避免出现「已完成任务还能暂停」这类非法调用 -->
              <template v-if="row.status === 'running'">
                <el-button link type="primary" @click="goResult(row)">查看</el-button>
                <el-button link type="warning" :loading="actingId === row.id" @click="handlePause(row)">暂停</el-button>
                <el-button link type="danger" :loading="actingId === row.id" @click="handleCancel(row)">取消</el-button>
              </template>

              <template v-else-if="row.status === 'finished'">
                <el-button link type="primary" @click="goResult(row)">查看</el-button>
                <el-button link type="success" :loading="exporting" @click="handleExport(row)">导出</el-button>
              </template>

              <template v-else-if="row.status === 'pending'">
                <el-button link type="success" :loading="actingId === row.id" @click="handleStart(row)">启动</el-button>
                <el-button link type="danger" :loading="actingId === row.id" @click="handleCancel(row)">取消</el-button>
              </template>

              <template v-else-if="row.status === 'failed'">
                <el-button link type="primary" :loading="actingId === row.id" @click="handleRerun(row)">重新计算</el-button>
              </template>

              <template v-else>
                <el-button link type="primary" @click="goResult(row)">查看</el-button>
                <el-button link type="warning" :loading="actingId === row.id" @click="handleStart(row)">启动</el-button>
              </template>
            </template>
          </el-table-column>

          <template #empty>
            <el-empty description="暂无计算任务，可点击右上角「新建计算任务」发起一次隐私计算" />
          </template>
        </el-table>

        <div style="display: flex; justify-content: flex-end; margin-top: 14px">
          <el-pagination
            v-model:current-page="query.page"
            v-model:page-size="query.size"
            :page-sizes="[10, 20, 50]"
            :total="total"
            layout="total, sizes, prev, pager, next, jumper"
            background
            @size-change="handleSizeChange"
            @current-change="handlePageChange"
          />
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
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
</script>

<style scoped>
.fs-toolbar .el-button + .el-button {
  margin-left: 0;
}
</style>
