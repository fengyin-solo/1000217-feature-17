<template>
  <section class="page" data-module="budget">
    <header class="page-head">
      <div>
        <h2>预算科目管理</h2>
        <p class="page-desc">维护预算科目，围绕科目编号、科目名称、费用类别、预算金额做登记、筛选与状态流转。</p>
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
      <label class="filter-item">
        <span>科目名称</span>
        <input v-model="filters.name" placeholder="按科目名称检索" />
      </label>
      <label class="filter-item">
        <span>费用类别</span>
        <select v-model="filters.category">
          <option value="">全部类别</option>
          <option v-for="item in categoryOptions" :key="item" :value="item">{{ item }}</option>
        </select>
      </label>
      <label class="filter-item">
        <span>负责人</span>
        <select v-model="filters.owner">
          <option value="">全部负责人</option>
          <option v-for="item in ownerOptions" :key="item" :value="item">{{ item }}</option>
        </select>
      </label>
      <fieldset class="filter-item filter-range">
        <legend>剩余额度范围</legend>
        <input v-model="filters.remainingMin" type="number" placeholder="最低额度" />
        <span class="range-sep">至</span>
        <input v-model="filters.remainingMax" type="number" placeholder="最高额度" />
      </fieldset>
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
        <tr v-for="row in (loadError ? [] : rows)" :key="String(row.id)">
          <td
            v-for="column in columns"
            :key="column"
            :class="{ 'negative-amount': column === '剩余额度' && toNumber(row[column]) < 0 }"
          >
            {{ displayCell(column, row) }}
          </td>
          <td class="row-actions">
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
        <tr v-if="loadError">
          <td :colspan="columns.length + 1" class="empty-state">
            <span class="error-text">{{ loadError }}</span>
            <button class="btn" type="button" @click="reload">重试</button>
          </td>
        </tr>
        <tr v-else-if="!rows.length">
          <td :colspan="columns.length + 1" class="empty-state">{{ emptyText }}</td>
        </tr>
      </tbody>
    </table>

    <footer class="page-foot">
      <span>匹配 {{ total }} 条 / 共 {{ totalAll }} 条预算科目记录（合计与导出始终取全部科目）</span>
      <span v-if="actionError" class="error-text">{{ actionError }}</span>
    </footer>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'

import { request } from '@/api/client'

type Row = Record<string, string | number | null>

interface Filters {
  name: string
  category: string
  owner: string
  remainingMin: string
  remainingMax: string
}

const ENDPOINT = '/api/budget'
const columns = ["科目编号", "科目名称", "费用类别", "预算金额", "已用金额", "剩余额度", "负责人", "审批人", "科目状态", "超支原因"]
const amountColumns = ["预算金额", "已用金额", "剩余额度"]
const actions = ["提交审批", "确认批复", "标记超支"]

const rows = ref<Row[]>([])
const total = ref(0)
const totalAll = ref(0)
const loadError = ref('')
const actionError = ref('')
const stats = ref([
  { label: "预算总额", value: '—' },
  { label: "已用金额", value: '—' },
  { label: "超支科目", value: '—' },
])
const categoryOptions = ref<string[]>([])
const ownerOptions = ref<string[]>([])
const filters = ref<Filters>({ name: '', category: '', owner: '', remainingMin: '', remainingMax: '' })

const emptyText = computed(() => {
  if (totalAll.value === 0) {
    return '暂无预算科目数据，可先登记预算科目'
  }
  return '没有符合筛选条件的预算科目，请调整筛选条件后重试'
})

function toNumber(value: string | number | null | undefined): number {
  const amount = Number(value)
  return Number.isFinite(amount) ? amount : NaN
}

function displayCell(column: string, row: Row): string {
  const value = row[column]
  // 超支原因允许为空：空原因不影响记录查看，统一展示占位符。
  if (value === null || value === undefined || value === '') {
    return '—'
  }
  if (amountColumns.includes(column)) {
    const amount = Number(value)
    return Number.isFinite(amount) ? amount.toLocaleString('zh-CN') : String(value)
  }
  return String(value)
}

function resetFilters() {
  filters.value = { name: '', category: '', owner: '', remainingMin: '', remainingMax: '' }
  void reload()
}

function exportRows() {
  // 导出范围固定为全部科目，不受当前筛选条件影响。
  window.open(`${ENDPOINT}/export`, '_blank')
}

function openCreate() {
  actionError.value = '预算科目登记入口尚未接入审批流'
}

async function runAction(action: string, row: Row) {
  actionError.value = ''
  try {
    const body: Record<string, string> = { action }
    if (action === '标记超支') {
      // 超支原因为选填：取消则不执行动作，留空也允许提交。
      const reason = window.prompt('请填写超支原因（可留空）', '')
      if (reason === null) {
        return
      }
      body['超支原因'] = reason
    }
    const response = await request(`${ENDPOINT}/${row.id}/actions`, {
      method: 'POST',
      body: JSON.stringify(body),
    })
    const payload = await response.json().catch(() => null)
    if (!response.ok || payload?.ok === false) {
      throw new Error(payload?.message ?? '预算科目动作未生效，请稍后重试')
    }
    await Promise.all([reload(), loadSummary()])
  } catch (error) {
    actionError.value = error instanceof Error ? error.message : '预算科目操作失败'
  }
}

async function loadSummary() {
  // 列表合计与筛选项只随数据变化刷新，切换筛选条件时不重新拉取，口径保持全部科目。
  try {
    const response = await request(`${ENDPOINT}/summary`)
    if (!response.ok) {
      return
    }
    const payload = await response.json()
    const summary = payload.summary ?? {}
    stats.value = [
      { label: "预算总额", value: formatAmount(summary["预算总额"]) },
      { label: "已用金额", value: formatAmount(summary["已用金额"]) },
      { label: "超支科目", value: String(summary["超支科目"] ?? 0) },
    ]
    totalAll.value = Number(summary["科目总数"] ?? 0)
    categoryOptions.value = payload.options?.["费用类别"] ?? []
    ownerOptions.value = payload.options?.["负责人"] ?? []
  } catch {
    // 合计读取失败不阻断列表；下次动作或刷新页面时再取。
  }
}

function formatAmount(value: unknown): string {
  const amount = Number(value)
  return Number.isFinite(amount) ? amount.toLocaleString('zh-CN') : '—'
}

async function reload() {
  loadError.value = ''
  const params = new URLSearchParams()
  if (filters.value.name.trim()) {
    params.set('name', filters.value.name.trim())
  }
  if (filters.value.category) {
    params.set('category', filters.value.category)
  }
  if (filters.value.owner) {
    params.set('owner', filters.value.owner)
  }
  if (filters.value.remainingMin.trim()) {
    params.set('remaining_min', filters.value.remainingMin.trim())
  }
  if (filters.value.remainingMax.trim()) {
    params.set('remaining_max', filters.value.remainingMax.trim())
  }
  const query = params.toString()
  try {
    const response = await request(`${ENDPOINT}${query ? `?${query}` : ''}`)
    const payload = await response.json().catch(() => null)
    if (!response.ok) {
      throw new Error(payload?.detail ?? '预算科目列表读取失败')
    }
    rows.value = payload.items ?? []
    total.value = payload.total ?? rows.value.length
  } catch (error) {
    // 读取失败时保留上一次的筛选结果，并给出可重试的入口。
    loadError.value = error instanceof Error ? error.message : '预算科目列表读取失败'
  }
}

onMounted(() => {
  void reload()
  void loadSummary()
})
</script>
