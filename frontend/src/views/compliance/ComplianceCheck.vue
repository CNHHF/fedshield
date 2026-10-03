<template>
  <div class="fs-page">
    <div class="fs-page__header">
      <div>
        <h2 class="fs-page__title">跨境合规校验</h2>
        <p class="fs-page__subtitle">
          数据出境前的实时合规预检：填写数据分级、来源/目的地与合规要件，后端规则引擎逐条执行已启用规则，
          返回总体结论、逐条校验明细与整改清单。
        </p>
      </div>
      <div class="fs-toolbar" style="margin-bottom: 0">
        <el-button :icon="RefreshLeft" @click="onReset">重置表单</el-button>
        <el-button type="primary" :icon="CircleCheck" :loading="loading" @click="onValidate">开始合规校验</el-button>
      </div>
    </div>

    <el-row :gutter="16">
      <!-- 左侧：校验表单 + 结果 -->
      <el-col :xs="24" :lg="16">
        <div class="fs-card">
          <div class="fs-card__header">
            <span class="fs-card__title">出境数据申报</span>
            <span class="fs-muted">对应接口 POST /compliance/rules/validate</span>
          </div>
          <div class="fs-card__body">
            <el-form ref="formRef" :model="form" :rules="formRules" label-width="104px">
              <el-form-item label="数据级别" prop="dataLevel">
                <el-radio-group v-model="form.dataLevel">
                  <el-radio v-for="item in LEVEL_OPTIONS" :key="item.value" :value="item.value" border>
                    {{ item.value }} · {{ item.label }}
                  </el-radio>
                </el-radio-group>
                <div class="level-tip">
                  <DataLevelTag :level="form.dataLevel" />
                  <span class="fs-muted">{{ levelDesc }}</span>
                </div>
              </el-form-item>

              <el-form-item label="来源地区" prop="sourceRegion">
                <el-select v-model="form.sourceRegion" placeholder="选择数据来源地区" style="width: 260px">
                  <el-option v-for="item in REGION_OPTIONS" :key="item.value" :label="item.label" :value="item.value" />
                </el-select>
              </el-form-item>

              <el-form-item label="目的地地区" prop="targetRegion">
                <el-select v-model="form.targetRegion" placeholder="选择数据出境目的地" style="width: 260px">
                  <el-option v-for="item in REGION_OPTIONS" :key="item.value" :label="item.label" :value="item.value" />
                </el-select>
                <span v-if="isCrossBorder" class="fs-muted" style="margin-left: 10px">
                  跨境传输：将按目的地法规评估出境机制
                </span>
              </el-form-item>

              <el-form-item label="数据字段" prop="fields">
                <el-select
                  v-model="form.fields"
                  multiple
                  collapse-tags
                  collapse-tags-tooltip
                  placeholder="选择本次出境涉及的数据字段"
                  style="width: 100%"
                >
                  <el-option v-for="item in FIELD_OPTIONS" :key="item.value" :label="item.label" :value="item.value" />
                </el-select>
              </el-form-item>

              <el-form-item label="使用目的" prop="purpose">
                <el-input
                  v-model="form.purpose"
                  type="textarea"
                  :rows="2"
                  maxlength="200"
                  show-word-limit
                  placeholder="如：跨境电商订单风控建模（横向联邦学习）"
                />
              </el-form-item>

              <el-form-item label="合规要件">
                <el-checkbox v-model="form.hasScc">已签订 SCC（标准合同条款）</el-checkbox>
                <el-checkbox v-model="form.hasDpia">已完成 DPIA（数据保护影响评估）</el-checkbox>
                <el-checkbox v-model="form.authorized">已取得用户授权</el-checkbox>
                <div class="fs-muted" style="margin-top: 4px">
                  P1 高敏感数据出境通常需同时满足上述三项要件，缺少要件时规则引擎会要求补充而非直接放行。
                </div>
              </el-form-item>

              <el-form-item>
                <el-button type="primary" :icon="Search" :loading="loading" @click="onValidate">提交校验</el-button>
                <el-button @click="onReset">重置</el-button>
              </el-form-item>
            </el-form>
          </div>
        </div>

        <!-- 校验结论 -->
        <div v-if="result" class="fs-card">
          <div class="fs-card__header">
            <span class="fs-card__title">校验结论</span>
            <span class="fs-muted">校验时间：{{ formatTime(checkedAt) }}</span>
          </div>
          <div class="fs-card__body">
            <el-result
              :icon="result.passed ? 'success' : 'error'"
              :title="result.passed ? '合规校验通过' : '合规校验未通过'"
              :sub-title="
                result.passed
                  ? '本次数据出境申请满足当前已启用规则的全部要求，可继续发起传输。'
                  : `共发现 ${issueList.length} 项问题，请按整改清单处理后重新提交校验。`
              "
            />

            <div class="fs-grid fs-grid--4" style="margin-bottom: 16px">
              <StatCard label="校验规则数" :value="checkedRules.length" unit="条" icon="List" color="#1f5fd8" />
              <StatCard label="通过规则" :value="passedRules" unit="条" icon="CircleCheck" color="#14a37f" />
              <StatCard label="未通过规则" :value="checkedRules.length - passedRules" unit="条" icon="Warning" color="#e5484d" />
              <StatCard label="待整改问题" :value="issueList.length" unit="项" icon="Tickets" color="#f5a623" />
            </div>

            <div class="check-block-title">逐条规则校验结果</div>
            <el-table :data="checkedRules" border stripe size="small">
              <el-table-column prop="code" label="规则编码" width="150">
                <template #default="{ row }">{{ row.code || '-' }}</template>
              </el-table-column>
              <el-table-column prop="name" label="规则名称" min-width="200" show-overflow-tooltip>
                <template #default="{ row }">{{ row.name || '-' }}</template>
              </el-table-column>
              <el-table-column prop="result" label="结果" width="110" align="center">
                <template #default="{ row }">
                  <el-tag :type="isPassResult(row.result) ? 'success' : 'danger'" size="small">
                    {{ isPassResult(row.result) ? '通过' : '未通过' }}
                  </el-tag>
                </template>
              </el-table-column>
              <el-table-column prop="detail" label="校验明细" min-width="300" show-overflow-tooltip>
                <template #default="{ row }">{{ row.detail || '-' }}</template>
              </el-table-column>
              <template #empty>
                <el-empty description="无规则命中记录" :image-size="70" />
              </template>
            </el-table>
          </div>
        </div>

        <!-- 问题与整改 -->
        <div v-if="result" class="fs-card">
          <div class="fs-card__header">
            <span class="fs-card__title">问题与整改清单</span>
            <el-tag :type="remainingIssues.length ? 'warning' : 'success'" size="small">
              {{ remainingIssues.length ? `剩余 ${remainingIssues.length} 项待整改` : '整改项已全部勾选完成' }}
            </el-tag>
          </div>
          <div class="fs-card__body">
            <el-table :data="issueList" border stripe size="small">
              <el-table-column prop="rule" label="命中规则" width="180" show-overflow-tooltip>
                <template #default="{ row }">{{ row.rule || '-' }}</template>
              </el-table-column>
              <el-table-column prop="level" label="风险等级" width="110" align="center">
                <template #default="{ row }">
                  <el-tag :type="issueLevelType(row.level)" size="small" effect="dark">
                    {{ issueLevelLabel(row.level) }}
                  </el-tag>
                </template>
              </el-table-column>
              <el-table-column prop="message" label="问题描述" min-width="280" show-overflow-tooltip>
                <template #default="{ row }">{{ row.message || '-' }}</template>
              </el-table-column>
              <el-table-column prop="rectification" label="整改建议" min-width="280" show-overflow-tooltip>
                <template #default="{ row }">{{ row.rectification || '-' }}</template>
              </el-table-column>
              <template #empty>
                <el-empty description="本次校验未发现问题" :image-size="70" />
              </template>
            </el-table>

            <div class="check-block-title" style="margin-top: 18px">整改清单（勾选表示已完成整改）</div>
            <el-checkbox-group v-model="rectified">
              <div v-for="(item, index) in rectificationItems" :key="index" class="rectify-item">
                <el-checkbox :value="item.key">
                  <span class="rectify-item__rule">{{ item.rule }}</span>
                  <span>{{ item.text }}</span>
                </el-checkbox>
              </div>
            </el-checkbox-group>
            <el-empty v-if="!rectificationItems.length" description="无需整改项" :image-size="70" />
          </div>
        </div>
      </el-col>

      <!-- 右侧：法规速查 -->
      <el-col :xs="24" :lg="8">
        <div class="fs-card">
          <div class="fs-card__header">
            <span class="fs-card__title">跨境合规要求速查</span>
            <el-button text :icon="Refresh" :loading="regLoading" @click="loadRegulations">刷新</el-button>
          </div>
          <div class="fs-card__body">
            <el-input
              v-model="regKeyword"
              placeholder="搜索法规名称 / 地区 / 数据范围"
              :prefix-icon="Search"
              clearable
              style="margin-bottom: 12px"
            />
            <div v-loading="regLoading" class="reg-list">
              <div v-for="item in regulationList" :key="item.code || item.name" class="reg-item">
                <div class="reg-item__head">
                  <span class="reg-item__name">{{ item.name || item.code || '未命名法规' }}</span>
                  <el-tag size="small" effect="plain">{{ regionLabel(item.region) }}</el-tag>
                </div>
                <div class="reg-item__row">
                  <span class="reg-item__label">敏感数据范围</span>
                  <span>{{ item.sensitiveScope || '-' }}</span>
                </div>
                <div class="reg-item__row">
                  <span class="reg-item__label">数据出境机制</span>
                  <span>{{ item.transferRule || '-' }}</span>
                </div>
                <div class="reg-item__row">
                  <span class="reg-item__label">审计留存</span>
                  <span>{{ item.auditRetentionYears ?? '-' }} 年</span>
                </div>
              </div>
              <el-empty
                v-if="!regulationList.length && !regLoading"
                :description="regKeyword ? '未匹配到法规，请调整关键字' : '法规库暂无数据'"
                :image-size="70"
              />
            </div>
            <div class="fs-muted" style="margin-top: 10px">
              共匹配 {{ matchedRegulations.length }} 条，展示前 {{ regulationList.length }} 条。
            </div>
          </div>
        </div>
      </el-col>
    </el-row>
  </div>
</template>

<script setup>
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
</script>

<style scoped>
.level-tip {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 6px;
  line-height: 1.5;
}
.check-block-title {
  font-size: 13px;
  font-weight: 600;
  margin-bottom: 10px;
  color: var(--fs-text);
}
.rectify-item {
  padding: 6px 0;
  border-bottom: 1px dashed var(--fs-border);
}
.rectify-item:last-child {
  border-bottom: none;
}
.rectify-item__rule {
  display: inline-block;
  margin-right: 8px;
  color: var(--fs-text-secondary);
  font-size: 12px;
}
.reg-list {
  max-height: 620px;
  overflow-y: auto;
}
.reg-item {
  padding: 10px 12px;
  border: 1px solid var(--fs-border);
  border-radius: 8px;
  background: #fbfcfe;
}
.reg-item + .reg-item {
  margin-top: 10px;
}
.reg-item__head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  margin-bottom: 6px;
}
.reg-item__name {
  font-size: 13px;
  font-weight: 600;
}
.reg-item__row {
  display: flex;
  gap: 8px;
  font-size: 12px;
  line-height: 1.7;
  color: var(--fs-text);
}
.reg-item__label {
  flex: 0 0 78px;
  color: var(--fs-text-secondary);
}
</style>
