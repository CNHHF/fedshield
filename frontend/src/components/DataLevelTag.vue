<template>
  <el-tag size="small" effect="plain" :class="`fs-tag--${String(level).toLowerCase()}`">
    {{ level }} · {{ LEVEL_NAMES[level] || '' }}
  </el-tag>
</template>

<script setup>
defineProps({
  level: { type: String, default: 'P3' }
})

// 数据分级说明（与后端 crypto/policy.py 的 LEVEL_META 保持一致）
const LEVEL_NAMES = {
  P1: '高敏感',
  P2: '中敏感',
  P3: '低敏感'
}
</script>
