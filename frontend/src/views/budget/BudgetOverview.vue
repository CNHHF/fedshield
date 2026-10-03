<template>
  <div class="fs-page">
    <div class="fs-page__header">
      <div>
        <h2 class="fs-page__title">隐私预算管理</h2>
        <p class="fs-page__subtitle">
          差分隐私预算按项目动态分配与消耗监控：预算不足时计算任务将被直接阻断（错误码 5001），
          因此需要按项目跟踪消耗趋势、及时申请追加额度。
        </p>
      </div>
      <el-button type="primary" @click="openApplication">
        <el-icon><Plus /></el-icon>新增预算申请
      </el-button>
    </div>

    <!-- 概览指标：总额度 / 已消耗 / 剩余额度 / 剩余占比 -->
    <div class="fs-grid fs-grid--4">
      <StatCard
        label="预算总额度"
        :value="formatNumber(overview.total || 0)"
        unit="元"
        icon="Wallet"
        color="#1f5fd8"
        tip="各项目隐私预算（ε 折算额度）之和"
      />
      <StatCard
        label="已消耗额度"
        :value="formatNumber(overview.used || 0)"
        unit="元"
        icon="TrendCharts"
        color="#f5a623"
        :sub="`本月新增消耗 ${formatNumber(overview.monthUsed || 0)} 元`"
      />
      <StatCard
        label="剩余额度"
        :value="formatNumber(overview.remaining || 0)"
        unit="元"
        icon="Coin"
        color="#14a37f"
      />
      <StatCard
        label="剩余占比"
        :value="percentText(overview.remainingRatio)"
        icon="PieChart"
        color="#8b5cf6"
        :sub="`已消耗占比 ${percentText(overview.usedRatio)}`"
      />
    </div>

    <!-- 预算预警：来自 /api/budget/overview 的 alerts -->
    <div v-if="alertRows.length" class="fs-card">
      <div class="fs-card__header">
        <div class="fs-card__title">预算预警</div>
        <span class="fs-muted">共 {{ alertRows.length }} 条</span>
      </div>
      <div class="fs-card__body">
        <el-alert
          v-for="(item, index) in alertRows"
          :key="index"
          :type="alertType(item.level)"
          :closable="false"
          show-icon
          class="fs-budget-alert"
        >
          <template #title>
            <span class="fs-budget-alert__head">
              <span>{{ item.title }}</span>
              <el-button link type="primary" size="small" @click="goDetail">查看明细</el-button>
            </span>
          </template>
          <span>{{ item.content }}</span>
        </el-alert>
      </div>
    </div>

    <!-- 组合图：近 6 个月 已消耗/剩余 堆叠柱 + 消耗占比折线；环形图：预算构成 -->
    <div class="fs-grid fs-grid--2 fs-mt">
      <div class="fs-card">
        <div class="fs-card__header">
          <div class="fs-card__title">近 6 个月预算消耗与占比</div>
          <span class="fs-muted">柱：额度（元） / 线：消耗占比</span>
        </div>
        <div class="fs-card__body">
          <ChartBox :option="comboOption" :loading="loading" height="320" empty-text="暂无预算趋势数据" />
        </div>
      </div>
      <div class="fs-card">
        <div class="fs-card__header">
          <div class="fs-card__title">预算构成</div>
          <span class="fs-muted">按项目类别汇总</span>
        </div>
        <div class="fs-card__body">
          <ChartBox :option="compositionOption" :loading="loading" height="320" empty-text="暂无预算构成数据" />
        </div>
      </div>
    </div>

    <div class="fs-card">
      <div class="fs-card__header">
        <div class="fs-card__title">消耗趋势</div>
        <span class="fs-muted">面积图：逐月已消耗额度</span>
      </div>
      <div class="fs-card__body">
        <ChartBox :option="areaOption" :loading="loading" height="280" empty-text="暂无消耗趋势数据" />
      </div>
    </div>

    <!-- 预算申请记录 -->
    <div class="fs-card">
      <div class="fs-card__header">
        <div class="fs-card__title">预算申请记录</div>
        <el-button :loading="appLoading" @click="loadApplications">
          <el-icon><Refresh /></el-icon>刷新
        </el-button>
      </div>
      <div class="fs-card__body">
        <el-table v-loading="appLoading" :data="applicationRows" border stripe empty-text="暂无预算申请记录">
          <el-table-column label="申请ID" width="150">
            <template #default="{ row }">
              <span class="fs-mono">{{ row.code || '-' }}</span>
            </template>
          </el-table-column>
          <el-table-column prop="project" label="项目名称" min-width="170" />
          <el-table-column label="项目类别" width="150">
            <template #default="{ row }">{{ categoryLabel(row.category) }}</template>
          </el-table-column>
          <el-table-column label="申请额度" width="150" align="right">
            <template #default="{ row }">{{ formatNumber(row.amount || 0, 2) }} 元</template>
          </el-table-column>
          <el-table-column label="状态" width="110">
            <template #default="{ row }">
              <el-tag size="small" :type="appStatus(row.status).type" effect="light">
                {{ appStatus(row.status).label }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="applicant" label="申请人" width="130" />
          <el-table-column label="申请时间" width="180">
            <template #default="{ row }">{{ formatTime(row.createdAt) }}</template>
          </el-table-column>
          <el-table-column label="操作" width="150" fixed="right">
            <template #default="{ row }">
              <!-- 仅待审批状态可操作，避免重复审批造成额度重复入账 -->
              <template v-if="row.status === 'pending'">
                <el-button link type="success" size="small" @click="handleApprove(row)">审批</el-button>
                <el-button link type="danger" size="small" @click="handleReject(row)">驳回</el-button>
              </template>
              <span v-else class="fs-muted">已处理</span>
            </template>
          </el-table-column>
        </el-table>

        <div class="fs-pager">
          <el-pagination
            v-model:current-page="query.page"
            v-model:page-size="query.size"
            :total="appTotal"
            :page-sizes="[10, 20, 50]"
            layout="total, sizes, prev, pager, next, jumper"
            background
            @current-change="loadApplications"
            @size-change="searchApplications"
          />
        </div>
      </div>
    </div>

    <!-- 新增预算申请 -->
    <el-dialog v-model="dialogVisible" title="新增预算申请" width="620px" destroy-on-close>
      <el-form ref="appFormRef" :model="appForm" :rules="appRules" label-width="110px">
        <el-form-item label="项目名称" prop="project">
          <el-input v-model="appForm.project" maxlength="60" placeholder="如：反欺诈模型联合训练" />
        </el-form-item>
        <el-form-item label="项目类别" prop="category">
          <el-select v-model="appForm.category" placeholder="请选择预算项目类别" style="width: 100%">
            <el-option
              v-for="item in categoryOptions"
              :key="item.code"
              :value="item.code"
              :label="item.name"
            >
              <div class="fs-option">
                <span>{{ item.name }}</span>
                <span class="fs-muted">{{ item.desc || '' }}</span>
              </div>
            </el-option>
          </el-select>
        </el-form-item>
        <el-form-item label="申请额度" prop="amount">
          <el-input-number
            v-model="appForm.amount"
            :min="0"
            :max="100000000"
            :step="10000"
            :precision="2"
            controls-position="right"
            style="width: 100%"
          />
          <div class="fs-muted fs-mt">单位：元；额度最终以审批后的项目预算为准。</div>
        </el-form-item>
        <el-form-item label="申请理由" prop="reason">
          <el-input
            v-model="appForm.reason"
            type="textarea"
            :rows="3"
            maxlength="200"
            show-word-limit
            placeholder="说明业务场景、预计计算任务量、合规依据等"
          />
        </el-form-item>
        <el-form-item label="期望生效时间" prop="expectedAt">
          <el-date-picker
            v-model="appForm.expectedAt"
            type="date"
            value-format="YYYY-MM-DD"
            placeholder="选择期望生效日期"
            style="width: 100%"
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="submitting" @click="submitApplication">提交申请</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
/**
 * 隐私预算管理（对应文档图31 / 图33）
 * 概览指标 + 消耗趋势（组合图/面积图）+ 预算构成环形图 + 预算预警 + 申请记录与审批
 */
import { computed, onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { budgetApi } from '@/api'
import { useAppStore } from '@/store/app'
import { ALERT_LEVEL, baseChartOption, dictOf, formatNumber, formatPercent, formatTime } from '@/utils/format'
import ChartBox from '@/components/ChartBox.vue'
import StatCard from '@/components/StatCard.vue'

const router = useRouter()
const appStore = useAppStore()

const loading = ref(false)
const appLoading = ref(false)
const submitting = ref(false)

const overview = ref({})
const trend = ref({ months: [], used: [], remaining: [], usedRatio: [] })
const applicationRows = ref([])
const appTotal = ref(0)
const query = reactive({ page: 1, size: 10 })

const dialogVisible = ref(false)
const appFormRef = ref(null)
const appForm = reactive({ project: '', category: '', amount: 0, reason: '', expectedAt: '' })

const appRules = {
  project: [{ required: true, message: '请填写项目名称', trigger: 'blur' }],
  category: [{ required: true, message: '请选择项目类别', trigger: 'change' }],
  amount: [{ required: true, type: 'number', min: 1, message: '申请额度需大于 0', trigger: 'change' }],
  reason: [{ required: true, message: '请填写申请理由', trigger: 'blur' }],
  expectedAt: [{ required: true, message: '请选择期望生效时间', trigger: 'change' }]
}

/** 预算申请状态字典（后端未在 API.md 中固定枚举，这里做展示兜底） */
const APP_STATUS = {
  pending: { label: '待审批', type: 'warning' },
  approved: { label: '已通过', type: 'success' },
  rejected: { label: '已驳回', type: 'danger' },
  canceled: { label: '已取消', type: 'info' }
}

function appStatus(status) {
  return APP_STATUS[status] || { label: status || '-', type: 'info' }
}

const categoryOptions = computed(() => appStore.budgetCategories ?? [])

function categoryLabel(code) {
  if (!code) return '-'
  return categoryOptions.value.find((item) => item.code === code)?.name || code
}

/**
 * 百分比口径兼容：后端可能返回 0~1 的比率，也可能返回 0~100 的百分数，
 * 统一归一化后复用 format.js 的 formatPercent，保证全站格式一致。
 */
function percentText(value, precision = 1) {
  const num = Number(value ?? 0)
  if (!Number.isFinite(num)) return '-'
  const ratio = Math.abs(num) > 1 ? num / 100 : num
  return formatPercent(ratio, precision)
}

function ratioToNumber(value) {
  const num = Number(value ?? 0)
  if (!Number.isFinite(num)) return 0
  return Number((Math.abs(num) > 1 ? num : num * 100).toFixed(2))
}

/** el-alert 不支持 danger 类型，这里把 ALERT_LEVEL 的 danger 映射为 error */
function alertType(level) {
  const type = dictOf(ALERT_LEVEL, level).type
  return type === 'danger' ? 'error' : type
}

const alertRows = computed(() => {
  const list = overview.value.alerts
  const rows = Array.isArray(list) ? list : []
  return rows.map((item) => {
    // 后端可能直接返回字符串提示，这里统一成 { title, content, level }
    const record = typeof item === 'string' ? { title: item } : item || {}
    return {
      level: record.level || 'medium',
      title: record.title || record.project || record.code || '预算预警',
      content: record.content || record.message || record.remark || '该项目预算接近或低于阈值，请评估是否追加额度。'
    }
  })
})

/* ---------------- 图表配置 ---------------- */
const comboOption = computed(() =>
  baseChartOption({
    tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
    xAxis: { type: 'category', data: trend.value.months ?? [], axisTick: { alignWithLabel: true } },
    yAxis: [
      { type: 'value', name: '额度（元）', axisLine: { show: false } },
      { type: 'value', name: '消耗占比', min: 0, max: 100, axisLabel: { formatter: '{value}%' }, splitLine: { show: false } }
    ],
    series: [
      { name: '已消耗', type: 'bar', stack: 'budget', barWidth: 20, data: (trend.value.used ?? []).map((v) => Number(v || 0)) },
      {
        name: '剩余额度',
        type: 'bar',
        stack: 'budget',
        barWidth: 20,
        itemStyle: { borderRadius: [4, 4, 0, 0] },
        data: (trend.value.remaining ?? []).map((v) => Number(v || 0))
      },
      {
        name: '消耗占比',
        type: 'line',
        yAxisIndex: 1,
        smooth: true,
        symbolSize: 7,
        lineStyle: { width: 2 },
        data: (trend.value.usedRatio ?? []).map((v) => ratioToNumber(v))
      }
    ]
  })
)

const areaOption = computed(() =>
  baseChartOption({
    tooltip: { trigger: 'axis' },
    xAxis: { type: 'category', boundaryGap: false, data: trend.value.months ?? [] },
    yAxis: { type: 'value', name: '已消耗（元）' },
    series: [
      {
        name: '已消耗额度',
        type: 'line',
        smooth: true,
        symbolSize: 7,
        areaStyle: { opacity: 0.18 },
        data: (trend.value.used ?? []).map((v) => Number(v || 0))
      }
    ]
  })
)

const compositionOption = computed(() => {
  const data = (overview.value.composition ?? []).map((item) => ({
    name: item?.name || '未分类',
    value: Number(item?.value || 0)
  }))
  return baseChartOption({
    tooltip: { trigger: 'item', formatter: '{b}<br/>预算 {c} 元（{d}%）' },
    legend: { orient: 'vertical', right: 8, top: 'center', icon: 'circle', itemWidth: 10, itemHeight: 10 },
    series: [
      {
        name: '预算构成',
        type: 'pie',
        radius: ['46%', '72%'],
        center: ['38%', '52%'],
        avoidLabelOverlap: true,
        itemStyle: { borderColor: '#fff', borderWidth: 2 },
        label: { formatter: '{b}\n{d}%', fontSize: 12 },
        data
      }
    ]
  })
})

/* ---------------- 数据加载 ---------------- */
async function load() {
  loading.value = true
  try {
    const [overviewData, trendData] = await Promise.all([
      budgetApi.overview(),
      budgetApi.trend({ months: 6 })
    ])
    overview.value = overviewData || {}
    trend.value = {
      months: trendData?.months ?? [],
      used: trendData?.used ?? [],
      remaining: trendData?.remaining ?? [],
      usedRatio: trendData?.usedRatio ?? []
    }
  } catch (error) {
    // 后端未启动或接口异常时保持空态，页面结构仍完整可交互
    overview.value = {}
    trend.value = { months: [], used: [], remaining: [], usedRatio: [] }
  } finally {
    loading.value = false
  }
  // 申请记录单独加载：即使概览接口异常也不需要连带清空表格数据
  await loadApplications()
}

async function loadApplications() {
  appLoading.value = true
  try {
    const payload = await budgetApi.applications({ page: query.page, size: query.size })
    // 兼容分页信封 { list, total } 与直接返回数组两种形态
    const list = Array.isArray(payload) ? payload : payload?.list ?? []
    applicationRows.value = list ?? []
    appTotal.value = Array.isArray(payload) ? list.length : payload?.total ?? 0
  } catch (error) {
    applicationRows.value = []
    appTotal.value = 0
  } finally {
    appLoading.value = false
  }
}

function searchApplications() {
  query.page = 1
  loadApplications()
}

function goDetail() {
  router.push('/authz/budget/detail')
}

/* ---------------- 新增申请 ---------------- */
function openApplication() {
  appForm.project = ''
  appForm.category = ''
  appForm.amount = 0
  appForm.reason = ''
  appForm.expectedAt = ''
  dialogVisible.value = true
  appFormRef.value?.clearValidate()
}

async function submitApplication() {
  if (!appFormRef.value) return
  try {
    await appFormRef.value.validate()
  } catch (error) {
    return
  }
  submitting.value = true
  try {
    const data = await budgetApi.createApplication({
      project: appForm.project,
      category: appForm.category,
      amount: appForm.amount,
      reason: appForm.reason,
      expectedAt: appForm.expectedAt
    })
    ElMessage.success(`预算申请已提交，申请编号：${data?.code || '-'}（待审批）`)
    dialogVisible.value = false
    query.page = 1
    await load()
  } catch (error) {
    // 请求层已统一提示错误
  } finally {
    submitting.value = false
  }
}

/* ---------------- 审批 / 驳回 ---------------- */
async function handleApprove(row) {
  try {
    await ElMessageBox.confirm(
      `确认通过「${row.project || row.code}」的预算申请（${formatNumber(row.amount || 0, 2)} 元）？通过后将计入项目预算额度。`,
      '预算申请审批',
      { type: 'warning', confirmButtonText: '通过', cancelButtonText: '取消' }
    )
  } catch (error) {
    return
  }
  try {
    await budgetApi.approveApplication(row.id, { approved: true, comment: '审批通过，额度已入账' })
    ElMessage.success('预算申请已通过')
    await load()
  } catch (error) {
    // 请求层已统一提示错误
  }
}

async function handleReject(row) {
  let comment = ''
  try {
    const result = await ElMessageBox.prompt('请填写驳回原因（将通知申请人并写入审计日志）', '驳回预算申请', {
      confirmButtonText: '确认驳回',
      cancelButtonText: '取消',
      inputType: 'textarea',
      inputPlaceholder: '如：预算池不足 / 缺少合规依据 / 额度测算不合理',
      inputValidator: (value) => (value && value.trim().length >= 4 ? true : '驳回原因不少于 4 个字符')
    })
    comment = result.value || ''
  } catch (error) {
    return
  }
  try {
    await budgetApi.approveApplication(row.id, { approved: false, comment })
    ElMessage.success('预算申请已驳回')
    await load()
  } catch (error) {
    // 请求层已统一提示错误
  }
}

onMounted(async () => {
  try {
    // 预算项目类别来自元数据接口，首次进入时加载
    await appStore.loadMeta()
  } catch (error) {
    // 元数据失败时下拉框为空，不影响概览展示
  }
  await load()
})
</script>

<style scoped>
.fs-mt {
  margin-top: 16px;
}
.fs-option {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}
.fs-budget-alert + .fs-budget-alert {
  margin-top: 10px;
}
.fs-budget-alert__head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  width: 100%;
}
.fs-pager {
  display: flex;
  justify-content: flex-end;
  margin-top: 14px;
}
</style>
