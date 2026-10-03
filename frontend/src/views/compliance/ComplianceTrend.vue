<template>
  <div class="fs-page">
    <div class="fs-page__header">
      <div>
        <h2 class="fs-page__title">合规趋势与预警</h2>
        <p class="fs-page__subtitle">
          按地区统计跨境合规校验通过率走势，并汇总触发规则引擎的合规预警；
          预警来源与等级分布可帮助合规团队判断高风险监管辖区与集中问题类型。
        </p>
      </div>
      <div class="fs-toolbar" style="margin-bottom: 0">
        <el-button :icon="Refresh" :loading="loading" @click="loadAll">刷新</el-button>
      </div>
    </div>

    <div class="fs-card">
      <div class="fs-card__header">
        <span class="fs-card__title">跨境合规率趋势</span>
        <span class="fs-muted">数据来源 GET /compliance/trend</span>
      </div>
      <div class="fs-card__body">
        <div class="fs-toolbar">
          <el-radio-group v-model="months" @change="loadTrend">
            <el-radio-button :value="6">近 6 个月</el-radio-button>
            <el-radio-button :value="12">近 12 个月</el-radio-button>
          </el-radio-group>
          <el-select
            v-model="regions"
            multiple
            collapse-tags
            collapse-tags-tooltip
            placeholder="选择地区（默认 EU/US/SEA）"
            style="width: 320px"
            @change="loadTrend"
          >
            <el-option v-for="item in REGION_OPTIONS" :key="item.value" :label="item.label" :value="item.value" />
          </el-select>
          <div class="fs-toolbar__right">
            <span class="fs-muted">
              最新一期：{{ latestSummary || '暂无数据' }}
            </span>
          </div>
        </div>
        <ChartBox :option="trendOption" :height="340" :loading="loading" empty-text="暂无合规趋势数据" />
      </div>
    </div>

    <el-row :gutter="16" style="margin-top: 16px">
      <el-col :xs="24" :lg="14">
        <div class="fs-card" style="height: 100%">
          <div class="fs-card__header">
            <span class="fs-card__title">合规预警</span>
            <div style="display: flex; align-items: center; gap: 10px">
              <el-tag v-if="highCount" type="danger" size="small" effect="dark">高危 {{ highCount }}</el-tag>
              <el-tag v-if="mediumCount" type="warning" size="small" effect="dark">中度 {{ mediumCount }}</el-tag>
              <el-button text type="primary" @click="toggleAll">
                {{ showAll ? '仅看最新 10 条' : '查看全部' }}
              </el-button>
            </div>
          </div>
          <div class="fs-card__body">
            <div v-loading="alertLoading" class="alert-list">
              <el-alert
                v-for="item in alertList"
                :key="item.code || item.createdAt"
                :type="levelType(item.level)"
                :closable="false"
                show-icon
                class="alert-item"
              >
                <template #title>
                  <div class="alert-title">
                    <span class="alert-title__text">{{ item.title || '合规预警' }}</span>
                    <el-tag :type="levelType(item.level)" size="small" effect="plain">
                      {{ levelLabel(item.level) }}
                    </el-tag>
                    <el-tag v-if="item.status" size="small" type="info" effect="plain">
                      {{ statusLabel(item.status) }}
                    </el-tag>
                  </div>
                </template>
                <div class="alert-body">
                  <div class="alert-body__content">{{ item.content || '-' }}</div>
                  <div class="alert-body__meta">
                    <span>依据：{{ item.requirement || '-' }}</span>
                    <span>来源：{{ item.source || '-' }}</span>
                    <span>时间：{{ formatTime(item.createdAt) }}</span>
                  </div>
                  <div class="alert-body__actions">
                    <el-button size="small" type="primary" plain :loading="handlingCode === item.code" @click="onHandle(item)">
                      处理
                    </el-button>
                  </div>
                </div>
              </el-alert>
              <el-empty
                v-if="!alertList.length && !alertLoading"
                description="暂无合规预警，当前合规态势良好"
                :image-size="80"
              />
            </div>
          </div>
        </div>
      </el-col>

      <el-col :xs="24" :lg="10">
        <div class="fs-card" style="height: 100%">
          <div class="fs-card__header">
            <span class="fs-card__title">合规问题类型分布</span>
            <el-select v-model="pieDimension" size="small" style="width: 150px">
              <el-option label="按预警来源" value="source" />
              <el-option label="按风险等级" value="level" />
            </el-select>
          </div>
          <div class="fs-card__body">
            <ChartBox :option="pieOption" :height="360" :loading="alertLoading" empty-text="暂无预警数据" />
          </div>
        </div>
      </el-col>
    </el-row>
  </div>
</template>

<script setup>
/**
 * 合规趋势与预警（对应设计文档图 24 / 图 25）
 *
 * 关键实现：
 * 1. 趋势图：后端返回 { months, series:[{region,name,data}] }，前端直接映射为多条折线；
 *    地区筛选为空时回退默认三地（EU/US/SEA），避免把空参数传给后端导致全量返回。
 * 2. 预警列表：level → el-alert type 映射（high→error / medium→warning / low→info）；
 *    「查看全部」把 limit 从 10 放大到 50。
 * 3. 饼图数据由前端聚合（按 source 或 level），无独立后端接口。
 */
import { computed, onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { Refresh } from '@element-plus/icons-vue'
import { complianceApi } from '@/api'
import { ALERT_LEVEL, CHART_COLORS, baseChartOption, formatTime, formatPercent } from '@/utils/format'
import ChartBox from '@/components/ChartBox.vue'

const loading = ref(false)
const alertLoading = ref(false)
const handlingCode = ref(null)

const months = ref(6)
const regions = ref(['EU', 'US', 'SEA'])
const trendMonths = ref([])
const trendSeries = ref([])

const alerts = ref([])
const showAll = ref(false)
const pieDimension = ref('source')

const REGION_OPTIONS = [
  { value: 'EU', label: '欧盟' },
  { value: 'US', label: '美国' },
  { value: 'SEA', label: '东南亚' },
  { value: 'CN', label: '中国' },
  { value: 'SG', label: '新加坡' },
  { value: 'ME', label: '中东' },
  { value: 'AF', label: '非洲' }
]

/** 预警条数：默认展示 10 条，查看全部时放大到 50 条 */
const alertLimit = computed(() => (showAll.value ? 50 : 10))

const alertList = computed(() => {
  const list = alerts.value ?? []
  return showAll.value ? list : list.slice(0, 10)
})

const highCount = computed(() => (alerts.value ?? []).filter((item) => String(item?.level).toLowerCase() === 'high').length)
const mediumCount = computed(
  () => (alerts.value ?? []).filter((item) => String(item?.level).toLowerCase() === 'medium').length
)

/** 最新一期各地区合规率摘要 */
const latestSummary = computed(() => {
  const list = trendSeries.value ?? []
  if (!list.length || !trendMonths.value.length) return ''
  const index = trendMonths.value.length - 1
  return list
    .map((item) => {
      const value = item?.data?.[index]
      const text = typeof value === 'number' && value <= 1 ? formatPercent(value, 1) : `${value ?? '-'}`
      return `${item?.name || item?.region || '-'} ${text}`
    })
    .join(' · ')
})

const trendOption = computed(() =>
  baseChartOption({
    tooltip: {
      trigger: 'axis',
      // 合规率既可能是 0-1 小数也可能是百分数，这里统一按小数格式化展示
      valueFormatter: (value) => (typeof value === 'number' ? formatPercent(value, 1) : `${value ?? '-'}`)
    },
    legend: { right: 10, top: 4, icon: 'roundRect', itemWidth: 10, itemHeight: 10, textStyle: { fontSize: 12 } },
    xAxis: {
      type: 'category',
      boundaryGap: false,
      data: trendMonths.value ?? [],
      axisLine: { lineStyle: { color: '#e4e8ef' } },
      axisLabel: { color: '#5c6b7f' }
    },
    yAxis: {
      type: 'value',
      name: '合规率',
      axisLabel: {
        color: '#5c6b7f',
        formatter: (value) => (typeof value === 'number' && value <= 1 ? `${(value * 100).toFixed(0)}%` : value)
      },
      splitLine: { lineStyle: { color: '#eef1f6' } }
    },
    series: (trendSeries.value ?? []).map((item) => ({
      name: item?.name || item?.region || '未命名地区',
      type: 'line',
      smooth: true,
      symbolSize: 6,
      showSymbol: true,
      data: item?.data ?? [],
      lineStyle: { width: 2 }
    }))
  })
)

/** 饼图数据：按 source 或 level 聚合预警条数 */
const pieOption = computed(() => {
  const groups = {}
  ;(alerts.value ?? []).forEach((item) => {
    const key = pieDimension.value === 'level' ? levelLabel(item?.level) : item?.source || '未知来源'
    groups[key] = (groups[key] ?? 0) + 1
  })
  const data = Object.entries(groups).map(([name, value]) => ({ name, value }))
  return baseChartOption({
    color: CHART_COLORS,
    tooltip: { trigger: 'item', formatter: '{b}：{c} 条（{d}%）' },
    legend: { bottom: 0, top: 'auto', icon: 'circle', itemWidth: 10, itemHeight: 10, textStyle: { fontSize: 12 } },
    grid: { left: 10, right: 10, top: 20, bottom: 40, containLabel: true },
    series: [
      {
        type: 'pie',
        radius: ['42%', '68%'],
        center: ['50%', '46%'],
        avoidLabelOverlap: true,
        itemStyle: { borderColor: '#fff', borderWidth: 2 },
        label: { formatter: '{b}\n{c} 条', fontSize: 12 },
        data
      }
    ]
  })
})

function levelType(level) {
  const key = String(level || '').toLowerCase()
  if (key === 'high') return 'error'
  if (key === 'medium') return 'warning'
  return 'info'
}

function levelLabel(level) {
  return ALERT_LEVEL[String(level || '').toLowerCase()]?.label || level || '提示'
}

/** 预警处置状态（与后端 models.Alert.status 的枚举一致：open / handling / closed） */
const STATUS_LABELS = {
  open: '待处理',
  handling: '处理中',
  processing: '处理中',
  closed: '已闭环'
}

function statusLabel(status) {
  return STATUS_LABELS[String(status || '').toLowerCase()] || status
}

async function loadTrend() {
  loading.value = true
  try {
    // 地区为空时回退默认三地，避免后端返回全量导致图表拥挤
    const regionParam = (regions.value ?? []).length ? regions.value.join(',') : 'EU,US,SEA'
    const data = await complianceApi.trend({ months: months.value, regions: regionParam })
    trendMonths.value = data?.months ?? []
    trendSeries.value = data?.series ?? []
  } catch (error) {
    trendMonths.value = []
    trendSeries.value = []
  } finally {
    loading.value = false
  }
}

async function loadAlerts() {
  alertLoading.value = true
  try {
    const data = await complianceApi.alerts({ limit: alertLimit.value })
    alerts.value = Array.isArray(data) ? data : data?.list ?? []
  } catch (error) {
    alerts.value = []
  } finally {
    alertLoading.value = false
  }
}

async function loadAll() {
  loading.value = true
  try {
    await Promise.all([loadTrend(), loadAlerts()])
  } finally {
    loading.value = false
  }
}

function toggleAll() {
  showAll.value = !showAll.value
  // 查看全部时提升 limit 重新拉取，缩回时沿用已缓存数据即可
  if (showAll.value) loadAlerts()
}

function onHandle(item) {
  // 契约（docs/API.md §5.2）未提供预警处置接口，因此这里不伪造后端状态：
  // 仅提示已登记，并立即重新拉取列表以反映服务端的真实状态（handling/closed 由后端写入）。
  handlingCode.value = item?.code ?? null
  ElMessage.success(`已登记处理：${item?.title || item?.code || '合规预警'}`)
  handlingCode.value = null
  loadAlerts()
}

onMounted(loadAll)
</script>

<style scoped>
.alert-list {
  max-height: 560px;
  overflow-y: auto;
  padding-right: 4px;
}
.alert-item {
  align-items: flex-start;
  margin-bottom: 10px;
}
.alert-item :deep(.el-alert__content) {
  width: 100%;
}
.alert-title {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}
.alert-title__text {
  font-weight: 600;
}
.alert-body__content {
  margin-top: 4px;
  font-size: 13px;
  line-height: 1.6;
  color: var(--fs-text);
}
.alert-body__meta {
  margin-top: 6px;
  display: flex;
  flex-wrap: wrap;
  gap: 14px;
  font-size: 12px;
  color: var(--fs-text-secondary);
}
.alert-body__actions {
  margin-top: 8px;
}
</style>
