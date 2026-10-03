<template>
  <div class="fs-page fs-review">
    <!-- 页面头部 -->
    <div class="fs-page__header">
      <div>
        <h2 class="fs-page__title">
          <el-icon class="fs-review__title-icon"><Files /></el-icon>
          AI 审核一致性管理
        </h2>
        <p class="fs-page__subtitle">
          统一审核标准、统一风险标签、统一处置口径与一致性评估机制 ·
          形成「AI 初审 → 人工复核 → 差异回流 → 持续优化」的协同审核闭环
          （赛题 A16 实现目标 3 / 建设范围四）
        </p>
      </div>
      <div class="fs-toolbar__right">
        <el-tag :type="loading ? 'warning' : 'success'" effect="plain" size="large">
          当前批次：{{ batchFilter === 'all' ? '全部批次' : batchFilter || '全部批次' }}
        </el-tag>
        <el-button :icon="Refresh" @click="refreshAll">刷新</el-button>
      </div>
    </div>

    <!-- 统计口径说明 -->
    <el-alert
      type="info"
      :closable="false"
      show-icon
      title="一致性统计口径说明"
      class="fs-review__note"
    >
      <div class="fs-review__note-body">
        一致性 = AI 自主决策样本（通过 / 拒绝）中与人工结论一致的比例；
        <b>AI 转人工属于协同而非分歧</b>，计入总体协同率（overallAlignmentRate），不计入一致率与分歧统计。
        漏放 / 误拦仅在 AI 自主决策样本上统计，因为只有它们才代表 AI 的自主判断风险。
      </div>
    </el-alert>

    <!-- 审核批次 -->
    <div class="fs-card">
      <div class="fs-card__header">
        <span class="fs-card__title">审核批次</span>
        <span class="fs-muted">
          每批次样本数为 4~60 笔（AI 初审 + 人工复核 + 差异标记落库，构成一致性评估数据基础）
        </span>
      </div>
      <div class="fs-card__body">
        <div class="fs-toolbar">
          <span class="fs-review__field-label">审核笔数</span>
          <el-input-number v-model="batchCount" :min="4" :max="60" :step="4" />
          <span class="fs-review__field-label">一致性评估批次</span>
          <el-select v-model="batchFilter" placeholder="全部批次" style="width: 240px" @change="handleBatchChange">
            <el-option label="全部批次（汇总）" value="all" />
            <el-option
              v-for="item in batches"
              :key="item.batchCode"
              :label="`${item.batchCode}（${item.count} 笔）`"
              :value="item.batchCode"
            />
          </el-select>
          <el-button type="primary" :icon="VideoPlay" :loading="running" @click="handleRunBatch">
            执行审核批次
          </el-button>
          <el-button :icon="Refresh" @click="refreshAll">刷新</el-button>
        </div>

        <el-descriptions :column="4" border size="small">
          <el-descriptions-item label="当前通过阈值">
            {{ policy.approveThreshold ?? '-' }}
          </el-descriptions-item>
          <el-descriptions-item label="当前拒绝阈值">
            {{ policy.rejectThreshold ?? '-' }}
          </el-descriptions-item>
          <el-descriptions-item label="置信度门槛">
            {{ policy.confidenceFloor ?? '-' }}
          </el-descriptions-item>
          <el-descriptions-item label="评估样本量">
            {{ metrics.total || 0 }} 笔
          </el-descriptions-item>
        </el-descriptions>
      </div>
    </div>

    <!-- 核心 KPI -->
    <div class="fs-grid fs-grid--4 fs-review__kpi">
      <StatCard
        label="核心一致性"
        :value="percentValue(metrics.agreementRate)"
        unit="%"
        :precision="1"
        icon="CircleCheck"
        color="#14a37f"
        sub="AI 自主决策样本中与人工一致的比例"
      />
      <StatCard
        label="总体协同率"
        :value="percentValue(metrics.overallAlignmentRate)"
        unit="%"
        :precision="1"
        icon="Connection"
        color="#1f5fd8"
        sub="含转人工样本（转人工视为协同成功）"
      />
      <StatCard
        label="自动化率"
        :value="percentValue(metrics.automationRate)"
        unit="%"
        :precision="1"
        icon="MagicStick"
        color="#8b5cf6"
        sub="AI 可独立决策（通过 / 拒绝）比例"
      />
      <StatCard
        label="转人工比例"
        :value="percentValue(metrics.manualTransferRate)"
        unit="%"
        :precision="1"
        icon="UserFilled"
        color="#0ea5e9"
        sub="低置信度或高风险样本转人工复核"
      />
    </div>
    <div class="fs-grid fs-grid--4 fs-review__kpi">
      <StatCard
        label="Cohen's Kappa"
        :value="Number(metrics.kappa || 0)"
        :precision="3"
        icon="DataAnalysis"
        color="#f5a623"
        :sub="metrics.kappaLevel || '暂无评估数据'"
        tip="排除随机一致后 AI 与人工的真实一致性水平"
      />
      <StatCard
        label="漏放笔数"
        :value="Number(metrics.falseNegativeCount || 0)"
        unit="笔"
        icon="WarningFilled"
        color="#e5484d"
        :sub="`漏放率 ${formatPercent(metrics.falseNegativeRate)}（AI 通过但人工拒绝）`"
      />
      <StatCard
        label="误拦笔数"
        :value="Number(metrics.falsePositiveCount || 0)"
        unit="笔"
        icon="CircleCloseFilled"
        color="#f5a623"
        :sub="`误拦率 ${formatPercent(metrics.falsePositiveRate)}（AI 拒绝但人工通过）`"
      />
      <StatCard
        label="AI 初审提速"
        :value="Number(efficiency.speedup || 0)"
        unit="倍"
        :precision="1"
        icon="Odometer"
        color="#14a37f"
        sub="相对人工复核平均耗时的提速倍数"
      />
    </div>

    <!-- 一致性评估 -->
    <div class="fs-card">
      <div class="fs-card__header">
        <span class="fs-card__title">一致性评估</span>
        <span class="fs-muted">混淆矩阵 / 风险等级一致率 / 置信度区间一致率 / 效率与分歧统计</span>
      </div>
      <div class="fs-card__body">
        <el-row :gutter="16">
          <el-col :xs="24" :lg="10">
            <div class="fs-review__sub-title">混淆矩阵（行 = AI 结论，列 = 人工结论）</div>
            <el-table :data="matrixRows" border stripe size="small" class="fs-review__matrix">
              <el-table-column prop="aiLabel" label="AI 结论" width="130" fixed />
              <el-table-column v-for="col in matrixCols" :key="col.key" :label="col.label" align="center">
                <template #default="{ row }">
                  <span :class="{ 'fs-review__matrix-hit': row.aiKey === col.key }">
                    {{ cellValue(row.aiKey, col.key) }}
                  </span>
                </template>
              </el-table-column>
            </el-table>
            <div class="fs-muted fs-review__hint">
              对角线（同色高亮）为 AI 与人工结论一致的样本；非对角线即为分歧或转人工协同。
            </div>
          </el-col>
          <el-col :xs="24" :lg="14">
            <div class="fs-review__sub-title">按风险等级一致率</div>
            <ChartBox :option="riskOption" :height="260" :loading="loading" empty-text="暂无评估数据，请先执行审核批次" />
          </el-col>
        </el-row>

        <el-row :gutter="16" class="fs-review__row-gap">
          <el-col :xs="24" :lg="14">
            <div class="fs-review__sub-title">按置信度区间一致率（柱 = 一致率，折线 = 样本量）</div>
            <ChartBox
              :option="confidenceOption"
              :height="300"
              :loading="loading"
              empty-text="暂无评估数据，请先执行审核批次"
            />
          </el-col>
          <el-col :xs="24" :lg="10">
            <div class="fs-review__sub-title">效率对比（AI 初审 vs 人工复核）</div>
            <el-descriptions :column="1" border size="small">
              <el-descriptions-item label="AI 初审平均耗时">
                {{ formatDuration(efficiency.aiAvgLatencyMs) }}
              </el-descriptions-item>
              <el-descriptions-item label="人工复核平均耗时">
                {{ formatDuration(efficiency.humanAvgLatencyMs) }}
              </el-descriptions-item>
              <el-descriptions-item label="提速倍数">
                <b class="fs-review__speedup">{{ Number(efficiency.speedup || 0).toFixed(1) }} 倍</b>
              </el-descriptions-item>
              <el-descriptions-item label="自动化 / 转人工">
                {{ metrics.autoReviewedCount || 0 }} 笔 / {{ metrics.manualTransferredCount || 0 }} 笔
              </el-descriptions-item>
            </el-descriptions>
            <div class="fs-muted fs-review__hint">
              置信度越低越应交人工：低置信度区间一致率通常明显偏低，这正是「置信度门槛强制转人工」规则的依据。
            </div>
          </el-col>
        </el-row>

        <div class="fs-review__diff">
          <div class="fs-review__diff-card fs-review__diff-card--danger">
            <div class="fs-review__diff-head">
              <el-icon><WarningFilled /></el-icon>
              <span>漏放（false negative）</span>
              <b>{{ metrics.falseNegativeCount || 0 }} 笔</b>
            </div>
            <div class="fs-review__diff-desc">
              AI 通过但人工拒绝，属<b>合规风险</b>：漏放率 {{ formatPercent(metrics.falseNegativeRate) }}，
              需提高强证据规则权重或下调通过阈值。
            </div>
          </div>
          <div class="fs-review__diff-card fs-review__diff-card--warning">
            <div class="fs-review__diff-head">
              <el-icon><Warning /></el-icon>
              <span>误拦（false positive）</span>
              <b>{{ metrics.falsePositiveCount || 0 }} 笔</b>
            </div>
            <div class="fs-review__diff-desc">
              AI 拒绝但人工通过，属<b>体验损失</b>：误拦率 {{ formatPercent(metrics.falsePositiveRate) }}，
              需放缓拒绝阈值以避免误伤优质商户。
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- 审核记录 -->
    <div class="fs-card">
      <div class="fs-card__header">
        <span class="fs-card__title">审核记录</span>
        <span class="fs-muted">共 {{ records.total || 0 }} 条 · 点击「对照」查看 AI 评分、命中证据与人工意见</span>
      </div>
      <div class="fs-card__body">
        <div class="fs-toolbar">
          <el-select v-model="query.batchCode" placeholder="批次" style="width: 200px" @change="handleFilterChange">
            <el-option label="全部批次" value="all" />
            <el-option
              v-for="item in batches"
              :key="item.batchCode"
              :label="`${item.batchCode}（${item.count} 笔）`"
              :value="item.batchCode"
            />
          </el-select>
          <el-select v-model="query.agreed" placeholder="是否一致" style="width: 150px" @change="handleFilterChange">
            <el-option label="全部" value="all" />
            <el-option label="一致" value="true" />
            <el-option label="不一致" value="false" />
          </el-select>
          <el-select v-model="query.diffType" placeholder="分歧类型" style="width: 170px" @change="handleFilterChange">
            <el-option label="全部分歧类型" value="all" />
            <el-option v-for="item in DIFF_TYPES" :key="item.value" :label="item.label" :value="item.value" />
          </el-select>
          <el-select v-model="query.riskLevel" placeholder="风险等级" style="width: 150px" @change="handleFilterChange">
            <el-option label="全部等级" value="all" />
            <el-option v-for="item in RISK_LEVELS" :key="item.value" :label="item.label" :value="item.value" />
          </el-select>
          <el-button :icon="Refresh" @click="loadRecords">刷新记录</el-button>
        </div>

        <el-table v-loading="loading" :data="records.list" border stripe size="small">
          <el-table-column prop="code" label="编号" width="150" show-overflow-tooltip />
          <el-table-column prop="targetId" label="目标ID" width="130" show-overflow-tooltip />
          <el-table-column label="金额" width="130" align="right">
            <template #default="{ row }">{{ formatAmount(row?.amount) }}</template>
          </el-table-column>
          <el-table-column label="风险等级" width="100" align="center">
            <template #default="{ row }">
              <el-tag size="small" :type="riskTagType(row?.riskLevel)" effect="plain">
                {{ riskLabel(row?.riskLevel) }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column label="AI 结论" width="110">
            <template #default="{ row }">
              <el-tag size="small" :type="decisionTagType(row?.aiDecision)">
                {{ decisionLabel(row?.aiDecision) }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column label="置信度" width="190">
            <template #default="{ row }">
              <div class="fs-review__confidence">
                <el-progress
                  :percentage="confidencePercent(row?.aiConfidence)"
                  :stroke-width="10"
                  :show-text="false"
                  :color="confidenceColor(row?.aiConfidence)"
                />
                <span class="fs-mono fs-review__confidence-text">
                  {{ Number(row?.aiConfidence ?? 0).toFixed(2) }}
                </span>
              </div>
            </template>
          </el-table-column>
          <el-table-column label="人工结论" width="110">
            <template #default="{ row }">
              <el-tag size="small" :type="decisionTagType(row?.humanDecision)" effect="plain">
                {{ decisionLabel(row?.humanDecision) }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column label="是否一致" width="120" align="center">
            <template #default="{ row }">
              <span v-if="row?.agreed" class="fs-review__agreed">
                <el-icon><CircleCheckFilled /></el-icon>
                一致
              </span>
              <span v-else class="fs-review__disagreed">
                <el-icon><CircleCloseFilled /></el-icon>
                不一致
              </span>
            </template>
          </el-table-column>
          <el-table-column label="分歧类型" width="150" align="center">
            <template #default="{ row }">
              <el-tag v-if="!row?.agreed" size="small" :type="diffTagType(row?.diffType)">
                {{ diffLabel(row?.diffType) }}
              </el-tag>
              <span v-else class="fs-muted">-</span>
            </template>
          </el-table-column>
          <el-table-column label="操作" width="90" align="center" fixed="right">
            <template #default="{ row }">
              <el-button text type="primary" size="small" @click="openDrawer(row)">对照</el-button>
            </template>
          </el-table-column>
          <template #empty>暂无审核记录，请先执行审核批次</template>
        </el-table>

        <div class="fs-review__pagination">
          <el-pagination
            background
            layout="total, sizes, prev, pager, next, jumper"
            :total="records.total || 0"
            :current-page="query.page"
            :page-size="query.size"
            :page-sizes="[10, 20, 50, 100]"
            @current-change="handlePageChange"
            @size-change="handleSizeChange"
          />
        </div>
      </div>
    </div>

    <!-- 差异回流与持续优化 -->
    <div class="fs-card">
      <div class="fs-card__header">
        <span class="fs-card__title">差异回流与持续优化</span>
        <div class="fs-toolbar__right">
          <el-button type="primary" :icon="MagicStick" :loading="optimizing" @click="handleOptimize">
            生成优化建议
          </el-button>
          <el-button
            type="success"
            :icon="Select"
            :loading="applying"
            :disabled="!canApply"
            @click="handleApply"
          >
            应用优化策略
          </el-button>
        </div>
      </div>
      <div class="fs-card__body">
        <el-row :gutter="16">
          <el-col :xs="24" :lg="10">
            <div class="fs-review__sub-title">当前审核策略（统一审核标准）</div>
            <el-descriptions :column="1" border size="small">
              <el-descriptions-item label="通过阈值 approveThreshold">
                {{ policy.approveThreshold ?? '-' }}
              </el-descriptions-item>
              <el-descriptions-item label="拒绝阈值 rejectThreshold">
                {{ policy.rejectThreshold ?? '-' }}
              </el-descriptions-item>
              <el-descriptions-item label="置信度门槛 confidenceFloor">
                {{ policy.confidenceFloor ?? '-' }}
              </el-descriptions-item>
            </el-descriptions>
            <div class="fs-review__sub-title fs-review__sub-title--gap">规则权重 ruleWeights</div>
            <el-table :data="weightRows" border stripe size="small">
              <el-table-column prop="label" label="规则" min-width="130" />
              <el-table-column label="权重" width="90" align="center">
                <template #default="{ row }">
                  <span class="fs-mono">{{ row.weight }}</span>
                </template>
              </el-table-column>
              <el-table-column prop="desc" label="说明" min-width="170" show-overflow-tooltip />
              <template #empty>暂无规则权重</template>
            </el-table>
          </el-col>
          <el-col :xs="24" :lg="14">
            <div class="fs-review__sub-title">差异回流建议（基于分歧样本与候选策略复盘）</div>
            <el-alert
              v-if="optimizeResult"
              :type="optimizeResult.improved ? 'success' : 'info'"
              :closable="false"
              show-icon
              :title="optimizeResult.improved
                ? '已找到综合得分更优的策略（一致性 / 自动化率 / 漏放率加权目标）'
                : '当前策略已是最优：建议维持现有阈值，继续抽样复核积累样本'"
              class="fs-review__optimize-alert"
            />
            <el-timeline v-if="optimizePoints.length">
              <el-timeline-item
                v-for="(item, index) in optimizePoints"
                :key="index"
                :timestamp="`回流要点 ${index + 1}`"
                :type="index === 0 ? 'primary' : 'info'"
                placement="top"
              >
                <div class="fs-review__point">{{ item }}</div>
              </el-timeline-item>
            </el-timeline>
            <el-empty v-else description="尚未生成优化建议，点击右上角「生成优化建议」" :image-size="70" />

            <template v-if="optimizeResult">
              <div class="fs-review__sub-title fs-review__sub-title--gap">优化前后指标对比（同一批样本复盘）</div>
              <el-table :data="compareRows" border stripe size="small">
                <el-table-column prop="label" label="指标" min-width="140" />
                <el-table-column label="优化前" width="120" align="center">
                  <template #default="{ row }">{{ row.beforeText }}</template>
                </el-table-column>
                <el-table-column label="变化" width="110" align="center">
                  <template #default="{ row }">
                    <span v-if="row.trend === 'same'" class="fs-muted">持平</span>
                    <span v-else :class="row.trend === 'up' ? 'fs-review__trend-up' : 'fs-review__trend-down'">
                      <el-icon>
                        <component :is="row.trend === 'up' ? 'Top' : 'Bottom'" />
                      </el-icon>
                      {{ row.better ? '改善' : '变差' }}
                    </span>
                  </template>
                </el-table-column>
                <el-table-column label="优化后" width="120" align="center">
                  <template #default="{ row }">{{ row.afterText }}</template>
                </el-table-column>
              </el-table>
            </template>
          </el-col>
        </el-row>

        <template v-if="optimizeResult">
          <div class="fs-review__sub-title fs-review__sub-title--gap">
            候选策略表（阈值网格复盘结果，按综合得分降序取前 {{ optimizeCandidates.length }} 组）
          </div>
          <el-table :data="optimizeCandidates" border stripe size="small">
            <el-table-column label="通过阈值" width="100" align="center">
              <template #default="{ row }">{{ configOf(row, 'approveThreshold') }}</template>
            </el-table-column>
            <el-table-column label="拒绝阈值" width="100" align="center">
              <template #default="{ row }">{{ configOf(row, 'rejectThreshold') }}</template>
            </el-table-column>
            <el-table-column label="置信度门槛" width="110" align="center">
              <template #default="{ row }">{{ configOf(row, 'confidenceFloor') }}</template>
            </el-table-column>
            <el-table-column label="一致率" width="100" align="center">
              <template #default="{ row }">{{ formatPercent(row?.metrics?.agreementRate) }}</template>
            </el-table-column>
            <el-table-column label="自动化率" width="110" align="center">
              <template #default="{ row }">{{ formatPercent(row?.metrics?.automationRate) }}</template>
            </el-table-column>
            <el-table-column label="漏放 / 误拦" width="130" align="center">
              <template #default="{ row }">
                {{ row?.metrics?.falseNegativeCount ?? 0 }} / {{ row?.metrics?.falsePositiveCount ?? 0 }}
              </template>
            </el-table-column>
            <el-table-column label="综合得分" width="110" align="center">
              <template #default="{ row }">
                <b class="fs-mono">{{ Number(row?.score ?? 0).toFixed(4) }}</b>
              </template>
            </el-table-column>
            <el-table-column label="硬约束" min-width="150" align="center">
              <template #default="{ row }">
                <el-tag size="small" :type="row?.constraintOk ? 'success' : 'danger'" effect="plain">
                  {{ row?.constraintOk ? '满足硬约束' : '违反硬约束' }}
                </el-tag>
              </template>
            </el-table-column>
            <template #empty>暂无候选策略</template>
          </el-table>
          <div class="fs-muted fs-review__hint">
            硬约束：① 漏放率不得高于当前策略；② 一致性不得低于当前策略的 98%。
            综合得分 = 0.6 × 一致率 + 0.25 × 自动化率 − 1.0 × 漏放率（体现「宁可转人工，不可放过风险」的合规底线）。
          </div>
        </template>
      </div>
    </div>

    <!-- 优化记录 -->
    <div class="fs-card">
      <div class="fs-card__header">
        <span class="fs-card__title">优化记录</span>
        <span class="fs-muted">差异回流与持续优化的证据链（共 {{ optimizations.length }} 条）</span>
      </div>
      <div class="fs-card__body">
        <el-table v-loading="loading" :data="optimizations" border stripe size="small">
          <el-table-column prop="code" label="编号" width="130" show-overflow-tooltip />
          <el-table-column label="批次" width="150" show-overflow-tooltip>
            <template #default="{ row }">{{ row?.batchCode || 'all' }}</template>
          </el-table-column>
          <el-table-column label="建议摘要" min-width="300" show-overflow-tooltip>
            <template #default="{ row }">{{ row?.suggestion || '-' }}</template>
          </el-table-column>
          <el-table-column label="优化前一致率" width="130" align="center">
            <template #default="{ row }">{{ formatPercent(row?.beforeMetrics?.agreementRate) }}</template>
          </el-table-column>
          <el-table-column label="优化后一致率" width="130" align="center">
            <template #default="{ row }">
              <b>{{ formatPercent(row?.afterMetrics?.agreementRate) }}</b>
            </template>
          </el-table-column>
          <el-table-column label="是否已应用" width="120" align="center">
            <template #default="{ row }">
              <el-tag size="small" :type="row?.applied ? 'success' : 'info'" effect="plain">
                {{ row?.applied ? '已应用' : '未应用' }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column label="应用人" width="130" show-overflow-tooltip>
            <template #default="{ row }">{{ row?.appliedBy || '-' }}</template>
          </el-table-column>
          <el-table-column label="时间" width="170">
            <template #default="{ row }">{{ formatTime(row?.createdAt) }}</template>
          </el-table-column>
          <template #empty>暂无优化记录</template>
        </el-table>
      </div>
    </div>

    <!-- 人机对照抽屉 -->
    <el-drawer v-model="drawerVisible" title="AI 初审 / 人工复核对照" size="620px" destroy-on-close>
      <div v-if="current" class="fs-review__drawer">
        <el-descriptions :column="2" border size="small">
          <el-descriptions-item label="审核编号">{{ current.code || '-' }}</el-descriptions-item>
          <el-descriptions-item label="批次">{{ current.batchCode || '-' }}</el-descriptions-item>
          <el-descriptions-item label="目标对象">
            {{ current.targetId || '-' }}（{{ current.targetType || '-' }}）
          </el-descriptions-item>
          <el-descriptions-item label="金额">{{ formatAmount(current.amount) }}</el-descriptions-item>
          <el-descriptions-item label="风险等级">
            <el-tag size="small" :type="riskTagType(current.riskLevel)" effect="plain">
              {{ riskLabel(current.riskLevel) }}
            </el-tag>
          </el-descriptions-item>
          <el-descriptions-item label="复核时间">{{ formatTime(current.reviewedAt) }}</el-descriptions-item>
          <el-descriptions-item label="AI 结论">
            <el-tag size="small" :type="decisionTagType(current.aiDecision)">
              {{ decisionLabel(current.aiDecision) }}
            </el-tag>
          </el-descriptions-item>
          <el-descriptions-item label="人工结论">
            <el-tag size="small" :type="decisionTagType(current.humanDecision)" effect="plain">
              {{ decisionLabel(current.humanDecision) }}
            </el-tag>
          </el-descriptions-item>
        </el-descriptions>

        <el-divider content-position="left">AI 评分与置信度</el-divider>
        <div class="fs-review__score">
          <el-progress
            :percentage="scorePercent(current.aiScore)"
            :stroke-width="16"
            :color="scoreColor(current.aiScore)"
          >
            <span class="fs-review__score-text">
              AI 评分 {{ Number(current.aiScore ?? 0).toFixed(4) }}
            </span>
          </el-progress>
        </div>
        <div class="fs-muted">
          当前策略：通过阈值 {{ policy.approveThreshold ?? '-' }} ·
          拒绝阈值 {{ policy.rejectThreshold ?? '-' }} ·
          置信度门槛 {{ policy.confidenceFloor ?? '-' }}
        </div>
        <div class="fs-review__score">
          <el-progress
            :percentage="confidencePercent(current.aiConfidence)"
            :stroke-width="16"
            :color="confidenceColor(current.aiConfidence)"
          >
            <span class="fs-review__score-text">
              置信度 {{ Number(current.aiConfidence ?? 0).toFixed(4) }}
            </span>
          </el-progress>
        </div>
        <div class="fs-muted">
          AI 初审耗时 {{ formatDuration(current.aiLatencyMs) }} ·
          人工复核耗时 {{ formatDuration(current.humanLatencyMs) }}
        </div>

        <el-divider content-position="left">AI 命中证据（aiReasons）</el-divider>
        <div v-if="(current.aiReasons || []).length">
          <div v-for="(item, index) in current.aiReasons" :key="index" class="fs-review__reason">
            <el-tag size="small" type="danger" effect="plain">{{ item?.rule || 'rule' }}</el-tag>
            <span class="fs-review__reason-text">{{ item?.text || '-' }}</span>
            <span class="fs-muted">权重 {{ item?.weight ?? '-' }}</span>
          </div>
        </div>
        <el-alert
          v-else
          type="success"
          :closable="false"
          show-icon
          title="未命中任何风险规则：AI 依据低风险特征直接给出结论"
        />

        <el-divider content-position="left">人工复核意见</el-divider>
        <el-descriptions :column="1" border size="small">
          <el-descriptions-item label="复核人">{{ current.humanReviewer || '-' }}</el-descriptions-item>
          <el-descriptions-item label="人工意见">{{ current.humanComment || '-' }}</el-descriptions-item>
          <el-descriptions-item label="一致性判定">
            <el-tag size="small" :type="current.agreed ? 'success' : 'danger'" effect="plain">
              {{ current.agreed ? '一致' : `不一致 · ${diffLabel(current.diffType)}` }}
            </el-tag>
            <span v-if="current.diffSeverity" class="fs-muted">
              　分歧严重度：{{ severityLabel(current.diffSeverity) }}
            </span>
          </el-descriptions-item>
        </el-descriptions>

        <el-divider content-position="left">特征向量（features，用于同批复盘）</el-divider>
        <el-descriptions :column="2" border size="small">
          <el-descriptions-item v-for="item in featureRows" :key="item.label" :label="item.label">
            {{ item.value }}
          </el-descriptions-item>
        </el-descriptions>
      </div>
      <el-empty v-else description="请选择一条审核记录" :image-size="80" />
    </el-drawer>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { Files, MagicStick, Refresh, Select, VideoPlay } from '@element-plus/icons-vue'
import request from '@/api/request'
import ChartBox from '@/components/ChartBox.vue'
import StatCard from '@/components/StatCard.vue'
import { baseChartOption, formatAmount, formatDuration, formatPercent, formatTime } from '@/utils/format'

/** 统一审核结论口径（与后端 review.DECISION_LABELS 一致） */
const DECISION_LABELS = { approve: '通过', reject: '拒绝', manual: '转人工' }
const DECISION_TAG = { approve: 'success', reject: 'danger', manual: 'warning' }
/** 统一风险标签体系（与后端 review.RISK_TAGS 一致） */
const RISK_LABELS = { high: '高风险', medium: '中风险', low: '低风险' }
const RISK_TAG = { high: 'danger', medium: 'warning', low: 'success' }
/** 风险等级筛选项 */
const RISK_LEVELS = [
  { value: 'high', label: '高风险' },
  { value: 'medium', label: '中风险' },
  { value: 'low', label: '低风险' }
]
/** 分歧类型字典（none 表示一致） */
const DIFF_TYPES = [
  { value: 'false_negative', label: '漏放（AI 通过→人工拒绝）' },
  { value: 'false_positive', label: '误拦（AI 拒绝→人工通过）' },
  { value: 'both_manual', label: '均转人工' }
]
const DIFF_LABELS = {
  none: '一致',
  false_negative: '漏放',
  false_positive: '误拦',
  both_manual: '均转人工'
}
/** 规则权重中文说明（与后端规则引擎字段名一一对应） */
const RULE_LABELS = [
  { key: 'sanctionHit', label: '命中制裁清单', desc: 'OFAC / 联合国制裁清单命中，强证据' },
  { key: 'highRiskRegion', label: '高风险地区', desc: '交易目的地属高风险国家或地区' },
  { key: 'amountAnomaly', label: '金额异常', desc: '单笔金额显著高于同层级商户均值' },
  { key: 'velocity', label: '拆分交易', desc: '1 小时内多笔交易，存在化整为零特征' },
  { key: 'identityMismatch', label: '身份不一致', desc: 'KYC 身份信息与结算账户不一致' },
  { key: 'newMerchant', label: '新商户', desc: '商户入驻时间过短，历史数据不足' },
  { key: 'nightTrade', label: '夜间交易', desc: '夜间交易占比偏高，行为异常' }
]
/** 优化前后对比指标方向：up 表示越大越好，down 表示越小越好 */
const COMPARE_METRICS = [
  { key: 'agreementRate', label: '核心一致性', dir: 'up', percent: true },
  { key: 'overallAlignmentRate', label: '总体协同率', dir: 'up', percent: true },
  { key: 'automationRate', label: '自动化率', dir: 'up', percent: true },
  { key: 'manualTransferRate', label: '转人工比例', dir: 'down', percent: true },
  { key: 'kappa', label: "Cohen's Kappa", dir: 'up', percent: false },
  { key: 'falseNegativeCount', label: '漏放笔数', dir: 'down', percent: false },
  { key: 'falsePositiveCount', label: '误拦笔数', dir: 'down', percent: false }
]

const loading = ref(false)
const running = ref(false)
const optimizing = ref(false)
const applying = ref(false)

const batchCount = ref(20)
const batchFilter = ref('all')
const batches = ref([])
const policy = ref({})
const standards = ref({})
const metrics = ref({})
const optimizations = ref([])
const optimizeResult = ref(null)
const drawerVisible = ref(false)
const current = ref(null)

const query = reactive({
  batchCode: 'all',
  agreed: 'all',
  diffType: 'all',
  riskLevel: 'all',
  page: 1,
  size: 10
})
const records = reactive({ list: [], total: 0, page: 1, size: 10 })

/* ---------------- 取值兜底工具（接口缺字段时不出现 undefined 报错） ---------------- */

function valueOf(source, key, fallback = 0) {
  const value = (source || {})[key]
  return value === null || value === undefined ? fallback : value
}

function percentValue(rate, precision = 1) {
  return Number((Number(rate || 0) * 100).toFixed(precision))
}

function cellValue(aiKey, humanKey) {
  const matrix = metrics.value.confusionMatrix || {}
  const row = matrix[aiKey] || {}
  return Number(row[humanKey] || 0)
}

function decisionLabel(key) {
  return DECISION_LABELS[key] || key || '-'
}

function decisionTagType(key) {
  return DECISION_TAG[key] || 'info'
}

function riskLabel(key) {
  return RISK_LABELS[key] || key || '-'
}

/** 风险等级 → 标签色：未知取值回退为 info，避免空标签 */
function riskTagType(key) {
  return RISK_TAG[key] || 'info'
}

function diffLabel(key) {
  return DIFF_LABELS[key] || key || '-'
}

function diffTagType(key) {
  if (key === 'false_negative') return 'danger'
  if (key === 'false_positive') return 'warning'
  return 'info'
}

function severityLabel(key) {
  if (key === 'high') return '高'
  if (key === 'medium') return '中'
  if (key === 'low') return '低'
  return '-'
}

function confidencePercent(confidence) {
  return Math.max(0, Math.min(100, Math.round(Number(confidence || 0) * 100)))
}

function confidenceColor(confidence) {
  const value = Number(confidence || 0)
  if (value >= 0.8) return '#14a37f'
  if (value >= 0.6) return '#1f5fd8'
  return '#f5a623'
}

function scorePercent(score) {
  return Math.max(0, Math.min(100, Math.round(Number(score || 0) * 100)))
}

function scoreColor(score) {
  const value = Number(score || 0)
  if (value >= 0.72) return '#e5484d'
  if (value >= 0.35) return '#f5a623'
  return '#14a37f'
}

function configOf(row, key) {
  const value = ((row || {}).config || {})[key]
  return value === null || value === undefined ? '-' : value
}

/* ---------------- 计算属性 ---------------- */

const efficiency = computed(() => metrics.value.efficiency || {})

const matrixCols = computed(() =>
  Object.keys(DECISION_LABELS).map((key) => ({ key, label: DECISION_LABELS[key] }))
)

const matrixRows = computed(() =>
  Object.keys(DECISION_LABELS).map((key) => ({ aiKey: key, aiLabel: DECISION_LABELS[key] }))
)

const riskOption = computed(() => {
  const byRisk = metrics.value.byRiskLevel || {}
  // 仅在存在评估结果的风险等级上出柱，避免空数据时显示成「0%」的假数据
  const levels = ['high', 'medium', 'low'].filter((level) => byRisk[level])
  const labels = levels.map((level) => RISK_LABELS[level])
  const rates = levels.map((level) => percentValue(valueOf(byRisk[level], 'agreementRate')))
  const totals = levels.map((level) => Number(valueOf(byRisk[level], 'total')))
  return baseChartOption({
    tooltip: {
      trigger: 'axis',
      axisPointer: { type: 'shadow' },
      formatter: (params) => {
        const list = params || []
        if (!list.length) return ''
        const index = list[0].dataIndex
        return `${labels[index]}<br/>一致率：<b>${rates[index]}%</b><br/>AI 自主决策样本：${totals[index]} 笔`
      }
    },
    legend: { show: false },
    grid: { left: 12, right: 24, top: 24, bottom: 6, containLabel: true },
    xAxis: { type: 'category', data: labels, axisTick: { show: false } },
    yAxis: {
      type: 'value',
      name: '一致率(%)',
      min: 0,
      max: 100,
      axisLabel: { formatter: '{value}%' },
      splitLine: { lineStyle: { type: 'dashed' } }
    },
    series: [
      {
        name: '一致率',
        type: 'bar',
        barMaxWidth: 44,
        itemStyle: { borderRadius: [6, 6, 0, 0] },
        label: { show: true, position: 'top', formatter: '{c}%', fontSize: 12 },
        data: rates
      }
    ]
  })
})

const confidenceOption = computed(() => {
  const buckets = Array.isArray(metrics.value.byConfidence) ? metrics.value.byConfidence : []
  const ranges = buckets.map((item) => item?.range || '-')
  const rates = buckets.map((item) => percentValue(valueOf(item, 'agreementRate')))
  const totals = buckets.map((item) => Number(valueOf(item, 'total')))
  return baseChartOption({
    tooltip: { trigger: 'axis', axisPointer: { type: 'cross' } },
    legend: { show: true, right: 10, top: 4 },
    grid: { left: 12, right: 24, top: 40, bottom: 6, containLabel: true },
    xAxis: {
      type: 'category',
      name: '置信度区间',
      data: ranges,
      axisTick: { show: false },
      axisLabel: { fontSize: 11 }
    },
    yAxis: [
      {
        type: 'value',
        name: '一致率(%)',
        min: 0,
        max: 100,
        axisLabel: { formatter: '{value}%' },
        splitLine: { lineStyle: { type: 'dashed' } }
      },
      {
        type: 'value',
        name: '样本量',
        minInterval: 1,
        splitLine: { show: false },
        axisLabel: { formatter: '{value}' }
      }
    ],
    series: [
      {
        name: '一致率',
        type: 'bar',
        yAxisIndex: 0,
        barMaxWidth: 40,
        itemStyle: { color: '#1f5fd8', borderRadius: [6, 6, 0, 0] },
        label: { show: true, position: 'top', formatter: '{c}%', fontSize: 11 },
        data: rates
      },
      {
        name: '样本量',
        type: 'line',
        yAxisIndex: 1,
        smooth: true,
        symbolSize: 7,
        itemStyle: { color: '#f5a623' },
        lineStyle: { width: 2 },
        data: totals
      }
    ]
  })
})

const weightRows = computed(() => {
  const weights = policy.value.ruleWeights || {}
  return RULE_LABELS.map((item) => ({
    key: item.key,
    label: item.label,
    desc: item.desc,
    weight: weights[item.key] === undefined ? '-' : weights[item.key]
  }))
})

const optimizePoints = computed(() => {
  const points = (optimizeResult.value || {}).points
  return Array.isArray(points) ? points.filter((item) => !!item) : []
})

const optimizeCandidates = computed(() => {
  const list = (optimizeResult.value || {}).candidates
  return Array.isArray(list) ? list : []
})

/** 是否可应用优化策略：只有存在更优策略（improved=true）时才允许应用 */
const canApply = computed(() => !!optimizeResult.value && optimizeResult.value.improved === true)

const compareRows = computed(() => {
  const result = optimizeResult.value
  if (!result) return []
  const before = result.beforeMetrics || {}
  const after = result.afterMetrics || {}
  return COMPARE_METRICS.map((item) => {
    const beforeValue = Number(valueOf(before, item.key))
    const afterValue = Number(valueOf(after, item.key))
    const beforeText = item.percent ? formatPercent(beforeValue) : String(beforeValue)
    const afterText = item.percent ? formatPercent(afterValue) : String(afterValue)
    const diff = Number((afterValue - beforeValue).toFixed(6))
    let trend = 'same'
    if (diff > 0) trend = 'up'
    if (diff < 0) trend = 'down'
    const better = trend === 'same' ? true : item.dir === 'up' ? trend === 'up' : trend === 'down'
    return { key: item.key, label: item.label, beforeText, afterText, trend, better }
  })
})

/** 特征向量中文标注（用于抽屉中的样本复盘） */
const FEATURE_LABELS = [
  { key: 'code', label: '交易编号' },
  { key: 'name', label: '商户编码' },
  { key: 'amount', label: '交易金额' },
  { key: 'destRegion', label: '目的地' },
  { key: 'merchantAge', label: '商户账龄（月）' },
  { key: 'identityMatch', label: '身份一致性' },
  { key: 'nightRatio', label: '夜间交易占比' },
  { key: 'sanctionHit', label: '制裁清单命中' },
  { key: 'historyDeclines', label: '历史拒付笔数' },
  { key: 'velocity1h', label: '1 小时交易笔数' }
]

const featureRows = computed(() => {
  const features = (current.value || {}).features || {}
  return FEATURE_LABELS.map((item) => {
    const raw = features[item.key]
    let value = '-'
    if (raw !== undefined && raw !== null && raw !== '') {
      if (item.key === 'amount') value = formatAmount(raw)
      else if (typeof raw === 'boolean') value = raw ? '一致 / 命中' : '否'
      else value = String(raw)
    }
    return { label: item.label, value }
  })
})

/* ---------------- 数据加载 ---------------- */

async function loadBatches() {
  try {
    const data = await request.get('/ops/review/batches')
    batches.value = Array.isArray(data) ? data : []
  } catch (error) {
    batches.value = []
  }
}

async function loadPolicy() {
  try {
    const data = await request.get('/ops/review/policy')
    policy.value = (data && data.policy) || {}
    standards.value = (data && data.standards) || {}
  } catch (error) {
    policy.value = {}
    standards.value = {}
  }
}

async function loadConsistency() {
  try {
    const data = await request.get('/ops/review/consistency', {
      params: { batchCode: batchFilter.value || 'all' }
    })
    metrics.value = data || {}
  } catch (error) {
    metrics.value = {}
  }
}

async function loadRecords() {
  loading.value = true
  try {
    const data = await request.get('/ops/review/records', {
      params: {
        batchCode: query.batchCode || 'all',
        agreed: query.agreed || 'all',
        diffType: query.diffType || 'all',
        riskLevel: query.riskLevel || 'all',
        page: query.page,
        size: query.size
      }
    })
    const payload = data || {}
    records.list = Array.isArray(payload.list) ? payload.list : []
    records.total = Number(payload.total || 0)
    records.page = Number(payload.page || query.page)
    records.size = Number(payload.size || query.size)
  } catch (error) {
    records.list = []
    records.total = 0
  } finally {
    loading.value = false
  }
}

async function loadOptimizations() {
  try {
    const data = await request.get('/ops/review/optimizations')
    optimizations.value = Array.isArray(data) ? data : []
  } catch (error) {
    optimizations.value = []
  }
}

/** 刷新全部：批次、策略、一致性指标、记录、优化记录、标准 */
async function refreshAll() {
  loading.value = true
  try {
    await Promise.all([loadBatches(), loadPolicy(), loadConsistency(), loadOptimizations()])
    await loadRecords()
  } finally {
    loading.value = false
  }
}

/* ---------------- 交互事件 ---------------- */

async function handleRunBatch() {
  const count = Math.max(4, Math.min(60, Number(batchCount.value || 20)))
  running.value = true
  try {
    const data = await request.post('/ops/review/batch', { count })
    const payload = data || {}
    const batchCode = payload.batchCode || ''
    const rate = formatPercent(valueOf((payload.metrics || {}), 'agreementRate'))
    ElMessage.success(
      `审核批次 ${batchCode || '已完成'} 共 ${payload.count || count} 笔：一致性 ${rate}，正在刷新评估结果`
    )
    if (batchCode) {
      batchFilter.value = batchCode
      query.batchCode = batchCode
      query.page = 1
    }
    optimizeResult.value = null
    await refreshAll()
  } finally {
    running.value = false
  }
}

async function handleBatchChange() {
  query.batchCode = batchFilter.value
  query.page = 1
  loading.value = true
  try {
    await loadConsistency()
    await loadRecords()
  } finally {
    loading.value = false
  }
}

function handleFilterChange() {
  query.page = 1
  loadRecords()
}

function handlePageChange(page) {
  query.page = Number(page || 1)
  loadRecords()
}

function handleSizeChange(size) {
  query.size = Number(size || 10)
  query.page = 1
  loadRecords()
}

async function handleOptimize() {
  optimizing.value = true
  try {
    const data = await request.post('/ops/review/optimize', { batchCode: batchFilter.value || 'all' })
    optimizeResult.value = data || {}
    if (optimizeResult.value.improved) {
      ElMessage.success('已生成优化建议：存在综合得分更优的候选策略，可点击「应用优化策略」生效')
    } else {
      ElMessage.info('已完成候选策略复盘：当前策略在一致性 / 自动化率 / 漏放率目标下已是最优')
    }
    await loadOptimizations()
  } finally {
    optimizing.value = false
  }
}

async function handleApply() {
  if (!canApply.value) {
    ElMessage.warning('当前没有更优策略（improved = false），无需应用优化策略')
    return
  }
  applying.value = true
  try {
    const data = await request.post('/ops/review/apply', {})
    const payload = data || {}
    policy.value = payload.policy || policy.value
    const record = payload.record || {}
    ElMessage.success(
      `优化策略已应用${record.code ? `（${record.code}）` : ''}：通过阈值 ${policy.value.approveThreshold ?? '-'}、` +
        `拒绝阈值 ${policy.value.rejectThreshold ?? '-'}、置信度门槛 ${policy.value.confidenceFloor ?? '-'}，` +
        '后续审核批次将使用新策略'
    )
    await Promise.all([loadPolicy(), loadOptimizations()])
    optimizeResult.value = null
  } finally {
    applying.value = false
  }
}

function openDrawer(row) {
  current.value = row || null
  drawerVisible.value = true
}

onMounted(() => {
  refreshAll()
})
</script>

<style scoped>
.fs-review__title-icon {
  vertical-align: -2px;
  margin-right: 6px;
  color: #1f5fd8;
}
.fs-review__note {
  margin-bottom: 16px;
}
.fs-review__note-body {
  line-height: 1.7;
  font-size: 13px;
}
.fs-review__field-label {
  font-size: 13px;
  color: var(--fs-text-secondary);
}
.fs-review__kpi {
  margin-top: 16px;
}
.fs-review__sub-title {
  font-size: 13px;
  font-weight: 600;
  color: var(--fs-text);
  margin-bottom: 10px;
}
.fs-review__sub-title--gap {
  margin-top: 18px;
}
.fs-review__row-gap {
  margin-top: 20px;
}
.fs-review__matrix-hit {
  display: inline-block;
  min-width: 26px;
  padding: 1px 8px;
  border-radius: 6px;
  background: var(--fs-primary-light);
  color: var(--fs-primary);
  font-weight: 600;
}
.fs-review__hint {
  margin-top: 8px;
  line-height: 1.7;
}
.fs-review__speedup {
  color: var(--fs-success);
}
.fs-review__diff {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 16px;
  margin-top: 20px;
}
@media (max-width: 1024px) {
  .fs-review__diff {
    grid-template-columns: minmax(0, 1fr);
  }
}
.fs-review__diff-card {
  padding: 14px 16px;
  border-radius: 10px;
  border: 1px solid var(--fs-border);
  background: #fbfcfe;
}
.fs-review__diff-card--danger {
  border-color: #f7c5c6;
  background: #fdf1f1;
  color: #c02a2f;
}
.fs-review__diff-card--warning {
  border-color: #ffdcae;
  background: #fff8ec;
  color: #b5761a;
}
.fs-review__diff-head {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 14px;
  font-weight: 600;
}
.fs-review__diff-head b {
  margin-left: auto;
  font-size: 18px;
}
.fs-review__diff-desc {
  margin-top: 8px;
  font-size: 12px;
  line-height: 1.7;
  color: var(--fs-text-secondary);
}
.fs-review__agreed {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  color: var(--fs-success);
}
.fs-review__disagreed {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  color: var(--fs-danger);
}
.fs-review__pagination {
  display: flex;
  justify-content: flex-end;
  margin-top: 14px;
}
.fs-review__confidence {
  display: flex;
  align-items: center;
  gap: 8px;
}
.fs-review__confidence :deep(.el-progress) {
  flex: 1;
}
.fs-review__confidence-text {
  color: var(--fs-text-secondary);
}
.fs-review__optimize-alert {
  margin-bottom: 14px;
}
.fs-review__point {
  font-size: 13px;
  line-height: 1.7;
}
.fs-review__trend-up {
  color: var(--fs-success);
  display: inline-flex;
  align-items: center;
  gap: 2px;
}
.fs-review__trend-down {
  color: var(--fs-danger);
  display: inline-flex;
  align-items: center;
  gap: 2px;
}
.fs-review__drawer {
  padding-bottom: 20px;
}
.fs-review__score {
  margin: 6px 0 10px;
}
.fs-review__score-text {
  font-size: 12px;
  color: var(--fs-text-secondary);
}
.fs-review__reason {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 8px 0;
  border-bottom: 1px dashed var(--fs-border);
  font-size: 13px;
}
.fs-review__reason:last-child {
  border-bottom: none;
}
.fs-review__reason-text {
  flex: 1;
}
</style>
