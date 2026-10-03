<template>
  <div class="fs-page fs-standard">
    <!-- 页面头部 -->
    <div class="fs-page__header">
      <div>
        <h2 class="fs-page__title">
          <el-icon class="fs-standard__title-icon"><SetUp /></el-icon>
          统一审核标准与风险标签
        </h2>
        <p class="fs-page__subtitle">
          AI 初审与人工复核使用完全相同的审核结论口径、风险标签体系与处置口径 ·
          标准由「差异回流 → 持续优化」闭环动态调优（赛题 A16 建设范围四）
        </p>
      </div>
      <div class="fs-toolbar__right">
        <el-tag type="info" effect="plain" size="large">
          更新时间：{{ formatTime(updatedAt) }}
        </el-tag>
        <el-button :icon="Refresh" :loading="loading" @click="load">刷新</el-button>
      </div>
    </div>

    <!-- 统一审核标准概览 -->
    <div class="fs-grid fs-grid--4">
      <StatCard
        label="通过阈值"
        :value="Number(policy.approveThreshold ?? 0)"
        :precision="2"
        icon="CircleCheck"
        color="#14a37f"
        sub="AI 评分低于该值 → 通过"
      />
      <StatCard
        label="拒绝阈值"
        :value="Number(policy.rejectThreshold ?? 0)"
        :precision="2"
        icon="CircleClose"
        color="#e5484d"
        sub="AI 评分高于该值 → 拒绝"
      />
      <StatCard
        label="置信度门槛"
        :value="Number(policy.confidenceFloor ?? 0)"
        :precision="2"
        icon="Odometer"
        color="#f5a623"
        sub="置信度低于该值 → 强制转人工"
      />
      <StatCard
        label="规则权重项"
        :value="weightRows.length"
        unit="项"
        icon="SetUp"
        color="#8b5cf6"
        sub="评分公式中的可调权重因子"
      />
    </div>

    <el-alert
      type="info"
      :closable="false"
      show-icon
      title="统一口径说明"
      class="fs-standard__note"
    >
      <div class="fs-standard__note-body">
        审核结论统一为三分类（通过 / 拒绝 / 转人工），AI 与人工的取值完全一致，因此可以直接比对并在混淆矩阵中量化一致性；
        风险标签体系统一为高 / 中 / 低三级，并绑定建议处置动作，保证 AI 初审与人工复核的处置口径一致。
      </div>
    </el-alert>

    <!-- 审核结论口径 + 风险标签体系 -->
    <div class="fs-grid fs-grid--2">
      <div class="fs-card">
        <div class="fs-card__header">
          <span class="fs-card__title">审核结论口径（三分类）</span>
          <span class="fs-muted">decisionLabels · AI 与人工共用</span>
        </div>
        <div class="fs-card__body">
          <el-table :data="decisionRows" border stripe size="small">
            <el-table-column prop="code" label="结论编码" width="120">
              <template #default="{ row }">
                <span class="fs-mono">{{ row.code }}</span>
              </template>
            </el-table-column>
            <el-table-column label="结论标签" width="140">
              <template #default="{ row }">
                <el-tag size="small" :type="row.tagType">{{ row.label }}</el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="desc" label="口径说明" min-width="200" show-overflow-tooltip />
            <template #empty>暂无审核结论口径</template>
          </el-table>
          <div class="fs-muted fs-standard__hint">
            一致性评估以该口径为准：AI 自主决策（通过 / 拒绝）与人工结论相同的样本计入一致率；
            AI 转人工属于协同处置，计入总体协同率。
          </div>
        </div>
      </div>

      <div class="fs-card">
        <div class="fs-card__header">
          <span class="fs-card__title">风险标签体系</span>
          <span class="fs-muted">riskTags · 等级 / 标签 / 建议处置</span>
        </div>
        <div class="fs-card__body">
          <div class="fs-standard__tags">
            <div
              v-for="item in riskTagRows"
              :key="item.level"
              class="fs-standard__tag-card"
              :style="{ borderColor: item.color, background: `${item.color}12` }"
            >
              <div class="fs-standard__tag-head">
                <i class="fs-standard__tag-dot" :style="{ background: item.color }"></i>
                <strong :style="{ color: item.color }">{{ item.tag }}</strong>
                <span class="fs-mono fs-muted">{{ item.level }}</span>
              </div>
              <div class="fs-standard__tag-action">
                建议处置：<b>{{ item.action }}</b>
              </div>
            </div>
          </div>
          <el-table :data="riskTagRows" border stripe size="small" class="fs-standard__tag-table">
            <el-table-column prop="level" label="等级编码" width="110">
              <template #default="{ row }">
                <span class="fs-mono">{{ row.level }}</span>
              </template>
            </el-table-column>
            <el-table-column prop="tag" label="风险标签" width="110" />
            <el-table-column prop="action" label="建议处置" min-width="180" show-overflow-tooltip />
            <template #empty>暂无风险标签</template>
          </el-table>
        </div>
      </div>
    </div>

    <!-- 规则权重与评分公式 -->
    <div class="fs-grid fs-grid--2">
      <div class="fs-card">
        <div class="fs-card__header">
          <span class="fs-card__title">规则权重表</span>
          <span class="fs-muted">ruleWeights · 差异回流会调整权重</span>
        </div>
        <div class="fs-card__body">
          <el-table :data="weightRows" border stripe size="small">
            <el-table-column prop="key" label="规则字段" width="150">
              <template #default="{ row }">
                <span class="fs-mono">{{ row.key }}</span>
              </template>
            </el-table-column>
            <el-table-column prop="label" label="规则名" width="120" />
            <el-table-column label="权重" width="90" align="center">
              <template #default="{ row }">
                <b>{{ row.weight }}</b>
              </template>
            </el-table-column>
            <el-table-column prop="desc" label="规则说明" min-width="200" show-overflow-tooltip />
            <template #empty>暂无规则权重</template>
          </el-table>
          <div class="fs-muted fs-standard__hint">
            权重越高代表该规则对 AI 评分的影响越大；差异回流会基于分歧样本调整权重，
            当前权重来自最近一次审核策略（应用优化策略后实时同步）。
          </div>
        </div>
      </div>

      <div class="fs-card">
        <div class="fs-card__header">
          <span class="fs-card__title">AI 评分公式与三分类口径</span>
          <span class="fs-muted">统一标准 · 可解释 · 可复盘</span>
        </div>
        <div class="fs-card__body">
          <div class="fs-standard__formula">
            <div class="fs-standard__formula-main">score = 基线 + Σ (规则命中 × 规则权重)</div>
            <div class="fs-standard__formula-sub">
              基线 = 0.06 ± 0.06 噪声（体现模型固有不确定性）；评分最终截断到 [0.01, 0.99]；
              未命中任何规则时置信度按 0.9 处理（低风险结论更确定）。
            </div>
          </div>

          <el-steps :active="3" align-center class="fs-standard__steps">
            <el-step title="通过" :description="`score ≤ ${policy.approveThreshold ?? '-'}`" status="success" />
            <el-step title="转人工" :description="介于两阈值之间" status="warning" />
            <el-step title="拒绝" :description="`score ≥ ${policy.rejectThreshold ?? '-'}`" status="error" />
          </el-steps>

          <el-descriptions :column="1" border size="small">
            <el-descriptions-item label="置信度定义">
              置信度 = 距最近决策边界的距离映射（0.55 + 距离 × 1.6，上限 0.99）；
              命中制裁清单等强证据时不低于 0.96。
            </el-descriptions-item>
            <el-descriptions-item label="强制转人工规则">
              置信度低于 <b>{{ policy.confidenceFloor ?? '-' }}</b> 的样本，即使 AI 已给出通过 / 拒绝结论，
              也一律改判为转人工（协同优先，避免低置信度样本的自主决策风险）。
            </el-descriptions-item>
            <el-descriptions-item label="风险等级映射">
              score ≥ 0.7 → 高风险（拒绝 / 转人工复核）；0.4 ≤ score &lt; 0.7 → 中风险（二次验证 / 抽检）；
              score &lt; 0.4 → 低风险（自动通过）。
            </el-descriptions-item>
          </el-descriptions>
        </div>
      </div>
    </div>

    <!-- 四段闭环 -->
    <div class="fs-card">
      <div class="fs-card__header">
        <span class="fs-card__title">协同审核闭环：AI 初审 → 人工复核 → 差异回流 → 持续优化</span>
        <span class="fs-muted">各环节产出物与责任角色</span>
      </div>
      <div class="fs-card__body">
        <el-table :data="LOOP_STAGES" border stripe size="small">
          <el-table-column label="环节" width="150">
            <template #default="{ row }">
              <el-tag size="small" :type="row.tagType" effect="plain">{{ row.stage }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="owner" label="责任角色" width="140" />
          <el-table-column prop="action" label="关键动作" min-width="260" show-overflow-tooltip />
          <el-table-column prop="output" label="产出物" min-width="300" show-overflow-tooltip />
          <el-table-column prop="evidence" label="平台落点" min-width="220" show-overflow-tooltip />
        </el-table>
        <div class="fs-muted fs-standard__hint">
          四段闭环的每一段都在平台中留有可追溯证据：审核记录（含 AI 评分、命中证据、人工意见与特征向量）、
          一致性评估指标、策略优化记录与审计存证，可直接用于监管核查与赛题演示答辩。
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
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
</script>

<style scoped>
.fs-standard__title-icon {
  vertical-align: -2px;
  margin-right: 6px;
  color: #8b5cf6;
}
.fs-standard__note {
  margin: 16px 0;
}
.fs-standard__note-body {
  line-height: 1.7;
  font-size: 13px;
}
.fs-standard__hint {
  margin-top: 10px;
  line-height: 1.7;
}
.fs-standard__tags {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 12px;
}
@media (max-width: 1280px) {
  .fs-standard__tags {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}
@media (max-width: 768px) {
  .fs-standard__tags {
    grid-template-columns: minmax(0, 1fr);
  }
}
.fs-standard__tag-card {
  border: 1px solid var(--fs-border);
  border-radius: 10px;
  padding: 12px 14px;
}
.fs-standard__tag-head {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 14px;
}
.fs-standard__tag-dot {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  display: inline-block;
}
.fs-standard__tag-action {
  margin-top: 8px;
  font-size: 12px;
  line-height: 1.7;
  color: var(--fs-text-secondary);
}
.fs-standard__tag-table {
  margin-top: 14px;
}
.fs-standard__formula {
  padding: 14px 16px;
  border-radius: 10px;
  border: 1px dashed var(--fs-primary);
  background: var(--fs-primary-light);
}
.fs-standard__formula-main {
  font-family: 'JetBrains Mono', 'Cascadia Mono', Consolas, monospace;
  font-size: 15px;
  font-weight: 600;
  color: var(--fs-primary);
}
.fs-standard__formula-sub {
  margin-top: 8px;
  font-size: 12px;
  line-height: 1.7;
  color: var(--fs-text-secondary);
}
.fs-standard__steps {
  margin: 18px 0;
}
</style>
