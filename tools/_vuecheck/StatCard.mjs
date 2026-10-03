
import { computed } from 'vue'

const props = defineProps({
  label: { type: String, required: true },
  value: { type: [Number, String], default: 0 },
  unit: { type: String, default: '' },
  icon: { type: String, default: 'DataLine' },
  color: { type: String, default: '#1f5fd8' },
  delta: { type: [Number, String], default: null },
  deltaUnit: { type: String, default: '%' },
  deltaLabel: { type: String, default: '较上周期' },
  sub: { type: String, default: '' },
  tip: { type: String, default: '' },
  clickable: { type: Boolean, default: false },
  precision: { type: Number, default: 0 }
})

const emit = defineEmits(['click'])

const displayValue = computed(() => {
  if (typeof props.value !== 'number') return props.value
  const fixed = props.value.toFixed(props.precision)
  return Number(fixed).toLocaleString('zh-CN')
})

const iconBg = computed(() => `${props.color}1a`)
const iconColor = computed(() => props.color)

function onClick() {
  if (props.clickable) emit('click')
}
