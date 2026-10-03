<template>
  <div class="fs-page">
    <!-- 页面头部 -->
    <div class="fs-page__header">
      <div>
        <h2 class="fs-page__title">数据溯源查询</h2>
        <p class="fs-page__subtitle">
          按数据 ID 追溯数据全生命周期流转路径、加工节点与合规检查结论，并查询细粒度溯源审计记录。
        </p>
      </div>
    </div>

    <!-- 查询区 -->
    <div class="fs-card">
      <div class="fs-card__body">
        <el-form :inline="true" @submit.prevent>
          <el-form-item label="数据ID/名称">
            <el-input
              v-model="query.keyword"
              placeholder="请输入数据 ID 或名称，回车查询"
              clearable
              style="width: 230px"
              @keyup.enter="handleSearch"
            >
              <template #prefix>
                <el-icon><Search /></el-icon>
              </template>
            </el-input>
          </el-form-item>
          <el-form-item label="操作类型">
            <el-select v-model="query.operation" placeholder="全部操作" clearable style="width: 150px">
              <el-option v-for="item in OPERATIONS" :key="item.value" :label="item.label" :value="item.value" />
            </el-select>
          </el-form-item>
          <el-form-item label="数据类型">
            <el-select v-model="query.dataType" placeholder="全部类型" clearable style="width: 150px">
              <el-option v-for="item in DATA_TYPES" :key="item.value" :label="item.label" :value="item.value" />
            </el-select>
          </el-form-item>
          <el-form-item>
            <el-button type="primary" :loading="loading" @click="handleSearch">
              <el-icon><Search /></el-icon>
              查询
            </el-button>
            <el-button @click="handleReset">重置</el-button>
          </el-form-item>
        </el-form>
      </div>
    </div>

    <!-- 溯源详情 -->
    <div v-if="detail.basic" class="fs-card">
      <div class="fs-card__header">
        <div class="fs-card__title">溯源详情</div>
        <el-button @click="handleExportDetail">
          <el-icon><Download /></el-icon>
          导出详情
        </el-button>
      </div>
      <div class="fs-card__body">
        <div class="fs-grid fs-grid--2">
          <!-- 基本信息 -->
          <div class="trace-block">
            <div class="trace-block__title">基本信息</div>
            <el-descriptions :column="1" border size="small">
              <el-descriptions-item label="数据ID">{{ detail.basic?.dataId || '-' }}</el-descriptions-item>
              <el-descriptions-item label="数据名称">{{ detail.basic?.name || '-' }}</el-descriptions-item>
              <el-descriptions-item label="数据分类">{{ dataTypeLabel(detail.basic?.type) }}</el-descriptions-item>
              <el-descriptions-item label="数据分级">
                <DataLevelTag v-if="detail.basic?.level" :level="detail.basic.level" />
                <span v-else>-</span>
              </el-descriptions-item>
              <el-descriptions-item label="创建时间">{{ formatTime(detail.basic?.createdAt) }}</el-descriptions-item>
              <el-descriptions-item label="修改时间">{{ formatTime(detail.basic?.updatedAt) }}</el-descriptions-item>
              <el-descriptions-item label="归属主体">{{ detail.basic?.owner || '-' }}</el-descriptions-item>
            </el-descriptions>
          </div>

          <!-- 合规检查结果 -->
          <div class="trace-block">
            <div class="trace-block__title">
              合规检查结果
              <span class="fs-muted">
                {{ compliancePassed }} / {{ detail.compliance.length }} 项通过
              </span>
            </div>
            <div v-if="detail.compliance.length" class="trace-compliance">
              <div v-for="(item, index) in detail.compliance" :key="index" class="trace-compliance__item">
                <el-tag :type="item?.passed ? 'success' : 'danger'" effect="light">
                  <el-icon>
                    <component :is="item?.passed ? 'CircleCheck' : 'CircleClose'" />
                  </el-icon>
                  {{ item?.label || '合规检查' }}
                </el-tag>
                <span class="fs-muted">{{ item?.standard || '-' }}</span>
              </div>
            </div>
            <el-empty v-else description="暂无合规检查结论" :image-size="70" />
          </div>
        </div>

        <!-- 流转路径 -->
        <div class="trace-block trace-block--full">
          <div class="trace-block__title">
            数据流转路径
            <span class="fs-muted">共 {{ detail.timeline.length }} 个节点</span>
          </div>
          <el-timeline v-if="detail.timeline.length">
            <el-timeline-item
              v-for="(item, index) in detail.timeline"
              :key="index"
              :timestamp="formatTime(item?.ts)"
              placement="top"
              :type="index === detail.timeline.length - 1 ? 'primary' : 'success'"
              :hollow="index !== detail.timeline.length - 1"
            >
              <div class="trace-timeline__title">{{ item?.node || '-' }}</div>
              <div class="trace-timeline__meta">
                <el-tag size="small" effect="plain">{{ item?.action || '-' }}</el-tag>
                <span class="fs-muted">操作人：{{ item?.operator || '-' }}</span>
              </div>
              <div v-if="item?.detail" class="trace-timeline__detail">{{ item.detail }}</div>
            </el-timeline-item>
          </el-timeline>
          <el-empty v-else description="暂无流转路径数据" :image-size="70" />
        </div>
      </div>
    </div>

    <div v-else class="fs-card">
      <div class="fs-card__body trace-placeholder">
        <el-empty
          :description="loading ? '正在加载溯源详情…' : '请输入数据ID并点击查询，查看该数据的流转路径与合规结论'"
          :image-size="90"
        />
      </div>
    </div>

    <!-- 溯源审计记录 -->
    <div class="fs-card">
      <div class="fs-card__header">
        <div class="fs-card__title">溯源审计记录</div>
        <div class="fs-page__actions">
          <span class="fs-muted">共 {{ audit.total }} 条</span>
          <el-button :disabled="!audit.list.length" @click="handleExportAudit">
            <el-icon><Download /></el-icon>
            导出溯源记录
          </el-button>
        </div>
      </div>
      <div class="fs-card__body">
        <el-table v-loading="loading" :data="audit.list" border stripe size="small">
          <el-table-column label="时间" width="164">
            <template #default="{ row }">{{ formatTime(row?.ts) }}</template>
          </el-table-column>
          <el-table-column prop="operator" label="操作人" width="140" show-overflow-tooltip />
          <el-table-column prop="role" label="角色" width="110" />
          <el-table-column label="操作类型" width="100">
            <template #default="{ row }">
              <el-tag size="small" effect="plain">{{ operationLabel(row?.operation) }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="dataId" label="数据ID" min-width="150" show-overflow-tooltip />
          <el-table-column label="数据类型" width="110">
            <template #default="{ row }">{{ dataTypeLabel(row?.dataType) }}</template>
          </el-table-column>
          <el-table-column prop="node" label="节点" min-width="130" show-overflow-tooltip />
          <el-table-column label="结果" width="90">
            <template #default="{ row }">
              <el-tag size="small" :type="isPassed(row?.result) ? 'success' : 'danger'">
                {{ resultLabel(row?.result) }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column label="风险分" width="96" align="center">
            <template #default="{ row }">
              <span :class="{ 'trace-risk--high': Number(row?.riskScore || 0) >= 70 }">
                {{ formatNumber(row?.riskScore ?? 0) }}
              </span>
            </template>
          </el-table-column>
          <el-table-column label="签名" width="150">
            <template #default="{ row }">
              <span class="fs-mono">{{ shortSign(row?.signature) }}</span>
            </template>
          </el-table-column>
          <template #empty>暂无溯源审计记录</template>
        </el-table>

        <div class="trace-pagination">
          <el-pagination
            background
            layout="total, sizes, prev, pager, next, jumper"
            :total="audit.total"
            :current-page="audit.page"
            :page-size="audit.size"
            :page-sizes="[10, 20, 50, 100]"
            @current-change="handlePageChange"
            @size-change="handleSizeChange"
          />
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
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
</script>

<style scoped>
.fs-page__actions {
  display: flex;
  align-items: center;
  gap: 10px;
}
.trace-placeholder {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 180px;
}
.trace-block {
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.trace-block--full {
  margin-top: 18px;
}
.trace-block__title {
  display: flex;
  align-items: center;
  gap: 10px;
  font-size: 14px;
  font-weight: 600;
}
.trace-compliance {
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.trace-compliance__item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  padding: 8px 12px;
  border: 1px solid var(--fs-border);
  border-radius: 8px;
  background: #fbfcfe;
}
.trace-timeline__title {
  font-weight: 600;
  font-size: 13px;
}
.trace-timeline__meta {
  margin-top: 6px;
  display: flex;
  align-items: center;
  gap: 10px;
  font-size: 12px;
}
.trace-timeline__detail {
  margin-top: 6px;
  color: var(--fs-text-secondary);
  font-size: 12px;
  line-height: 1.6;
}
.trace-risk--high {
  color: var(--fs-danger);
  font-weight: 600;
}
.trace-pagination {
  display: flex;
  justify-content: flex-end;
  margin-top: 14px;
}
</style>
