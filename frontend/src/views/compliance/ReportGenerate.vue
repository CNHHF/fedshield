<template>
  <div class="fs-page">
    <div class="fs-page__header">
      <div>
        <h2 class="fs-page__title">生成合规报告</h2>
        <p class="fs-page__subtitle">
          按监管要求生成跨境数据合规报告：报告内容从合规校验记录、隐私计算任务与权限授权数据中自动汇总，
          生成结果可在「合规报告管理」中预览与下载。
        </p>
      </div>
      <div class="fs-toolbar" style="margin-bottom: 0">
        <el-button :icon="RefreshLeft" @click="onReset">重置</el-button>
        <el-button type="primary" :icon="DocumentAdd" :loading="loading" @click="onGenerate">生成报告</el-button>
      </div>
    </div>

    <el-row :gutter="16">
      <el-col :xs="24" :lg="16">
        <div class="fs-card">
          <div class="fs-card__header">
            <span class="fs-card__title">报告参数</span>
            <span class="fs-muted">对应接口 POST /compliance/reports</span>
          </div>
          <div class="fs-card__body">
            <el-form ref="formRef" :model="form" :rules="formRules" label-width="110px">
              <el-form-item label="报告类型" prop="type">
                <el-select
                  v-model="form.type"
                  placeholder="选择监管要求的报告类型"
                  style="width: 100%"
                  filterable
                  @change="onTypeChange"
                >
                  <el-option
                    v-for="item in reportTypeOptions"
                    :key="item.code"
                    :label="`${item.name}（${item.regulation || item.code}）`"
                    :value="item.code"
                  />
                </el-select>
                <div class="fs-muted" style="margin-top: 4px">
                  报告类型来自后端元数据 /meta/report-types，随监管要求更新自动同步。
                </div>
              </el-form-item>

              <el-form-item label="报告时间范围" prop="period">
                <el-date-picker
                  v-model="form.period"
                  type="daterange"
                  range-separator="至"
                  start-placeholder="开始日期"
                  end-placeholder="结束日期"
                  value-format="YYYY-MM-DD"
                  style="width: 100%"
                  @change="onPeriodChange"
                />
                <div class="period-tip">
                  <span class="fs-muted">最长支持 1 年，超出时后端会自动分段生成并合并统计口径。</span>
                  <el-tag v-if="periodTooLong" type="warning" size="small" effect="plain" style="margin-left: 8px">
                    当前跨度 {{ periodDays }} 天
                  </el-tag>
                </div>
              </el-form-item>

              <el-form-item label="适用地区" prop="regions">
                <el-select v-model="form.regions" multiple placeholder="选择报告覆盖的地区" style="width: 100%">
                  <el-option v-for="item in REGION_OPTIONS" :key="item.value" :label="item.label" :value="item.value" />
                </el-select>
              </el-form-item>

              <el-form-item label="高级选项">
                <div class="advanced-head">
                  <el-button text type="primary" @click="showAdvanced = !showAdvanced">
                    {{ showAdvanced ? '收起高级选项' : '展开高级选项' }}
                    <el-icon><component :is="showAdvanced ? 'ArrowUp' : 'ArrowDown'" /></el-icon>
                  </el-button>
                  <span class="fs-muted">已选 {{ advancedCount }} / 4 项附加章节</span>
                </div>
                <el-collapse-transition>
                  <div v-show="showAdvanced" class="advanced-body">
                    <el-checkbox v-model="form.advanced.includeDpia">
                      包含 DPIA 评估
                      <span class="advanced-desc">数据保护影响评估的执行记录与风险结论</span>
                    </el-checkbox>
                    <el-checkbox v-model="form.advanced.includeScc">
                      包含 SCC 条款执行情况
                      <span class="advanced-desc">标准合同条款签署、传输链路与第三方接收方清单</span>
                    </el-checkbox>
                    <el-checkbox v-model="form.advanced.includeSubjectRights">
                      包含数据主体权利响应
                      <span class="advanced-desc">访问/更正/删除/可携带等请求的受理与响应时效</span>
                    </el-checkbox>
                    <el-checkbox v-model="form.advanced.includePrivacyBudget">
                      包含隐私预算消耗记录
                      <span class="advanced-desc">各项目 ε 预算消耗、剩余额度与超限告警</span>
                    </el-checkbox>
                  </div>
                </el-collapse-transition>
              </el-form-item>

              <el-form-item>
                <el-button type="primary" :icon="DocumentAdd" :loading="loading" @click="onGenerate">生成报告</el-button>
                <el-button @click="onReset">重置</el-button>
              </el-form-item>
            </el-form>
          </div>
        </div>
      </el-col>

      <!-- 右侧：报告类型说明 -->
      <el-col :xs="24" :lg="8">
        <div class="fs-card">
          <div class="fs-card__header">
            <span class="fs-card__title">报告类型说明</span>
            <el-tag v-if="currentTypeName" size="small" effect="plain">{{ currentTypeName }}</el-tag>
          </div>
          <div class="fs-card__body">
            <div class="type-desc">
              <div class="type-desc__row">
                <span class="type-desc__label">适用场景</span>
                <span>{{ currentTypeInfo.scene }}</span>
              </div>
              <div class="type-desc__row">
                <span class="type-desc__label">必需要件</span>
                <ul class="type-desc__list">
                  <li v-for="(item, index) in currentTypeInfo.requirements" :key="index">{{ item }}</li>
                </ul>
              </div>
              <div class="type-desc__row">
                <span class="type-desc__label">核心要求</span>
                <ul class="type-desc__list">
                  <li v-for="(item, index) in currentTypeInfo.core" :key="index">{{ item }}</li>
                </ul>
              </div>
              <div class="type-desc__row">
                <span class="type-desc__label">建议频次</span>
                <span>{{ currentTypeInfo.frequency }}</span>
              </div>
            </div>

            <el-divider content-position="left">全部报告类型</el-divider>
            <div class="type-list">
              <div
                v-for="item in reportTypeOptions"
                :key="item.code"
                class="type-list__item"
                :class="{ 'type-list__item--active': item.code === form.type }"
                @click="form.type = item.code"
              >
                <div class="type-list__name">{{ item.name }}</div>
                <div class="type-list__meta fs-muted">{{ item.regulation || '-' }} · {{ item.desc || '暂无说明' }}</div>
              </div>
            </div>
          </div>
        </div>
      </el-col>
    </el-row>
  </div>
</template>

<script setup>
/**
 * 生成合规报告（对应设计文档图 19 / 图 20）
 *
 * 关键交互：
 * 1. 时间范围限制最长 1 年：选择超过 365 天时给出 warning 提示，
 *    但仍允许提交（后端会自动分段生成），避免直接阻断合规人员的长周期报送需求。
 * 2. 高级选项用 v-show + el-collapse-transition 折叠，默认收起，保持表单简洁。
 * 3. 右侧「报告类型说明」为前端字典，按所选类型的 code 匹配，
 *    匹配不到时按报告名称关键字兜底，保证国际化/后端改码时仍有中文说明。
 */
import { computed, onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { DocumentAdd, RefreshLeft } from '@element-plus/icons-vue'
import { complianceApi } from '@/api'
import { useAppStore } from '@/store/app'

const router = useRouter()
const appStore = useAppStore()

const loading = ref(false)
const formRef = ref(null)
const showAdvanced = ref(false)

const form = reactive({
  type: '',
  period: [],
  regions: [],
  advanced: {
    includeDpia: true,
    includeScc: true,
    includeSubjectRights: false,
    includePrivacyBudget: false
  }
})

const formRules = {
  type: [{ required: true, message: '请选择报告类型', trigger: 'change' }],
  period: [{ required: true, type: 'array', message: '请选择报告时间范围', trigger: 'change' }],
  regions: [{ required: true, type: 'array', min: 1, message: '请至少选择一个适用地区', trigger: 'change' }]
}

const REGION_OPTIONS = [
  { value: 'CN', label: '中国' },
  { value: 'EU', label: '欧盟' },
  { value: 'US', label: '美国' },
  { value: 'SG', label: '新加坡' },
  { value: 'SEA', label: '东南亚' },
  { value: 'ME', label: '中东' },
  { value: 'AF', label: '非洲' },
  { value: 'GLOBAL', label: '全球' }
]

/** 报告类型中文说明字典：键为后端报告类型 code，另按名称关键字兜底匹配 */
const TYPE_INFO = {
  'GDPR': {
    scene: '面向欧盟 EDPB 及欧盟境内数据主体，说明跨境传输个人数据的合法性基础与保障措施。',
    requirements: ['合法性基础（SCC / BCR / 充分性认定）', 'DPIA 评估结论', '数据主体权利响应记录', '处理活动记录 RoPA'],
    core: ['第 44-49 条跨境传输合规', '数据最小化与目的限制', '72 小时内数据泄露通报', 'DPO 联系方式与投诉渠道'],
    frequency: '年度报告；发生重大数据事件时 72 小时内补充报送'
  },
  'PIPL': {
    scene: '面向中国网信部门，说明个人信息出境活动的安全评估、标准合同或认证路径的落实情况。',
    requirements: ['出境安全评估或标准合同备案', '个人信息保护影响评估', '单独同意记录', '境内存储与本地化说明'],
    core: ['告知—同意与单独同意', '最小必要原则', '关键信息基础设施数据本地化', '个人信息保护负责人信息'],
    frequency: '年度报告；出境情形变化时重新评估'
  },
  'CCPA': {
    scene: '面向美国加州隐私保护局（CPPA），说明加州居民个人信息的收集、共享与出售情况。',
    requirements: ['消费者权利请求受理记录', '信息类别与来源清单', '第三方共享/出售清单', '不歧视声明'],
    core: ['知情权与删除权响应（45 天内）', 'Do Not Sell/Share 链接', '敏感个人信息限制使用', '12 个月数据留存口径'],
    frequency: '每 12 个月更新一次指标披露'
  },
  'FATF': {
    scene: '面向反洗钱监管与金融情报机构，说明跨境支付业务的可疑交易监测与客户尽职调查执行情况。',
    requirements: ['KYC/CDD 记录', '可疑交易报告（STR）统计', '制裁名单筛查日志', '受益所有人识别记录'],
    core: ['风险为本的客户分级', '大额与可疑交易阈值监测', 'OFAC/UN 名单实时筛查', '交易记录 5 年留存'],
    frequency: '季度或年度报送，按属地监管要求'
  },
  // 键与后端 compliance/report.py 的 REPORT_TYPES code 保持一致（Schrems II 为 SCHREMS_II）
  'SCHREMS_II': {
    scene: '面向欧盟监管机构，针对 Schrems II 判决要求补充传输影响评估（TIA）与补充保障措施。',
    requirements: ['传输影响评估（TIA）', '目的地法律环境分析', '补充技术措施（端到端加密/假名化）', '政府访问请求披露统计'],
    core: ['第三国法律与政府访问风险', '补充措施有效性验证', 'SCC 附加条款执行', '传输链路加密与密钥管辖权说明'],
    frequency: '年度复审；法律环境变化时即时更新'
  }
}

/** 关键字兜底：后端 code 变更或新增类型时，尽量复用中文说明 */
const TYPE_KEYWORDS = [
  { keys: ['gdpr', 'edpb'], code: 'GDPR' },
  { keys: ['pipl', '个人信息保护法', '中国'], code: 'PIPL' },
  { keys: ['ccpa', 'cpra', '加州'], code: 'CCPA' },
  { keys: ['fatf', '反洗钱', 'aml'], code: 'FATF' },
  { keys: ['schrems', 'tia', '传输影响评估'], code: 'SCHREMS_II' }
]

const FALLBACK_INFO = {
  scene: '请结合报告类型的监管归属，确认报送对象与覆盖的数据处理活动范围。',
  requirements: ['数据处理活动清单', '合规校验记录', '数据主体权利响应记录'],
  core: ['数据出境合法性基础', '加密与脱敏措施', '审计留痕与存证'],
  frequency: '按属地监管要求定期报送'
}

const reportTypeOptions = computed(() => appStore.reportTypes ?? [])
const currentTypeName = computed(
  () => reportTypeOptions.value.find((item) => item.code === form.type)?.name || ''
)

const currentTypeInfo = computed(() => {
  if (!form.type) return FALLBACK_INFO
  if (TYPE_INFO[form.type]) return TYPE_INFO[form.type]
  const selected = reportTypeOptions.value.find((item) => item.code === form.type)
  const text = `${form.type} ${selected?.name || ''} ${selected?.regulation || ''}`.toLowerCase()
  const hit = TYPE_KEYWORDS.find((item) => item.keys.some((key) => text.includes(key.toLowerCase())))
  return hit ? TYPE_INFO[hit.code] : FALLBACK_INFO
})

const advancedCount = computed(
  () => Object.values(form.advanced ?? {}).filter(Boolean).length
)

const periodDays = computed(() => {
  const [start, end] = form.period ?? []
  if (!start || !end) return 0
  const startTime = new Date(String(start).replace(' ', 'T')).getTime()
  const endTime = new Date(String(end).replace(' ', 'T')).getTime()
  if (Number.isNaN(startTime) || Number.isNaN(endTime)) return 0
  return Math.round((endTime - startTime) / 86400000) + 1
})

const periodTooLong = computed(() => periodDays.value > 365)

function onPeriodChange() {
  if (periodTooLong.value) {
    ElMessage.warning('超过 1 年将自动分段生成')
  }
}

function onTypeChange() {
  // 切换类型时提示该报告的核心要求，减少选错类型的概率
  if (currentTypeInfo.value !== FALLBACK_INFO) {
    ElMessage.info(`已选择「${currentTypeName.value || form.type}」，报告将包含 ${currentTypeInfo.value.core.length} 项核心要求章节`)
  }
}

async function onGenerate() {
  if (!formRef.value) return
  try {
    await formRef.value.validate()
  } catch (error) {
    ElMessage.warning('请先补全带 * 的必填项')
    return
  }
  const [periodStart, periodEnd] = form.period ?? []
  loading.value = true
  try {
    await complianceApi.createReport({
      type: form.type,
      periodStart,
      periodEnd,
      regions: form.regions ?? [],
      advanced: {
        includeDpia: Boolean(form.advanced.includeDpia),
        includeScc: Boolean(form.advanced.includeScc),
        includeSubjectRights: Boolean(form.advanced.includeSubjectRights),
        includePrivacyBudget: Boolean(form.advanced.includePrivacyBudget)
      }
    })
    ElMessage.success('报告已提交生成，请在报告管理中查看进度')
    router.push('/compliance/reports')
  } catch (error) {
    // 请求拦截器已统一提示
  } finally {
    loading.value = false
  }
}

function onReset() {
  form.type = reportTypeOptions.value[0]?.code || ''
  form.period = []
  form.regions = []
  form.advanced.includeDpia = true
  form.advanced.includeScc = true
  form.advanced.includeSubjectRights = false
  form.advanced.includePrivacyBudget = false
  showAdvanced.value = false
  formRef.value?.clearValidate()
  ElMessage.info('表单已重置')
}

async function load() {
  loading.value = true
  try {
    await appStore.loadMeta()
    if (!form.type) form.type = reportTypeOptions.value[0]?.code || ''
  } catch (error) {
    // 元数据失败时保留空下拉，用户可稍后刷新重试
  } finally {
    loading.value = false
  }
}

onMounted(load)
</script>

<style scoped>
.period-tip {
  margin-top: 4px;
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 4px;
}
.advanced-head {
  display: flex;
  align-items: center;
  gap: 10px;
}
.advanced-body {
  width: 100%;
  margin-top: 4px;
  padding: 10px 14px;
  border: 1px solid var(--fs-border);
  border-radius: 8px;
  background: #fbfcfe;
}
.advanced-body .el-checkbox {
  display: flex;
  align-items: center;
  height: auto;
  margin-bottom: 8px;
  white-space: normal;
}
.advanced-desc {
  margin-left: 8px;
  font-size: 12px;
  color: var(--fs-text-secondary);
}
.type-desc__row {
  display: flex;
  gap: 10px;
  font-size: 13px;
  line-height: 1.7;
  padding: 6px 0;
}
.type-desc__label {
  flex: 0 0 64px;
  color: var(--fs-text-secondary);
}
.type-desc__list {
  margin: 0;
  padding-left: 18px;
}
.type-list {
  max-height: 260px;
  overflow-y: auto;
}
.type-list__item {
  padding: 8px 10px;
  border: 1px solid var(--fs-border);
  border-radius: 8px;
  cursor: pointer;
  transition: border-color 0.15s ease, background 0.15s ease;
}
.type-list__item + .type-list__item {
  margin-top: 8px;
}
.type-list__item:hover {
  border-color: var(--fs-primary);
}
.type-list__item--active {
  border-color: var(--fs-primary);
  background: var(--fs-primary-light);
}
.type-list__name {
  font-size: 13px;
  font-weight: 600;
}
.type-list__meta {
  margin-top: 2px;
}
</style>
