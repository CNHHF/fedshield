<template>
  <div class="fs-page">
    <div class="fs-page__header">
      <div>
        <h2 class="fs-page__title">多方协同权限管控</h2>
        <p class="fs-page__subtitle">
          以「最小必要 + 目的限定」为原则为跨境协作机构分配数据授权：申请、审批、撤销、续期全过程落链存证；
          监管端按角色进入风险视图，查看异常访问、即将到期授权与 MFA 失败记录。
        </p>
      </div>
      <el-tag v-if="isRegulator" type="warning" effect="plain" size="large">监管视图 · 仅可查看</el-tag>
    </div>

    <div class="fs-card">
      <div class="fs-card__body">
        <el-tabs v-model="activeTab" @tab-change="onTabChange">
          <!-- ==================== ① 新建数据授权 ==================== -->
          <el-tab-pane v-if="!isRegulator" label="新建数据授权" name="create">
            <el-form ref="grantFormRef" :model="grantForm" :rules="grantRules" label-width="110px" class="fs-grant-form">
              <el-form-item label="授权对象" prop="partner">
                <el-select
                  v-model="grantForm.partner"
                  filterable
                  clearable
                  placeholder="请选择跨境协作机构（仅已认证机构可被授权）"
                  style="width: 100%"
                >
                  <el-option
                    v-for="item in partnerOptions"
                    :key="item.code"
                    :value="item.code"
                    :label="`${item.name}（${item.region || '未知地区'}）`"
                    :disabled="!item.verified"
                  >
                    <div class="fs-option">
                      <span class="fs-option__label">{{ item.name }}（{{ item.region || '未知地区' }}）</span>
                      <span class="fs-option__meta">
                        <el-tag size="small" :type="item.verified ? 'success' : 'danger'" effect="plain">
                          {{ item.verified ? '已认证' : '未认证' }}
                        </el-tag>
                        <span class="fs-muted">资质证书有效期至 {{ formatTime(item.certExpireAt, false) }}</span>
                        <span v-if="!item.verified" class="fs-muted">需先通过资质审核</span>
                      </span>
                    </div>
                  </el-option>
                </el-select>
                <div v-if="partnerCertTip" class="fs-muted fs-mt">{{ partnerCertTip }}</div>
              </el-form-item>

              <el-form-item label="数据范围" prop="datasetScope">
                <el-select
                  v-model="grantForm.datasetScope"
                  multiple
                  collapse-tags
                  collapse-tags-tooltip
                  placeholder="请选择可授权的数据集（按分级最小必要授权）"
                  style="width: 100%"
                >
                  <el-option
                    v-for="item in datasetOptions"
                    :key="item.code"
                    :value="item.code"
                    :label="`${item.name}（${item.level || 'P3'}）`"
                  >
                    <div class="fs-option">
                      <span class="fs-option__label">{{ item.name }}</span>
                      <DataLevelTag :level="item.level || 'P3'" />
                    </div>
                  </el-option>
                </el-select>
                <!-- 已选数据的分级预检：含 P1 时必须先通过合规校验才能传输 -->
                <div v-if="grantForm.datasetScope.length" class="fs-scope-preview">
                  <span class="fs-muted">已选范围分级：</span>
                  <DataLevelTag v-for="(level, index) in selectedLevels" :key="index" :level="level" class="fs-gap" />
                  <el-tag v-if="hasP1Scope" type="danger" effect="dark" size="small" class="fs-gap">
                    含 P1 高敏感数据，传输前需通过跨境合规校验
                  </el-tag>
                </div>
              </el-form-item>

              <el-form-item label="使用目的" prop="purpose">
                <el-checkbox-group v-model="grantForm.purpose">
                  <el-checkbox v-for="item in PURPOSE_OPTIONS" :key="item" :value="item">{{ item }}</el-checkbox>
                </el-checkbox-group>
              </el-form-item>

              <el-form-item label="授权级别" prop="level">
                <el-radio-group v-model="grantForm.level">
                  <el-radio v-for="item in LEVEL_OPTIONS" :key="item.value" :value="item.value">
                    {{ item.label }}
                  </el-radio>
                </el-radio-group>
                <div class="fs-muted fs-mt">{{ currentLevelDesc }}</div>
              </el-form-item>

              <el-form-item label="授权有效期" prop="validity">
                <el-date-picker
                  v-model="grantForm.validity"
                  type="datetimerange"
                  value-format="YYYY-MM-DD HH:mm:ss"
                  range-separator="至"
                  start-placeholder="生效时间"
                  end-placeholder="到期时间（最长 1 年）"
                  :disabled-date="disableBeyondOneYear"
                  @change="onValidityChange"
                />
                <span class="fs-muted fs-ml">最长 1 年，超出将自动截断为起始时间后 365 天</span>
              </el-form-item>

              <el-form-item>
                <el-button link type="primary" @click="showMore = !showMore">
                  <el-icon><component :is="showMore ? 'ArrowUp' : 'ArrowDown'" /></el-icon>
                  {{ showMore ? '收起更多选项' : '更多选项（二次授权 / 多因素认证 / 备注）' }}
                </el-button>
              </el-form-item>

              <div v-show="showMore">
                <el-form-item label="二次授权">
                  <el-switch v-model="grantForm.allowReGrant" />
                  <span class="fs-muted fs-ml">开启后该机构可将授权范围内的数据再授权给下游合作方（默认关闭）</span>
                </el-form-item>
                <el-form-item label="多因素认证">
                  <el-switch v-model="grantForm.requireMfa" />
                  <span class="fs-muted fs-ml">要求其访问 P1 数据时通过 MFA 动态码二次校验（推荐开启）</span>
                </el-form-item>
                <el-form-item label="备注" prop="remark">
                  <el-input
                    v-model="grantForm.remark"
                    type="textarea"
                    :rows="3"
                    maxlength="200"
                    show-word-limit
                    placeholder="补充授权背景、合规依据（如 SCC 编号、DPIA 结论）等"
                  />
                </el-form-item>
              </div>

              <el-form-item>
                <el-button @click="resetGrantForm">重置</el-button>
                <el-button type="primary" :loading="submitting" @click="submitGrant">提交授权申请</el-button>
              </el-form-item>
            </el-form>
          </el-tab-pane>

          <!-- ==================== ② 授权记录管理 ==================== -->
          <el-tab-pane label="授权记录管理" name="records">
            <div class="fs-toolbar">
              <el-select v-model="query.status" placeholder="授权状态" clearable style="width: 150px" @change="searchGrants">
                <el-option v-for="item in statusOptions" :key="item.value" :value="item.value" :label="item.label" />
              </el-select>
              <el-select
                v-model="query.partner"
                placeholder="授权对象"
                clearable
                filterable
                style="width: 200px"
                @change="searchGrants"
              >
                <el-option
                  v-for="item in partnerOptions"
                  :key="item.code"
                  :value="item.code"
                  :label="`${item.name}（${item.region || '未知地区'}）`"
                />
              </el-select>
              <el-input
                v-model="query.keyword"
                placeholder="授权ID / 机构名称 / 使用目的"
                clearable
                style="width: 240px"
                @keyup.enter="searchGrants"
                @clear="searchGrants"
              >
                <template #prefix><el-icon><Search /></el-icon></template>
              </el-input>
              <el-button type="primary" @click="searchGrants">查询</el-button>
              <div class="fs-toolbar__right">
                <el-button :loading="exporting" @click="handleExport">
                  <el-icon><Download /></el-icon>导出记录
                </el-button>
                <el-button :loading="loading" @click="load">
                  <el-icon><Refresh /></el-icon>刷新
                </el-button>
              </div>
            </div>

            <el-table v-loading="loading" :data="grantRows" border stripe empty-text="暂无授权记录">
              <el-table-column prop="code" label="授权ID" width="150">
                <template #default="{ row }">
                  <span class="fs-mono">{{ row.code || '-' }}</span>
                </template>
              </el-table-column>
              <el-table-column label="授权对象" min-width="190">
                <template #default="{ row }">
                  <div>{{ row.partner || '-' }}</div>
                  <div class="fs-muted">{{ row.partnerRegion || '未知地区' }}</div>
                </template>
              </el-table-column>
              <el-table-column label="数据范围" min-width="230">
                <template #default="{ row }">
                  <template v-if="Array.isArray(row.datasetScope) && row.datasetScope.length">
                    <el-tag
                      v-for="code in row.datasetScope"
                      :key="code"
                      size="small"
                      effect="plain"
                      class="fs-gap"
                    >
                      {{ datasetLabel(code) }}
                    </el-tag>
                  </template>
                  <span v-else class="fs-muted">-</span>
                </template>
              </el-table-column>
              <el-table-column label="使用目的" min-width="170">
                <template #default="{ row }">
                  <span>{{ purposeText(row.purpose) }}</span>
                </template>
              </el-table-column>
              <el-table-column label="级别" width="140">
                <template #default="{ row }">
                  <el-tag size="small" :type="levelTagType(row.level)" effect="plain">
                    {{ levelLabel(row.level) }}
                  </el-tag>
                </template>
              </el-table-column>
              <el-table-column label="有效期" min-width="200">
                <template #default="{ row }">
                  <div class="fs-mono">{{ formatTime(row.validFrom, false) }}</div>
                  <div class="fs-mono fs-muted">至 {{ formatTime(row.validTo, false) }}</div>
                </template>
              </el-table-column>
              <el-table-column label="状态" width="100">
                <template #default="{ row }">
                  <el-tag size="small" :type="dictOf(GRANT_STATUS, row.status).type" effect="light">
                    {{ dictOf(GRANT_STATUS, row.status).label }}
                  </el-tag>
                </template>
              </el-table-column>
              <el-table-column label="操作" width="210" fixed="right">
                <template #default="{ row }">
                  <el-button link type="primary" size="small" @click="openDetail(row)">查看</el-button>
                  <!-- 操作按钮严格按授权状态渲染，避免出现非法状态流转 -->
                  <template v-if="row.status === 'active'">
                    <el-button link type="danger" size="small" @click="handleRevoke(row)">撤销</el-button>
                    <el-button link type="primary" size="small" @click="handleRenew(row)">续期</el-button>
                  </template>
                  <template v-else-if="row.status === 'pending'">
                    <el-button link type="success" size="small" @click="handleApprove(row)">审批</el-button>
                    <el-button link type="info" size="small" @click="handleCancel(row)">取消</el-button>
                  </template>
                  <template v-else-if="row.status === 'expired'">
                    <el-button link type="primary" size="small" @click="handleRenew(row)">续期</el-button>
                  </template>
                </template>
              </el-table-column>
            </el-table>

            <div class="fs-pager">
              <el-pagination
                v-model:current-page="query.page"
                v-model:page-size="query.size"
                :total="grantTotal"
                :page-sizes="[10, 20, 50]"
                layout="total, sizes, prev, pager, next, jumper"
                background
                @current-change="load"
                @size-change="searchGrants"
              />
            </div>
          </el-tab-pane>

          <!-- ==================== ③ 风险与预警 ==================== -->
          <el-tab-pane label="风险与预警" name="risk">
            <div class="fs-toolbar">
              <span class="fs-muted">数据来源：/api/authz/risks（异常访问检测 + 授权到期预警 + MFA 失败聚合）</span>
              <div class="fs-toolbar__right">
                <el-button :loading="riskLoading" @click="loadRisks">
                  <el-icon><Refresh /></el-icon>刷新
                </el-button>
              </div>
            </div>

            <el-alert type="error" :closable="false" show-icon class="fs-risk-alert">
              <template #title>零信任熔断规则（命中任一条即触发分级熔断，锁定账号 1 ~ 24 小时）</template>
              <ul class="fs-risk-alert__list">
                <li>同一账号 1 小时内跨欧盟与中国同时登录 → 判定为凭证共享/盗用，锁定 24 小时并要求重新进行数字证书校验。</li>
                <li>10 分钟内访问 P1 级数据超过 5 次 → 判定为批量拖库行为，锁定 12 小时并冻结相关授权。</li>
                <li>未通过合规校验尝试传输数据 → 直接阻断传输，锁定 6 小时并生成整改清单。</li>
                <li>解密次数超过阈值（单账号单日 100 次）→ 判定为密钥滥用风险，锁定 1 小时起并逐级上报。</li>
              </ul>
            </el-alert>

            <div class="fs-subsection">
              <div class="fs-subsection__title">
                <el-icon><WarnTriangleFilled /></el-icon>
                异常访问行为
                <el-tag size="small" type="danger" effect="plain">{{ abnormalRows.length }} 条</el-tag>
              </div>
              <el-table v-loading="riskLoading" :data="abnormalRows" border size="small" empty-text="暂无异常访问记录">
                <el-table-column label="时间" width="180">
                  <template #default="{ row }">{{ formatTime(row.ts) }}</template>
                </el-table-column>
                <el-table-column prop="account" label="账号" min-width="150" />
                <el-table-column prop="action" label="行为" min-width="220" />
                <el-table-column label="风险分" width="120">
                  <template #default="{ row }">
                    <el-tag size="small" :type="riskScoreType(row.riskScore)" effect="plain">
                      {{ formatNumber(row.riskScore) }}
                    </el-tag>
                  </template>
                </el-table-column>
              </el-table>
            </div>

            <div class="fs-subsection">
              <div class="fs-subsection__title">
                <el-icon><Timer /></el-icon>
                即将过期授权
                <el-tag size="small" type="warning" effect="plain">{{ expiringRows.length }} 条</el-tag>
              </div>
              <el-table v-loading="riskLoading" :data="expiringRows" border size="small" empty-text="暂无即将到期授权">
                <el-table-column label="授权ID" width="160">
                  <template #default="{ row }">
                    <span class="fs-mono">{{ row.code }}</span>
                  </template>
                </el-table-column>
                <el-table-column prop="partner" label="授权对象" min-width="200" />
                <el-table-column label="到期时间" width="190">
                  <template #default="{ row }">{{ formatTime(row.validTo) }}</template>
                </el-table-column>
                <el-table-column label="剩余天数" width="120">
                  <template #default="{ row }">
                    <el-tag size="small" :type="row.remainDays <= 7 ? 'danger' : 'warning'" effect="plain">
                      {{ formatNumber(row.remainDays) }} 天
                    </el-tag>
                  </template>
                </el-table-column>
              </el-table>
            </div>

            <div class="fs-subsection">
              <div class="fs-subsection__title">
                <el-icon><Lock /></el-icon>
                MFA 校验失败
                <el-tag size="small" type="info" effect="plain">{{ mfaRows.length }} 条</el-tag>
              </div>
              <el-table v-loading="riskLoading" :data="mfaRows" border size="small" empty-text="暂无 MFA 失败记录">
                <el-table-column prop="account" label="账号" min-width="160" />
                <el-table-column label="时间" width="190">
                  <template #default="{ row }">{{ formatTime(row.ts) }}</template>
                </el-table-column>
                <el-table-column prop="ip" label="IP 地址" min-width="160">
                  <template #default="{ row }">
                    <span class="fs-mono">{{ row.ip }}</span>
                  </template>
                </el-table-column>
                <el-table-column label="失败次数" width="120">
                  <template #default="{ row }">
                    <el-tag size="small" :type="row.count >= 5 ? 'danger' : 'warning'" effect="plain">
                      {{ formatNumber(row.count) }} 次
                    </el-tag>
                  </template>
                </el-table-column>
              </el-table>
            </div>
          </el-tab-pane>
        </el-tabs>
      </div>
    </div>

    <!-- 授权详情抽屉：授权要素 + 权限变更日志 -->
    <el-drawer v-model="detailVisible" title="授权详情与变更日志" size="620px">
      <div v-loading="detailLoading">
        <el-descriptions :column="2" border size="small">
          <el-descriptions-item label="授权ID">
            <span class="fs-mono">{{ detail.code || '-' }}</span>
          </el-descriptions-item>
          <el-descriptions-item label="状态">
            <el-tag size="small" :type="dictOf(GRANT_STATUS, detail.status).type" effect="light">
              {{ dictOf(GRANT_STATUS, detail.status).label }}
            </el-tag>
          </el-descriptions-item>
          <el-descriptions-item label="授权对象">{{ detail.partner || '-' }}</el-descriptions-item>
          <el-descriptions-item label="所属地区">{{ detail.partnerRegion || '-' }}</el-descriptions-item>
          <el-descriptions-item label="授权级别">{{ levelLabel(detail.level) }}</el-descriptions-item>
          <el-descriptions-item label="资质证书到期">{{ formatTime(detail.certExpireAt, false) }}</el-descriptions-item>
          <el-descriptions-item label="生效时间">{{ formatTime(detail.validFrom) }}</el-descriptions-item>
          <el-descriptions-item label="到期时间">{{ formatTime(detail.validTo) }}</el-descriptions-item>
          <el-descriptions-item label="使用目的" :span="2">{{ purposeText(detail.purpose) }}</el-descriptions-item>
          <el-descriptions-item label="权限点" :span="2">
            <template v-if="Array.isArray(detail.permissions) && detail.permissions.length">
              <el-tag v-for="code in detail.permissions" :key="code" size="small" effect="plain" class="fs-gap">
                {{ code }}
              </el-tag>
            </template>
            <span v-else class="fs-muted">按授权级别自动推导</span>
          </el-descriptions-item>
          <el-descriptions-item label="备注" :span="2">{{ detail.remark || '-' }}</el-descriptions-item>
        </el-descriptions>

        <div class="fs-subsection">
          <div class="fs-subsection__title"><el-icon><Files /></el-icon>数据范围</div>
          <template v-if="Array.isArray(detail.datasetScope) && detail.datasetScope.length">
            <div v-for="code in detail.datasetScope" :key="code" class="fs-scope-row">
              <span>{{ datasetLabel(code) }}</span>
              <DataLevelTag :level="datasetLevel(code)" />
            </div>
          </template>
          <span v-else class="fs-muted">-</span>
        </div>

        <div class="fs-subsection">
          <div class="fs-subsection__title"><el-icon><Clock /></el-icon>权限变更日志</div>
          <el-timeline v-if="detailHistory.length">
            <el-timeline-item
              v-for="(item, index) in detailHistory"
              :key="index"
              :timestamp="formatTime(item.ts)"
              :type="item.type"
            >
              <div class="fs-history__title">{{ item.title }}</div>
              <div class="fs-muted">操作人：{{ item.actor }}</div>
              <div v-if="item.detail" class="fs-muted">{{ item.detail }}</div>
            </el-timeline-item>
          </el-timeline>
          <span v-else class="fs-muted">暂无变更日志</span>
        </div>
      </div>
    </el-drawer>
  </div>
</template>

<script setup>
/**
 * 多方协同权限管控（对应文档图26~图30）
 * 三个页签：新建数据授权 / 授权记录管理 / 风险与预警
 * 监管端（regulator）默认停留在风险页签，且不可新建授权（前端隐藏 + 后端 authz:grant:manage 鉴权双重控制）
 */
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { authzApi } from '@/api'
import { useAppStore } from '@/store/app'
import { useUserStore } from '@/store/user'
import { GRANT_STATUS, dictOf, formatNumber, formatTime } from '@/utils/format'
import { downloadResponse } from '@/utils/download'
import DataLevelTag from '@/components/DataLevelTag.vue'

const appStore = useAppStore()
const userStore = useUserStore()

/** 使用目的字典（与后端授权用途枚举对应） */
const PURPOSE_OPTIONS = ['反欺诈模型训练', '联合风控验证', '黑名单核验', '监管申报统计']

/** 授权级别：只读计算 / 结果查询限制 / 允许参与隐私计算 */
const LEVEL_OPTIONS = [
  { value: 'readonly', label: '只读计算', desc: '仅允许在密文域内参与计算，任何情况下不返回明细数据。' },
  { value: 'query-limited', label: '结果查询限制', desc: '仅可查询聚合结果，且单日查询次数受限（最小必要原则）。' },
  { value: 'mpc', label: '允许参与隐私计算', desc: '可作为计算节点参与联邦学习 / 同态加密等多方计算任务。' }
]

const LEVEL_TAG_TYPE = { readonly: 'info', 'query-limited': 'warning', mpc: 'success' }

const isRegulator = computed(() => userStore.role === 'regulator')

const activeTab = ref('create')
const showMore = ref(false)
const loading = ref(false)
const submitting = ref(false)
const exporting = ref(false)
const riskLoading = ref(false)

const grantFormRef = ref(null)
const grantForm = reactive({
  partner: '',
  datasetScope: [],
  purpose: ['反欺诈模型训练'],
  level: 'readonly',
  validity: [],
  allowReGrant: false,
  requireMfa: true,
  remark: ''
})

const grantRules = {
  partner: [{ required: true, message: '请选择授权对象', trigger: 'change' }],
  datasetScope: [{ required: true, type: 'array', min: 1, message: '请至少选择一个数据范围', trigger: 'change' }],
  purpose: [{ required: true, type: 'array', min: 1, message: '请至少选择一个使用目的', trigger: 'change' }],
  level: [{ required: true, message: '请选择授权级别', trigger: 'change' }],
  validity: [
    {
      // 有效期必填校验：必须是 [生效时间, 到期时间] 两元素数组
      validator: (rule, value, callback) => {
        if (!Array.isArray(value) || value.length !== 2 || !value[0] || !value[1]) {
          callback(new Error('请选择授权有效期'))
          return
        }
        callback()
      },
      trigger: 'change'
    }
  ]
}

/* ---------------- 字典与选项（全部做空值兜底） ---------------- */
const partnerOptions = computed(() => appStore.partners ?? [])
const datasetOptions = computed(() => appStore.datasets ?? [])
const statusOptions = computed(() => Object.entries(GRANT_STATUS).map(([value, meta]) => ({ value, label: meta.label })))

const selectedLevels = computed(() =>
  (grantForm.datasetScope ?? []).map((code) => datasetLevel(code))
)
const hasP1Scope = computed(() => selectedLevels.value.includes('P1'))

const currentLevelDesc = computed(
  () => LEVEL_OPTIONS.find((item) => item.value === grantForm.level)?.desc || ''
)

/** 授权对象为未认证机构时的额外提示（选项已 disabled，这里做二次说明） */
const partnerCertTip = computed(() => {
  const partner = partnerOptions.value.find((item) => item.code === grantForm.partner)
  if (!partner) return ''
  if (!partner.verified) return '该机构尚未通过资质审核，需先在合作方管理中完成认证后方可授权。'
  const expire = partner.certExpireAt ? new Date(String(partner.certExpireAt).replace(' ', 'T')).getTime() : 0
  if (expire && expire - Date.now() < 90 * 24 * 3600 * 1000) {
    return '该机构资质证书将在 90 天内到期，请同步安排证书续期，避免授权生效期间证书失效。'
  }
  return ''
})

function datasetLevel(code) {
  return datasetOptions.value.find((item) => item.code === code)?.level || 'P3'
}

function datasetLabel(code) {
  const dataset = datasetOptions.value.find((item) => item.code === code)
  return dataset ? `${dataset.name}（${dataset.level || 'P3'}）` : code
}

function levelLabel(level) {
  return LEVEL_OPTIONS.find((item) => item.value === level)?.label || level || '-'
}

function levelTagType(level) {
  return LEVEL_TAG_TYPE[level] || 'info'
}

/** purpose 契约上是标量字符串，但后端也可能返回数组，这里统一转为展示文本 */
function purposeText(purpose) {
  if (Array.isArray(purpose)) return purpose.length ? purpose.join('、') : '-'
  return purpose || '-'
}

function riskScoreType(score) {
  const value = Number(score || 0)
  if (value >= 80) return 'danger'
  if (value >= 60) return 'warning'
  return 'info'
}

/* ---------------- ① 新建授权 ---------------- */
/** 有效期上限 1 年：超出时提示并自动截断到「起始时间 + 365 天」 */
function onValidityChange(value) {
  if (!Array.isArray(value) || value.length !== 2 || !value[0] || !value[1]) return
  const start = new Date(String(value[0]).replace(' ', 'T')).getTime()
  const end = new Date(String(value[1]).replace(' ', 'T')).getTime()
  if (Number.isNaN(start) || Number.isNaN(end)) return
  const limit = start + 365 * 24 * 3600 * 1000
  if (end > limit) {
    const date = new Date(limit)
    const pad = (n) => String(n).padStart(2, '0')
    const truncated = `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())} ${pad(
      date.getHours()
    )}:${pad(date.getMinutes())}:${pad(date.getSeconds())}`
    grantForm.validity = [value[0], truncated]
    ElMessage.warning('授权有效期最长 1 年，已自动截断为起始时间后 365 天')
  }
}

/** 日期选择器：禁止选择「起始时间 + 365 天」之后的日期 */
function disableBeyondOneYear(date) {
  const start = grantForm.validity?.[0]
  if (!start) return false
  const startTime = new Date(String(start).replace(' ', 'T')).getTime()
  if (Number.isNaN(startTime)) return false
  return date.getTime() > startTime + 365 * 24 * 3600 * 1000
}

function resetGrantForm() {
  grantForm.partner = ''
  grantForm.datasetScope = []
  grantForm.purpose = ['反欺诈模型训练']
  grantForm.level = 'readonly'
  grantForm.validity = []
  grantForm.allowReGrant = false
  grantForm.requireMfa = true
  grantForm.remark = ''
  showMore.value = false
  grantFormRef.value?.clearValidate()
}

async function submitGrant() {
  if (!grantFormRef.value) return
  try {
    await grantFormRef.value.validate()
  } catch (error) {
    return
  }
  // 额外兜底：有效期跨度再校验一次，防止绕过日期控件传入超长有效期
  const start = new Date(String(grantForm.validity[0]).replace(' ', 'T')).getTime()
  const end = new Date(String(grantForm.validity[1]).replace(' ', 'T')).getTime()
  if (end - start > 365 * 24 * 3600 * 1000) {
    ElMessage.warning('授权有效期最长 1 年，请重新选择到期时间')
    return
  }

  // 权限点：按级别推导 + 附加开关（二次授权 / 强制 MFA）落库，便于后端鉴权与审计
  const permissions = []
  if (grantForm.allowReGrant) permissions.push('authz:re-authorize')
  if (grantForm.requireMfa) permissions.push('authz:mfa-required')

  submitting.value = true
  try {
    const data = await authzApi.createGrant({
      partner: grantForm.partner,
      datasetScope: [...grantForm.datasetScope],
      purpose: grantForm.purpose.join('、'),
      level: grantForm.level,
      validFrom: grantForm.validity[0],
      validTo: grantForm.validity[1],
      permissions,
      remark: grantForm.remark
    })
    ElMessage.success(`授权申请已提交，授权ID：${data?.code || '-'}（待审批）`)
    resetGrantForm()
    activeTab.value = 'records'
    query.page = 1
    await load()
  } catch (error) {
    // 请求层已统一提示错误，这里仅保证不阻塞后续操作
  } finally {
    submitting.value = false
  }
}

/* ---------------- ② 授权记录 ---------------- */
const grantRows = ref([])
const grantTotal = ref(0)
const query = reactive({ status: '', partner: '', keyword: '', page: 1, size: 10 })

async function load() {
  loading.value = true
  try {
    const payload = await authzApi.grants({
      status: query.status || undefined,
      partner: query.partner || undefined,
      keyword: query.keyword || undefined,
      page: query.page,
      size: query.size
    })
    // 兼容分页信封 { list, total } 与直接返回数组两种形态
    const list = Array.isArray(payload) ? payload : payload?.list ?? []
    grantRows.value = list ?? []
    grantTotal.value = Array.isArray(payload) ? list.length : payload?.total ?? 0
  } catch (error) {
    grantRows.value = []
    grantTotal.value = 0
  } finally {
    loading.value = false
  }
}

function searchGrants() {
  query.page = 1
  load()
}

async function handleExport() {
  exporting.value = true
  try {
    const response = await authzApi.exportGrants()
    downloadResponse(response, `数据授权记录_${Date.now()}.csv`)
    ElMessage.success('授权记录导出成功')
  } catch (error) {
    // 导出失败已由请求层提示
  } finally {
    exporting.value = false
  }
}

async function handleApprove(row) {
  let comment = ''
  try {
    const result = await ElMessageBox.prompt('请输入审批意见（将写入链上存证）', '审批授权申请', {
      confirmButtonText: '通过',
      cancelButtonText: '取消',
      inputValue: '资质与合规要件齐全，同意授权',
      inputPlaceholder: '审批意见'
    })
    comment = result.value || ''
  } catch (error) {
    return
  }
  try {
    await authzApi.approveGrant(row.id, { approved: true, comment })
    ElMessage.success('已审批通过，授权正式生效')
    await load()
  } catch (error) {
    // 错误提示由请求层统一处理
  }
}

async function handleRevoke(row) {
  let reason = ''
  try {
    const result = await ElMessageBox.prompt(
      `撤销后「${row.partner || row.code}」将立即失去授权范围内数据的访问能力，请填写撤销原因`,
      '撤销授权',
      {
        confirmButtonText: '确认撤销',
        cancelButtonText: '取消',
        inputType: 'textarea',
        inputPlaceholder: '如：合作终止 / 资质过期 / 触发熔断规则',
        inputValidator: (value) => (value && value.trim().length >= 4 ? true : '撤销原因不少于 4 个字符')
      }
    )
    reason = result.value || ''
  } catch (error) {
    return
  }
  try {
    await authzApi.revokeGrant(row.id, { reason })
    ElMessage.success('授权已撤销，变更已落链存证')
    await load()
  } catch (error) {
    // 错误提示由请求层统一处理
  }
}

/** 取消待审核申请：语义等同撤销，走同一接口并标注原因 */
async function handleCancel(row) {
  let reason = ''
  try {
    const result = await ElMessageBox.prompt('请填写取消该授权申请的原因', '取消授权申请', {
      confirmButtonText: '确认取消',
      cancelButtonText: '返回',
      inputPlaceholder: '如：业务需求变更 / 重复申请',
      inputValidator: (value) => (value && value.trim().length >= 2 ? true : '请填写取消原因')
    })
    reason = result.value || ''
  } catch (error) {
    return
  }
  try {
    await authzApi.revokeGrant(row.id, { reason })
    ElMessage.success('授权申请已取消')
    await load()
  } catch (error) {
    // 错误提示由请求层统一处理
  }
}

async function handleRenew(row) {
  // 续期新到期日：默认在原到期日基础上顺延 90 天，且不得超过「今天 + 1 年」
  const base = row.validTo ? new Date(String(row.validTo).replace(' ', 'T')).getTime() : Date.now()
  const pad = (n) => String(n).padStart(2, '0')
  const toDateText = (time) => {
    const date = new Date(time)
    return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`
  }
  const defaultDate = toDateText(Math.max(base, Date.now()) + 90 * 24 * 3600 * 1000)
  const maxDate = toDateText(Date.now() + 365 * 24 * 3600 * 1000)

  let validTo = ''
  try {
    const result = await ElMessageBox.prompt(
      `请选择新的到期日期（不得晚于 ${maxDate}，续期同样受 1 年上限约束）`,
      '授权续期',
      {
        confirmButtonText: '确认续期',
        cancelButtonText: '取消',
        inputType: 'date',
        inputValue: defaultDate,
        inputValidator: (value) => {
          if (!value) return '请选择新的到期日期'
          const time = new Date(String(value).replace(' ', 'T')).getTime()
          if (Number.isNaN(time)) return '日期格式不正确，应为 YYYY-MM-DD'
          if (time <= Date.now()) return '新到期日期必须晚于当前时间'
          if (time > Date.now() + 365 * 24 * 3600 * 1000) return '续期后有效期不得超过 1 年'
          return true
        }
      }
    )
    validTo = result.value
  } catch (error) {
    return
  }
  try {
    await authzApi.renewGrant(row.id, { validTo: `${validTo} 23:59:59` })
    ElMessage.success('授权已续期')
    await load()
  } catch (error) {
    // 错误提示由请求层统一处理
  }
}

/* ---------------- 授权详情抽屉 ---------------- */
const detailVisible = ref(false)
const detailLoading = ref(false)
const detail = ref({})

const detailHistory = computed(() => {
  const raw = detail.value?.history
  const rows = Array.isArray(raw) ? raw : []
  return rows.map((item) => {
    // 后端可能返回字符串数组或对象数组，这里统一成时间线需要的结构
    const record = typeof item === 'string' ? { action: item } : item || {}
    return {
      ts: record.ts || record.time || record.createdAt || '',
      title: record.action || record.title || record.type || '权限变更',
      actor: record.actor || record.operator || record.user || '-',
      detail: record.detail || record.comment || record.remark || record.reason || '',
      type: record.result === 'failed' ? 'danger' : 'primary'
    }
  })
})

async function openDetail(row) {
  detailVisible.value = true
  detailLoading.value = true
  detail.value = { ...row }
  try {
    const data = await authzApi.grantDetail(row.id)
    detail.value = data || { ...row }
  } catch (error) {
    // 详情获取失败时保留列表行的基础信息，抽屉仍可展示
  } finally {
    detailLoading.value = false
  }
}

/* ---------------- ③ 风险与预警 ---------------- */
const risks = ref({ abnormalAccess: [], expiringSoon: [], mfaFailures: [] })

/** 字段别名兜底：API.md 未固定 risks 子项字段名，逐个键尝试避免 undefined */
function pick(source, keys, fallback = '-') {
  for (const key of keys) {
    const value = source?.[key]
    if (value !== undefined && value !== null && value !== '') return value
  }
  return fallback
}

/** 剩余天数兜底：后端未返回时按到期时间前端计算 */
function daysLeft(validTo) {
  if (!validTo) return 0
  const time = new Date(String(validTo).replace(' ', 'T')).getTime()
  if (Number.isNaN(time)) return 0
  const diff = time - Date.now()
  return diff > 0 ? Math.ceil(diff / (24 * 3600 * 1000)) : 0
}

const abnormalRows = computed(() =>
  (risks.value.abnormalAccess ?? []).map((item) => ({
    ts: pick(item, ['ts', 'time', 'createdAt', 'at']),
    account: pick(item, ['account', 'actor', 'username', 'user', 'subject']),
    action: pick(item, ['action', 'behavior', 'event', 'detail']),
    riskScore: Number(pick(item, ['riskScore', 'score', 'risk'], 0)) || 0
  }))
)

const expiringRows = computed(() =>
  (risks.value.expiringSoon ?? []).map((item) => {
    const validTo = pick(item, ['validTo', 'expireAt', 'expiredAt', 'endTime'], '')
    return {
      code: pick(item, ['code', 'grantCode', 'id']),
      partner: pick(item, ['partner', 'partnerName', 'org']),
      validTo,
      remainDays: Number(pick(item, ['remainDays', 'daysLeft', 'remainingDays', 'days'], daysLeft(validTo))) || 0
    }
  })
)

const mfaRows = computed(() =>
  (risks.value.mfaFailures ?? []).map((item) => ({
    account: pick(item, ['account', 'username', 'actor', 'user']),
    ts: pick(item, ['ts', 'time', 'lastAt', 'createdAt']),
    ip: pick(item, ['ip', 'clientIp', 'sourceIp']),
    count: Number(pick(item, ['count', 'failCount', 'times', 'attempts'], 0)) || 0
  }))
)

async function loadRisks() {
  riskLoading.value = true
  try {
    const data = await authzApi.risks()
    risks.value = {
      abnormalAccess: data?.abnormalAccess ?? [],
      expiringSoon: data?.expiringSoon ?? [],
      mfaFailures: data?.mfaFailures ?? []
    }
  } catch (error) {
    risks.value = { abnormalAccess: [], expiringSoon: [], mfaFailures: [] }
  } finally {
    riskLoading.value = false
  }
}

/** 页签切换：首次进入风险页签时才拉取风险数据，减少无效请求 */
function onTabChange(name) {
  if (name === 'risk' && !abnormalRows.value.length && !expiringRows.value.length && !mfaRows.value.length) {
    loadRisks()
  }
  if (name === 'records') {
    load()
  }
}

onMounted(async () => {
  // 监管端默认停留在风险页签，且不展示「新建数据授权」
  activeTab.value = isRegulator.value ? 'risk' : 'create'
  try {
    await appStore.loadMeta()
  } catch (error) {
    // 元数据拉取失败时，下拉框退化为空列表，不影响表格功能
  }
  await load()
  if (isRegulator.value) {
    await loadRisks()
  }
})
</script>

<style scoped>
.fs-grant-form {
  max-width: 880px;
}
.fs-option {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}
.fs-option__label {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.fs-option__meta {
  display: flex;
  align-items: center;
  gap: 8px;
  flex: 0 0 auto;
  font-size: 12px;
}
.fs-scope-preview {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px;
  margin-top: 8px;
}
.fs-gap {
  margin-right: 4px;
  margin-bottom: 4px;
}
.fs-mt {
  margin-top: 6px;
}
.fs-ml {
  margin-left: 10px;
}
.fs-pager {
  display: flex;
  justify-content: flex-end;
  margin-top: 14px;
}
.fs-risk-alert {
  margin-bottom: 16px;
}
.fs-risk-alert__list {
  margin: 6px 0 0;
  padding-left: 18px;
  line-height: 1.9;
  font-size: 13px;
}
.fs-subsection {
  margin-bottom: 18px;
}
.fs-subsection__title {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-bottom: 10px;
  font-size: 14px;
  font-weight: 600;
}
.fs-scope-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 0;
  border-bottom: 1px dashed var(--fs-border);
}
.fs-history__title {
  font-weight: 600;
  margin-bottom: 2px;
}
</style>
