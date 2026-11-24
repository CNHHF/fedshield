<template>
  <div class="process-canvas" :class="['process-canvas--'+stage, { 'is-running': running }]" @pointermove="tilt" @pointerleave="resetTilt" ref="surface">
    <Transition name="process-change" mode="out-in">
      <div :key="stage" class="process-scene">
        <template v-if="stage==='classify'">
          <div class="data-stack" :aria-label="detail.fields?'本批实际字段分级':'字段分级规则示意'" :title="detail.fields?'本批实际字段':'执行前的字段分级规则示意'">
            <button v-for="(group,i) in groups" :key="group.level" :title="group.fields" class="data-layer" :class="{'is-selected': inspected===i}" :style="{'--layer':i}" @click="inspected=i" :aria-pressed="inspected===i">
              <span class="layer-chip">{{ group.level }}</span><strong>{{ group.title }}</strong><span>{{ group.fields }}</span><el-icon><TopRight /></el-icon>
            </button>
          </div>
          <div class="scene-copy"><strong>{{ groups[inspected].title }}</strong><p>{{ groups[inspected].description }}</p></div>
        </template>
        <template v-else-if="stage==='protect'">
          <div class="encryption-object" :class="{'show-cipher':cipherView}">
            <button class="encryption-switch" @click="cipherView=!cipherView" :aria-pressed="cipherView" :title="cipherView?'查看保护方式':'查看密文摘要'"><el-icon><Lock /></el-icon><span>{{ cipherView?'密文摘要':'分级加密' }}</span><el-icon><RefreshRight /></el-icon></button>
            <div class="cipher-display" aria-live="polite"><span v-for="(p,i) in proofs" :key="p.level"><small>{{ p.level }}</small><code>{{ cipherView ? p.digest || '运行后生成实际摘要' : p.cipher }}</code><i>{{ cipherView ? p.length ? p.length+' B' : '待执行' : ['身份与账户','金额与特征','地区与币种'][i] }}</i></span></div>
          </div>
          <div class="scene-copy"><strong>{{ detail.publication ? number(detail.publication.value)+' '+currency : '精确值加密，统计值加噪。' }}</strong><p>{{ detail.publication?'本次发布的加噪均值':'SM4 · Paillier 密钥封装 · AES-GCM' }}</p></div>
        </template>
        <template v-else-if="stage==='compliance'">
          <div class="region-route"><div><span>来源</span><strong>{{ detail.sourceRegions?.join(' / ') || '—' }}</strong></div><div class="region-connection"><svg viewBox="0 0 240 60" aria-hidden="true"><path d="M0 30C60 30 60 5 120 5s60 25 120 25"/><circle cx="120" cy="5" r="5"/></svg><span :class="{'route-blocked':detail.passed===false}">{{ detail.checks ? detail.passed?'门禁通过':'流转阻断':'等待校验' }}</span></div><div><span>目的地</span><strong>{{ target }}</strong></div></div>
          <div class="gate-dots"><span v-for="(g,i) in gates" :key="i" :class="{passed:g.passed===true,blocked:g.passed===false}"><el-icon><component :is="g.passed===false?'Close':g.passed===true?'Check':'Minus'"/></el-icon>{{ g.name }}</span></div>
        </template>
        <template v-else-if="stage==='risk'">
          <div class="risk-orbit" :style="{'--rate':(detail.automationRate || 0)*100+'%'}"><div><strong>{{ detail.counts?Math.round(detail.automationRate*100)+'%':'—' }}</strong><span>自动处理比例</span></div><svg viewBox="0 0 200 200" aria-hidden="true"><circle cx="100" cy="100" r="85"/><circle class="risk-orbit__value" cx="100" cy="100" r="85" :style="{strokeDasharray:((detail.automationRate||0)*534)+' 534'}"/></svg></div>
          <div class="risk-legend"><span v-for="(name,key) in verdicts" :key="key"><i :class="key"/><span>{{ name }}</span><strong>{{ detail.counts?.[key] ?? '—' }}</strong></span></div>
        </template>
        <template v-else>
          <div class="audit-seal" :class="{verified:detail.hash}"><svg viewBox="0 0 100 112" aria-hidden="true"><path d="M50 5 88 20v31c0 25-20 42-38 53C32 93 12 76 12 51V20Z"/><path class="seal-tick" d="m31 53 13 13 26-30"/></svg><strong>{{ detail.hash?'已完成存证':'等待存证' }}</strong></div><div class="scene-copy"><p class="seal-hash">{{ detail.hash || '完成处理后生成可核对的流程摘要' }}</p></div>
        </template>
      </div>
    </Transition>
    <div v-if="running" class="process-activity" role="status"><i/>{{ replay ? '过程回放' : '处理中' }}</div>
  </div>
</template>
<script setup>
import { computed,ref } from 'vue'
const props=defineProps({stage:{type:String,default:'classify'},detail:{type:Object,default:()=>({})},running:Boolean,replay:Boolean,currency:{type:String,default:''},target:{type:String,default:'EU'}})
const surface=ref(null),inspected=ref(0),cipherView=ref(false)
const dictionary=[{level:'P1',title:'身份与账户',fields:'商户标识 · 结算账户',description:'高敏感字段，以 SM4 加密，随机数据密钥由 Paillier 封装。'},{level:'P2',title:'金额与业务特征',fields:'交易金额 · 交易对手数',description:'精确字段使用 AES-GCM；仅统计出口单独加噪。'},{level:'P3',title:'交易属性',fields:'币种 · 地区 · 时间',description:'保留业务分析所需的属性，使用认证加密保存。'}]
const groups=computed(()=>dictionary.map(group=>({...group,fields:props.detail.fields?props.detail.fields.filter(field=>field.level===group.level).map(field=>field.name).join(' · ') || '本批无此类字段':group.fields})))
const proofs=computed(()=>props.detail.proofs || [{level:'P1',cipher:'SM4 + Paillier'},{level:'P2',cipher:'AES-256-GCM'},{level:'P3',cipher:'AES-256-GCM'}])
const gates=computed(()=>props.detail.checks || [{name:'处理授权'},{name:'传输依据'},{name:'影响评估'}])
const verdicts={approve:'自动通过',reject:'自动拒绝',manual:'人工复核',blocked:'合规阻断'}
const number=v=>Number(v).toLocaleString('zh-CN',{maximumFractionDigits:2})
function tilt(e){if(e.pointerType!=='mouse'||matchMedia('(prefers-reduced-motion: reduce)').matches)return;const b=surface.value.getBoundingClientRect();surface.value.style.setProperty('--tilt-x',((e.clientY-b.top)/b.height-.5)*-5+'deg');surface.value.style.setProperty('--tilt-y',((e.clientX-b.left)/b.width-.5)*7+'deg')}
function resetTilt(){surface.value?.style.setProperty('--tilt-x','0deg');surface.value?.style.setProperty('--tilt-y','0deg')}
</script>
