
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import * as echarts from 'echarts'

/**
 * ECharts 通用容器
 * - 自适应容器尺寸变化（ResizeObserver）
 * - option 深度监听自动重绘
 * - 组件卸载时释放实例，避免内存泄漏
 */
const props = defineProps({
  option: { type: Object, default: () => ({}) },
  height: { type: [Number, String], default: 300 },
  loading: { type: Boolean, default: false },
  emptyText: { type: String, default: '暂无数据' }
})

const chartRef = ref(null)
let chart = null
let observer = null

const empty = computed(() => {
  const series = props.option?.series
  if (!series) return true
  const list = Array.isArray(series) ? series : [series]
  return list.every((item) => !item.data || item.data.length === 0)
})

function render() {
  if (!chart) return
  chart.setOption(props.option || {}, true)
}

onMounted(() => {
  chart = echarts.init(chartRef.value)
  render()
  observer = new ResizeObserver(() => chart && chart.resize())
  observer.observe(chartRef.value)
})

watch(() => props.option, render, { deep: true })
watch(
  () => props.loading,
  (value) => {
    if (!chart) return
    if (value) {
      chart.showLoading({ text: '加载中', color: '#1f5fd8', textColor: '#5c6b7f', maskColor: 'rgba(255,255,255,0.7)' })
    } else {
      chart.hideLoading()
    }
  }
)

onBeforeUnmount(() => {
  if (observer) observer.disconnect()
  if (chart) {
    chart.dispose()
    chart = null
  }
})

defineExpose({ getInstance: () => chart })
