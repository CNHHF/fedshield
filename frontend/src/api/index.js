import request from './request'

/* ---------------- 认证与用户 ---------------- */
export const authApi = {
  login: (data) => request.post('/auth/login', data),
  logout: () => request.post('/auth/logout'),
  profile: () => request.get('/auth/profile'),
  roles: () => request.get('/auth/roles'),
  sessions: () => request.get('/auth/sessions')
}

/* ---------------- 元数据 ---------------- */
export const metaApi = {
  nodes: () => request.get('/meta/nodes'),
  datasets: () => request.get('/meta/datasets'),
  partners: () => request.get('/meta/partners'),
  algorithms: () => request.get('/meta/algorithms'),
  taskTypes: () => request.get('/meta/task-types'),
  reportTypes: () => request.get('/meta/report-types'),
  regulations: (params) => request.get('/meta/regulations', { params }),
  budgetCategories: () => request.get('/meta/budget-categories'),
  dicts: () => request.get('/meta/dicts')
}

/* ---------------- 数据概览控制台 ---------------- */
export const dashboardApi = {
  overview: (params) => request.get('/dashboard/overview', { params }),
  flowTrend: (params) => request.get('/dashboard/flow-trend', { params }),
  alerts: (params) => request.get('/dashboard/alerts', { params }),
  riskDistribution: () => request.get('/dashboard/risk-distribution'),
  performance: () => request.get('/dashboard/performance')
}

/* ---------------- AI 风控合规智能大脑 ---------------- */
export const brainApi = {
  // 脑区图谱 + 数据流 + 关键指标 + 实时脉冲（silent 用于后台定时刷新，不弹提示）
  overview: (options = {}) => request.get('/brain/overview', options),
  atlas: (options = {}) => request.get('/brain/atlas', options)
}

/* ---------------- 隐私计算引擎 ---------------- */
export const engineApi = {
  createTask: (data) => request.post('/engine/tasks', data),
  tasks: (params) => request.get('/engine/tasks', { params }),
  taskDetail: (id) => request.get(`/engine/tasks/${id}`),
  startTask: (id) => request.post(`/engine/tasks/${id}/start`),
  pauseTask: (id) => request.post(`/engine/tasks/${id}/pause`),
  cancelTask: (id) => request.post(`/engine/tasks/${id}/cancel`),
  rerunTask: (id) => request.post(`/engine/tasks/${id}/rerun`),
  taskLogs: (id) => request.get(`/engine/tasks/${id}/logs`),
  taskResult: (id) => request.get(`/engine/tasks/${id}/result`),
  taskPreview: (id) => request.get(`/engine/tasks/${id}/preview`),
  exportTask: (id) => request.get(`/engine/tasks/${id}/export`, { responseType: 'blob' }),

  federatedTraining: (data) => request.post('/engine/federated-training', data),
  obliviousQuery: (data) => request.post('/engine/oblivious-query', data),
  jointStats: (data) => request.post('/engine/joint-stats', data),
  psi: (data) => request.post('/engine/psi', data),
  classify: (data) => request.post('/engine/classify', data)
}

/* ---------------- 合规校验与报告 ---------------- */
export const complianceApi = {
  rules: (params) => request.get('/compliance/rules', { params }),
  createRule: (data) => request.post('/compliance/rules', data),
  updateRule: (id, data) => request.put(`/compliance/rules/${id}`, data),
  deleteRule: (id) => request.delete(`/compliance/rules/${id}`),
  toggleRule: (id, enabled) => request.post(`/compliance/rules/${id}/toggle`, { enabled }),
  validate: (data) => request.post('/compliance/rules/validate', data),
  ruleTemplates: () => request.get('/compliance/rule-templates'),

  createReport: (data) => request.post('/compliance/reports', data),
  reports: (params) => request.get('/compliance/reports', { params }),
  reportDetail: (id) => request.get(`/compliance/reports/${id}`),
  regenerateReport: (id) => request.post(`/compliance/reports/${id}/regenerate`),
  downloadReport: (id) => request.get(`/compliance/reports/${id}/download`, { responseType: 'blob' }),
  exportReports: () => request.get('/compliance/reports/export', { responseType: 'blob' }),
  trend: (params) => request.get('/compliance/trend', { params }),
  alerts: (params) => request.get('/compliance/alerts', { params }),
  taxonomy: () => request.get('/compliance/taxonomy')
}

/* ---------------- 多方协同权限管控 ---------------- */
export const authzApi = {
  grants: (params) => request.get('/authz/grants', { params }),
  createGrant: (data) => request.post('/authz/grants', data),
  grantDetail: (id) => request.get(`/authz/grants/${id}`),
  approveGrant: (id, data) => request.post(`/authz/grants/${id}/approve`, data),
  revokeGrant: (id, data) => request.post(`/authz/grants/${id}/revoke`, data),
  renewGrant: (id, data) => request.post(`/authz/grants/${id}/renew`, data),
  exportGrants: () => request.get('/authz/export', { responseType: 'blob' }),
  filters: () => request.get('/authz/filters'),
  risks: () => request.get('/authz/risks'),
  audit: (params) => request.get('/authz/audit', { params })
}

/* ---------------- 隐私预算动态管理 ---------------- */
export const budgetApi = {
  overview: () => request.get('/budget/overview'),
  items: () => request.get('/budget/items'),
  trend: (params) => request.get('/budget/trend', { params }),
  adjustItem: (id, data) => request.post(`/budget/items/${id}/adjust`, data),
  transfer: (data) => request.post('/budget/transfer', data),
  applications: (params) => request.get('/budget/applications', { params }),
  createApplication: (data) => request.post('/budget/applications', data),
  approveApplication: (id, data) => request.post(`/budget/applications/${id}/approve`, data),
  adjustments: () => request.get('/budget/adjustments'),
  consume: (data) => request.post('/budget/consume', data)
}

/* ---------------- 数据血缘与溯源 ---------------- */
export const lineageApi = {
  graph: (params) => request.get('/lineage/graph', { params }),
  node: (id) => request.get(`/lineage/nodes/${id}`),
  trace: (dataId) => request.get(`/lineage/trace/${dataId}`),
  createRecord: (data) => request.post('/lineage/records', data),
  downloadRecord: (recordId) => request.get(`/lineage/records/${recordId}/download`, { responseType: 'blob' }),
  audit: (params) => request.get('/lineage/audit', { params }),
  exportAudit: (params) => request.get('/lineage/audit/export', { params, responseType: 'blob' })
}

/* ---------------- 审计存证（联盟链） ---------------- */
export const auditApi = {
  logs: (params) => request.get('/audit/logs', { params }),
  chain: (params) => request.get('/audit/chain', { params }),
  verifyChain: (options = {}) => request.post('/audit/chain/verify', undefined, options),
  chainDetail: (txId) => request.get(`/audit/chain/${txId}`),
  stats: () => request.get('/audit/stats')
}
