
/**
 * 多方协同权限管控（对应文档图26~图30）
 * 三个页签：新建数据授权 / 授权记录管理 / 风险与预警
 * 监管端（regulator）默认停留在风险页签，且不可新建授权（前端隐藏 + 后端 authz:grant:manage 鉴权双重控制）
 */
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { authzApi } from '@/api'
import { useAppStore } from '@/store/app'
import { useUserStore } from '@/store/user'
import { GRANT_STATUS, dictOf, formatNumber, formatTime } from '@/utils/format'
import { downloadResponse } from '@/utils/download'
import DataLevelTag from '@/components/DataLevelTag.vue'

const appStore = useAppStore()
const userStore = useUserStore()

/** 使用目的字典（与后端授权用途枚举对应） */
const PURPOSE_OPTIONS = ['反欺诈模型训练', '联合风控验证', '黑名单核验', '监管申报统计']

/** 授权级别：只读计算 / 结果查询限制 / 允许参与隐私计算 */
const LEVEL_OPTIONS = [
  { value: 'readonly', label: '只读计算', desc: '仅允许在密文域内参与计算，任何情况下不返回明细数据。' },
  { value: 'query-limited', label: '结果查询限制', desc: '仅可查询聚合结果，且单日查询次数受限（最小必要原则）。' },
  { value: 'mpc', label: '允许参与隐私计算', desc: '可作为计算节点参与联邦学习 / 同态加密等多方计算任务。' }
]

const LEVEL_TAG_TYPE = { readonly: 'info', 'query-limited': 'warning', mpc: 'success' }

const isRegulator = computed(() => userStore.role === 'regulator')

const activeTab = ref('create')
const showMore = ref(false)
const loading = ref(false)
const submitting = ref(false)
const exporting = ref(false)
const riskLoading = ref(false)

const grantFormRef = ref(null)
const grantForm = reactive({
  partner: '',
  datasetScope: [],
  purpose: ['反欺诈模型训练'],
  level: 'readonly',
  validity: [],
  allowReGrant: false,
  requireMfa: true,
  remark: ''
})

const grantRules = {
  partner: [{ required: true, message: '请选择授权对象', trigger: 'change' }],
  datasetScope: [{ required: true, type: 'array', min: 1, message: '请至少选择一个数据范围', trigger: 'change' }],
  purpose: [{ required: true, type: 'array', min: 1, message: '请至少选择一个使用目的', trigger: 'change' }],
  level: [{ required: true, message: '请选择授权级别', trigger: 'change' }],
  validity: [
    {
      // 有效期必填校验：必须是 [生效时间, 到期时间] 两元素数组
      validator: (rule, value, callback) => {
        if (!Array.isArray(value) || value.length !== 2 || !value[0] || !value[1]) {
          callback(new Error('请选择授权有效期'))
          return
        }
        callback()
      },
      trigger: 'change'
    }
  ]
}

/* ---------------- 字典与选项（全部做空值兜底） ---------------- */
const partnerOptions = computed(() => appStore.partners ?? [])
const datasetOptions = computed(() => appStore.datasets ?? [])
const statusOptions = computed(() => Object.entries(GRANT_STATUS).map(([value, meta]) => ({ value, label: meta.label })))

const selectedLevels = computed(() =>
  (grantForm.datasetScope ?? []).map((code) => datasetLevel(code))
)
const hasP1Scope = computed(() => selectedLevels.value.includes('P1'))

const currentLevelDesc = computed(
  () => LEVEL_OPTIONS.find((item) => item.value === grantForm.level)?.desc || ''
)

/** 授权对象为未认证机构时的额外提示（选项已 disabled，这里做二次说明） */
const partnerCertTip = computed(() => {
  const partner = partnerOptions.value.find((item) => item.code === grantForm.partner)
  if (!partner) return ''
  if (!partner.verified) return '该机构尚未通过资质审核，需先在合作方管理中完成认证后方可授权。'
  const expire = partner.certExpireAt ? new Date(String(partner.certExpireAt).replace(' ', 'T')).getTime() : 0
  if (expire && expire - Date.now() < 90 * 24 * 3600 * 1000) {
    return '该机构资质证书将在 90 天内到期，请同步安排证书续期，避免授权生效期间证书失效。'
  }
  return ''
})

function datasetLevel(code) {
  return datasetOptions.value.find((item) => item.code === code)?.level || 'P3'
}

function datasetLabel(code) {
  const dataset = datasetOptions.value.find((item) => item.code === code)
  return dataset ? `${dataset.name}（${dataset.level || 'P3'}）` : code
}

function levelLabel(level) {
  return LEVEL_OPTIONS.find((item) => item.value === level)?.label || level || '-'
}

function levelTagType(level) {
  return LEVEL_TAG_TYPE[level] || 'info'
}

/** purpose 契约上是标量字符串，但后端也可能返回数组，这里统一转为展示文本 */
function purposeText(purpose) {
  if (Array.isArray(purpose)) return purpose.length ? purpose.join('、') : '-'
  return purpose || '-'
}

function riskScoreType(score) {
  const value = Number(score || 0)
  if (value >= 80) return 'danger'
  if (value >= 60) return 'warning'
  return 'info'
}

/* ---------------- ① 新建授权 ---------------- */
/** 有效期上限 1 年：超出时提示并自动截断到「起始时间 + 365 天」 */
function onValidityChange(value) {
  if (!Array.isArray(value) || value.length !== 2 || !value[0] || !value[1]) return
  const start = new Date(String(value[0]).replace(' ', 'T')).getTime()
  const end = new Date(String(value[1]).replace(' ', 'T')).getTime()
  if (Number.isNaN(start) || Number.isNaN(end)) return
  const limit = start + 365 * 24 * 3600 * 1000
  if (end > limit) {
    const date = new Date(limit)
    const pad = (n) => String(n).padStart(2, '0')
    const truncated = `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())} ${pad(
      date.getHours()
    )}:${pad(date.getMinutes())}:${pad(date.getSeconds())}`
    grantForm.validity = [value[0], truncated]
    ElMessage.warning('授权有效期最长 1 年，已自动截断为起始时间后 365 天')
  }
}

/** 日期选择器：禁止选择「起始时间 + 365 天」之后的日期 */
function disableBeyondOneYear(date) {
  const start = grantForm.validity?.[0]
  if (!start) return false
  const startTime = new Date(String(start).replace(' ', 'T')).getTime()
  if (Number.isNaN(startTime)) return false
  return date.getTime() > startTime + 365 * 24 * 3600 * 1000
}

function resetGrantForm() {
  grantForm.partner = ''
  grantForm.datasetScope = []
  grantForm.purpose = ['反欺诈模型训练']
  grantForm.level = 'readonly'
  grantForm.validity = []
  grantForm.allowReGrant = false
  grantForm.requireMfa = true
  grantForm.remark = ''
  showMore.value = false
  grantFormRef.value?.clearValidate()
}

async function submitGrant() {
  if (!grantFormRef.value) return
  try {
    await grantFormRef.value.validate()
  } catch (error) {
    return
  }
  // 额外兜底：有效期跨度再校验一次，防止绕过日期控件传入超长有效期
  const start = new Date(String(grantForm.validity[0]).replace(' ', 'T')).getTime()
  const end = new Date(String(grantForm.validity[1]).replace(' ', 'T')).getTime()
  if (end - start > 365 * 24 * 3600 * 1000) {
    ElMessage.warning('授权有效期最长 1 年，请重新选择到期时间')
    return
  }

  // 权限点：按级别推导 + 附加开关（二次授权 / 强制 MFA）落库，便于后端鉴权与审计
  const permissions = []
  if (grantForm.allowReGrant) permissions.push('authz:re-authorize')
  if (grantForm.requireMfa) permissions.push('authz:mfa-required')

  submitting.value = true
  try {
    const data = await authzApi.createGrant({
      partner: grantForm.partner,
      datasetScope: [...grantForm.datasetScope],
      purpose: grantForm.purpose.join('、'),
      level: grantForm.level,
      validFrom: grantForm.validity[0],
      validTo: grantForm.validity[1],
      permissions,
      remark: grantForm.remark
    })
    ElMessage.success(`授权申请已提交，授权ID：${data?.code || '-'}（待审批）`)
    resetGrantForm()
    activeTab.value = 'records'
    query.page = 1
    await load()
  } catch (error) {
    // 请求层已统一提示错误，这里仅保证不阻塞后续操作
  } finally {
    submitting.value = false
  }
}

/* ---------------- ② 授权记录 ---------------- */
const grantRows = ref([])
const grantTotal = ref(0)
const query = reactive({ status: '', partner: '', keyword: '', page: 1, size: 10 })

async function load() {
  loading.value = true
  try {
    const payload = await authzApi.grants({
      status: query.status || undefined,
      partner: query.partner || undefined,
      keyword: query.keyword || undefined,
      page: query.page,
      size: query.size
    })
    // 兼容分页信封 { list, total } 与直接返回数组两种形态
    const list = Array.isArray(payload) ? payload : payload?.list ?? []
    grantRows.value = list ?? []
    grantTotal.value = Array.isArray(payload) ? list.length : payload?.total ?? 0
  } catch (error) {
    grantRows.value = []
    grantTotal.value = 0
  } finally {
    loading.value = false
  }
}

function searchGrants() {
  query.page = 1
  load()
}

async function handleExport() {
  exporting.value = true
  try {
    const response = await authzApi.exportGrants()
    downloadResponse(response, `数据授权记录_${Date.now()}.csv`)
    ElMessage.success('授权记录导出成功')
  } catch (error) {
    // 导出失败已由请求层提示
  } finally {
    exporting.value = false
  }
}

async function handleApprove(row) {
  let comment = ''
  try {
    const result = await ElMessageBox.prompt('请输入审批意见（将写入链上存证）', '审批授权申请', {
      confirmButtonText: '通过',
      cancelButtonText: '取消',
      inputValue: '资质与合规要件齐全，同意授权',
      inputPlaceholder: '审批意见'
    })
    comment = result.value || ''
  } catch (error) {
    return
  }
  try {
    await authzApi.approveGrant(row.id, { approved: true, comment })
    ElMessage.success('已审批通过，授权正式生效')
    await load()
  } catch (error) {
    // 错误提示由请求层统一处理
  }
}

async function handleRevoke(row) {
  let reason = ''
  try {
    const result = await ElMessageBox.prompt(
      `撤销后「${row.partner || row.code}」将立即失去授权范围内数据的访问能力，请填写撤销原因`,
      '撤销授权',
      {
        confirmButtonText: '确认撤销',
        cancelButtonText: '取消',
        inputType: 'textarea',
        inputPlaceholder: '如：合作终止 / 资质过期 / 触发熔断规则',
        inputValidator: (value) => (value && value.trim().length >= 4 ? true : '撤销原因不少于 4 个字符')
      }
    )
    reason = result.value || ''
  } catch (error) {
    return
  }
  try {
    await authzApi.revokeGrant(row.id, { reason })
    ElMessage.success('授权已撤销，变更已落链存证')
    await load()
  } catch (error) {
    // 错误提示由请求层统一处理
  }
}

/** 取消待审核申请：语义等同撤销，走同一接口并标注原因 */
async function handleCancel(row) {
  let reason = ''
  try {
    const result = await ElMessageBox.prompt('请填写取消该授权申请的原因', '取消授权申请', {
      confirmButtonText: '确认取消',
      cancelButtonText: '返回',
      inputPlaceholder: '如：业务需求变更 / 重复申请',
      inputValidator: (value) => (value && value.trim().length >= 2 ? true : '请填写取消原因')
    })
    reason = result.value || ''
  } catch (error) {
    return
  }
  try {
    await authzApi.revokeGrant(row.id, { reason })
    ElMessage.success('授权申请已取消')
    await load()
  } catch (error) {
    // 错误提示由请求层统一处理
  }
}

async function handleRenew(row) {
  // 续期新到期日：默认在原到期日基础上顺延 90 天，且不得超过「今天 + 1 年」
  const base = row.validTo ? new Date(String(row.validTo).replace(' ', 'T')).getTime() : Date.now()
  const pad = (n) => String(n).padStart(2, '0')
  const toDateText = (time) => {
    const date = new Date(time)
    return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`
  }
  const defaultDate = toDateText(Math.max(base, Date.now()) + 90 * 24 * 3600 * 1000)
  const maxDate = toDateText(Date.now() + 365 * 24 * 3600 * 1000)

  let validTo = ''
  try {
    const result = await ElMessageBox.prompt(
      `请选择新的到期日期（不得晚于 ${maxDate}，续期同样受 1 年上限约束）`,
      '授权续期',
      {
        confirmButtonText: '确认续期',
        cancelButtonText: '取消',
        inputType: 'date',
        inputValue: defaultDate,
        inputValidator: (value) => {
          if (!value) return '请选择新的到期日期'
          const time = new Date(String(value).replace(' ', 'T')).getTime()
          if (Number.isNaN(time)) return '日期格式不正确，应为 YYYY-MM-DD'
          if (time <= Date.now()) return '新到期日期必须晚于当前时间'
          if (time > Date.now() + 365 * 24 * 3600 * 1000) return '续期后有效期不得超过 1 年'
          return true
        }
      }
    )
    validTo = result.value
  } catch (error) {
    return
  }
  try {
    await authzApi.renewGrant(row.id, { validTo: `${validTo} 23:59:59` })
    ElMessage.success('授权已续期')
    await load()
  } catch (error) {
    // 错误提示由请求层统一处理
  }
}

/* ---------------- 授权详情抽屉 ---------------- */
const detailVisible = ref(false)
const detailLoading = ref(false)
const detail = ref({})

const detailHistory = computed(() => {
  const raw = detail.value?.history
  const rows = Array.isArray(raw) ? raw : []
  return rows.map((item) => {
    // 后端可能返回字符串数组或对象数组，这里统一成时间线需要的结构
    const record = typeof item === 'string' ? { action: item } : item || {}
    return {
      ts: record.ts || record.time || record.createdAt || '',
      title: record.action || record.title || record.type || '权限变更',
      actor: record.actor || record.operator || record.user || '-',
      detail: record.detail || record.comment || record.remark || record.reason || '',
      type: record.result === 'failed' ? 'danger' : 'primary'
    }
  })
})

async function openDetail(row) {
  detailVisible.value = true
  detailLoading.value = true
  detail.value = { ...row }
  try {
    const data = await authzApi.grantDetail(row.id)
    detail.value = data || { ...row }
  } catch (error) {
    // 详情获取失败时保留列表行的基础信息，抽屉仍可展示
  } finally {
    detailLoading.value = false
  }
}

/* ---------------- ③ 风险与预警 ---------------- */
const risks = ref({ abnormalAccess: [], expiringSoon: [], mfaFailures: [] })

/** 字段别名兜底：API.md 未固定 risks 子项字段名，逐个键尝试避免 undefined */
function pick(source, keys, fallback = '-') {
  for (const key of keys) {
    const value = source?.[key]
    if (value !== undefined && value !== null && value !== '') return value
  }
  return fallback
}

/** 剩余天数兜底：后端未返回时按到期时间前端计算 */
function daysLeft(validTo) {
  if (!validTo) return 0
  const time = new Date(String(validTo).replace(' ', 'T')).getTime()
  if (Number.isNaN(time)) return 0
  const diff = time - Date.now()
  return diff > 0 ? Math.ceil(diff / (24 * 3600 * 1000)) : 0
}

const abnormalRows = computed(() =>
  (risks.value.abnormalAccess ?? []).map((item) => ({
    ts: pick(item, ['ts', 'time', 'createdAt', 'at']),
    account: pick(item, ['account', 'actor', 'username', 'user', 'subject']),
    action: pick(item, ['action', 'behavior', 'event', 'detail']),
    riskScore: Number(pick(item, ['riskScore', 'score', 'risk'], 0)) || 0
  }))
)

const expiringRows = computed(() =>
  (risks.value.expiringSoon ?? []).map((item) => {
    const validTo = pick(item, ['validTo', 'expireAt', 'expiredAt', 'endTime'], '')
    return {
      code: pick(item, ['code', 'grantCode', 'id']),
      partner: pick(item, ['partner', 'partnerName', 'org']),
      validTo,
      remainDays: Number(pick(item, ['remainDays', 'daysLeft', 'remainingDays', 'days'], daysLeft(validTo))) || 0
    }
  })
)

const mfaRows = computed(() =>
  (risks.value.mfaFailures ?? []).map((item) => ({
    account: pick(item, ['account', 'username', 'actor', 'user']),
    ts: pick(item, ['ts', 'time', 'lastAt', 'createdAt']),
    ip: pick(item, ['ip', 'clientIp', 'sourceIp']),
    count: Number(pick(item, ['count', 'failCount', 'times', 'attempts'], 0)) || 0
  }))
)

async function loadRisks() {
  riskLoading.value = true
  try {
    const data = await authzApi.risks()
    risks.value = {
      abnormalAccess: data?.abnormalAccess ?? [],
      expiringSoon: data?.expiringSoon ?? [],
      mfaFailures: data?.mfaFailures ?? []
    }
  } catch (error) {
    risks.value = { abnormalAccess: [], expiringSoon: [], mfaFailures: [] }
  } finally {
    riskLoading.value = false
  }
}

/** 页签切换：首次进入风险页签时才拉取风险数据，减少无效请求 */
function onTabChange(name) {
  if (name === 'risk' && !abnormalRows.value.length && !expiringRows.value.length && !mfaRows.value.length) {
    loadRisks()
  }
  if (name === 'records') {
    load()
  }
}

onMounted(async () => {
  // 监管端默认停留在风险页签，且不展示「新建数据授权」
  activeTab.value = isRegulator.value ? 'risk' : 'create'
  try {
    await appStore.loadMeta()
  } catch (error) {
    // 元数据拉取失败时，下拉框退化为空列表，不影响表格功能
  }
  await load()
  if (isRegulator.value) {
    await loadRisks()
  }
})
