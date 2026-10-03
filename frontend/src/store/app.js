import { defineStore } from 'pinia'
import { metaApi } from '@/api'

// 全局字典与节点状态缓存，避免每个页面重复拉取元数据
export const useAppStore = defineStore('app', {
  state: () => ({
    dicts: {},
    nodes: [],
    datasets: [],
    partners: [],
    algorithms: [],
    taskTypes: [],
    reportTypes: [],
    regulations: [],
    budgetCategories: [],
    loaded: false
  }),

  getters: {
    onlineNodes: (state) => state.nodes.filter((node) => node.status === 'online'),
    taskTypeName: (state) => (code) => state.taskTypes.find((item) => item.code === code)?.name || code,
    datasetName: (state) => (code) => state.datasets.find((item) => item.code === code)?.name || code,
    nodeName: (state) => (code) => state.nodes.find((item) => item.code === code)?.name || code
  },

  actions: {
    async loadMeta(force = false) {
      if (this.loaded && !force) return
      const [dicts, nodes, datasets, partners, algorithms, taskTypes, reportTypes, budgetCategories] =
        await Promise.all([
          metaApi.dicts(),
          metaApi.nodes(),
          metaApi.datasets(),
          metaApi.partners(),
          metaApi.algorithms(),
          metaApi.taskTypes(),
          metaApi.reportTypes(),
          metaApi.budgetCategories()
        ])
      this.dicts = dicts
      this.nodes = nodes
      this.datasets = datasets
      this.partners = partners
      this.algorithms = algorithms
      this.taskTypes = taskTypes
      this.reportTypes = reportTypes
      this.budgetCategories = budgetCategories
      this.loaded = true
    },

    async loadRegulations() {
      this.regulations = await metaApi.regulations()
      return this.regulations
    }
  }
})
