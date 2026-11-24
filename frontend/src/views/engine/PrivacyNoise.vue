<template>
  <div class="fs-page privacy-page">
    <div class="fs-page__header"><div><h2 class="fs-page__title">加噪隐私处理</h2><p class="fs-page__subtitle">裁剪数值 → 计算统计量 → 拉普拉斯加噪 → 扣减隐私预算 → 发布结果</p></div></div>
    <div class="privacy-layout">
      <section class="fs-card fs-card__body">
        <h3>发布设置</h3>
        <el-form label-position="top" @submit.prevent="submit">
          <el-form-item label="待处理数值（以逗号、空格或换行分隔，2–1000 条）"><el-input v-model="values" type="textarea" :rows="5" placeholder="输入演示数值" /></el-form-item>
          <el-button text @click="values = '42, 58, 63, 77, 51, 69, 86, 34'">填入演示数据</el-button>
          <div class="bounds"><el-form-item label="公开裁剪下界"><el-input-number v-model="form.lower" /></el-form-item><el-form-item label="公开裁剪上界"><el-input-number v-model="form.upper" /></el-form-item></div>
          <el-form-item label="统计类型"><el-radio-group v-model="form.statistic"><el-radio value="mean">均值</el-radio><el-radio value="sum">总和</el-radio></el-radio-group></el-form-item>
          <el-form-item label="本次消耗 ε（越小，噪声越大）"><el-input-number v-model="form.epsilon" :min="0.01" :max="10" :step="0.1" :precision="2" /></el-form-item>
          <el-form-item label="扣减的隐私预算项目"><el-select v-model="form.budgetId" :loading="loading" placeholder="选择预算项目"><el-option v-for="b in budgets" :key="b.id" :value="b.id" :label="`${b.project}（剩余 ε ${b.remaining}）`" /></el-select><el-button text @click="loadBudgets">刷新额度</el-button></el-form-item>
          <p v-if="loadError" role="alert">预算读取失败，请刷新重试。</p>
          <p v-else-if="!loading && !budgets.length" class="fs-muted">暂无预算项目，请先在隐私预算管理中配置额度。</p>
          <p v-if="error" role="alert" class="error">{{ error }}</p>
          <el-button type="primary" @click="submit" :loading="busy" :disabled="!form.budgetId || !values.trim()">扣减 ε 并发布加噪结果</el-button>
        </el-form>
      </section>
      <section class="fs-card fs-card__body" aria-live="polite">
        <h3>发布结果</h3><el-empty v-if="!result" description="设置参数后发布，原始统计量不会显示" />
        <template v-else><p class="fs-muted">{{ result.statistic === 'mean' ? '加噪均值' : '加噪总和' }}</p><div class="released-value">{{ result.value.toFixed(4) }}</div><el-descriptions :column="1" border><el-descriptions-item label="本次消耗 ε">{{ result.epsilon }}</el-descriptions-item><el-descriptions-item label="敏感度 Δ">{{ result.sensitivity.toFixed(6) }}</el-descriptions-item><el-descriptions-item label="噪声尺度 Δ/ε">{{ result.noiseScale.toFixed(6) }}</el-descriptions-item><el-descriptions-item label="裁剪范围">[{{ result.lower }}, {{ result.upper }}]</el-descriptions-item><el-descriptions-item label="项目剩余 ε">{{ result.budget.remaining }}</el-descriptions-item></el-descriptions><p>{{ result.note }}</p></template>
        <p class="fs-muted explanation">保护口径：固定样本量、替换一条记录，每条记录为一个保护单元。公开上下界须在分析前确定；多条记录属于同一主体时，此处不代表主体级保护。每次点击均产生一次新发布并消耗 ε。输出可能超出原始范围，不作无说明的截断。</p>
      </section>
    </div>
  </div>
</template>
<script setup>
import { onMounted, reactive, ref } from 'vue'
import { assistantApi, budgetApi } from '@/api'
const values = ref(''), budgets = ref([]), result = ref(null), busy = ref(false), loading = ref(false), loadError = ref(false), error = ref('')
const form = reactive({ lower: 0, upper: 100, epsilon: 1, statistic: 'mean', budgetId: null })
async function loadBudgets() {
  loading.value = true; loadError.value = false
  try { budgets.value = await budgetApi.items() || []; if (!form.budgetId) form.budgetId = budgets.value[0]?.id ?? null }
  catch { loadError.value = true } finally { loading.value = false }
}
async function submit() {
  if (busy.value) return
  error.value = ''
  const parsed = values.value.trim().split(/[\s,，;；]+/).map(Number)
  if (parsed.length < 2 || parsed.length > 1000 || parsed.some(x => !Number.isFinite(x))) { error.value = '请输入 2–1000 个有效数值。'; return }
  if (!(form.lower < form.upper)) { error.value = '裁剪下界必须小于上界。'; return }
  busy.value = true; result.value = null
  try { result.value = await assistantApi.privacyRelease({ ...form, values: parsed }); await loadBudgets() }
  catch { error.value = '本次未取得发布结果，请核对提示与预算额度后重试。' }
  finally { busy.value = false }
}
onMounted(loadBudgets)
</script>
<style scoped>
.privacy-layout { display: grid; grid-template-columns: minmax(0, 1fr) minmax(0, 1fr); gap: 20px; }.bounds { display: flex; flex-wrap: wrap; gap: 22px; margin-top: 16px; }.released-value { font-size: 32px; font-variant-numeric: tabular-nums; color: #1f5fd8; margin: 16px 0 26px; overflow-wrap: anywhere; }.explanation { line-height: 1.8; margin-top: 24px; }.error { color: #b42318; }@media(max-width:900px){.privacy-layout { grid-template-columns: 1fr; }}
</style>

