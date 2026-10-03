<template>
  <div class="fs-page">
    <div class="fs-page__header">
      <div>
        <h2 class="fs-page__title">数据概览控制台</h2>
        <p class="fs-page__subtitle">
          当前视图：<strong>{{ ROLE_LABELS[userStore.activeRole] || userStore.activeRole }}</strong>
          · 数据更新时间 {{ generatedAt || '-' }}
          · 全部指标来自平台真实运行记录
        </p>
      </div>
      <div class="fs-toolbar__right">
        <el-select v-model="role" size="default" class="fs-console__role" @change="onRoleChange">
          <el-option
            v-for="item in roleOptions"
            :key="item.value"
            :label="item.label"
            :value="item.value"
          />
        </el-select>
        <el-button :icon="Refresh" @click="loadAll">刷新</el-button>
      </div>
    </div>

    <!-- 统计卡片 -->
    <div class="fs-grid fs-grid--4" v-loading="loading">
      <StatCard
        v-for="item in stats"
        :key="item.key"
        :label="item.label"
        :value="item.value"
        :unit="item.unit"
        :icon="STAT_ICONS[item.key] || 'DataLine'"
        :color="STAT_COLORS[item.key] || '#1f5fd8'"
        :delta="item.delta"
        :delta-label="'较上周期'"
        :sub="item.sub"
        :clickable="Boolean(STAT_LINKS[item.key])"
        @click="go(STAT_LINKS[item.key])"
      />
    </div>

    <!-- 图表区 -->
    <div class="fs-grid fs-grid--2 fs-console__charts">
      <div class="fs-card">
        <div class="fs-card__header">
          <span class="fs-card__title">数据流转趋势</span>
          <el-radio-group v-model="trendDays" size="small" @change="loadTrend">
            <el-radio-button :value="7">近 7 天</el-radio-button>
            <el-radio-button :value="30">近 30 天</el-radio-button>
            <el-radio-button :value="90">近 90 天</el-radio-button>
          </el-radio-group>
        </div>
        <div class="fs-card__body">
          <ChartBox :option="trendOption" :height="310" :loading="trendLoading" />
        </div>
      </div>

      <div class="fs-card">
        <div class="fs-card__header">
          <span class="fs-card__title">交易风险分布</span>
          <el-button text type="primary" @click="go('/engine/tasks')">风控模型详情</el-button>
        </div>
        <div class="fs-card__body">
          <ChartBox :option="riskOption" :height="310" />
        </div>
      </div>
    </div>

    <!-- 节点状态 + 预警 -->
    <div class="fs-grid fs-grid--2">
      <div class="fs-card">
        <div class="fs-card__header">
          <span class="fs-card__title">跨境协作节点</span>
          <span class="fs-muted">共 {{ nodes.length }} 个 · 在线 {{ onlineCount }} 个</span>
        </div>
        <div class="fs-card__body">
          <el-table :data="nodes" size="small" max-height="300">
            <el-table-column prop="name" label="节点" min-width="150" />
            <el-table-column label="地区" width="90">
              <template #default="{ row }">{{ REGION_NAMES[row.region] || row.region }}</template>
            </el-table-column>
            <el-table-column label="状态" width="100">
              <template #default="{ row }">
                <el-tag :type="NODE_STATUS[row.status]?.type || 'info'" size="small">
                  {{ NODE_STATUS[row.status]?.label || row.status }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column label="时延" width="90">
              <template #default="{ row }">
                <span :class="{ 'fs-console__warn': row.latencyMs > 200 }">{{ row.latencyMs }} ms</span>
              </template>
            </el-table-column>
            <el-table-column prop="tlsVersion" label="传输协议" width="110" />
          </el-table>
        </div>
      </div>

      <div class="fs-card">
        <div class="fs-card__header">
          <span class="fs-card__title">合规与风险预警</span>
          <el-button text type="primary" @click="loadAlerts(50)">查看全部</el-button>
        </div>
        <div class="fs-card__body">
          <el-empty v-if="!alerts.length" description="暂无未闭环预警" :image-size="80" />
          <div v-else class="fs-console__alerts">
            <el-alert
              v-for="item in alerts"
              :key="item.code"
              :type="ALERT_LEVEL[item.level]?.type || 'info'"
              :title="item.title"
              :description="item.content"
              show-icon
              :closable="false"
            >
              <template #default>
                <div class="fs-console__alert-body">
                  <span>{{ item.content }}</span>
                  <div class="fs-console__alert-meta">
                    <el-tag size="small" effect="plain">{{ item.source }}</el-tag>
                    <span class="fs-muted">{{ item.createdAt }}</span>
                    <el-button text type="primary" size="small" @click="go('/compliance/trend')">处理</el-button>
                  </div>
                </div>
              </template>
            </el-alert>
          </div>
        </div>
      </div>
    </div>

    <!-- 效能指标 -->
    <div class="fs-card">
      <div class="fs-card__header">
        <span class="fs-card__title">隐私计算 vs 明文处理 效能对照</span>
        <el-tag size="small" :type="performance.source === 'measured' ? 'success' : 'info'" effect="plain">
          {{ performance.source === 'measured' ? '来自真实任务实测' : '设计目标值' }}
        </el-tag>
      </div>
      <div class="fs-card__body">
        <el-table :data="performance.items" size="small">
          <el-table-column prop="name" label="指标" min-width="180" />
          <el-table-column label="明文处理" width="140">
            <template #default="{ row }">
              {{ row.plain ? `${formatNumber(row.plain)} ${row.unit || ''}` : '—' }}
            </template>
          </el-table-column>
          <el-table-column label="隐私计算" width="150">
            <template #default="{ row }">{{ formatNumber(row.secure) }} {{ row.unit || '' }}</template>
          </el-table-column>
          <el-table-column label="效率" min-width="180">
            <template #default="{ row }">
              <template v-if="row.efficiency !== null && row.efficiency !== undefined">
                <el-progress
                  :percentage="Math.min(100, Math.max(0, 100 - row.efficiency))"
                  :stroke-width="12"
                  :color="row.pass === false ? '#e5484d' : '#14a37f'"
                />
                <span class="fs-muted">较明文{{ row.efficiency >= 0 ? '节省' : '增加' }} {{ Math.abs(row.efficiency) }}%</span>
              </template>
              <span v-else class="fs-muted">—</span>
            </template>
          </el-table-column>
          <el-table-column label="达标" width="90">
            <template #default="{ row }">
              <el-tag v-if="row.pass !== null && row.pass !== undefined" :type="row.pass ? 'success' : 'danger'" size="small">
                {{ row.pass ? '达标' : '超标' }}
              </el-tag>
              <span v-else class="fs-muted">—</span>
            </template>
          </el-table-column>
        </el-table>
        <p class="fs-muted fs-console__standard">{{ performance.standard }}</p>
      </div>
    </div>

    <!-- 功能入口 -->
    <div class="fs-card">
      <div class="fs-card__header"><span class="fs-card__title">功能模块</span></div>
      <div class="fs-card__body">
        <div class="fs-grid fs-grid--4">
          <div v-for="item in modules" :key="item.key" class="fs-console__module" @click="go(item.path)">
            <el-icon :size="22" color="#1f5fd8"><component :is="item.icon" /></el-icon>
            <div>
              <strong>{{ item.title }}</strong>
              <span>{{ item.desc }}</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { Refresh } from '@element-plus/icons-vue'
import { dashboardApi } from '@/api'
import ChartBox from '@/components/ChartBox.vue'
import StatCard from '@/components/StatCard.vue'
import { useAppStore } from '@/store/app'
import { ROLE_LABELS, useUserStore } from '@/store/user'
import { ALERT_LEVEL, baseChartOption, formatNumber } from '@/utils/format'

const router = useRouter()
const userStore = useUserStore()
const appStore = useAppStore()

const loading = ref(false)
const trendLoading = ref(false)
const role = ref(userStore.activeRole || 'pingpong')
const trendDays = ref(30)
const stats = ref([])
const nodes = ref([])
const modules = ref([])
const alerts = ref([])
const generatedAt = ref('')
const trend = ref({ dates: [], series: [] })
const riskDistribution = ref([])
const performance = ref({ items: [], source: 'design', standard: '' })

const roleOptions = computed(() => {
  const all = Object.entries(ROLE_LABELS).map(([value, label]) => ({ value, label }))
  const mine = userStore.user?.role
  if (mine === 'pingpong' || mine === 'admin') return all
  return all.filter((item) => item.value === mine)
})

const onlineCount = computed(() => nodes.value.filter((item) => item.status === 'online').length)

const STAT_ICONS = {
  task: 'List', transaction: 'Tickets', merchant: 'OfficeBuilding', grant: 'Key',
  report: 'Document', audit: 'Files', alert: 'WarningFilled', compliance: 'CircleCheck'
}
const STAT_COLORS = {
  task: '#1f5fd8', transaction: '#14a37f', merchant: '#8b5cf6', grant: '#f5a623',
  report: '#0ea5e9', audit: '#64748b', alert: '#e5484d', compliance: '#14a37f'
}
const STAT_LINKS = {
  task: '/engine/tasks', transaction: '/engine/stats', grant: '/authz/grants',
  report: '/compliance/reports', audit: '/lineage/audit', alert: '/compliance/trend'
}
const NODE_STATUS = {
  online: { label: '在线', type: 'success' },
  degraded: { label: '降级', type: 'warning' },
  offline: { label: '离线', type: 'danger' }
}
const REGION_NAMES = { CN: '中国', EU: '欧盟', US: '北美', SEA: '东南亚', ME: '中东', AF: '非洲', GLOBAL: '全球' }

const trendOption = computed(() =>
  baseChartOption({
    tooltip: { trigger: 'axis' },
    xAxis: { type: 'category', boundaryGap: false, data: trend.value.dates, axisLine: { lineStyle: { color: '#e4e8ef' } } },
    yAxis: { type: 'value', splitLine: { lineStyle: { color: '#f0f3f8' } } },
    series: (trend.value.series || []).map((item) => ({
      name: item.name,
      type: 'line',
      smooth: true,
      showSymbol: false,
      areaStyle: { opacity: 0.08 },
      data: item.data
    }))
  })
)

const riskOption = computed(() => ({
  color: ['#e5484d', '#f5a623', '#14a37f'],
  tooltip: { trigger: 'item', formatter: '{b}：{c} 笔（{d}%）' },
  legend: { bottom: 0, icon: 'circle' },
  series: [
    {
      type: 'pie',
      radius: ['46%', '68%'],
      center: ['50%', '46%'],
      avoidLabelOverlap: true,
      itemStyle: { borderColor: '#fff', borderWidth: 2 },
      label: { formatter: '{b}\n{d}%' },
      data: riskDistribution.value
    }
  ]
}))

async function loadOverview() {
  loading.value = true
  try {
    const data = await dashboardApi.overview({ role: role.value })
    stats.value = data.stats || []
    nodes.value = data.nodes || []
    modules.value = data.modules || []
    generatedAt.value = data.generatedAt || ''
  } finally {
    loading.value = false
  }
}

async function loadTrend() {
  trendLoading.value = true
  try {
    trend.value = await dashboardApi.flowTrend({ days: trendDays.value })
  } finally {
    trendLoading.value = false
  }
}

async function loadAlerts(limit = 5) {
  alerts.value = (await dashboardApi.alerts({ limit })) || []
}

async function loadPerformance() {
  performance.value = await dashboardApi.performance()
}

function onRoleChange(value) {
  userStore.switchRole(value)
  loadOverview()
}

function go(path) {
  if (path) router.push(path)
}

async function loadAll() {
  await Promise.all([loadOverview(), loadTrend(), loadAlerts(), loadPerformance()])
}

onMounted(async () => {
  if (!appStore.loaded) {
    // 元数据加载失败不应阻塞控制台渲染
    appStore.loadMeta().catch(() => {})
  }
  riskDistribution.value = (await dashboardApi.riskDistribution()) || []
  await loadAll()
})
</script>

<style scoped>
.fs-console__role {
  width: 190px;
}
.fs-console__charts {
  margin-top: 16px;
}
.fs-grid + .fs-card,
.fs-grid + .fs-grid {
  margin-top: 16px;
}
.fs-console__alerts {
  display: flex;
  flex-direction: column;
  gap: 10px;
  max-height: 300px;
  overflow-y: auto;
}
.fs-console__alert-body {
  font-size: 12px;
  line-height: 1.7;
}
.fs-console__alert-meta {
  margin-top: 6px;
  display: flex;
  align-items: center;
  gap: 10px;
}
.fs-console__module {
  display: flex;
  gap: 12px;
  padding: 14px 16px;
  border: 1px solid var(--fs-border);
  border-radius: 8px;
  cursor: pointer;
  transition: all 0.18s ease;
}
.fs-console__module:hover {
  border-color: var(--fs-primary);
  box-shadow: 0 6px 16px rgba(31, 95, 216, 0.12);
  transform: translateY(-2px);
}
.fs-console__module strong {
  display: block;
  font-size: 14px;
  margin-bottom: 4px;
}
.fs-console__module span {
  color: var(--fs-text-secondary);
  font-size: 12px;
  line-height: 1.6;
}
.fs-console__standard {
  margin: 12px 0 0;
}
.fs-console__warn {
  color: var(--fs-danger);
}
</style>
