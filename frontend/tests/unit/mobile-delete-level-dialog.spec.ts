/**
 * 移动四级删除对话框契约（2026-09-05 移动验收补齐）：
 * - 四个等级选项与桌面删除下拉同语义（4 标记待删除/3 回收站/2 删任务保数据/1 完全删除）；
 * - 点选后按桌面同款文案二次确认：1/3 警告句式（等级1 error 级），确认通过才 emit confirm；
 * - 取消不 emit；确认后先关对话框再 emit confirm(level)；
 * - DELETE_LEVEL_SUCCESS_TEXT 四级文案单源导出。
 * 注：shallowMount 下 el-dialog 为 stub 不渲染插槽，选项交互直调 choose(opt)。
 */

import { shallowMount, Wrapper } from '@vue/test-utils'
import Vue from 'vue'
import MobileDeleteLevelDialog from '@/views/mobile/components/DeleteLevelDialog.vue'
import { DELETE_LEVEL_SUCCESS_TEXT } from '@/views/mobile/delete-level'

const mountDialog = (confirmResult: Promise<string>): Wrapper<Vue> =>
  shallowMount(MobileDeleteLevelDialog, {
    propsData: { visible: true, name: '测试种子' },
    mocks: {
      $confirm: jest.fn().mockImplementation(() => confirmResult),
      $message: { success: jest.fn(), error: jest.fn() }
    }
  })

/** 挂载级：el-dialog 以渲染插槽的 stub 替身，验证选项按钮真实渲染与点击链 */
const mountDialogUi = (
  props: { busy?: boolean } = {},
  confirmResult: Promise<string> = Promise.resolve('confirm')
): Wrapper<Vue> =>
  shallowMount(MobileDeleteLevelDialog, {
    propsData: { visible: true, name: '测试种子', ...props },
    stubs: {
      'el-dialog': {
        name: 'ElDialogStub',
        props: ['visible'],
        template: '<div class="el-dialog-stub"><slot /></div>'
      }
    },
    mocks: {
      $confirm: jest.fn().mockImplementation(() => confirmResult),
      $message: { success: jest.fn(), error: jest.fn() }
    }
  })

const levelOption = (level: number): { level: number, label: string, icon: string } => {
  const option = (mountDialog(Promise.resolve('confirm')).vm as any).levelOptions.find(
    (item: { level: number }) => item.level === level
  )
  return option
}

describe('views/mobile/components/DeleteLevelDialog', () => {
  it('四个等级选项：与桌面删除下拉同语义、顺序 4→1', () => {
    const wrapper = mountDialog(Promise.resolve('confirm'))
    const options = (wrapper.vm as any).levelOptions as Array<{ level: number, label: string }>
    expect(options.map(item => item.level)).toEqual([4, 3, 2, 1])
    expect(options[0].label).toContain('标记为待删除')
    expect(options[0].label).toContain('推荐')
    expect(options[1].label).toContain('移至回收站')
    expect(options[2].label).toContain('保留数据')
    expect(options[3].label).toContain('完全删除')
  })

  it('等级4：普通确认句式（warning），确认后关闭对话框并 emit confirm(4)', async() => {
    const wrapper = mountDialog(Promise.resolve('confirm'))
    await (wrapper.vm as any).choose(levelOption(4))
    expect(wrapper.vm.$confirm).toHaveBeenCalledWith('确定要将种子标记为待删除吗？', '确认删除', {
      confirmButtonText: '确定',
      cancelButtonText: '取消',
      type: 'warning'
    })
    expect(wrapper.emitted('update:visible')?.[0]).toEqual([false])
    expect(wrapper.emitted('confirm')?.[0]).toEqual([4])
  })

  it('等级1：警告句式 + error 级确认（完全删除不可恢复）', async() => {
    const wrapper = mountDialog(Promise.resolve('confirm'))
    await (wrapper.vm as any).choose(levelOption(1))
    expect(wrapper.vm.$confirm).toHaveBeenCalledWith('警告：此操作将完全删除，是否继续？', '确认删除', {
      confirmButtonText: '确定',
      cancelButtonText: '取消',
      type: 'error'
    })
    expect(wrapper.emitted('confirm')?.[0]).toEqual([1])
  })

  it('等级3：警告句式（回收站破坏性等级同桌面）', async() => {
    const wrapper = mountDialog(Promise.resolve('confirm'))
    await (wrapper.vm as any).choose(levelOption(3))
    expect(wrapper.vm.$confirm).toHaveBeenCalledWith('警告：此操作将移至回收站，是否继续？', '确认删除', expect.objectContaining({ type: 'warning' }))
    expect(wrapper.emitted('confirm')?.[0]).toEqual([3])
  })

  it('取消确认：不 emit confirm、对话框保持打开', async() => {
    const wrapper = mountDialog(Promise.reject('cancel'))
    await (wrapper.vm as any).choose(levelOption(2))
    expect(wrapper.emitted('confirm')).toBeUndefined()
    expect(wrapper.emitted('update:visible')).toBeUndefined()
  })

  it('DELETE_LEVEL_SUCCESS_TEXT：四级成功文案单源齐全', () => {
    expect(DELETE_LEVEL_SUCCESS_TEXT[4]).toBe('已标记为待删除')
    expect(DELETE_LEVEL_SUCCESS_TEXT[3]).toContain('回收站')
    expect(DELETE_LEVEL_SUCCESS_TEXT[2]).toContain('保留')
    expect(DELETE_LEVEL_SUCCESS_TEXT[1]).toBe('已完全删除')
  })

  // ============ 挂载级 UI（2026-09-05 回归加固：选项渲染/点击链/busy 禁用） ============

  it('UI 渲染：四个等级选项按钮按 4→1 顺序渲染，等级1 带 is-danger 样式', async() => {
    const wrapper = mountDialogUi()
    await Vue.nextTick()
    const buttons = wrapper.findAll('.m-delete-level-option')
    expect(buttons).toHaveLength(4)
    expect(buttons.at(0).text()).toContain('等级4：标记为待删除')
    expect(buttons.at(3).text()).toContain('等级1：完全删除')
    expect(buttons.at(3).classes()).toContain('is-danger')
    // 目标种子名在对话框内展示（移动端对话框可能遮挡卡片，需自带上下文）
    expect(wrapper.find('.m-delete-target').text()).toContain('测试种子')
  })

  it('UI 点击链：点等级4 走 $confirm 后 emit confirm(4) 并关闭对话框', async() => {
    const wrapper = mountDialogUi()
    await Vue.nextTick()
    await wrapper.findAll('.m-delete-level-option').at(0).trigger('click')
    await Vue.nextTick()
    expect(wrapper.vm.$confirm).toHaveBeenCalledTimes(1)
    expect(wrapper.emitted('confirm')?.[0]).toEqual([4])
    expect(wrapper.emitted('update:visible')?.[0]).toEqual([false])
  })

  it('UI 点击链：取消确认不 emit（等级1 红色误触保护链完整）', async() => {
    const wrapper = mountDialogUi({}, Promise.reject('cancel'))
    await Vue.nextTick()
    await wrapper.findAll('.m-delete-level-option').at(3).trigger('click')
    await Vue.nextTick()
    expect(wrapper.vm.$confirm).toHaveBeenCalledTimes(1)
    expect(wrapper.emitted('confirm')).toBeUndefined()
    expect(wrapper.emitted('update:visible')).toBeUndefined()
  })

  it('busy 禁用：删除请求在途时选项禁用且点击不触发确认', async() => {
    const wrapper = mountDialogUi({ busy: true })
    await Vue.nextTick()
    const button = wrapper.findAll('.m-delete-level-option').at(0)
    expect(button.attributes('disabled')).toBeDefined()
    await button.trigger('click')
    await Vue.nextTick()
    expect(wrapper.vm.$confirm).not.toHaveBeenCalled()
    expect(wrapper.emitted('confirm')).toBeUndefined()
  })
})
