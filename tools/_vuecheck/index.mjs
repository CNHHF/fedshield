
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
    ElMessage.success('登录成功，正在进入 AI 风控大脑')
    router.push(route.query.redirect || '/brain')
  } catch (error) {
    // 错误提示已由 axios 拦截器统一处理
  } finally {
    loading.value = false
  }
}
