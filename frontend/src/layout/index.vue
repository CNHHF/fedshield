<template>
  <el-container class="fs-layout" :class="{'nav-open':mobileOpen}" @keydown="navKey">
    <button v-if="mobileOpen" class="fs-nav-scrim" aria-label="关闭导航" @click="mobileOpen=false" />
    <el-aside ref="nav" :inert="!mobileOpen" role="dialog" aria-label="全部功能" :aria-modal="mobileOpen || undefined" :width="collapsed ? '68px' : '228px'" class="fs-layout__aside"><button class="fs-nav-close" aria-label="收起导航" @click="mobileOpen=false">×</button><Sidebar :collapsed="collapsed" @navigate="mobileOpen=false"/></el-aside>
    <el-container class="fs-layout__body" :inert="mobileOpen"><el-header class="fs-layout__header"><Navbar v-model:collapsed="collapsed" @toggle-mobile="mobileOpen=!mobileOpen"/></el-header><el-main class="fs-layout__main"><router-view v-slot="{ Component }"><component :is="Component" /></router-view></el-main></el-container>
  </el-container>
</template>
<script setup>
import { nextTick,ref,watch } from 'vue'
import Sidebar from './Sidebar.vue'
import Navbar from './Navbar.vue'
const collapsed=ref(false),mobileOpen=ref(false)
const nav=ref(null)
let previousFocus=null
const focusable=()=>Array.from(nav.value?.$el.querySelectorAll('a[href],button:not([disabled]),[tabindex="0"]') || []).filter(el=>el.getClientRects().length && getComputedStyle(el).visibility!=='hidden')
watch(mobileOpen,async open=>{if(open){previousFocus=document.activeElement;await nextTick();focusable()[0]?.focus()}else{await nextTick();previousFocus?.focus()}})
function navKey(event){if(!mobileOpen.value)return;if(event.key==='Escape'){event.preventDefault();mobileOpen.value=false;return}if(event.key==='Tab'){const items=focusable(),first=items[0],last=items.at(-1);if(!items.length)return;if(event.shiftKey&&document.activeElement===first){event.preventDefault();last.focus()}else if(!event.shiftKey&&document.activeElement===last){event.preventDefault();first.focus()}}}
</script>
<style scoped>
.fs-layout{height:100dvh;background:#f3f7f8}.fs-layout__body{min-width:0}.fs-layout__aside{background:#f3f7f8;transition:width .2s;overflow:hidden}.fs-layout__header{height:56px;padding:0;background:#f3f7f8}.fs-layout__main{margin:0 8px 8px 0;padding:0;min-width:0;background:#fff;border:1px solid #e8eaec;border-radius:16px;overflow:auto}.fs-nav-scrim{display:none}
@media(max-width:1100px){.fs-layout__aside{position:fixed;left:0;top:0;bottom:0;width:228px!important;z-index:100;transform:translateX(-100%);transition:transform .2s}.nav-open .fs-layout__aside{transform:translateX(0)}.fs-layout__main{margin-left:8px}.fs-nav-scrim{display:block;position:fixed;inset:0;border:0;background:rgba(0,0,0,.3);z-index:99}}
</style>
