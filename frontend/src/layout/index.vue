<template>
  <el-container class="fs-layout">
    <el-aside :width="collapsed ? '64px' : '224px'" class="fs-layout__aside">
      <Sidebar :collapsed="collapsed" />
    </el-aside>

    <el-container>
      <el-header class="fs-layout__header">
        <Navbar v-model:collapsed="collapsed" />
      </el-header>
      <el-main class="fs-layout__main">
        <router-view v-slot="{ Component }">
          <transition name="fade-slide" mode="out-in">
            <component :is="Component" />
          </transition>
        </router-view>
      </el-main>
    </el-container>
  </el-container>
</template>

<script setup>
import { ref } from 'vue'
import Sidebar from './Sidebar.vue'
import Navbar from './Navbar.vue'

const collapsed = ref(false)
</script>

<style scoped>
.fs-layout {
  height: 100vh;
}
.fs-layout__aside {
  background: var(--fs-sidebar-bg);
  transition: width 0.22s ease;
  overflow: hidden;
}
.fs-layout__header {
  height: 58px;
  padding: 0;
  background: #fff;
  border-bottom: 1px solid var(--fs-border);
  box-shadow: 0 1px 4px rgba(31, 39, 51, 0.04);
  z-index: 10;
}
.fs-layout__main {
  padding: 0;
  background: var(--fs-bg);
  overflow-y: auto;
}
.fade-slide-enter-active,
.fade-slide-leave-active {
  transition: all 0.2s ease;
}
.fade-slide-enter-from {
  opacity: 0;
  transform: translateY(10px);
}
.fade-slide-leave-to {
  opacity: 0;
}
</style>
