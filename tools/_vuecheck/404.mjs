
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
