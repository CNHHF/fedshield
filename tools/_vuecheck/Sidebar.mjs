
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
