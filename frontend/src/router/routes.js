import Layout from '@/layout/index.vue'

/**
 * 路由表（独立模块，供 router/index.js 与侧边菜单共同使用，避免循环依赖）
 *
 * meta.title      菜单/面包屑标题
 * meta.icon       Element Plus 图标组件名（main.js 已全量注册）
 * meta.permission 访问所需权限点（与后端 backend/api/deps.py 的 PERMISSION_MATRIX 一致）
 * meta.hidden     是否在侧边菜单中隐藏
 * meta.group      菜单分组名
 */
export const routes = [
  {
    path: '/login',
    name: 'Login',
    component: () => import('@/views/login/index.vue'),
    meta: { title: '登录', hidden: true, public: true }
  },
  {
    path: '/',
    component: Layout,
    redirect: '/brain',
    children: [
      {
        path: 'brain',
        name: 'Brain',
        component: () => import('@/views/brain/index.vue'),
        meta: { title: 'AI 风控大脑', icon: 'Cpu', group: '智能大脑' }
      },
      {
        path: 'home',
        name: 'Home',
        component: () => import('@/views/home/index.vue'),
        meta: { title: '平台首页', icon: 'HomeFilled', group: '智能大脑' }
      },
      {
        path: 'console',
        name: 'Console',
        component: () => import('@/views/console/index.vue'),
        meta: { title: '数据概览控制台', icon: 'Odometer', group: '智能大脑' }
      }
    ]
  },
  {
    path: '/engine',
    component: Layout,
    redirect: '/engine/tasks',
    children: [
      {
        path: 'tasks',
        name: 'EngineTasks',
        component: () => import('@/views/engine/TaskList.vue'),
        meta: { title: '计算任务管理', icon: 'List', group: '隐私计算', permission: 'engine:task:manage' }
      },
      {
        path: 'create',
        name: 'EngineTaskCreate',
        component: () => import('@/views/engine/TaskCreate.vue'),
        meta: { title: '新建计算任务', icon: 'MagicStick', group: '隐私计算', permission: 'engine:task:create' }
      },
      {
        path: 'result/:id?',
        name: 'EngineResult',
        component: () => import('@/views/engine/TaskResult.vue'),
        meta: { title: '计算结果分析', icon: 'DataAnalysis', group: '隐私计算' }
      },
      {
        path: 'query',
        name: 'EngineQuery',
        component: () => import('@/views/engine/ObliviousQuery.vue'),
        meta: { title: '黑名单匿踪查询', icon: 'Search', group: '隐私计算', permission: 'engine:query:oblivious' }
      },
      {
        path: 'stats',
        name: 'EngineStats',
        component: () => import('@/views/engine/JointStats.vue'),
        meta: { title: '全球交易联合统计', icon: 'PieChart', group: '隐私计算', permission: 'engine:stats:joint' }
      },
      {
        path: 'psi',
        name: 'EnginePsi',
        component: () => import('@/views/engine/PsiPanel.vue'),
        meta: { title: '隐私求交集', icon: 'Connection', group: '隐私计算' }
      }
    ]
  },
  {
    path: '/compliance',
    component: Layout,
    redirect: '/compliance/rules',
    children: [
      {
        path: 'rules',
        name: 'ComplianceRules',
        component: () => import('@/views/compliance/RuleEngine.vue'),
        meta: { title: '规则引擎配置', icon: 'SetUp', group: '合规管控', permission: 'compliance:rule:manage' }
      },
      {
        path: 'validate',
        name: 'ComplianceValidate',
        component: () => import('@/views/compliance/ComplianceCheck.vue'),
        meta: { title: '跨境合规校验', icon: 'CircleCheck', group: '合规管控' }
      },
      {
        path: 'reports',
        name: 'ComplianceReports',
        component: () => import('@/views/compliance/ReportList.vue'),
        meta: { title: '合规报告管理', icon: 'Document', group: '合规管控', permission: 'compliance:report:view' }
      },
      {
        path: 'reports/create',
        name: 'ComplianceReportCreate',
        component: () => import('@/views/compliance/ReportGenerate.vue'),
        meta: { title: '生成合规报告', icon: 'DocumentAdd', group: '合规管控', permission: 'compliance:report:create' }
      },
      {
        path: 'reports/:id',
        name: 'ComplianceReportPreview',
        component: () => import('@/views/compliance/ReportPreview.vue'),
        meta: { title: '报告预览', hidden: true, permission: 'compliance:report:view' }
      },
      {
        path: 'trend',
        name: 'ComplianceTrend',
        component: () => import('@/views/compliance/ComplianceTrend.vue'),
        meta: { title: '合规趋势与预警', icon: 'TrendCharts', group: '合规管控' }
      }
    ]
  },
  {
    path: '/authz',
    component: Layout,
    redirect: '/authz/grants',
    children: [
      {
        path: 'grants',
        name: 'AuthzGrants',
        component: () => import('@/views/authz/GrantManage.vue'),
        meta: { title: '数据授权管理', icon: 'Key', group: '权限与预算', permission: 'authz:grant:view' }
      },
      {
        path: 'budget',
        name: 'BudgetOverview',
        component: () => import('@/views/budget/BudgetOverview.vue'),
        meta: { title: '隐私预算管理', icon: 'Wallet', group: '权限与预算', permission: 'budget:manage' }
      },
      {
        path: 'budget/detail',
        name: 'BudgetDetail',
        component: () => import('@/views/budget/BudgetDetail.vue'),
        meta: { title: '预算分配明细', icon: 'Tickets', group: '权限与预算', permission: 'budget:manage' }
      }
    ]
  },
  {
    path: '/lineage',
    component: Layout,
    redirect: '/lineage/graph',
    children: [
      {
        path: 'graph',
        name: 'LineageGraph',
        component: () => import('@/views/lineage/LineageGraph.vue'),
        meta: { title: '数据血缘图谱', icon: 'Share', group: '审计与溯源', permission: 'lineage:view' }
      },
      {
        path: 'trace',
        name: 'LineageTrace',
        component: () => import('@/views/lineage/TraceDetail.vue'),
        meta: { title: '数据溯源查询', icon: 'Location', group: '审计与溯源', permission: 'lineage:view' }
      },
      {
        path: 'audit',
        name: 'LineageAudit',
        component: () => import('@/views/lineage/AuditRecords.vue'),
        meta: { title: '审计记录与存证', icon: 'Files', group: '审计与溯源', permission: 'audit:view' }
      }
    ]
  },
  {
    path: '/:pathMatch(.*)*',
    name: 'NotFound',
    component: () => import('@/views/error/404.vue'),
    meta: { title: '页面不存在', hidden: true, public: true }
  }
]

/**
 * 生成侧边菜单结构：[{ name, icon, children: [{ path, title, icon, permission }] }]
 * - 过滤 hidden 路由与无权限项
 * - 权限判断由调用方传入的 hasPermission 函数完成
 */
export function buildMenus(hasPermission) {
  const groups = []
  routes.forEach((route) => {
    const children = (route.children || []).filter(
      (child) => !child.meta?.hidden && hasPermission(child.meta?.permission)
    )
    if (!children.length) return
    const groupName = children[0].meta?.group || '其他'
    let group = groups.find((item) => item.name === groupName)
    if (!group) {
      group = { name: groupName, icon: children[0].meta?.icon || 'Menu', children: [] }
      groups.push(group)
    }
    children.forEach((child) => {
      group.children.push({
        path: `${route.path === '/' ? '' : route.path}/${child.path}`,
        title: child.meta.title,
        icon: child.meta.icon || 'Menu',
        permission: child.meta.permission
      })
    })
  })
  // 分组图标取该组第一个菜单项的图标，单子项分组退化为直接菜单项
  groups.forEach((group) => {
    if (group.children.length === 1) group.icon = group.children[0].icon
  })
  return groups
}
