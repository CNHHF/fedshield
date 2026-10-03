<template>
  <div class="fs-page">
    <!-- 标题区 -->
    <div class="fs-page__header">
      <div>
        <h2 class="fs-page__title">智能风控与异常监测</h2>
        <p class="fs-page__subtitle">
          对应赛题 A16「建设范围二：智能风控能力建设」·
          交易风险识别 → 账户/商户风险评估 → 异常行为检测 → 实时预警 → 自动处置闭环
          · 数据更新时间 {{ updatedAt || '-' }}
        </p>
      </div>
      <div class="fs-toolbar__right">
        <el-tag :type="scanned ? 'success' : 'info'" effect="plain" size="large">
          最近扫描 {{ scanned ? `${scanned} 笔交易` : '尚未执行检测' }}
        </el-tag>
      </div>
    </div>

    <!-- 检测控制卡：手动触发异常检测与刷新 -->
    <div class="fs-card">
      <div class="fs-card__body">
        <div class="fs-toolbar" style="margin-bottom: 0">
          <span class="fs-muted">扫描交易条数</span>
          <el-input-number
            v-model="detectForm.limit"
            :min="20"
            :max="2000"
            :step="100"
            controls-position="right"
            style="width: 160px"
          />
          <el-button type="primary" :loading="detecting" @click="runDetect">
            <el-icon><Cpu /></el-icon>
            <span>执行异常检测</span>
          </el-button>
          <el-button :loading="loading" @click="loadAll">
            <el-icon><Refresh /></el-icon>
            <span>刷新</span>
          </el-button>
          <span class="fs-muted">
            检测命中规则后按统一处置口径自动处置（自动放行 / 二次验证 / 转人工复核 / 自动拦截），人工可再确认
          </span>
        </div>
      </div>
    </div>

    <!-- KPI 行：预警规模、等级分布、涉险金额与处置自动化水平 -->
    <div class="fs-grid fs-grid--4 ops-monitor__kpis">
      <StatCard
        v-for="item in kpiCards"
        :key="item.label"
        :label="item.label"
        :value="item.value"
        :unit="item.unit"
        :sub="item.sub"
        :icon="item.icon"
        :color="item.color"
        :precision="item.precision || 0"
      />
    </div>

    <!-- 处置闭环：命中规则分布 + 处置动作分布 -->
    <div class="fs-grid fs-grid--2 ops-monitor__charts">
      <div class="fs-card">
        <div class="fs-card__header">
          <span class="fs-card__title">命中规则分布</span>
          <span class="fs-muted">共 {{ (summary.byRule || []).length }} 类规则命中</span>
        </div>
        <div class="fs-card__body">
          <ChartBox :option="byRuleOption" :height="320" :loading="loading" empty-text="暂无预警，请先执行异常检测" />
        </div>
      </div>

      <div class="fs-card">
        <div class="fs-card__header">
          <span class="fs-card__title">处置动作分布（自动处置闭环）</span>
          <span class="fs-muted">自动化处置率 {{ percentText(summary.autoHandledRate) }}</span>
        </div>
        <div class="fs-card__body">
          <ChartBox :option="byActionOption" :height="320" :loading="loading" empty-text="暂无处置数据" />
        </div>
      </div>
    </div>

    <!-- 异常检测规则 -->
    <div class="fs-card">
      <div class="fs-card__header">
        <span class="fs-card__title">异常检测规则</span>
        <span class="fs-muted">共 {{ rules.length }} 条可解释规则 · 每条预警均输出证据链</span>
      </div>
      <div class="fs-card__body">
        <el-table v-loading="loading" :data="rules" border stripe size="small" style="width: 100%">
          <el-table-column prop="name" label="规则名" width="200">
            <template #default="{ row }">
              <div class="ops-monitor__rule">
                <strong>{{ row?.name || '-' }}</strong>
                <span class="fs-mono fs-muted">{{ row?.code || '-' }}</span>
              </div>
            </template>
          </el-table-column>

          <el-table-column prop="desc" label="说明" min-width="360" show-overflow-tooltip>
            <template #default="{ row }">{{ row?.desc || '-' }}</template>
          </el-table-column>

          <el-table-column label="基础分" width="110" align="center">
            <template #default="{ row }">
              <el-tag size="small" effect="plain">{{ Number(row?.baseScore || 0).toFixed(2) }}</el-tag>
            </template>
          </el-table-column>

          <el-table-column prop="threshold" label="触发阈值" width="180">
            <template #default="{ row }">{{ row?.threshold || '-' }}</template>
          </el-table-column>

          <template #empty>暂无规则数据</template>
        </el-table>
        <p class="fs-muted ops-monitor__note">
          说明：规则可组合，同一商户命中多条规则时叠加组合风险加成，最高升级为自动拦截。
          风险分区间口径：≥0.85 自动拦截、≥0.70 转人工复核、≥0.45 二次验证、其余自动放行。
        </p>
      </div>
    </div>

    <!-- 实时预警 -->
    <div class="fs-card">
      <div class="fs-card__header">
        <span class="fs-card__title">实时预警</span>
        <span class="fs-muted">共 {{ total }} 条预警 · 按风险分倒序</span>
      </div>
      <div class="fs-card__body">
        <!-- 筛选条件由后端统一过滤，避免前端二次筛选造成分页口径错乱 -->
        <div class="fs-toolbar">
          <el-select v-model="query.riskLevel" placeholder="风险等级" style="width: 140px" @change="handleSearch">
            <el-option v-for="item in RISK_OPTIONS" :key="item.value" :label="item.label" :value="item.value" />
          </el-select>

          <el-select v-model="query.action" placeholder="处置动作" style="width: 160px" @change="handleSearch">
            <el-option label="全部动作" value="all" />
            <el-option v-for="item in actions" :key="item.code" :label="item.label" :value="item.code" />
          </el-select>

          <el-select v-model="query.status" placeholder="处置状态" style="width: 150px" @change="handleSearch">
            <el-option v-for="item in STATUS_OPTIONS" :key="item.value" :label="item.label" :value="item.value" />
          </el-select>

          <el-button type="primary" @click="handleSearch">
            <el-icon><Search /></el-icon>
            <span>查询</span>
          </el-button>
          <el-button @click="resetQuery">
            <el-icon><RefreshLeft /></el-icon>
            <span>重置</span>
          </el-button>
        </div>

        <el-table v-loading="loading" :data="alerts" border stripe style="width: 100%">
          <el-table-column label="预警编号" width="140" fixed>
            <template #default="{ row }">
              <span class="fs-mono">{{ row?.code || '-' }}</span>
            </template>
          </el-table-column>

          <el-table-column label="命中规则" min-width="190">
            <template #default="{ row }">
              <div class="ops-monitor__rule">
                <strong>{{ row?.ruleName || '-' }}</strong>
                <span class="fs-mono fs-muted">{{ row?.ruleCode || '-' }}</span>
              </div>
            </template>
          </el-table-column>

          <el-table-column label="对象" min-width="200">
            <template #default="{ row }">
              <div class="ops-monitor__target">
                <span>{{ row?.targetName || '-' }}</span>
                <span class="fs-mono fs-muted">{{ row?.targetId || '-' }}</span>
              </div>
            </template>
          </el-table-column>

          <el-table-column label="金额" width="140" align="right">
            <template #default="{ row }">
              <span>{{ formatAmount(row?.amount) }}</span>
            </template>
          </el-table-column>

          <el-table-column label="风险等级" width="110" align="center">
            <template #default="{ row }">
              <el-tag size="small" :type="riskTagType(row?.riskLevel)">
                {{ riskLabel(row?.riskLevel) }}
              </el-tag>
            </template>
          </el-table-column>

          <el-table-column label="风险分" width="170">
            <template #default="{ row }">
              <el-progress
                :percentage="scorePercent(row?.riskScore)"
                :stroke-width="10"
                :color="scoreColor(row?.riskLevel)"
                :format="() => Number(row?.riskScore || 0).toFixed(2)"
              />
            </template>
          </el-table-column>

          <el-table-column label="处置动作" width="120" align="center">
            <template #default="{ row }">
              <el-tag size="small" effect="plain" :type="actionTagType(row?.action)">
                {{ row?.actionLabel || actionLabel(row?.action) }}
              </el-tag>
            </template>
          </el-table-column>

          <el-table-column label="状态" width="120" align="center">
            <template #default="{ row }">
              <el-tag size="small" :type="statusOf(row?.status).type" effect="light">
                {{ statusOf(row?.status).label }}
              </el-tag>
            </template>
          </el-table-column>

          <el-table-column label="操作" width="180" fixed="right" align="center">
            <template #default="{ row }">
              <el-button link type="primary" @click="openEvidence(row)">证据</el-button>
              <el-button link type="warning" @click="openHandle(row)">确认处置</el-button>
            </template>
          </el-table-column>

          <template #empty>
            <el-empty description="暂无预警记录，请点击「执行异常检测」" :image-size="80" />
          </template>
        </el-table>

        <el-pagination
          v-model:current-page="query.page"
          v-model:page-size="query.size"
          :total="total"
          :page-sizes="[10, 20, 50]"
          layout="total, sizes, prev, pager, next, jumper"
          style="margin-top: 14px; justify-content: flex-end"
          @size-change="handleSizeChange"
          @current-change="loadAlerts"
        />
      </div>
    </div>

    <!-- 账户 / 商户风险 Top10 -->
    <div class="fs-card">
      <div class="fs-card__header">
        <span class="fs-card__title">账户/商户风险 Top10</span>
        <span class="fs-muted">按最高风险分排序 · 用于账户与商户风险评估</span>
      </div>
      <div class="fs-card__body">
        <el-table v-loading="loading" :data="accountRisk" border stripe size="small" style="width: 100%">
          <el-table-column label="商户编码" min-width="180">
            <template #default="{ row }">
              <span class="fs-mono">{{ row?.merchantCode || '-' }}</span>
            </template>
          </el-table-column>

          <el-table-column label="预警数" width="110" align="center">
            <template #default="{ row }">
              <el-tag size="small" effect="plain">{{ row?.alerts || 0 }}</el-tag>
            </template>
          </el-table-column>

          <el-table-column label="最高风险分" min-width="220">
            <template #default="{ row }">
              <el-progress
                :percentage="scorePercent(row?.maxScore)"
                :stroke-width="12"
                :color="scoreColor(levelOfScore(row?.maxScore))"
                :format="() => Number(row?.maxScore || 0).toFixed(2)"
              />
            </template>
          </el-table-column>

          <el-table-column label="涉险金额" min-width="150" align="right">
            <template #default="{ row }">
              <span>{{ formatAmount(row?.amount) }}</span>
            </template>
          </el-table-column>

          <template #empty>暂无账户风险数据，请先执行异常检测</template>
        </el-table>
      </div>
    </div>

    <!-- 证据链抽屉 -->
    <el-drawer v-model="evidenceVisible" title="预警证据链" size="560px">
      <template v-if="currentAlert">
        <el-descriptions :column="1" border size="small">
          <el-descriptions-item label="预警编号">
            <span class="fs-mono">{{ currentAlert.code || '-' }}</span>
          </el-descriptions-item>
          <el-descriptions-item label="命中规则">
            {{ currentAlert.ruleName || '-' }}
            <span class="fs-mono fs-muted">{{ currentAlert.ruleCode || '-' }}</span>
          </el-descriptions-item>
          <el-descriptions-item label="对象">
            {{ currentAlert.targetName || '-' }}（{{ currentAlert.targetId || '-' }}）
          </el-descriptions-item>
          <el-descriptions-item label="涉险金额">{{ formatAmount(currentAlert.amount) }}</el-descriptions-item>
          <el-descriptions-item label="风险评级">
            <el-tag size="small" :type="riskTagType(currentAlert.riskLevel)">
              {{ riskLabel(currentAlert.riskLevel) }}
            </el-tag>
            <span class="ops-monitor__score">风险分 {{ Number(currentAlert.riskScore || 0).toFixed(2) }}</span>
          </el-descriptions-item>
          <el-descriptions-item label="处置动作">
            <el-tag size="small" effect="plain" :type="actionTagType(currentAlert.action)">
              {{ currentAlert.actionLabel || actionLabel(currentAlert.action) }}
            </el-tag>
          </el-descriptions-item>
          <el-descriptions-item label="处置状态">
            <el-tag size="small" :type="statusOf(currentAlert.status).type">
              {{ statusOf(currentAlert.status).label }}
            </el-tag>
            <span class="fs-muted ops-monitor__score">{{ formatTime(currentAlert.handledAt) }}</span>
          </el-descriptions-item>
          <el-descriptions-item label="风险研判">{{ currentAlert.detail || '-' }}</el-descriptions-item>
        </el-descriptions>

        <el-divider content-position="left">证据链（可解释性依据）</el-divider>
        <el-empty v-if="!(currentAlert.evidence || []).length" description="暂无证据明细" :image-size="60" />
        <ul v-else class="ops-monitor__evidence">
          <li v-for="(item, index) in currentAlert.evidence || []" :key="index">
            <el-icon color="#1f5fd8"><Document /></el-icon>
            <span>{{ item }}</span>
          </li>
        </ul>
        <p class="fs-muted ops-monitor__note">
          预警依据来自规则命中与统计基线偏离，证据链可直接用于监管报送与人工复核留痕。
        </p>
      </template>
      <el-empty v-else description="请选择一条预警" :image-size="70" />
    </el-drawer>

    <!-- 人工确认处置 -->
    <el-dialog v-model="handleVisible" title="人工确认处置" width="460px">
      <el-descriptions :column="1" border size="small">
        <el-descriptions-item label="预警编号">
          <span class="fs-mono">{{ handleForm.code || '-' }}</span>
        </el-descriptions-item>
        <el-descriptions-item label="命中规则">{{ handleForm.ruleName || '-' }}</el-descriptions-item>
        <el-descriptions-item label="当前动作">{{ handleForm.actionLabel || '-' }}</el-descriptions-item>
      </el-descriptions>

      <div class="ops-monitor__handle">
        <span class="fs-muted">处置动作</span>
        <el-select v-model="handleForm.action" placeholder="请选择处置动作" style="width: 220px">
          <el-option v-for="item in actions" :key="item.code" :label="item.label" :value="item.code" />
        </el-select>
      </div>
      <p class="fs-muted">
        提交后预警状态将置为「人工已确认」并记录处置时间与操作人，形成「自动处置 + 人工确认」闭环。
      </p>

      <template #footer>
        <el-button @click="handleVisible = false">取消</el-button>
        <el-button type="primary" :loading="handling" @click="submitHandle">提交处置</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
/**
 * 智能风控与异常监测（赛题 A16 建设范围二）
 *
 * 数据来源（接口契约见 backend/api/ops.py「② 智能风控与异常监测」）：
 * - GET  /ops/monitoring/rules           规则与统一处置口径
 * - POST /ops/monitoring/detect          执行异常检测（落库并返回汇总）
 * - GET  /ops/monitoring/alerts          实时预警分页列表（等级/动作/状态筛选）
 * - POST /ops/monitoring/alerts/:id/handle  人工确认处置
 * - GET  /ops/monitoring/summary         汇总（含账户/商户风险 Top10）
 *
 * 说明：不使用 src/api/index.js（保持该文件不变），直接经 request 统一封装调用，
 * 以便复用鉴权、统一解包与错误提示；所有返回值均做空值兜底。
 */
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { Cpu, Refresh, RefreshLeft, Search } from '@element-plus/icons-vue'
import request from '@/api/request'
import ChartBox from '@/components/ChartBox.vue'
import StatCard from '@/components/StatCard.vue'
import { baseChartOption, formatAmount, formatTime } from '@/utils/format'

const loading = ref(false)
const detecting = ref(false)
const handling = ref(false)
const updatedAt = ref('')
const scanned = ref(0)

/** 检测参数：默认扫描 600 笔最新交易，与后端 20~2000 的取值区间保持一致 */
const detectForm = reactive({ limit: 600 })

/** 风控汇总（字段与 engine/monitoring.summarize_alerts 对齐，全部做空值兜底） */
const summary = reactive({
  total: 0,
  high: 0,
  medium: 0,
  low: 0,
  amountAtRisk: 0,
  byRule: [],
  byAction: [],
  autoHandledRate: 0,
  manualPendingRate: 0,
  accountRisk: []
})

const rules = ref([])
const actions = ref([])

const query = reactive({ riskLevel: 'all', action: 'all', status: 'all', page: 1, size: 10 })
const alerts = ref([])
const total = ref(0)

const evidenceVisible = ref(false)
const currentAlert = ref(null)
const handleVisible = ref(false)
const handleForm = reactive({ id: null, code: '', ruleName: '', actionLabel: '', action: '' })

const RISK_OPTIONS = [
  { label: '全部等级', value: 'all' },
  { label: '高危', value: 'high' },
  { label: '中危', value: 'medium' },
  { label: '低危', value: 'low' }
]

const STATUS_OPTIONS = [
  { label: '全部状态', value: 'all' },
  { label: '已自动处置', value: 'handled' },
  { label: '待人工确认', value: 'pending' },
  { label: '人工已确认', value: 'confirmed' }
]

/** 状态字典：handled/pending 由自动处置写入，confirmed 由人工确认写入 */
const STATUS_MAP = {
  handled: { label: '已自动处置', type: 'success' },
  pending: { label: '待人工确认', type: 'warning' },
  confirmed: { label: '人工已确认', type: 'success' },
  closed: { label: '已闭环', type: 'info' }
}

/** 处置动作配色：与 engine/monitoring.ACTIONS 口径一致 */
const ACTION_TYPES = { pass: 'success', verify: 'primary', manual: 'warning', block: 'danger' }
const ACTION_LABELS = { pass: '自动放行', verify: '二次验证', manual: '转人工复核', block: '自动拦截' }
const RISK_META = {
  high: { label: '高危', type: 'danger', color: '#e5484d' },
  medium: { label: '中危', type: 'warning', color: '#f5a623' },
  low: { label: '低危', type: 'success', color: '#14a37f' }
}

function riskMeta(level) {
  return RISK_META[level] || { label: level || '-', type: 'info', color: '#94a3b8' }
}

function riskLabel(level) {
  return RISK_META[level]?.label || level || '-'
}

function riskTagType(level) {
  return RISK_META[level]?.type || 'info'
}

function scoreColor(level) {
  return RISK_META[level]?.color || '#94a3b8'
}

function actionTagType(code) {
  return ACTION_TYPES[code] || 'info'
}

function actionLabel(code) {
  return ACTION_LABELS[code] || code || '-'
}

function statusOf(status) {
  return STATUS_MAP[status] || { label: status || '-', type: 'info' }
}

/** 风险分（0~1）转 el-progress 百分比（0~100 整数） */
function scorePercent(score) {
  const value = Number(score || 0) * 100
  return Math.max(0, Math.min(100, Math.round(value)))
}

/** 由分数反推等级（用于账户风险 Top10 的进度条配色） */
function levelOfScore(score) {
  const value = Number(score || 0)
  if (value >= 0.7) return 'high'
  if (value >= 0.4) return 'medium'
  return value > 0 ? 'low' : ''
}

/** 比率转百分比文本；后端可能返回 null，统一兜底为占位符 */
function percentText(value) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return '-'
  return `${(Number(value) * 100).toFixed(1)}%`
}

/* ---------------- KPI ---------------- */

const kpiCards = computed(() => [
  {
    label: '预警总数',
    value: Number(summary.total || 0),
    unit: '条',
    icon: 'Warning',
    color: '#1f5fd8',
    sub: `命中 ${(summary.byRule || []).length} 类检测规则`
  },
  {
    label: '高危预警',
    value: Number(summary.high || 0),
    unit: '条',
    icon: 'CircleCloseFilled',
    color: '#e5484d',
    sub: '风险分 ≥ 0.70，优先处置'
  },
  {
    label: '中危预警',
    value: Number(summary.medium || 0),
    unit: '条',
    icon: 'WarningFilled',
    color: '#f5a623',
    sub: '0.40 ≤ 风险分 < 0.70'
  },
  {
    label: '低危预警',
    value: Number(summary.low || 0),
    unit: '条',
    icon: 'InfoFilled',
    color: '#14a37f',
    sub: '风险分 < 0.40，持续监测'
  },
  {
    label: '涉险金额',
    value: Number(((summary.amountAtRisk || 0) / 10000).toFixed(2)),
    unit: '万元',
    precision: 2,
    icon: 'Money',
    color: '#8b5cf6',
    sub: '命中规则交易的金额合计'
  },
  {
    label: '自动化处置率',
    value: Number(((summary.autoHandledRate || 0) * 100).toFixed(1)),
    unit: '%',
    precision: 1,
    icon: 'MagicStick',
    color: '#0ea5e9',
    sub: '自动放行 + 自动拦截占比'
  },
  {
    label: '待人工比例',
    value: Number(((summary.manualPendingRate || 0) * 100).toFixed(1)),
    unit: '%',
    precision: 1,
    icon: 'UserFilled',
    color: '#e5484d',
    sub: '转人工复核预警占比'
  }
])

/* ---------------- 图表 ---------------- */

/** 命中规则分布：横轴规则名、纵轴预警数量 */
const byRuleOption = computed(() => {
  const rows = summary.byRule || []
  return baseChartOption({
    tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
    legend: { show: false },
    grid: { left: 20, right: 24, top: 30, bottom: 8, containLabel: true },
    xAxis: {
      type: 'category',
      data: rows.map((item) => item.ruleName || item.ruleCode || '-'),
      axisLabel: { interval: 0, fontSize: 11, rotate: rows.length > 4 ? 16 : 0 }
    },
    yAxis: { type: 'value', name: '预警数', minInterval: 1 },
    series: [
      {
        name: '命中预警数',
        type: 'bar',
        barMaxWidth: 36,
        itemStyle: { borderRadius: [4, 4, 0, 0] },
        label: { show: true, position: 'top', fontSize: 11 },
        data: rows.map((item) => Number(item.count || 0))
      }
    ]
  })
})

/** 处置动作分布：环形饼图（自动放行 / 二次验证 / 转人工复核 / 自动拦截） */
const byActionOption = computed(() => {
  const rows = summary.byAction || []
  const actionColor = { 自动放行: '#14a37f', 二次验证: '#1f5fd8', 转人工复核: '#f5a623', 自动拦截: '#e5484d' }
  return baseChartOption({
    tooltip: { trigger: 'item', formatter: '{b}：{c} 条（{d}%）' },
    legend: { bottom: 0, left: 'center', icon: 'circle', itemWidth: 10, itemHeight: 10, textStyle: { fontSize: 12 } },
    series: [
      {
        name: '处置动作分布',
        type: 'pie',
        radius: ['46%', '68%'],
        center: ['50%', '45%'],
        avoidLabelOverlap: true,
        itemStyle: { borderColor: '#fff', borderWidth: 2 },
        label: { formatter: '{b}\n{c} 条', fontSize: 11 },
        data: rows.map((item) => ({
          name: item.action || '未标注',
          value: Number(item.count || 0),
          itemStyle: { color: actionColor[item.action] }
        }))
      }
    ]
  })
})

const accountRisk = computed(() =>
  (summary.accountRisk || [])
    .slice()
    .sort((prev, next) => Number(next.maxScore || 0) - Number(prev.maxScore || 0))
)

/* ---------------- 数据加载 ---------------- */

/** 汇总兜底：直接覆盖 KPI，不依赖接口字段完整（total 为 0 时后端仅返回 4 个字段） */
function applySummary(payload) {
  const data = payload || {}
  Object.assign(summary, {
    total: Number(data.total || 0),
    high: Number(data.high || 0),
    medium: Number(data.medium || 0),
    low: Number(data.low || 0),
    amountAtRisk: Number(data.amountAtRisk || 0),
    byRule: data.byRule || [],
    byAction: data.byAction || [],
    autoHandledRate: Number(data.autoHandledRate || 0),
    manualPendingRate: Number(data.manualPendingRate || 0),
    accountRisk: data.accountRisk || []
  })
  updatedAt.value = formatTime(new Date())
}

async function loadRules() {
  const payload = await request.get('/ops/monitoring/rules')
  rules.value = payload?.rules || []
  actions.value = payload?.actions || []
}

async function loadSummary() {
  applySummary(await request.get('/ops/monitoring/summary'))
}

async function loadAlerts() {
  const payload = await request.get('/ops/monitoring/alerts', {
    params: {
      riskLevel: query.riskLevel,
      action: query.action,
      status: query.status,
      page: query.page,
      size: query.size
    }
  })
  alerts.value = payload?.list || []
  total.value = Number(payload?.total || 0)
}

async function loadAll() {
  loading.value = true
  try {
    // 三个接口相互独立，任一失败不影响其余数据的展示
    await Promise.all([loadRules(), loadSummary(), loadAlerts()])
  } catch (error) {
    // 错误提示已由请求层统一处理，这里仅保证页面渲染不中断
  } finally {
    loading.value = false
  }
}

/** 执行异常检测：后端基于交易数据生成预警并落库 */
async function runDetect() {
  detecting.value = true
  try {
    const payload = await request.post('/ops/monitoring/detect', { limit: detectForm.limit })
    const scannedCount = Number(payload?.scanned || 0)
    const detectedSummary = payload?.summary || {}
    const alertCount = Number(detectedSummary.total || (payload?.alerts || []).length)
    scanned.value = scannedCount
    applySummary(detectedSummary)
    ElMessage.success(`扫描 ${scannedCount} 笔 / 生成预警 ${alertCount} 条`)
    query.page = 1
    // 再拉取落库后的汇总与列表，保证页面与数据库口径一致
    await Promise.all([loadSummary(), loadAlerts()])
  } catch (error) {
    // 检测失败（如无交易数据）已由请求层提示，保持页面原状
  } finally {
    detecting.value = false
  }
}

function handleSearch() {
  query.page = 1
  loadAlerts().catch(() => {})
}

function handleSizeChange() {
  query.page = 1
  loadAlerts().catch(() => {})
}

function resetQuery() {
  query.riskLevel = 'all'
  query.action = 'all'
  query.status = 'all'
  handleSearch()
}

/* ---------------- 证据与处置 ---------------- */

function openEvidence(row) {
  currentAlert.value = row || null
  evidenceVisible.value = true
}

function openHandle(row) {
  if (!row?.id) {
    ElMessage.warning('该预警缺少主键，无法确认处置')
    return
  }
  handleForm.id = row.id
  handleForm.code = row.code || ''
  handleForm.ruleName = row.ruleName || ''
  handleForm.actionLabel = row.actionLabel || actionLabel(row.action)
  handleForm.action = row.action || actions.value[0]?.code || 'manual'
  handleVisible.value = true
}

async function submitHandle() {
  if (!handleForm.id) return
  if (!handleForm.action) {
    ElMessage.warning('请选择处置动作')
    return
  }
  handling.value = true
  try {
    await request.post(`/ops/monitoring/alerts/${handleForm.id}/handle`, {
      status: 'confirmed',
      action: handleForm.action
    })
    ElMessage.success('处置结果已确认')
    handleVisible.value = false
    await Promise.all([loadAlerts(), loadSummary()])
  } catch (error) {
    // 失败提示由请求层统一处理
  } finally {
    handling.value = false
  }
}

onMounted(loadAll)
</script>

<style scoped>
/* 栅格内卡片间距由 grid gap 控制，抵消全局 .fs-card + .fs-card 的上外边距 */
.fs-grid > .fs-card + .fs-card {
  margin-top: 0;
}
.ops-monitor__kpis,
.ops-monitor__charts {
  margin-top: 16px;
}
.fs-grid + .fs-card {
  margin-top: 16px;
}
.ops-monitor__rule,
.ops-monitor__target {
  display: flex;
  flex-direction: column;
  line-height: 1.5;
}
.ops-monitor__note {
  margin: 12px 0 0;
  line-height: 1.7;
}
.ops-monitor__score {
  margin-left: 8px;
}
.ops-monitor__evidence {
  margin: 0;
  padding: 0;
  list-style: none;
}
.ops-monitor__evidence li {
  display: flex;
  gap: 8px;
  padding: 9px 12px;
  margin-bottom: 8px;
  background: #f7f9fc;
  border: 1px solid var(--fs-border);
  border-radius: 8px;
  font-size: 13px;
  line-height: 1.6;
}
.ops-monitor__handle {
  display: flex;
  align-items: center;
  gap: 10px;
  margin: 16px 0 8px;
}
</style>
