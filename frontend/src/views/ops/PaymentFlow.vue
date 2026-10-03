<template>
  <div class="fs-page">
    <!-- 标题区 -->
    <div class="fs-page__header">
      <div>
        <h2 class="fs-page__title">支付智能处理</h2>
        <p class="fs-page__subtitle">
          浙江省服务外包大赛 A16 · 建设范围一：支付智能处理能力建设 ——
          交易接入 → AI 风控前置 → 智能路由 → 通道处理 → 失败重试 → 自动补偿，
          全链路状态可跟踪、路由决策可解释、异常处置可回溯。
        </p>
      </div>
      <div class="fs-toolbar__right">
        <el-button :icon="Refresh" :loading="loading" @click="loadAll">刷新</el-button>
        <el-button plain @click="goChannels">通道池与路由权重</el-button>
      </div>
    </div>

    <!-- 支付链路核心指标 -->
    <div class="fs-grid fs-grid--4">
      <StatCard
        label="处理总量"
        :value="Number(summary.total || 0)"
        unit="笔"
        icon="Tickets"
        color="#1f5fd8"
        :sub="`已进入支付链路 ${formatNumber(summary.processedCount || 0)} 笔`"
      />
      <StatCard
        label="成功率"
        :value="percentValue(summary.successRate)"
        unit="%"
        :precision="1"
        icon="CircleCheck"
        color="#14a37f"
        :sub="`成功 ${formatNumber(summary.successCount || 0)} 笔 / 链路 ${formatNumber(summary.processedCount || 0)} 笔`"
        tip="口径：分母只统计进入支付链路的订单，风控拦截与转人工不计为支付失败"
      />
      <StatCard
        label="直通率"
        :value="percentValue(summary.straightThroughRate)"
        unit="%"
        :precision="1"
        icon="Promotion"
        color="#0ea5e9"
        :sub="'一次通过、无需重试的订单占比'"
      />
      <StatCard
        label="平均耗时"
        :value="Number(summary.avgDurationMs || 0)"
        unit="ms"
        icon="Timer"
        color="#8b5cf6"
        :sub="`P95 耗时 ${formatNumber(summary.p95DurationMs || 0)} ms`"
      />
      <StatCard
        label="重试率"
        :value="percentValue(summary.retryRate)"
        unit="%"
        :precision="1"
        icon="RefreshRight"
        color="#f5a623"
        :sub="'尝试次数大于 1 的订单占比'"
      />
      <StatCard
        label="补偿率"
        :value="percentValue(summary.compensationRate)"
        unit="%"
        :precision="1"
        icon="FirstAidKit"
        color="#e5484d"
        :sub="'重试耗尽后触发自动补偿的占比'"
      />
      <StatCard
        label="风控拦截率"
        :value="percentValue(summary.riskBlockRate)"
        unit="%"
        :precision="1"
        icon="Lock"
        color="#64748b"
        :sub="`拦截 ${formatNumber(summary.blockedCount || 0)} 笔 · 转人工 ${formatNumber(summary.manualCount || 0)} 笔`"
        tip="风控拦截 + 转人工审核占全量订单的比例，体现合规前置强度"
      />
      <StatCard
        label="自动化率"
        :value="percentValue(summary.automationRate)"
        unit="%"
        :precision="1"
        icon="Cpu"
        color="#1f5fd8"
        :sub="'无需人工介入即可闭环的比例'"
        tip="自动化率 =（成功 + 自动补偿 + 风控自动拦截）/ 全量订单"
      />
    </div>

    <!-- 批量处理 + 通道故障演练 -->
    <div class="fs-card fs-flow__batch-card">
      <div class="fs-card__header">
        <span class="fs-card__title">批量处理（含通道故障演练）</span>
        <span class="fs-muted">单批 1 ~ 50 笔 · 故障演练用于现场演示「失败重试 + 自动补偿」</span>
      </div>
      <div class="fs-card__body">
        <div class="fs-toolbar">
          <span class="fs-flow__label">处理笔数</span>
          <el-input-number
            v-model="processForm.count"
            :min="1"
            :max="50"
            :step="1"
            controls-position="right"
            style="width: 130px"
          />
          <span class="fs-flow__label">通道故障演练</span>
          <el-slider
            v-model="processForm.injectFailureRate"
            :min="0"
            :max="0.6"
            :step="0.05"
            :format-tooltip="failureTip"
            style="width: 220px"
          />
          <el-tag size="small" :type="processForm.injectFailureRate > 0 ? 'warning' : 'info'" effect="plain">
            故障注入 {{ formatPercent(processForm.injectFailureRate, 0) }}
          </el-tag>
          <div class="fs-toolbar__right">
            <el-button type="primary" :icon="VideoPlay" :loading="processing" @click="handleProcess">
              开始处理
            </el-button>
          </div>
        </div>

        <el-alert
          type="info"
          show-icon
          :closable="false"
          title="演练说明"
          description="调高故障注入比例后，订单会真实经历「通道处理失败 → 指数退避（200ms / 600ms）→ 自动切换备用通道重试 → 重试耗尽则自动补偿（改道重发或原路退回）」，每一步都会写入订单事件流，可在下方订单表的「全链路跟踪」中逐步回放。"
        />

        <el-descriptions v-if="lastBatch" :column="4" border size="small" class="fs-flow__batch">
          <el-descriptions-item label="本批订单">{{ formatNumber(lastBatch.total || 0) }} 笔</el-descriptions-item>
          <el-descriptions-item label="成功">{{ formatNumber(lastBatch.successCount || 0) }} 笔</el-descriptions-item>
          <el-descriptions-item label="失败 / 已补偿">{{ formatNumber(lastBatch.failedCount || 0) }} 笔</el-descriptions-item>
          <el-descriptions-item label="风控拦截">{{ formatNumber(lastBatch.blockedCount || 0) }} 笔</el-descriptions-item>
          <el-descriptions-item label="转人工审核">{{ formatNumber(lastBatch.manualCount || 0) }} 笔</el-descriptions-item>
          <el-descriptions-item label="本批成功率">{{ formatPercent(lastBatch.successRate || 0) }}</el-descriptions-item>
          <el-descriptions-item label="本批直通率">{{ formatPercent(lastBatch.straightThroughRate || 0) }}</el-descriptions-item>
          <el-descriptions-item label="平均耗时">{{ formatDuration(lastBatch.avgDurationMs || 0) }}</el-descriptions-item>
        </el-descriptions>
      </div>
    </div>

    <!-- 智能路由预演 -->
    <div class="fs-card">
      <div class="fs-card__header">
        <span class="fs-card__title">智能路由预演</span>
        <span class="fs-muted">对一笔拟发起交易打分全部候选通道，输出「为什么选它 / 为什么排除它」</span>
      </div>
      <div class="fs-card__body">
        <div class="fs-toolbar">
          <span class="fs-flow__label">金额</span>
          <el-input-number
            v-model="previewForm.amount"
            :min="1000"
            :max="10000000"
            :step="10000"
            controls-position="right"
            style="width: 170px"
          />
          <span class="fs-flow__label">币种</span>
          <el-select v-model="previewForm.currency" style="width: 110px">
            <el-option v-for="code in currencyOptions" :key="code" :label="code" :value="code" />
          </el-select>
          <span class="fs-flow__label">目的地地区</span>
          <el-select v-model="previewForm.destRegion" style="width: 190px">
            <el-option
              v-for="item in destOptions"
              :key="item.value"
              :label="item.label"
              :value="item.value"
            />
          </el-select>
          <span class="fs-flow__label">风险等级</span>
          <el-select v-model="previewForm.riskLevel" style="width: 130px">
            <el-option v-for="item in RISK_OPTIONS" :key="item.value" :label="item.label" :value="item.value" />
          </el-select>
          <div class="fs-toolbar__right">
            <el-button type="primary" :icon="MagicStick" :loading="previewLoading" @click="handlePreview">
              路由预演
            </el-button>
          </div>
        </div>

        <!-- 权重说明：成本 40% / 成功率 30% / 时效 20% / 合规 10% -->
        <div class="fs-flow__weights">
          <span class="fs-flow__weights-title">路由评分权重</span>
          <el-tooltip v-for="item in weightItems" :key="item.key" :content="item.desc" placement="top">
            <el-tag size="small" effect="plain" :style="{ borderColor: item.color, color: item.color }">
              {{ item.label }} {{ formatPercent(item.value, 0) }}
            </el-tag>
          </el-tooltip>
          <span class="fs-muted">{{ weightSource === 'server' ? '权重来自后端路由引擎实时配置' : '后端未返回权重，按引擎默认配置展示' }}</span>
        </div>

        <el-alert
          v-if="previewResult"
          :type="previewResult.selected ? 'success' : 'warning'"
          show-icon
          :closable="false"
          :title="previewResult.selected ? `选中通道：${previewResult.selectedName || previewResult.selected}` : '无可用通道：所有候选均被排除'"
          :description="selectedDesc"
        />

        <el-table
          v-loading="previewLoading"
          :data="previewResult ? previewResult.candidates || [] : []"
          border
          stripe
          size="small"
          :row-class-name="previewRowClass"
          class="fs-flow__preview-table"
        >
          <el-table-column label="候选通道" min-width="180">
            <template #default="{ row }">
              <div class="fs-flow__channel">
                <strong>{{ row.name || '-' }}</strong>
                <span class="fs-mono fs-muted">{{ row.code || '-' }}</span>
              </div>
            </template>
          </el-table-column>

          <el-table-column label="综合得分" width="150">
            <template #default="{ row }">
              <div class="fs-flow__score">
                <el-progress
                  :percentage="scorePercent(row.score)"
                  :stroke-width="10"
                  :show-text="false"
                  :color="row.eligible ? '#1f5fd8' : '#c9d2e0'"
                />
                <span class="fs-flow__score-text">{{ scoreText(row.score) }}</span>
              </div>
            </template>
          </el-table-column>

          <el-table-column label="是否可选" width="100" align="center">
            <template #default="{ row }">
              <el-tag size="small" :type="row.eligible ? 'success' : 'danger'" effect="plain">
                {{ row.eligible ? '可选' : '已排除' }}
              </el-tag>
            </template>
          </el-table-column>

          <el-table-column label="评分分解（成本 / 成功率 / 时效 / 合规）" min-width="260">
            <template #default="{ row }">
              <div class="fs-flow__breakdown">
                <div v-for="item in breakdownItems(row)" :key="item.key" class="fs-flow__breakdown-row">
                  <span class="fs-flow__breakdown-label">{{ item.label }}</span>
                  <el-progress
                    :percentage="item.percent"
                    :stroke-width="6"
                    :show-text="false"
                    :color="item.color"
                    class="fs-flow__breakdown-bar"
                  />
                  <span class="fs-flow__breakdown-value">{{ item.text }}</span>
                </div>
              </div>
            </template>
          </el-table-column>

          <el-table-column label="费率" width="90" align="right">
            <template #default="{ row }">{{ formatPercent(row.feeRate || 0, 2) }}</template>
          </el-table-column>

          <el-table-column label="历史成功率" width="110" align="right">
            <template #default="{ row }">{{ formatPercent(row.successRate || 0, 1) }}</template>
          </el-table-column>

          <el-table-column label="平均时延" width="105" align="right">
            <template #default="{ row }">{{ formatNumber(row.avgLatencyMs || 0) }} ms</template>
          </el-table-column>

          <el-table-column label="通道状态" width="100" align="center">
            <template #default="{ row }">
              <el-tag size="small" :type="channelStatusOf(row.status).type" effect="plain">
                {{ channelStatusOf(row.status).label }}
              </el-tag>
            </template>
          </el-table-column>

          <el-table-column label="说明 / 排除原因" min-width="260" show-overflow-tooltip>
            <template #default="{ row }">
              <span :class="{ 'fs-flow__reason--excluded': !row.eligible }">{{ row.reason || '-' }}</span>
            </template>
          </el-table-column>

          <template #empty>
            <el-empty description="点击「路由预演」查看全部候选通道的打分与排除原因" :image-size="70" />
          </template>
        </el-table>

        <div v-if="previewResult" class="fs-muted fs-flow__preview-meta">
          预演条件：金额 {{ formatNumber(previewResult.order?.amount || 0, 2) }} {{ previewResult.order?.currency || '-' }}
          · 商户 {{ previewResult.order?.merchantName || '-' }}
          · 目的地 {{ destLabel(previewResult.order?.destRegion) }}
          · 风险等级 {{ riskLabel(previewResult.riskLevel) }}
          · 候选 {{ (previewResult.candidates || []).length }} 条（可选 {{ eligibleCount }} 条）
        </div>
      </div>
    </div>

    <!-- 支付订单列表 -->
    <div class="fs-card">
      <div class="fs-card__header">
        <span class="fs-card__title">支付订单</span>
        <span class="fs-muted">共 {{ formatNumber(total) }} 笔 · 点击任意订单查看全链路状态跟踪</span>
      </div>
      <div class="fs-card__body">
        <el-alert
          v-if="!loading && !total"
          type="info"
          show-icon
          :closable="false"
          :title="summary.note || '暂无支付订单'"
          description="可点击上方「批量处理 → 开始处理」生成演示订单；建议先把「通道故障演练」调到 0.25 ~ 0.4，以便同时演示重试与自动补偿。"
          class="fs-flow__empty-tip"
        />

        <div class="fs-toolbar">
          <el-select v-model="query.status" placeholder="订单状态" clearable style="width: 150px" @change="handleSearch">
            <el-option v-for="item in ORDER_STATUS_OPTIONS" :key="item.value" :label="item.label" :value="item.value" />
          </el-select>

          <el-select v-model="query.channel" placeholder="清算通道" clearable style="width: 200px" @change="handleSearch">
            <el-option v-for="item in channels" :key="item.code" :label="item.name || item.code" :value="item.code" />
          </el-select>

          <el-select v-model="query.riskLevel" placeholder="风险等级" clearable style="width: 130px" @change="handleSearch">
            <el-option v-for="item in RISK_OPTIONS" :key="item.value" :label="item.label" :value="item.value" />
          </el-select>

          <el-input
            v-model="query.keyword"
            placeholder="订单号 / 商户名称"
            clearable
            style="width: 210px"
            @keyup.enter="handleSearch"
            @clear="handleSearch"
          >
            <template #prefix>
              <el-icon><Search /></el-icon>
            </template>
          </el-input>

          <el-button type="primary" :icon="Search" @click="handleSearch">查询</el-button>
          <el-button :icon="RefreshLeft" @click="handleReset">重置</el-button>
        </div>

        <el-table
          v-loading="loading"
          :data="orders"
          border
          stripe
          style="width: 100%"
          @row-click="openDetail"
        >
          <el-table-column prop="code" label="订单号" width="190" fixed>
            <template #default="{ row }">
              <span class="fs-mono fs-flow__code">{{ row.code || '-' }}</span>
            </template>
          </el-table-column>

          <el-table-column label="商户" min-width="170" show-overflow-tooltip>
            <template #default="{ row }">
              <div>{{ row.merchantName || '-' }}</div>
              <span class="fs-muted fs-mono">{{ row.merchantCode || '-' }}</span>
            </template>
          </el-table-column>

          <el-table-column label="金额（币种）" width="150" align="right">
            <template #default="{ row }">
              <span>{{ formatNumber(row.amount || 0, 2) }}</span>
              <span class="fs-muted"> {{ row.currency || '-' }}</span>
            </template>
          </el-table-column>

          <el-table-column label="目的地" width="105">
            <template #default="{ row }">
              <el-tag v-if="isRestricted(row.destRegion)" size="small" type="danger" effect="plain">
                {{ destLabel(row.destRegion) }}
              </el-tag>
              <span v-else>{{ destLabel(row.destRegion) }}</span>
            </template>
          </el-table-column>

          <el-table-column label="清算通道" min-width="170" show-overflow-tooltip>
            <template #default="{ row }">
              <template v-if="row.channel">
                <div>{{ row.channelName || row.channel }}</div>
                <span class="fs-muted fs-mono">{{ row.channel }}</span>
              </template>
              <span v-else class="fs-muted">未路由（未进入清算）</span>
            </template>
          </el-table-column>

          <el-table-column label="状态" width="130">
            <template #default="{ row }">
              <el-tag size="small" :type="statusOf(row.status).type">{{ statusOf(row.status).label }}</el-tag>
            </template>
          </el-table-column>

          <el-table-column label="风险分" width="140">
            <template #default="{ row }">
              <div class="fs-flow__score">
                <el-progress
                  :percentage="riskPercent(row)"
                  :stroke-width="8"
                  :show-text="false"
                  :color="riskColor(row)"
                />
                <span class="fs-flow__score-text">{{ riskText(row.riskScore) }}</span>
                <el-tag size="small" effect="plain" :style="{ color: riskColor(row), borderColor: riskColor(row) }">
                  {{ riskLabel(row.riskLevel) }}
                </el-tag>
              </div>
            </template>
          </el-table-column>

          <el-table-column label="尝试次数" width="95" align="center">
            <template #default="{ row }">
              <span :class="{ 'fs-flow__retry': Number(row.attempts || 0) > 1 }">
                {{ formatNumber(row.attempts || 0) }} 次
              </span>
            </template>
          </el-table-column>

          <el-table-column label="链路耗时" width="105" align="right">
            <template #default="{ row }">{{ formatDuration(row.durationMs || 0) }}</template>
          </el-table-column>

          <el-table-column label="接入时间" width="165">
            <template #default="{ row }">{{ formatTime(row.createdAt) }}</template>
          </el-table-column>

          <el-table-column label="操作" width="110" fixed="right">
            <template #default="{ row }">
              <el-button link type="primary" @click.stop="openDetail(row)">全链路跟踪</el-button>
            </template>
          </el-table-column>

          <template #empty>
            <el-empty description="暂无符合条件的支付订单" :image-size="80" />
          </template>
        </el-table>

        <div class="fs-flow__pager">
          <el-pagination
            v-model:current-page="query.page"
            v-model:page-size="query.size"
            :page-sizes="[10, 20, 50]"
            :total="total"
            layout="total, sizes, prev, pager, next, jumper"
            background
            @size-change="handleSizeChange"
            @current-change="handlePageChange"
          />
        </div>
      </div>
    </div>

    <!-- 图表区：通道路由分布 + 订单状态分布 -->
    <div class="fs-grid fs-grid--2 fs-flow__charts">
      <div class="fs-card">
        <div class="fs-card__header">
          <span class="fs-card__title">通道路由分布</span>
          <span class="fs-muted">智能路由选中的通道及其承接订单量</span>
        </div>
        <div class="fs-card__body">
          <ChartBox :option="channelOption" :height="300" :loading="loading" empty-text="暂无路由分布数据" />
        </div>
      </div>

      <div class="fs-card">
        <div class="fs-card__header">
          <span class="fs-card__title">订单状态分布</span>
          <span class="fs-muted">成功 / 失败补偿 / 风控拦截 / 转人工</span>
        </div>
        <div class="fs-card__body">
          <ChartBox :option="statusPieOption" :height="300" :loading="loading" empty-text="暂无订单状态数据" />
        </div>
      </div>
    </div>

    <!-- 订单全链路状态跟踪抽屉 -->
    <el-drawer v-model="detailVisible" title="支付订单全链路状态跟踪" size="780px">
      <div v-loading="detailLoading" class="fs-flow__detail">
        <template v-if="detail">
          <!-- 处置结论 -->
          <el-alert
            :type="conclusion.type"
            show-icon
            :closable="false"
            :title="conclusion.title"
            :description="conclusion.desc"
          />

          <!-- 链路步骤：接入 → 风控 → 路由 → 处理 → 重试 → 补偿 -->
          <el-steps :active="6" align-center finish-status="success" class="fs-flow__steps">
            <el-step
              v-for="(item, index) in chainSteps"
              :key="item.stage || index"
              :title="item.label || item.stage || `步骤${index + 1}`"
              :description="chainDesc(item.stage)"
              :status="stepStatusOf(index)"
            />
          </el-steps>

          <el-descriptions :column="2" border size="small" class="fs-flow__detail-meta">
            <el-descriptions-item label="订单号">
              <span class="fs-mono">{{ detail.code || '-' }}</span>
            </el-descriptions-item>
            <el-descriptions-item label="订单状态">
              <el-tag size="small" :type="statusOf(detail.status).type">{{ statusOf(detail.status).label }}</el-tag>
            </el-descriptions-item>
            <el-descriptions-item label="商户">
              {{ detail.merchantName || '-' }}
              <span class="fs-muted fs-mono">（{{ detail.merchantCode || '-' }}）</span>
            </el-descriptions-item>
            <el-descriptions-item label="交易地区">
              {{ destLabel(detail.region) }} → {{ destLabel(detail.destRegion) }}
            </el-descriptions-item>
            <el-descriptions-item label="金额">
              {{ formatNumber(detail.amount || 0, 2) }} {{ detail.currency || '-' }}
            </el-descriptions-item>
            <el-descriptions-item label="清算通道">
              {{ detail.channelName || detail.channel || '未路由' }}
              <span v-if="detail.channel" class="fs-muted fs-mono">（{{ detail.channel }}）</span>
            </el-descriptions-item>
            <el-descriptions-item label="风险评分">
              <span :style="{ color: riskColor(detail) }">{{ riskText(detail.riskScore) }}</span>
              · {{ riskLabel(detail.riskLevel) }}
            </el-descriptions-item>
            <el-descriptions-item label="路由综合得分">{{ scoreText(detail.routeScore) }}</el-descriptions-item>
            <el-descriptions-item label="尝试次数">
              {{ formatNumber(detail.attempts || 0) }} 次
              <span class="fs-muted">（最多重试 {{ retryPolicy.maxRetry ?? 2 }} 次）</span>
            </el-descriptions-item>
            <el-descriptions-item label="链路耗时">{{ formatDuration(detail.durationMs || 0) }}</el-descriptions-item>
            <el-descriptions-item label="接入时间">{{ formatTime(detail.createdAt) }}</el-descriptions-item>
            <el-descriptions-item label="完成时间">{{ formatTime(detail.finishedAt) }}</el-descriptions-item>
            <el-descriptions-item label="失败原因" :span="2">{{ detail.failureReason || '无（链路未发生失败）' }}</el-descriptions-item>
            <el-descriptions-item label="自动补偿" :span="2">
              <el-tag size="small" :type="detail.compensated ? 'warning' : 'info'" effect="plain">
                {{ detail.compensated ? '已生成补偿单（改道重发 / 原路退回）' : '未触发补偿' }}
              </el-tag>
            </el-descriptions-item>
          </el-descriptions>

          <!-- 事件时间线：按 level 着色 -->
          <el-divider content-position="left">全链路事件留痕（{{ events.length }} 条）</el-divider>
          <el-timeline v-if="events.length" class="fs-flow__timeline">
            <el-timeline-item
              v-for="(item, index) in events"
              :key="index"
              :timestamp="item.ts || '-'"
              :type="eventType(item)"
              size="normal"
            >
              <div class="fs-flow__event">
                <el-tag size="small" effect="plain" :type="eventType(item)">{{ item.stage || '事件' }}</el-tag>
                <span>{{ item.detail || '-' }}</span>
              </div>
              <div v-if="item.channel" class="fs-muted fs-mono">通道：{{ item.channel }}</div>
            </el-timeline-item>
          </el-timeline>
          <el-empty v-else description="该订单暂无链路事件" :image-size="70" />
        </template>

        <el-empty v-else description="请选择一笔订单查看全链路状态跟踪" :image-size="80" />
      </div>
    </el-drawer>
  </div>
</template>

<script setup>
/**
 * 支付智能处理（赛题 A16 · 建设范围一）
 *
 * 接口契约（backend/api/ops.py 的「① 支付智能处理」段落）：
 * - GET  /api/ops/payment/channels        通道池 + 受限目的地 + 重试策略 + 路由权重
 * - POST /api/ops/payment/route-preview   路由预演（候选打分明细与排除原因）
 * - POST /api/ops/payment/process         批量处理（接入→风控→路由→处理→重试→补偿）
 * - GET  /api/ops/payment/orders          订单分页（状态/通道/风险等级/关键字筛选）
 * - GET  /api/ops/payment/orders/<code>   订单详情（含 chain 链路定义）
 * - GET  /api/ops/payment/summary         链路指标（成功率/直通率/重试率/补偿率/拦截率）
 *
 * 项目当前 api 封装（src/api/index.js）尚未包含 ops 接口，为避免改动既有文件，
 * 本页直接使用 axios 实例 request 调用，响应拦截器已统一解包 { code, message, data }。
 */
import { computed, onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
// 仅导入需要以组件对象形式绑定的图标（其余图标在 main.js 已全量全局注册，模板中可直接写标签名）
import { MagicStick, Refresh, RefreshLeft, Search, VideoPlay } from '@element-plus/icons-vue'
import request from '@/api/request'
import ChartBox from '@/components/ChartBox.vue'
import StatCard from '@/components/StatCard.vue'
import { CHART_COLORS, RISK_LEVEL, baseChartOption, formatDuration, formatNumber, formatPercent, formatTime } from '@/utils/format'

const router = useRouter()

/* ---------------- 字典与常量 ---------------- */

/** 订单状态字典（与 backend/models.py PaymentOrder.status 注释一致） */
const ORDER_STATUS = {
  received: { label: '已接入', type: 'info' },
  risk_checked: { label: '风控通过', type: 'primary' },
  routed: { label: '已路由', type: 'primary' },
  processing: { label: '处理中', type: 'primary' },
  success: { label: '支付成功', type: 'success' },
  retrying: { label: '重试后成功', type: 'success' },
  failed: { label: '处理失败', type: 'danger' },
  compensated: { label: '已自动补偿', type: 'warning' },
  blocked: { label: '风控拦截', type: 'danger' },
  manual: { label: '转人工审核', type: 'warning' }
}

const ORDER_STATUS_OPTIONS = Object.entries(ORDER_STATUS).map(([value, meta]) => ({ value, label: meta.label }))

/** 通道健康状态字典 */
const CHANNEL_STATUS = {
  available: { label: '可用', type: 'success' },
  degraded: { label: '降级', type: 'warning' },
  down: { label: '已下线', type: 'danger' }
}

const RISK_OPTIONS = [
  { value: 'low', label: '低风险' },
  { value: 'medium', label: '中风险' },
  { value: 'high', label: '高风险' }
]

/** 地区中文名（后端以地区编码返回，前端做可读映射） */
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

const CURRENCY_FALLBACK = ['USD', 'EUR', 'CNY', 'SGD']
const DEST_FALLBACK = ['EU', 'US', 'SEA', 'ME', 'AF', 'CN']

/** 链路步骤兜底定义（订单详情接口返回 chain 时优先使用后端定义） */
const CHAIN_FALLBACK = [
  { stage: '接入', label: '交易接入' },
  { stage: '风控', label: 'AI 风控前置' },
  { stage: '路由', label: '智能路由' },
  { stage: '处理', label: '通道处理' },
  { stage: '重试', label: '失败重试' },
  { stage: '补偿', label: '自动补偿' }
]

/** 链路步骤说明（用于 el-steps 的 description） */
const CHAIN_DESC = {
  接入: '统一接单入口，落地订单',
  风控: '风险评分 → 拦截 / 转人工 / 放行',
  路由: '成本·成功率·时效·合规多目标打分',
  处理: '提交清算并跟踪回执',
  重试: '指数退避 + 自动切换备用通道',
  补偿: '改道重发或原路退回'
}

/** 事件阶段 → 链路步骤下标（把事件流映射到 el-steps 的进度） */
const STAGE_INDEX = {
  接入: 0,
  风控: 1,
  处置: 1,
  路由: 2,
  处理: 3,
  成功: 3,
  失败: 3,
  重试: 4,
  补偿: 5
}

/** 已进入终态的订单状态 */
const TERMINAL_STATUSES = ['success', 'retrying', 'failed', 'compensated', 'blocked', 'manual']

/** 路由评分权重元数据（权重值以后端 /payment/channels 返回为准） */
const WEIGHT_META = [
  { key: 'cost', label: '成本', color: '#1f5fd8', desc: '通道费率越低得分越高（按费率 / 1.5% 归一化）' },
  { key: 'success', label: '成功率', color: '#14a37f', desc: '以通道历史清算成功率直接计分' },
  { key: 'latency', label: '时效', color: '#f5a623', desc: '平均到账时延越低得分越高（按时延 / 4000ms 归一化）' },
  { key: 'compliance', label: '合规', color: '#8b5cf6', desc: '合规能力评分：降级通道扣分、高风险订单加权' }
]

const DEFAULT_WEIGHTS = { cost: 0.4, success: 0.3, latency: 0.2, compliance: 0.1 }

/** 评分分解的展示顺序与配色（与后端 breakdown 的键一致） */
const BREAKDOWN_META = [
  { key: 'cost', label: '成本', color: '#1f5fd8' },
  { key: 'success', label: '成功率', color: '#14a37f' },
  { key: 'latency', label: '时效', color: '#f5a623' },
  { key: 'compliance', label: '合规', color: '#8b5cf6' }
]

/* ---------------- 响应式状态 ---------------- */

const loading = ref(false)
const processing = ref(false)
const previewLoading = ref(false)
const detailLoading = ref(false)
const detailVisible = ref(false)

const channels = ref([])
const restricted = ref([])
const retryPolicy = ref({ maxRetry: 2, backoffMs: [200, 600] })
const weights = ref({ ...DEFAULT_WEIGHTS })
const weightSource = ref('default')

const summary = ref({})
const orders = ref([])
const total = ref(0)
const lastBatch = ref(null)
const previewResult = ref(null)
const detail = ref(null)

const processForm = reactive({ count: 12, injectFailureRate: 0.25 })
const previewForm = reactive({ amount: 200000, currency: 'USD', destRegion: 'EU', riskLevel: 'low' })
const query = reactive({ status: '', channel: '', riskLevel: '', keyword: '', page: 1, size: 10 })

/* ---------------- 计算属性 ---------------- */

const currencyOptions = computed(() => {
  const set = new Set()
  channels.value.forEach((item) => (item.currencies || []).forEach((code) => set.add(code)))
  const list = Array.from(set)
  return list.length ? list : CURRENCY_FALLBACK
})

const destOptions = computed(() => {
  const list = []
  channels.value.forEach((item) => {
    ;(item.destinations || []).forEach((code) => {
      if (!list.some((exist) => exist.value === code)) list.push({ value: code, label: destLabel(code) })
    })
  })
  // 受限目的地由后端返回，追加到选项末尾，便于演示「合规前置直接排除」
  ;(restricted.value || []).forEach((code) => {
    if (!list.some((exist) => exist.value === code)) list.push({ value: code, label: `${destLabel(code)}（受限）` })
  })
  if (list.length) return list
  return DEST_FALLBACK.map((code) => ({ value: code, label: destLabel(code) }))
})

const weightItems = computed(() =>
  WEIGHT_META.map((item) => {
    const value = Number(weights.value?.[item.key] ?? DEFAULT_WEIGHTS[item.key]) || 0
    return { ...item, value }
  })
)

const eligibleCount = computed(() =>
  (previewResult.value?.candidates || []).filter((item) => item.eligible).length
)

/** 预演结论说明：选中通道的关键指标 + 被排除通道数量 */
const selectedDesc = computed(() => {
  const result = previewResult.value
  if (!result) return ''
  const candidates = result.candidates || []
  if (!result.selected) {
    const excluded = candidates.filter((item) => !item.eligible)
    const reasons = excluded.slice(0, 3).map((item) => `${item.name || item.code}：${item.reason || '不满足准入条件'}`)
    return `共 ${candidates.length} 条候选全部被排除（币种 / 目的地 / 限额 / 合规限制）。示例：${reasons.join('；') || '无候选通道'}`
  }
  const selected = candidates.find((item) => item.code === result.selected) || {}
  return `按「${weightItems.value.map((item) => `${item.label}${formatPercent(item.value, 0)}`).join(' + ')}」加权，` +
    `该通道综合得分 ${scoreText(selected.score)}，费率 ${formatPercent(selected.feeRate || 0, 2)}、` +
    `历史成功率 ${formatPercent(selected.successRate || 0, 1)}、平均到账 ${formatNumber(selected.avgLatencyMs || 0)} ms；` +
    `另有 ${candidates.filter((item) => !item.eligible).length} 条候选因准入条件被排除。`
})

const chainSteps = computed(() => {
  const chain = detail.value?.chain
  return Array.isArray(chain) && chain.length ? chain : CHAIN_FALLBACK
})

const events = computed(() => (Array.isArray(detail.value?.events) ? detail.value.events : []))

/** 处置结论：把订单状态翻译成一句可读的业务结论 */
const conclusion = computed(() => {
  const order = detail.value || {}
  const status = order.status || ''
  const attempts = Number(order.attempts || 0)
  const reason = order.failureReason || ''
  if (status === 'blocked') {
    return {
      type: 'error',
      title: '处置结论：风控前置拦截，未进入支付链路',
      desc: `风险评分 ${riskText(order.riskScore)}（${riskLabel(order.riskLevel)}）超过拦截阈值，订单被直接拒绝并上链存证，未占用通道资源。${reason ? `处置原因：${reason}。` : ''}`
    }
  }
  if (status === 'manual') {
    return {
      type: 'warning',
      title: '处置结论：转人工合规审核',
      desc: `风险评分 ${riskText(order.riskScore)}（${riskLabel(order.riskLevel)}）超过人工复核阈值，订单已转人工合规岗处理，等待人工放行或拒绝。`
    }
  }
  if (status === 'compensated') {
    return {
      type: 'error',
      title: '处置结论：重试耗尽 → 已触发自动补偿',
      desc: `共尝试 ${attempts} 次（最多重试 ${retryPolicy.value?.maxRetry ?? 2} 次），最终失败原因「${reason || '处理失败'}」；系统已生成补偿单，按「改道重发 / 原路退回」完成兜底，无需人工介入。`
    }
  }
  if (status === 'failed') {
    return {
      type: 'error',
      title: '处置结论：处理失败（已进入补偿流程）',
      desc: `失败原因「${reason || '无可用通道'}」，路由阶段未找到满足币种 / 目的地 / 限额 / 合规要求的通道，订单未提交清算。`
    }
  }
  if (status === 'success' || status === 'retrying') {
    return {
      type: 'success',
      title: status === 'retrying' ? '处置结论：失败重试后成功' : '处置结论：一次直通成功',
      desc: `经「${order.channelName || order.channel || '最优通道'}」清算成功，共尝试 ${attempts} 次，链路耗时 ${formatDuration(order.durationMs || 0)}，路由综合得分 ${scoreText(order.routeScore)}。`
    }
  }
  return {
    type: 'info',
    title: '处置结论：链路处理中',
    desc: `订单当前状态「${statusOf(status).label}」，尚未进入终态，可刷新列表查看最新进度。`
  }
})

/* ---------------- 图表配置 ---------------- */

/** 柱状图：通道路由分布（数量 + 金额） */
const channelOption = computed(() => {
  const list = Array.isArray(summary.value.channelDistribution) ? summary.value.channelDistribution : []
  return baseChartOption({
    tooltip: {
      trigger: 'axis',
      axisPointer: { type: 'shadow' },
      formatter: (params) => {
        const first = Array.isArray(params) ? params[0] : params
        if (!first) return ''
        const bucket = list[first.dataIndex] || {}
        return `${first.name}<br/>承接订单：<b>${formatNumber(bucket.count || 0)}</b> 笔<br/>承接金额：<b>${formatNumber(bucket.amount || 0, 2)}</b>`
      }
    },
    legend: { show: false },
    xAxis: {
      type: 'category',
      data: list.map((item) => item.code || '-'),
      axisLabel: { interval: 0, fontSize: 11, rotate: list.length > 4 ? 20 : 0 }
    },
    yAxis: { type: 'value', name: '订单数', nameTextStyle: { fontSize: 11 } },
    series: [
      {
        name: '承接订单',
        type: 'bar',
        barMaxWidth: 36,
        itemStyle: { borderRadius: [4, 4, 0, 0], color: CHART_COLORS[0] },
        label: { show: true, position: 'top', fontSize: 11 },
        data: list.map((item) => Number(item.count || 0))
      }
    ]
  })
})

/** 环形饼图：订单状态分布（取自 summary 的全量口径计数） */
const statusPieOption = computed(() => {
  const list = [
    { name: '成功（含重试后成功）', value: Number(summary.value.successCount || 0) },
    { name: '失败 / 已自动补偿', value: Number(summary.value.failedCount || 0) },
    { name: '风控拦截', value: Number(summary.value.blockedCount || 0) },
    { name: '转人工审核', value: Number(summary.value.manualCount || 0) }
  ].filter((item) => item.value > 0)
  return {
    color: ['#14a37f', '#e5484d', '#f5a623', '#8b5cf6'],
    tooltip: { trigger: 'item', formatter: '{b}：{c} 笔（{d}%）' },
    legend: { bottom: 0, icon: 'circle', itemWidth: 10, itemHeight: 10, textStyle: { fontSize: 12 } },
    series: [
      {
        type: 'pie',
        radius: ['46%', '68%'],
        center: ['50%', '44%'],
        avoidLabelOverlap: true,
        itemStyle: { borderColor: '#fff', borderWidth: 2 },
        label: { formatter: '{b}\n{c} 笔', fontSize: 11 },
        data: list
      }
    ]
  }
})

/* ---------------- 展示辅助函数 ---------------- */

function destLabel(code) {
  if (!code) return '-'
  return REGION_LABEL[code] || code
}

function isRestricted(code) {
  return (restricted.value || []).includes(code)
}

function statusOf(status) {
  return ORDER_STATUS[status] || { label: status || '未知', type: 'info' }
}

function channelStatusOf(status) {
  return CHANNEL_STATUS[status] || { label: status || '未知', type: 'info' }
}

function riskLabel(level) {
  return RISK_LEVEL[level]?.label || level || '未评级'
}

function riskColor(row) {
  return RISK_LEVEL[row?.riskLevel]?.color || '#1f5fd8'
}

function riskText(score) {
  const value = Number(score || 0)
  return value.toFixed(3)
}

/** 百分比数值（StatCard 用 number + precision 展示，避免字符串拼接） */
function percentValue(rate) {
  return Number(((Number(rate || 0) * 100).toFixed(1)))
}

function scoreText(score) {
  return Number(score || 0).toFixed(4)
}

function scorePercent(score) {
  const value = Number(score || 0) * 100
  return Math.min(100, Math.max(0, Number(value.toFixed(1))))
}

function riskPercent(row) {
  const value = Number(row?.riskScore || 0) * 100
  return Math.min(100, Math.max(0, Math.round(value)))
}

/** el-slider 提示文案：故障注入概率 */
function failureTip(value) {
  return `故障注入 ${formatPercent(value || 0, 0)}`
}

/** 评分分解：把 breakdown 转为 4 条小进度条 */
function breakdownItems(row) {
  const breakdown = row?.breakdown || {}
  return BREAKDOWN_META.map((item) => {
    const value = Number(breakdown[item.key] ?? 0)
    return {
      key: item.key,
      label: item.label,
      color: item.color,
      percent: Math.min(100, Math.max(0, Number((value * 100).toFixed(1)))),
      text: value.toFixed(3)
    }
  })
}

/** 预演表格行高亮：选中通道（row-class-name 必须返回字符串） */
function previewRowClass({ row }) {
  return previewResult.value?.selected && row?.code === previewResult.value.selected
    ? 'fs-flow__row--selected'
    : ''
}

/** 事件着色：优先使用后端写入的 level，其次按阶段推断 */
function eventType(item) {
  const level = item?.level
  if (level === 'danger') return 'danger'
  if (level === 'warning') return 'warning'
  const stage = item?.stage || ''
  if (stage === '成功') return 'success'
  if (stage === '失败' || stage === '补偿') return 'danger'
  if (stage === '重试') return 'warning'
  if (stage === '处置') return ['blocked', 'manual'].includes(detail.value?.status) ? 'danger' : 'warning'
  return 'primary'
}

function chainDesc(stage) {
  return CHAIN_DESC[stage] || ''
}

/**
 * 链路步骤状态：把订单状态 + 事件流映射为 el-step 的 status
 * - 风控拦截 / 转人工：链路终止在「风控」步骤（红色）
 * - 已发生的步骤标绿；非终态订单的最后一步标为进行中
 * - 重试 / 补偿只有真实发生时才点亮，避免「未发生也显示已完成」
 */
function stepStatusOf(index) {
  const order = detail.value || {}
  const status = order.status || 'received'
  const occurred = new Set()
  events.value.forEach((item) => {
    const value = STAGE_INDEX[item?.stage]
    if (value !== undefined) occurred.add(value)
  })
  const reached = occurred.size ? Math.max(...occurred) : 0

  if (status === 'blocked' || status === 'manual') {
    if (index === 0) return 'finish'
    return index === 1 ? 'error' : 'wait'
  }
  if (index === 5 && status === 'compensated') return 'error'
  if (!occurred.has(index)) return index > reached ? 'wait' : 'finish'
  if (status === 'failed' && index === reached) return 'error'
  if (!TERMINAL_STATUSES.includes(status) && index === reached) return 'process'
  return 'finish'
}

/* ---------------- 数据加载 ---------------- */

/** 通道池 + 受限目的地 + 重试策略 + 路由权重 */
async function loadChannels() {
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
    // 拦截器已提示错误，这里退化为空通道池，页面其余部分仍可用
    channels.value = []
    restricted.value = []
  }
}

/** 链路指标 */
async function loadSummary() {
  try {
    const data = await request.get('/ops/payment/summary')
    summary.value = data || {}
  } catch (error) {
    summary.value = {}
  }
}

/** 订单分页列表 */
async function loadOrders() {
  try {
    const data = await request.get('/ops/payment/orders', {
      params: {
        page: query.page,
        size: query.size,
        status: query.status || undefined,
        channel: query.channel || undefined,
        riskLevel: query.riskLevel || undefined,
        keyword: query.keyword || undefined
      }
    })
    orders.value = data?.list ?? []
    total.value = Number(data?.total || 0)
  } catch (error) {
    orders.value = []
    total.value = 0
  }
}

async function loadAll() {
  loading.value = true
  try {
    // 三个接口互不依赖，并发拉取；单个失败由各自的 catch 兜底
    await Promise.all([loadChannels(), loadSummary(), loadOrders()])
  } finally {
    loading.value = false
  }
}

/* ---------------- 交互 ---------------- */

function handleSearch() {
  query.page = 1
  loadOrders()
}

function handleReset() {
  query.status = ''
  query.channel = ''
  query.riskLevel = ''
  query.keyword = ''
  query.page = 1
  loadOrders()
}

function handleSizeChange() {
  query.page = 1
  loadOrders()
}

// 分页组件清空页号时会传 undefined，这里做保护避免带非法页码请求
function handlePageChange(page) {
  if (!page) return
  loadOrders()
}

/** 批量处理：接入 → 风控 → 智能路由 → 处理 → 重试 → 补偿 */
async function handleProcess() {
  processing.value = true
  try {
    const count = Math.min(50, Math.max(1, Number(processForm.count || 1)))
    const data = await request.post(
      '/ops/payment/process',
      {
        count,
        injectFailureRate: Number(processForm.injectFailureRate || 0)
      },
      { silent: false }
    )
    const batchSummary = data?.summary || {}
    const created = data?.orders ?? []
    lastBatch.value = batchSummary
    ElMessage.success(
      `本次处理 ${formatNumber(created.length || batchSummary.total || 0)} 笔：` +
        `成功 ${formatNumber(batchSummary.successCount || 0)} 笔、` +
        `失败/补偿 ${formatNumber(batchSummary.failedCount || 0)} 笔、` +
        `风控拦截 ${formatNumber(batchSummary.blockedCount || 0)} 笔、` +
        `转人工 ${formatNumber(batchSummary.manualCount || 0)} 笔`
    )
    query.page = 1
    await Promise.all([loadOrders(), loadSummary()])
  } catch (error) {
    // 接口层已弹出失败提示，这里只需保证按钮 loading 复位
  } finally {
    processing.value = false
  }
}

/** 路由预演 */
async function handlePreview() {
  previewLoading.value = true
  try {
    const data = await request.post(
      '/ops/payment/route-preview',
      {
        amount: Number(previewForm.amount || 0),
        currency: previewForm.currency,
        destRegion: previewForm.destRegion,
        riskLevel: previewForm.riskLevel
      },
      { silent: false }
    )
    previewResult.value = data || null
    if (!data?.selected) {
      ElMessage.warning('本次预演没有可用通道：全部候选均被排除，请在表格中查看排除原因')
    }
  } catch (error) {
    previewResult.value = null
  } finally {
    previewLoading.value = false
  }
}

/** 打开订单全链路跟踪抽屉 */
async function openDetail(row) {
  if (!row?.code) {
    ElMessage.warning('订单号缺失，无法查看链路详情')
    return
  }
  detailVisible.value = true
  detailLoading.value = true
  detail.value = row // 先用列表行兜底渲染，避免抽屉出现空白
  try {
    const data = await request.get(`/ops/payment/orders/${encodeURIComponent(row.code)}`)
    detail.value = data || row
  } catch (error) {
    // 详情接口失败时保留列表行数据，链路事件仍可展示
  } finally {
    detailLoading.value = false
  }
}

function goChannels() {
  router.push('/ops/channels')
}

onMounted(() => {
  loadAll()
})
</script>

<style scoped>
.fs-flow__batch-card {
  margin-top: 16px;
}
.fs-flow__label {
  color: var(--fs-text-secondary);
  font-size: 13px;
}
.fs-flow__batch {
  margin-top: 14px;
}
.fs-flow__weights {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 10px;
  margin: 14px 0;
  padding: 10px 12px;
  background: #f7f9fc;
  border: 1px dashed var(--fs-border);
  border-radius: 8px;
}
.fs-flow__weights-title {
  font-weight: 600;
  font-size: 13px;
}
.fs-flow__preview-table {
  margin-top: 14px;
}
.fs-flow__preview-meta {
  margin-top: 10px;
}
.fs-flow__channel {
  display: flex;
  flex-direction: column;
  line-height: 1.4;
}
.fs-flow__score {
  display: flex;
  flex-direction: column;
  gap: 4px;
  align-items: flex-start;
}
.fs-flow__score-text {
  font-size: 12px;
  color: var(--fs-text-secondary);
  font-variant-numeric: tabular-nums;
}
.fs-flow__retry {
  color: var(--fs-warning);
  font-weight: 600;
}
.fs-flow__code {
  color: var(--fs-primary);
  cursor: pointer;
}
.fs-flow__breakdown {
  display: flex;
  flex-direction: column;
  gap: 3px;
  padding: 4px 0;
}
.fs-flow__breakdown-row {
  display: flex;
  align-items: center;
  gap: 8px;
}
.fs-flow__breakdown-label {
  width: 44px;
  flex: 0 0 44px;
  font-size: 12px;
  color: var(--fs-text-secondary);
}
.fs-flow__breakdown-bar {
  flex: 1;
  min-width: 60px;
}
.fs-flow__breakdown-value {
  width: 40px;
  flex: 0 0 40px;
  font-size: 12px;
  text-align: right;
  color: var(--fs-text-secondary);
  font-variant-numeric: tabular-nums;
}
.fs-flow__reason--excluded {
  color: var(--fs-danger);
}
.fs-flow__empty-tip {
  margin-bottom: 14px;
}
.fs-flow__pager {
  display: flex;
  justify-content: flex-end;
  margin-top: 14px;
}
.fs-flow__charts {
  margin-top: 16px;
}
/* 栅格内的卡片由 grid 的 gap 控制间距，去掉 .fs-card + .fs-card 的纵向外边距 */
.fs-flow__charts > .fs-card + .fs-card {
  margin-top: 0;
}
.fs-flow__detail {
  min-height: 240px;
}
.fs-flow__steps {
  margin: 20px 0 6px;
}
.fs-flow__detail-meta {
  margin-top: 14px;
}
.fs-flow__timeline {
  padding-left: 2px;
}
.fs-flow__event {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  font-size: 13px;
  line-height: 1.6;
}
/* 预演表格选中行高亮（row-class-name 生成的 tr 在子组件内，需要 :deep 穿透） */
:deep(.fs-flow__row--selected) td.el-table__cell {
  background: #e8f0fe !important;
}
</style>
