
import { computed, onMounted, ref } from 'vue'
import { Refresh, SetUp } from '@element-plus/icons-vue'
import request from '@/api/request'
import StatCard from '@/components/StatCard.vue'
import { formatTime } from '@/utils/format'

/** 结论口径兜底（后端 review.DECISION_LABELS 不可用时使用，保证页面不空白） */
const FALLBACK_DECISIONS = {
  approve: '通过',
  reject: '拒绝',
  manual: '转人工/需补充材料'
}
/** 风险标签兜底（后端 review.RISK_TAGS 不可用时使用） */
const FALLBACK_RISK_TAGS = [
  { level: 'high', tag: '高风险', color: '#e5484d', action: '拒绝 / 转人工复核' },
  { level: 'medium', tag: '中风险', color: '#f5a623', action: '二次验证 / 抽检' },
  { level: 'low', tag: '低风险', color: '#14a37f', action: '自动通过' }
]
/** 规则权重中文映射（规则字段 → 规则名 / 说明） */
const RULE_LABELS = [
  { key: 'sanctionHit', label: '命中制裁清单', desc: '命中 OFAC / 联合国制裁清单，属强证据（高权重）' },
  { key: 'highRiskRegion', label: '高风险地区', desc: '交易目的地属高风险国家或地区' },
  { key: 'amountAnomaly', label: '金额异常', desc: '单笔金额显著高于同层级商户均值' },
  { key: 'velocity', label: '拆分交易', desc: '1 小时内多笔交易，存在化整为零特征' },
  { key: 'identityMismatch', label: '身份不一致', desc: 'KYC 身份信息与结算账户不一致' },
  { key: 'newMerchant', label: '新商户', desc: '商户入驻时间过短，历史数据不足' },
  { key: 'nightTrade', label: '夜间交易', desc: '夜间交易占比超过 50%，行为异常' }
]
/** 结论口径的业务说明（补充后端字段之外的处置含义） */
const DECISION_DESC = {
  approve: '风险可控，资金可直接放行；对应低风险标签与「自动通过」处置口径',
  reject: '存在实质风险，拒绝并上报；对应高风险标签与「拒绝 / 转人工复核」处置口径',
  manual: '证据不足以直接判定，转人工复核或要求补充材料；计入总体协同率而非分歧'
}
const DECISION_TAG = { approve: 'success', reject: 'danger', manual: 'warning' }
/** 四段闭环静态说明表（AI 初审 → 人工复核 → 差异回流 → 持续优化） */
const LOOP_STAGES = [
  {
    stage: '① AI 初审',
    tagType: 'primary',
    owner: '风控策略岗',
    action: '按统一标准计算 AI 评分、置信度与风险等级，输出通过 / 拒绝 / 转人工结论并附命中证据',
    output: 'AI 结论、AI 评分、置信度、风险标签、命中证据（aiReasons）、初审耗时',
    evidence: '审核记录中的 AI 侧字段'
  },
  {
    stage: '② 人工复核',
    tagType: 'success',
    owner: '人工审核岗',
    action: '按同一套结论口径独立复核（低置信度与高风险必转人工），填写复核意见',
    output: '人工结论、复核人、人工意见、复核耗时',
    evidence: '审核记录中的人工侧字段与对照抽屉'
  },
  {
    stage: '③ 差异回流',
    tagType: 'warning',
    owner: '风控策略岗',
    action: '比对 AI 与人工结论，标记漏放 / 误拦 / 均转人工，量化漏放率与误拦率并回溯分歧样本',
    output: '一致率、总体协同率、Kappa、混淆矩阵、按风险等级与置信度区间一致率、分歧样本清单',
    evidence: '一致性评估区与审核记录筛选'
  },
  {
    stage: '④ 持续优化',
    tagType: 'danger',
    owner: '运营管理岗',
    action: '在候选阈值网格上用同一批样本复盘，按「一致性 / 自动化率 / 漏放率」目标选优并应用新策略',
    output: '优化建议要点、优化前后指标对比、候选策略表、优化记录（含应用人与时间）',
    evidence: '差异回流与持续优化卡 + 优化记录表'
  }
]

const loading = ref(false)
const policy = ref({})
const standards = ref({})
const updatedAt = ref('')

/* ---------------- 计算属性（全部空值兜底） ---------------- */

const decisionRows = computed(() => {
  const labels = standards.value.decisionLabels || {}
  const keys = Object.keys(labels).length ? Object.keys(labels) : Object.keys(FALLBACK_DECISIONS)
  return keys.map((key) => ({
    code: key,
    label: labels[key] || FALLBACK_DECISIONS[key] || key,
    tagType: DECISION_TAG[key] || 'info',
    desc: DECISION_DESC[key] || '-'
  }))
})

const riskTagRows = computed(() => {
  const list = standards.value.riskTags
  const rows = Array.isArray(list) && list.length ? list : FALLBACK_RISK_TAGS
  return rows.map((item) => ({
    level: item?.level || '-',
    tag: item?.tag || '-',
    color: item?.color || '#1f5fd8',
    action: item?.action || '-'
  }))
})

const weightRows = computed(() => {
  const weights = policy.value.ruleWeights || {}
  const keys = Object.keys(weights)
  const ordered = RULE_LABELS.filter((item) => keys.includes(item.key))
  const extra = keys
    .filter((key) => !RULE_LABELS.some((item) => item.key === key))
    .map((key) => ({ key, label: key, desc: '自定义规则权重' }))
  return [...ordered, ...extra].map((item) => ({
    key: item.key,
    label: item.label,
    desc: item.desc,
    weight: weights[item.key] === undefined ? '-' : weights[item.key]
  }))
})

/* ---------------- 数据加载 ---------------- */

async function load() {
  loading.value = true
  try {
    const data = await request.get('/ops/review/policy')
    const payload = data || {}
    policy.value = payload.policy || {}
    standards.value = payload.standards || {}
    updatedAt.value = new Date().toISOString()
  } catch (error) {
    policy.value = {}
    standards.value = {}
  } finally {
    loading.value = false
  }
}

onMounted(load)
