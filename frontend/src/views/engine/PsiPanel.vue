<template>
  <div class="fs-page">
    <div class="fs-page__header">
      <div>
        <h2 class="fs-page__title">隐私求交集（PSI）</h2>
        <p class="fs-page__subtitle">
          双方在不暴露各自集合明文的前提下求取交集：本方商户白名单与对方清单各自本地哈希后，
          仅交换经 RSA 盲签名变换的值，命中结果由查询方去盲后判定。
        </p>
      </div>
      <div style="display: flex; gap: 10px">
        <el-button @click="loadSample">
          <el-icon><MagicStick /></el-icon>
          <span>载入示例数据</span>
        </el-button>
        <el-button type="primary" :loading="loading" :disabled="!leftItems.length || !rightItems.length" @click="handleSubmit">
          <el-icon><Connection /></el-icon>
          <span>执行隐私求交</span>
        </el-button>
      </div>
    </div>

    <el-alert
      type="info"
      show-icon
      :closable="false"
      title="协议说明：RSA 盲签名 PSI"
      description="双方仅交换「盲化 / 签名后的哈希值」，不传输任何明文集元素：本方先把查询词乘以随机盲因子 r^e 发送给对方；对方用私钥盲签名后返回，本方去盲得到 H(x)^d，再与对方公开的签名集合做哈希表比对。对方无法还原本方查询内容，本方也无法枚举对方集合，未命中项无法反推任何信息。"
    />

    <!-- 双方集合录入 -->
    <div class="fs-grid fs-grid--2" style="margin-top: 16px">
      <div class="fs-card">
        <div class="fs-card__header">
          <div class="fs-card__title">本方商户白名单</div>
          <span class="fs-muted">每行一条，共 {{ leftItems.length }} 条</span>
        </div>
        <div class="fs-card__body">
          <el-input
            v-model="leftText"
            type="textarea"
            :rows="12"
            resize="vertical"
            placeholder="每行输入一条商户名称或税号，例如：&#10;深圳跨境优选电商有限公司&#10;91440300MA5xxxxxx1"
          />
        </div>
      </div>

      <div class="fs-card">
        <div class="fs-card__header">
          <div class="fs-card__title">对方清单</div>
          <span class="fs-muted">每行一条，共 {{ rightItems.length }} 条</span>
        </div>
        <div class="fs-card__body">
          <el-input
            v-model="rightText"
            type="textarea"
            :rows="12"
            resize="vertical"
            placeholder="每行输入一条对方清单元素（如合作方商户名单、制裁清单子集）"
          />
        </div>
      </div>
    </div>

    <!-- 求交结果 -->
    <div class="fs-card" style="margin-top: 16px">
      <div class="fs-card__header">
        <div class="fs-card__title">求交结果</div>
        <el-tag v-if="hasResult" size="small" :type="result.intersectionSize ? 'success' : 'info'" effect="plain">
          交集大小 {{ formatNumber(result.intersectionSize ?? 0, 0) }}
        </el-tag>
      </div>
      <div class="fs-card__body" v-loading="loading">
        <el-empty v-if="!hasResult" description="暂无求交结果，请填写双方集合并点击「执行隐私求交」" />

        <template v-else>
          <el-descriptions :column="3" border size="small">
            <el-descriptions-item label="交集大小">
              <el-tag size="small" :type="result.intersectionSize ? 'success' : 'info'" effect="plain">
                {{ formatNumber(result.intersectionSize ?? 0, 0) }} 条
              </el-tag>
            </el-descriptions-item>
            <el-descriptions-item label="本方规模">{{ formatNumber(result.leftSize ?? leftItems.length, 0) }} 条</el-descriptions-item>
            <el-descriptions-item label="对方规模">{{ formatNumber(result.rightSize ?? rightItems.length, 0) }} 条</el-descriptions-item>
            <el-descriptions-item label="计算耗时">{{ formatDuration(result.elapsedMs) }}</el-descriptions-item>
            <el-descriptions-item label="本方重叠率">
              {{ formatPercent(overlapRatio, 2) }}
            </el-descriptions-item>
            <el-descriptions-item label="链上交易ID">
              <span class="fs-mono">{{ result.chainTxId || '待存证' }}</span>
            </el-descriptions-item>
          </el-descriptions>

          <el-divider content-position="left">交集元素</el-divider>
          <div v-if="(result.intersection || []).length">
            <el-tag
              v-for="item in result.intersection || []"
              :key="item"
              type="success"
              effect="plain"
              size="large"
              style="margin: 0 8px 8px 0"
            >
              {{ item }}
            </el-tag>
          </div>
          <el-empty v-else :image-size="60" description="双方集合无交集" />
        </template>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { engineApi } from '@/api'
import { formatDuration, formatNumber, formatPercent } from '@/utils/format'

const loading = ref(false)
const result = ref({})
const leftText = ref('')
const rightText = ref('')

/** 文本域按行拆分为集合元素：去空白、去空行，保证提交的长度口径与后端一致 */
function toItems(text) {
  return String(text || '')
    .split('\n')
    .map((item) => item.trim())
    .filter(Boolean)
}

const leftItems = computed(() => toItems(leftText.value))
const rightItems = computed(() => toItems(rightText.value))
const hasResult = computed(() => Object.keys(result.value || {}).length > 0)

// 重叠率 = 交集 / 本方规模，反映本方白名单在对方清单中的命中比例
const overlapRatio = computed(() => {
  const size = Number(result.value?.leftSize ?? leftItems.value.length) || 0
  if (!size) return 0
  return Number(result.value?.intersectionSize ?? 0) / size
})

function loadSample() {
  leftText.value = [
    '深圳跨境优选电商有限公司',
    '91440300MA5EX00001',
    '广州海丝供应链管理有限公司',
    '91440101MA5CX00002',
    '杭州云桥数字科技有限公司',
    '义乌小商品出口贸易行'
  ].join('\n')

  rightText.value = [
    '91440300MA5EX00001',
    '上海泓远国际贸易有限公司',
    '91440101MA5CX00002',
    '北京中欧通供应链有限公司',
    '义乌小商品出口贸易行',
    'Shenzhen Global Trade Co., Ltd.'
  ].join('\n')

  ElMessage.success('已载入示例数据，可直接执行隐私求交')
}

async function handleSubmit() {
  if (!leftItems.value.length || !rightItems.value.length) {
    ElMessage.warning('请先在左右两侧各输入至少一条集合元素')
    return
  }

  loading.value = true
  try {
    const data = await engineApi.psi({ left: leftItems.value, right: rightItems.value })
    result.value = data || {}
    ElMessage.success(`隐私求交完成，交集 ${result.value.intersectionSize ?? 0} 条`)
  } catch (error) {
    result.value = {}
  } finally {
    loading.value = false
  }
}
</script>
