<template>
  <div class="fs-page fs-brain">
    <!-- 标题区 -->
    <div class="fs-page__header">
      <div>
        <h2 class="fs-page__title">
          <el-icon class="fs-brain__title-icon"><Cpu /></el-icon>
          AI 风控合规智能大脑
        </h2>
        <p class="fs-page__subtitle">
          面向全球支付场景的 AI 驱动风控合规智能大脑框架 ·
          以「感知输入 → 脑区计算 → 决策输出」的数据流可视化呈现平台运行态势
          · 更新时间 {{ data.updatedAt || '-' }}
        </p>
      </div>
      <div class="fs-toolbar__right">
        <el-tag :type="autoRefresh ? 'success' : 'info'" effect="plain" size="large">
          <el-icon><Refresh /></el-icon>
          {{ autoRefresh ? '脉冲实时刷新中' : '已暂停刷新' }}
        </el-tag>
        <el-switch v-model="autoRefresh" active-text="实时" inactive-text="暂停" />
        <el-button :icon="Refresh" @click="load(true)">刷新</el-button>
      </div>
    </div>

    <!-- 大脑运行指标 -->
    <div class="fs-grid fs-grid--4">
      <StatCard
        v-for="(item, index) in data.kpis"
        :key="item.key"
        :label="item.label"
        :value="item.value"
        :unit="item.unit"
        :sub="item.sub"
        :icon="KPI_ICONS[index % KPI_ICONS.length]"
        :color="KPI_COLORS[index % KPI_COLORS.length]"
      />
    </div>

    <!-- 脑机结构数据流展板 -->
    <div class="fs-card fs-brain__board-card">
      <div class="fs-card__header">
        <span class="fs-card__title">脑机结构数据流展板</span>
        <div class="fs-brain__legend">
          <span v-for="group in data.groups" :key="group.code" class="fs-brain__legend-item">
            <i :style="{ background: GROUP_COLORS[group.code] }"></i>
            {{ group.name }}
            <em>{{ countOfGroup(group.code) }}</em>
          </span>
          <span class="fs-brain__legend-tip">节点大小 = 当前负载 · 流动光点 = 数据脉冲</span>
        </div>
      </div>
      <div class="fs-card__body">
        <ChartBox :option="boardOption" :height="620" :loading="loading" empty-text="暂无脑区数据" />
      </div>
    </div>

    <div class="fs-grid fs-grid--2">
      <!-- 实时神经脉冲 -->
      <div class="fs-card">
        <div class="fs-card__header">
          <span class="fs-card__title">实时神经脉冲（操作审计流）</span>
          <el-button text type="primary" @click="go('/lineage/audit')">查看全部存证</el-button>
        </div>
        <div class="fs-card__body fs-brain__pulses">
          <el-empty v-if="!data.events.length" description="暂无脉冲事件" :image-size="70" />
          <el-timeline v-else>
            <el-timeline-item
              v-for="(item, index) in data.events"
              :key="index"
              :timestamp="item.ts"
              :type="item.result === 'success' ? 'success' : item.result === 'denied' ? 'danger' : 'info'"
              size="normal"
            >
              <div class="fs-brain__pulse">
                <strong>{{ item.actor }}</strong>
                <el-tag size="small" effect="plain">{{ item.action }}</el-tag>
                <span v-if="item.target" class="fs-muted">→ {{ item.target }}</span>
                <el-tag v-if="item.chainTxId" size="small" type="success" effect="plain">
                  已存证 {{ item.chainTxId.slice(0, 10) }}
                </el-tag>
              </div>
            </el-timeline-item>
          </el-timeline>
        </div>
      </div>

      <!-- 脑区负载与性能 -->
      <div class="fs-card">
        <div class="fs-card__header">
          <span class="fs-card__title">脑区负载与决策性能</span>
        </div>
        <div class="fs-card__body">
          <div v-for="item in data.regions" :key="item.id" class="fs-brain__load">
            <div class="fs-brain__load-head">
              <span class="fs-brain__load-dot" :style="{ background: groupColor(item.group) }"></span>
              <strong>{{ item.name }}</strong>
              <span class="fs-muted">{{ item.groupLabel }}</span>
              <el-tag size="small" :type="STATUS_TAG[item.status] || 'info'" effect="plain">
                {{ STATUS_LABEL[item.status] || item.status }}
              </el-tag>
              <span class="fs-brain__load-value">{{ (item.load * 100).toFixed(0) }}%</span>
            </div>
            <el-progress
              :percentage="Math.round(item.load * 100)"
              :show-text="false"
              :stroke-width="8"
              :color="groupColor(item.group)"
            />
          </div>

          <el-divider content-position="left">最近一次大脑决策</el-divider>
          <el-descriptions v-if="data.performance.length" :column="1" border size="small">
            <el-descriptions-item v-for="item in data.performance" :key="item.label" :label="item.label">
              {{ item.value }} {{ item.unit }}
            </el-descriptions-item>
          </el-descriptions>
          <el-empty v-else description="尚未执行隐私计算任务" :image-size="60" />
          <div class="fs-brain__actions">
            <el-button type="primary" @click="go('/engine/create')">发起大脑决策任务</el-button>
            <el-button plain @click="go('/engine/tasks')">任务管理</el-button>
            <el-button plain @click="go('/compliance/rules')">规则引擎</el-button>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { Cpu, Refresh } from '@element-plus/icons-vue'
import { brainApi } from '@/api'
import ChartBox from '@/components/ChartBox.vue'
import StatCard from '@/components/StatCard.vue'

const router = useRouter()

const loading = ref(false)
const autoRefresh = ref(true)
let timer = null

const data = reactive({
  canvas: { width: 1000, height: 620 },
  regions: [],
  flows: [],
  kpis: [],
  events: [],
  performance: [],
  groups: [],
  updatedAt: ''
})

// 三大功能层的配色（感知=蓝 / 脑区=紫 / 决策=绿）
const GROUP_COLORS = { sensory: '#1f5fd8', cortex: '#8b5cf6', motor: '#14a37f' }
const STATUS_TAG = { busy: 'danger', active: 'warning', idle: 'success' }
const STATUS_LABEL = { busy: '高负载', active: '运行中', idle: '空闲' }
const KPI_ICONS = ['Odometer', 'Share', 'Connection', 'Cpu', 'Files']
const KPI_COLORS = ['#1f5fd8', '#8b5cf6', '#14a37f', '#f5a623', '#0ea5e9']

function groupColor(group) {
  return GROUP_COLORS[group] || '#1f5fd8'
}

function countOfGroup(code) {
  return data.regions.filter((item) => item.group === code).length
}

function go(path) {
  router.push(path)
}

const regionMap = computed(() => {
  const map = {}
  data.regions.forEach((item) => {
    map[item.id] = item
  })
  return map
})

/**
 * 展板图表：
 * - graphic：脑机结构底图（左右半球 + 中央核团 + 出入通道）
 * - lines：数据通路，带流动光点（effect）表现「神经脉冲」
 * - scatter：脑区节点，尺寸与颜色随实时负载变化
 */
const boardOption = computed(() => {
  const flows = data.flows
    .map((flow) => {
      const from = regionMap.value[flow.source]
      const to = regionMap.value[flow.target]
      if (!from || !to) return null
      return {
        coords: [
          [from.x, from.y],
          [to.x, to.y]
        ],
        lineStyle: { color: groupColor(to.group) },
        throughput: flow.throughput,
        label: flow.label
      }
    })
    .filter(Boolean)

  const nodes = data.regions.map((item) => ({
    name: item.name,
    value: [item.x, item.y, item.symbolSize],
    itemStyle: { color: groupColor(item.group) },
    meta: item
  }))

  return {
    backgroundColor: 'transparent',
    tooltip: {
      trigger: 'item',
      confine: true,
      backgroundColor: 'rgba(16,26,44,0.92)',
      borderWidth: 0,
      textStyle: { color: '#fff', fontSize: 12 },
      formatter: (params) => {
        const meta = params.data && params.data.meta
        if (!meta) return params.name
        const lines = (meta.metrics || [])
          .map((m) => `${m.label}：<b>${m.value}${m.unit || ''}</b>`)
          .join('<br/>')
        return (
          `<div style="font-weight:600;margin-bottom:4px">${meta.name}</div>` +
          `<div style="color:#9fb2cd;margin-bottom:6px">${meta.groupLabel} · 负载 ${(meta.load * 100).toFixed(0)}%</div>` +
          `${lines}<div style="color:#9fb2cd;margin-top:6px;max-width:240px;white-space:normal">${meta.desc}</div>`
        )
      }
    },
    grid: { left: 10, right: 10, top: 10, bottom: 10 },
    xAxis: { type: 'value', min: 0, max: data.canvas.width, show: false },
    yAxis: { type: 'value', min: 0, max: data.canvas.height, inverse: true, show: false },
    // 脑机结构底图（百分比定位，随容器自适应）
    graphic: [
      // 左半球 / 右半球
      { type: 'rect', left: '22%', top: '5%', width: '26%', height: '90%', shape: { r: 130 },
        style: { fill: 'rgba(139,92,246,0.05)', stroke: 'rgba(139,92,246,0.22)', lineWidth: 1.5 }, silent: true },
      { type: 'rect', left: '52%', top: '5%', width: '26%', height: '90%', shape: { r: 130 },
        style: { fill: 'rgba(139,92,246,0.05)', stroke: 'rgba(139,92,246,0.22)', lineWidth: 1.5 }, silent: true },
      // 中央纵裂（脑干/核团通道）
      { type: 'rect', left: '47.4%', top: '14%', width: '5.2%', height: '72%', shape: { r: 26 },
        style: { fill: 'rgba(31,95,216,0.08)', stroke: 'rgba(31,95,216,0.25)', lineWidth: 1 }, silent: true },
      // 感知输入通道 / 决策输出通道
      { type: 'rect', left: '2.5%', top: '8%', width: '14%', height: '84%', shape: { r: 60 },
        style: { fill: 'rgba(31,95,216,0.05)', stroke: 'rgba(31,95,216,0.18)', lineWidth: 1, lineDash: [6, 6] }, silent: true },
      { type: 'rect', left: '83%', top: '18%', width: '14%', height: '64%', shape: { r: 60 },
        style: { fill: 'rgba(20,163,127,0.05)', stroke: 'rgba(20,163,127,0.18)', lineWidth: 1, lineDash: [6, 6] }, silent: true },
      // 结构标注
      { type: 'text', left: '3.6%', top: '3.2%', style: { text: '感知输入层', fill: '#1f5fd8', fontSize: 12, fontWeight: 600 }, silent: true },
      { type: 'text', left: '44.6%', top: '3.2%', style: { text: '脑区计算层', fill: '#8b5cf6', fontSize: 12, fontWeight: 600 }, silent: true },
      { type: 'text', left: '84.4%', top: '13.5%', style: { text: '决策输出层', fill: '#14a37f', fontSize: 12, fontWeight: 600 }, silent: true }
    ],
    series: [
      {
        // 数据通路 + 神经脉冲动画
        type: 'lines',
        coordinateSystem: 'cartesian2d',
        polyline: false,
        zlevel: 1,
        effect: {
          show: true,
          period: 4.5,
          trailLength: 0.35,
          symbol: 'circle',
          symbolSize: 5,
          color: '#ffffff'
        },
        lineStyle: { width: 1.4, opacity: 0.42, curveness: 0.18 },
        data: flows,
        silent: true
      },
      {
        // 脑区节点
        type: 'scatter',
        coordinateSystem: 'cartesian2d',
        zlevel: 2,
        symbol: 'circle',
        symbolSize: (value) => value[2],
        itemStyle: { borderColor: 'rgba(255,255,255,0.85)', borderWidth: 2, shadowBlur: 12 },
        label: {
          show: true,
          position: 'bottom',
          distance: 6,
          formatter: '{b}',
          color: '#1f2733',
          fontSize: 12,
          fontWeight: 500
        },
        emphasis: { scale: 1.15, label: { fontSize: 13, fontWeight: 700 } },
        data: nodes
      }
    ]
  }
})

async function load(manual = false) {
  if (!manual) loading.value = true
  try {
    // 自动刷新时使用 silent，避免偶发失败弹窗打扰演示
    const payload = await brainApi.overview(manual ? {} : { silent: true })
    Object.assign(data, {
      canvas: payload.canvas || { width: 1000, height: 620 },
      regions: payload.regions || [],
      flows: payload.flows || [],
      kpis: payload.kpis || [],
      events: payload.events || [],
      performance: payload.performance || [],
      groups: payload.groups || [],
      updatedAt: payload.updatedAt || ''
    })
  } catch (error) {
    // 演示期间的静默刷新失败不打断页面
  } finally {
    loading.value = false
  }
}

function startTimer() {
  stopTimer()
  timer = window.setInterval(() => load(false), 10000)
}

function stopTimer() {
  if (timer) {
    window.clearInterval(timer)
    timer = null
  }
}

watch(autoRefresh, (value) => {
  if (value) {
    startTimer()
  } else {
    stopTimer()
  }
})

onMounted(() => {
  load(true)
  startTimer()
})

onBeforeUnmount(stopTimer)
</script>

<style scoped>
.fs-brain__title-icon {
  vertical-align: -2px;
  margin-right: 6px;
  color: #8b5cf6;
}
.fs-brain__board-card {
  margin-top: 16px;
  background:
    radial-gradient(1200px 320px at 50% -10%, rgba(139, 92, 246, 0.08), transparent),
    #fff;
}
.fs-brain__legend {
  display: flex;
  align-items: center;
  gap: 16px;
  flex-wrap: wrap;
  font-size: 12px;
  color: var(--fs-text-secondary);
}
.fs-brain__legend-item {
  display: flex;
  align-items: center;
  gap: 6px;
}
.fs-brain__legend-item i {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  display: inline-block;
}
.fs-brain__legend-item em {
  font-style: normal;
  color: var(--fs-text);
  font-weight: 600;
}
.fs-brain__legend-tip {
  padding-left: 8px;
  border-left: 1px solid var(--fs-border);
}
.fs-brain__pulses {
  max-height: 520px;
  overflow-y: auto;
}
.fs-brain__pulse {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  font-size: 13px;
}
.fs-brain__load {
  margin-bottom: 12px;
}
.fs-brain__load-head {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 4px;
  font-size: 13px;
}
.fs-brain__load-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
}
.fs-brain__load-value {
  margin-left: auto;
  font-weight: 600;
  color: var(--fs-text-secondary);
}
.fs-brain__actions {
  margin-top: 16px;
  display: flex;
  gap: 10px;
  flex-wrap: wrap;
}
</style>
