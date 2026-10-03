
import { computed, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { engineApi } from '@/api'
import { formatDuration, formatNumber, formatPercent } from '@/utils/format'

const loading = ref(false)
const result = ref({})
const leftText = ref('')
const rightText = ref('')

/** 文本域按行拆分为集合元素：去空白、去空行，保证提交的长度口径与后端一致 */
function toItems(text) {
  return String(text || '')
    .split('\n')
    .map((item) => item.trim())
    .filter(Boolean)
}

const leftItems = computed(() => toItems(leftText.value))
const rightItems = computed(() => toItems(rightText.value))
const hasResult = computed(() => Object.keys(result.value || {}).length > 0)

// 重叠率 = 交集 / 本方规模，反映本方白名单在对方清单中的命中比例
const overlapRatio = computed(() => {
  const size = Number(result.value?.leftSize ?? leftItems.value.length) || 0
  if (!size) return 0
  return Number(result.value?.intersectionSize ?? 0) / size
})

function loadSample() {
  leftText.value = [
    '深圳跨境优选电商有限公司',
    '91440300MA5EX00001',
    '广州海丝供应链管理有限公司',
    '91440101MA5CX00002',
    '杭州云桥数字科技有限公司',
    '义乌小商品出口贸易行'
  ].join('\n')

  rightText.value = [
    '91440300MA5EX00001',
    '上海泓远国际贸易有限公司',
    '91440101MA5CX00002',
    '北京中欧通供应链有限公司',
    '义乌小商品出口贸易行',
    'Shenzhen Global Trade Co., Ltd.'
  ].join('\n')

  ElMessage.success('已载入示例数据，可直接执行隐私求交')
}

async function handleSubmit() {
  if (!leftItems.value.length || !rightItems.value.length) {
    ElMessage.warning('请先在左右两侧各输入至少一条集合元素')
    return
  }

  loading.value = true
  try {
    const data = await engineApi.psi({ left: leftItems.value, right: rightItems.value })
    result.value = data || {}
    ElMessage.success(`隐私求交完成，交集 ${result.value.intersectionSize ?? 0} 条`)
  } catch (error) {
    result.value = {}
  } finally {
    loading.value = false
  }
}
