<template>
  <div class="fs-page">
    <div class="fs-page__header">
      <div>
        <h2 class="fs-page__title">合规报告管理</h2>
        <p class="fs-page__subtitle">
          统一管理监管报送报告：按状态、报告类型与生成时间筛选，支持预览、下载与重新生成；
          报告文件与区块存证 ID 关联，可供监管机构核验。
        </p>
      </div>
      <div class="fs-toolbar" style="margin-bottom: 0">
        <el-button :icon="Download" :loading="exporting" @click="onExport">导出列表</el-button>
        <el-button type="primary" :icon="DocumentAdd" @click="goCreate">生成合规报告</el-button>
      </div>
    </div>

    <div class="fs-card">
      <div class="fs-card__header">
        <span class="fs-card__title">报告记录</span>
        <el-button text :icon="Refresh" :loading="loading" @click="load">刷新</el-button>
      </div>
      <div class="fs-card__body">
        <div class="fs-toolbar">
          <el-select v-model="query.status" placeholder="报告状态" clearable style="width: 150px" @change="onSearch">
            <el-option v-for="(item, key) in REPORT_STATUS" :key="key" :label="item.label" :value="key" />
          </el-select>
          <el-select v-model="query.type" placeholder="报告类型" clearable filterable style="width: 220px" @change="onSearch">
            <el-option v-for="item in reportTypes" :key="item.code" :label="item.name" :value="item.code" />
          </el-select>
          <el-date-picker
            v-model="query.range"
            type="daterange"
            range-separator="至"
            start-placeholder="生成开始日期"
            end-placeholder="生成结束日期"
            value-format="YYYY-MM-DD"
            style="width: 280px"
            @change="onSearch"
          />
          <div class="fs-toolbar__right">
            <el-button :icon="RefreshLeft" @click="onResetQuery">重置</el-button>
            <el-button type="primary" :icon="Search" @click="onSearch">查询</el-button>
          </div>
        </div>

        <el-table v-loading="loading" :data="list" border stripe>
          <el-table-column prop="code" label="报告ID" width="190" show-overflow-tooltip>
            <template #default="{ row }">
              <span class="fs-mono">{{ row.code || '-' }}</span>
            </template>
          </el-table-column>
          <el-table-column prop="typeName" label="报告类型" min-width="220" show-overflow-tooltip>
            <template #default="{ row }">{{ row.typeName || row.type || '-' }}</template>
          </el-table-column>
          <el-table-column label="时间范围" min-width="220">
            <template #default="{ row }">
              <span>{{ formatTime(row.periodStart, false) }}</span>
              <span class="fs-muted"> ~ </span>
              <span>{{ formatTime(row.periodEnd, false) }}</span>
            </template>
          </el-table-column>
          <el-table-column prop="status" label="状态" width="110" align="center">
            <template #default="{ row }">
              <el-tag :type="statusOf(row.status).type" size="small">{{ statusOf(row.status).label }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="createdAt" label="生成时间" width="170">
            <template #default="{ row }">{{ formatTime(row.createdAt) }}</template>
          </el-table-column>
          <el-table-column prop="createdBy" label="生成人" width="130" show-overflow-tooltip>
            <template #default="{ row }">{{ row.createdBy || '-' }}</template>
          </el-table-column>
          <el-table-column prop="sizeKb" label="大小" width="110" align="right">
            <template #default="{ row }">{{ sizeText(row.sizeKb) }}</template>
          </el-table-column>
          <el-table-column label="操作" width="210" fixed="right">
            <template #default="{ row }">
              <el-button link type="primary" @click="goPreview(row)">预览</el-button>
              <el-button link type="primary" :loading="downloadingId === row.id" @click="onDownload(row)">下载</el-button>
              <el-button link type="warning" :loading="regeneratingId === row.id" @click="onRegenerate(row)">
                重新生成
              </el-button>
            </template>
          </el-table-column>
          <template #empty>
            <el-empty description="暂无报告记录，请点击右上角生成合规报告" :image-size="80" />
          </template>
        </el-table>

        <el-pagination
          v-model:current-page="query.page"
          v-model:page-size="query.size"
          :total="total"
          :page-sizes="[10, 20, 50]"
          layout="total, sizes, prev, pager, next, jumper"
          style="margin-top: 14px; justify-content: flex-end"
          @size-change="onSizeChange"
          @current-change="load"
        />
      </div>
    </div>
  </div>
</template>

<script setup>
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
</script>

<style scoped>
/* 窄屏下分页组件允许换行，避免页码与跳转输入框被挤压 */
@media (max-width: 900px) {
  :deep(.el-pagination) {
    flex-wrap: wrap;
    justify-content: flex-start !important;
  }
}
</style>
