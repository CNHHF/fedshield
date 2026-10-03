<template>
  <div class="fs-home">
    <!-- 英雄区 -->
    <section class="fs-home__hero">
      <div class="fs-home__hero-inner">
        <el-tag effect="dark" class="fs-home__badge">跨境电商 · 外贸 B2B · 全球收单</el-tag>
        <h1>跨境敏感数据合规流通解决方案</h1>
        <p>
          FedShield 以联邦学习、同态加密、差分隐私为核心，结合联盟链存证与全球合规规则引擎，
          实现「原始数据不出域、可用不可见、合规可追溯」，支撑联合风控、黑名单匿踪查询与全球交易联合统计。
        </p>
        <div class="fs-home__actions">
          <el-button type="primary" size="large" @click="go('/console')">
            <el-icon><Odometer /></el-icon>进入数据概览控制台
          </el-button>
          <el-button size="large" plain @click="go('/engine/query')">
            <el-icon><Search /></el-icon>体验黑名单匿踪查询
          </el-button>
        </div>
        <div class="fs-home__hero-stats">
          <div v-for="item in heroStats" :key="item.label">
            <strong>{{ item.value }}</strong>
            <span>{{ item.label }}</span>
          </div>
        </div>
      </div>
    </section>

    <div class="fs-home__body">
      <!-- 关于平台 -->
      <section class="fs-card">
        <div class="fs-card__header">
          <span class="fs-card__title">关于平台</span>
          <el-button text type="primary" @click="go('/console')">查看运行状态</el-button>
        </div>
        <div class="fs-card__body">
          <p class="fs-home__paragraph">
            FedShield 面向 PingPong 全球支付业务场景，替代传统「明文传输 + 集中建模」模式：
            各地区节点在本地完成数据治理与模型训练，仅将加密后的参数、密文计算结果或盲化查询值通过
            TLS1.3 专有通道传输至中立聚合节点，在密文域完成聚合与比对。
            全流程操作日志经 Hyperledger Fabric 联盟链哈希存证，满足 GDPR（7 年）、PIPL（5 年）等
            多地区审计留存要求。
          </p>
          <div class="fs-grid fs-grid--4 fs-home__arch">
            <div v-for="layer in architecture" :key="layer.name" class="fs-home__layer">
              <el-icon :size="22" :color="layer.color"><component :is="layer.icon" /></el-icon>
              <strong>{{ layer.name }}</strong>
              <span>{{ layer.desc }}</span>
            </div>
          </div>
        </div>
      </section>

      <!-- 核心价值 -->
      <section class="fs-card">
        <div class="fs-card__header"><span class="fs-card__title">核心价值</span></div>
        <div class="fs-card__body">
          <div class="fs-grid fs-grid--3">
            <div v-for="item in values" :key="item.title" class="fs-home__value">
              <div class="fs-home__value-icon" :style="{ background: `${item.color}1a`, color: item.color }">
                <el-icon :size="20"><component :is="item.icon" /></el-icon>
              </div>
              <h3>{{ item.title }}</h3>
              <p>{{ item.desc }}</p>
              <ul>
                <li v-for="point in item.points" :key="point">{{ point }}</li>
              </ul>
            </div>
          </div>
        </div>
      </section>

      <!-- 适用场景 -->
      <section class="fs-card">
        <div class="fs-card__header">
          <span class="fs-card__title">适用场景</span>
          <span class="fs-muted">点击卡片进入对应功能页</span>
        </div>
        <div class="fs-card__body">
          <div class="fs-grid fs-grid--3">
            <div
              v-for="item in scenes"
              :key="item.title"
              class="fs-home__scene"
              @click="go(item.path)"
            >
              <div class="fs-home__scene-head">
                <el-icon :size="20" :color="item.color"><component :is="item.icon" /></el-icon>
                <strong>{{ item.title }}</strong>
              </div>
              <p>{{ item.desc }}</p>
              <div class="fs-home__scene-metrics">
                <span v-for="metric in item.metrics" :key="metric">{{ metric }}</span>
              </div>
            </div>
          </div>
        </div>
      </section>

      <!-- 合规框架 -->
      <section class="fs-card">
        <div class="fs-card__header">
          <span class="fs-card__title">支持的合规框架</span>
          <el-button text type="primary" @click="go('/compliance/reports')">合规报告管理</el-button>
        </div>
        <div class="fs-card__body">
          <div class="fs-home__frameworks">
            <el-tag v-for="item in frameworks" :key="item" effect="plain" size="large">{{ item }}</el-tag>
          </div>
          <el-alert
            class="fs-home__notice"
            type="info"
            :closable="false"
            show-icon
            title="合规即基础设施"
            description="平台内置全球法规库与可视化规则引擎：新规发布后可快速转化为自动化校验规则，未通过校验的数据自动退回并生成整改清单。"
          />
        </div>
      </section>

      <!-- 底部行动号召 -->
      <section class="fs-home__cta">
        <div>
          <h3>准备好开始跨境隐私计算了吗？</h3>
          <p>使用演示账号一键体验三大核心场景，全部计算均在本地完成，不产生任何真实数据出境。</p>
        </div>
        <div class="fs-home__cta-actions">
          <el-button type="primary" @click="go('/engine/tasks')">发起计算任务</el-button>
          <el-button plain @click="go('/lineage/graph')">查看数据血缘</el-button>
        </div>
      </section>
    </div>
  </div>
</template>

<script setup>
import { useRouter } from 'vue-router'
import { useUserStore } from '@/store/user'

const router = useRouter()
const userStore = useUserStore()

function go(path) {
  router.push(path)
}

const heroStats = [
  { value: '180+', label: '覆盖国家/地区法规库' },
  { value: '≤300ms', label: '黑名单匿踪查询响应' },
  { value: 'AUC 0.85+', label: '联邦联合风控模型' },
  { value: '0 条', label: '原始数据出境记录' }
]

const architecture = [
  { name: '数据来源层', desc: '各地区交易数据、商户主数据、监管制裁清单', icon: 'Coin', color: '#1f5fd8' },
  { name: '数据应用层', desc: '隐私加密存储与中间库，分级差异化管理', icon: 'Files', color: '#14a37f' },
  { name: '业务与算法层', desc: '联邦学习、同态加密、合规规则引擎', icon: 'Cpu', color: '#f5a623' },
  { name: '信息展示层', desc: '运营端 / 商户端 / 监管端专属视图', icon: 'Monitor', color: '#8b5cf6' }
]

const values = [
  {
    title: '合规适配',
    icon: 'DocumentChecked',
    color: '#1f5fd8',
    desc: '内置全球法规库与可视化规则引擎，自动解析法规条款并生成数据处理策略。',
    points: ['覆盖 GDPR / PIPL / PDPA / CCPA 等主流法规', '数据出境前自动校验 SCC、DPIA 等要件', '未通过校验的数据自动退回并生成整改清单']
  },
  {
    title: '数据安全',
    icon: 'Lock',
    color: '#14a37f',
    desc: '「传输—计算—访问」三重防护，敏感数据全生命周期可用不可见。',
    points: ['P1 级数据国密 SM4 + Paillier 双重加密', '联邦学习与同态加密实现密文域计算', '零信任动态授权 + 异常行为熔断']
  },
  {
    title: '业务效能',
    icon: 'Odometer',
    color: '#f5a623',
    desc: '在合规安全前提下保障业务效率，核心场景效率不低于明文处理的 80%。',
    points: ['参数量化压缩 + 剪枝，传输量下降约 70%', '黑名单查询响应 ≤300ms', '全球交易统计耗时从 80 小时压缩至 8 小时以内']
  }
]

const scenes = [
  {
    title: '跨境电商联合风控',
    icon: 'DataAnalysis',
    color: '#1f5fd8',
    path: '/engine/tasks',
    desc: '欧洲—中国双节点横向联邦建模，补足跨地域特征短板，识别虚假交易与跨境洗钱风险。',
    metrics: ['漏检率 ≤7%', 'AUC 与明文偏差 ≤0.02', '参数密文聚合']
  },
  {
    title: '外贸 B2B 黑名单查询',
    icon: 'Search',
    color: '#14a37f',
    path: '/engine/query',
    desc: '基于同态加密与 RSA 盲签名 OPRF 的匿踪查询，商户信息与制裁清单互不泄露。',
    metrics: ['响应 ≤300ms', '零明文暴露', '全流程上链存证']
  },
  {
    title: '全球交易联合统计',
    icon: 'PieChart',
    color: '#f5a623',
    path: '/engine/stats',
    desc: '各地区本地聚合后密文上传，在密文域完成金额求和与类别统计，直接输出申报口径。',
    metrics: ['误差率 ≤1%', '海关 / VAT 申报口径', '审计留存 5-7 年']
  }
]

const frameworks = [
  '欧盟 GDPR', '中国 PIPL', '中国数据安全法', '新加坡 PDPA', '美国 CCPA / CPRA',
  'Schrems II 判决', 'FATF 旅行规则', 'PCI-DSS v4.0', 'ISO/IEC 27701'
]

void userStore
</script>

<style scoped>
.fs-home {
  padding-bottom: 28px;
}
.fs-home__hero {
  background: linear-gradient(140deg, #0d1b34 0%, #14315e 48%, #1f5fd8 100%);
  color: #fff;
  padding: 46px 32px 34px;
}
.fs-home__hero-inner {
  max-width: 1120px;
  margin: 0 auto;
}
.fs-home__badge {
  margin-bottom: 14px;
}
.fs-home__hero h1 {
  margin: 0 0 12px;
  font-size: 32px;
  letter-spacing: 0.5px;
}
.fs-home__hero p {
  margin: 0;
  max-width: 780px;
  color: #b9cbe6;
  line-height: 1.8;
  font-size: 14px;
}
.fs-home__actions {
  margin-top: 22px;
  display: flex;
  gap: 12px;
  flex-wrap: wrap;
}
.fs-home__hero-stats {
  margin-top: 30px;
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 18px;
  padding-top: 20px;
  border-top: 1px solid rgba(255, 255, 255, 0.14);
}
.fs-home__hero-stats strong {
  display: block;
  font-size: 22px;
}
.fs-home__hero-stats span {
  font-size: 12px;
  color: #a9bcd8;
}
.fs-home__body {
  max-width: 1120px;
  margin: -18px auto 0;
  padding: 0 20px;
  display: flex;
  flex-direction: column;
  gap: 16px;
}
.fs-home__paragraph {
  margin: 0 0 18px;
  color: var(--fs-text-secondary);
  line-height: 1.9;
  font-size: 13px;
}
.fs-home__arch {
  gap: 12px;
}
.fs-home__layer {
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding: 16px;
  border: 1px solid var(--fs-border);
  border-radius: 8px;
  background: #fafbfd;
}
.fs-home__layer strong {
  font-size: 14px;
}
.fs-home__layer span {
  color: var(--fs-text-secondary);
  font-size: 12px;
  line-height: 1.6;
}
.fs-home__value {
  padding: 18px;
  border: 1px solid var(--fs-border);
  border-radius: 8px;
}
.fs-home__value-icon {
  width: 40px;
  height: 40px;
  border-radius: 10px;
  display: flex;
  align-items: center;
  justify-content: center;
}
.fs-home__value h3 {
  margin: 12px 0 8px;
  font-size: 16px;
}
.fs-home__value p {
  margin: 0 0 10px;
  color: var(--fs-text-secondary);
  font-size: 13px;
  line-height: 1.7;
}
.fs-home__value ul {
  margin: 0;
  padding-left: 18px;
  color: var(--fs-text-secondary);
  font-size: 12px;
  line-height: 1.9;
}
.fs-home__scene {
  padding: 18px;
  border: 1px solid var(--fs-border);
  border-radius: 8px;
  cursor: pointer;
  transition: all 0.18s ease;
}
.fs-home__scene:hover {
  border-color: var(--fs-primary);
  box-shadow: 0 6px 18px rgba(31, 95, 216, 0.12);
  transform: translateY(-2px);
}
.fs-home__scene-head {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
}
.fs-home__scene p {
  margin: 0 0 12px;
  color: var(--fs-text-secondary);
  font-size: 13px;
  line-height: 1.7;
}
.fs-home__scene-metrics {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}
.fs-home__scene-metrics span {
  font-size: 12px;
  color: var(--fs-primary);
  background: var(--fs-primary-light);
  padding: 3px 8px;
  border-radius: 4px;
}
.fs-home__frameworks {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
}
.fs-home__notice {
  margin-top: 16px;
}
.fs-home__cta {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 20px;
  padding: 22px 24px;
  border-radius: var(--fs-card-radius);
  background: linear-gradient(120deg, #eef4ff, #e9fbf5);
  border: 1px solid var(--fs-border);
  flex-wrap: wrap;
}
.fs-home__cta h3 {
  margin: 0 0 6px;
  font-size: 17px;
}
.fs-home__cta p {
  margin: 0;
  color: var(--fs-text-secondary);
  font-size: 13px;
}
.fs-home__cta-actions {
  display: flex;
  gap: 10px;
}
@media (max-width: 1024px) {
  .fs-home__hero-stats {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}
</style>
