<template>
  <div class="fs-sidebar">
    <div class="fs-sidebar__brand">
      <div class="fs-sidebar__logo">FS</div>
      <div v-show="!collapsed" class="fs-sidebar__title">
        <strong>FedShield</strong>
        <span>跨境隐私计算平台 v1.0</span>
      </div>
    </div>

    <el-scrollbar class="fs-sidebar__scroll">
      <el-menu
        :default-active="activePath"
        :collapse="collapsed"
        :collapse-transition="false"
        background-color="transparent"
        text-color="#b6c2d4"
        active-text-color="#ffffff"
        router
      >
        <template v-for="group in menus" :key="group.name">
          <el-sub-menu v-if="group.children.length > 1" :index="group.name">
            <template #title>
              <el-icon><component :is="group.icon" /></el-icon>
              <span>{{ group.name }}</span>
            </template>
            <el-menu-item v-for="item in group.children" :key="item.path" :index="item.path">
              <el-icon><component :is="item.icon" /></el-icon>
              <template #title>{{ item.title }}</template>
            </el-menu-item>
          </el-sub-menu>

          <el-menu-item v-else :index="group.children[0].path">
            <el-icon><component :is="group.children[0].icon" /></el-icon>
            <template #title>{{ group.children[0].title }}</template>
          </el-menu-item>
        </template>
      </el-menu>
    </el-scrollbar>

    <div v-show="!collapsed" class="fs-sidebar__footer">
      <div class="fs-sidebar__footer-item">
        <el-icon><Lock /></el-icon>
        <span>TLS1.3 双向认证 · 已连接</span>
      </div>
      <div class="fs-sidebar__footer-item">
        <el-icon><Link /></el-icon>
        <span>Fabric 存证节点 · 正常</span>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import { useUserStore } from '@/store/user'
import { buildMenus } from '@/router/routes'

defineProps({
  collapsed: { type: Boolean, default: false }
})

const route = useRoute()
const userStore = useUserStore()

const activePath = computed(() => route.path)
const menus = computed(() => buildMenus((permission) => userStore.hasPermission(permission)))
</script>

<style scoped>
.fs-sidebar {
  display: flex;
  flex-direction: column;
  height: 100%;
}
.fs-sidebar__brand {
  display: flex;
  align-items: center;
  gap: 10px;
  height: 58px;
  padding: 0 16px;
  border-bottom: 1px solid rgba(255, 255, 255, 0.06);
}
.fs-sidebar__logo {
  width: 32px;
  height: 32px;
  flex: 0 0 32px;
  border-radius: 8px;
  background: linear-gradient(135deg, #2f7bff, #14d0a0);
  color: #fff;
  font-weight: 700;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 14px;
}
.fs-sidebar__title {
  display: flex;
  flex-direction: column;
  line-height: 1.3;
  color: #fff;
  overflow: hidden;
  white-space: nowrap;
}
.fs-sidebar__title strong {
  font-size: 15px;
  letter-spacing: 0.4px;
}
.fs-sidebar__title span {
  font-size: 11px;
  color: #8798b0;
}
.fs-sidebar__scroll {
  flex: 1;
  padding: 8px 0;
}
.fs-sidebar__footer {
  padding: 10px 16px 14px;
  border-top: 1px solid rgba(255, 255, 255, 0.06);
  color: #7d8ea6;
  font-size: 11px;
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.fs-sidebar__footer-item {
  display: flex;
  align-items: center;
  gap: 6px;
}
:deep(.el-menu) {
  border-right: none;
}
:deep(.el-menu-item.is-active) {
  background: linear-gradient(90deg, rgba(47, 123, 255, 0.9), rgba(47, 123, 255, 0.35)) !important;
  border-radius: 6px;
}
:deep(.el-menu-item),
:deep(.el-sub-menu__title) {
  height: 42px;
  line-height: 42px;
  margin: 2px 8px;
  border-radius: 6px;
}
:deep(.el-menu-item:hover),
:deep(.el-sub-menu__title:hover) {
  background: rgba(255, 255, 255, 0.06) !important;
}
</style>
