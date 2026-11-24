<template>
  <div class="fs-page security-lab">
    <header class="fs-page__header"><div><h1 class="fs-page__title">安全实验室</h1><p class="fs-page__subtitle">用可复现的对照，检验保护机制的边界。</p></div><el-button @click="router.push('/workbench')">返回业务流程</el-button></header>
    <div class="wb-lab-controls"><el-select v-model="runId" placeholder="选择已加密的流程" style="width:min(390px,100%)"><el-option v-for="r in readyRuns" :key="r.id" :value="r.id" :label="`${r.id} · ${r.count} 笔`"/></el-select><el-radio-group v-model="kind" :disabled="busy"><el-radio-button value="tamper">传输篡改</el-radio-button><el-radio-button value="poisoning">模型投毒</el-radio-button></el-radio-group><el-button type="primary" :disabled="!runId" :loading="busy" @click="execute">运行隔离实验</el-button></div>
    <p v-if="error" class="wb-negative" role="alert">{{ error }}<el-button text @click="load">重试</el-button></p>
    <div v-if="!readyRuns.length && !loading" class="wb-empty">请先完成一个流程的加密阶段。<el-button text @click="router.push('/workbench')">前往工作台</el-button></div>
    <section class="wb-lab-stage" :aria-busy="busy">
      <div class="wb-lab-path" :class="{running:busy}"><div><el-icon><Coin /></el-icon><strong>{{ kind==='tamper'?'密文副本':'5 个仿真节点' }}</strong></div><span class="wb-lab-wire"/><div class="wb-lab-attack"><el-icon><Aim /></el-icon><strong>{{ kind==='tamper'?'修改一个字节':'单节点注入异常更新' }}</strong></div><span class="wb-lab-wire"/><div><el-icon><CircleCheck /></el-icon><strong>{{ kind==='tamper'?'认证校验':'聚合方法对照' }}</strong></div></div>
      <div v-if="busy" class="wb-lab-status" role="status">正在隔离副本上执行检测…</div>
      <template v-else-if="result && result.kind===kind">
        <div class="wb-section-head"><h2>{{ result.title }}</h2><span class="fs-mono">{{ result.id }}</span></div>
        <template v-if="kind==='tamper'"><div class="wb-compare"><div v-for="c in result.checks" :key="c.name"><span>{{ c.name }}</span><strong :class="c.safe?'wb-positive':'wb-negative'">{{ c.outcome }}</strong></div></div><dl class="wb-dl"><div><dt>检测耗时</dt><dd>{{ result.elapsedMs }} ms</dd></div><div><dt>原密文</dt><dd>{{ result.originalIntact?'保持完整':'校验异常' }}</dd></div></dl><div class="wb-hash-pair"><div><span>篡改前摘要</span><code>{{ result.beforeHash }}</code></div><div><span>篡改后摘要</span><code>{{ result.afterHash }}</code></div></div></template>
        <template v-else><div class="wb-compare"><div><span>普通均值聚合偏差</span><strong>{{ result.meanDeviation }}</strong></div><div><span>坐标中位数聚合偏差</span><strong class="wb-positive">{{ result.medianDeviation }}</strong></div></div><ChartBox :option="chart" :height="240"/><p class="wb-source-note">偏差为聚合更新相对干净均值的 L2 距离，越小越接近基线；本次降低 {{ (result.improvement*100).toFixed(1) }}%。</p><a class="wb-reference" href="https://proceedings.mlr.press/v80/yin18a.html" target="_blank" rel="noopener">方法参考：Yin 等，ICML 2018</a></template>
        <p class="wb-source-note">{{ result.scope }}</p>
      </template>
      <div v-else class="wb-empty">{{ kind==='tamper'?'在密文副本上翻转字节，比较未认证传输与认证加密的检测结果。':'对固定仿真更新注入单节点投毒，对比普通均值和坐标中位数的聚合偏差。' }}</div>
    </section>
    <el-collapse class="wb-disclosure"><el-collapse-item title="实验边界" name="scope"><p>实验不发送外部攻击，不修改原始交易或密文库。模型投毒对照是独立的合成更新实验，未接入现有联邦训练调度；加密与差分隐私本身不能阻止恶意节点投毒。一次试验不能证明完整安全性。</p></el-collapse-item></el-collapse>
  </div>
</template>
<script setup>
import { computed,onMounted,ref } from 'vue'
import { useRoute,useRouter } from 'vue-router'
import { workbenchApi } from '@/api'
import ChartBox from '@/components/ChartBox.vue'
const route=useRoute(),router=useRouter(),runId=ref(String(route.query.run||'')),runs=ref([]),kind=ref('tamper'),result=ref(null),busy=ref(false),loading=ref(true),error=ref('')
const readyRuns=computed(()=>runs.value.filter(r=>r.stages.some(s=>s.key==='protect')))
const chart=computed(()=>({tooltip:{trigger:'axis'},grid:{left:50,right:24,top:38,bottom:38},xAxis:{type:'category',data:result.value?.updates?.map(r=>r.node)||[],axisLabel:{color:'#627078',fontSize:12},axisTick:{show:false},axisLine:{lineStyle:{color:'#e5e7eb'}}},yAxis:{type:'value',name:'更新 L2 范数',splitNumber:4,nameTextStyle:{color:'#627078',fontSize:12},axisLabel:{fontSize:12,color:'#627078'},splitLine:{lineStyle:{color:'#eef0f2'}}},series:[{type:'bar',barMaxWidth:34,data:result.value?.updates?.map(r=>({value:r.norm,itemStyle:{color:r.malicious?'#b23b3b':'#1b6c80'}}))||[]}]}))
async function load(){loading.value=true;error.value='';try{runs.value=(await workbenchApi.overview()).runs;if(!runId.value)runId.value=readyRuns.value[0]?.id||''}catch{error.value='流程列表读取失败。'}finally{loading.value=false}}
async function execute(){if(busy.value)return;busy.value=true;error.value='';try{result.value=await workbenchApi.experiment({runId:runId.value,kind:kind.value})}catch(e){error.value=e.message||'实验未完成，请重试。'}finally{busy.value=false}}
onMounted(load)
</script>
