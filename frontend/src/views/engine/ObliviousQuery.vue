<template>
  <div class="fs-page">
    <div class="fs-page__header">
      <div>
        <h2 class="fs-page__title">黑名单匿踪查询</h2>
        <p class="fs-page__subtitle">
          外贸 B2B 商户制裁清单匿踪查询：查询方与清单方均不接触对方明文，
          仅交换盲化/密文后的比对值，满足跨境支付「秒级到账」的 300ms 响应要求。
        </p>
      </div>
      <el-tag type="success" effect="plain" size="large">
        <el-icon><Lock /></el-icon>
        <span style="margin-left: 4px">数据可用不可见</span>
      </el-tag>
    </div>

    <div class="fs-grid fs-grid--2">
      <!-- 左：查询表单 -->
      <div class="fs-card">
        <div class="fs-card__header">
          <div class="fs-card__title">查询条件</div>
          <span class="fs-muted">查询字段仅在本节点内使用，不落库明文</span>
        </div>
        <div class="fs-card__body">
          <el-form ref="formRef" :model="form" :rules="rules" label-width="96px">
            <el-form-item label="商户名称" prop="merchantName">
              <el-input v-model="form.merchantName" placeholder="请输入待核验的商户名称" clearable @keyup.enter="handleSubmit" />
            </el-form-item>

            <el-form-item label="税号" prop="taxNo">
              <el-input v-model="form.taxNo" placeholder="请输入统一社会信用代码 / 税号" clearable @keyup.enter="handleSubmit" />
            </el-form-item>

            <el-form-item label="制裁清单" prop="lists">
              <el-checkbox-group v-model="form.lists">
                <el-checkbox v-for="item in LIST_OPTIONS" :key="item.value" :value="item.value">
                  {{ item.label }}
                </el-checkbox>
              </el-checkbox-group>
            </el-form-item>

            <el-form-item label="协议模式" prop="mode">
              <el-radio-group v-model="form.mode">
                <el-radio value="oprf">RSA盲签名OPRF（生产模式）</el-radio>
                <el-radio value="paillier">同态密文比对（Paillier）</el-radio>
              </el-radio-group>
              <div class="fs-muted" style="line-height: 1.6">
                OPRF：清单变换一次后缓存，单次查询仅一次盲签名往返，响应稳定在毫秒级，适合 OFAC/联合国全量清单；
                Paillier：密文域逐项比对，安全性直观但耗时随清单规模线性增长，适合中小规模清单。
              </div>
            </el-form-item>

            <el-form-item>
              <el-button type="primary" :loading="loading" @click="handleSubmit">
                <el-icon><Search /></el-icon>
                <span>提交匿踪查询</span>
              </el-button>
              <el-button @click="handleReset">重置</el-button>
            </el-form-item>
          </el-form>

          <el-alert
            type="info"
            :closable="false"
            show-icon
            title="隐私保护说明"
            description="查询方仅上传盲化/加密后的查询词，清单方仅返回签名值或密文比对结果，双方都无法还原对方的原始数据；命中结论与密文摘要写入联盟链存证。"
          />
        </div>
      </div>

      <!-- 右：查询结果 -->
      <div class="fs-card">
        <div class="fs-card__header">
          <div class="fs-card__title">查询结果</div>
          <el-tag v-if="result.modeName" size="small" effect="plain">{{ result.modeName }}</el-tag>
        </div>
        <div class="fs-card__body" v-loading="loading">
          <el-empty v-if="!hasResult" description="暂无查询结果，请填写商户信息后提交查询" />

          <template v-else>
            <!-- el-result 仅支持 success / warning / info / error 四种图标类型 -->
            <el-result
              :icon="result.hit ? 'error' : 'success'"
              :title="result.hit ? '命中制裁清单' : '未命中制裁清单'"
              :sub-title="result.hit ? '该商户存在制裁清单匹配记录，建议阻断或转人工复核' : '该商户未出现在所选制裁清单中，可正常放行'"
            >
              <template #extra>
                <el-tag :type="result.hit ? 'danger' : 'success'" size="large" effect="dark">
                  {{ result.hit ? '命中' : '未命中' }}
                </el-tag>
              </template>
            </el-result>

            <el-descriptions :column="2" border size="small">
              <el-descriptions-item label="命中清单">
                <template v-if="(result.matchedList || []).length">
                  <el-tag v-for="name in result.matchedList || []" :key="name" size="small" type="danger" effect="plain" style="margin-right: 4px">
                    {{ name }}
                  </el-tag>
                </template>
                <span v-else class="fs-muted">无</span>
              </el-descriptions-item>
              <el-descriptions-item label="命中实体">{{ result.matchedEntity || '无' }}</el-descriptions-item>
              <el-descriptions-item label="查询耗时">
                <span :style="{ color: performance.pass ? 'var(--fs-success)' : 'var(--fs-danger)', fontWeight: 600 }">
                  {{ formatDuration(result.elapsedMs) }}
                </span>
              </el-descriptions-item>
              <el-descriptions-item label="性能达标">
                <el-tag size="small" :type="performance.pass ? 'success' : 'danger'" effect="plain">
                  {{ performance.pass ? '达标' : '未达标' }}（标准 ≤ {{ formatNumber(performance.target ?? 300, 0) }} ms）
                </el-tag>
              </el-descriptions-item>
              <el-descriptions-item label="清单条目数">{{ formatNumber(result.listSize ?? 0, 0) }}</el-descriptions-item>
              <el-descriptions-item label="密文比对次数">{{ formatNumber(result.comparisons ?? 0, 0) }}</el-descriptions-item>
            </el-descriptions>

            <template v-if="(result.matchedEntries || []).length">
              <el-divider content-position="left">命中条目明细</el-divider>
              <el-table :data="result.matchedEntries || []" size="small" border>
                <el-table-column prop="list" label="清单" width="110" />
                <el-table-column prop="name" label="实体名称" min-width="160" show-overflow-tooltip />
                <el-table-column prop="country" label="国家/地区" width="110" />
                <el-table-column prop="program" label="制裁项目" min-width="140" show-overflow-tooltip />
              </el-table>
            </template>

            <el-divider content-position="left">查询步骤与耗时</el-divider>
            <el-timeline>
              <el-timeline-item
                v-for="(step, index) in result.steps || []"
                :key="`${index}-${step.name}`"
                :timestamp="formatDuration(step.ms)"
                placement="top"
                :type="index === (result.steps || []).length - 1 ? 'success' : 'primary'"
              >
                <div style="font-weight: 600">{{ step.name || `步骤 ${index + 1}` }}</div>
                <div class="fs-muted" style="margin-top: 4px">
                  加密算法：<span class="fs-mono">{{ step.cipher || '-' }}</span>
                </div>
                <div class="fs-muted" style="margin-top: 2px">{{ step.detail || '—' }}</div>
              </el-timeline-item>
            </el-timeline>

            <el-divider content-position="left">隐私保护结果</el-divider>
            <el-descriptions :column="2" border size="small">
              <el-descriptions-item label="查询方明文暴露">
                <el-tag size="small" :type="Number(result.privacy?.queryPlaintextExposed ?? 0) === 0 ? 'success' : 'danger'" effect="plain">
                  {{ formatNumber(result.privacy?.queryPlaintextExposed ?? 0, 0) }} 条
                </el-tag>
              </el-descriptions-item>
              <el-descriptions-item label="清单方明文暴露">
                <el-tag size="small" :type="Number(result.privacy?.listPlaintextExposed ?? 0) === 0 ? 'success' : 'danger'" effect="plain">
                  {{ formatNumber(result.privacy?.listPlaintextExposed ?? 0, 0) }} 条
                </el-tag>
              </el-descriptions-item>
              <el-descriptions-item label="查询词摘要" :span="2">
                <span class="fs-mono">{{ result.queryDigest || '-' }}</span>
              </el-descriptions-item>
              <el-descriptions-item label="密文摘要（存证）" :span="2">
                <span class="fs-mono">{{ result.cipherDigest || '-' }}</span>
              </el-descriptions-item>
              <el-descriptions-item v-if="result.chainTxId" label="链上交易ID" :span="2">
                <span class="fs-mono">{{ result.chainTxId }}</span>
              </el-descriptions-item>
            </el-descriptions>

            <div v-if="result.privacy?.principle" class="fs-muted" style="margin-top: 10px">
              {{ result.privacy.principle }}
            </div>
          </template>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { engineApi } from '@/api'
import { formatDuration, formatNumber } from '@/utils/format'

const formRef = ref(null)
const loading = ref(false)
const result = ref({})

const LIST_OPTIONS = [
  { value: 'OFAC', label: 'OFAC（美国财政部海外资产控制办公室）' },
  { value: 'UN', label: '联合国安理会制裁清单' },
  { value: 'EU', label: '欧盟制裁清单' },
  { value: 'CUSTOM', label: '自定义内部黑名单' }
]

const form = reactive({
  merchantName: '',
  taxNo: '',
  // 默认勾选覆盖面最广的两份清单，与后端演示数据集保持一致
  lists: ['OFAC', 'UN'],
  mode: 'oprf'
})

const rules = {
  merchantName: [{ required: true, message: '请输入商户名称', trigger: 'blur' }],
  taxNo: [{ required: true, message: '请输入税号', trigger: 'blur' }],
  lists: [
    {
      validator: (rule, value, callback) =>
        value && value.length ? callback() : callback(new Error('请至少选择一份制裁清单')),
      trigger: 'change'
    }
  ],
  mode: [{ required: true, message: '请选择协议模式', trigger: 'change' }]
}

const hasResult = computed(() => Object.keys(result.value || {}).length > 0)

// 性能判定：后端返回 performance，若缺失则按 300ms 标准前端兜底判定
const performance = computed(() => {
  const item = result.value?.performance || {}
  const target = Number(item.target ?? 300)
  const actual = Number(item.actual ?? result.value?.elapsedMs ?? 0)
  return {
    target,
    actual,
    pass: item.pass !== undefined ? Boolean(item.pass) : actual <= target
  }
})

function handleReset() {
  formRef.value?.resetFields()
  form.lists = ['OFAC', 'UN']
  form.mode = 'oprf'
  result.value = {}
}

async function handleSubmit() {
  const valid = await formRef.value?.validate().catch(() => false)
  if (!valid) return

  loading.value = true
  try {
    // 请求体字段与 API.md §4.2 /oblivious-query 保持一致（额外携带 mode 以支持双协议切换）
    const data = await engineApi.obliviousQuery({
      merchantName: form.merchantName,
      taxNo: form.taxNo,
      lists: form.lists,
      mode: form.mode
    })
    result.value = data || {}
    ElMessage.success(result.value.hit ? '查询完成：命中制裁清单' : '查询完成：未命中制裁清单')
  } catch (error) {
    result.value = {}
  } finally {
    loading.value = false
  }
}
</script>
