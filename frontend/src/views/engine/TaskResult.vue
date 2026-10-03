<template>
  <div class="fs-page">
    <div class="fs-page__header">
      <div>
        <h2 class="fs-page__title">计算结果分析</h2>
        <p class="fs-page__subtitle">
          展示最近计算结果：风控模型核心指标、联邦学习每轮收敛曲线、参数传输优化效果与基线对比。
          所有指标均在密文域计算后由授权节点解密汇总。
        </p>
      </div>
      <div style="display: flex; gap: 10px; align-items: center">
        <el-select
          v-model="selectedId"
          filterable
          clearable
          placeholder="切换已完成任务"
          style="width: 280px"
          @change="handleTaskChange"
        >
          <el-option
            v-for="item in finishedTasks"
            :key="item.id"
            :label="`${item.code || item.id} · ${item.name || ''}`"
            :value="item.id"
          />
        </el-select>
        <el-button :loading="loading" @click="load">
          <el-icon><Refresh /></el-icon>
          <span>刷新</span>
        </el-button>
      </div>
    </div>

    <el-empty v-if="!loading && !hasData" description="暂无计算结果，请先在任务管理中启动一个计算任务">
      <el-button type="primary" @click="router.push('/engine/tasks')">前往任务管理</el-button>
    </el-empty>

    <template v-else>
      <!-- 任务基本信息 + 核心结果 -->
      <div class="fs-grid fs-grid--2">
        <div class="fs-card">
          <div class="fs-card__header">
            <div class="fs-card__title">任务基本信息</div>
            <el-tag size="small" :type="statusOf(taskMeta.status).type">{{ statusOf(taskMeta.status).label }}</el-tag>
          </div>
          <div class="fs-card__body">
            <el-descriptions :column="2" border size="small">
              <el-descriptions-item label="任务ID">
                <span class="fs-mono">{{ taskMeta.code || '-' }}</span>
              </el-descriptions-item>
              <el-descriptions-item label="任务名称">{{ taskMeta.name || '-' }}</el-descriptions-item>
              <el-descriptions-item label="计算类型">{{ typeLabel(taskMeta) }}</el-descriptions-item>
              <el-descriptions-item label="加密算法">{{ cipherText }}</el-descriptions-item>
              <el-descriptions-item label="迭代次数">{{ iterations }}</el-descriptions-item>
              <el-descriptions-item label="创建时间">{{ formatTime(taskMeta.createdAt) }}</el-descriptions-item>
              <el-descriptions-item label="参与节点" :span="2">
                <template v-if="partnerCodes.length">
                  <el-tag
                    v-for="code in partnerCodes"
                    :key="code"
                    size="small"
                    type="info"
                    effect="plain"
                    style="margin: 2px 4px 2px 0"
                  >
                    {{ appStore.nodeName(code) || code }}
                  </el-tag>
                </template>
                <span v-else class="fs-muted">未记录</span>
              </el-descriptions-item>
              <el-descriptions-item label="资源消耗" :span="2">
                <span>CPU {{ formatNumber(resource.cpuSec, 2) }} s</span>
                <el-divider direction="vertical" />
                <span>内存 {{ formatNumber(resource.memoryMb, 0) }} MB</span>
                <el-divider direction="vertical" />
                <span>耗时 {{ formatDuration(resource.elapsedMs) }}</span>
              </el-descriptions-item>
            </el-descriptions>

            <el-divider content-position="left">核心结果</el-divider>

            <div class="fs-grid fs-grid--4" style="gap: 10px">
              <StatCard
                label="风控 AUC"
                :value="numberOrNull(metric.auc, 4)"
                icon="TrendCharts"
                color="#1f5fd8"
                sub="越接近 1 判别力越强"
              />
              <StatCard
                label="漏检率"
                :value="percentOrNull(metric.missRate)"
                icon="WarningFilled"
                color="#e5484d"
                :sub="`业务红线 ≤ ${formatPercent(metric.missRateStandard || 0.07, 0)}`"
              />
              <StatCard
                label="精确率"
                :value="percentOrNull(metric.precision)"
                icon="Aim"
                color="#14a37f"
                sub="告警中真实风险占比"
              />
              <StatCard
                label="告警量"
                :value="percentOrNull(metric.alertVolume)"
                icon="BellFilled"
                color="#f5a623"
                sub="按红线阈值反推的告警比例"
              />
            </div>

            <div v-if="chainTxId" class="fs-muted" style="margin-top: 12px">
              存证交易ID：<span class="fs-mono">{{ chainTxId }}</span>
            </div>
          </div>
        </div>

        <div class="fs-card">
          <div class="fs-card__header">
            <div class="fs-card__title">风险分布</div>
            <el-tag size="small" effect="plain" type="info">评测集样本 {{ formatNumber(riskTotal, 0) }} 条</el-tag>
          </div>
          <div class="fs-card__body">
            <ChartBox :option="riskPieOption" :height="320" empty-text="暂无风险分布数据" />
          </div>
        </div>
      </div>

      <!-- 收敛曲线 + 传输量对比 -->
      <div class="fs-grid fs-grid--2">
        <div class="fs-card">
          <div class="fs-card__header">
            <div class="fs-card__title">联邦学习每轮指标</div>
            <span class="fs-muted">左轴：训练损失 Loss　右轴：评测 AUC</span>
          </div>
          <div class="fs-card__body">
            <ChartBox :option="roundsOption" :height="320" empty-text="该任务未返回逐轮训练记录" />
          </div>
        </div>

        <div class="fs-card">
          <div class="fs-card__header">
            <div class="fs-card__title">参数传输量对比</div>
            <el-tag v-if="traffic.savedPercent !== undefined" size="small" type="success" effect="plain">
              压缩率 {{ formatNumber(traffic.savedPercent, 2) }}%
            </el-tag>
          </div>
          <div class="fs-card__body">
            <ChartBox :option="trafficOption" :height="280" empty-text="暂无参数传输量数据" />
            <div class="fs-muted" style="margin-top: 8px">
              基线：float32 全量参数；优化后：差分隐私加噪 → int16 量化 → Top-K 剪枝 → 增量 varint 编码。
              目标压缩率 {{ formatNumber(traffic.target ?? 70, 0) }}%。
            </div>
          </div>
        </div>
      </div>

      <!-- 基线对比 -->
      <div class="fs-card">
        <div class="fs-card__header">
          <div class="fs-card__title">基线对比</div>
          <span class="fs-muted">{{ baselineRule }}</span>
        </div>
        <div class="fs-card__body">
          <el-table :data="baselineRows" border stripe style="width: 100%">
            <el-table-column prop="name" label="建模方式" min-width="220" />
            <el-table-column label="AUC" width="120">
              <template #default="{ row }">{{ formatNumber(row.auc, 4) }}</template>
            </el-table-column>
            <el-table-column label="漏检率" width="120">
              <template #default="{ row }">{{ formatPercent(row.missRate, 2) }}</template>
            </el-table-column>
            <el-table-column label="精确率" width="120">
              <template #default="{ row }">{{ formatPercent(row.precision, 2) }}</template>
            </el-table-column>
            <el-table-column label="告警量" width="120">
              <template #default="{ row }">{{ formatPercent(row.alertVolume, 2) }}</template>
            </el-table-column>
            <el-table-column prop="note" label="说明" min-width="220" show-overflow-tooltip />
          </el-table>

          <div class="fs-toolbar" style="margin-top: 14px; margin-bottom: 0">
            <el-tag v-if="baseline.aucGainOverLocal !== undefined" size="small" type="success" effect="plain">
              联合建模 AUC 较单地区本地建模提升 {{ formatNumber(baseline.aucGainOverLocal, 4) }}
            </el-tag>
            <el-tag
              v-if="baseline.alertWorkloadReductionPercent !== undefined"
              size="small"
              type="warning"
              effect="plain"
            >
              人工审核告警量下降 {{ formatNumber(baseline.alertWorkloadReductionPercent, 2) }}%
            </el-tag>
            <el-tag
              v-if="baseline.aucGapPass !== undefined"
              size="small"
              :type="baseline.aucGapPass ? 'success' : 'danger'"
              effect="plain"
            >
              与明文集中建模的 AUC 差距 {{ formatNumber(baseline.aucGapToPlaintext, 4) }}
              （标准 ≤ {{ formatNumber(baseline.aucGapStandard ?? 0.02, 2) }}，
              {{ baseline.aucGapPass ? '达标' : '未达标' }}）
            </el-tag>
          </div>
        </div>
      </div>

      <div class="fs-card">
        <div class="fs-card__body" style="display: flex; justify-content: flex-end; gap: 10px">
          <el-button :disabled="!taskId" @click="goAllResults">
            <el-icon><Document /></el-icon>
            <span>查看全部结果</span>
          </el-button>
          <el-button type="primary" :loading="exporting" :disabled="!taskId" @click="handleExport">
            <el-icon><Download /></el-icon>
            <span>导出结果</span>
          </el-button>
        </div>
      </div>
    </template>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { engineApi } from '@/api'
import ChartBox from '@/components/ChartBox.vue'
import StatCard from '@/components/StatCard.vue'
import { useAppStore } from '@/store/app'
import {
  CHART_COLORS,
  RISK_LEVEL,
  TASK_STATUS,
  TASK_TYPE,
  baseChartOption,
  dictOf,
  formatDuration,
  formatNumber,
  formatPercent,
  formatTime
} from '@/utils/format'
import { downloadResponse, exportCsv } from '@/utils/download'

const route = useRoute()
const router = useRouter()
const appStore = useAppStore()

const loading = ref(false)
const exporting = ref(false)
const finishedTasks = ref([])
const selectedId = ref('')
const result = ref({})
// 列表接口拿到的任务摘要，作为详情接口缺字段时的兜底展示来源
const taskMeta = ref({})

const taskId = computed(() => selectedId.value || route.params.id || '')

/**
 * 结果体兼容处理：
 * - 任务详情接口把结果摘要放在 data.result 中；
 * - 三大场景计算接口直接返回扁平结构。
 * 统一取出「含指标的那一层」，避免出现 undefined.xxx。
 */
const payload = computed(() => {
  const data = result.value || {}
  if (data.metrics || data.rounds) return data
  if (data.result && typeof data.result === 'object') return data.result
  return data
})

const metric = computed(() => payload.value.metrics || payload.value || {})

const riskDistribution = computed(() => payload.value.riskDistribution ?? metric.value.riskDistribution ?? [])

const riskTotal = computed(() => riskDistribution.value.reduce((sum, item) => sum + Number(item?.value ?? 0), 0))

const rounds = computed(() => payload.value.rounds ?? [])

const traffic = computed(() => payload.value.traffic ?? {})

const baseline = computed(() => payload.value.baseline ?? {})

const resource = computed(() => {
  const item = result.value?.resource || payload.value.resource || {}
  return {
    cpuSec: item.cpuSec ?? 0,
    // 后端不同模块对内存字段命名不完全一致（resource.memoryMb / resource.memMb），做兼容取值
    memoryMb: item.memoryMb ?? item.memMb ?? 0,
    elapsedMs: item.elapsedMs ?? result.value?.durationMs ?? 0
  }
})

const params = computed(() => result.value?.params || payload.value.params || {})

const cipherText = computed(() => {
  if (params.value.cipher) return params.value.cipher
  if (payload.value.homomorphic?.scheme) return payload.value.homomorphic.scheme
  return TASK_TYPE[taskMeta.value.type]?.tech || '-'
})

const iterations = computed(() => {
  const value = params.value.iterations ?? rounds.value.length
  return value ? `${value} 轮` : '-'
})

const partnerCodes = computed(() => {
  const list = taskMeta.value.partners || payload.value.partners || []
  return Array.isArray(list) ? list : []
})

const chainTxId = computed(() => payload.value.chainTxId || result.value?.chainTxId || '')

const baselineRule = computed(
  () =>
    baseline.value.operatingRule ||
    `各建模方式均按漏检率 ≤ ${formatPercent(metric.value.missRateStandard || 0.07, 0)} 红线反推告警阈值后对比`
)

// 基线对比三行：联合建模（本次结果）、单地区本地建模、明文集中建模
const baselineRows = computed(() => {
  const rows = [
    {
      name: '联合建模（横向联邦 + 差分隐私 + 同态聚合）',
      auc: metric.value.auc,
      missRate: metric.value.missRate,
      precision: metric.value.precision,
      alertVolume: metric.value.alertVolume,
      note: '本次任务实际结果，原始数据不出各参与方节点'
    }
  ]
  const local = baseline.value.localOnly
  if (local) {
    rows.push({
      name: '单地区本地建模',
      auc: local.auc,
      missRate: local.missRate,
      precision: local.precision,
      alertVolume: local.alertVolume,
      note: local.note || '不进行跨地域协作，缺少其他地区风险成因特征'
    })
  }
  const plain = baseline.value.plaintext
  if (plain) {
    rows.push({
      name: '明文集中建模（效果上限参考）',
      auc: plain.auc,
      missRate: plain.missRate,
      precision: plain.precision,
      alertVolume: plain.alertVolume,
      note: plain.note || '不加密、不加噪，仅作为效果上限参考'
    })
  }
  return rows
})

const riskPieOption = computed(() => {
  const colors = { 高风险: RISK_LEVEL.high.color, 中风险: RISK_LEVEL.medium.color, 低风险: RISK_LEVEL.low.color }
  return baseChartOption({
    tooltip: { trigger: 'item', formatter: '{b}：{c} 条（{d}%）' },
    legend: { bottom: 0, icon: 'circle', itemWidth: 10, itemHeight: 10 },
    series: [
      {
        name: '风险分布',
        type: 'pie',
        radius: ['45%', '68%'],
        center: ['50%', '46%'],
        avoidLabelOverlap: true,
        label: { formatter: '{b}\n{d}%', fontSize: 12 },
        data: riskDistribution.value.map((item) => ({
          name: item?.name || '未分类',
          value: Number(item?.value ?? 0),
          itemStyle: { color: colors[item?.name] || CHART_COLORS[6] }
        }))
      }
    ]
  })
})

const roundsOption = computed(() =>
  baseChartOption({
    tooltip: { trigger: 'axis' },
    legend: { data: ['训练损失 Loss', '评测 AUC'], right: 10, top: 4 },
    xAxis: {
      type: 'category',
      name: '轮次',
      boundaryGap: false,
      data: rounds.value.map((item) => `第 ${item?.round ?? '-'} 轮`)
    },
    yAxis: [
      { type: 'value', name: 'Loss', scale: true, axisLabel: { formatter: (value) => Number(value).toFixed(2) } },
      { type: 'value', name: 'AUC', min: 0.5, max: 1, axisLabel: { formatter: (value) => Number(value).toFixed(2) } }
    ],
    series: [
      {
        name: '训练损失 Loss',
        type: 'line',
        smooth: true,
        symbolSize: 6,
        yAxisIndex: 0,
        areaStyle: { opacity: 0.08 },
        data: rounds.value.map((item) => item?.loss ?? null)
      },
      {
        name: '评测 AUC',
        type: 'line',
        smooth: true,
        symbolSize: 6,
        yAxisIndex: 1,
        data: rounds.value.map((item) => item?.auc ?? null)
      }
    ]
  })
)

const trafficOption = computed(() =>
  baseChartOption({
    tooltip: {
      trigger: 'axis',
      axisPointer: { type: 'shadow' },
      valueFormatter: (value) => `${formatNumber(value, 2)} KB`
    },
    legend: { show: false },
    grid: { left: 46, right: 22, top: 30, bottom: 30, containLabel: true },
    xAxis: { type: 'category', data: ['参数传输量'] },
    yAxis: { type: 'value', name: 'KB' },
    series: [
      {
        name: '优化前（float32 全量）',
        type: 'bar',
        barWidth: 46,
        itemStyle: { color: CHART_COLORS[0], borderRadius: [4, 4, 0, 0] },
        label: { show: true, position: 'top', formatter: (item) => `${formatNumber(item.value, 2)} KB` },
        data: [Number(traffic.value.rawKb ?? 0)]
      },
      {
        name: `优化后（量化+剪枝，目标 ${formatNumber(traffic.value.target ?? 70, 0)}%）`,
        type: 'bar',
        barWidth: 46,
        itemStyle: { color: CHART_COLORS[1], borderRadius: [4, 4, 0, 0] },
        label: { show: true, position: 'top', formatter: (item) => `${formatNumber(item.value, 2)} KB` },
        data: [Number(traffic.value.optimizedKb ?? 0)]
      }
    ]
  })
)

const hasData = computed(() => Object.keys(result.value || {}).length > 0)

function statusOf(status) {
  return dictOf(TASK_STATUS, status || 'finished', '已完成')
}

function typeLabel(task) {
  if (task?.typeName) return task.typeName
  if (TASK_TYPE[task?.type]) return TASK_TYPE[task.type].label
  return appStore.taskTypeName(task?.type) || task?.type || '-'
}

// StatCard 的数值属性只接受数字或字符串，缺失指标返回 null 以免渲染出误导性的 0
function numberOrNull(value, precision = 2) {
  if (value === null || value === undefined || value === '') return null
  const num = Number(value)
  return Number.isNaN(num) ? null : Number(num.toFixed(precision))
}

function percentOrNull(value, precision = 1) {
  if (value === null || value === undefined || value === '') return null
  const num = Number(value)
  return Number.isNaN(num) ? null : `${(num * 100).toFixed(precision)}%`
}

/** 拉取已完成任务，供顶部「切换任务」下拉使用 */
async function loadFinishedTasks() {
  try {
    const data = await engineApi.tasks({ status: 'finished', page: 1, size: 100 })
    // 列表接口返回分页对象；若后端直接返回数组也兼容
    finishedTasks.value = Array.isArray(data) ? data : data?.list ?? []
  } catch (error) {
    finishedTasks.value = []
  }
  return finishedTasks.value
}

async function loadResult(id) {
  loading.value = true
  try {
    // 先取任务详情（含参数与资源消耗），再取计算结果：详情里的 result 摘要作为兜底
    const detail = await engineApi.taskDetail(id)
    taskMeta.value = detail || {}
    const data = await engineApi.taskResult(id)
    result.value = data && Object.keys(data).length ? data : detail?.result || {}
  } catch (error) {
    result.value = {}
  } finally {
    loading.value = false
  }
}

async function load() {
  loading.value = true
  try {
    const list = await loadFinishedTasks()
    // 路由参数优先；无参数时默认展示最近完成的一个任务
    const routeId = route.params.id ? String(route.params.id) : ''
    const target = routeId || (list.length ? String(list[0].id) : '')
    selectedId.value = target
    const summary = list.find((item) => String(item.id) === target)
    taskMeta.value = summary || {}
  } finally {
    loading.value = false
  }
  if (taskId.value) {
    await loadResult(taskId.value)
  } else {
    result.value = {}
    taskMeta.value = {}
  }
}

function handleTaskChange(id) {
  if (!id) {
    result.value = {}
    return
  }
  // 切换任务时同步路由，便于结果页被分享或刷新后仍定位到同一任务
  router.replace(`/engine/result/${id}`).catch(() => {})
  loadResult(id)
}

function goAllResults() {
  ElMessage.info('完整结果集含脱敏样本预览与逐轮明细，可在任务管理页导出加密审计日志后查看')
  router.push('/engine/tasks')
}

async function handleExport() {
  if (!taskId.value) {
    ElMessage.warning('请先选择要导出的任务')
    return
  }
  exporting.value = true
  try {
    const response = await engineApi.exportTask(taskId.value)
    downloadResponse(response, `fedshield-计算结果-${taskMeta.value.code || taskId.value}.csv`)
    ElMessage.success('计算结果导出已开始下载')
  } catch (error) {
    // 导出接口不可用时退化为前端导出基线对比表，保证用户仍能拿到核心结论
    exportCsv(
      baselineRows.value,
      [
        { prop: 'name', label: '建模方式' },
        { prop: (row) => formatNumber(row.auc, 4), label: 'AUC' },
        { prop: (row) => formatPercent(row.missRate, 2), label: '漏检率' },
        { prop: (row) => formatPercent(row.precision, 2), label: '精确率' },
        { prop: (row) => formatPercent(row.alertVolume, 2), label: '告警量' },
        { prop: 'note', label: '说明' }
      ],
      `fedshield-基线对比-${taskId.value}.csv`
    )
    ElMessage.warning('服务端导出不可用，已改为导出前端基线对比表')
  } finally {
    exporting.value = false
  }
}

onMounted(async () => {
  try {
    await appStore.loadMeta()
  } catch (error) {
    // 节点名称为展示增强项，失败不阻塞结果加载
  }
  load()
})
</script>

<style scoped>
:deep(.el-divider--vertical) {
  margin: 0 8px;
}
</style>
