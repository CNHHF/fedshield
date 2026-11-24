<template>
  <nav class="fs-sidebar" aria-label="主导航">
    <router-link class="fs-sidebar__brand" :to="'/home'"><svg viewBox="0 0 36 40" width="28" height="32" aria-hidden="true"><path d="M18 2 32 8v11c0 9-7 15-14 19C11 34 4 28 4 19V8Z" fill="none" stroke="currentColor" stroke-width="2"/><path d="M12 13h13M12 13v15m0-9h10" stroke="currentColor" stroke-width="2"/></svg><strong v-show="!collapsed">FedShield</strong></router-link>
    <el-scrollbar class="fs-sidebar__scroll"><div v-if="!collapsed" class="fs-sidebar__scope">全球支付风控工作空间</div><div v-if="primary.length" class="fs-sidebar__primary"><router-link v-for="item in primary" :key="item.path" :to="item.path" :title="item.title" @click="$emit('navigate')"><el-icon><component :is="item.icon"/></el-icon><span v-show="!collapsed">{{ item.title }}</span></router-link></div>
    <el-menu :default-active="route.path" :collapse="collapsed" :collapse-transition="false" router @select="$emit('navigate')"><el-sub-menu v-for="g in groups" :key="g.name" :index="g.name"><template #title><el-icon><component :is="g.icon"/></el-icon><span>{{ g.name }}</span></template><el-menu-item v-for="item in g.children" :key="item.path" :index="item.path"><span>{{ item.title }}</span></el-menu-item></el-sub-menu></el-menu></el-scrollbar>
    <div class="fs-sidebar__footer" v-show="!collapsed"><span class="fs-sidebar__dot"/>本地演示环境</div>
  </nav>
</template>
<script setup>
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import { useUserStore } from '@/store/user'
import { buildMenus } from '@/router/routes'
defineProps({collapsed:Boolean});defineEmits(['navigate'])
const route=useRoute(),user=useUserStore()
const menus=computed(()=>buildMenus(p=>user.hasPermission(p)))
const primary=computed(()=>[...menus.value.flatMap(g=>g.children).filter(i=>['/workbench','/data','/ops/assistant'].includes(i.path))].sort((a,b)=>['/workbench','/data','/ops/assistant'].indexOf(a.path)-['/workbench','/data','/ops/assistant'].indexOf(b.path)))
const groups=computed(()=>menus.value.map(g=>({...g,children:g.children.filter(i=>!primary.value.some(p=>p.path===i.path))})).filter(g=>g.children.length))
</script>
<style scoped>
.fs-sidebar{display:flex;flex-direction:column;height:100%;color:#343b40}.fs-sidebar__brand{height:72px;padding:0 22px;display:flex;align-items:center;gap:12px;color:#1b6c80}.fs-sidebar__brand strong{font-size:20px;color:#1b292e;letter-spacing:-.5px}.fs-sidebar__scroll{flex:1}.fs-sidebar__scope{padding:8px 22px 18px;font-size:12px;color:#626d73}.fs-sidebar__primary{display:grid;gap:4px;padding:0 12px 20px}.fs-sidebar__primary a{height:40px;padding:0 12px;display:flex;gap:12px;align-items:center;border-radius:6px;color:#535e64;white-space:nowrap}.fs-sidebar__primary a:hover{background:#eaf0f1}.fs-sidebar__primary .router-link-active{background:#e3eaec;color:#152a32;font-weight:600}.fs-sidebar__primary .el-icon{font-size:18px}.fs-sidebar__footer{padding:20px 22px;font-size:12px;color:#667176;display:flex;align-items:center;gap:8px}.fs-sidebar__dot{width:6px;height:6px;border-radius:50%;background:#1b6c80}:deep(.el-menu){border:0;background:transparent;--el-menu-bg-color:transparent;--el-menu-hover-bg-color:#eaf0f1;--el-menu-text-color:#535e64;--el-menu-active-color:#152a32}:deep(.el-sub-menu__title),:deep(.el-menu-item){height:38px;line-height:38px;border-radius:6px;margin:3px 12px}:deep(.el-menu-item.is-active){background:#e3eaec;font-weight:600}:deep(.el-sub-menu .el-menu-item){padding-left:42px!important;font-size:13px}:deep(.el-menu--collapse .el-sub-menu__title){padding-left:12px!important}
</style>
