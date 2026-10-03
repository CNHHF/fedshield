<template>
  <div class="fs-page">
    <!-- 标题区 -->
    <div class="fs-page__header">
      <div>
        <h2 class="fs-page__title">支付通道池与路由权重</h2>
        <p class="fs-page__subtitle">
          浙江省服务外包大赛 A16 · 建设范围一：支付智能处理的「通道选择」能力 ——
          通道池即智能路由的候选集合，路由按「成本 / 成功率 / 时效 / 合规」四目标加权打分，
          受制裁与受限目的地做合规前置排除，失败重试与自动补偿保证资金链路最终闭环。
        </p>
      </div>
      <div class="fs-toolbar__right">
        <el-button :icon="Refresh" :loading="loading" @click="loadChannels">刷新</el-button>
        <el-button plain @click="goFlow">返回支付智能处理</el-button>
      </div>
    </div>

    <!-- 合规前置：受制裁 / 受限目的地 -->
    <el-alert
      v-if="restricted.length"
      type="warning"
      show-icon
      :closable="false"
      title="受制裁 / 受限目的地（合规前置，不允许直接清算）"
      class="fs-channels__alert"
    >
      <template #default>
        <div class="fs-channels__alert-body">
          <span>以下目的地命中制裁或高风险清单，智能路由会直接排除全部通道，订单转人工合规专项审批后再决定是否放行：</span>
          <div class="fs-channels__alert-tags">
            <el-tag v-for="code in restricted" :key="code" size="small" type="danger" effect="plain">
              {{ destLabel(code) }}
            </el-tag>
          </div>
        </div>
      </template>
    </el-alert>

    <el-alert
      v-else
      type="success"
      show-icon
      :closable="false"
      title="当前无受限目的地配置"
      description="受限目的地清单由后端 /api/ops/payment/channels 返回（restricted 字段）；为空表示未配置制裁清单。"
      class="fs-channels__alert"
    />

    <!-- 通道池 -->
    <div class="fs-card">
      <div class="fs-card__header">
        <span class="fs-card__title">通道池（智能路由候选集）</span>
        <div class="fs-channels__summary">
          <el-tag size="small" type="info" effect="plain">共 {{ formatNumber(channels.length) }} 条</el-tag>
          <el-tag size="small" type="success" effect="plain">可用 {{ formatNumber(availableCount) }} 条</el-tag>
          <el-tag size="small" type="warning" effect="plain">降级 {{ formatNumber(degradedCount) }} 条</el-tag>
          <el-tag size="small" type="danger" effect="plain">下线 {{ formatNumber(downCount) }} 条</el-tag>
        </div>
      </div>
      <div class="fs-card__body">
        <el-table v-loading="loading" :data="channels" border stripe style="width: 100%">
          <el-table-column label="通道名称" min-width="200" fixed>
            <template #default="{ row }">
              <div class="fs-channels__name">
                <strong>{{ row.name || '-' }}</strong>
                <span class="fs-mono fs-muted">{{ row.code || '-' }}</span>
              </div>
            </template>
          </el-table-column>

          <el-table-column label="所属地区" width="130">
            <template #default="{ row }">{{ destLabel(row.region) }}</template>
          </el-table-column>

          <el-table-column label="支持币种" min-width="170">
            <template #default="{ row }">
              <template v-if="(row.currencies || []).length">
                <el-tag
                  v-for="code in row.currencies || []"
                  :key="code"
                  size="small"
                  effect="plain"
                  class="fs-channels__tag"
                >
                  {{ code }}
                </el-tag>
              </template>
              <span v-else class="fs-muted">-</span>
            </template>
          </el-table-column>

          <el-table-column label="支持目的地" min-width="200">
            <template #default="{ row }">
              <template v-if="(row.destinations || []).length">
                <el-tag
                  v-for="code in row.destinations || []"
                  :key="code"
                  size="small"
                  effect="plain"
                  :type="isRestricted(code) ? 'danger' : 'info'"
                  class="fs-channels__tag"
                >
                  {{ destLabel(code) }}
                </el-tag>
              </template>
              <span v-else class="fs-muted">-</span>
            </template>
          </el-table-column>

          <el-table-column label="费率" width="90" align="right">
            <template #default="{ row }">{{ formatPercent(row.feeRate || 0, 2) }}</template>
          </el-table-column>

          <el-table-column label="历史成功率" width="170">
            <template #default="{ row }">
              <div class="fs-channels__rate">
                <el-progress
                  :percentage="ratePercent(row.successRate)"
                  :stroke-width="10"
                  :show-text="false"
                  :color="rateColor(row.successRate)"
                />
                <span class="fs-channels__rate-text">{{ formatPercent(row.successRate || 0, 1) }}</span>
              </div>
            </template>
          </el-table-column>

          <el-table-column label="平均时延" width="115" align="right">
            <template #default="{ row }">
              <span :class="latencyClass(row.avgLatencyMs)">{{ formatNumber(row.avgLatencyMs || 0) }} ms</span>
            </template>
          </el-table-column>

          <el-table-column label="单笔限额" width="140" align="right">
            <template #default="{ row }">{{ formatNumber(row.singleLimit || 0, 0) }} 元</template>
          </el-table-column>

          <el-table-column label="状态" width="95" align="center">
            <template #default="{ row }">
              <el-tag size="small" :type="channelStatusOf(row.status).type" effect="plain">
                {{ channelStatusOf(row.status).label }}
              </el-tag>
            </template>
          </el-table-column>

          <el-table-column label="合规说明" min-width="260" show-overflow-tooltip>
            <template #default="{ row }">
              <span>{{ row.complianceNote || '-' }}</span>
            </template>
          </el-table-column>

          <template #empty>
            <el-empty description="暂无通道配置" :image-size="80" />
          </template>
        </el-table>
      </div>
    </div>

    <!-- 路由评分公式 / 重试策略 / 补偿策略 -->
    <div class="fs-grid fs-grid--3 fs-channels__policy">
      <div class="fs-card">
        <div class="fs-card__header">
          <span class="fs-card__title">路由评分公式</span>
          <span class="fs-muted">{{ weightSource === 'server' ? '后端实时配置' : '引擎默认配置' }}</span>
        </div>
        <div class="fs-card__body">
          <div class="fs-channels__formula">{{ weightFormula }}</div>

          <div v-for="item in weightItems" :key="item.key" class="fs-channels__weight">
            <div class="fs-channels__weight-head">
              <strong>{{ item.label }}</strong>
              <span class="fs-muted">{{ item.desc }}</span>
              <span class="fs-channels__weight-value">{{ formatPercent(item.value, 0) }}</span>
            </div>
            <el-progress
              :percentage="item.percent"
              :stroke-width="8"
              :show-text="false"
              :color="item.color"
            />
          </div>

          <el-divider content-position="left">单项归一化口径</el-divider>
          <ul class="fs-channels__list">
            <li>成本得分 = 1 − 通道费率 ÷ 1.5%（费率越低得分越高）</li>
            <li>成功率得分 = 通道历史清算成功率（直接取值）</li>
            <li>时效得分 = 1 − 平均时延 ÷ 4000ms（时延越低得分越高）</li>
            <li>合规得分：基准 0.95（含 P1 敏感数据为 0.85）；通道降级 −0.15，高风险订单 +0.05</li>
          </ul>
          <el-alert
            type="info"
            show-icon
            :closable="false"
            title="合规前置优先于打分"
            description="通道下线、币种不支持、目的地不支持、超单笔限额、目的地受限这五种情况直接排除（得分为 0），不参与加权排序。"
          />
        </div>
      </div>

      <div class="fs-card">
        <div class="fs-card__header">
          <span class="fs-card__title">失败重试策略</span>
          <el-tag size="small" type="warning" effect="plain">最多重试 {{ retryMax }} 次</el-tag>
        </div>
        <div class="fs-card__body">
          <el-descriptions :column="1" border size="small">
            <el-descriptions-item label="最大重试次数">{{ retryMax }} 次（连同首次共 {{ retryMax + 1 }} 次尝试）</el-descriptions-item>
            <el-descriptions-item label="退避策略">
              指数退避 {{ backoffText }}（毫秒级，避免通道抖动期集中打爆）
            </el-descriptions-item>
            <el-descriptions-item label="通道切换">重试时按同一套路由打分重新选择通道，并排除已失败通道，实现自动切换备用通道</el-descriptions-item>
            <el-descriptions-item label="失败分类">
              通道网络超时 / 对方行拒付 / 通道限额触发 / 报文校验失败，分类记录到订单事件流
            </el-descriptions-item>
          </el-descriptions>

          <el-divider content-position="left">重试链路</el-divider>
          <el-timeline class="fs-channels__timeline">
            <el-timeline-item
              v-for="(item, index) in retryTimeline"
              :key="index"
              :type="item.type"
              size="normal"
            >
              <span class="fs-channels__timeline-text">{{ item.title }}</span>
            </el-timeline-item>
          </el-timeline>
        </div>
      </div>

      <div class="fs-card">
        <div class="fs-card__header">
          <span class="fs-card__title">自动补偿策略</span>
          <el-tag size="small" type="danger" effect="plain">重试耗尽后兜底</el-tag>
        </div>
        <div class="fs-card__body">
          <el-descriptions :column="1" border size="small">
            <el-descriptions-item label="触发条件">
              重试 {{ retryMax }} 次后仍未成功，或路由阶段无可用通道（币种 / 目的地 / 限额 / 合规全部不满足）
            </el-descriptions-item>
            <el-descriptions-item label="补偿方式一">改道重发：切换到其他可用通道重新发起清算，资金链路不中断</el-descriptions-item>
            <el-descriptions-item label="补偿方式二">原路退回：无法重新发起时生成补偿单，资金原路退回并通知商户</el-descriptions-item>
            <el-descriptions-item label="订单状态">
              置为「已自动补偿」（compensated），并标记 compensated = true
            </el-descriptions-item>
            <el-descriptions-item label="留痕要求">
              补偿原因、失败通道、尝试次数写入订单事件流，同步落审计日志与联盟链存证，可逐笔回溯
            </el-descriptions-item>
          </el-descriptions>

          <el-divider content-position="left">异常处置口径</el-divider>
          <ul class="fs-channels__list">
            <li>风控拦截（blocked）：风险评分超拦截阈值，直接拒绝并上链存证，不占用通道资源</li>
            <li>转人工审核（manual）：风险评分超人工复核阈值，转合规岗处理，人工放行或拒绝</li>
            <li>处理失败（failed）：路由阶段无可用通道，直接进入补偿流程</li>
            <li>重试后成功（retrying）：失败重试后成功清算，仍计入成功口径，但计入重试率</li>
          </ul>
          <el-button type="primary" plain class="fs-channels__go" @click="goFlow">
            前往支付智能处理页面演示故障重试与自动补偿
          </el-button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
/**
 * 支付通道池与路由权重说明（赛题 A16 · 建设范围一：通道选择能力）
 *
 * 数据来源：GET /api/ops/payment/channels
 *   { channels: [...], restricted: [...], retryPolicy: { maxRetry, backoffMs }, weights: { cost, success, latency, compliance } }
 *
 * 项目当前 api 封装（src/api/index.js）尚未包含 ops 接口，为避免改动既有文件，
 * 本页直接使用 axios 实例 request 调用，响应拦截器已统一解包 { code, message, data }。
 */
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { Refresh } from '@element-plus/icons-vue'
import request from '@/api/request'
import { formatNumber, formatPercent } from '@/utils/format'

const router = useRouter()

/** 通道健康状态字典（与 backend/models.py PaymentChannel.status 一致） */
const CHANNEL_STATUS = {
  available: { label: '可用', type: 'success' },
  degraded: { label: '降级', type: 'warning' },
  down: { label: '已下线', type: 'danger' }
}

/** 地区中文名映射（后端以地区编码返回） */
const REGION_LABEL = {
  GLOBAL: '全球 GLOBAL',
  EU: '欧盟 EU',
  US: '美国 US',
  SEA: '东南亚 SEA',
  ME: '中东 ME',
  AF: '非洲 AF',
  CN: '中国 CN',
  IR: '伊朗 IR',
  KP: '朝鲜 KP',
  SY: '叙利亚 SY',
  CU: '古巴 CU'
}

/** 权重维度元数据（权重值以后端返回为准，后端缺省时用引擎默认值） */
const WEIGHT_META = [
  { key: 'cost', label: '成本权重', color: '#1f5fd8', desc: '通道费率越低得分越高' },
  { key: 'success', label: '成功率权重', color: '#14a37f', desc: '历史清算成功率' },
  { key: 'latency', label: '时效权重', color: '#f5a623', desc: '平均到账时延越低越好' },
  { key: 'compliance', label: '合规权重', color: '#8b5cf6', desc: '牌照与数据合规能力' }
]

const DEFAULT_WEIGHTS = { cost: 0.4, success: 0.3, latency: 0.2, compliance: 0.1 }

const loading = ref(false)
const channels = ref([])
const restricted = ref([])
const retryPolicy = ref({ maxRetry: 2, backoffMs: [200, 600] })
const weights = ref({ ...DEFAULT_WEIGHTS })
const weightSource = ref('default')

const availableCount = computed(() => channels.value.filter((item) => item.status === 'available').length)
const degradedCount = computed(() => channels.value.filter((item) => item.status === 'degraded').length)
const downCount = computed(() => channels.value.filter((item) => item.status === 'down').length)

const retryMax = computed(() => {
  const value = Number(retryPolicy.value?.maxRetry ?? 2)
  return Number.isFinite(value) && value > 0 ? value : 2
})

const backoffText = computed(() => {
  const list = Array.isArray(retryPolicy.value?.backoffMs) ? retryPolicy.value.backoffMs : [200, 600]
  const text = list.filter((item) => Number(item) > 0).map((item) => `${formatNumber(item)}ms`)
  return text.length ? text.join(' → ') : '200ms → 600ms'
})

const weightItems = computed(() =>
  WEIGHT_META.map((item) => {
    const value = Number(weights.value?.[item.key] ?? DEFAULT_WEIGHTS[item.key]) || 0
    return { ...item, value, percent: Math.min(100, Math.max(0, Number((value * 100).toFixed(1)))) }
  })
)

/** 评分公式文案（权重全部取自接口，避免前后端口径漂移） */
const weightFormula = computed(() => {
  const part = weightItems.value
    .map((item) => `${formatPercent(item.value, 0)} × ${item.label.replace('权重', '得分')}`)
    .join(' + ')
  return `综合得分 = ${part}`
})

/** 重试链路时间线（由 maxRetry / backoffMs 动态推导，保证与后端策略一致） */
const retryTimeline = computed(() => {
  const max = retryMax.value
  const backoff = Array.isArray(retryPolicy.value?.backoffMs) ? retryPolicy.value.backoffMs : [200, 600]
  const list = [{ title: '第 1 次尝试：智能路由选中的主通道提交清算', type: 'primary' }]
  for (let index = 0; index < max; index += 1) {
    const wait = backoff[Math.min(index, backoff.length - 1)]
    list.push({ title: `第 ${index + 1} 次尝试失败：分类判定失败原因并写入事件流`, type: 'danger' })
    list.push({
      title: `${formatNumber(wait ?? 200)}ms 指数退避后切换备用通道（已排除失败通道）`,
      type: 'warning'
    })
    list.push({ title: `第 ${index + 2} 次尝试：备用通道提交清算`, type: 'primary' })
  }
  list.push({ title: `重试 ${max} 次仍失败 → 触发自动补偿（改道重发 / 原路退回）`, type: 'danger' })
  return list
})

function destLabel(code) {
  if (!code) return '-'
  return REGION_LABEL[code] || code
}

function isRestricted(code) {
  return (restricted.value || []).includes(code)
}

function channelStatusOf(status) {
  return CHANNEL_STATUS[status] || { label: status || '未知', type: 'info' }
}

function ratePercent(rate) {
  const value = Number(rate || 0) * 100
  return Math.min(100, Math.max(0, Number(value.toFixed(1))))
}

/** 成功率配色：< 95% 危险，< 98% 预警，其余正常 */
function rateColor(rate) {
  const value = Number(rate || 0)
  if (value < 0.95) return '#e5484d'
  if (value < 0.98) return '#f5a623'
  return '#14a37f'
}

/** 时延配色：≥ 3000ms 危险，≥ 2000ms 预警 */
function latencyClass(latency) {
  const value = Number(latency || 0)
  if (value >= 3000) return 'fs-channels__latency--danger'
  if (value >= 2000) return 'fs-channels__latency--warning'
  return ''
}

async function loadChannels() {
  loading.value = true
  try {
    const data = await request.get('/ops/payment/channels')
    channels.value = data?.channels ?? []
    restricted.value = data?.restricted ?? []
    if (data?.retryPolicy) retryPolicy.value = data.retryPolicy
    if (data?.weights) {
      weights.value = data.weights
      weightSource.value = 'server'
    }
  } catch (error) {
    // 请求层已弹出错误提示，这里保证页面回到可用（空）状态
    channels.value = []
    restricted.value = []
  } finally {
    loading.value = false
  }
}

function goFlow() {
  router.push('/ops/payment')
}

onMounted(() => {
  loadChannels()
})
</script>

<style scoped>
.fs-channels__alert {
  margin-bottom: 16px;
}
.fs-channels__alert-body {
  display: flex;
  flex-direction: column;
  gap: 6px;
  line-height: 1.6;
}
.fs-channels__alert-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}
.fs-channels__summary {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}
.fs-channels__name {
  display: flex;
  flex-direction: column;
  line-height: 1.4;
}
.fs-channels__tag {
  margin: 2px 4px 2px 0;
}
.fs-channels__rate {
  display: flex;
  align-items: center;
  gap: 8px;
}
.fs-channels__rate-text {
  font-size: 12px;
  color: var(--fs-text-secondary);
  font-variant-numeric: tabular-nums;
  white-space: nowrap;
}
.fs-channels__latency--warning {
  color: var(--fs-warning);
  font-weight: 600;
}
.fs-channels__latency--danger {
  color: var(--fs-danger);
  font-weight: 600;
}
.fs-channels__policy {
  margin-top: 16px;
}
/* 栅格内卡片由 grid 的 gap 控制间距，去掉 .fs-card + .fs-card 的纵向外边距 */
.fs-channels__policy > .fs-card + .fs-card {
  margin-top: 0;
}
.fs-channels__formula {
  padding: 10px 12px;
  margin-bottom: 14px;
  background: #f7f9fc;
  border: 1px dashed var(--fs-border);
  border-radius: 8px;
  font-size: 13px;
  line-height: 1.6;
  color: var(--fs-text);
}
.fs-channels__weight {
  margin-bottom: 12px;
}
.fs-channels__weight-head {
  display: flex;
  align-items: baseline;
  gap: 8px;
  margin-bottom: 4px;
  font-size: 13px;
}
.fs-channels__weight-head .fs-muted {
  flex: 1;
  min-width: 0;
}
.fs-channels__weight-value {
  font-weight: 600;
  color: var(--fs-text-secondary);
}
.fs-channels__list {
  margin: 0;
  padding-left: 18px;
  color: var(--fs-text-secondary);
  font-size: 12px;
  line-height: 1.9;
}
.fs-channels__timeline {
  padding-left: 2px;
  margin-bottom: 0;
}
.fs-channels__timeline-text {
  font-size: 13px;
}
.fs-channels__go {
  margin-top: 14px;
  width: 100%;
}
</style>
