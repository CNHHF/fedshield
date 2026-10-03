<template>
  <div class="fs-navbar">
    <div class="fs-navbar__left">
      <el-icon class="fs-navbar__collapse" @click="$emit('update:collapsed', !collapsed)">
        <component :is="collapsed ? 'Expand' : 'Fold'" />
      </el-icon>
      <el-breadcrumb separator="/">
        <el-breadcrumb-item :to="{ path: '/console' }">FedShield</el-breadcrumb-item>
        <el-breadcrumb-item v-if="currentGroup">{{ currentGroup }}</el-breadcrumb-item>
        <el-breadcrumb-item>{{ currentTitle }}</el-breadcrumb-item>
      </el-breadcrumb>
    </div>

    <div class="fs-navbar__right">
      <el-tag v-if="chainValid !== null" :type="chainValid ? 'success' : 'danger'" effect="plain" size="small">
        <el-icon><Link /></el-icon>
        联盟链存证 {{ chainValid ? '完整性正常' : '校验异常' }}
      </el-tag>

      <RoleSwitcher />

      <el-tooltip content="帮助中心" placement="bottom">
        <el-icon class="fs-navbar__icon" @click="helpVisible = true"><QuestionFilled /></el-icon>
      </el-tooltip>

      <el-dropdown @command="onCommand">
        <div class="fs-navbar__user">
          <el-avatar :size="28" class="fs-navbar__avatar">{{ avatarText }}</el-avatar>
          <div class="fs-navbar__userinfo">
            <span class="fs-navbar__username">{{ userStore.displayName }}</span>
            <span class="fs-navbar__org">{{ userStore.org || ROLE_LABELS[userStore.role] }}</span>
          </div>
          <el-icon><ArrowDown /></el-icon>
        </div>
        <template #dropdown>
          <el-dropdown-menu>
            <el-dropdown-item command="profile">
              <el-icon><User /></el-icon>当前身份与权限
            </el-dropdown-item>
            <el-dropdown-item command="sessions">
              <el-icon><Monitor /></el-icon>在线会话与异常登录
            </el-dropdown-item>
            <el-dropdown-item divided command="logout">
              <el-icon><SwitchButton /></el-icon>退出登录
            </el-dropdown-item>
          </el-dropdown-menu>
        </template>
      </el-dropdown>
    </div>

    <el-dialog v-model="helpVisible" title="帮助中心" width="620px">
      <el-alert type="info" :closable="false" show-icon title="平台定位">
        FedShield 以「原始数据不出域、可用不可见、合规可追溯」为目标，支撑跨境电商联合风控、
        外贸 B2B 黑名单匿踪查询、全球交易联合统计三大场景。
      </el-alert>
      <el-descriptions :column="1" border class="fs-navbar__help">
        <el-descriptions-item label="隐私计算任务">联邦学习、同态加密、隐匿查询、联合统计、隐私求交</el-descriptions-item>
        <el-descriptions-item label="合规校验">内置 180+ 国家/地区法规库，规则引擎可视化配置</el-descriptions-item>
        <el-descriptions-item label="权限模型">零信任动态授权，权限与任务周期绑定（最长 30 天）自动回收</el-descriptions-item>
        <el-descriptions-item label="审计存证">Hyperledger Fabric 联盟链哈希存证，GDPR 7 年 / PIPL 5 年留存</el-descriptions-item>
      </el-descriptions>
    </el-dialog>

    <el-drawer v-model="profileVisible" title="当前身份与权限" size="460px">
      <el-descriptions :column="1" border>
        <el-descriptions-item label="用户名">{{ userStore.user?.username || '-' }}</el-descriptions-item>
        <el-descriptions-item label="姓名">{{ userStore.displayName }}</el-descriptions-item>
        <el-descriptions-item label="角色">{{ ROLE_LABELS[userStore.role] || userStore.role }}</el-descriptions-item>
        <el-descriptions-item label="所属机构">{{ userStore.org || '-' }}</el-descriptions-item>
        <el-descriptions-item label="数字证书有效期">{{ userStore.user?.certExpireAt || '-' }}</el-descriptions-item>
      </el-descriptions>
      <h4>已授予权限点</h4>
      <el-tag v-for="item in userStore.permissions" :key="item" class="fs-navbar__perm" type="info" effect="plain">
        {{ item }}
      </el-tag>
    </el-drawer>

    <el-drawer v-model="sessionVisible" title="在线会话与异常登录检测" size="720px">
      <el-table :data="sessions" v-loading="sessionLoading" size="small">
        <el-table-column prop="username" label="账号" width="140" />
        <el-table-column prop="role" label="角色" width="110" />
        <el-table-column prop="region" label="登录地区" width="120" />
        <el-table-column prop="ip" label="来源 IP" width="140" />
        <el-table-column prop="loginAt" label="登录时间" min-width="160" />
        <el-table-column label="风险" width="100">
          <template #default="{ row }">
            <el-tag :type="row.risk === 'high' ? 'danger' : row.risk === 'medium' ? 'warning' : 'success'" size="small">
              {{ row.risk === 'high' ? '高危' : row.risk === 'medium' ? '关注' : '正常' }}
            </el-tag>
          </template>
        </el-table-column>
      </el-table>
      <el-alert
        class="fs-navbar__help"
        type="warning"
        :closable="false"
        show-icon
        title="熔断规则"
        description="同一账号 1 小时内跨欧盟与中国同时登录、10 分钟内超过 5 次访问 P1 级数据且未发起建模任务、未通过合规校验尝试传输数据、解密次数超当日阈值 —— 任一命中即触发分级熔断（锁定账号或暂停数据传输权限 1-24 小时）。"
      />
    </el-drawer>
  </div>
</template>

<script setup>
import { computed, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useUserStore, ROLE_LABELS } from '@/store/user'
import { auditApi, authApi } from '@/api'
import RoleSwitcher from '@/components/RoleSwitcher.vue'

const props = defineProps({
  collapsed: { type: Boolean, default: false }
})
defineEmits(['update:collapsed'])

const route = useRoute()
const router = useRouter()
const userStore = useUserStore()

const helpVisible = ref(false)
const profileVisible = ref(false)
const sessionVisible = ref(false)
const sessionLoading = ref(false)
const sessions = ref([])
const chainValid = ref(null)

const currentTitle = computed(() => route.meta?.title || '数据概览控制台')
const currentGroup = computed(() => route.meta?.group || '')
const avatarText = computed(() => (userStore.displayName || 'U').slice(0, 1).toUpperCase())

async function onCommand(command) {
  if (command === 'profile') {
    profileVisible.value = true
  } else if (command === 'sessions') {
    sessionVisible.value = true
    sessionLoading.value = true
    try {
      sessions.value = await authApi.sessions()
    } finally {
      sessionLoading.value = false
    }
  } else if (command === 'logout') {
    await ElMessageBox.confirm('确认退出登录？退出后令牌将加入黑名单并失效。', '退出登录', {
      type: 'warning'
    })
    await userStore.logout()
    ElMessage.success('已安全退出')
    router.push('/login')
  }
}

// 顶部常驻展示联盟链完整性状态（进入后台时校验一次；失败静默处理，不打扰用户）
auditApi
  .verifyChain({ silent: true })
  .then((data) => {
    chainValid.value = Boolean(data?.valid)
  })
  .catch(() => {
    chainValid.value = null
  })

void props
</script>

<style scoped>
.fs-navbar {
  height: 58px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 18px;
  gap: 16px;
}
.fs-navbar__left,
.fs-navbar__right {
  display: flex;
  align-items: center;
  gap: 14px;
}
.fs-navbar__collapse {
  font-size: 18px;
  cursor: pointer;
  color: var(--fs-text-secondary);
}
.fs-navbar__collapse:hover {
  color: var(--fs-primary);
}
.fs-navbar__icon {
  font-size: 17px;
  cursor: pointer;
  color: var(--fs-text-secondary);
}
.fs-navbar__icon:hover {
  color: var(--fs-primary);
}
.fs-navbar__user {
  display: flex;
  align-items: center;
  gap: 8px;
  cursor: pointer;
  padding: 4px 8px;
  border-radius: 8px;
}
.fs-navbar__user:hover {
  background: #f2f5fa;
}
.fs-navbar__avatar {
  background: linear-gradient(135deg, #2f7bff, #14d0a0);
  color: #fff;
  font-size: 13px;
}
.fs-navbar__userinfo {
  display: flex;
  flex-direction: column;
  line-height: 1.25;
}
.fs-navbar__username {
  font-size: 13px;
  font-weight: 600;
}
.fs-navbar__org {
  font-size: 11px;
  color: var(--fs-text-secondary);
}
.fs-navbar__help {
  margin-top: 14px;
}
.fs-navbar__perm {
  margin: 0 6px 6px 0;
}
</style>
