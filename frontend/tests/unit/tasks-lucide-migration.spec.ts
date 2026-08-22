/**
 * 定时任务页 lucide 图标迁移回归测试。
 *
 * tasks/index.vue 模板庞大（含 MonacoEditor、嵌套 el-tab-pane），整体 shallowMount 易触发
 * vue-template-compiler 解析异常，故本测试改为"契约断言 + 源码扫描"两层守护，
 * 既稳定又能精准捕捉迁移回退：
 *
 *   1. LucideIcon 注册表覆盖 tasks 页用到的所有图标名（防漏注册导致占位框）。
 *   2. tasks/index.vue 源码已清除 el-icon-* 残留、已使用 lucide-icon/LucideIcon。
 *
 * 任一回退（改回 el-icon、name 写错、漏注册、danger 红色丢失）都会让本用例失败。
 */
import { readFileSync } from 'fs'
import { resolve } from 'path'

import { createLocalVue, mount } from '@vue/test-utils'
import BatchButton from '@/components/BatchButton/index.vue'
import LucideIcon from '@/components/common/LucideIcon.vue'

const localVue = createLocalVue()

// tasks/index.vue 源码（一次性读取，断言迁移完整性）
const tasksSource = readFileSync(
  resolve(__dirname, '../../src/views/tasks/index.vue'),
  'utf8'
)

// tasks 页迁移用到的全部图标名（全量清单）
const REQUIRED_TASK_ICONS = [
  'play', 'pause', 'trash', 'refresh-cw', 'plus',      // 批量工具栏
  'chevron-down',                                       // 操作触发箭头
  'pencil', 'eye', 'info', 'check',                     // 下拉项 + 表单
  'bar-chart-3', 'circle-check-big', 'circle-x', 'calendar-days', // 统计卡片
  'search', 'rotate-ccw', 'download', 'wand-sparkles',  // 查询/操作按钮
  'file-text'                                           // 任务类型选项
]

describe('tasks 页 lucide 图标迁移回归', () => {
  describe('LucideIcon 注册表覆盖', () => {
    it('tasks 页用到的所有图标名都在 LucideIcon ICONS 注册表中', () => {
      const iconSource = readFileSync(
        resolve(__dirname, '../../src/components/common/LucideIcon.vue'),
        'utf8'
      )
      // 从 ICONS 注册表块中提取已注册名（兼容 'kebab-name': Ident 与 ident: Ident 两种写法）
      const registered = new Set<string>()
      const reg = /(?:'([a-z0-9-]+)'|([a-zA-Z][a-zA-Z0-9-]*)):\s*[A-Z]\w+/g
      let m: RegExpExecArray | null
      while ((m = reg.exec(iconSource)) !== null) {
        registered.add(m[1] || m[2])
      }

      const missing = REQUIRED_TASK_ICONS.filter(name => !registered.has(name))
      expect(missing).toEqual([])
    })
  })

  describe('tasks/index.vue 源码迁移完整性', () => {
    it('模板/代码区已清除 el-icon-* 字体图标（迁移到 lucide）', () => {
      // 排除注释行
      const lines = tasksSource.split('\n')
      const elIconLines = lines.filter(
        line => /el-icon-/.test(line) && !/^\s*\/\//.test(line) && !/^\s*\*/.test(line)
      )
      expect(elIconLines).toEqual([])
    })

    it('已使用 lucide-icon prop（BatchButton 工具栏迁移）', () => {
      expect(tasksSource).toContain('lucide-icon="play"')
      expect(tasksSource).toContain('lucide-icon="pause"')
      expect(tasksSource).toContain('lucide-icon="trash"')
      expect(tasksSource).toContain('lucide-icon="refresh-cw"')
      expect(tasksSource).toContain('lucide-icon="plus"')
    })

    it('下拉项使用 menu-icon / menu-icon danger 变体', () => {
      expect(tasksSource).toContain('class="menu-icon"')
      expect(tasksSource).toContain('class="menu-icon danger"')
    })

    it('统计卡片 emoji 已替换为 LucideIcon', () => {
      // 排除注释行（文档注释里仍含 ✅，属正常）
      const nonComment = tasksSource.split('\n').filter(
        line => !/^\s*\*/.test(line) && !/^\s*\/\//.test(line)
      ).join('\n')
      expect(nonComment).not.toContain('📊')
      expect(nonComment).not.toContain('✅')
      expect(nonComment).not.toContain('❌')
      expect(nonComment).not.toContain('📅')
      expect(tasksSource).toContain('bar-chart-3')
      expect(tasksSource).toContain('circle-check-big')
      expect(tasksSource).toContain('circle-x')
      expect(tasksSource).toContain('calendar-days')
    })

    it('操作按钮 emoji 已替换为 LucideIcon', () => {
      // 排除注释行
      const nonComment = tasksSource.split('\n').filter(
        line => !/^\s*\*/.test(line) && !/^\s*\/\//.test(line)
      ).join('\n')
      // 清理/导出/批量删除/查询/重置/预览清理 的 emoji 都应消失
      expect(nonComment).not.toContain('🧹')
      expect(nonComment).not.toContain('📥')
      expect(nonComment).not.toContain('🗑️')
      expect(nonComment).not.toContain('🔍')
      expect(nonComment).not.toContain('🔄')
      expect(tasksSource).toContain('wand-sparkles')
      expect(tasksSource).toContain('download')
      expect(tasksSource).toContain('rotate-ccw')
    })

    it('任务表单图标已迁移（chevron-up/down、check、file-text/trash data 值）', () => {
      expect(tasksSource).toContain("chevron-up'")
      expect(tasksSource).not.toContain('el-icon-check')
      expect(tasksSource).toContain("icon: 'file-text'")
      expect(tasksSource).toContain("icon: 'trash'")
    })

    it('已在 @Component 注册 LucideIcon 组件', () => {
      // 组件注册块应含 LucideIcon
      expect(tasksSource).toMatch(/components:\s*\{[^}]*LucideIcon/)
    })
  })

  describe('BatchButton lucide 契约（集成 BatchButton.spec.ts 关键用例）', () => {
    it('lucide-icon 优先于 el-icon，渲染真实 LucideIcon', () => {
      const wrapper = mount(BatchButton, {
        localVue,
        propsData: { lucideIcon: 'play', tooltip: '启用' }
      })
      const icon = wrapper.findComponent(LucideIcon)
      expect(icon.exists()).toBe(true)
      expect(icon.props('name')).toBe('play')
      // 不渲染 el-icon
      expect(wrapper.find('i.el-icon-play').exists()).toBe(false)
    })

    it('danger 操作通过 class="menu-icon danger" 配色（非 BatchButton 内联）', () => {
      // 这是源码契约：danger 红色靠全局 menu-icon.danger，非组件 prop
      const wrapper = mount(BatchButton, {
        localVue,
        propsData: { lucideIcon: 'trash', tooltip: '删除' }
      })
      // BatchButton 渲染 LucideIcon 但不带 danger（danger 由调用方在下拉项上加 class）
      const icon = wrapper.findComponent(LucideIcon)
      expect(icon.exists()).toBe(true)
      expect(icon.props('name')).toBe('trash')
    })
  })
})
