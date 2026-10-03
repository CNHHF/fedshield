<template>
  <div class="fs-stat" :class="{ 'fs-stat--clickable': clickable }" @click="onClick">
    <div class="fs-stat__icon" :style="{ background: iconBg, color: iconColor }">
      <el-icon :size="20"><component :is="icon" /></el-icon>
    </div>
    <div class="fs-stat__body">
      <div class="fs-stat__label">
        {{ label }}
        <el-tooltip v-if="tip" :content="tip" placement="top">
          <el-icon class="fs-stat__tip"><InfoFilled /></el-icon>
        </el-tooltip>
      </div>
      <div class="fs-stat__value">
        <span class="fs-stat__number">{{ displayValue }}</span>
        <span v-if="unit" class="fs-stat__unit">{{ unit }}</span>
      </div>
      <div v-if="delta !== null && delta !== undefined" class="fs-stat__delta">
        <el-icon :color="delta >= 0 ? '#14a37f' : '#e5484d'">
          <component :is="delta >= 0 ? 'CaretTop' : 'CaretBottom'" />
        </el-icon>
        <span :style="{ color: delta >= 0 ? '#14a37f' : '#e5484d' }">{{ Math.abs(delta) }}{{ deltaUnit }}</span>
        <span class="fs-stat__delta-label">{{ deltaLabel }}</span>
      </div>
      <div v-else-if="sub" class="fs-stat__sub">{{ sub }}</div>
    </div>
  </div>
</template>

<script setup>
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
</script>

<style scoped>
.fs-stat {
  display: flex;
  gap: 14px;
  align-items: flex-start;
  padding: 16px 18px;
  background: #fff;
  border: 1px solid var(--fs-border);
  border-radius: var(--fs-card-radius);
  box-shadow: var(--fs-shadow);
  transition: transform 0.18s ease, box-shadow 0.18s ease;
}
.fs-stat--clickable {
  cursor: pointer;
}
.fs-stat--clickable:hover {
  transform: translateY(-2px);
  box-shadow: 0 6px 18px rgba(31, 39, 51, 0.1);
}
.fs-stat__icon {
  width: 42px;
  height: 42px;
  flex: 0 0 42px;
  border-radius: 10px;
  display: flex;
  align-items: center;
  justify-content: center;
}
.fs-stat__body {
  min-width: 0;
  flex: 1;
}
.fs-stat__label {
  display: flex;
  align-items: center;
  gap: 4px;
  color: var(--fs-text-secondary);
  font-size: 13px;
}
.fs-stat__tip {
  font-size: 12px;
  cursor: help;
}
.fs-stat__value {
  margin-top: 6px;
  display: flex;
  align-items: baseline;
  gap: 4px;
}
.fs-stat__number {
  font-size: 24px;
  font-weight: 600;
  letter-spacing: 0.2px;
  line-height: 1.1;
}
.fs-stat__unit {
  font-size: 12px;
  color: var(--fs-text-secondary);
}
.fs-stat__delta {
  margin-top: 6px;
  display: flex;
  align-items: center;
  gap: 4px;
  font-size: 12px;
}
.fs-stat__delta-label {
  color: var(--fs-text-secondary);
}
.fs-stat__sub {
  margin-top: 6px;
  font-size: 12px;
  color: var(--fs-text-secondary);
}
</style>
