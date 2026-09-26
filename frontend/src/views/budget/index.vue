<template>
  <section class="page" data-module="budget">
    <header class="page-head">
      <div>
        <h2>预算科目管理</h2>
        <p class="page-desc">维护预算科目，支持按科目名称、费用类别、负责人与剩余额度范围组合筛选，合计与导出始终跟随当前条件。</p>
      </div>
      <div class="page-actions">
        <button class="btn primary" type="button" @click="openCreate">登记预算科目</button>
        <button class="btn" type="button" @click="exportRows">导出预算科目清单</button>
      </div>
    </header>

    <div class="stat-row">
      <article v-for="item in stats" :key="item.label" class="stat-card">
        <span class="stat-label">{{ item.label }}</span>
        <strong class="stat-value">{{ item.value }}</strong>
      </article>
    </div>

    <form class="filter-bar" @submit.prevent="reload">
      <label v-for="field in filterFields" :key="field.key" class="filter-item">
        <span>{{ field.label }}</span>
        <input
          v-model="filters[field.key]"
          :type="field.numeric ? 'number' : 'text'"
          :placeholder="field.numeric ? `按${field.label}过滤` : `按${field.label}检索`"
        />
      </label>
      <button class="btn" type="submit">查询</button>
      <button class="btn ghost" type="button" @click="resetFilters">重置条件</button>
    </form>

    <table class="data-table">
      <thead>
        <tr>
          <th v-for="column in columns" :key="column">{{ column }}</th>
          <th>可执行动作</th>
        </tr>
      </thead>
      <tbody>
        <template v-for="row in rows" :key="String(row.id)">
          <tr>
            <td v-for="column in columns" :key="column">{{ row[column] ?? '—' }}</td>
            <td class="row-actions">
              <button class="link" type="button" @click="toggleDetail(row)">
                {{ expandedId === row.id ? '收起' : '查看' }}
              </button>
              <button
                v-for="action in actions"
                :key="action"
                class="link"
                type="button"
                @click="runAction(action, row)"
              >
                {{ action }}
              </button>
            </td>
          </tr>
          <tr v-if="expandedId === row.id" class="detail-row">
            <td :colspan="columns.length + 1">
              <dl class="detail-grid">
                <div v-for="field in detailFields" :key="field" class="detail-item">
                  <dt>{{ field }}</dt>
                  <dd>{{ displayValue(row[field]) }}</dd>
                </div>
              </dl>
            </td>
          </tr>
        </template>
        <tr v-if="!rows.length">
          <td :colspan="columns.length + 1" class="empty-state">{{ emptyText }}</td>
        </tr>
      </tbody>
    </table>

    <footer class="page-foot">
      <span>共 {{ total }} 条预算科目记录</span>
      <span v-if="errorMessage" class="error-text">
        {{ errorMessage }}
        <button class="link" type="button" @click="reload">重试</button>
      </span>
    </footer>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'

import { request } from '@/api/client'

type Row = Record<string, string | number | null>

const ENDPOINT = '/api/budget'
const columns = ["科目编号", "科目名称", "费用类别", "负责人", "预算金额", "已用金额", "剩余额度", "科目状态"]
const actions = ["提交审批", "确认批复", "标记超支"]
const detailFields = ["科目编号", "科目名称", "费用类别", "负责人", "审批人", "预算金额", "已用金额", "剩余额度", "科目状态", "超支原因"]
const filterFields = [
  { key: 'keyword', label: '科目编号', numeric: false },
  { key: 'name', label: '科目名称', numeric: false },
  { key: 'category', label: '费用类别', numeric: false },
  { key: 'owner', label: '负责人', numeric: false },
  { key: 'remaining_min', label: '剩余额度下限', numeric: true },
  { key: 'remaining_max', label: '剩余额度上限', numeric: true },
]

const rows = ref<Row[]>([])
const total = ref(0)
const errorMessage = ref('')
const expandedId = ref<string | number | null>(null)
const filters = ref<Record<string, string>>({
  keyword: '',
  name: '',
  category: '',
  owner: '',
  remaining_min: '',
  remaining_max: '',
})
const stats = ref([
  { label: '预算总额', value: '0' },
  { label: '已用金额', value: '0' },
  { label: '剩余额度', value: '0' },
  { label: '超支科目', value: '0' },
])

const hasActiveFilters = computed(() =>
  Object.values(filters.value).some((value) => String(value).trim() !== ''),
)

const emptyText = computed(() =>
  hasActiveFilters.value
    ? '没有匹配当前筛选条件的预算科目，可调整条件后重新查询'
    : '暂无预算科目数据，可先登记预算科目',
)

function displayValue(value: Row[string]): string {
  if (value === null || value === undefined || String(value).trim() === '') {
    return '—'
  }
  return String(value)
}

function formatAmount(value: unknown): string {
  const num = Number(value)
  if (!Number.isFinite(num)) {
    return '0'
  }
  return num.toLocaleString('zh-CN', { maximumFractionDigits: 2 })
}

function buildQuery(): string {
  const params = new URLSearchParams()
  for (const [key, value] of Object.entries(filters.value)) {
    const text = String(value).trim()
    if (text) {
      params.set(key, text)
    }
  }
  return params.toString()
}

function validateFilters(): boolean {
  const { remaining_min: min, remaining_max: max } = filters.value
  for (const [label, text] of [['剩余额度下限', min], ['剩余额度上限', max]] as const) {
    if (text.trim() && !Number.isFinite(Number(text))) {
      errorMessage.value = `${label}需要填写数字，请调整后重试`
      return false
    }
  }
  if (min.trim() && max.trim() && Number(min) > Number(max)) {
    errorMessage.value = '剩余额度下限不能大于上限，请调整范围'
    return false
  }
  return true
}

function resetFilters() {
  for (const key of Object.keys(filters.value)) {
    filters.value[key] = ''
  }
  void reload()
}

function exportRows() {
  const query = buildQuery()
  window.open(`${ENDPOINT}/export${query ? `?${query}` : ''}`, '_blank')
}

function openCreate() {
  errorMessage.value = '预算科目登记入口尚未接入审批流'
}

function toggleDetail(row: Row) {
  expandedId.value = expandedId.value === row.id ? null : row.id ?? null
}

async function runAction(action: string, row: Row) {
  errorMessage.value = ''
  let reason: string | undefined
  if (action === '标记超支') {
    const input = window.prompt('可填写超支原因，留空则稍后在明细中补充', String(row['超支原因'] ?? ''))
    if (input === null) {
      return
    }
    reason = input
  }
  try {
    const response = await request(`${ENDPOINT}/${row.id}/actions`, {
      method: 'POST',
      body: JSON.stringify({ action, 超支原因: reason }),
    })
    if (!response.ok) {
      throw new Error('预算科目动作未生效，请稍后重试')
    }
    await reload()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '预算科目操作失败'
  }
}

async function loadList(query: string) {
  const response = await request(`${ENDPOINT}?${query}`)
  if (!response.ok) {
    throw new Error('预算科目列表读取失败')
  }
  const payload = await response.json()
  rows.value = payload.items ?? []
  total.value = payload.total ?? rows.value.length
}

async function loadSummary(query: string) {
  const response = await request(`${ENDPOINT}/summary?${query}`)
  if (!response.ok) {
    throw new Error('剩余额度合计读取失败')
  }
  const payload = await response.json()
  stats.value = [
    { label: '预算总额', value: formatAmount(payload['预算总额']) },
    { label: '已用金额', value: formatAmount(payload['已用金额']) },
    { label: '剩余额度', value: formatAmount(payload['剩余额度']) },
    { label: '超支科目', value: String(payload['超支科目'] ?? 0) },
  ]
}

async function reload() {
  errorMessage.value = ''
  if (!validateFilters()) {
    return
  }
  const query = buildQuery()
  try {
    // 列表与合计用同一组筛选条件请求，保证切换条件后两者范围一致
    await Promise.all([loadList(query), loadSummary(query)])
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '预算科目数据读取失败'
  }
}

onMounted(reload)
</script>

<style scoped>
.detail-row td {
  background: #f8fafc;
}

.detail-grid {
  display: flex;
  flex-wrap: wrap;
  gap: 8px 24px;
  margin: 0;
}

.detail-item dt {
  font-size: 12px;
  color: var(--muted);
}

.detail-item dd {
  margin: 2px 0 0;
  font-size: 13px;
}

.filter-item input[type='number'] {
  width: 110px;
}
</style>
