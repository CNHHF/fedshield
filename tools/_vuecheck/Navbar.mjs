
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

const currentTitle = computed(() => route.meta?.title || 'AI 风控大脑')
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
