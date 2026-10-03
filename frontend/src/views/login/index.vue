<template>
  <div class="fs-login">
    <div class="fs-login__left">
      <div class="fs-login__brand">
        <div class="fs-login__logo">FS</div>
        <div>
          <h1>FedShield</h1>
          <p>面向全球支付场景的跨境敏感数据合规流通平台</p>
        </div>
      </div>

      <ul class="fs-login__points">
        <li v-for="item in highlights" :key="item.title">
          <el-icon :size="18"><component :is="item.icon" /></el-icon>
          <div>
            <strong>{{ item.title }}</strong>
            <span>{{ item.desc }}</span>
          </div>
        </li>
      </ul>

      <div class="fs-login__metrics">
        <div v-for="item in metrics" :key="item.label">
          <strong>{{ item.value }}</strong>
          <span>{{ item.label }}</span>
        </div>
      </div>
    </div>

    <div class="fs-login__right">
      <el-card class="fs-login__card" shadow="never">
        <h2>账号登录</h2>
        <p class="fs-login__tip">
          采用「口令 + 多因素认证 + 数字证书」三要素校验，登录行为全程上链存证
        </p>

        <el-form ref="formRef" :model="form" :rules="rules" label-position="top" @submit.prevent>
          <el-form-item label="用户名" prop="username">
            <el-input v-model="form.username" placeholder="请输入用户名" clearable>
              <template #prefix><el-icon><User /></el-icon></template>
            </el-input>
          </el-form-item>

          <el-form-item label="登录口令" prop="password">
            <el-input v-model="form.password" type="password" show-password placeholder="请输入登录口令">
              <template #prefix><el-icon><Lock /></el-icon></template>
            </el-input>
          </el-form-item>

          <el-form-item label="MFA 动态码" prop="mfaCode">
            <el-input v-model="form.mfaCode" maxlength="6" placeholder="演示环境固定为 123456">
              <template #prefix><el-icon><Cellphone /></el-icon></template>
            </el-input>
          </el-form-item>

          <el-form-item label="登录视图" prop="role">
            <el-select v-model="form.role" class="fs-login__full">
              <el-option v-for="item in roleOptions" :key="item.value" :label="item.label" :value="item.value" />
            </el-select>
          </el-form-item>

          <el-button type="primary" class="fs-login__submit" :loading="loading" @click="onSubmit">
            登录平台
          </el-button>
        </el-form>

        <el-divider>演示账号（点击快速填充）</el-divider>
        <div class="fs-login__accounts">
          <el-tag
            v-for="item in demoAccounts"
            :key="item.username"
            class="fs-login__account"
            :type="item.type"
            effect="plain"
            @click="fill(item)"
          >
            {{ item.label }}
          </el-tag>
        </div>
      </el-card>
    </div>
  </div>
</template>

<script setup>
import { reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { useUserStore } from '@/store/user'

const router = useRouter()
const route = useRoute()
const userStore = useUserStore()

const formRef = ref(null)
const loading = ref(false)

const form = reactive({
  username: 'risk.officer',
  password: 'FedShield@2026',
  mfaCode: '123456',
  role: 'pingpong',
  region: '中国'
})

const rules = {
  username: [{ required: true, message: '请输入用户名', trigger: 'blur' }],
  password: [{ required: true, message: '请输入登录口令', trigger: 'blur' }],
  mfaCode: [{ required: true, message: '请输入 MFA 动态码', trigger: 'blur' }]
}

const roleOptions = [
  { value: 'pingpong', label: 'PingPong 运营端（风控 / 合规）' },
  { value: 'merchant', label: '商户端（跨境电商 / 外贸 B2B）' },
  { value: 'regulator', label: '监管端（合规审计）' },
  { value: 'admin', label: '数据安全管理端' }
]

const demoAccounts = [
  { label: '风控技术专员', username: 'risk.officer', role: 'pingpong', type: 'primary' },
  { label: '全球合规负责人', username: 'compliance.lead', role: 'pingpong', type: 'primary' },
  { label: '跨境电商商户', username: 'merchant.demo', role: 'merchant', type: 'success' },
  { label: '欧盟监管机构', username: 'regulator.eu', role: 'regulator', type: 'warning' },
  { label: '数据安全管理员', username: 'security.admin', role: 'admin', type: 'danger' }
]

const highlights = [
  { icon: 'Lock', title: '数据可用不可见', desc: '联邦学习 + 同态加密 + 差分隐私，原始数据不出域' },
  { icon: 'DocumentChecked', title: '合规可追溯', desc: '180+ 国家/地区法规库，规则引擎自动校验与整改' },
  { icon: 'Link', title: '存证不可篡改', desc: 'Hyperledger Fabric 联盟链哈希存证，监管一键调证' },
  { icon: 'Odometer', title: '效率不低于明文 80%', desc: '参数压缩与密文聚合优化，黑名单查询响应 ≤300ms' }
]

const metrics = [
  { value: '3 大场景', label: '联合风控 / 匿踪查询 / 联合统计' },
  { value: '≤300ms', label: '黑名单查询响应' },
  { value: '7 年', label: '审计日志留存（GDPR）' }
]

function fill(item) {
  form.username = item.username
  form.role = item.role
  form.password = 'FedShield@2026'
  form.mfaCode = '123456'
  ElMessage.success(`已填充「${item.label}」演示账号`)
}

async function onSubmit() {
  const valid = await formRef.value.validate().catch(() => false)
  if (!valid) return
  loading.value = true
  try {
    await userStore.login({ ...form })
    ElMessage.success('登录成功，正在进入控制台')
    router.push(route.query.redirect || '/console')
  } catch (error) {
    // 错误提示已由 axios 拦截器统一处理
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.fs-login {
  display: grid;
  grid-template-columns: 1.15fr 0.85fr;
  min-height: 100vh;
  background: #f4f6fa;
}
.fs-login__left {
  padding: 56px 64px;
  color: #fff;
  background: linear-gradient(150deg, #0d1b34 0%, #14315e 45%, #1f5fd8 100%);
  display: flex;
  flex-direction: column;
  gap: 34px;
}
.fs-login__brand {
  display: flex;
  align-items: center;
  gap: 16px;
}
.fs-login__logo {
  width: 52px;
  height: 52px;
  border-radius: 14px;
  background: linear-gradient(135deg, #2f7bff, #14d0a0);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 20px;
  font-weight: 700;
}
.fs-login__brand h1 {
  margin: 0;
  font-size: 30px;
  letter-spacing: 1px;
}
.fs-login__brand p {
  margin: 6px 0 0;
  color: #a9bcd8;
  font-size: 14px;
}
.fs-login__points {
  list-style: none;
  padding: 0;
  margin: 0;
  display: flex;
  flex-direction: column;
  gap: 20px;
}
.fs-login__points li {
  display: flex;
  gap: 12px;
  align-items: flex-start;
}
.fs-login__points strong {
  display: block;
  font-size: 15px;
  margin-bottom: 4px;
}
.fs-login__points span {
  color: #a9bcd8;
  font-size: 13px;
  line-height: 1.6;
}
.fs-login__metrics {
  margin-top: auto;
  display: flex;
  gap: 34px;
  padding-top: 22px;
  border-top: 1px solid rgba(255, 255, 255, 0.12);
}
.fs-login__metrics strong {
  display: block;
  font-size: 20px;
}
.fs-login__metrics span {
  font-size: 12px;
  color: #a9bcd8;
}
.fs-login__right {
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 40px;
}
.fs-login__card {
  width: 100%;
  max-width: 420px;
  border-radius: 14px;
  border: 1px solid var(--fs-border);
  box-shadow: 0 12px 32px rgba(13, 27, 52, 0.08);
}
.fs-login__card h2 {
  margin: 0 0 6px;
  font-size: 20px;
}
.fs-login__tip {
  margin: 0 0 18px;
  color: var(--fs-text-secondary);
  font-size: 12px;
  line-height: 1.6;
}
.fs-login__full {
  width: 100%;
}
.fs-login__submit {
  width: 100%;
  height: 42px;
  font-size: 15px;
}
.fs-login__accounts {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}
.fs-login__account {
  cursor: pointer;
}
@media (max-width: 1024px) {
  .fs-login {
    grid-template-columns: 1fr;
  }
  .fs-login__left {
    display: none;
  }
}
</style>
