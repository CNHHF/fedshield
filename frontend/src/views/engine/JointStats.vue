<template>
  <div class="fs-page">
    <div class="fs-page__header">
      <div>
        <h2 class="fs-page__title">全球交易联合统计</h2>
        <p class="fs-page__subtitle">
          各地区节点在本地完成聚合与分级加密后上传（P1 走 Paillier 同态求和、P2 走差分隐私 + AES-256-GCM），
          聚合节点在密文域完成求和与计数，直接生成海关 / VAT 申报口径统计。
        </p>
      </div>
      <div style="display: flex; gap: 10px">
        <el-button :loading="loading" @click="handleQuery">
          <el-icon><Refresh /></el-icon>
          <span>重新统计</span>
        </el-button>
        <el-button type="primary" :disabled="!rows.length" @click="handleExport">
          <el-icon><Download /></el-icon>
          <span>导出申报报表</span>
        </el-button>
      </div>
    </div>

    <!-- 筛选区 -->
    <div class="fs-card">
      <div class="fs-card__body">
        <div class="fs-toolbar" style="margin-bottom: 0">
          <span class="fs-muted">统计维度</span>
          <el-select v-model="query.dimension" style="width: 150px" @change="handleQuery">
            <el-option v-for="item in DIMENSION_OPTIONS" :key="item.value" :label="item.label" :value="item.value" />
          </el-select>

          <span class="fs-muted">时间范围</span>
          <el-date-picker
            v-model="query.dateRange"
            type="daterange"
            range-separator="至"
            start-placeholder="开始日期"
            end-placeholder="结束日期"
            value-format="YYYY-MM-DD"
            style="width: 280px"
            @change="handleQuery"
          />

          <span class="fs-muted">隐私预算 ε</span>
          <el-slider
            v-model="query.epsilon"
            :min="0.1"
            :max="10"
            :step="0.1"
            style="width: 220px; margin: 0 10px"
            @change="handleQuery"
          />
          <span class="fs-mono">{{ query.epsilon.toFixed(1) }}</span>

          <div class="fs-toolbar__right">
            <el-button type="primary" :loading="loading" @click="handleQuery">
              <el-icon><Search /></el-icon>
              <span>执行联合统计</span>
            </el-button>
          </div>
        </div>
      </div>
    </div>

    <!-- 统计概览 -->
    <div class="fs-grid fs-grid--4" style="margin-top: 16px">
      <StatCard
        label="交易总金额"
        :value="formatNumber(stats.totalAmount, 2)"
        unit="CNY"
        icon="Money"
        color="#1f5fd8"
        :sub="`密文域求和结果，币种 ${stats.currency || 'CNY'}`"
      />
      <StatCard
        label="交易笔数"
        :value="formatNumber(stats.txCount, 0)"
        unit="笔"
        icon="Tickets"
        color="#14a37f"
        sub="各地区节点本地上报后汇总"
      />
      <StatCard
        label="对公付款方数"
        :value="formatNumber(stats.counterpartyTotal, 0)"
        unit="户"
        icon="OfficeBuilding"
        color="#8b5cf6"
        sub="P1 级数据经 Paillier 密文域求和"
      />
      <StatCard
        label="统计误差率"
        :value="errorRateText"
        icon="WarningFilled"
        :color="stats.errorPass ? '#14a37f' : '#e5484d'"
        :sub="`标准 ≤ ${formatPercent(stats.errorStandard ?? 0.01, 0)}，判定：${stats.errorPass ? '达标' : '未达标'}`"
      />
    </div>

    <!-- 图表 -->
    <div class="fs-grid fs-grid--2" style="margin-top: 16px">
      <div class="fs-card">
        <div class="fs-card__header">
          <div class="fs-card__title">分地区统计</div>
          <span class="fs-muted">柱状：金额（元）　折线：笔数</span>
        </div>
        <div class="fs-card__body">
          <ChartBox :option="regionOption" :height="330" empty-text="暂无分地区统计数据" />
        </div>
      </div>

      <div class="fs-card">
        <div class="fs-card__header">
          <div class="fs-card__title">商品类别占比</div>
          <span class="fs-muted">按金额占比（P3 级 AES-256-GCM 传输）</span>
        </div>
        <div class="fs-card__body">
          <ChartBox :option="categoryOption" :height="330" empty-text="暂无商品类别统计数据" />
        </div>
      </div>
    </div>

    <!-- 明细与步骤 -->
    <div class="fs-grid fs-grid--2" style="margin-top: 16px">
      <div class="fs-card">
        <div class="fs-card__header">
          <div class="fs-card__title">统计明细</div>
          <el-tag size="small" effect="plain">ε 实际消耗 {{ formatNumber(stats.epsilonUsed, 4) }}</el-tag>
        </div>
        <div class="fs-card__body">
          <el-table :data="rows" border stripe size="small" style="width: 100%">
            <el-table-column prop="name" label="维度项" min-width="120" />
            <el-table-column label="交易金额（元）" min-width="150">
              <template #default="{ row }">{{ formatNumber(row.amount, 2) }}</template>
            </el-table-column>
            <el-table-column label="金额占比" width="110">
              <template #default="{ row }">{{ formatPercent(row.share, 2) }}</template>
            </el-table-column>
            <el-table-column v-if="query.dimension === 'region'" label="交易笔数" width="110">
              <template #default="{ row }">{{ formatNumber(row.count, 0) }}</template>
            </el-table-column>
            <el-table-column v-if="query.dimension === 'region'" label="对公付款方数" width="130">
              <template #default="{ row }">{{ formatNumber(row.counterparties, 0) }}</template>
            </el-table-column>
            <template #empty>
              <el-empty description="暂无统计数据，请先执行联合统计" />
            </template>
          </el-table>
        </div>
      </div>

      <div class="fs-card">
        <div class="fs-card__header">
          <div class="fs-card__title">计算链路</div>
          <span class="fs-muted">地区本地聚合 → 密文域运算 → 申报口径</span>
        </div>
        <div class="fs-card__body">
          <el-timeline v-if="steps.length">
            <el-timeline-item
              v-for="(step, index) in steps"
              :key="`${index}-${step.name}`"
              :timestamp="formatDuration(step.ms)"
              placement="top"
              :type="index === steps.length - 1 ? 'success' : 'primary'"
            >
              <div style="font-weight: 600">{{ step.name || `步骤 ${index + 1}` }}</div>
              <div class="fs-muted" style="margin-top: 4px">
                加密算法：<span class="fs-mono">{{ step.cipher || '-' }}</span>
              </div>
              <div class="fs-muted" style="margin-top: 2px">{{ step.detail || '—' }}</div>
            </el-timeline-item>
          </el-timeline>

          <!-- 后端未返回 steps 时，按标准链路静态展示，说明该场景的隐私计算流程 -->
          <el-timeline v-else>
            <el-timeline-item
              v-for="(step, index) in FALLBACK_STEPS"
              :key="step.title"
              :timestamp="step.cipher"
              placement="top"
              :type="index === FALLBACK_STEPS.length - 1 ? 'success' : 'primary'"
            >
              <div style="font-weight: 600">{{ step.title }}</div>
              <div class="fs-muted" style="margin-top: 2px">{{ step.desc }}</div>
            </el-timeline-item>
          </el-timeline>

          <el-descriptions v-if="steps.length" :column="2" border size="small" style="margin-top: 8px">
            <el-descriptions-item label="执行耗时">{{ formatDuration(stats.resource?.elapsedMs) }}</el-descriptions-item>
            <el-descriptions-item label="参与地区数">{{ formatNumber(stats.resource?.regions ?? 0, 0) }}</el-descriptions-item>
            <el-descriptions-item label="密文份数">{{ formatNumber(stats.resource?.ciphertexts ?? 0, 0) }}</el-descriptions-item>
            <el-descriptions-item label="密文信封">{{ formatNumber(stats.resource?.envelopes ?? 0, 0) }}</el-descriptions-item>
          </el-descriptions>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { engineApi } from '@/api'
import ChartBox from '@/components/ChartBox.vue'
import StatCard from '@/components/StatCard.vue'
import { CHART_COLORS, baseChartOption, formatDuration, formatNumber, formatPercent } from '@/utils/format'
import { exportCsv } from '@/utils/download'

const loading = ref(false)
const stats = ref({})
const steps = ref([])
const rows = ref([])

const DIMENSION_OPTIONS = [
  { value: 'region', label: '地区' },
  { value: 'category', label: '商品类别' }
]

// 后端未返回 steps 时的标准链路说明（与 backend/engine/joint_stats.py 的流程一致）
const FALLBACK_STEPS = [
  { title: '地区本地聚合', cipher: '—', desc: '各地区节点在本地完成金额、笔数、付款方数量聚合，交易明细不出域' },
  { title: 'P1 级同态加密', cipher: 'SM4 + Paillier', desc: '收付款方实名信息经国密 SM4 加密本体，数据密钥再经 Paillier 公钥封装' },
  { title: '密文域求和', cipher: 'Paillier 同态加法', desc: 'E(Σxᵢ) = Π E(xᵢ)，聚合节点全程无需解密单节点数据' },
  { title: 'P2 级差分隐私', cipher: 'Laplace(Δf/ε) + AES-256-GCM', desc: '交易金额按各地区分配预算加噪，抵御差分攻击' },
  { title: '生成申报口径', cipher: '—', desc: '输出全球总金额、分地区笔数、商品类别占比，可直接用于海关 / VAT 申报' }
]

const query = reactive({
  dimension: 'region',
  dateRange: [],
  // 默认 ε=1.5，与后端演示默认值一致
  epsilon: 1.5
})

const errorRateText = computed(() =>
  stats.value.errorRate === undefined || stats.value.errorRate === null
    ? '-'
    : formatPercent(stats.value.errorRate, 2)
)

const byRegion = computed(() => stats.value.byRegion ?? [])
const byCategory = computed(() => stats.value.byCategory ?? [])

const regionOption = computed(() =>
  baseChartOption({
    tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
    legend: { data: ['交易金额', '交易笔数'], right: 10, top: 4 },
    grid: { left: 60, right: 60, top: 40, bottom: 30, containLabel: true },
    xAxis: {
      type: 'category',
      data: byRegion.value.map((item) => item?.name || item?.region || '-'),
      axisLabel: { interval: 0 }
    },
    yAxis: [
      { type: 'value', name: '金额(元)', axisLabel: { formatter: (value) => formatNumber(value, 0) } },
      { type: 'value', name: '笔数', axisLabel: { formatter: (value) => formatNumber(value, 0) } }
    ],
    series: [
      {
        name: '交易金额',
        type: 'bar',
        barWidth: 34,
        itemStyle: { color: CHART_COLORS[0], borderRadius: [4, 4, 0, 0] },
        data: byRegion.value.map((item) => Number(item?.amount ?? 0))
      },
      {
        name: '交易笔数',
        type: 'line',
        smooth: true,
        symbolSize: 7,
        yAxisIndex: 1,
        itemStyle: { color: CHART_COLORS[2] },
        data: byRegion.value.map((item) => Number(item?.count ?? 0))
      }
    ]
  })
)

const categoryOption = computed(() => {
  const total = byCategory.value.reduce((sum, item) => sum + Number(item?.amount ?? 0), 0)
  return baseChartOption({
    tooltip: { trigger: 'item', formatter: '{b}：{c} 元（{d}%）' },
    legend: { bottom: 0, type: 'scroll', icon: 'circle', itemWidth: 10, itemHeight: 10 },
    series: [
      {
        name: '商品类别金额',
        type: 'pie',
        radius: ['42%', '68%'],
        center: ['50%', '46%'],
        label: {
          // 占比优先用后端 share，缺失时按金额自算，保证饼图标签不出现 NaN
          formatter: (item) => {
            const share = byCategory.value[item.dataIndex]?.share
            const percent = share === undefined || share === null ? (total ? item.value / total : 0) : Number(share)
            return `${item.name}\n${(percent * 100).toFixed(1)}%`
          },
          fontSize: 12
        },
        data: byCategory.value.map((item) => ({ name: item?.name || '其他', value: Number(item?.amount ?? 0) }))
      }
    ]
  })
})

/** 明细表数据：地区维度展示笔数与付款方数，类别维度展示金额占比 */
function normalizeRows(data) {
  if (data?.dimension === 'category') {
    return (data.byCategory ?? []).map((item) => ({
      name: item?.name || '其他',
      amount: Number(item?.amount ?? 0),
      share: Number(item?.share ?? 0)
    }))
  }
  return (data?.byRegion ?? []).map((item) => ({
    name: item?.name || item?.region || '-',
    amount: Number(item?.amount ?? 0),
    share: Number(item?.share ?? 0),
    count: Number(item?.count ?? 0),
    counterparties: Number(item?.counterparties ?? 0)
  }))
}

async function load() {
  loading.value = true
  try {
    const [startDate, endDate] = query.dateRange || []
    const data = await engineApi.jointStats({
      dimension: query.dimension,
      startDate: startDate || undefined,
      endDate: endDate || undefined,
      epsilon: query.epsilon
    })
    stats.value = data || {}
    steps.value = data?.steps ?? []
    rows.value = normalizeRows(data || {})
  } catch (error) {
    stats.value = {}
    steps.value = []
    rows.value = []
  } finally {
    loading.value = false
  }
}

function handleQuery() {
  load()
}

/** 导出当前表格为申报报表 CSV（前端导出，无需等待后端生成文件） */
function handleExport() {
  if (!rows.value.length) {
    ElMessage.warning('暂无可导出的统计数据')
    return
  }
  const dimensionName = DIMENSION_OPTIONS.find((item) => item.value === query.dimension)?.label || '地区'
  const columns =
    query.dimension === 'category'
      ? [
          { prop: 'name', label: `${dimensionName}` },
          { prop: (row) => formatNumber(row.amount, 2), label: '交易金额(元)' },
          { prop: (row) => formatPercent(row.share, 2), label: '金额占比' }
        ]
      : [
          { prop: 'name', label: `${dimensionName}` },
          { prop: (row) => formatNumber(row.amount, 2), label: '交易金额(元)' },
          { prop: (row) => formatNumber(row.count, 0), label: '交易笔数' },
          { prop: (row) => formatNumber(row.counterparties, 0), label: '对公付款方数' },
          { prop: (row) => formatPercent(row.share, 2), label: '金额占比' }
        ]

  exportCsv(
    rows.value,
    columns,
    `fedshield-联合统计申报报表-${query.dimension}-${new Date().toISOString().slice(0, 10)}.csv`
  )
  ElMessage.success('申报报表已开始下载')
}

onMounted(load)
</script>
