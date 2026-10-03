<template>
  <div class="fs-page">
    <div class="fs-page__header">
      <div>
        <h2 class="fs-page__title">规则引擎配置</h2>
        <p class="fs-page__subtitle">
          可视化编排跨境数据合规规则：从左侧拖拽「触发条件 → 判断条件 → 执行动作」节点到画布，连线定义执行顺序，
          点击节点在右侧编辑属性。规则保存后由后端规则引擎在数据出境前实时执行。
        </p>
      </div>
      <div class="fs-toolbar" style="margin-bottom: 0">
        <el-button :icon="Plus" @click="onNewRule">新建规则</el-button>
        <el-button :icon="Delete" @click="onClearCanvas">清空画布</el-button>
        <el-button type="primary" :icon="Select" :loading="saving" @click="onSaveRule">
          {{ editingId ? '保存修改' : '保存规则' }}
        </el-button>
      </div>
    </div>

    <!-- 基础信息：规则名称/场景/优先级/启用状态 -->
    <div class="fs-card">
      <div class="fs-card__header">
        <span class="fs-card__title">规则基础信息</span>
        <span class="fs-muted">
          {{ editingId ? `正在编辑规则 #${editingId}` : '当前为新规则' }}
          · 画布节点 {{ nodes.length }} 个 / 连线 {{ edges.length }} 条
        </span>
      </div>
      <div class="fs-card__body">
        <el-form :model="ruleForm" label-width="88px" :inline="true">
          <el-form-item label="规则名称">
            <el-input v-model="ruleForm.name" placeholder="如：P1 数据未授权出境阻断" style="width: 260px" clearable />
          </el-form-item>
          <el-form-item label="作用场景">
            <el-select v-model="ruleForm.scene" placeholder="选择场景" style="width: 180px">
              <el-option v-for="item in SCENE_OPTIONS" :key="item.value" :label="item.label" :value="item.value" />
            </el-select>
          </el-form-item>
          <el-form-item label="优先级">
            <el-input-number v-model="ruleForm.priority" :min="1" :max="99" />
          </el-form-item>
          <el-form-item label="启用">
            <el-switch v-model="ruleForm.enabled" />
          </el-form-item>
          <el-form-item label="作用说明">
            <el-input v-model="ruleForm.description" placeholder="说明该规则拦截/放行的判定口径" style="width: 460px" clearable />
          </el-form-item>
        </el-form>
      </div>
    </div>

    <!-- 三栏画布区 -->
    <div class="fs-card">
      <div class="fs-card__header">
        <span class="fs-card__title">规则编排画布</span>
        <span class="fs-muted">提示：鼠标按住节点卡片可移动位置；从节点右侧圆点拖出连线到目标节点完成串联</span>
      </div>
      <div class="fs-card__body">
        <div class="rule-builder">
          <!-- 左侧：节点面板 -->
          <div class="rule-panel">
            <div class="rule-panel__title">节点面板</div>
            <div v-loading="templateLoading" class="rule-panel__body">
              <div v-for="group in templateGroups" :key="group.type" class="rule-panel__group">
                <div class="rule-panel__group-name">
                  <span class="rule-dot" :style="{ background: NODE_COLORS[group.type] }"></span>
                  {{ group.title }}
                </div>
                <div
                  v-for="(item, index) in group.items"
                  :key="`${group.type}-${index}`"
                  class="rule-palette"
                  :style="{ borderLeftColor: NODE_COLORS[group.type] }"
                  draggable="true"
                  @dragstart="onPaletteDragStart($event, group.type, index)"
                >
                  <div class="rule-palette__label">{{ item.label || item.type || '未命名节点' }}</div>
                  <div class="rule-palette__desc">{{ item.description || '拖拽到画布生成节点' }}</div>
                </div>
                <el-empty v-if="!group.items.length" :description="`暂无${group.title}模板`" :image-size="50" />
              </div>
            </div>
          </div>

          <!-- 中间：编排画布 -->
          <div class="rule-canvas-wrap">
            <div
              ref="canvasRef"
              class="rule-canvas"
              :class="{ 'rule-canvas--linking': linking.active }"
              @dragover="onCanvasDragOver"
              @drop="onCanvasDrop"
              @click="onCanvasClick"
            >
              <!-- 连线层：SVG 使用画布坐标系（与节点 x/y 同一坐标系） -->
              <svg class="rule-canvas__svg" :width="CANVAS_WIDTH" :height="CANVAS_HEIGHT">
                <defs>
                  <marker
                    id="rule-arrow"
                    markerWidth="10"
                    markerHeight="10"
                    refX="8"
                    refY="3"
                    orient="auto"
                    markerUnits="strokeWidth"
                  >
                    <path d="M0,0 L8,3 L0,6 Z" fill="#8a97a8" />
                  </marker>
                </defs>
                <path
                  v-for="(item, index) in edgePaths"
                  :key="`edge-${index}`"
                  :d="item.d"
                  fill="none"
                  stroke="#8a97a8"
                  stroke-width="1.6"
                  marker-end="url(#rule-arrow)"
                />
                <path
                  v-if="linking.active && linking.from"
                  :d="previewPath"
                  fill="none"
                  stroke="#1f5fd8"
                  stroke-width="1.6"
                  stroke-dasharray="5 4"
                />
              </svg>

              <!-- 节点层 -->
              <div
                v-for="node in nodes"
                :key="node.id"
                class="rule-node"
                :class="{ 'rule-node--active': node.id === selectedId }"
                :style="{
                  left: `${node.x}px`,
                  top: `${node.y}px`,
                  borderTopColor: nodeColor(node.type)
                }"
                @mousedown.stop="onNodeMouseDown($event, node)"
                @click.stop="selectNode(node)"
              >
                <div class="rule-node__type" :style="{ background: nodeColor(node.type), borderColor: nodeColor(node.type) }">
                  {{ NODE_TYPE_NAMES[node.type] || node.type }}
                </div>
                <div class="rule-node__name" :title="node.name">{{ node.name || '未命名节点' }}</div>
                <div class="rule-node__config" :title="configSummary(node)">{{ configSummary(node) }}</div>
                <div class="rule-node__delete" title="删除节点" @mousedown.stop @click.stop="removeNode(node.id)">
                  <el-icon><Close /></el-icon>
                </div>
                <div
                  class="rule-node__port"
                  title="按住拖出连线"
                  @mousedown.stop="onPortMouseDown($event, node)"
                  @mouseup.stop="onNodeMouseUp($event, node)"
                ></div>
                <div v-if="node.type !== 'trigger'" class="rule-node__in-port" title="连线入口"></div>
              </div>

              <div v-if="!nodes.length" class="rule-canvas__empty">
                <el-empty description="画布为空：从左侧节点面板拖拽节点到这里开始编排" :image-size="90" />
              </div>
            </div>
            <div class="rule-canvas__footer fs-muted">
              画布尺寸 {{ CANVAS_WIDTH }} × {{ CANVAS_HEIGHT }}（可滚动）· 节点坐标以画布左上角为原点记录为 x/y
            </div>
          </div>

          <!-- 右侧：节点属性 -->
          <div class="rule-props">
            <div class="rule-panel__title">节点属性</div>
            <div class="rule-props__body">
              <el-empty v-if="!selectedNode" description="请点击画布中的节点进行编辑" :image-size="70" />
              <el-form v-else :model="selectedNode" label-width="86px" label-position="top">
                <el-form-item label="节点类型">
                  <el-tag :color="nodeColor(selectedNode.type)" effect="dark" style="border: none">
                    {{ NODE_TYPE_NAMES[selectedNode.type] || selectedNode.type }}
                  </el-tag>
                </el-form-item>
                <el-form-item label="节点名称">
                  <el-input v-model="selectedNode.name" placeholder="节点展示名称" />
                </el-form-item>

                <!-- 触发条件 -->
                <template v-if="selectedNode.type === 'trigger'">
                  <el-form-item label="触发事件">
                    <el-select v-model="selectedNode.config.event" placeholder="选择触发事件" style="width: 100%" filterable allow-create>
                      <el-option
                        v-for="item in triggerTemplates"
                        :key="item.type"
                        :label="`${item.label}（${item.type}）`"
                        :value="item.type"
                      />
                    </el-select>
                  </el-form-item>
                  <el-form-item label="事件说明">
                    <el-input v-model="selectedNode.config.remark" type="textarea" :rows="2" placeholder="可选：补充触发条件说明" />
                  </el-form-item>
                </template>

                <!-- 判断条件 -->
                <template v-else-if="selectedNode.type === 'condition'">
                  <el-form-item label="判断字段 field">
                    <el-select v-model="selectedNode.config.field" placeholder="选择判断字段" style="width: 100%" filterable allow-create>
                      <el-option v-for="item in FIELD_OPTIONS" :key="item.value" :label="item.label" :value="item.value" />
                    </el-select>
                  </el-form-item>
                  <el-form-item label="操作符 op">
                    <el-select v-model="selectedNode.config.op" placeholder="选择操作符" style="width: 100%">
                      <el-option v-for="item in OP_OPTIONS" :key="item.value" :label="item.label" :value="item.value" />
                    </el-select>
                  </el-form-item>
                  <el-form-item label="比较值 value">
                    <el-input v-model="selectedNode.config.value" placeholder="如 P1 / 银行卡号 / 100000" />
                    <div class="fs-muted" style="margin-top: 4px">
                      多值请用英文逗号分隔（对应 in / contains 操作符）
                    </div>
                  </el-form-item>
                </template>

                <!-- 执行动作 -->
                <template v-else-if="selectedNode.type === 'action'">
                  <el-form-item label="动作 action">
                    <el-select v-model="selectedNode.config.action" placeholder="选择执行动作" style="width: 100%">
                      <el-option v-for="item in ACTION_OPTIONS" :key="item.value" :label="item.label" :value="item.value" />
                    </el-select>
                  </el-form-item>
                  <el-form-item label="通知角色">
                    <el-select
                      v-model="selectedNode.config.notify"
                      multiple
                      placeholder="选择需要通知的角色"
                      style="width: 100%"
                    >
                      <el-option v-for="item in NOTIFY_OPTIONS" :key="item.value" :label="item.label" :value="item.value" />
                    </el-select>
                  </el-form-item>
                  <el-form-item label="提示信息">
                    <el-input
                      v-model="selectedNode.config.message"
                      type="textarea"
                      :rows="3"
                      placeholder="如：P1 数据禁止未授权出境"
                    />
                  </el-form-item>
                </template>

                <el-form-item label="画布坐标">
                  <div style="display: flex; gap: 8px">
                    <el-input-number v-model="selectedNode.x" :min="0" :max="CANVAS_WIDTH - 20" controls-position="right" />
                    <el-input-number v-model="selectedNode.y" :min="0" :max="CANVAS_HEIGHT - 20" controls-position="right" />
                  </div>
                </el-form-item>
                <el-form-item>
                  <el-button type="danger" plain :icon="Delete" @click="removeNode(selectedNode.id)">删除该节点</el-button>
                </el-form-item>
              </el-form>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- 已保存规则列表 -->
    <div class="fs-card">
      <div class="fs-card__header">
        <span class="fs-card__title">已保存规则</span>
        <el-button text :icon="Refresh" :loading="loading" @click="loadRules">刷新</el-button>
      </div>
      <div class="fs-card__body">
        <div class="fs-toolbar">
          <el-select v-model="ruleQuery.scene" placeholder="作用场景" clearable style="width: 170px" @change="loadRules">
            <el-option v-for="item in SCENE_OPTIONS" :key="item.value" :label="item.label" :value="item.value" />
          </el-select>
          <el-select v-model="ruleQuery.enabled" placeholder="启用状态" clearable style="width: 140px" @change="loadRules">
            <el-option label="已启用" :value="true" />
            <el-option label="已禁用" :value="false" />
          </el-select>
          <span class="fs-muted">共 {{ ruleList.length }} 条规则</span>
        </div>

        <el-table v-loading="loading" :data="ruleList" border stripe>
          <el-table-column prop="code" label="规则编码" width="140" show-overflow-tooltip>
            <template #default="{ row }">{{ row.code || '-' }}</template>
          </el-table-column>
          <el-table-column prop="name" label="规则名称" min-width="200" show-overflow-tooltip>
            <template #default="{ row }">
              <span>{{ row.name || '-' }}</span>
              <el-tag v-if="row.version" size="small" effect="plain" style="margin-left: 6px">v{{ row.version }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="description" label="作用说明" min-width="240" show-overflow-tooltip>
            <template #default="{ row }">{{ row.description || '-' }}</template>
          </el-table-column>
          <el-table-column prop="scene" label="场景" width="120">
            <template #default="{ row }">{{ sceneLabel(row.scene) }}</template>
          </el-table-column>
          <el-table-column prop="priority" label="优先级" width="90" align="center">
            <template #default="{ row }">{{ row.priority ?? '-' }}</template>
          </el-table-column>
          <el-table-column prop="updatedAt" label="最后修改时间" width="170">
            <template #default="{ row }">{{ formatTime(row.updatedAt) }}</template>
          </el-table-column>
          <el-table-column prop="enabled" label="状态" width="90">
            <template #default="{ row }">
              <el-tag :type="row.enabled ? 'success' : 'info'" size="small">
                {{ row.enabled ? '已启用' : '已禁用' }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column label="操作" width="210" fixed="right">
            <template #default="{ row }">
              <el-button link type="primary" @click="onEditRule(row)">编辑</el-button>
              <el-button link type="warning" :loading="togglingId === row.id" @click="onToggleRule(row)">
                {{ row.enabled ? '禁用' : '启用' }}
              </el-button>
              <el-button link type="danger" @click="onDeleteRule(row)">删除</el-button>
            </template>
          </el-table-column>
          <template #empty>
            <el-empty description="暂无规则，请在上方画布中编排并保存" :image-size="80" />
          </template>
        </el-table>
      </div>
    </div>
  </div>
</template>

<script setup>
/**
 * 规则引擎可视化配置（对应设计文档图 17 / 图 18）
 *
 * 画布实现说明（不引入第三方拖拽库）：
 * 1. 节点坐标统一使用「画布坐标系」（左上角为原点），直接等于鼠标事件坐标 + 容器滚动偏移，
 *    避免画布滚动后节点与鼠标位置错位；SVG 连线层与节点层共用同一坐标系。
 * 2. 新增节点：HTML5 原生拖拽（dragstart 写入模板索引，drop 读取并换算坐标）。
 * 3. 移动节点：mousedown/mousemove/mouseup 手动跟踪，位移超过阈值(4px)才算拖动，
 *    否则视为点击选中，避免「想选中却轻微移动」的体验问题。
 * 4. 连线：从节点右侧连接点 mousedown 开始，mouseup 落在目标节点上结束；
 *    连线数据落库为 edges:[{source,target}]（仅存节点 id，坐标由前端实时计算）。
 */
import { computed, onBeforeUnmount, onMounted, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Close, Delete, Plus, Refresh, Select } from '@element-plus/icons-vue'
import { complianceApi } from '@/api'
import { formatTime } from '@/utils/format'

/* ---------------- 画布与节点尺寸常量 ---------------- */
const CANVAS_WIDTH = 1100
const CANVAS_HEIGHT = 560
const NODE_WIDTH = 168
const NODE_HEIGHT = 62 // 与 .rule-node 的 min-height 保持一致，用于计算连线端点
const DRAG_THRESHOLD = 4 // 位移阈值，小于该值视为点击而非拖动

/** 节点类型 → 主题色（触发蓝 / 判断橙 / 动作绿） */
const NODE_COLORS = {
  trigger: '#1f5fd8',
  condition: '#f5a623',
  action: '#14a37f'
}
const NODE_TYPE_NAMES = {
  trigger: '触发条件',
  condition: '判断条件',
  action: '执行动作'
}

// 场景取值与后端 models.ComplianceRule.scene 的枚举保持一致
// （data_transfer / authorization / compute / masking）
const SCENE_OPTIONS = [
  { label: '数据出境传输', value: 'data_transfer' },
  { label: '数据授权审批', value: 'authorization' },
  { label: '隐私计算任务', value: 'compute' },
  { label: '数据脱敏', value: 'masking' },
  { label: '监管报送', value: 'report' }
]

const OP_OPTIONS = [
  { label: '等于 eq', value: 'eq' },
  { label: '不等于 ne', value: 'ne' },
  { label: '大于 gt', value: 'gt' },
  { label: '大于等于 gte', value: 'gte' },
  { label: '小于 lt', value: 'lt' },
  { label: '小于等于 lte', value: 'lte' },
  { label: '包含于 in', value: 'in' },
  { label: '包含 contains', value: 'contains' },
  { label: '存在 exists', value: 'exists' },
  { label: '正则匹配 regex', value: 'regex' }
]

const ACTION_OPTIONS = [
  { label: '阻断 block', value: 'block' },
  { label: '脱敏 mask', value: 'mask' },
  { label: '补充要件 require', value: 'require' },
  { label: '告警 notify', value: 'notify' },
  { label: '存证 audit', value: 'audit' },
  { label: '放行 allow', value: 'allow' }
]

const NOTIFY_OPTIONS = [
  { label: '数据安全管理端（admin）', value: 'security.admin' },
  { label: '全球合规部（compliance.lead）', value: 'compliance.lead' },
  { label: '风控技术部（risk.officer）', value: 'risk.officer' },
  { label: '监管机构（regulator）', value: 'regulator' },
  { label: '业务商户（merchant）', value: 'merchant' }
]

const FIELD_OPTIONS = [
  { label: '数据分级 dataLevel', value: 'dataLevel' },
  { label: '来源地区 sourceRegion', value: 'sourceRegion' },
  { label: '目的地地区 targetRegion', value: 'targetRegion' },
  { label: '数据字段 fields', value: 'fields' },
  { label: '使用目的 purpose', value: 'purpose' },
  { label: '已签订 SCC hasScc', value: 'hasScc' },
  { label: '已完成 DPIA hasDpia', value: 'hasDpia' },
  { label: '已取得授权 authorized', value: 'authorized' },
  { label: '交易金额 amount', value: 'amount' },
  { label: '合作方区域 partnerRegion', value: 'partnerRegion' }
]

/* ---------------- 页面状态 ---------------- */
const route = useRoute()
const router = useRouter()

const loading = ref(false)
const saving = ref(false)
const templateLoading = ref(false)
const togglingId = ref(null)

const canvasRef = ref(null)
const nodes = ref([])
const edges = ref([])
const selectedId = ref('')
const templates = reactive({ triggers: [], conditions: [], actions: [] })

const ruleForm = reactive({
  name: '',
  description: '',
  scene: 'data_transfer',
  priority: 10,
  enabled: true
})
const editingId = ref(null) // 非空表示编辑已有规则，保存时走 PUT
const ruleList = ref([])
const ruleQuery = reactive({ scene: '', enabled: '' })

/* 拖动节点 / 拉连线 的运行时状态（不需要响应式渲染的部分放在普通对象里） */
const drag = reactive({ active: false, nodeId: '', startX: 0, startY: 0, originX: 0, originY: 0, moved: false })
const linking = reactive({ active: false, source: '', mouseX: 0, mouseY: 0, from: null })

let nodeSeq = 0

/* ---------------- 计算属性 ---------------- */
const templateGroups = computed(() => [
  { type: 'trigger', title: '触发条件', items: templates.triggers || [] },
  { type: 'condition', title: '判断条件', items: templates.conditions || [] },
  { type: 'action', title: '执行动作', items: templates.actions || [] }
])

const triggerTemplates = computed(() => templates.triggers || [])

const selectedNode = computed(() => nodes.value.find((item) => item.id === selectedId.value) || null)

/** 节点 id → 节点对象，供连线坐标计算使用 */
const nodeMap = computed(() => {
  const map = {}
  nodes.value.forEach((node) => {
    map[node.id] = node
  })
  return map
})

/** 把 edges 换算为 SVG path（直线 + 箭头），无效连线（节点已删除）自动忽略 */
const edgePaths = computed(() =>
  (edges.value || [])
    .map((edge) => {
      const source = nodeMap.value[edge.source]
      const target = nodeMap.value[edge.target]
      if (!source || !target) return null
      return { d: linePath(source, target) }
    })
    .filter(Boolean)
)

/** 拉线过程中的虚线预览 */
const previewPath = computed(() => {
  if (!linking.active || !linking.from) return ''
  return `M ${linking.from.x} ${linking.from.y} L ${linking.mouseX} ${linking.mouseY}`
})

/* ---------------- 工具函数 ---------------- */
function nodeColor(type) {
  return NODE_COLORS[type] || '#64748b'
}

function sceneLabel(value) {
  return SCENE_OPTIONS.find((item) => item.value === value)?.label || value || '-'
}

/** 连线端点：从源节点右边中点 → 目标节点左边中点 */
function linePath(source, target) {
  const x1 = (source.x || 0) + NODE_WIDTH
  const y1 = (source.y || 0) + NODE_HEIGHT / 2
  const x2 = target.x || 0
  const y2 = (target.y || 0) + NODE_HEIGHT / 2
  return `M ${x1} ${y1} L ${x2} ${y2}`
}

/** 节点摘要：让画布上一眼能看出判断口径/动作，无需逐个点开属性面板 */
function configSummary(node) {
  const config = node.config || {}
  if (node.type === 'trigger') return config.event ? `事件：${config.event}` : '未设置触发事件'
  if (node.type === 'condition') {
    if (!config.field && !config.op) return '未设置判断条件'
    return `${config.field || 'field'} ${config.op || 'op'} ${config.value ?? ''}`.trim()
  }
  if (node.type === 'action') {
    const label = ACTION_OPTIONS.find((item) => item.value === config.action)?.label || config.action || '未设置动作'
    return config.message ? `${label} · ${config.message}` : label
  }
  return ''
}

/** 取鼠标在画布坐标系中的位置（含滚动偏移，保证画布滚动后坐标依然正确） */
function canvasPoint(event) {
  const el = canvasRef.value
  if (!el) return { x: 0, y: 0 }
  const rect = el.getBoundingClientRect()
  return {
    x: event.clientX - rect.left + el.scrollLeft,
    y: event.clientY - rect.top + el.scrollTop
  }
}

function nextNodeId() {
  nodeSeq += 1
  return `n${Date.now().toString(36)}${nodeSeq}`
}

/* ---------------- 左侧面板 → 画布 拖拽新增 ---------------- */
function onPaletteDragStart(event, type, index) {
  const item = (templates[`${type}s`] || [])[index] || {}
  // 只传索引与类型，模板内容在 drop 时重新读取，避免把整个对象塞进 dataTransfer
  event.dataTransfer.setData('application/x-rule-node', JSON.stringify({ type, index }))
  event.dataTransfer.effectAllowed = 'copy'
  void item
}

function onCanvasDragOver(event) {
  event.preventDefault()
  event.dataTransfer.dropEffect = 'copy'
}

function onCanvasDrop(event) {
  event.preventDefault()
  const raw = event.dataTransfer.getData('application/x-rule-node')
  if (!raw) return
  let payload = {}
  try {
    payload = JSON.parse(raw)
  } catch (error) {
    ElMessage.error('节点模板解析失败，请重新拖拽')
    return
  }
  const template = (templates[`${payload.type}s`] || [])[payload.index]
  if (!template) {
    ElMessage.warning('未找到该节点模板，请刷新页面重试')
    return
  }
  const point = canvasPoint(event)
  // 以鼠标落点为中心放置卡片，并限制在画布范围内
  const x = Math.max(0, Math.min(CANVAS_WIDTH - NODE_WIDTH, Math.round(point.x - NODE_WIDTH / 2)))
  const y = Math.max(0, Math.min(CANVAS_HEIGHT - NODE_HEIGHT, Math.round(point.y - NODE_HEIGHT / 2)))
  const node = {
    id: nextNodeId(),
    type: payload.type,
    name: template.label || NODE_TYPE_NAMES[payload.type] || '新节点',
    x,
    y,
    config: buildConfig(payload.type, template)
  }
  nodes.value.push(node)
  selectedId.value = node.id
  ElMessage.success(`已添加节点：${node.name}`)
}

/**
 * 依据模板生成节点初始配置。
 * 注意：后端 /compliance/rule-templates 返回的是「扁平」模板对象
 * （如 {type:'condition', field:'dataLevel', op:'eq', value:'P1', label, description}），
 * 并没有嵌套的 config 字段；但节点落库时 config 必须是嵌套对象
 * （规则引擎 evaluate_node 读取 node.config.field / op / value）。
 * 因此这里显式地按类型组装 config，同时兼容后端未来改成 {type,label,description,config} 的形态。
 */
function buildConfig(type, template) {
  const source = { ...(template?.config || {}), ...(template || {}) }
  if (type === 'condition') {
    return {
      field: source.field || 'dataLevel',
      op: source.op || 'eq',
      value: source.value ?? 'P1'
    }
  }
  if (type === 'action') {
    return {
      action: source.action || 'block',
      notify: Array.isArray(source.notify) ? source.notify : [],
      message: source.message || ''
    }
  }
  // 触发条件：模板用 event 字段（如 data.transfer）
  return { event: source.event || '' }
}

/* ---------------- 节点选中与拖动 ---------------- */
function selectNode(node) {
  selectedId.value = node.id
}

function onCanvasClick() {
  // 点击画布空白处取消选中，方便快速取消高亮
  selectedId.value = ''
}

function onNodeMouseDown(event, node) {
  // 只响应左键
  if (event.button !== 0) return
  selectedId.value = node.id
  const point = canvasPoint(event)
  drag.active = true
  drag.nodeId = node.id
  drag.startX = point.x
  drag.startY = point.y
  drag.originX = node.x || 0
  drag.originY = node.y || 0
  drag.moved = false
}

function onMouseMove(event) {
  if (drag.active) {
    const node = nodeMap.value[drag.nodeId]
    if (!node) return
    const point = canvasPoint(event)
    const dx = point.x - drag.startX
    const dy = point.y - drag.startY
    if (!drag.moved && Math.abs(dx) + Math.abs(dy) < DRAG_THRESHOLD) return
    drag.moved = true
    node.x = Math.max(0, Math.min(CANVAS_WIDTH - NODE_WIDTH, Math.round(drag.originX + dx)))
    node.y = Math.max(0, Math.min(CANVAS_HEIGHT - NODE_HEIGHT, Math.round(drag.originY + dy)))
    return
  }
  if (linking.active) {
    const point = canvasPoint(event)
    linking.mouseX = point.x
    linking.mouseY = point.y
  }
}

function onMouseUp() {
  drag.active = false
  drag.nodeId = ''
  // 拉线在空白处松开 → 取消本次连线（避免产生指向不存在的边）
  if (linking.active) {
    cancelLinking()
  }
}

/* ---------------- 连线（从连接点拖到目标节点） ---------------- */
function onPortMouseDown(event, node) {
  if (event.button !== 0) return
  const point = canvasPoint(event)
  linking.active = true
  linking.source = node.id
  linking.mouseX = point.x
  linking.mouseY = point.y
  linking.from = { x: (node.x || 0) + NODE_WIDTH, y: (node.y || 0) + NODE_HEIGHT / 2 }
}

function onNodeMouseUp(event, node) {
  if (!linking.active) return
  event.stopPropagation()
  const source = linking.source
  cancelLinking()
  if (!source || source === node.id) {
    ElMessage.warning('不能连接到节点自身')
    return
  }
  const exists = edges.value.some((edge) => edge.source === source && edge.target === node.id)
  if (exists) {
    ElMessage.warning('该连线已存在')
    return
  }
  // 一个连接点只保留一条出线，重复拉线时替换旧连线，避免规则语义歧义
  const duplicated = edges.value.find((edge) => edge.source === source)
  if (duplicated) {
    duplicated.target = node.id
  } else {
    edges.value.push({ source, target: node.id })
  }
  ElMessage.success('连线已建立')
}

function cancelLinking() {
  linking.active = false
  linking.source = ''
  linking.from = null
}

/* ---------------- 节点删除（级联删除相关连线） ---------------- */
function removeNode(id) {
  nodes.value = nodes.value.filter((node) => node.id !== id)
  // 同步清理与该节点相关的连线，否则后端会收到悬空的 source/target
  edges.value = edges.value.filter((edge) => edge.source !== id && edge.target !== id)
  if (selectedId.value === id) selectedId.value = ''
}

function onClearCanvas() {
  if (!nodes.value.length && !edges.value.length) {
    ElMessage.info('画布已是空的')
    return
  }
  ElMessageBox.confirm('清空画布会移除所有未保存的节点与连线，确认继续？', '清空画布', {
    type: 'warning',
    confirmButtonText: '清空',
    cancelButtonText: '取消'
  })
    .then(() => {
      nodes.value = []
      edges.value = []
      selectedId.value = ''
      ElMessage.success('画布已清空')
    })
    .catch(() => {})
}

/* ---------------- 新建 / 保存 / 编辑 ---------------- */
function onNewRule() {
  editingId.value = null
  nodes.value = []
  edges.value = []
  selectedId.value = ''
  ruleForm.name = ''
  ruleForm.description = ''
  ruleForm.scene = 'data_transfer'
  ruleForm.priority = 10
  ruleForm.enabled = true
  // 清掉 query 上的 id，避免刷新后又回到编辑态
  if (route.query.id) router.replace({ path: route.path })
  ElMessage.info('已切换到新建规则模式')
}

function buildPayload() {
  return {
    name: ruleForm.name.trim(),
    description: ruleForm.description.trim(),
    scene: ruleForm.scene,
    priority: Number(ruleForm.priority) || 1,
    enabled: Boolean(ruleForm.enabled),
    // 只提交后端契约需要的字段，config 原样透传给规则引擎
    nodes: nodes.value.map((node) => ({
      id: node.id,
      type: node.type,
      name: node.name,
      x: Math.round(node.x || 0),
      y: Math.round(node.y || 0),
      config: node.config || {}
    })),
    edges: edges.value.map((edge) => ({ source: edge.source, target: edge.target }))
  }
}

async function onSaveRule() {
  if (!ruleForm.name.trim()) {
    ElMessage.warning('请先填写规则名称')
    return
  }
  if (!nodes.value.length) {
    ElMessage.warning('画布为空：请至少添加一个节点')
    return
  }
  const hasTrigger = nodes.value.some((node) => node.type === 'trigger')
  if (!hasTrigger) {
    ElMessage.warning('规则需包含至少一个「触发条件」节点，否则引擎无法确定执行时机')
    return
  }
  const payload = buildPayload()
  saving.value = true
  try {
    if (editingId.value) {
      await complianceApi.updateRule(editingId.value, payload)
      ElMessage.success('规则已更新')
    } else {
      await complianceApi.createRule(payload)
      ElMessage.success('规则已创建')
    }
    await loadRules()
  } catch (error) {
    // 请求拦截器已统一提示错误，这里不再重复弹窗
  } finally {
    saving.value = false
  }
}

/**
 * 从列表进入编辑：把后端返回的 nodes/edges 还原到画布
 * @param {Object} row 规则记录
 */
function onEditRule(row) {
  editingId.value = row.id
  ruleForm.name = row.name || ''
  ruleForm.description = row.description || ''
  ruleForm.scene = row.scene || 'data_transfer'
  ruleForm.priority = row.priority ?? 10
  ruleForm.enabled = row.enabled !== false
  // 兜底：后端历史数据可能缺少 config/x/y，补默认值避免画布渲染异常
  nodes.value = (row.nodes || []).map((node, index) => ({
    id: node.id || `n${index + 1}`,
    type: node.type || 'condition',
    name: node.name || NODE_TYPE_NAMES[node.type] || '未命名节点',
    x: Number(node.x) || 60 + index * 200,
    y: Number(node.y) || 120,
    config: node.config || {}
  }))
  edges.value = (row.edges || []).map((edge) => ({ source: edge.source, target: edge.target }))
  selectedId.value = nodes.value[0]?.id || ''
  window.scrollTo({ top: 0, behavior: 'smooth' })
  ElMessage.success(`已载入规则「${row.name || row.code || row.id}」`)
}

async function onToggleRule(row) {
  togglingId.value = row.id
  try {
    await complianceApi.toggleRule(row.id, !row.enabled)
    row.enabled = !row.enabled
    ElMessage.success(row.enabled ? '规则已启用' : '规则已禁用')
  } catch (error) {
    // 已统一提示
  } finally {
    togglingId.value = null
  }
}

function onDeleteRule(row) {
  ElMessageBox.confirm(`确认删除规则「${row.name || row.code || row.id}」？删除后不可恢复。`, '删除规则', {
    type: 'warning',
    confirmButtonText: '删除',
    cancelButtonText: '取消'
  })
    .then(async () => {
      try {
        await complianceApi.deleteRule(row.id)
        ElMessage.success('规则已删除')
        if (editingId.value === row.id) onNewRule()
        await loadRules()
      } catch (error) {
        // 已统一提示
      }
    })
    .catch(() => {})
}

/* ---------------- 数据加载 ---------------- */
async function loadRules() {
  loading.value = true
  try {
    const params = {}
    if (ruleQuery.scene) params.scene = ruleQuery.scene
    if (ruleQuery.enabled !== '' && ruleQuery.enabled !== null) params.enabled = ruleQuery.enabled
    const data = await complianceApi.rules(params)
    // 兼容后端返回数组或分页对象两种形态
    ruleList.value = Array.isArray(data) ? data : data?.list ?? []
  } catch (error) {
    ruleList.value = []
  } finally {
    loading.value = false
  }
}

async function loadTemplates() {
  templateLoading.value = true
  try {
    const data = await complianceApi.ruleTemplates()
    templates.triggers = data?.triggers ?? []
    templates.conditions = data?.conditions ?? []
    templates.actions = data?.actions ?? []
  } catch (error) {
    templates.triggers = []
    templates.conditions = []
    templates.actions = []
  } finally {
    templateLoading.value = false
  }
}

async function load() {
  loading.value = true
  try {
    await Promise.all([loadTemplates(), loadRules()])
    // 支持从其他页面带 ?id= 直接进入编辑态
    const id = route.query.id
    if (id) {
      const target = ruleList.value.find((item) => String(item.id) === String(id))
      if (target) onEditRule(target)
    }
  } finally {
    loading.value = false
  }
}

onMounted(() => {
  window.addEventListener('mousemove', onMouseMove)
  window.addEventListener('mouseup', onMouseUp)
  load()
})

onBeforeUnmount(() => {
  window.removeEventListener('mousemove', onMouseMove)
  window.removeEventListener('mouseup', onMouseUp)
})
</script>

<style scoped>
.rule-builder {
  display: grid;
  grid-template-columns: 220px minmax(0, 1fr) 300px;
  gap: 14px;
  align-items: stretch;
}
@media (max-width: 1440px) {
  .rule-builder {
    grid-template-columns: 200px minmax(0, 1fr) 280px;
  }
}

/* 左侧节点面板 */
.rule-panel {
  border: 1px solid var(--fs-border);
  border-radius: 8px;
  overflow: hidden;
  background: #fbfcfe;
}
.rule-panel__title {
  padding: 10px 12px;
  font-size: 13px;
  font-weight: 600;
  background: #f2f5fa;
  border-bottom: 1px solid var(--fs-border);
}
.rule-panel__body {
  padding: 10px;
  max-height: 560px;
  overflow-y: auto;
}
.rule-panel__group + .rule-panel__group {
  margin-top: 12px;
}
.rule-panel__group-name {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  color: var(--fs-text-secondary);
  margin-bottom: 6px;
}
.rule-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  display: inline-block;
}
.rule-palette {
  padding: 8px 10px;
  margin-bottom: 8px;
  background: #fff;
  border: 1px solid var(--fs-border);
  border-left-width: 3px;
  border-radius: 6px;
  cursor: grab;
  transition: box-shadow 0.15s ease, transform 0.15s ease;
}
.rule-palette:hover {
  box-shadow: 0 3px 10px rgba(31, 39, 51, 0.1);
  transform: translateY(-1px);
}
.rule-palette:active {
  cursor: grabbing;
}
.rule-palette__label {
  font-size: 13px;
  font-weight: 500;
}
.rule-palette__desc {
  margin-top: 3px;
  font-size: 12px;
  color: var(--fs-text-secondary);
  line-height: 1.4;
}

/* 中间画布 */
.rule-canvas-wrap {
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.rule-canvas {
  position: relative;
  width: 100%;
  height: 560px;
  overflow: auto;
  border: 1px dashed #cfd8e6;
  border-radius: 8px;
  background-color: #fafbfe;
  /* 点阵背景：便于用户判断节点对齐与坐标 */
  background-image: radial-gradient(#dde4ef 1px, transparent 1px);
  background-size: 18px 18px;
  user-select: none;
}
.rule-canvas--linking {
  border-color: var(--fs-primary);
  cursor: crosshair;
}
.rule-canvas__svg {
  position: absolute;
  left: 0;
  top: 0;
  pointer-events: none;
  overflow: visible;
}
.rule-canvas__empty {
  position: absolute;
  left: 0;
  top: 120px;
  width: 100%;
  pointer-events: none;
}
.rule-canvas__footer {
  font-size: 12px;
}

/* 画布节点卡片 */
.rule-node {
  position: absolute;
  width: 168px;
  min-height: 62px;
  padding: 8px 10px;
  background: #fff;
  border: 1px solid var(--fs-border);
  border-top: 3px solid var(--fs-primary);
  border-radius: 8px;
  box-shadow: 0 2px 8px rgba(31, 39, 51, 0.08);
  cursor: move;
  box-sizing: border-box;
}
.rule-node--active {
  box-shadow: 0 0 0 2px rgba(31, 95, 216, 0.35), 0 4px 14px rgba(31, 39, 51, 0.14);
}
.rule-node__type {
  display: inline-block;
  padding: 0 6px;
  border-radius: 3px;
  color: #fff;
  font-size: 11px;
  line-height: 16px;
}
.rule-node__name {
  margin-top: 5px;
  font-size: 13px;
  font-weight: 600;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.rule-node__config {
  margin-top: 2px;
  font-size: 11px;
  color: var(--fs-text-secondary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.rule-node__delete {
  position: absolute;
  right: 4px;
  top: 4px;
  width: 18px;
  height: 18px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 50%;
  color: #9aa7b8;
  cursor: pointer;
}
.rule-node__delete:hover {
  background: #fdecec;
  color: var(--fs-danger);
}
.rule-node__port {
  position: absolute;
  right: -7px;
  top: 50%;
  margin-top: -6px;
  width: 12px;
  height: 12px;
  border-radius: 50%;
  background: #fff;
  border: 2px solid var(--fs-primary);
  cursor: crosshair;
}
.rule-node__port:hover {
  background: var(--fs-primary);
}
.rule-node__in-port {
  position: absolute;
  left: -6px;
  top: 50%;
  margin-top: -5px;
  width: 10px;
  height: 10px;
  border-radius: 50%;
  background: #dfe6f1;
  border: 1px solid #b9c5d8;
}

/* 右侧属性面板 */
.rule-props {
  border: 1px solid var(--fs-border);
  border-radius: 8px;
  overflow: hidden;
  background: #fff;
}
.rule-props__body {
  padding: 12px;
  max-height: 560px;
  overflow-y: auto;
}
</style>
