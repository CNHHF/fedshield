<template>
  <div class="fs-page">
    <!-- 页面头部 -->
    <div class="fs-page__header">
      <div>
        <h2 class="fs-page__title">审计记录与联盟链存证</h2>
        <p class="fs-page__subtitle">
          汇聚全平台操作审计日志，并将关键操作摘要写入联盟链存证，支持链完整性校验与监管机构专属查询节点接入。
        </p>
      </div>
      <div class="fs-page__actions">
        <el-button type="primary" :loading="verifying" @click="handleVerifyChain">
          <el-icon><Lock /></el-icon>
          校验链完整性
        </el-button>
      </div>
    </div>

    <!-- 存证统计 -->
    <div class="fs-grid fs-grid--4">
      <StatCard label="存证交易总量" :value="stats.txTotal ?? 0" unit="笔" icon="Files" color="#1f5fd8" sub="累计写入联盟链的操作摘要" />
      <StatCard label="当前区块高度" :value="stats.blockHeight ?? 0" unit="块" icon="Box" color="#14a37f" sub="联盟链最新区块高度" />
      <StatCard label="存证吞吐 TPS" :value="stats.tps ?? 0" unit="笔/秒" icon="Odometer" color="#f5a623" :precision="1" sub="近一分钟平均写入速率" />
      <StatCard label="审计留存年限" :value="stats.retentionYears ?? 0" unit="年" icon="Clock" color="#8b5cf6" sub="满足跨境监管审计留存要求" />
    </div>

    <!-- 链完整性校验结果 -->
    <div v-if="verifyResult" class="fs-card">
      <div class="fs-card__body">
        <el-alert
          :type="verifyResult.valid ? 'success' : 'error'"
          :closable="false"
          show-icon
          :title="verifyResult.valid ? '链完整性校验通过：哈希链连续，未检测到篡改' : '链完整性校验失败：检测到哈希链断裂'"
        >
          <div class="audit-verify">
            <span>校验结论：<b>{{ verifyResult.valid ? '完整（valid = true）' : '异常（valid = false）' }}</b></span>
            <span>校验区块数：<b>{{ verifyResult.blocks ?? 0 }}</b></span>
            <span>断裂位置：<b>{{ verifyResult.brokenAt || '无' }}</b></span>
            <span>校验时间：<b>{{ formatTime(verifyResult.checkedAt) }}</b></span>
          </div>
        </el-alert>
      </div>
    </div>

    <!-- 审计日志检索 -->
    <div class="fs-card">
      <div class="fs-card__header">
        <div class="fs-card__title">审计日志检索</div>
        <span class="fs-muted">共 {{ logs.total }} 条记录</span>
      </div>
      <div class="fs-card__body">
        <div class="fs-toolbar">
          <el-input
            v-model="logQuery.actor"
            placeholder="操作人"
            clearable
            style="width: 170px"
            @keyup.enter="handleLogSearch"
          >
            <template #prefix>
              <el-icon><User /></el-icon>
            </template>
          </el-input>
          <el-select v-model="logQuery.action" placeholder="操作类型" clearable style="width: 160px">
            <el-option v-for="item in ACTIONS" :key="item.value" :label="item.label" :value="item.value" />
          </el-select>
          <el-date-picker
            v-model="logQuery.range"
            type="datetimerange"
            unlink-panels
            range-separator="至"
            start-placeholder="开始时间"
            end-placeholder="结束时间"
            value-format="YYYY-MM-DD HH:mm:ss"
            style="width: 360px"
          />
          <el-select v-model="logQuery.result" placeholder="执行结果" clearable style="width: 140px">
            <el-option label="成功" value="success" />
            <el-option label="失败" value="failed" />
            <el-option label="已阻断" value="blocked" />
          </el-select>
          <el-button type="primary" :loading="loading" @click="handleLogSearch">
            <el-icon><Search /></el-icon>
            检索
          </el-button>
          <el-button @click="handleLogReset">重置</el-button>
        </div>

        <el-table v-loading="loading" :data="logs.list" border stripe size="small">
          <el-table-column label="时间" width="164">
            <template #default="{ row }">{{ formatTime(row?.ts) }}</template>
          </el-table-column>
          <el-table-column prop="actor" label="操作人" width="140" show-overflow-tooltip />
          <el-table-column prop="role" label="角色" width="120" show-overflow-tooltip />
          <el-table-column label="操作" min-width="150" show-overflow-tooltip>
            <template #default="{ row }">{{ actionLabel(row?.action) }}</template>
          </el-table-column>
          <el-table-column prop="target" label="对象" min-width="160" show-overflow-tooltip />
          <el-table-column label="结果" width="92">
            <template #default="{ row }">
              <el-tag size="small" :type="resultType(row?.result)">{{ resultLabel(row?.result) }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column label="风险分" width="96" align="center">
            <template #default="{ row }">
              <span :class="{ 'audit-risk--high': Number(row?.riskScore || 0) >= 70 }">
                {{ formatNumber(row?.riskScore ?? 0) }}
              </span>
            </template>
          </el-table-column>
          <el-table-column label="防篡改签名" width="150">
            <template #default="{ row }">
              <span class="fs-mono">{{ shortSignature(row?.signature) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="区块链交易ID" min-width="180" show-overflow-tooltip>
            <template #default="{ row }">
              <span class="fs-mono">{{ row?.chainTxId || '-' }}</span>
            </template>
          </el-table-column>
          <template #empty>暂无审计日志</template>
        </el-table>

        <div class="audit-pagination">
          <el-pagination
            background
            layout="total, sizes, prev, pager, next, jumper"
            :total="logs.total"
            :current-page="logs.page"
            :page-size="logs.size"
            :page-sizes="[10, 20, 50, 100]"
            @current-change="handleLogPageChange"
            @size-change="handleLogSizeChange"
          />
        </div>
      </div>
    </div>

    <!-- 联盟链存证 -->
    <div class="fs-card">
      <div class="fs-card__header">
        <div class="fs-card__title">联盟链存证区块</div>
        <div class="fs-page__actions">
          <span class="fs-muted">共 {{ chain.total }} 个区块 · 点击行可展开完整载荷</span>
          <el-button :loading="chainLoading" @click="loadChain">
            <el-icon><Refresh /></el-icon>
            刷新区块
          </el-button>
        </div>
      </div>
      <div class="fs-card__body">
        <el-table
          v-loading="chainLoading"
          :data="chain.list"
          border
          stripe
          size="small"
          row-key="txId"
          @expand-change="handleExpandChange"
        >
          <el-table-column type="expand">
            <template #default="{ row }">
              <div class="audit-payload">
                <div class="audit-payload__title">
                  <span>区块完整载荷（payload）</span>
                  <el-button size="small" text type="primary" @click="handleCopyPayload(row)">
                    <el-icon><CopyDocument /></el-icon>
                    复制 JSON
                  </el-button>
                </div>
                <pre class="fs-mono audit-payload__code">{{ payloadText(row) }}</pre>
                <div class="fs-muted">
                  存证节点：{{ row?.node || '-' }} · 交易ID：{{ row?.txId || '-' }}
                </div>
              </div>
            </template>
          </el-table-column>
          <el-table-column label="区块高度" width="100" align="center">
            <template #default="{ row }">
              <el-tag size="small" type="primary" effect="plain">#{{ row?.height ?? '-' }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column label="交易ID" min-width="190" show-overflow-tooltip>
            <template #default="{ row }">
              <span class="fs-mono">{{ row?.txId || '-' }}</span>
            </template>
          </el-table-column>
          <el-table-column label="时间" width="164">
            <template #default="{ row }">{{ formatTime(row?.ts) }}</template>
          </el-table-column>
          <el-table-column label="载荷摘要" min-width="170" show-overflow-tooltip>
            <template #default="{ row }">
              <span class="fs-mono">{{ row?.payloadDigest || '-' }}</span>
            </template>
          </el-table-column>
          <el-table-column label="前序哈希" min-width="180" show-overflow-tooltip>
            <template #default="{ row }">
              <span class="fs-mono">{{ row?.prevHash || '-' }}</span>
            </template>
          </el-table-column>
          <el-table-column label="当前哈希" min-width="180" show-overflow-tooltip>
            <template #default="{ row }">
              <span class="fs-mono audit-hash--current">{{ row?.hash || '-' }}</span>
            </template>
          </el-table-column>
          <el-table-column prop="node" label="存证节点" width="160" show-overflow-tooltip />
          <template #empty>暂无存证区块</template>
        </el-table>

        <div class="audit-pagination">
          <el-pagination
            background
            layout="total, sizes, prev, pager, next, jumper"
            :total="chain.total"
            :current-page="chain.page"
            :page-size="chain.size"
            :page-sizes="[10, 20, 50]"
            @current-change="handleChainPageChange"
            @size-change="handleChainSizeChange"
          />
        </div>
      </div>
    </div>

    <!-- 监管机构专属查询节点 -->
    <div class="fs-card">
      <div class="fs-card__header">
        <div class="fs-card__title">监管机构专属查询节点</div>
        <span class="fs-muted">按权限开放只读存证查询，满足跨境监管审计要求</span>
      </div>
      <div class="fs-card__body">
        <div v-if="regulatorNodes.length" class="audit-regulators">
          <div v-for="(item, index) in regulatorNodes" :key="index" class="audit-regulator">
            <el-icon class="audit-regulator__icon"><OfficeBuilding /></el-icon>
            <div class="audit-regulator__body">
              <div class="audit-regulator__name">{{ nodeName(item) }}</div>
              <div class="fs-muted">
                {{ nodeRegion(item) }}
                <span v-if="nodeStatus(item)"> · {{ nodeStatus(item) }}</span>
              </div>
            </div>
            <el-tag size="small" type="success" effect="plain">只读查询</el-tag>
          </div>
        </div>
        <el-empty v-else description="暂无监管机构查询节点" :image-size="70" />
      </div>
    </div>
  </div>
</template>

<script setup>
import { onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { auditApi } from '@/api'
import StatCard from '@/components/StatCard.vue'
import { formatNumber, formatTime } from '@/utils/format'

/* ---------------- 字典 ---------------- */
const ACTIONS = [
  { value: 'login', label: '登录认证' },
  { value: 'query', label: '数据查询' },
  { value: 'export', label: '数据导出' },
  { value: 'compute', label: '发起计算' },
  { value: 'grant', label: '授权变更' },
  { value: 'rule', label: '规则调整' },
  { value: 'verify', label: '链上校验' }
]

/* ---------------- 状态 ---------------- */
const loading = ref(false)
const chainLoading = ref(false)
const verifying = ref(false)

const stats = reactive({ txTotal: 0, blockHeight: 0, tps: 0, retentionYears: 0, regulatorNodes: [] })

const logQuery = reactive({ actor: '', action: '', range: [], result: '' })
const logs = reactive({ list: [], total: 0, page: 1, size: 10 })

const chain = reactive({ list: [], total: 0, page: 1, size: 10 })

const verifyResult = ref(null)
/* 行展开时缓存的完整载荷：key 为交易ID */
const payloadCache = reactive({})

const regulatorNodes = ref([])

/* ---------------- 展示辅助 ---------------- */
function actionLabel(action) {
  if (!action) return '-'
  const hit = ACTIONS.find((item) => item.value === action)
  return hit ? hit.label : action
}

function resultType(result) {
  const text = String(result ?? '').toLowerCase()
  if (text === 'success' || text === 'ok' || text === '通过') return 'success'
  if (text === 'blocked' || text === '阻断') return 'warning'
  if (!text) return 'info'
  return 'danger'
}

function resultLabel(result) {
  if (!result) return '-'
  const text = String(result).toLowerCase()
  if (text === 'success' || text === 'ok') return '成功'
  if (text === 'blocked') return '已阻断'
  if (text === 'failed') return '失败'
  return String(result)
}

/** 防篡改签名仅展示前 12 位 */
function shortSignature(signature) {
  if (!signature) return '-'
  const text = String(signature)
  return text.length > 12 ? `${text.slice(0, 12)}…` : text
}

function nodeName(item) {
  if (typeof item === 'string') return item
  return item?.name || item?.code || '-'
}

function nodeRegion(item) {
  if (typeof item === 'string') return '监管查询节点'
  return item?.region || item?.org || '监管查询节点'
}

function nodeStatus(item) {
  if (typeof item === 'string') return ''
  return item?.status || ''
}

function payloadText(row) {
  const payload = payloadCache[row?.txId] ?? row?.payload ?? null
  if (payload === null || payload === undefined) return '载荷未返回，点击此行将按交易ID查询完整存证内容'
  if (typeof payload === 'string') {
    try {
      return JSON.stringify(JSON.parse(payload), null, 2)
    } catch (error) {
      return payload
    }
  }
  try {
    return JSON.stringify(payload, null, 2)
  } catch (error) {
    return String(payload)
  }
}

/* ---------------- 数据加载 ---------------- */
/** 存证统计与监管节点 */
async function loadStats() {
  try {
    const data = await auditApi.stats()
    stats.txTotal = data?.txTotal ?? 0
    stats.blockHeight = data?.blockHeight ?? 0
    stats.tps = data?.tps ?? 0
    stats.retentionYears = data?.retentionYears ?? 0
    regulatorNodes.value = data?.regulatorNodes ?? []
  } catch (error) {
    regulatorNodes.value = []
  }
}

function buildLogParams() {
  const params = { page: logs.page, size: logs.size }
  if (logQuery.actor) params.actor = logQuery.actor.trim()
  if (logQuery.action) params.action = logQuery.action
  if (logQuery.result) params.result = logQuery.result
  if (Array.isArray(logQuery.range) && logQuery.range.length === 2) {
    params.start = logQuery.range[0]
    params.end = logQuery.range[1]
  }
  return params
}

/** 审计日志检索 */
async function loadLogs() {
  loading.value = true
  try {
    const data = await auditApi.logs(buildLogParams())
    logs.list = data?.list ?? []
    logs.total = data?.total ?? 0
  } finally {
    loading.value = false
  }
}

/** 联盟链区块列表 */
async function loadChain() {
  chainLoading.value = true
  try {
    const data = await auditApi.chain({ page: chain.page, size: chain.size })
    chain.list = data?.list ?? []
    chain.total = data?.total ?? 0
  } finally {
    chainLoading.value = false
  }
}

/** 初始化加载：统计 + 日志 + 区块 */
async function load() {
  loading.value = true
  try {
    await Promise.all([loadStats(), loadLogs(), loadChain()])
  } finally {
    loading.value = false
  }
}

function handleLogSearch() {
  logs.page = 1
  loadLogs()
}

function handleLogReset() {
  logQuery.actor = ''
  logQuery.action = ''
  logQuery.range = []
  logQuery.result = ''
  logs.page = 1
  loadLogs()
}

function handleLogPageChange(page) {
  logs.page = page
  loadLogs()
}

function handleLogSizeChange(size) {
  logs.size = size
  logs.page = 1
  loadLogs()
}

function handleChainPageChange(page) {
  chain.page = page
  loadChain()
}

function handleChainSizeChange(size) {
  chain.size = size
  chain.page = 1
  loadChain()
}

/** 展开区块行时按交易ID拉取完整 payload */
async function handleExpandChange(row, expandedRows) {
  const isExpanded = Array.isArray(expandedRows) ? expandedRows.includes(row) : Boolean(expandedRows)
  const txId = row?.txId
  if (!isExpanded || !txId || payloadCache[txId]) return
  try {
    const data = await auditApi.chainDetail(txId)
    payloadCache[txId] = data?.payload ?? {}
  } catch (error) {
    payloadCache[txId] = { message: '该交易ID未查询到完整存证载荷' }
  }
}

/* ---------------- 链完整性校验 ---------------- */
async function handleVerifyChain() {
  verifying.value = true
  try {
    const data = await auditApi.verifyChain()
    verifyResult.value = {
      valid: Boolean(data?.valid),
      blocks: data?.blocks ?? 0,
      brokenAt: data?.brokenAt ?? null,
      checkedAt: data?.checkedAt
    }
    if (verifyResult.value.valid) {
      ElMessage.success(`链完整性校验通过，共校验 ${verifyResult.value.blocks} 个区块`)
    } else {
      ElMessage.error(`链完整性校验失败，断裂位置：${verifyResult.value.brokenAt || '未知'}`)
    }
  } finally {
    verifying.value = false
  }
}

/* ---------------- 载荷复制 ---------------- */
async function handleCopyPayload(row) {
  const text = payloadText(row)
  try {
    if (navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(text)
    } else {
      const area = document.createElement('textarea')
      area.value = text
      document.body.appendChild(area)
      area.select()
      document.execCommand('copy')
      document.body.removeChild(area)
    }
    ElMessage.success('载荷 JSON 已复制到剪贴板')
  } catch (error) {
    ElMessage.warning('当前浏览器环境不支持自动复制，请手动选择文本复制')
  }
}

onMounted(load)
</script>

<style scoped>
.fs-page__actions {
  display: flex;
  align-items: center;
  gap: 10px;
}
.fs-grid + .fs-card {
  margin-top: 16px;
}
.audit-verify {
  display: flex;
  flex-wrap: wrap;
  gap: 18px;
  margin-top: 6px;
  font-size: 13px;
}
.audit-pagination {
  display: flex;
  justify-content: flex-end;
  margin-top: 14px;
}
.audit-risk--high {
  color: var(--fs-danger);
  font-weight: 600;
}
.audit-hash--current {
  color: var(--fs-primary);
}
.audit-payload {
  padding: 12px 18px;
  background: #f7f9fc;
}
.audit-payload__title {
  display: flex;
  align-items: center;
  justify-content: space-between;
  font-weight: 600;
  font-size: 13px;
  margin-bottom: 8px;
}
.audit-payload__code {
  margin: 0 0 8px;
  padding: 12px;
  max-height: 320px;
  overflow: auto;
  background: #101a2c;
  color: #d6e2f5;
  border-radius: 8px;
  line-height: 1.6;
  white-space: pre-wrap;
  word-break: break-all;
}
.audit-regulators {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 12px;
}
.audit-regulator {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px 14px;
  border: 1px solid var(--fs-border);
  border-radius: 8px;
  background: #fbfcfe;
}
.audit-regulator__icon {
  font-size: 20px;
  color: var(--fs-primary);
}
.audit-regulator__body {
  flex: 1;
  min-width: 0;
}
.audit-regulator__name {
  font-weight: 600;
  font-size: 13px;
}
@media (max-width: 1280px) {
  .audit-regulators {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}
@media (max-width: 768px) {
  .audit-regulators {
    grid-template-columns: minmax(0, 1fr);
  }
}
</style>
