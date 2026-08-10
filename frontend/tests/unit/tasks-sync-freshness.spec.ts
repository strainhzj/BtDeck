/**
 * 任务同步结果语义（outcome 六态 / skip / 数据新鲜度）回归测试。
 *
 * 背景（PLANS/sync-database-blocking-remediation.md W3-4 / P1-05）：
 * 任务页需要区分 success / partial / skipped / failed / no_action / cancelled 六态，
 * 并对旧数据（无 outcome 字段）回退到传统 success 布尔两态展示。
 *
 * tasks/index.vue 模板庞大（MonacoEditor、嵌套 el-tab-pane、CronEditor），整体 mount
 * 易触发 vue-template-compiler 解析异常（与 tasks-lucide-migration.spec.ts 同一原因），
 * 故采用"映射函数单测 + 轻量渲染组件 + 源码契约扫描"三层守护：
 *   1. 映射函数单测：getTaskOutcomeMeta 六态/空值回退、isTaskDataStale 三场景、
 *      getStaleTooltipText 两种成因文案。
 *   2. 轻量组件：mount 一个使用 getTaskOutcomeMeta 渲染结果标签的最小组件
 *      （class 风格 + render 函数，jest 下 Vue 为 runtime 构建、无模板编译器），
 *      验证标签 type/文案与无 outcome 时的回退占位。
 *   3. 源码契约：tasks/index.vue 已接入六态映射与 stale 告警，且日志展示保留
 *      success 布尔回退。
 */
import { readFileSync } from 'fs'
import { resolve } from 'path'

import Vue, { CreateElement } from 'vue'
import { Component, Prop } from 'vue-property-decorator'
import { createLocalVue, mount } from '@vue/test-utils'
import {
  getTaskOutcomeMeta,
  getStaleTooltipText,
  isTaskDataStale,
  TaskOutcome
} from '@/api/tasks'

describe('任务 outcome 六态映射（getTaskOutcomeMeta）', () => {
  it.each([
    ['success', 'success', '成功'],
    ['partial', 'warning', '部分成功'],
    ['skipped', 'info', '已跳过'],
    ['failed', 'danger', '失败'],
    ['no_action', 'info', '无变化'],
    ['cancelled', 'info', '已取消']
  ] as const)('%s → el-tag type=%s 文案=%s', (outcome, tagType, text) => {
    expect(getTaskOutcomeMeta(outcome)).toEqual({ type: tagType, text })
  })

  it('无 outcome（旧数据）回退：undefined / null 返回 null', () => {
    expect(getTaskOutcomeMeta(undefined)).toBeNull()
    expect(getTaskOutcomeMeta(null)).toBeNull()
  })

  it('未知 outcome 取值防御性回退为 null（后端契约外值不破坏展示）', () => {
    expect(getTaskOutcomeMeta('unknown' as TaskOutcome)).toBeNull()
  })
})

describe('任务数据陈旧（isTaskDataStale）', () => {
  it('stale === true 时始终判定陈旧（连续跳过超阈值场景）', () => {
    expect(isTaskDataStale(true, '2026-08-01 10:00:00', '2026-08-10 10:00:00')).toBe(true)
    expect(isTaskDataStale(true, null, null)).toBe(true)
  })

  it('无成功数据但存在执行尝试时判定陈旧', () => {
    expect(isTaskDataStale(false, null, '2026-08-10 10:00:00')).toBe(true)
    expect(isTaskDataStale(undefined, undefined, '2026-08-10 10:00:00')).toBe(true)
  })

  it('有成功数据或所有字段缺失时判定不陈旧（兼容旧数据）', () => {
    expect(isTaskDataStale(false, '2026-08-10 10:00:00', '2026-08-10 10:00:00')).toBe(false)
    expect(isTaskDataStale(undefined, undefined, undefined)).toBe(false)
    expect(isTaskDataStale(null, null, null)).toBe(false)
  })

  it('陈旧提示文案区分两种成因', () => {
    // 成因1：有过成功数据但已超期（文案含最后数据更新时间）
    expect(getStaleTooltipText('2026-08-10 10:00:00', '2026-08-11 10:00:00')).toContain('2026-08-10 10:00:00')
    // 成因2：有执行尝试但从未成功
    expect(getStaleTooltipText(null, '2026-08-11 10:00:00')).toContain('尚无成功数据更新')
    // 无上下文兜底文案
    expect(getStaleTooltipText(null, null)).toBe('数据陈旧：最近一次数据更新距今过久')
  })
})

describe('outcome 标签渲染（轻量组件）', () => {
  const localVue = createLocalVue()

  // 最小展示组件：与 tasks/index.vue "最近结果" 单元格相同的映射逻辑
  @Component
  class OutcomeTag extends Vue {
    @Prop({ type: String, default: null }) readonly outcome!: string | null

    render(h: CreateElement) {
      const meta = getTaskOutcomeMeta(this.outcome)
      if (meta) {
        return h('span', { class: 'outcome-tag', attrs: { 'data-type': meta.type } }, meta.text)
      }
      return h('span', { class: 'outcome-fallback' }, '—')
    }
  }

  it('六态渲染为对应标签 type 与中文文案', () => {
    const wrapper = mount(OutcomeTag, { localVue, propsData: { outcome: 'partial' } })
    const tag = wrapper.find('.outcome-tag')
    expect(tag.exists()).toBe(true)
    expect(tag.attributes('data-type')).toBe('warning')
    expect(tag.text()).toBe('部分成功')
  })

  it('无 outcome 时渲染回退占位（旧数据兼容）', () => {
    const wrapper = mount(OutcomeTag, { localVue, propsData: { outcome: null } })
    expect(wrapper.find('.outcome-tag').exists()).toBe(false)
    expect(wrapper.find('.outcome-fallback').exists()).toBe(true)
    expect(wrapper.text()).toBe('—')
  })
})

describe('tasks/index.vue 源码契约（W3-4 接入守卫）', () => {
  const tasksSource = readFileSync(
    resolve(__dirname, '../../src/views/tasks/index.vue'),
    'utf8'
  )

  it('任务列表"上次执行"列已接入 outcome 六态与数据陈旧告警', () => {
    expect(tasksSource).toContain('getTaskOutcomeMeta(scope.row.lastOutcome)')
    expect(tasksSource).toContain(
      'isTaskDataStale(scope.row.stale, scope.row.lastSuccessfulDataAt, scope.row.lastAttemptAt)'
    )
    expect(tasksSource).toContain('数据陈旧')
  })

  it('日志表格执行结果保留 success 布尔回退（兼容旧日志）', () => {
    expect(tasksSource).toContain('getTaskOutcomeMeta(scope.row.outcome)')
    expect(tasksSource).toContain("scope.row.success ? '成功' : '失败'")
  })

  it('日志详情弹窗与复制文案同步六态文案', () => {
    expect(tasksSource).toContain('getTaskOutcomeMeta(selectedLog?.outcome)')
    expect(tasksSource).toContain('执行结果：${outcomeText}')
  })
})
