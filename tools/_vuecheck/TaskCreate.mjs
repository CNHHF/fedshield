
import { computed, onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { engineApi } from '@/api'
import DataLevelTag from '@/components/DataLevelTag.vue'
import { useAppStore } from '@/store/app'
import { TASK_TYPE } from '@/utils/format'

const router = useRouter()
const appStore = useAppStore()

const formRef = ref(null)
const submitting = ref(false)
// 高级配置默认收起（空数组即折叠）
const activePanels = ref([])

const form = reactive({
  name: '',
  type: 'federated',
  algorithm: 'fedavg',
  partners: [],
  datasets: [],
  epsilon: 2.0,
  rounds: 10,
  description: '',
  hyper: {
    learningRate: 0.08,
    treeDepth: 6,
    batchSize: 256,
    quantization: true,
    mutualTls: true,
    auditRetentionYears: 5
  }
})

const rules = {
  name: [{ required: true, message: '请输入任务名称', trigger: 'blur' }],
  type: [{ required: true, message: '请选择任务类型', trigger: 'change' }],
  algorithm: [{ required: true, message: '请选择算法模板', trigger: 'change' }],
  partners: [
    {
      // 数组类字段用自定义校验：至少选择一个参与方，否则无法建立联邦计算
      validator: (rule, value, callback) => (value && value.length ? callback() : callback(new Error('请至少选择一个合作节点'))),
      trigger: 'change'
    }
  ],
  datasets: [
    {
      validator: (rule, value, callback) => (value && value.length ? callback() : callback(new Error('请至少选择一个计算数据集'))),
      trigger: 'change'
    }
  ],
  rounds: [{ required: true, message: '请设置迭代轮次', trigger: 'change' }],
  epsilon: [{ required: true, message: '请设置隐私预算 ε', trigger: 'change' }]
}

// 任务类型：优先使用后端 /meta/task-types，缺失时用本地 TASK_TYPE 兜底
const typeOptions = computed(() => {
  const remote = (appStore.taskTypes || []).map((item) => ({
    code: item.code,
    name: item.name || TASK_TYPE[item.code]?.label || item.code,
    tech: item.tech || TASK_TYPE[item.code]?.tech || '',
    desc: item.desc || ''
  }))
  if (remote.length) return remote
  return Object.entries(TASK_TYPE).map(([code, meta]) => ({ code, name: meta.label, tech: meta.tech, desc: '' }))
})

const currentType = computed(() => typeOptions.value.find((item) => item.code === form.type) || null)

// 节点与数据集：接口可能返回空数组，这里提供演示兜底，保证多选框不为空
const nodeOptions = computed(() => {
  const remote = appStore.nodes || []
  if (remote.length) return remote
  return [
    { code: 'NODE-CN', name: '中国节点', region: 'CN', status: 'online' },
    { code: 'NODE-EU', name: '欧盟节点', region: 'EU', status: 'online' },
    { code: 'NODE-SEA', name: '东南亚节点', region: 'SEA', status: 'offline' }
  ]
})

const datasetOptions = computed(() => {
  const remote = appStore.datasets || []
  if (remote.length) return remote
  return [
    { code: 'DS-TX', name: '跨境交易明细', level: 'P2', region: 'CN' },
    { code: 'DS-KYC', name: '商户实名信息', level: 'P1', region: 'EU' },
    { code: 'DS-CATEGORY', name: '商品类别字典', level: 'P3', region: 'SEA' }
  ]
})

const algorithmOptions = computed(() => {
  const remote = appStore.algorithms || []
  if (remote.length) return remote
  return [
    { code: 'fedavg', name: 'FedAvg 联邦平均', desc: '横向联邦学习基础聚合算法' },
    { code: 'fedprox', name: 'FedProx 近端项', desc: '缓解 Non-IID 数据导致的模型漂移' },
    { code: 'paillier-sum', name: 'Paillier 同态求和', desc: '密文域求和，适合联合统计' },
    { code: 'oprf', name: 'RSA 盲签名 OPRF', desc: '匿踪查询 / 隐私求交' }
  ]
})

// 已选数据集涉及的分级（去重并按 P1→P3 排序）
const involvedLevels = computed(() => {
  const levels = new Set()
  form.datasets.forEach((code) => {
    const dataset = datasetOptions.value.find((item) => item.code === code)
    if (dataset?.level) levels.add(dataset.level)
  })
  return ['P1', 'P2', 'P3'].filter((level) => levels.has(level))
})

const ENCRYPTION_POLICIES = [
  {
    level: 'P1',
    name: '高敏感数据',
    algorithm: '国密SM4 + Paillier',
    desc: '身份证号、银行卡号、收付款方实名信息：SM4-CBC+HMAC 加密本体，数据密钥再经 Paillier 公钥封装。'
  },
  {
    level: 'P2',
    name: '中敏感数据',
    algorithm: '差分隐私 + AES-256-GCM',
    desc: '交易金额、商户税号、经营地址：Laplace(Δf/ε) 加噪后再做 AES-256-GCM 对称加密。'
  },
  {
    level: 'P3',
    name: '低敏感数据',
    algorithm: 'AES-256-GCM',
    desc: '商品类别、币种、地区编码：直接使用 AES-256-GCM 加密传输与落盘。'
  }
]

const FLOW_STEPS = [
  { title: '数据接入（分级）', desc: '自动识别敏感字段并分级为 P1/P2/P3，原始数据留存各参与方节点' },
  { title: '安全传输（加密通道）', desc: 'TLS1.3 双向认证 + 节点证书校验，密文信封跨节点传输' },
  { title: '隐私计算（密文运算）', desc: '联邦学习 / 同态加密 / 盲签名，计算全程不接触明文' },
  { title: '合规校验（规则引擎）', desc: '出境规则、隐私预算与授权范围校验，未通过则阻断并生成整改清单' },
  { title: '结果应用（落链存证）', desc: '密文摘要与计算请求写入联盟链，结果仅授权方可见' }
]

const FLOW_ICONS = ['UploadFilled', 'Lock', 'Cpu', 'CircleCheck', 'Link']

function handleReset() {
  formRef.value?.resetFields()
  form.partners = []
  form.datasets = []
  form.epsilon = 2.0
  form.rounds = 10
  form.description = ''
  ElMessage.info('表单已重置')
}

async function handleSubmit() {
  const valid = await formRef.value?.validate().catch(() => false)
  if (!valid) {
    ElMessage.warning('请先补全带 * 的必填项')
    return
  }

  submitting.value = true
  try {
    // hyper 字段名与 API.md §4.1 的请求体保持一致；advanced 附带同一份配置，
    // 便于后端在做严格字段校验时仍能取到高级参数（多余字段不影响创建）
    const payload = {
      name: form.name,
      type: form.type,
      algorithm: form.algorithm,
      partners: form.partners,
      datasets: form.datasets,
      epsilon: form.epsilon,
      rounds: form.rounds,
      description: form.description,
      hyper: { ...form.hyper },
      advanced: { ...form.hyper }
    }
    const data = await engineApi.createTask(payload)
    ElMessage.success(`计算任务创建成功${data?.code ? `（任务ID：${data.code}）` : ''}`)
    router.push('/engine/tasks')
  } catch (error) {
    // 创建失败时保留表单内容，便于用户修正后重试
  } finally {
    submitting.value = false
  }
}

onMounted(async () => {
  try {
    await appStore.loadMeta()
  } catch (error) {
    // 元数据失败时页面使用本地兜底选项，仍可完成创建
  }
})
