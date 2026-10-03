<template>
  <div class="fs-page">
    <!-- 页面头部 -->
    <div class="fs-page__header">
      <div>
        <h2 class="fs-page__title">数据血缘图谱</h2>
        <p class="fs-page__subtitle">
          展示跨境数据从采集、抽取、转换、计算到应用的全链路血缘关系，支持节点双向追溯与链路记录落链存证。
        </p>
      </div>
      <div class="fs-page__actions">
        <el-tag type="info" effect="plain">
          <el-icon><Share /></el-icon>
          节点 {{ graph.nodes.length }} · 链路 {{ graph.links.length }}
        </el-tag>
      </div>
    </div>

    <!-- 筛选工具栏 -->
    <div class="fs-card">
      <div class="fs-card__body">
        <div class="fs-toolbar">
          <el-select v-model="filters.dataType" placeholder="数据类型" clearable style="width: 150px" @change="handleSearch">
            <el-option v-for="item in DATA_TYPES" :key="item.value" :label="item.label" :value="item.value" />
          </el-select>
          <el-select v-model="filters.stage" placeholder="处理阶段" clearable style="width: 150px" @change="handleSearch">
            <el-option v-for="item in STAGES" :key="item.value" :label="item.label" :value="item.value" />
          </el-select>
          <el-date-picker
            v-model="filters.range"
            type="daterange"
            unlink-panels
            range-separator="至"
            start-placeholder="开始日期"
            end-placeholder="结束日期"
            value-format="YYYY-MM-DD"
            style="width: 260px"
            @change="handleSearch"
          />
          <el-input
            v-model="filters.keyword"
            placeholder="按节点名称 / 归属主体搜索"
            clearable
            style="width: 220px"
            @keyup.enter="handleSearch"
          >
            <template #prefix>
              <el-icon><Search /></el-icon>
            </template>
          </el-input>
          <el-button type="primary" :loading="loading" @click="handleSearch">
            <el-icon><Refresh /></el-icon>
            刷新图谱
          </el-button>
          <div class="fs-toolbar__right">
            <el-button :disabled="loading" @click="handleCreateRecord">
              <el-icon><DocumentAdd /></el-icon>
              生成链路记录
            </el-button>
          </div>
        </div>

        <div class="fs-toolbar">
          <span class="fs-muted">视图操作：</span>
          <el-button-group>
            <el-button @click="zoomIn">
              <el-icon><ZoomIn /></el-icon>
              放大
            </el-button>
            <el-button @click="zoomOut">
              <el-icon><ZoomOut /></el-icon>
              缩小
            </el-button>
            <el-button @click="resetView">
              <el-icon><Aim /></el-icon>
              重置视图
            </el-button>
          </el-button-group>
          <el-button v-if="selectedId" text type="primary" @click="clearSelection">
            取消节点选中（{{ selectedId }}）
          </el-button>
          <span class="fs-muted">支持鼠标滚轮缩放、拖拽平移、点击节点查看详情</span>
        </div>
      </div>
    </div>

    <!-- 图谱主体 + 节点详情 -->
    <div class="fs-card">
      <div class="fs-card__header">
        <div class="fs-card__title">血缘链路视图</div>
        <div class="fs-muted">阶段配色：采集 / 抽取 / 转换 / 计算 / 应用</div>
      </div>
      <div class="fs-card__body">
        <div class="lineage-main">
          <div class="lineage-main__chart">
            <div v-if="!graph.nodes.length && !loading" class="lineage-empty">
              <el-empty description="当前筛选条件下暂无血缘数据" :image-size="90" />
            </div>
            <ChartBox
              v-else
              ref="chartBoxRef"
              :option="chartOption"
              :loading="loading"
              height="580"
              empty-text="当前筛选条件下暂无血缘数据"
              @vue:mounted="attachChartEvents"
            />
          </div>

          <!-- 节点详情区 -->
          <div class="lineage-detail">
            <div class="lineage-detail__title">
              <el-icon><InfoFilled /></el-icon>
              节点详情
            </div>

            <el-empty v-if="!selectedId" description="点击图谱中的任意节点查看详情" :image-size="70" />

            <div v-else v-loading="nodeLoading" class="lineage-detail__body">
              <el-descriptions :column="1" border size="small">
                <el-descriptions-item label="节点名称">{{ nodeDetail.name || '-' }}</el-descriptions-item>
                <el-descriptions-item label="节点类型">{{ nodeDetail.type || '-' }}</el-descriptions-item>
                <el-descriptions-item label="处理阶段">
                  <el-tag size="small" effect="plain">{{ stageLabel(nodeDetail.stage) }}</el-tag>
                </el-descriptions-item>
                <el-descriptions-item label="归属主体">{{ nodeDetail.owner || '-' }}</el-descriptions-item>
                <el-descriptions-item label="所属地区">{{ nodeDetail.region || '-' }}</el-descriptions-item>
                <el-descriptions-item label="数据分级">
                  <DataLevelTag v-if="nodeDetail.level" :level="nodeDetail.level" />
                  <span v-else>-</span>
                </el-descriptions-item>
                <el-descriptions-item label="加工时间">{{ formatTime(nodeDetail.processedAt) }}</el-descriptions-item>
              </el-descriptions>

              <div class="lineage-detail__section">
                <div class="lineage-detail__label">数据标签</div>
                <div class="lineage-detail__tags">
                  <el-tag v-for="tag in nodeTags" :key="tag" size="small" type="info" effect="plain">{{ tag }}</el-tag>
                  <span v-if="!nodeTags.length" class="fs-muted">暂无标签</span>
                </div>
              </div>

              <div class="lineage-detail__section">
                <div class="lineage-detail__label">合规标签</div>
                <div class="lineage-detail__tags">
                  <el-tag v-for="(tag, index) in complianceTags" :key="index" size="small" type="success" effect="light">
                    {{ tag }}
                  </el-tag>
                  <span v-if="!complianceTags.length" class="fs-muted">暂无合规标签</span>
                </div>
              </div>

              <div class="lineage-detail__section">
                <div class="lineage-detail__label">上游来源（{{ upstream.length }}）</div>
                <el-table :data="upstream" size="small" border max-height="180">
                  <el-table-column prop="name" label="来源节点" show-overflow-tooltip />
                  <el-table-column prop="operation" label="操作" width="82" />
                  <el-table-column label="时间" width="140">
                    <template #default="{ row }">{{ formatTime(row.ts) }}</template>
                  </el-table-column>
                  <template #empty>暂无上游来源</template>
                </el-table>
              </div>

              <div class="lineage-detail__section">
                <div class="lineage-detail__label">下游流向（{{ downstream.length }}）</div>
                <el-table :data="downstream" size="small" border max-height="180">
                  <el-table-column prop="name" label="流向节点" show-overflow-tooltip />
                  <el-table-column prop="operation" label="操作" width="82" />
                  <el-table-column label="时间" width="140">
                    <template #default="{ row }">{{ formatTime(row.ts) }}</template>
                  </el-table-column>
                  <template #empty>暂无下游流向</template>
                </el-table>
              </div>

              <div v-if="rules.length" class="lineage-detail__section">
                <div class="lineage-detail__label">关联合规规则（{{ rules.length }}）</div>
                <el-table :data="rules" size="small" border max-height="160">
                  <el-table-column prop="name" label="规则名称" show-overflow-tooltip />
                  <el-table-column prop="scene" label="场景" width="110" />
                  <el-table-column label="优先级" width="76">
                    <template #default="{ row }">{{ row.priority ?? '-' }}</template>
                  </el-table-column>
                  <template #empty>暂无关联规则</template>
                </el-table>
              </div>

              <div class="lineage-detail__actions">
                <el-button type="primary" plain @click="traceDirection('upstream')">
                  <el-icon><Back /></el-icon>
                  向前追溯来源
                </el-button>
                <el-button type="primary" plain @click="traceDirection('downstream')">
                  向后查看流向
                  <el-icon><Right /></el-icon>
                </el-button>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, nextTick, onMounted, reactive, ref, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { lineageApi } from '@/api'
import ChartBox from '@/components/ChartBox.vue'
import DataLevelTag from '@/components/DataLevelTag.vue'
import { CHART_COLORS, formatTime } from '@/utils/format'
import { downloadResponse } from '@/utils/download'

/* ---------------- 字典 ---------------- */
const DATA_TYPES = [
  { value: 'user', label: '用户数据' },
  { value: 'transaction', label: '交易数据' },
  { value: 'list', label: '清单数据' }
]

const STAGES = [
  { value: 'collect', label: '采集' },
  { value: 'extract', label: '抽取' },
  { value: 'transform', label: '转换' },
  { value: 'compute', label: '计算' },
  { value: 'apply', label: '应用' }
]

/* 处理阶段配色与节点尺寸（阶段越靠后节点越大，体现加工深度） */
const STAGE_STYLE = {
  collect: { color: CHART_COLORS[0], size: 42 },
  extract: { color: CHART_COLORS[1], size: 50 },
  transform: { color: CHART_COLORS[2], size: 58 },
  compute: { color: CHART_COLORS[3], size: 66 },
  apply: { color: CHART_COLORS[4], size: 74 }
}
const STAGE_FALLBACK = CHART_COLORS[6]

/* ---------------- 状态 ---------------- */
const loading = ref(false)
const nodeLoading = ref(false)
const chartBoxRef = ref(null)

const filters = reactive({
  dataType: '',
  stage: '',
  range: [],
  keyword: ''
})

/* 图谱原始数据 */
const graph = reactive({ nodes: [], links: [] })
/* 节点详情 */
const selectedId = ref('')
const nodeDetail = ref({})
const upstream = ref([])
const downstream = ref([])
const rules = ref([])
const complianceTags = ref([])
/* 高亮链路：'upstream' 向前追溯 | 'downstream' 向后查看 | '' 无 */
const highlightMode = ref('')

/* ---------------- 工具函数 ---------------- */
function stageLabel(stage) {
  const hit = STAGES.find((item) => item.value === stage)
  return hit ? hit.label : stage || '-'
}

function stageStyle(stage) {
  return STAGE_STYLE[stage] || { color: STAGE_FALLBACK, size: 46 }
}

/** 组装请求参数（空值不下发，避免后端把空串当成有效筛选） */
function buildParams() {
  const params = {}
  if (filters.dataType) params.dataType = filters.dataType
  if (filters.stage) params.stage = filters.stage
  if (filters.keyword) params.keyword = filters.keyword.trim()
  if (Array.isArray(filters.range) && filters.range.length === 2) {
    params.start = filters.range[0]
    params.end = filters.range[1]
  }
  return params
}

/** 解析节点名称（兼容 id 直连与后端返回对象两种形式） */
function resolveName(id) {
  const hit = graph.nodes.find((item) => item.id === id)
  return hit ? hit.name || hit.id : id
}

/** 把节点详情里可能出现的字符串数组统一成标签数组 */
function toTagList(value) {
  if (!Array.isArray(value)) return []
  return value
    .map((item) => (typeof item === 'string' ? item : item?.label || item?.name || ''))
    .filter((item) => Boolean(item))
}

/** 转义 HTML 特殊字符（用于 ElMessageBox 的 dangerouslyUseHTMLString 文本） */
function escapeHtml(value) {
  return String(value ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
}

/* ---------------- 图谱渲染 ---------------- */
/* 当前节点的数据标签（详情接口未返回时回退到图谱节点自带 tags） */
const nodeTags = computed(() => {
  const tags = toTagList(nodeDetail.value?.tags)
  return tags.length ? tags : toTagList(nodeDetail.value?._raw?.tags)
})

/* 聚焦节点集合：为空表示展示全图；有值时非聚焦节点淡化 */
const focusNodes = computed(() => {
  if (!selectedId.value) return null
  const keep = new Set([selectedId.value])
  const push = (id) => {
    if (id) keep.add(id)
  }
  graph.links.forEach((link) => {
    if (link.target === selectedId.value) push(link.source)
    if (link.source === selectedId.value) push(link.target)
  })
  return keep
})

/** 构建 ECharts graph 数据 */
function buildGraphData() {
  const focus = focusNodes.value
  const nodes = graph.nodes.map((item) => {
    const style = stageStyle(item.stage)
    const focused = !focus || focus.has(item.id)
    return {
      id: item.id,
      name: item.name || item.id,
      value: stageLabel(item.stage),
      symbolSize: focused && focus ? style.size + 8 : style.size,
      itemStyle: {
        color: style.color,
        borderColor: item.id === selectedId.value ? '#1f2733' : '#ffffff',
        borderWidth: item.id === selectedId.value ? 3 : 1.5,
        opacity: focused ? 1 : 0.22
      },
      label: {
        show: focused,
        color: focused ? '#1f2733' : 'rgba(92,107,127,0.45)',
        width: 92,
        overflow: 'truncate',
        formatter: (params) => (params?.data?._raw?.name || params?.data?.id || '').slice(0, 12)
      },
      _raw: item
    }
  })

  const links = graph.links.map((link) => {
    const connected = !focus || (focus.has(link.source) && focus.has(link.target))
    return {
      source: link.source,
      target: link.target,
      value: link.operation || '',
      lineStyle: {
        color: connected && focus ? CHART_COLORS[0] : '#c9d2e0',
        width: connected && focus ? 2.2 : 1,
        opacity: connected ? (focus ? 1 : 0.5) : 0.12,
        curveness: 0.12
      },
      label: { show: Boolean(link.operation) && connected, opacity: connected ? 1 : 0.2, formatter: link.operation || '' },
      _raw: link
    }
  })

  return { nodes, links }
}

const chartOption = computed(() => {
  const data = buildGraphData()
  return {
    color: CHART_COLORS,
    tooltip: {
      confine: true,
      formatter: (params) => {
        if (params.dataType === 'edge') {
          const raw = params.data?._raw || {}
          return [
            `<b>${resolveName(raw.source)} → ${resolveName(raw.target)}</b>`,
            `操作：${raw.operation || '-'}`,
            `时间：${formatTime(raw.ts)}`
          ].join('<br/>')
        }
        const raw = params.data?._raw || {}
        return [
          `<b>${raw.name || raw.id || '-'}</b>`,
          `类型：${raw.type || '-'}`,
          `阶段：${stageLabel(raw.stage)}`,
          `归属主体：${raw.owner || '-'}`,
          `地区：${raw.region || '-'}`,
          `分级：${raw.level || '-'}`,
          `加工时间：${formatTime(raw.processedAt)}`
        ].join('<br/>')
      }
    },
    series: [
      {
        type: 'graph',
        layout: 'force',
        roam: true,
        draggable: true,
        zoom: 1,
        focusNodeAdjacency: false,
        edgeSymbol: ['none', 'arrow'],
        edgeSymbolSize: [0, 9],
        force: { repulsion: 360, edgeLength: [110, 190], gravity: 0.06, friction: 0.16 },
        label: {
          show: true,
          position: 'bottom',
          fontSize: 11,
          distance: 6,
          width: 92,
          overflow: 'truncate'
        },
        lineStyle: { color: '#c9d2e0', width: 1, curveness: 0.12 },
        emphasis: {
          focus: 'adjacency',
          label: { show: true, fontWeight: 'bold' },
          lineStyle: { width: 3 }
        },
        data: data.nodes,
        links: data.links
      }
    ]
  }
})

/* ---------------- 视图缩放与交互绑定 ---------------- */
function getChart() {
  return chartBoxRef.value?.getInstance?.() || null
}

/** 绑定图表点击事件（ChartBox 未暴露事件，这里直接绑定 ECharts 实例） */
function attachChartEvents() {
  nextTick(() => {
    const chart = getChart()
    if (!chart || chart.__lineageBound) return
    chart.on('click', handleNodeClick)
    chart.__lineageBound = true
  })
}

function zoomIn() {
  const chart = getChart()
  if (!chart) return
  chart.dispatchAction({ type: 'graphRoam', zoom: 1.2 })
}

function zoomOut() {
  const chart = getChart()
  if (!chart) return
  chart.dispatchAction({ type: 'graphRoam', zoom: 0.8 })
}

function resetView() {
  const chart = getChart()
  if (!chart) return
  chart.setOption({ series: [{ zoom: 1, center: null }] })
  ElMessage.success('视图已重置')
}

/* ---------------- 数据加载 ---------------- */
async function load() {
  loading.value = true
  try {
    const data = await lineageApi.graph(buildParams())
    graph.nodes = data?.nodes ?? []
    graph.links = data?.links ?? []
    // 已选节点不在新数据里则清空详情，避免出现「详情与图谱对不上」
    if (selectedId.value && !graph.nodes.some((item) => item.id === selectedId.value)) {
      clearSelection()
    }
  } finally {
    loading.value = false
  }
}

function handleSearch() {
  clearSelection()
  load()
}

/** 点击图谱节点：拉取节点详情 */
async function handleNodeClick(params) {
  const raw = params?.data?._raw
  if (!raw || !raw.id) return
  selectedId.value = raw.id
  highlightMode.value = ''
  nodeDetail.value = { ...raw }
  upstream.value = []
  downstream.value = []
  rules.value = []
  complianceTags.value = []
  nodeLoading.value = true
  try {
    const data = await lineageApi.node(raw.id)
    nodeDetail.value = data?.node || raw
    upstream.value = data?.upstream ?? []
    downstream.value = data?.downstream ?? []
    rules.value = data?.rules ?? []
    complianceTags.value = toTagList(data?.complianceTags)
  } finally {
    nodeLoading.value = false
  }
}

function clearSelection() {
  selectedId.value = ''
  highlightMode.value = ''
  nodeDetail.value = {}
  upstream.value = []
  downstream.value = []
  rules.value = []
  complianceTags.value = []
}

/**
 * 链路追溯：
 * - upstream：沿连线反向做 BFS，得到该节点的全部上游祖先链路
 * - downstream：沿连线正向做 BFS，得到该节点的全部下游链路
 * 计算完成后图谱会高亮该链路（其余节点淡化）
 */
function collectReachable(startId, direction) {
  const visited = new Set([startId])
  const queue = [startId]
  const pathLinks = new Set()
  while (queue.length) {
    const current = queue.shift()
    graph.links.forEach((link, index) => {
      const matched = direction === 'upstream' ? link.target === current : link.source === current
      if (!matched) return
      pathLinks.add(index)
      const next = direction === 'upstream' ? link.source : link.target
      if (next && !visited.has(next)) {
        visited.add(next)
        queue.push(next)
      }
    })
  }
  return { nodes: visited, links: pathLinks }
}

function traceDirection(direction) {
  if (!selectedId.value) {
    ElMessage.warning('请先在图谱中点击选择一个节点')
    return
  }
  const result = collectReachable(selectedId.value, direction)
  highlightMode.value = direction
  // 高亮方式：把链路内的节点/连线挑出来重新着色，其余淡化
  const focus = new Set(result.nodes)
  const data = buildGraphData()
  data.nodes.forEach((node) => {
    const focused = focus.has(node.id)
    node.itemStyle = {
      ...node.itemStyle,
      borderColor: focused ? (direction === 'upstream' ? '#14a37f' : '#1f5fd8') : '#ffffff',
      borderWidth: focused ? 3 : 1.5,
      opacity: focused ? 1 : 0.16
    }
    node.label = { show: focused, color: focused ? '#1f2733' : 'rgba(92,107,127,0.35)' }
  })
  data.links.forEach((link, index) => {
    const active = result.links.has(index)
    link.lineStyle = {
      ...link.lineStyle,
      color: active ? (direction === 'upstream' ? '#14a37f' : '#1f5fd8') : '#dde3ec',
      width: active ? 2.6 : 1,
      opacity: active ? 1 : 0.12
    }
  })
  const chart = getChart()
  if (chart) {
    chart.setOption({ series: [{ data: data.nodes, links: data.links }] })
  }
  const label = direction === 'upstream' ? '上游来源' : '下游流向'
  ElMessage.success(
    `已高亮「${nodeDetail.value.name || selectedId.value}」的${label}链路：${result.nodes.size} 个节点 / ${result.links.size} 条连线`
  )
}

/* ---------------- 链路记录与溯源报告 ---------------- */
async function handleCreateRecord() {
  const payload = {}
  if (selectedId.value) {
    payload.dataId = selectedId.value
  } else {
    // 未选中节点时，按当前筛选范围生成链路记录
    payload.range = buildParams()
  }
  const confirmText = selectedId.value
    ? `将为节点「${nodeDetail.value.name || selectedId.value}」生成链路记录并落链存证，是否继续？`
    : '未选中节点，将按当前筛选范围内全部数据生成链路记录并落链存证，是否继续？'
  try {
    await ElMessageBox.confirm(confirmText, '生成链路记录', {
      type: 'warning',
      confirmButtonText: '生成并存证',
      cancelButtonText: '取消'
    })
  } catch (error) {
    return // 用户取消
  }

  loading.value = true
  let record = null
  try {
    record = await lineageApi.createRecord(payload)
  } finally {
    loading.value = false
  }
  if (!record) return

  const recordId = record.recordId || '-'
  const chainTxId = record.chainTxId || '-'
  try {
    await ElMessageBox.confirm(
      `<div style="line-height:1.9">
        <div>链路记录已生成并写入联盟链存证：</div>
        <div>记录编号：<b class="fs-mono">${escapeHtml(recordId)}</b></div>
        <div>链上交易 ID：<b class="fs-mono">${escapeHtml(chainTxId)}</b></div>
        <div>覆盖节点数：<b>${record.nodes ?? 0}</b></div>
        <div>生成时间：<b>${escapeHtml(formatTime(record.generatedAt))}</b></div>
      </div>`,
      '链路记录生成成功',
      {
        dangerouslyUseHTMLString: true,
        showCancelButton: true,
        confirmButtonText: '下载溯源报告',
        cancelButtonText: '关闭',
        type: 'success'
      }
    )
  } catch (error) {
    return // 用户选择关闭
  }
  await downloadRecord(recordId)
}

async function downloadRecord(recordId) {
  const target = recordId || '-'
  try {
    const response = await lineageApi.downloadRecord(target)
    downloadResponse(response, `溯源报告-${target}.md`)
    ElMessage.success('溯源报告已开始下载')
  } catch (error) {
    // 请求拦截器已给出错误提示
  }
}

/* 图表数据变化（含数据加载完成）后补绑一次事件，防止实例监听丢失 */
watch(chartOption, () => attachChartEvents())

onMounted(load)
</script>

<style scoped>
.fs-page__actions {
  display: flex;
  align-items: center;
  gap: 8px;
}
.lineage-main {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 380px;
  gap: 16px;
}
.lineage-main__chart {
  min-width: 0;
  border: 1px solid var(--fs-border);
  border-radius: 8px;
  background: #fbfcfe;
}
.lineage-empty {
  height: 580px;
  display: flex;
  align-items: center;
  justify-content: center;
}
.lineage-detail {
  border: 1px solid var(--fs-border);
  border-radius: 8px;
  padding: 14px;
  background: #fff;
  max-height: 580px;
  overflow: auto;
}
.lineage-detail__title {
  display: flex;
  align-items: center;
  gap: 6px;
  font-weight: 600;
  font-size: 14px;
  margin-bottom: 12px;
}
.lineage-detail__body {
  display: flex;
  flex-direction: column;
  gap: 14px;
}
.lineage-detail__section {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.lineage-detail__label {
  font-size: 13px;
  font-weight: 600;
  color: var(--fs-text-secondary);
}
.lineage-detail__tags {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}
.lineage-detail__actions {
  display: flex;
  gap: 10px;
  padding-top: 4px;
}
.lineage-detail__actions .el-button {
  flex: 1;
  margin-left: 0;
}
@media (max-width: 1280px) {
  .lineage-main {
    grid-template-columns: minmax(0, 1fr);
  }
  .lineage-detail {
    max-height: none;
  }
}
</style>
