<template>
  <div class="fs-page assistant-workspace">
    <header class="fs-page__header"><div><h1 class="fs-page__title">AI 风控助手</h1><p class="fs-page__subtitle">让结论回到交易、规则和处理记录。</p></div><el-button :disabled="busy || !messages.length" @click="clear">新对话</el-button></header>
    <div class="wb-assistant-layout">
      <aside class="wb-assistant-context"><h2>业务上下文</h2><el-select v-model="runId" :disabled="busy" placeholder="全局业务记录"><el-option label="全局业务记录" value=""/><el-option v-for="r in runs" :key="r.id" :value="r.id" :label="r.id"/></el-select><template v-if="currentRun"><dl class="wb-dl wb-dl--vertical"><div><dt>本批交易</dt><dd>{{ currentRun.count }} 笔</dd></div><div><dt>已完成阶段</dt><dd>{{ currentRun.stages.length }}/5</dd></div><div><dt>流转目的地</dt><dd>{{ currentRun.config.targetRegion }}</dd></div></dl><el-button @click="router.push('/workbench?run='+runId)">查看处理流程</el-button></template><div class="wb-assistant-questions"><h3>从这里开始</h3><button v-for="q in suggestions" :key="q" :disabled="busy" @click="send(q)"><span>{{ q }}</span><el-icon><TopRight /></el-icon></button></div></aside>
      <section class="wb-assistant-chat">
        <div ref="conversation" class="wb-chat-scroll" aria-live="polite" aria-relevant="additions text">
          <div v-if="!messages.length" class="wb-chat-welcome"><svg viewBox="0 0 64 64" aria-hidden="true"><path d="M32 5 54 15v17c0 14-11 23-22 28C21 55 10 46 10 32V15Z" fill="none" stroke="currentColor" stroke-width="2"/><path d="m21 33 8 8 16-19" fill="none" stroke="currentColor" stroke-width="2"/></svg><h2>从一笔交易，问清整个流程。</h2><p>选取处理流程，或直接询问当前业务记录。</p></div>
          <article v-for="(m,i) in messages" :key="i" :class="['wb-chat-message',m.role]"><div class="wb-chat-message__head"><strong>{{ m.role==='user'?'你':'FedShield' }}</strong><small v-if="m.mode">{{ m.mode }}</small></div><div v-if="m.tools?.length" class="wb-tool-results"><div v-for="t in m.tools" :key="t.name"><el-icon><CircleCheck /></el-icon><span>{{ t.name }}</span><code>{{ t.result }}</code></div></div><p>{{ m.text }}</p><div v-if="m.citations?.length" class="wb-citations"><span v-for="c in m.citations" :key="c.label" :title="c.value">{{ c.label }}</span></div><p v-if="m.notice" class="fs-muted">{{ m.notice }}</p><el-button v-for="a in m.actions||[]" :key="a.path" text @click="router.push(a.path)">{{ a.label }}<el-icon><TopRight /></el-icon></el-button><el-button v-if="m.retry" text :disabled="busy" @click="send(m.retry)">重试</el-button><small v-if="m.asOf" class="wb-chat-time">{{ m.asOf.replace('T',' ').slice(0,19) }}</small></article>
          <div v-if="busy" class="wb-chat-thinking" role="status"><el-icon class="is-loading"><Loading /></el-icon>检索业务依据并生成回答…</div>
        </div>
        <form class="wb-chat-composer" @submit.prevent="send(input)"><label class="wb-sr-only" for="risk-question">输入风控问题</label><textarea id="risk-question" v-model="input" maxlength="500" placeholder="输入问题，Enter 发送，Shift + Enter 换行" :disabled="busy" @keydown.enter.exact.prevent="send(input)"/><div><span>解释与建议不会自动放行交易</span><el-button type="primary" :disabled="!input.trim()" :loading="busy" native-type="submit">发送<el-icon><Promotion /></el-icon></el-button></div></form>
      </section>
    </div>
  </div>
</template>
<script setup>
import { computed,nextTick,onMounted,ref } from 'vue'
import { useRoute,useRouter } from 'vue-router'
import { assistantApi,workbenchApi } from '@/api'
const router=useRouter(),route=useRoute(),input=ref(''),topic=ref(''),busy=ref(false),messages=ref([]),runs=ref([]),runId=ref(String(route.query.run||'')),conversation=ref(null)
const currentRun=computed(()=>runs.value.find(r=>r.id===runId.value))
const suggestions=computed(()=>runId.value?['这批交易为什么被阻断？','哪些交易需要人工复核？','这次加噪消耗了多少隐私预算？','概括这批交易的处理结果']:['当前有哪些高风险预警？','支付订单有没有异常？','审核一致性怎么样？','加噪的隐私预算怎么选择？'])
async function scroll(){await nextTick();conversation.value?.scrollTo({top:conversation.value.scrollHeight,behavior:window.matchMedia('(prefers-reduced-motion: reduce)').matches?'instant':'smooth'})}
function clear(){messages.value=[];topic.value=''}
async function send(question){if(busy.value||!question?.trim())return;const q=question.trim();const context=runId.value;busy.value=true;input.value='';messages.value.push({role:'user',text:q});scroll();try{const r=context?await workbenchApi.ask({question:q,runId:context}):await assistantApi.ask({question:q,topic:topic.value});topic.value=r.topic||'';messages.value.push({role:'assistant',...r,text:r.answer})}catch{messages.value.push({role:'assistant',text:'未能取得回答，请重试。',retry:q})}finally{busy.value=false;scroll()}}
onMounted(async()=>{try{runs.value=(await workbenchApi.overview()).runs;if(runId.value&&!runs.value.some(r=>r.id===runId.value)){const r=await workbenchApi.run(runId.value);runs.value.unshift(r)}}catch{}})
</script>
