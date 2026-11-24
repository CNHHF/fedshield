<template>
  <div class="product-home">
    <header class="platform-home-heading"><div><h1>全球支付，协同风控。</h1><p>数据感知、隐私计算与决策输出。</p></div><el-button type="primary" size="large" @click="router.push(canOperate?'/workbench':'/ops/payment')">{{canOperate?'进入业务工作台':'查看业务记录'}}<el-icon><ArrowRight /></el-icon></el-button></header>
    <HomeShowcase />
    <section class="product-home__routes" aria-label="业务入口">
      <h2>按业务继续。</h2><div class="product-home__links"><router-link v-for="item in links" :key="item.path" :to="item.path"><span>{{ item.title }}</span><p>{{ item.text }}</p><el-icon><TopRight /></el-icon></router-link></div>
    </section>
    <p class="product-home__scope">本地仿真原型。模型、节点和攻击实验的演示结果，可在对应页面核对；不执行真实资金支付。</p>
  </div>
</template>
<script setup>
import { computed } from 'vue'
import { useRouter } from 'vue-router'
import { useUserStore } from '@/store/user'
import HomeShowcase from '@/components/HomeShowcase.vue'
import { buildMenus } from '@/router/routes'
const router=useRouter(),user=useUserStore()
const canOperate=computed(()=>user.hasPermission('engine:task:manage'))
const allowed=computed(()=>new Set(buildMenus(p=>user.hasPermission(p)).flatMap(group=>group.children.map(item=>item.path))))
const links=computed(()=>(canOperate.value?[
 {path:'/data',title:'数据资产',text:'原始交易、法规依据与加密样本。'},
 {path:'/compliance/rules',title:'合规规则',text:'从申报需求编排判断条件与整改动作。'},
 {path:'/ops/assistant',title:'AI 风控助手',text:'结合流程证据解释风险与预算。'},
 {path:'/lineage/audit',title:'审计追查',text:'核对已保留的操作与存证记录。'}
]:[
 {path:'/ops/payment',title:'支付记录',text:'查看订单与处理轨迹。'},
 {path:'/compliance/validate',title:'合规校验',text:'提交要件，核对规则结果。'},
 {path:'/engine/stats',title:'联合统计',text:'按授权查看聚合结果。'},
 {path:'/lineage/trace',title:'数据溯源',text:'查询数据的处理与使用记录。'}
]).filter(item=>allowed.value.has(item.path)))
</script>
<style scoped>
.product-home{max-width:1800px;padding:38px 36px}
.platform-home-heading{display:flex;align-items:center;justify-content:space-between;gap:24px;margin-bottom:30px}
.platform-home-heading h1{font-size:clamp(28px,3vw,44px);font-weight:650;letter-spacing:-1.5px;margin:0 0 10px}
.platform-home-heading p{font-size:16px;color:#6e6e73;margin:0}
.platform-home-heading>.el-button{flex-shrink:0}
.platform-home-brain{overflow-x:auto;border-radius:24px;background:#fff}
.platform-home-brain :deep(.fs-brain--embedded){min-width:900px}
.platform-home-brain :deep(.fs-brain__board-card){margin:0;border:0;box-shadow:none}
.platform-home-brain :deep(.fs-card__header){flex-wrap:wrap;gap:16px}
@media(max-width:650px){.product-home{padding:24px 16px}.platform-home-heading{align-items:flex-start;flex-direction:column;gap:18px}.platform-home-heading h1{letter-spacing:-1px}.platform-home-heading p{font-size:14px}}
</style>
