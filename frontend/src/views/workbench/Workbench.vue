<template>
  <div class="fs-page workbench">
    <header class="fs-page__header">
      <div><h1 class="fs-page__title">业务工作台</h1><p class="fs-page__subtitle">跨境交易，从原始数据到可追溯决策。</p></div>
      <div class="fs-toolbar__right"><el-button @click="historyOpen = true" :disabled="busy || !overview.runs?.length">历史流程</el-button><el-button @click="router.push('/ops/assistant' + (run ? '?run='+run.id : ''))">询问 AI</el-button><el-button type="primary" :loading="busy" :disabled="!run && (!selectedRows.length || !form.budgetId)" @click="run?.status==='completed'?replay():execute(false)">{{ run?.status==='completed'?'回放流程':'运行流程' }}</el-button></div>
    </header>

    <div v-if="loadError" class="wb-error" role="alert">工作台读取失败。<el-button text @click="load">重新加载</el-button></div>
    <section class="wb-summary" aria-label="数据资产概况">
      <button @click="router.push('/data')"><span>原始交易</span><strong>{{ number(overview.sourceCount) }}</strong><small>{{overview.sourceMode==='public'?'UCI真实公开交易':'项目仿真与自行导入'}}</small></button>
      <button @click="router.push('/data?tab=policies')"><span>政策条目</span><strong>{{ number(overview.policy?.total) }}</strong><small>已校对 {{ overview.policy?.verifiedCount ?? '—' }} 条</small></button>
      <button @click="router.push('/data?tab=protected')"><span>加密记录</span><strong>{{ number(overview.protectedCount) }}</strong><small>当前账号的处理结果</small></button>
    </section>

    <section class="fs-card" style="margin-bottom:24px">
      <div class="fs-card__header"><h2 class="fs-card__title">业务申报与材料</h2><div class="fs-toolbar__right"><el-button v-if="!run" :disabled="busy || selectedRows.length<2 || !form.budgetId" @click="createDeclaration">创建申报</el-button><template v-else><el-button :disabled="busy" @click="checkDeclaration">申报预检</el-button><el-button :disabled="busy" @click="showReport">生成核查报告</el-button></template></div></div>
      <div class="fs-card__body">
        <p v-if="!run" class="fs-muted">选取交易并填写处理设置后创建申报，再登记对应材料。</p>
        <template v-else>
          <div class="fs-toolbar" v-if="!stageDone('compliance')"><el-select v-model="materialKind" style="width:180px"><el-option v-for="(label,key) in materialKinds" :key="key" :value="key" :label="label"/></el-select><el-button :loading="materialBusy" :disabled="busy" @click="materialInput?.click()">上传材料</el-button><input hidden ref="materialInput" type="file" accept=".pdf,.txt,.csv" @change="uploadMaterial"/><span class="fs-muted">PDF / UTF-8 文本，单份不超过 2 MB</span></div>
          <el-table :data="run.materials || []" empty-text="尚未登记材料"><el-table-column prop="kindName" label="类型" width="145"/><el-table-column prop="filename" label="文件" min-width="180"/><el-table-column label="SHA-256" min-width="180"><template #default="{row}"><code :title="row.digest">{{row.digest.slice(0,20)}}…</code></template></el-table-column><el-table-column label="操作" width="90"><template #default="{row}"><el-button text @click="downloadMaterial(row)">下载</el-button></template></el-table-column></el-table>
          <p class="fs-muted">材料已收件不代表内容合法有效；上传材料及登记声明仍需人工审查。</p>
          <template v-if="declarationCheck"><el-alert :type="declarationCheck.passed?'success':'warning'" :closable="false" :title="declarationCheck.passed?'规则预检满足，可继续处理':stageDone('protect')?'当前预检需整改，请核对规则及材料':'申报待整改，尚未扣减隐私预算'"/><el-table :data="declarationCheck.checks"><el-table-column prop="name" label="核查项"/><el-table-column prop="actual" label="依据"/><el-table-column label="状态" width="100"><template #default="{row}">{{row.passed?'满足':'未满足'}}</template></el-table-column></el-table><div v-for="group in declarationCheck.rules || []" :key="group.sourceRegion"><h3>{{group.sourceRegion}} → {{declarationCheck.targetRegion}} · 规则执行</h3><el-table :data="group.checkedRules"><el-table-column prop="name" label="规则"/><el-table-column prop="result" label="结果" width="100"/><el-table-column prop="detail" label="命中依据" min-width="280"/></el-table></div></template>
        </template>
      </div>
    </section>
    <el-dialog v-model="reportOpen" title="数据处理与合规核查报告" width="min(960px,94vw)" append-to-body>
      <div v-if="reportData" style="max-height:65vh;overflow:auto;overflow-wrap:anywhere">
        <p class="fs-muted">{{reportData.frozen?'合规阶段快照':'当前申报预检'}} · {{reportData.runId}}</p>
        <el-alert :closable="false" :type="reportData.passed?'success':'warning'" :title="reportData.passed?'规则预检满足':'需整改，禁止继续处理'"/>
        <h3>1 申报材料</h3><el-table :data="reportData.materials" empty-text="未登记材料"><el-table-column prop="kindName" label="类型"/><el-table-column prop="filename" label="文件"/><el-table-column prop="size" label="字节数" width="90"/></el-table>
        <h3>2 校验与整改</h3><el-table :data="reportData.checks"><el-table-column prop="name" label="核查项"/><el-table-column label="结果" width="85"><template #default="{row}">{{row.passed?'满足':'未满足'}}</template></el-table-column><el-table-column label="依据或整改" min-width="200"><template #default="{row}">{{row.passed?row.actual:row.required}}</template></el-table-column></el-table>
        <h3>3 规则执行与适用条目</h3><div v-for="group in reportData.rules" :key="group.sourceRegion"><el-table :data="group.checkedRules"><el-table-column prop="name" label="规则"/><el-table-column prop="result" label="执行结果" width="100"/><el-table-column prop="detail" label="判断依据" min-width="200"/></el-table></div><p>{{reportData.policies.map(p=>p.code+' '+p.name).join('；')}}</p>
        <p class="fs-muted">材料收件及规则校验不构成法律意见或监管批准；文件内容及授权效力须人工审核。下载文件包含材料哈希、规则版本、保护阶段与耗时记录。</p>
        <details><summary>查看完整报告文本</summary><pre style="white-space:pre-wrap;overflow-wrap:anywhere;font:inherit;line-height:1.8">{{reportData.markdown}}</pre></details>
      </div>
      <template #footer><el-button @click="reportOpen=false">关闭</el-button><el-button type="primary" @click="downloadReport">下载报告</el-button></template>
    </el-dialog>
    <section class="wb-flow" :aria-busy="busy">
      <div class="wb-section-head"><h2>交易处理链路</h2><div v-if="run" class="wb-flow-actions"><span class="fs-mono">{{ run.id }}</span><el-button v-if="run.status==='completed'" text :disabled="busy" @click="replay">{{ replaying ? '停止回放' : '回放过程' }}</el-button></div><span v-else class="fs-muted">尚未创建流程</span></div>
      <div class="wb-pipeline" role="tablist" aria-label="处理阶段" @keydown="navigateStage">
        <button v-for="(step, i) in steps" :key="step.key" :class="['wb-node', {done: stageDone(step.key), active: activeStage === step.key || replayStage === step.key, selected: selected === step.key}]"
          :id="'stage-tab-'+step.key" role="tab" :tabindex="selected === step.key?0:-1" :aria-selected="selected === step.key" :aria-controls="'stage-detail'" @click="selected = step.key">
          <span class="wb-node__marker"><el-icon v-if="stageDone(step.key)"><Check /></el-icon><el-icon v-else><component :is="step.icon" /></el-icon></span>
          <strong>{{ step.title }}</strong><small>{{ replayStage === step.key ? '过程回放' : activeStage === step.key ? '处理中' : stageDone(step.key) ? duration(step.key) : '等待处理' }}</small>
          <span v-if="i < steps.length-1" class="wb-node__connector" aria-hidden="true"><i v-if="(busy && activeStage === step.key) || replayStage === step.key"></i></span>
        </button>
      </div>

      <div class="wb-stage-layout">
        <div id="stage-detail" class="wb-stage-detail" role="tabpanel" :aria-labelledby="'stage-tab-'+selected" tabindex="0">
          <div class="wb-section-head"><h3>{{ steps.find(s => s.key === selected)?.title }}</h3><span class="wb-state" :class="{complete: stageDone(selected)}">{{ stageDone(selected) ? '已完成' : '待执行' }}</span></div>
          <ProcessCanvas :stage="selected" :detail="detail" :running="selected===activeStage || selected===replayStage" :replay="replaying" :currency="publicationCurrency" :target="run?.config.targetRegion || form.targetRegion" />
          <details class="wb-evidence" :open="stageDone(selected)"><summary>{{ selected==='classify'?'字段明细':selected==='protect'?'加密与发布依据':selected==='compliance'?'合规要件':selected==='risk'?'初筛与模型依据':'存证详情' }}</summary>
          <template v-if="selected === 'classify'">
            <div v-if="detail.fields" class="wb-field-list"><div v-for="field in detail.fields" :key="field.key"><span>{{ field.name }}</span><code>{{ field.key }}</code><span :class="['wb-level', field.level.toLowerCase()]">{{ field.level }}</span></div></div>
            <div v-else class="wb-preview"><div v-for="f in previewFields" :key="f.key"><span>{{ f.name }}</span><code>{{ f.key }}</code><span :class="['wb-level', f.level.toLowerCase()]">{{ f.level }}</span></div><p class="fs-muted">按字段字典分级；执行后展示本批实际字段。</p></div>
          </template>
          <template v-else-if="selected === 'protect'">
            <div v-if="!detail.proofs" class="wb-crypto-lanes"><div><span class="wb-level p1">P1</span><strong>SM4 + Paillier</strong><span>身份与账户</span></div><div><span class="wb-level p2">P2</span><strong>AES-256-GCM</strong><span>金额与业务特征</span></div><div><span class="wb-level p3">P3</span><strong>AES-256-GCM</strong><span>交易属性</span></div></div>
            <template v-if="detail.publication"><div class="wb-encryption-proof" v-for="proof in detail.proofs || []" :key="proof.level"><span :class="['wb-level',proof.level.toLowerCase()]">{{ proof.level }}</span><span>{{ proof.length }} 字节 → {{ proof.cipher }}</span><code :title="proof.digest">{{ proof.digest.slice(0,16) }}…</code><small>{{ proof.keyProtection }}</small></div><div class="wb-publication"><span>加噪均值</span><strong>{{ number(detail.publication.value, 4) }}</strong><span>{{ publicationCurrency }}</span></div><dl class="wb-dl"><div><dt>本次 ε</dt><dd>{{ detail.publication.epsilon }}</dd></div><div><dt>噪声尺度</dt><dd>{{ number(detail.publication.noiseScale, 2) }}</dd></div><div><dt>剩余 ε</dt><dd>{{ detail.remaining }}</dd></div></dl></template>
            <p v-else class="wb-empty">运行后生成逐笔密文，并对统计出口加噪。</p>
            <el-collapse class="wb-disclosure"><el-collapse-item title="保护范围与统计口径" name="scope"><p>逐笔字段保留精确值并加密；仅公开裁剪范围内的金额均值做拉普拉斯发布，每次消耗 ε。固定样本量、替换一条记录为保护口径；不发布原始均值或实际噪声。推理在本地授权解密后进行。</p></el-collapse-item></el-collapse>
          </template>
          <template v-else-if="selected === 'compliance'">
            <template v-if="detail.checks"><div class="wb-check" v-for="c in detail.checks" :key="c.key"><el-icon :class="c.passed ? 'wb-positive' : 'wb-negative'"><component :is="c.passed ? 'CircleCheck' : 'CircleClose'" /></el-icon><div><strong>{{ c.name }}</strong><span>{{ c.required }}</span></div><span>{{ c.actual }}</span></div><div class="wb-policy-tags"><el-tag v-for="p in detail.policies" :key="p.code" type="info" :title="p.name">{{ p.code }}</el-tag></div><p class="fs-muted">{{ detail.scope }}</p></template>
            <div v-else class="wb-empty">依据数据来源与目的地区，核对授权、传输依据和影响评估。</div>
          </template>
          <template v-else-if="selected === 'risk'">
            <template v-if="detail.counts"><div class="wb-decision-counts"><div v-for="(title,key) in labels" :key="key"><span>{{ title }}</span><strong>{{ detail.counts[key] }}</strong></div></div><dl class="wb-dl"><div><dt>自动处理比例</dt><dd>{{ (detail.automationRate*100).toFixed(1) }}%</dd></div><div><dt>初筛模型</dt><dd>{{ detail.model.name }}</dd></div></dl><p class="fs-muted">{{ detail.scope }}</p></template>
            <div v-else class="wb-empty">模型先做批量初筛；仅低置信度记录进入人工复核。</div>
            <el-collapse class="wb-disclosure"><el-collapse-item title="模型训练与验证" name="model"><p>{{ overview.model?.scope }}</p><p v-if="overview.model?.kind!=='anomaly'">训练 {{ overview.model?.trainingRows }} 条，留出验证 {{ overview.model?.validationRows }} 条，AUC {{ overview.model?.validationAuc }}。特征：{{ overview.model?.features?.join('、') }}。</p><p v-if="overview.model?.kind==='anomaly'">真实订单拟合 {{overview.model.trainingRows}} 份，时间留出 {{overview.model.validationRows}} 份；留出告警率 {{(overview.model.validationAlertRate*100).toFixed(2)}}%。异常分位达到98%转人工，不把异常当成欺诈结论。</p><p v-else>自动结论要求置信度不低于80%；合规阻断优先。</p></el-collapse-item></el-collapse>
          </template>
          <template v-else>
            <template v-if="detail.hash"><div class="wb-proof"><el-icon><CircleCheck /></el-icon><h3>流程已存证</h3><code>{{ detail.hash }}</code></div><dl class="wb-dl"><div><dt>审计记录</dt><dd>#{{ detail.auditId }}</dd></div><div><dt>存证交易</dt><dd class="fs-mono">{{ detail.chainTxId }}</dd></div></dl><p class="fs-muted">{{ detail.scope }}</p></template>
            <div v-else class="wb-empty">记录流程与结论摘要，敏感原始字段不写入存证日志。</div>
          </template>
          </details>
        </div>

        <aside class="wb-config">
          <h3>处理设置</h3>
          <dl v-if="run" class="wb-dl"><div><dt>本批交易</dt><dd>{{ run.count }} 笔 · {{ run.config.currency }}</dd></div><div><dt>数据流转目的地</dt><dd>{{ overview.regions?.find(r=>r.value===run.config.targetRegion)?.label }}</dd></div><div><dt>统计发布</dt><dd>ε {{ run.config.epsilon }} · 裁剪 [{{ run.config.lower }}, {{ number(run.config.upper) }}]</dd></div><div><dt>演示凭证</dt><dd>{{ run.config.authorized?'已登记授权':'缺少处理授权' }}<br/>{{ run.config.transferBasis?'已登记传输依据':'缺少传输依据' }}<br/>{{ run.config.impactAssessment?'已登记影响评估':'缺少影响评估' }}</dd></div></dl>
          <el-form v-else label-position="top" :disabled="busy">
            <el-form-item label="交易数据"><el-button class="wb-select-data" @click="picker = true">{{ selectedRows.length ? `已选 ${selectedRows.length} 笔交易` : '选择原始交易' }}<el-icon><ArrowRight /></el-icon></el-button></el-form-item>
            <el-form-item label="数据流转目的地"><el-select v-model="form.targetRegion" @change="form.businessConfigId='' "><el-option v-for="r in overview.regions" :key="r.value" :value="r.value" :label="r.label" /></el-select></el-form-item>
            <el-form-item label="业务规则方案"><el-select v-model="form.businessConfigId" clearable placeholder="选择业务方案"><el-option v-for="b in businessPlans.filter(b=>b.region===form.targetRegion)" :key="b.id" :value="b.id" :disabled="!b.enabledCount" :label="b.summary+'（已启用 '+b.enabledCount+'/'+b.ruleCount+'）'" /></el-select></el-form-item>
            <div class="wb-config-pair"><el-form-item label="统计发布 ε"><el-input-number v-model="form.epsilon" :min=".01" :max="10" :step=".1" :precision="2" controls-position="right" /></el-form-item><el-form-item label="裁剪上界"><el-input-number v-model="form.upper" :min="1" :max="1e12" controls-position="right" /></el-form-item></div>
            <el-form-item label="隐私预算项目"><el-select v-model="form.budgetId" placeholder="选择项目"><el-option v-for="b in budgets" :key="b.id" :value="b.id" :label="`${b.project} · 剩余 ${b.remaining} ε`" /></el-select></el-form-item>
            <div class="wb-gates"><el-checkbox v-model="form.authorized">已登记处理授权</el-checkbox><el-checkbox v-model="form.transferBasis">已登记跨境传输依据</el-checkbox><el-checkbox v-model="form.impactAssessment">已登记影响评估</el-checkbox></div>
          </el-form>
          <p v-if="run?.status!=='completed'" class="fs-muted wb-consequence">运行会保存本批密文，并消耗 {{ run?.config.epsilon ?? form.epsilon }} ε；缺少合规凭证将阻断流转。</p>
          <p v-if="error" role="alert" class="wb-negative">{{ error }}</p>
          <el-button v-if="run?.status!=='completed'" class="wb-run" type="primary" :loading="busy" :disabled="run?.status === 'completed' || (!run && (!selectedRows.length || !form.budgetId))" @click="execute(false)">{{ run?.status === 'completed' ? '处理完成' : run ? '继续处理' : '运行完整流程' }}<el-icon v-if="!busy"><VideoPlay /></el-icon></el-button>
          <el-button v-if="run && !busy" class="wb-new" :type="run.status==='completed'?'primary':'default'" @click="reset">新建流程</el-button><el-button v-if="!busy && run?.status!=='completed'" text class="wb-new" :disabled="!run && (!selectedRows.length || !form.budgetId)" @click="execute(true)">单步执行</el-button>
        </aside>
      </div>
    </section>

    <section v-if="run?.decisions?.length" class="wb-results">
      <div class="wb-section-head"><h2>初筛结果 <span class="fs-muted">{{ filteredDecisions.length }} 笔</span></h2><div><el-button @click="router.push('/data?tab=protected')">查看密文</el-button></div></div>
      <el-radio-group v-model="decisionFilter" size="small"><el-radio-button value="all">全部</el-radio-button><el-radio-button v-for="(title,key) in labels" :key="key" :value="key">{{ title }}</el-radio-button></el-radio-group>
      <el-table :data="filteredDecisions" class="wb-result-table"><el-table-column prop="code" label="交易编号" min-width="170" /><el-table-column :label="run.decisions[0]?.scoreKind==='anomaly'?'异常分位':'风险概率'" width="150" align="right"><template #default="{row}"><span class="wb-score">{{row.riskScore==null?'—':(row.riskScore*100).toFixed(1)+'%'}}<i :style="{width:row.riskScore*100+'%'}"></i></span></template></el-table-column><el-table-column label="置信度" width="110" align="right"><template #default="{row}">{{ row.confidence==null?'—':(row.confidence*100).toFixed(1)+'%' }}</template></el-table-column><el-table-column label="处理结论" width="145"><template #default="{row}"><span :class="['wb-verdict',row.finalDecision]">{{ row.review ? '复核'+(row.finalDecision === 'approve' ? '通过' : '拒绝') : labels[row.finalDecision] }}</span></template></el-table-column><el-table-column prop="reason" label="依据" min-width="230" /><el-table-column label="操作" width="85"><template #default="{row}"><el-button text @click="reviewing = row">{{ row.finalDecision === 'manual' ? '复核' : '详情' }}</el-button></template></el-table-column></el-table>
    </section>

    <el-dialog v-model="picker" title="选择原始交易" width="min(940px, 94vw)" @opened="loadSources">
      <div class="fs-toolbar"><el-select v-if="overview.sourceMode==='public'" v-model="sourceScope" style="width:180px" @change="changeSourceScope"><el-option label="电商零售订单" value="public"/><el-option label="真实银行流水" value="bank"/><el-option label="自行导入记录" value="imports"/></el-select><el-input v-model="sourceQuery" placeholder="交易编号或商户" clearable @keyup.enter="loadSources" style="width:240px"/><el-select v-model="sourceRegion" clearable placeholder="来源地区" @change="loadSources" style="width:160px"><el-option v-for="r in overview.regions" :key="r.value" :value="r.value" :label="r.label" /></el-select><el-button @click="loadSources">查询</el-button><el-button @click="chooseCurrent">选取当前页</el-button></div>
      <p class="fs-muted">仅同币种交易可合并统计，最多选取 100 笔。{{overview.sourceMode==='public'?'公开库保留原始明细、来源与汇总记录。':'内置交易为项目仿真数据。'}}</p>
      <el-table ref="sourceTable" :data="sourceRows" row-key="key" height="350" v-loading="sourceBusy" @selection-change="selectionChanged"><el-table-column type="selection" :reserve-selection="true" width="44"/><el-table-column prop="code" label="交易编号" min-width="160"/><el-table-column prop="merchantCode" label="商户" width="130"/><el-table-column label="金额" width="145" align="right"><template #default="{row}">{{ number(row.amount,2) }} {{ row.currency }}</template></el-table-column><el-table-column prop="region" label="来源" width="75"/><el-table-column prop="origin" label="数据来源" min-width="150"/></el-table>
      <el-pagination layout="prev, pager, next, total" :total="sourceTotal" :page-size="20" v-model:current-page="sourcePage" @current-change="loadSources"/>
      <template #footer><el-button @click="picker = false">取消</el-button><el-button type="primary" :disabled="pendingRows.length < 2 || pendingRows.length > 100" @click="confirmSelection">使用 {{ pendingRows.length }} 笔交易</el-button></template>
    </el-dialog>
    <el-drawer v-model="historyOpen" title="历史流程" size="min(480px, 95vw)"><button class="wb-history-row" v-for="r in overview.runs" :key="r.id" @click="openRun(r.id); historyOpen = false"><strong>{{ r.id }}</strong><span>{{ r.count }} 笔 · {{ r.stages.length }}/5 阶段</span><small>{{ r.createdAt }}</small></button></el-drawer>
    <el-drawer :model-value="Boolean(reviewing)" @close="reviewing = null; reviewNote = ''" title="审核依据" size="min(480px, 95vw)">
      <template v-if="reviewing"><h3 class="fs-mono">{{ reviewing.code }}</h3><p>{{ reviewing.reason }}</p><div class="wb-factor" v-for="f in reviewing.factors" :key="f.name"><span>{{ f.name }}</span><strong>{{ f.contribution }}</strong></div><p class="fs-muted">{{reviewing.factorBasis || '数值为模型对数几率贡献，不是归因因果证明。'}}</p><template v-if="reviewing.finalDecision === 'manual'"><el-input v-model="reviewNote" type="textarea" :rows="4" placeholder="填写复核依据（4–300 字）" :maxlength="300"/><div class="wb-review-actions"><el-button :loading="reviewBusy" @click="review('reject')">复核拒绝</el-button><el-button type="primary" :loading="reviewBusy" @click="review('approve')">复核通过</el-button></div></template><p v-if="reviewing.review">{{ reviewing.review.actor }}：{{ reviewing.review.note }}</p></template>
    </el-drawer>
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, ref, reactive, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { workbenchApi, budgetApi, complianceApi } from '@/api'
import { useUserStore } from '@/store/user'
import ProcessCanvas from '@/components/ProcessCanvas.vue'
const router=useRouter(), route=useRoute(), user=useUserStore()
const overview=ref({}), budgets=ref([]), run=ref(null), busy=ref(false), loadError=ref(false), error=ref(''), selected=ref('classify'), activeStage=ref('')
const selectedRows=ref([]), picker=ref(false), historyOpen=ref(false), sourceRows=ref([]), sourceTotal=ref(0), sourcePage=ref(1), sourceQuery=ref(''),sourceScope=ref('public'), sourceRegion=ref(''), sourceBusy=ref(false), pendingRows=ref([]), sourceTable=ref(null)
const decisionFilter=ref('all'), reviewing=ref(null), reviewNote=ref(''), reviewBusy=ref(false)
const businessPlans=ref([])
const form=reactive({targetRegion:'EU',businessConfigId:'',epsilon:1,lower:0,upper:1000000,budgetId:null,authorized:false,transferBasis:false,impactAssessment:false})
const materialKinds={authorization:'处理授权',basis:'跨境传输依据',assessment:'影响评估'},materialKind=ref('authorization'),materialInput=ref(null),materialBusy=ref(false),declarationCheck=ref(null),reportOpen=ref(false),reportData=ref(null)
async function createDeclaration(){if(busy.value)return;busy.value=true;try{run.value=await workbenchApi.create({...form,keys:selectedRows.value.map(r=>r.key)});localStorage.setItem(storageKey.value,run.value.id);declarationCheck.value=null}catch{}finally{busy.value=false}}
async function uploadMaterial(event){const file=event.target.files?.[0],id=run.value?.id;if(!file||!id||busy.value)return;materialBusy.value=true;try{const result=await workbenchApi.material(id,materialKind.value,file);if(run.value?.id===id){run.value=result;declarationCheck.value=null;ElMessage.success('材料已登记')}}catch{}finally{materialBusy.value=false;event.target.value=''}}
async function checkDeclaration(){const id=run.value?.id,version=run.value?.version,epoch=openingRun;if(!id||materialBusy.value)return;try{const result=await workbenchApi.precheck(id);if(openingRun===epoch&&run.value?.id===id&&run.value?.version===version)declarationCheck.value=result}catch{}}
async function showReport(){const id=run.value?.id,version=run.value?.version,epoch=openingRun;if(!id||materialBusy.value)return;try{const result=await workbenchApi.report(id);if(openingRun===epoch&&run.value?.id===id&&run.value?.version===version){reportData.value=result;reportOpen.value=true}}catch{}}
function saveBlob(blob,name){const url=URL.createObjectURL(blob),a=document.createElement('a');a.href=url;a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000)}
function downloadReport(){if(reportData.value)saveBlob(new Blob(['\ufeff'+reportData.value.markdown],{type:'text/markdown;charset=utf-8'}),'FedShield核查报告-'+run.value.id+'.md')}
async function downloadMaterial(row){try{const response=await workbenchApi.downloadMaterial(run.value.id,row.id);saveBlob(response.data,row.filename)}catch{}}
const labels={approve:'自动通过',reject:'自动拒绝',manual:'待人工复核',blocked:'合规阻断'}
const steps=[{key:'classify',title:'字段分级',icon:'Grid'},{key:'protect',title:'加密与加噪',icon:'Lock'},{key:'compliance',title:'跨境合规',icon:'DocumentChecked'},{key:'risk',title:'智能初筛',icon:'Cpu'},{key:'audit',title:'结果存证',icon:'Connection'}]
const previewFields=[{key:'merchantCode',name:'商户标识',level:'P1'},{key:'amount',name:'交易金额',level:'P2'},{key:'currency',name:'币种',level:'P3'},{key:'region',name:'来源地区',level:'P3'}]
function navigateStage(event){if(!['ArrowLeft','ArrowRight','Home','End'].includes(event.key))return;event.preventDefault();const index=steps.findIndex(s=>s.key===selected.value);const next=event.key==='Home'?0:event.key==='End'?steps.length-1:(index+(event.key==='ArrowRight'?1:-1)+steps.length)%steps.length;selected.value=steps[next].key;event.currentTarget.querySelectorAll('[role=tab]')[next]?.focus()}
const detail=computed(()=>run.value?.stages.find(s=>s.key===selected.value)?.detail || {})
const filteredDecisions=computed(()=>(run.value?.decisions || []).filter(r=>decisionFilter.value==='all'||r.finalDecision===decisionFilter.value))
const publicationCurrency=computed(()=>run.value?.config.currency || selectedRows.value[0]?.currency || '')
const storageKey=computed(()=>'fedshield_workflow_'+user.user?.username)
let disposed=false, replayTimer=null
const replaying=ref(false),replayStage=ref('')
function replay(){if(replayTimer){clearInterval(replayTimer);replayTimer=null;replaying.value=false;replayStage.value='';return}let i=0;replaying.value=true;selected.value=steps[0].key;replayStage.value=steps[0].key;replayTimer=setInterval(()=>{i++;if(i>=steps.length){clearInterval(replayTimer);replayTimer=null;replaying.value=false;replayStage.value='';return}selected.value=steps[i].key;replayStage.value=steps[i].key},1600)}
const number=(v, digits=0)=>v===undefined?'—':Number(v).toLocaleString('zh-CN',{minimumFractionDigits:digits,maximumFractionDigits:digits})
const stageDone=key=>Boolean(run.value?.stages.some(s=>s.key===key))
const duration=key=>`${number(run.value?.stages.find(s=>s.key===key)?.durationMs,1)} ms`
async function load(){loadError.value=false;try{const [o,b,plans]=await Promise.all([workbenchApi.overview(),budgetApi.items(),complianceApi.businessPlans()]);overview.value=o;budgets.value=b;businessPlans.value=plans;if(!form.budgetId)form.budgetId=b[0]?.id}catch{loadError.value=true}}
let sourceLoad=0
async function loadSources(){const ticket=++sourceLoad;sourceBusy.value=true;try{const d=await workbenchApi.sources({page:sourcePage.value,size:20,q:sourceQuery.value,region:sourceRegion.value,scope:sourceScope.value});if(ticket!==sourceLoad)return;sourceRows.value=d.items;sourceTotal.value=d.total}catch{ElMessage.error('交易读取失败，请重试')}finally{if(ticket===sourceLoad)sourceBusy.value=false}}
async function changeSourceScope(){pendingRows.value=[];sourcePage.value=1;sourceTable.value?.clearSelection();await loadSources()}
function selectionChanged(rows){pendingRows.value=rows}
function chooseCurrent(){sourceRows.value.forEach(r=>sourceTable.value?.toggleRowSelection(r,true))}
function confirmSelection(){if(new Set(pendingRows.value.map(r=>r.currency)).size>1){ElMessage.warning('请选择同一币种，避免不同币种直接求均值');return}selectedRows.value=[...pendingRows.value];picker.value=false}
let openingRun=0
async function openRun(id){if(busy.value || materialBusy.value)return;const request=++openingRun;declarationCheck.value=null;reportData.value=null;reportOpen.value=false;try{const result=await workbenchApi.run(id);if(request!==openingRun)return;run.value=result;Object.assign(form,run.value.config);selected.value=run.value.stages.at(-1)?.key || 'classify';localStorage.setItem(storageKey.value,id)}catch{error.value='历史流程读取失败，请重新选择。'}}
async function execute(single=false){
  if(busy.value || materialBusy.value)return
  error.value=''
  if(!stageDone('protect') && (!single || stageDone('classify'))){try{await ElMessageBox.confirm(`本次将发布加噪均值并扣减 ${run.value?.config.epsilon ?? form.epsilon} ε。已扣减的隐私预算不能撤销。`,'运行交易流程',{confirmButtonText:'确认运行',cancelButtonText:'取消'})}catch{return}}
  busy.value=true
  try{
    if(!run.value){run.value=await workbenchApi.create({...form,keys:selectedRows.value.map(r=>r.key)});localStorage.setItem(storageKey.value,run.value.id)}
    const executionId=run.value.id
    for(const step of steps){if(disposed)break;if(stageDone(step.key))continue;activeStage.value=step.key;selected.value=step.key;const data=await workbenchApi.advance(executionId,step.key);if(disposed)break;run.value=data;if(single)break}
    if(!disposed)await load()
  }catch(e){error.value=e.message || '处理未完成，可核对后继续；已完成阶段不会重复扣费。'}finally{busy.value=false;activeStage.value=''}
}
function reset(){if(busy.value||materialBusy.value)return;++openingRun;if(replayTimer){clearInterval(replayTimer);replayTimer=null;replaying.value=false;replayStage.value=''}run.value=null;declarationCheck.value=null;reportData.value=null;selected.value='classify';error.value='';decisionFilter.value='all';localStorage.removeItem(storageKey.value);router.replace('/workbench')}
async function review(decision){if(reviewBusy.value)return;if(reviewNote.value.trim().length<4){ElMessage.warning('请填写至少 4 字的复核依据');return}try{await ElMessageBox.confirm(`将交易 ${reviewing.value.code} 的复核结论登记为“${decision==='approve'?'通过':'拒绝'}”，并写入审计记录。该原型不会发送真实支付指令。`,'确认复核',{confirmButtonText:'登记结论',cancelButtonText:'取消'})}catch{return}reviewBusy.value=true;try{run.value=await workbenchApi.review(run.value.id,{code:reviewing.value.code,decision,note:reviewNote.value});reviewing.value=null;reviewNote.value=''}catch{}finally{reviewBusy.value=false}}
watch(()=>route.query.run,id=>{if(id&&!busy.value)openRun(String(id))})
onMounted(async()=>{await load();const id=route.query.run || localStorage.getItem(storageKey.value);if(id)await openRun(String(id))})
onBeforeUnmount(()=>{disposed=true;if(replayTimer)clearInterval(replayTimer)})
</script>
