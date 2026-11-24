<template>
  <div class="fs-navbar"><div class="fs-navbar__left"><router-link class="fs-navbar__brand" :to="'/home'"><svg viewBox="0 0 36 40" aria-hidden="true"><path d="M18 2 32 8v11c0 9-7 15-14 19C11 34 4 28 4 19V8Z"/><path d="M12 13h13M12 13v15m0-9h10"/></svg><strong>FedShield</strong></router-link><nav class="fs-top-links" aria-label="工作空间"><router-link v-for="item in topLinks" :key="item.path" :to="item.path">{{ item.title }}</router-link></nav></div><div class="fs-navbar__right"><button class="fs-icon-button fs-mobile-toggle" aria-label="打开导航" title="全部功能" @click="$emit('toggle-mobile')"><el-icon><Menu /></el-icon></button><button class="fs-navbar__search" @click="openSearch" title="查找功能 Ctrl K"><el-icon><Search /></el-icon><span>搜索</span><kbd>⌘ K</kbd></button><el-dropdown @command="command"><button class="fs-navbar__user" aria-label="账号菜单" :title="user.displayName"><span>{{ user.displayName.slice(0,1) }}</span><el-icon><ArrowDown /></el-icon></button><template #dropdown><el-dropdown-menu><el-dropdown-item command="profile">身份与权限</el-dropdown-item><el-dropdown-item command="sessions">在线会话</el-dropdown-item><el-dropdown-item command="logout" divided>退出登录</el-dropdown-item></el-dropdown-menu></template></el-dropdown></div>
  <el-dialog v-model="searchOpen" title="查找功能" fullscreen append-to-body destroy-on-close class="fs-navbar-panel" @opened="searchInput?.focus()">
    <div class="fs-navbar-panel__content">
      <el-input ref="searchInput" v-model="query" size="large" placeholder="输入功能名称" clearable @keydown.enter.prevent="navigate(matches[0])"/>
      <div class="fs-command-results fs-panel-search-results">
        <button v-for="m in matches" :key="m.path" @click="navigate(m)"><el-icon><component :is="m.icon"/></el-icon><span>{{ m.title }}</span><small>{{ m.group }}</small></button>
        <p v-if="!matches.length">没有匹配功能</p>
      </div>
    </div>
  </el-dialog>
  <el-dialog v-model="profileOpen" title="身份与权限" fullscreen append-to-body destroy-on-close class="fs-navbar-panel">
    <div class="fs-navbar-panel__content fs-panel-profile">
      <div class="fs-panel-identity"><h2>{{ user.displayName }}</h2><p>{{ ROLE_LABELS[user.role] }}</p><p>{{ user.org }}</p></div>
      <section aria-labelledby="profile-permissions-title"><h2 id="profile-permissions-title">权限</h2><div class="fs-panel-permissions"><el-tag v-for="p in user.permissions" :key="p" type="info">{{ p }}</el-tag></div></section>
    </div>
  </el-dialog>
  <el-dialog v-model="sessionsOpen" title="在线会话" fullscreen append-to-body destroy-on-close class="fs-navbar-panel">
    <div class="fs-navbar-panel__content"><el-table v-loading="sessionsLoading" :data="sessions" style="width:100%"><el-table-column prop="username" label="账号" min-width="140"/><el-table-column prop="region" label="地区" width="90"/><el-table-column prop="ip" label="来源 IP" min-width="140"/><el-table-column prop="loginAt" label="登录时间" min-width="170"/></el-table></div>
  </el-dialog>
  </div>
</template>
<script setup>
import { computed,nextTick,onBeforeUnmount,onMounted,ref } from 'vue'
import { useRoute,useRouter } from 'vue-router'
import { useUserStore,ROLE_LABELS } from '@/store/user'
import { buildMenus } from '@/router/routes'
import { authApi } from '@/api'
defineProps({collapsed:Boolean});defineEmits(['update:collapsed','toggle-mobile'])
const route=useRoute(),router=useRouter(),user=useUserStore(),searchOpen=ref(false),query=ref(''),searchInput=ref(null),profileOpen=ref(false),sessionsOpen=ref(false),sessions=ref([]),sessionsLoading=ref(false)
const topLinks=computed(()=>buildMenus(p=>user.hasPermission(p)).flatMap(g=>g.children).filter(m=>['/home','/workbench','/data','/ops/assistant'].includes(m.path)))
const matches=computed(()=>buildMenus(p=>user.hasPermission(p)).flatMap(g=>g.children.map(m=>({...m,group:g.name}))).filter(m=>(m.title+m.group).includes(query.value)).slice(0,12))
function openSearch(){profileOpen.value=false;sessionsOpen.value=false;searchOpen.value=true;query.value=''}
function shortcut(e){if((e.ctrlKey||e.metaKey)&&e.key.toLowerCase()==='k'){e.preventDefault();openSearch()}}
function navigate(m){if(!m)return;router.push(m.path);searchOpen.value=false}
async function command(c){searchOpen.value=false;profileOpen.value=c==='profile';sessionsOpen.value=c==='sessions';if(c==='sessions'){sessionsLoading.value=true;try{sessions.value=await authApi.sessions()}catch{sessions.value=[]}finally{sessionsLoading.value=false}}else if(c==='logout'){await user.logout();router.push('/login')}}
onMounted(()=>window.addEventListener('keydown',shortcut));onBeforeUnmount(()=>window.removeEventListener('keydown',shortcut))
</script>
<style scoped>
.fs-navbar{height:56px;display:flex;align-items:center;justify-content:space-between;padding:0 24px;gap:20px;font-size:13px}.fs-navbar__left,.fs-navbar__right{display:flex;align-items:center;gap:14px;min-width:0}.fs-navbar__location,.fs-navbar__separator{color:#647079}.fs-icon-button{border:0;background:transparent;color:#536067;width:32px;height:32px;cursor:pointer;font-size:18px;display:grid;place-items:center}.fs-navbar__search{display:flex;align-items:center;gap:10px;background:transparent;border:1px solid #d7dfe1;border-radius:6px;padding:6px 10px;color:#58666c;cursor:pointer}.fs-navbar__search kbd{margin-left:24px;font:11px inherit}.fs-navbar__user{border:0;background:transparent;display:flex;align-items:center;gap:10px;cursor:pointer;color:#343f44}.fs-navbar__user>span{width:28px;height:28px;display:grid;place-items:center;background:#e0e8eb;border-radius:50%;font-size:12px}.fs-navbar__user strong{font-size:13px;font-weight:500}.fs-command-results{display:grid;margin-top:16px}.fs-command-results button{display:flex;align-items:center;gap:14px;text-align:left;border:0;border-radius:6px;background:transparent;padding:13px;cursor:pointer;color:#243840}.fs-command-results button:hover,.fs-command-results button:focus-visible{background:#edf2f3}.fs-command-results small{margin-left:auto;color:#65737a}.fs-permission{margin:6px}.fs-mobile-toggle{display:none}@media(max-width:1100px){.fs-desktop-toggle{display:none}.fs-mobile-toggle{display:grid}}@media(max-width:640px){.fs-navbar{padding:0 16px}.fs-navbar__location,.fs-navbar__separator,.fs-navbar__search span,.fs-navbar__search kbd,.fs-navbar__user strong{display:none}.fs-navbar__search{border:0}.fs-navbar__right{gap:8px}}
</style>
