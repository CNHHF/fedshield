<template>
  <div class="fs-page">
    <div class="fs-page__header">
      <div>
        <h2 class="fs-page__title">新建计算任务</h2>
        <p class="fs-page__subtitle">
          隐私计算任务构建：选择参与方与分级数据、配置算法模板与隐私预算，
          平台将自动为各参与方建立 TLS1.3 加密通道，并在密文域完成计算。
        </p>
      </div>
      <div>
        <el-button @click="router.push('/engine/tasks')">
          <el-icon><Back /></el-icon>
          <span>返回任务列表</span>
        </el-button>
      </div>
    </div>

    <div class="fs-grid fs-grid--2">
      <!-- 左侧：任务构建表单 -->
      <div>
        <el-form ref="formRef" :model="form" :rules="rules" label-width="110px" label-position="right">
          <!-- ① 基本信息 -->
          <div class="fs-card">
            <div class="fs-card__header">
              <div class="fs-card__title">基本信息</div>
            </div>
            <div class="fs-card__body">
              <el-form-item label="任务名称" prop="name">
                <el-input v-model="form.name" maxlength="60" show-word-limit placeholder="例如：2026Q1 跨境电商联合风控建模" />
              </el-form-item>

              <el-form-item label="任务类型" prop="type">
                <el-select v-model="form.type" placeholder="请选择计算任务类型" style="width: 100%">
                  <el-option v-for="item in typeOptions" :key="item.code" :label="item.name" :value="item.code">
                    <span>{{ item.name }}</span>
                    <span class="fs-muted" style="margin-left: 8px">{{ item.tech }}</span>
                  </el-option>
                </el-select>
              </el-form-item>

              <!-- 随任务类型展示技术说明，帮助业务同学理解底层协议 -->
              <el-alert
                v-if="currentType"
                :title="`${currentType.name} · ${currentType.tech || '加密计算'}`"
                :description="currentType.desc || '该类型任务将在密文域完成计算，原始数据不出各参与方节点。'"
                type="info"
                show-icon
                :closable="false"
              />

              <el-form-item label="任务说明" prop="description" style="margin-top: 16px">
                <el-input
                  v-model="form.description"
                  type="textarea"
                  :rows="3"
                  maxlength="200"
                  show-word-limit
                  placeholder="填写本次计算的目的与合规依据（将写入审计存证）"
                />
              </el-form-item>
            </div>
          </div>

          <!-- ② 参与方与数据 -->
          <div class="fs-card">
            <div class="fs-card__header">
              <div class="fs-card__title">参与方与数据</div>
              <span class="fs-muted">已选 {{ form.partners.length }} 个节点 / {{ form.datasets.length }} 个数据集</span>
            </div>
            <div class="fs-card__body">
              <el-form-item label="合作节点" prop="partners">
                <el-select
                  v-model="form.partners"
                  multiple
                  filterable
                  collapse-tags
                  collapse-tags-tooltip
                  placeholder="选择参与本次计算的跨境协作节点"
                  style="width: 100%"
                >
                  <el-option v-for="node in nodeOptions" :key="node.code" :label="node.name" :value="node.code">
                    <span>{{ node.name }}</span>
                    <span class="fs-muted" style="margin-left: 8px">{{ node.region || '-' }}</span>
                    <el-tag
                      size="small"
                      effect="plain"
                      :type="node.status === 'online' ? 'success' : 'info'"
                      style="margin-left: 8px"
                    >
                      {{ node.status === 'online' ? '在线' : '离线' }}
                    </el-tag>
                  </el-option>
                </el-select>
              </el-form-item>

              <el-form-item label="计算数据集" prop="datasets">
                <el-select
                  v-model="form.datasets"
                  multiple
                  filterable
                  collapse-tags
                  collapse-tags-tooltip
                  placeholder="选择参与计算的数据集（按 P1/P2/P3 分级加密）"
                  style="width: 100%"
                >
                  <el-option v-for="dataset in datasetOptions" :key="dataset.code" :label="dataset.name" :value="dataset.code">
                    <span>{{ dataset.name }}</span>
                    <span class="fs-muted" style="margin-left: 8px">{{ dataset.region || '-' }}</span>
                    <DataLevelTag :level="dataset.level || 'P3'" style="margin-left: 8px" />
                  </el-option>
                </el-select>
              </el-form-item>

              <el-form-item v-if="form.datasets.length" label="涉及数据级别">
                <DataLevelTag v-for="level in involvedLevels" :key="level" :level="level" style="margin-right: 6px" />
                <span class="fs-muted" style="margin-left: 6px">最高级别决定本次任务的加密策略与合规校验强度</span>
              </el-form-item>
            </div>
          </div>

          <!-- ③ 计算参数 -->
          <div class="fs-card">
            <div class="fs-card__header">
              <div class="fs-card__title">计算参数</div>
            </div>
            <div class="fs-card__body">
              <el-form-item label="算法模板" prop="algorithm">
                <el-select v-model="form.algorithm" placeholder="选择算法模板" style="width: 100%">
                  <el-option
                    v-for="item in algorithmOptions"
                    :key="item.code"
                    :label="item.name"
                    :value="item.code"
                  >
                    <span>{{ item.name }}</span>
                    <span v-if="item.desc" class="fs-muted" style="margin-left: 8px">{{ item.desc }}</span>
                  </el-option>
                </el-select>
              </el-form-item>

              <el-form-item label="隐私预算 ε" prop="epsilon">
                <el-slider
                  v-model="form.epsilon"
                  :min="0.1"
                  :max="10"
                  :step="0.1"
                  :marks="{ 0.1: '0.1', 2: '2.0', 5: '5', 10: '10' }"
                />
                <div class="fs-muted">
                  ε 越小隐私保护越强、统计误差越大。默认 2.0（平衡点），各轮按串行组合累加消耗。
                </div>
              </el-form-item>

              <el-form-item label="迭代轮次" prop="rounds">
                <el-input-number v-model="form.rounds" :min="1" :max="200" :step="1" />
                <span class="fs-muted" style="margin-left: 10px">联邦学习建议 10~50 轮；统计类任务 1~5 轮即可收敛</span>
              </el-form-item>

              <!-- 加密级别说明卡片：与后端 crypto/policy.py 的 LEVEL_META 保持一致 -->
              <div class="fs-grid fs-grid--3" style="gap: 10px">
                <div v-for="policy in ENCRYPTION_POLICIES" :key="policy.level" class="fs-policy">
                  <div class="fs-policy__head">
                    <DataLevelTag :level="policy.level" />
                    <span class="fs-policy__name">{{ policy.name }}</span>
                  </div>
                  <div class="fs-policy__algo">{{ policy.algorithm }}</div>
                  <div class="fs-muted fs-policy__desc">{{ policy.desc }}</div>
                </div>
              </div>

              <!-- 高级配置：默认收起，避免一次性暴露过多参数 -->
              <el-collapse v-model="activePanels" style="margin-top: 12px">
                <el-collapse-item name="advanced">
                  <template #title>
                    <span style="font-weight: 600">高级配置</span>
                    <span class="fs-muted" style="margin-left: 8px">超参数 / 压缩 / 传输安全 / 审计留存</span>
                  </template>

                  <el-form-item label="学习率">
                    <el-input-number v-model="form.hyper.learningRate" :min="0.001" :max="1" :step="0.01" :precision="3" />
                  </el-form-item>

                  <el-form-item label="树深度">
                    <el-input-number v-model="form.hyper.treeDepth" :min="2" :max="12" :step="1" />
                    <span class="fs-muted" style="margin-left: 10px">仅梯度提升类模板生效（当前模板为线性/联邦平均，展示用）</span>
                  </el-form-item>

                  <el-form-item label="批次大小">
                    <el-input-number v-model="form.hyper.batchSize" :min="16" :max="2048" :step="16" />
                  </el-form-item>

                  <el-form-item label="参数压缩">
                    <el-switch v-model="form.hyper.quantization" active-text="参数量化压缩（float32→int16 + Top-K 剪枝）" />
                  </el-form-item>

                  <el-form-item label="传输安全">
                    <el-switch v-model="form.hyper.mutualTls" active-text="TLS1.3 双向认证（节点证书校验）" />
                  </el-form-item>

                  <el-form-item label="审计留存">
                    <el-select v-model="form.hyper.auditRetentionYears" style="width: 200px">
                      <el-option v-for="year in [3, 5, 7, 10]" :key="year" :label="`${year} 年`" :value="year" />
                    </el-select>
                    <span class="fs-muted" style="margin-left: 10px">按所属地区法规要求留存（多数地区为 5~7 年）</span>
                  </el-form-item>
                </el-collapse-item>
              </el-collapse>
            </div>
          </div>

          <div class="fs-card">
            <div class="fs-card__body" style="display: flex; justify-content: flex-end; gap: 10px">
              <el-button @click="handleReset">重置</el-button>
              <el-button type="primary" :loading="submitting" @click="handleSubmit">
                <el-icon><Promotion /></el-icon>
                <span>提交任务</span>
              </el-button>
            </div>
          </div>
        </el-form>
      </div>

      <!-- 右侧：任务流程预览 -->
      <div>
        <div class="fs-card">
          <div class="fs-card__header">
            <div class="fs-card__title">任务流程预览</div>
            <el-tag size="small" effect="plain">{{ currentType?.tech || '隐私计算' }}</el-tag>
          </div>
          <div class="fs-card__body">
            <el-steps direction="vertical" :active="5" finish-status="success">
              <el-step
                v-for="(step, index) in FLOW_STEPS"
                :key="step.title"
                :title="step.title"
                :description="step.desc"
              >
                <template #icon>
                  <el-icon><component :is="FLOW_ICONS[index]" /></el-icon>
                </template>
              </el-step>
            </el-steps>

            <el-divider />

            <el-descriptions :column="1" border size="small">
              <el-descriptions-item label="参与节点">{{ form.partners.length || 0 }} 个</el-descriptions-item>
              <el-descriptions-item label="数据集">{{ form.datasets.length || 0 }} 个</el-descriptions-item>
              <el-descriptions-item label="隐私预算 ε">{{ form.epsilon.toFixed(1) }}</el-descriptions-item>
              <el-descriptions-item label="迭代轮次">{{ form.rounds }} 轮</el-descriptions-item>
              <el-descriptions-item label="参数压缩">{{ form.hyper.quantization ? '已开启' : '未开启' }}</el-descriptions-item>
              <el-descriptions-item label="双向认证">{{ form.hyper.mutualTls ? 'TLS1.3 双向' : '单向' }}</el-descriptions-item>
              <el-descriptions-item label="审计留存">{{ form.hyper.auditRetentionYears }} 年</el-descriptions-item>
            </el-descriptions>

            <el-alert
              style="margin-top: 14px"
              type="warning"
              :closable="false"
              show-icon
              title="提示"
              description="提交后任务进入「待启动」状态，需在任务管理页点击启动；启动即开始消耗隐私预算并写入审计存证。"
            />
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
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
</script>

<style scoped>
.fs-policy {
  border: 1px solid var(--fs-border);
  border-radius: 8px;
  padding: 10px 12px;
  background: #fafbfd;
}
.fs-policy__head {
  display: flex;
  align-items: center;
  gap: 6px;
}
.fs-policy__name {
  font-size: 13px;
  font-weight: 600;
}
.fs-policy__algo {
  margin-top: 6px;
  font-size: 12px;
  color: var(--fs-primary);
}
.fs-policy__desc {
  margin-top: 4px;
  line-height: 1.5;
}
</style>
