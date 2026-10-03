<template>
  <div class="error-page">
    <div class="error-card">
      <div class="error-card__code">404</div>
      <h2 class="error-card__title">404 页面不存在</h2>
      <p class="error-card__desc">
        抱歉，您访问的页面不存在或已被移除。可能是链接输入有误、页面路径已调整，或当前角色无权访问该功能模块。
      </p>
      <div class="error-card__actions">
        <el-button type="primary" @click="goConsole">
          <el-icon><Odometer /></el-icon>
          返回控制台
        </el-button>
        <el-button @click="goBack">
          <el-icon><Back /></el-icon>
          返回上一页
        </el-button>
      </div>
      <div class="error-card__tip fs-muted">
        FedShield 跨境支付隐私计算平台 · 如需访问审计与溯源模块，请从左侧菜单进入
      </div>
    </div>
  </div>
</template>

<script setup>
import { useRouter } from 'vue-router'

const router = useRouter()

/** 返回数据概览控制台 */
function goConsole() {
  router.push('/console')
}

/** 返回上一页（无历史记录时兜底回控制台） */
function goBack() {
  if (window.history.length > 1) {
    router.back()
  } else {
    router.push('/console')
  }
}
</script>

<style scoped>
.error-page {
  min-height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 60px 20px;
}
.error-card {
  width: 100%;
  max-width: 520px;
  padding: 40px 36px;
  text-align: center;
  background: #fff;
  border: 1px solid var(--fs-border);
  border-radius: var(--fs-card-radius);
  box-shadow: var(--fs-shadow);
}
.error-card__code {
  font-size: 68px;
  font-weight: 700;
  line-height: 1;
  letter-spacing: 4px;
  color: var(--fs-primary);
  opacity: 0.9;
}
.error-card__title {
  margin: 18px 0 10px;
  font-size: 20px;
  font-weight: 600;
}
.error-card__desc {
  margin: 0;
  color: var(--fs-text-secondary);
  font-size: 13px;
  line-height: 1.8;
}
.error-card__actions {
  margin-top: 24px;
  display: flex;
  justify-content: center;
  gap: 12px;
}
.error-card__tip {
  margin-top: 22px;
  line-height: 1.7;
}
</style>
