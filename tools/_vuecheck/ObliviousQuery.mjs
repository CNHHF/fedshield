
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
