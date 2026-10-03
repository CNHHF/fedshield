
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
