<template>
  <div class="fs-page" v-loading="loading">
    <div class="fs-page__header">
      <div>
        <el-button :icon="ArrowLeft" text @click="goBack" style="padding-left: 0; margin-bottom: 4px">返回</el-button>
        <h2 class="fs-page__title">{{ detail?.typeName || detail?.type || '合规报告预览' }}</h2>
        <p class="fs-page__subtitle">
          报告 ID：<span class="fs-mono">{{ detail?.code || '-' }}</span>
          · 生成时间：{{ formatTime(detail?.createdAt) }}
          · 结构化内容来自后端 /compliance/reports/&lt;id&gt;
        </p>
      </div>
      <div class="fs-toolbar" style="margin-bottom: 0">
        <el-button :icon="Refresh" :loading="loading" @click="load">刷新</el-button>
        <el-button type="primary" :icon="Download" :loading="downloading" @click="onDownload">下载报告</el-button>
      </div>
    </div>

    <!-- 基础信息 -->
    <div class="fs-card">
      <div class="fs-card__header">
        <span class="fs-card__title">基础信息</span>
        <el-tag v-if="detail?.status" size="small" :type="statusOf(detail.status).type">
          {{ statusOf(detail.status).label }}
        </el-tag>
      </div>
      <div class="fs-card__body">
        <el-descriptions :column="3" border>
          <el-descriptions-item label="报告ID">
            <span class="fs-mono">{{ detail?.code || '-' }}</span>
          </el-descriptions-item>
          <el-descriptions-item label="报告类型">{{ detail?.typeName || detail?.type || '-' }}</el-descriptions-item>
          <el-descriptions-item label="时间范围">
            {{ periodText }}
          </el-descriptions-item>
          <el-descriptions-item label="生成时间">{{ formatTime(detail?.createdAt) }}</el-descriptions-item>
          <el-descriptions-item label="关联区块存证ID">
            <span class="fs-mono">{{ detail?.chainTxId || '-' }}</span>
          </el-descriptions-item>
          <el-descriptions-item label="生成人">{{ detail?.createdBy || basicInfo.createdBy || '-' }}</el-descriptions-item>
          <el-descriptions-item v-for="item in basicExtra" :key="item.key" :label="item.label">
            {{ item.value }}
          </el-descriptions-item>
        </el-descriptions>
      </div>
    </div>

    <!-- 关键指标（后端 metrics 分区，缺失时整块隐藏） -->
    <div v-if="metricCards.length" class="fs-card">
      <div class="fs-card__header">
        <span class="fs-card__title">关键指标</span>
        <span class="fs-muted">取自报告期内的交易、任务、授权与审计统计</span>
      </div>
      <div class="fs-card__body">
        <div class="fs-grid fs-grid--4">
          <StatCard
            v-for="item in metricCards"
            :key="item.label"
            :label="item.label"
            :value="item.value"
            :unit="item.unit"
            :icon="item.icon"
            :color="item.color"
            :sub="item.sub"
          />
        </div>
      </div>
    </div>

    <!-- 数据处理活动统计 -->
    <div class="fs-card">
      <div class="fs-card__header">
        <span class="fs-card__title">数据处理活动统计</span>
        <span class="fs-muted">共 {{ dataActivities.length }} 条活动记录</span>
      </div>
      <div class="fs-card__body">
        <el-table :data="dataActivities" border stripe size="small">
          <el-table-column
            v-for="column in activityColumns"
            :key="column.prop"
            :prop="column.prop"
            :label="column.label"
            :min-width="column.width || 130"
            show-overflow-tooltip
          >
            <template #default="{ row }">{{ cellText(row?.[column.prop]) }}</template>
          </el-table-column>
          <template #empty>
            <el-empty description="该报告未包含数据处理活动明细" :image-size="70" />
          </template>
        </el-table>
      </div>
    </div>

    <!-- 数据主体权利响应 -->
    <div class="fs-card">
      <div class="fs-card__header">
        <span class="fs-card__title">数据主体权利响应情况</span>
        <span class="fs-muted">共 {{ subjectRights.length }} 类权利请求</span>
      </div>
      <div class="fs-card__body">
        <el-table :data="subjectRights" border stripe size="small">
          <el-table-column
            v-for="column in subjectRightColumns"
            :key="column.prop"
            :prop="column.prop"
            :label="column.label"
            :min-width="column.width || 130"
            show-overflow-tooltip
          >
            <template #default="{ row }">{{ cellText(row?.[column.prop]) }}</template>
          </el-table-column>
          <template #empty>
            <el-empty description="该报告未包含数据主体权利响应记录" :image-size="70" />
          </template>
        </el-table>
      </div>
    </div>

    <!-- 合规评估结论 -->
    <div class="fs-card">
      <div class="fs-card__header">
        <span class="fs-card__title">合规评估结论</span>
      </div>
      <div class="fs-card__body">
        <div class="conclusion-block">
          <div class="conclusion-block__title">总体情况</div>
          <p class="conclusion-block__text">{{ conclusion.overall || '暂无总体结论内容' }}</p>
        </div>

        <div class="conclusion-block">
          <div class="conclusion-block__title">
            存在问题
            <el-tag v-if="conclusionIssues.length" type="danger" size="small" effect="plain">
              {{ conclusionIssues.length }} 项
            </el-tag>
          </div>
          <el-alert
            v-for="(item, index) in conclusionIssues"
            :key="`issue-${index}`"
            :title="issueTitle(item)"
            :description="issueDesc(item)"
            :type="issueAlertType(item)"
            show-icon
            :closable="false"
            style="margin-bottom: 8px"
          />
          <el-empty v-if="!conclusionIssues.length" description="未发现合规问题" :image-size="70" />
        </div>

        <div class="conclusion-block">
          <div class="conclusion-block__title">改进建议</div>
          <ol class="suggestion-list">
            <li v-for="(item, index) in conclusionSuggestions" :key="`sug-${index}`">{{ textOf(item) }}</li>
          </ol>
          <el-empty v-if="!conclusionSuggestions.length" description="暂无改进建议" :image-size="70" />
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
/**
 * 报告预览（对应设计文档图 22，Card 分区展示）
 *
 * 渲染策略：
 * - 后端 dataActivities / subjectRights 的字段可能随报告类型变化（不同法规关注点不同），
 *   因此优先使用后端返回的 columns 定义，其次由首行数据的键动态推断列，最后回退到常见字段，
 *   保证「字段缺失不报错、字段新增能展示」。
 * - conclusion 内部结构做多形态兼容（字符串数组 / 对象数组），避免出现 [object Object]。
 */
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { ArrowLeft, Download, Refresh } from '@element-plus/icons-vue'
import { complianceApi } from '@/api'
import { REPORT_STATUS, formatNumber, formatPercent, formatTime } from '@/utils/format'
import { downloadResponse } from '@/utils/download'
import StatCard from '@/components/StatCard.vue'

const route = useRoute()
const router = useRouter()

const loading = ref(false)
const downloading = ref(false)
const detail = ref(null)

/** 常见字段的中文表头与兜底列定义（键名对齐后端 compliance/report.py 的实际输出） */
const FIELD_LABELS = {
  dataType: '数据类型',
  type: '类型',
  name: '项目',
  targetRegion: '跨境目的地',
  destination: '跨境目的地',
  region: '地区',
  count: '笔数',
  txCount: '笔数',
  records: '记录数',
  amount: '金额(元)',
  cipher: '加密方式',
  encryption: '加密方式',
  level: '数据分级',
  compliance: '合规状态',
  partner: '接收方',
  purpose: '使用目的',
  right: '权利类型',
  requestType: '权利类型',
  requestCount: '请求数',
  received: '收到请求',
  responded: '已响应',
  responseRate: '响应率',
  avgHours: '平均响应时长(小时)',
  status: '状态',
  remark: '备注'
}

// 兜底列顺序与后端输出字段顺序一致（dataActivities / subjectRights）
const ACTIVITY_FALLBACK = ['dataType', 'destination', 'level', 'count', 'amount', 'cipher', 'compliance']
const SUBJECT_RIGHT_FALLBACK = ['requestType', 'received', 'responded', 'responseRate', 'status']

const dataActivities = computed(() => detail.value?.dataActivities ?? [])
const subjectRights = computed(() => detail.value?.subjectRights ?? [])
const conclusion = computed(() => detail.value?.conclusion ?? {})
const basicInfo = computed(() => detail.value?.basicInfo ?? {})

const conclusionIssues = computed(() => normalizeList(conclusion.value?.issues))
const conclusionSuggestions = computed(() => normalizeList(conclusion.value?.suggestions))

const periodText = computed(() => {
  const period = detail.value?.period
  const start = detail.value?.periodStart ?? period?.start ?? period?.[0]
  const end = detail.value?.periodEnd ?? period?.end ?? period?.[1]
  if (!start && !end) return '-'
  return `${formatTime(start, false)} ~ ${formatTime(end, false)}`
})

/** 基础信息中的额外字段（basicInfo 里除已展示项外的键值对） */
const basicExtra = computed(() => {
  const skip = ['createdBy', 'code', 'typeName', 'periodStart', 'periodEnd']
  return Object.entries(basicInfo.value || {})
    .filter(([key, value]) => !skip.includes(key) && value !== null && value !== undefined && value !== '')
    .slice(0, 6)
    .map(([key, value]) => ({ key, label: FIELD_LABELS[key] || key, value: textOf(value) }))
})

const activityColumns = computed(() =>
  buildColumns(dataActivities.value, detail.value?.activityColumns, ACTIVITY_FALLBACK)
)
const subjectRightColumns = computed(() =>
  buildColumns(subjectRights.value, detail.value?.subjectRightColumns, SUBJECT_RIGHT_FALLBACK)
)

/** 关键指标卡片：后端 metrics 为嵌套统计对象，逐项取数并做空值兜底 */
const metricCards = computed(() => {
  const metrics = detail.value?.metrics ?? {}
  const tx = metrics.transactions ?? {}
  const tasks = metrics.tasks ?? {}
  const audit = metrics.audit ?? {}
  const alerts = metrics.alerts ?? {}
  const transfer = metrics.transfer ?? {}
  const cards = []
  if (tx.count !== undefined) {
    cards.push({
      label: '跨境交易笔数',
      value: Number(tx.count || 0),
      unit: '笔',
      icon: 'Tickets',
      color: '#1f5fd8',
      sub: tx.amount !== undefined ? `金额合计 ${formatNumber(tx.amount, 2)} 元` : ''
    })
  }
  if (tasks.total !== undefined) {
    cards.push({
      label: '隐私计算任务',
      value: Number(tasks.total || 0),
      unit: '个',
      icon: 'Cpu',
      color: '#8b5cf6',
      sub: `已完成 ${Number(tasks.finished || 0)} 个`
    })
  }
  if (transfer.complianceRate !== undefined) {
    // 后端 complianceRate 为 0-1 小数，统一按百分比展示
    cards.push({
      label: '跨境传输合规通过率',
      value: formatPercent(transfer.complianceRate, 2),
      unit: '',
      icon: 'CircleCheck',
      color: '#14a37f',
      sub: `被阻断 ${Number(transfer.denied || 0)} 次`
    })
  }
  if (alerts.open !== undefined) {
    cards.push({
      label: '未闭环合规预警',
      value: Number(alerts.open || 0),
      unit: '条',
      icon: 'Warning',
      color: Number(alerts.high || 0) ? '#e5484d' : '#f5a623',
      sub: `高危 ${Number(alerts.high || 0)} 条`
    })
  }
  if (audit.total !== undefined) {
    cards.push({
      label: '审计日志',
      value: Number(audit.total || 0),
      unit: '条',
      icon: 'Files',
      color: '#0ea5e9',
      sub: ''
    })
  }
  return cards
})

function textOf(value) {
  if (value === null || value === undefined) return '-'
  if (typeof value === 'object') {
    // 兜底：对象类型字段序列化为可读文本，避免渲染成 [object Object]
    if (Array.isArray(value)) return value.map((item) => textOf(item)).join('、')
    return Object.entries(value)
      .map(([key, item]) => `${FIELD_LABELS[key] || key}：${textOf(item)}`)
      .join('；')
  }
  return String(value)
}

function cellText(value) {
  return textOf(value)
}

function normalizeList(value) {
  if (!value) return []
  if (Array.isArray(value)) return value.filter((item) => item !== null && item !== undefined)
  if (typeof value === 'string') return [value]
  return Object.values(value)
}

/** 依据后端列定义 / 首行数据键 / 兜底字段生成表格列 */
function buildColumns(rows, apiColumns, fallback) {
  if (Array.isArray(apiColumns) && apiColumns.length) {
    return apiColumns.map((item) => {
      if (typeof item === 'string') return { prop: item, label: FIELD_LABELS[item] || item }
      const prop = item.prop || item.key || item.field
      return { prop, label: item.label || FIELD_LABELS[prop] || prop, width: item.width }
    })
  }
  const first = rows?.[0]
  if (first && typeof first === 'object') {
    const keys = Object.keys(first)
    if (keys.length) {
      return keys.map((key) => ({ prop: key, label: FIELD_LABELS[key] || key }))
    }
  }
  return fallback.map((key) => ({ prop: key, label: FIELD_LABELS[key] || key }))
}

function statusOf(status) {
  return REPORT_STATUS[status] || { label: status || '未知', type: 'info' }
}

function issueTitle(item) {
  if (typeof item === 'string') return item
  return item?.title || item?.rule || item?.name || '合规问题'
}

function issueDesc(item) {
  if (typeof item === 'string') return ''
  const level = item?.level ? `风险等级：${item.level}。` : ''
  return `${level}${item?.detail || item?.message || item?.description || item?.rectification || ''}`
}

function issueAlertType(item) {
  const level = String((typeof item === 'object' ? item?.level : '') || '').toLowerCase()
  if (['high', 'p1', '严重', '高'].includes(level)) return 'error'
  if (['medium', 'p2', '中'].includes(level)) return 'warning'
  return 'info'
}

function goBack() {
  router.push('/compliance/reports')
}

async function onDownload() {
  const id = detail.value?.id || route.params.id
  if (!id) {
    ElMessage.warning('报告 ID 缺失，无法下载')
    return
  }
  downloading.value = true
  try {
    const response = await complianceApi.downloadReport(id)
    downloadResponse(response, `${detail.value?.code || 'compliance-report'}.md`)
    ElMessage.success('报告下载已开始')
  } catch (error) {
    // 请求拦截器已统一提示
  } finally {
    downloading.value = false
  }
}

async function load() {
  const id = route.params.id
  if (!id) {
    ElMessage.warning('缺少报告 ID，无法加载')
    return
  }
  loading.value = true
  try {
    detail.value = (await complianceApi.reportDetail(id)) ?? null
  } catch (error) {
    detail.value = null
  } finally {
    loading.value = false
  }
}

onMounted(load)
</script>

<style scoped>
.conclusion-block + .conclusion-block {
  margin-top: 18px;
}
.conclusion-block__title {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 14px;
  font-weight: 600;
  margin-bottom: 8px;
}
.conclusion-block__text {
  margin: 0;
  line-height: 1.8;
  color: var(--fs-text);
  background: #fbfcfe;
  border: 1px solid var(--fs-border);
  border-radius: 8px;
  padding: 12px 14px;
}
.suggestion-list {
  margin: 0;
  padding-left: 20px;
  line-height: 2;
}
</style>
