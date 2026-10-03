
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
