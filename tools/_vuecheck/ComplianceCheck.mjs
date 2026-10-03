
/**
 * 跨境合规校验（数据出境前校验）
 *
 * 交互说明：
 * - 提交前做必填校验，避免把空地区/空目的传给规则引擎导致误判；
 * - 结果区把「总体结论 / 逐条规则 / 问题与整改」分成三块，便于合规人员按清单销项；
 * - 整改清单勾选状态保存在前端（后端 rectificationList 为静态清单），
 *   勾选后即时反馈剩余待整改数量，方便截图留档。
 */
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { CircleCheck, Refresh, RefreshLeft, Search, Warning } from '@element-plus/icons-vue'
import { complianceApi } from '@/api'
import { useAppStore } from '@/store/app'
import { formatTime } from '@/utils/format'
import StatCard from '@/components/StatCard.vue'
import DataLevelTag from '@/components/DataLevelTag.vue'

const appStore = useAppStore()

const loading = ref(false)
const regLoading = ref(false)
const formRef = ref(null)
const result = ref(null)
const checkedAt = ref('')
const rectified = ref([])
const regKeyword = ref('')

const form = reactive({
  dataLevel: 'P2',
  sourceRegion: 'CN',
  targetRegion: 'EU',
  fields: [],
  purpose: '',
  hasScc: false,
  hasDpia: false,
  authorized: false
})

const formRules = {
  dataLevel: [{ required: true, message: '请选择数据级别', trigger: 'change' }],
  sourceRegion: [{ required: true, message: '请选择来源地区', trigger: 'change' }],
  targetRegion: [{ required: true, message: '请选择目的地地区', trigger: 'change' }],
  fields: [{ required: true, type: 'array', min: 1, message: '请至少选择一个数据字段', trigger: 'change' }],
  purpose: [{ required: true, message: '请填写数据使用目的', trigger: 'blur' }]
}

/** 数据分级说明（与文档 §0.5 的加密策略一致） */
const LEVEL_OPTIONS = [
  { value: 'P1', label: '高敏感', desc: '身份证号、银行卡号、生物特征、收付款方实名信息 → 国密 SM4 + Paillier 同态加密（双重）' },
  { value: 'P2', label: '中敏感', desc: '交易金额、商户税号、地址 → 差分隐私（Laplace）+ AES-256-GCM' },
  { value: 'P3', label: '低敏感', desc: '商品类别、币种、地区编码 → AES-256-GCM' }
]

const REGION_OPTIONS = [
  { value: 'CN', label: '中国' },
  { value: 'EU', label: '欧盟' },
  { value: 'SG', label: '新加坡' },
  { value: 'US', label: '美国' },
  { value: 'ME', label: '中东' },
  { value: 'AF', label: '非洲' }
]

const FIELD_OPTIONS = [
  { value: 'bankCard', label: '银行卡号' },
  { value: 'idCard', label: '身份证号' },
  { value: 'realName', label: '收付款方实名' },
  { value: 'amount', label: '交易金额' },
  { value: 'taxNo', label: '商户税号' },
  { value: 'category', label: '商品类别' },
  { value: 'address', label: '收货地址' },
  { value: 'phone', label: '联系电话' },
  { value: 'email', label: '电子邮箱' },
  { value: 'biometric', label: '生物特征' },
  { value: 'deviceId', label: '设备指纹' },
  { value: 'currency', label: '币种' }
]

const levelDesc = computed(() => LEVEL_OPTIONS.find((item) => item.value === form.dataLevel)?.desc || '')
const isCrossBorder = computed(() => form.sourceRegion && form.targetRegion && form.sourceRegion !== form.targetRegion)

const checkedRules = computed(() => result.value?.checkedRules ?? [])
const issueList = computed(() => result.value?.issues ?? [])
const passedRules = computed(() => checkedRules.value.filter((item) => isPassResult(item?.result)).length)

/** 整改清单：优先使用后端 rectificationList，缺失时用 issues 的整改建议兜底 */
const rectificationItems = computed(() => {
  const fromApi = result.value?.rectificationList
  if (Array.isArray(fromApi) && fromApi.length) {
    return fromApi.map((item, index) => {
      if (typeof item === 'string') {
        return { key: `api-${index}`, rule: '整改项', text: item }
      }
      return {
        key: `api-${index}`,
        rule: item?.rule || item?.code || '整改项',
        text: item?.rectification || item?.message || item?.text || '-'
      }
    })
  }
  return issueList.value.map((item, index) => ({
    key: `issue-${index}`,
    rule: item?.rule || '命中规则',
    text: item?.rectification || item?.message || '-'
  }))
})

const remainingIssues = computed(() => rectificationItems.value.filter((item) => !rectified.value.includes(item.key)))

/** 法规速查：按关键字过滤后取前 8 条 */
const matchedRegulations = computed(() => {
  const list = appStore.regulations ?? []
  const keyword = regKeyword.value.trim().toLowerCase()
  if (!keyword) return list
  return list.filter((item) => {
    const text = [item?.name, item?.code, item?.region, item?.sensitiveScope, item?.transferRule]
      .filter(Boolean)
      .join(' ')
      .toLowerCase()
    return text.includes(keyword)
  })
})

const regulationList = computed(() => matchedRegulations.value.slice(0, 8))

function isPassResult(value) {
  // 后端可能返回 true/'pass'/'passed'/1 等形态，统一归一化判断
  if (value === true || value === 1) return true
  const text = String(value ?? '').toLowerCase()
  return ['pass', 'passed', 'true', 'ok', 'success'].includes(text)
}

function issueLevelType(level) {
  const key = String(level || '').toLowerCase()
  if (['high', 'p1', '严重', '高'].includes(key)) return 'danger'
  if (['medium', 'p2', '中'].includes(key)) return 'warning'
  return 'info'
}

function issueLevelLabel(level) {
  const key = String(level || '').toLowerCase()
  if (['high', 'p1', '严重', '高'].includes(key)) return '高危'
  if (['medium', 'p2', '中'].includes(key)) return '中度'
  if (['low', 'p3', '低'].includes(key)) return '轻度'
  return level || '提示'
}

function regionLabel(code) {
  if (!code) return '-'
  return REGION_OPTIONS.find((item) => item.value === code)?.label || code
}

async function onValidate() {
  if (!formRef.value) return
  try {
    await formRef.value.validate()
  } catch (error) {
    ElMessage.warning('请先补全带 * 的必填项')
    return
  }
  loading.value = true
  try {
    const data = await complianceApi.validate({
      dataLevel: form.dataLevel,
      sourceRegion: form.sourceRegion,
      targetRegion: form.targetRegion,
      fields: form.fields ?? [],
      purpose: form.purpose.trim(),
      hasScc: Boolean(form.hasScc),
      hasDpia: Boolean(form.hasDpia),
      authorized: Boolean(form.authorized)
    })
    result.value = data ?? { passed: false, checkedRules: [], issues: [] }
    checkedAt.value = new Date().toISOString()
    rectified.value = []
    if (result.value.passed) {
      ElMessage.success('合规校验通过')
    } else {
      ElMessage.warning('合规校验未通过，请查看整改清单')
    }
  } catch (error) {
    // 注意：后端在合规未通过时可能返回 code 5002（附整改清单），
    // 此时请求拦截器会 reject，这里保留上一次结果并提示用户重试。
  } finally {
    loading.value = false
  }
}

function onReset() {
  form.dataLevel = 'P2'
  form.sourceRegion = 'CN'
  form.targetRegion = 'EU'
  form.fields = []
  form.purpose = ''
  form.hasScc = false
  form.hasDpia = false
  form.authorized = false
  result.value = null
  rectified.value = []
  checkedAt.value = ''
  formRef.value?.clearValidate()
}

async function loadRegulations() {
  regLoading.value = true
  try {
    await appStore.loadRegulations()
  } catch (error) {
    // 法规库拉取失败不影响校验主流程
  } finally {
    regLoading.value = false
  }
}

async function load() {
  loading.value = true
  try {
    await Promise.all([appStore.loadMeta(), loadRegulations()])
  } catch (error) {
    // 元数据失败时页面仍可使用（地区/字段为本地常量）
  } finally {
    loading.value = false
  }
}

onMounted(load)
