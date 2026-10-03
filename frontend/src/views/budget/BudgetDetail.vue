<template>
  <div class="fs-page">
    <div class="fs-page__header">
      <div>
        <h2 class="fs-page__title">预算分配明细与调整</h2>
        <p class="fs-page__subtitle">
          按项目查看隐私预算的额度、消耗与占比；单项额度调整需填写原因，项目间内部调整单次不得超过总预算的 10%，
          所有调整动作生成调整记录报告并落链存证。
        </p>
      </div>
      <el-button @click="load">
        <el-icon><Refresh /></el-icon>刷新
      </el-button>
    </div>

    <div class="fs-grid fs-grid--2">
      <!-- 左区：项目预算明细 -->
      <div class="fs-card">
        <div class="fs-card__header">
          <div class="fs-card__title">项目预算明细</div>
          <span class="fs-muted">总预算 {{ formatNumber(totalBudget, 2) }} 元</span>
        </div>
        <div class="fs-card__body">
          <el-table v-loading="loading" :data="items" border stripe empty-text="暂无项目预算数据">
            <el-table-column prop="project" label="项目" min-width="150" show-overflow-tooltip />
            <el-table-column label="类别" width="120">
              <template #default="{ row }">{{ categoryLabel(row.category) }}</template>
            </el-table-column>
            <el-table-column label="总额度" width="120" align="right">
              <template #default="{ row }">{{ formatNumber(row.total, 2) }}</template>
            </el-table-column>
            <el-table-column label="已使用" width="120" align="right">
              <template #default="{ row }">{{ formatNumber(row.used, 2) }}</template>
            </el-table-column>
            <el-table-column label="剩余" width="120" align="right">
              <template #default="{ row }">{{ formatNumber(row.remaining, 2) }}</template>
            </el-table-column>
            <el-table-column label="已用占比" min-width="160">
              <template #default="{ row }">
                <el-progress
                  :percentage="itemUsedPercent(row)"
                  :stroke-width="12"
                  :status="progressStatus(row)"
                  :format="(percent) => `${percent}%`"
                />
              </template>
            </el-table-column>
            <el-table-column label="级别" width="110">
              <template #default="{ row }">
                <DataLevelTag v-if="isDataLevel(row.level)" :level="row.level" />
                <el-tag v-else size="small" effect="plain">{{ row.level || '-' }}</el-tag>
              </template>
            </el-table-column>
            <el-table-column label="操作" width="90" fixed="right">
              <template #default="{ row }">
                <el-button link type="primary" size="small" @click="openAdjust(row)">调整</el-button>
              </template>
            </el-table-column>
          </el-table>
        </div>
      </div>

      <!-- 右区：项目间内部调整 -->
      <div class="fs-card">
        <div class="fs-card__header">
          <div class="fs-card__title">内部调整</div>
          <span class="fs-muted">单次上限 {{ formatNumber(maxTransfer, 2) }} 元（总预算 10%）</span>
        </div>
        <div class="fs-card__body">
          <el-form :model="transferForm" label-width="96px">
            <el-form-item label="调出项目">
              <el-select v-model="transferForm.fromProject" placeholder="请选择调出项目" style="width: 100%">
                <el-option
                  v-for="item in items"
                  :key="`from-${item.id}`"
                  :value="item.project"
                  :label="item.project"
                >
                  <div class="fs-option">
                    <span>{{ item.project }}</span>
                    <span class="fs-muted">剩余 {{ formatNumber(item.remaining, 2) }} 元</span>
                  </div>
                </el-option>
              </el-select>
            </el-form-item>
            <el-form-item label="调入项目">
              <el-select v-model="transferForm.toProject" placeholder="请选择调入项目" style="width: 100%">
                <el-option
                  v-for="item in items"
                  :key="`to-${item.id}`"
                  :value="item.project"
                  :label="item.project"
                >
                  <div class="fs-option">
                    <span>{{ item.project }}</span>
                    <span class="fs-muted">已用 {{ percentText(item.usedRatio) }}</span>
                  </div>
                </el-option>
              </el-select>
            </el-form-item>
            <el-form-item label="调整额度">
              <el-input-number
                v-model="transferForm.amount"
                :min="0"
                :max="maxTransfer"
                :step="1000"
                :precision="2"
                controls-position="right"
                style="width: 100%"
              />
              <div class="fs-muted fs-mt">
                不得超过总预算的 10%（{{ formatNumber(maxTransfer, 2) }} 元），超出将被阻止提交。
              </div>
            </el-form-item>
            <el-form-item label="备注">
              <el-input
                v-model="transferForm.note"
                maxlength="100"
                show-word-limit
                placeholder="如：反欺诈项目 ε 预算不足，由联合统计项目内部调剂"
              />
            </el-form-item>
            <el-form-item>
              <el-button type="primary" :loading="transferring" @click="submitTransfer">提交调整</el-button>
              <el-button @click="resetTransfer">重置</el-button>
            </el-form-item>
          </el-form>

          <el-alert type="info" :closable="false" show-icon>
            <template #title>内部调整说明</template>
            调整仅在同一预算池内的项目之间调剂，不改变预算总额；单次调整幅度受 10% 上限约束，
            避免因大额调剂导致某一项目的差分隐私预算被稀释而影响模型可用性。
          </el-alert>
        </div>
      </div>
    </div>

    <!-- 各项目 已使用/剩余 占比对比 -->
    <div class="fs-card">
      <div class="fs-card__header">
        <div class="fs-card__title">各项目已使用 / 剩余占比</div>
        <span class="fs-muted">占比为各项目总额度内的构成</span>
      </div>
      <div class="fs-card__body">
        <ChartBox :option="compareOption" :loading="loading" height="300" empty-text="暂无项目预算数据" />
      </div>
    </div>

    <!-- 调整记录报告 -->
    <div class="fs-card">
      <div class="fs-card__header">
        <div class="fs-card__title">调整记录报告</div>
        <el-button :disabled="!adjustments.length" @click="handleExport">
          <el-icon><Download /></el-icon>导出调整记录
        </el-button>
      </div>
      <div class="fs-card__body">
        <el-table v-loading="loading" :data="adjustments" border stripe empty-text="暂无调整记录">
          <el-table-column label="调整编号" width="160">
            <template #default="{ row }">
              <span class="fs-mono">{{ row.code || '-' }}</span>
            </template>
          </el-table-column>
          <el-table-column prop="fromProject" label="调出项目" min-width="150">
            <template #default="{ row }">{{ row.fromProject || '-' }}</template>
          </el-table-column>
          <el-table-column prop="toProject" label="调入项目" min-width="150">
            <template #default="{ row }">{{ row.toProject || '-' }}</template>
          </el-table-column>
          <el-table-column label="调整额度" width="150" align="right">
            <template #default="{ row }">{{ formatNumber(row.amount || 0, 2) }} 元</template>
          </el-table-column>
          <el-table-column prop="operator" label="操作人" width="140">
            <template #default="{ row }">{{ row.operator || '-' }}</template>
          </el-table-column>
          <el-table-column label="调整时间" width="180">
            <template #default="{ row }">{{ formatTime(row.createdAt) }}</template>
          </el-table-column>
          <el-table-column label="备注" min-width="180">
            <template #default="{ row }">{{ row.note || '-' }}</template>
          </el-table-column>
        </el-table>
      </div>
    </div>

    <!-- 单项额度调整 -->
    <el-dialog v-model="adjustVisible" title="调整项目预算额度" width="520px" destroy-on-close>
      <el-form ref="adjustFormRef" :model="adjustForm" :rules="adjustRules" label-width="110px">
        <el-form-item label="项目名称">
          <el-input :model-value="adjustForm.project" disabled />
        </el-form-item>
        <el-form-item label="已使用额度">
          <el-input :model-value="`${formatNumber(adjustForm.used, 2)} 元`" disabled />
        </el-form-item>
        <el-form-item label="调整后总额度" prop="total">
          <el-input-number
            v-model="adjustForm.total"
            :min="0"
            :max="100000000"
            :step="10000"
            :precision="2"
            controls-position="right"
            style="width: 100%"
          />
          <div class="fs-muted fs-mt">
            调整后总额度不得低于已使用额度（{{ formatNumber(adjustForm.used, 2) }} 元），
            调整后剩余 {{ formatNumber(Math.max(adjustForm.total - adjustForm.used, 0), 2) }} 元。
          </div>
        </el-form-item>
        <el-form-item label="调整原因" prop="reason">
          <el-input
            v-model="adjustForm.reason"
            type="textarea"
            :rows="3"
            maxlength="150"
            show-word-limit
            placeholder="如：业务量增长需追加 ε 预算 / 项目结项回收剩余额度"
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="adjustVisible = false">取消</el-button>
        <el-button type="primary" :loading="adjustSubmitting" @click="submitAdjust">确认调整</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
/**
 * 预算分配明细与调整（对应文档图32 / 图34）
 * 左：项目预算明细 + 单项额度调整；右：项目间内部调整（≤ 总预算 10%）；
 * 下：调整记录报告（可导出 CSV）+ 各项目已使用/剩余占比对比图
 */
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { budgetApi } from '@/api'
import { useAppStore } from '@/store/app'
import { baseChartOption, formatNumber, formatPercent, formatTime } from '@/utils/format'
import { exportCsv } from '@/utils/download'
import ChartBox from '@/components/ChartBox.vue'
import DataLevelTag from '@/components/DataLevelTag.vue'

const appStore = useAppStore()

const loading = ref(false)
const transferring = ref(false)
const adjustSubmitting = ref(false)

const items = ref([])
const adjustments = ref([])
const overviewTotal = ref(0)

const adjustVisible = ref(false)
const adjustFormRef = ref(null)
const adjustForm = reactive({ id: null, project: '', used: 0, total: 0, reason: '' })

const transferForm = reactive({ fromProject: '', toProject: '', amount: 0, note: '' })

const adjustRules = {
  total: [{ required: true, type: 'number', message: '请填写调整后的总额度', trigger: 'change' }],
  reason: [{ required: true, message: '请填写调整原因（用于审计存证）', trigger: 'blur' }]
}

/* ---------------- 计算与格式化 ---------------- */
const categoryOptions = computed(() => appStore.budgetCategories ?? [])

function categoryLabel(code) {
  if (!code) return '-'
  return categoryOptions.value.find((item) => item.code === code)?.name || code
}

/** 总预算：优先取概览总额，概览不可用时退化为各项目额度之和 */
const totalBudget = computed(() => {
  const fromOverview = Number(overviewTotal.value || 0)
  if (fromOverview > 0) return fromOverview
  return items.value.reduce((sum, item) => sum + Number(item.total || 0), 0)
})

/** 项目间内部调整上限：总预算的 10% */
const maxTransfer = computed(() => Number((totalBudget.value * 0.1).toFixed(2)))

/** 占比归一化：兼容 0~1 比率与 0~100 百分数两种口径，输出 0~100 的数值 */
function ratioToPercent(value) {
  const num = Number(value ?? 0)
  if (!Number.isFinite(num)) return 0
  return Math.min(100, Math.max(0, Math.abs(num) > 1 ? num : num * 100))
}

function itemUsedPercent(row) {
  if (row?.usedRatio !== undefined && row?.usedRatio !== null && row?.usedRatio !== '') {
    return Number(ratioToPercent(row.usedRatio).toFixed(2))
  }
  // 后端未返回占比时按 已使用 / 总额度 前端计算，避免进度条空白
  const total = Number(row?.total || 0)
  if (!total) return 0
  return Number(((Number(row?.used || 0) / total) * 100).toFixed(2))
}

function percentText(value, precision = 1) {
  return formatPercent(ratioToPercent(value) / 100, precision)
}

/** 已用占比达到 90% 视为异常（预算即将耗尽），75% 起预警 */
function progressStatus(row) {
  const percent = itemUsedPercent(row)
  if (percent >= 90) return 'exception'
  if (percent >= 75) return 'warning'
  return ''
}

function isDataLevel(level) {
  return ['P1', 'P2', 'P3'].includes(level)
}

/** 项目预算明细：字段全量兜底，避免后端缺字段导致模板取值异常 */
function normalizeItem(item) {
  const total = Number(item?.total || 0)
  const used = Number(item?.used || 0)
  const remaining = item?.remaining === undefined || item?.remaining === null ? total - used : Number(item.remaining)
  return {
    id: item?.id ?? item?.code ?? item?.project,
    project: item?.project || item?.name || '-',
    category: item?.category || '',
    total,
    used,
    remaining: Number.isFinite(remaining) ? remaining : 0,
    usedRatio: item?.usedRatio ?? null,
    level: item?.level || '',
    updatedAt: item?.updatedAt || ''
  }
}

/* ---------------- 图表：各项目已使用/剩余占比 ---------------- */
const compareOption = computed(() => {
  const projects = items.value.map((item) => item.project)
  const usedPercent = items.value.map((item) => itemUsedPercent(item))
  const remainPercent = usedPercent.map((value) => Number((100 - value).toFixed(2)))
  return baseChartOption({
    tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' }, valueFormatter: (value) => `${value}%` },
    xAxis: { type: 'category', data: projects, axisLabel: { interval: 0, rotate: projects.length > 5 ? 18 : 0 } },
    yAxis: { type: 'value', min: 0, max: 100, axisLabel: { formatter: '{value}%' } },
    series: [
      { name: '已使用占比', type: 'bar', stack: 'ratio', barWidth: 26, data: usedPercent },
      {
        name: '剩余占比',
        type: 'bar',
        stack: 'ratio',
        barWidth: 26,
        itemStyle: { borderRadius: [4, 4, 0, 0] },
        data: remainPercent
      }
    ]
  })
})

/* ---------------- 数据加载 ---------------- */
async function load() {
  loading.value = true
  try {
    // 明细与调整记录是页面主体数据；概览总额仅用于计算 10% 上限，失败时退化为明细之和
    const [itemList, adjustmentList] = await Promise.all([budgetApi.items(), budgetApi.adjustments()])
    const rawItems = Array.isArray(itemList) ? itemList : itemList?.list ?? []
    items.value = (rawItems ?? []).map((item) => normalizeItem(item))
    adjustments.value = Array.isArray(adjustmentList) ? adjustmentList : adjustmentList?.list ?? []
  } catch (error) {
    // 接口异常时保持空态，页面不崩溃
    items.value = []
    adjustments.value = []
  } finally {
    loading.value = false
  }
  try {
    const overviewData = await budgetApi.overview()
    overviewTotal.value = Number(overviewData?.total || 0)
  } catch (error) {
    overviewTotal.value = 0
  }
}

/* ---------------- 单项额度调整 ---------------- */
function openAdjust(row) {
  adjustForm.id = row.id
  adjustForm.project = row.project
  adjustForm.used = Number(row.used || 0)
  adjustForm.total = Number(row.total || 0)
  adjustForm.reason = ''
  adjustVisible.value = true
  adjustFormRef.value?.clearValidate()
}

async function submitAdjust() {
  if (!adjustFormRef.value) return
  try {
    await adjustFormRef.value.validate()
  } catch (error) {
    return
  }
  // 业务兜底：下调额度不得低于已消耗额度，否则会造成已用占比超过 100%
  if (Number(adjustForm.total) < Number(adjustForm.used)) {
    ElMessage.warning(`调整后总额度不得低于已使用额度 ${formatNumber(adjustForm.used, 2)} 元`)
    return
  }
  adjustSubmitting.value = true
  try {
    const data = await budgetApi.adjustItem(adjustForm.id, {
      total: Number(adjustForm.total),
      reason: adjustForm.reason
    })
    ElMessage.success(
      `额度调整成功，剩余额度 ${formatNumber(data?.remaining ?? 0, 2)} 元（已生成调整记录）`
    )
    adjustVisible.value = false
    await load()
  } catch (error) {
    // 请求层已统一提示错误
  } finally {
    adjustSubmitting.value = false
  }
}

/* ---------------- 项目间内部调整 ---------------- */
function resetTransfer() {
  transferForm.fromProject = ''
  transferForm.toProject = ''
  transferForm.amount = 0
  transferForm.note = ''
}

async function submitTransfer() {
  if (!transferForm.fromProject) {
    ElMessage.warning('请选择调出项目')
    return
  }
  if (!transferForm.toProject) {
    ElMessage.warning('请选择调入项目')
    return
  }
  if (transferForm.fromProject === transferForm.toProject) {
    ElMessage.warning('调出项目与调入项目不能相同')
    return
  }
  if (!transferForm.amount || Number(transferForm.amount) <= 0) {
    ElMessage.warning('请填写大于 0 的调整额度')
    return
  }
  // 硬性规则：内部调整单次不得超过总预算的 10%（后端同样校验）
  if (Number(transferForm.amount) > maxTransfer.value) {
    ElMessage.warning(
      `内部调整单次不得超过总预算的 10%，当前上限为 ${formatNumber(maxTransfer.value, 2)} 元`
    )
    return
  }
  const from = items.value.find((item) => item.project === transferForm.fromProject)
  if (from && Number(transferForm.amount) > Number(from.remaining || 0)) {
    ElMessage.warning(`调出项目剩余额度仅 ${formatNumber(from.remaining, 2)} 元，不足以调出`)
    return
  }

  transferring.value = true
  try {
    await budgetApi.transfer({
      fromProject: transferForm.fromProject,
      toProject: transferForm.toProject,
      amount: Number(transferForm.amount),
      note: transferForm.note
    })
    ElMessage.success('内部调整已完成，调整记录已生成')
    resetTransfer()
    await load()
  } catch (error) {
    // 请求层已统一提示错误
  } finally {
    transferring.value = false
  }
}

/* ---------------- 调整记录导出 ---------------- */
const ADJUST_COLUMNS = [
  { label: '调整编号', prop: 'code' },
  { label: '调出项目', prop: 'fromProject' },
  { label: '调入项目', prop: 'toProject' },
  { label: '调整额度（元）', prop: (row) => formatNumber(row.amount || 0, 2) },
  { label: '操作人', prop: 'operator' },
  { label: '调整时间', prop: (row) => formatTime(row.createdAt) },
  { label: '备注', prop: 'note' }
]

function handleExport() {
  if (!adjustments.value.length) {
    ElMessage.warning('暂无调整记录可导出')
    return
  }
  exportCsv(adjustments.value, ADJUST_COLUMNS, `预算调整记录_${Date.now()}.csv`)
  ElMessage.success('调整记录已导出')
}

onMounted(async () => {
  try {
    // 项目类别字典来自元数据接口
    await appStore.loadMeta()
  } catch (error) {
    // 元数据失败时类别列回退展示原始编码
  }
  await load()
})
</script>

<style scoped>
.fs-option {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}
.fs-mt {
  margin-top: 6px;
}
</style>
