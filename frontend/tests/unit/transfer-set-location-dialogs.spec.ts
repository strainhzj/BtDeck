import fs from 'fs'
import { createLocalVue, shallowMount, Wrapper } from '@vue/test-utils'
import Vue from 'vue'

import SetLocationDialog from '@/views/torrents/components/SetLocationDialog.vue'
import TransferDialog from '@/views/torrents/components/TransferDialog.vue'
import { getDownloaderList, getDownloaderPaths } from '@/api/torrents'

/**
 * 转移/修改路径弹窗移动端适配（源码契约 + 挂载行为）：
 * - jsdom 不应用媒体查询，布局保护走源码契约（仓内既有模式），视觉由真机兜底；
 * - 根因防回退：SetLocationDialog 曾用根 div 包 el-dialog——调用方透传的
 *   custom-class 经 $attrs 落到外层 div，94vw 收窄从未生效。源码契约断言
 *   custom-class 打在 el-dialog 根上，挂载行为断言其真实到达 ElDialog
 *   （customClass prop）；div 包裹回退两道都会红；
 * - 组件自治适配（TorrentAddDialog 2026-09-12 模式）：非 scoped ≤768 块收
 *   弹窗骨架（94vw !important 压内联 width / body 64vh 内滚），scoped 块收
 *   内部布局（表单标签上堆 / 底部按钮 44px 等宽）。
 */

jest.mock('@/api/torrents', () => ({
  transferSeed: jest.fn(),
  getDownloaderList: jest.fn(),
  getDownloaderPaths: jest.fn(),
  deleteTorrents: jest.fn(),
  setTorrentLocation: jest.fn()
}))

const localVue = createLocalVue()

// 测试环境未安装 Element：注册可断言的 ElDialog 占位组件（声明被测 props，
// 渲染 slot 让嵌套结构可枚举）。custom-class 经 Vue 的 attrs→prop 提取，
// 在占位组件上读 customClass 即验证「真实到达 el-dialog」。
const ElDialogStub = Vue.extend({
  name: 'ElDialog',
  props: {
    visible: {},
    customClass: {},
    // 无值属性 append-to-body 按 Element 真组件语义转 true
    appendToBody: { type: Boolean }
  },
  render(h) {
    return h('div', { class: 'el-dialog-stub' }, [this.$slots.default, this.$slots.footer])
  }
})
localVue.component('ElDialog', ElDialogStub)

async function flushPromises(): Promise<void> {
  for (let index = 0; index < 20; index += 1) {
    await Promise.resolve()
  }
}

const readSource = (relative: string): string =>
  fs.readFileSync(relative, 'utf-8')

const transferSource = (): string =>
  readSource('src/views/torrents/components/TransferDialog.vue')

const setLocationSource = (): string =>
  readSource('src/views/torrents/components/SetLocationDialog.vue')

const mobileTorrentsSource = (): string =>
  readSource('src/views/mobile/torrents.vue')

/** 提取非 scoped 样式块（`<style lang="scss">` 精确匹配，scoped 块含 scoped 关键字）。 */
const unscopedStyleBlock = (source: string): string => {
  const match = source.match(/<style lang="scss">([\s\S]*?)<\/style>/)
  return match ? match[1] : ''
}

/** 提取 scoped 样式块。 */
const scopedStyleBlock = (source: string): string => {
  const match = source.match(/<style scoped lang="scss">([\s\S]*?)<\/style>/)
  return match ? match[1] : ''
}

describe('TransferDialog/SetLocationDialog 移动端适配（源码契约）', () => {
  it('custom-class 落在 el-dialog 开标签上（根 div 包裹防回退）', () => {
    const transfer = transferSource()
    expect(transfer).toMatch(/<el-dialog[^>]*custom-class="transfer-dialog"/s)
    // 嵌套删除确认一并收窄（append-to-body，须自有钩子类）
    expect(transfer).toMatch(/<el-dialog[^>]*custom-class="transfer-delete-confirm"/s)

    const setLocation = setLocationSource()
    expect(setLocation).toMatch(/<el-dialog[^>]*custom-class="set-location-dialog"/s)
    // $attrs 陷阱防回退：模板根不得再用 div 包裹 el-dialog
    expect(setLocation).not.toMatch(/<div>\s*<el-dialog/)
  })

  it('非 scoped ≤768 块：94vw !important 压内联宽度 + 弹窗体 64vh 内滚', () => {
    const transfer = unscopedStyleBlock(transferSource())
    expect(transfer).toContain('@media (max-width: 768px)')
    expect(transfer).toContain('.transfer-dialog')
    expect(transfer).toContain('width: 94vw !important')
    expect(transfer).toContain('max-height: 64vh')
    // 嵌套删除确认弹窗收窄（400px 桌面宽度让位 88vw）
    expect(transfer).toContain('.transfer-delete-confirm')
    expect(transfer).toContain('width: 88vw !important')

    const setLocation = unscopedStyleBlock(setLocationSource())
    expect(setLocation).toContain('@media (max-width: 768px)')
    expect(setLocation).toContain('.set-location-dialog')
    expect(setLocation).toContain('width: 94vw !important')
    expect(setLocation).toContain('max-height: 64vh')
  })

  it('非 scoped ≤768 块：UI 移动化（头部/关闭钮触控/内边距/圆角，2026-09-12 复验）', () => {
    for (const source of [transferSource(), setLocationSource()]) {
      const block = unscopedStyleBlock(source)
      // 关闭钮触控区 36px（Element 默认 20×20 指尖难命中）
      expect(block).toContain('.el-dialog__headerbtn')
      expect(block).toContain('width: 36px')
      // 标题移动字号与弹窗圆角
      expect(block).toContain('.el-dialog__title')
      expect(block).toContain('font-size: 16px')
      expect(block).toContain('border-radius: 12px')
      // 体/头部/底部内边距收敛（Element 桌面 padding 太松散）
      expect(block).toMatch(/\.el-dialog__body\s*{[^}]*padding: 12px 14px/s)
      expect(block).toContain('.el-dialog__footer')
    }
  })

  it('scoped ≤768 块：表单标签上堆 + 底部按钮 44px 等宽触控 + 复选框触控行', () => {
    for (const source of [transferSource(), setLocationSource()]) {
      const scoped = scopedStyleBlock(source)
      expect(scoped).toContain('@media (max-width: 768px)')
      // label-width 110/120px 左右布局 → 标签上堆、内容全宽
      expect(scoped).toContain('width: auto !important')
      expect(scoped).toContain('margin-left: 0 !important')
      expect(scoped).toContain('min-height: 44px')
      // 「删除原种子/移动已下载的文件」复选框行放大触控
      expect(scoped).toMatch(/\.el-checkbox\s*{[^}]*padding: 6px 0/s)
    }
  })
})

describe('移动种子页透传清理（源码契约）', () => {
  it('转移/修改路径弹窗不再依赖 m-reuse-dialog 透传（组件自治适配）', () => {
    const source = mobileTorrentsSource()
    expect(source).not.toMatch(/<transfer-dialog[^>]*custom-class=/s)
    expect(source).not.toMatch(/<set-location-dialog[^>]*custom-class=/s)
  })

  it('m-reuse-dialog 仍服务 Tracker操作/全局替换两弹窗（组件自治后使用处恰 2）', () => {
    const source = mobileTorrentsSource()
    expect(source).toMatch(/<tracker-operation-dialog[^>]*custom-class="m-reuse-dialog"/s)
    expect(source).toMatch(/<global-replace-tracker-dialog[^>]*custom-class="m-reuse-dialog"/s)
    // 按属性使用处计数（注释提及不计），防其它弹窗悄悄回流依赖页级透传
    expect(source.match(/custom-class="m-reuse-dialog"/g)).toHaveLength(2)
  })
})

describe('TransferDialog/SetLocationDialog 挂载行为（custom-class 到达 + 打开流程）', () => {
  let wrapper: Wrapper<Vue>

  beforeEach(() => {
    jest.clearAllMocks()
    jest.mocked(getDownloaderPaths).mockResolvedValue({
      code: '200', status: 'success', msg: 'ok', data: { paths: [] }
    } as never)
    jest.mocked(getDownloaderList).mockResolvedValue({
      code: '200', status: 'success', msg: 'ok', data: []
    } as never)
  })

  afterEach(() => {
    wrapper?.destroy()
  })

  const mountWith = (component: typeof SetLocationDialog | typeof TransferDialog, propsData: Record<string, unknown>): Wrapper<Vue> =>
    shallowMount(component as never, {
      localVue,
      propsData,
      mocks: {
        $message: { success: jest.fn(), error: jest.fn(), warning: jest.fn() }
      }
    })

  /** shallowMount 下 el-form 是 stub：补回 resetForm/validate 依赖的方法。 */
  const stubFormRef = (vm: any, refName: string): void => {
    vm.$refs[refName] = {
      clearValidate: jest.fn(),
      validate: jest.fn().mockResolvedValue(undefined)
    }
  }

  it('SetLocationDialog：自有 custom-class 真实到达 ElDialog 组件（误删/改名即红）', () => {
    wrapper = mountWith(SetLocationDialog, {
      visible: false,
      torrents: [{ hash: 'h1', savePath: '/downloads', downloader_id: 'dl-1' }]
    })
    const dialog = wrapper.findComponent({ name: 'ElDialog' })
    expect(dialog.exists()).toBe(true)
    // 钉「到达 ElDialog」而非滞留 attrs；根 div 包裹回退由源码契约用例拦截
    // （div 回退时模板字面量仍在 el-dialog 上，本用例不敏感——两道防线分工）
    expect(dialog.props('customClass')).toBe('set-location-dialog')
  })

  it('SetLocationDialog：visible 置真打开弹窗并按下载器拉取路径建议', async() => {
    wrapper = mountWith(SetLocationDialog, {
      visible: false,
      torrents: [{ hash: 'h1', savePath: '/downloads', downloader_id: 'dl-1' }]
    })
    stubFormRef(wrapper.vm as any, 'locationForm')
    await wrapper.setProps({ visible: true })
    await flushPromises()

    expect(getDownloaderPaths).toHaveBeenCalledWith('dl-1')
    const dialog = wrapper.findComponent({ name: 'ElDialog' })
    expect(dialog.props('visible')).toBe(true)
  })

  it('TransferDialog：主弹窗与嵌套删除确认的 custom-class 均到达各自 el-dialog', () => {
    wrapper = mountWith(TransferDialog, {
      visible: false,
      torrent: { hash: 'h1', downloaderId: 'dl-1', downloaderName: '源', savePath: '/downloads', infoId: 1 }
    })
    const dialogs = wrapper.findAllComponents({ name: 'ElDialog' })
    expect(dialogs).toHaveLength(2)
    expect(dialogs.at(0).props('customClass')).toBe('transfer-dialog')
    // 嵌套删除确认（append-to-body 脱离组件树，移动收窄只能靠自有钩子类）
    const confirm = dialogs.at(1)
    expect(confirm.props('customClass')).toBe('transfer-delete-confirm')
    expect(confirm.props('appendToBody')).toBe(true)
  })

  it('TransferDialog：visible 置真打开弹窗并加载可用下载器', async() => {
    wrapper = mountWith(TransferDialog, {
      visible: false,
      torrent: { hash: 'h1', downloaderId: 'dl-1', downloaderName: '源', savePath: '/downloads', infoId: 1 }
    })
    stubFormRef(wrapper.vm as any, 'transferForm')
    await wrapper.setProps({ visible: true })
    await flushPromises()

    expect(getDownloaderList).toHaveBeenCalledWith({ enabled: true })
    const dialog = wrapper.findAllComponents({ name: 'ElDialog' }).at(0)
    expect(dialog.props('visible')).toBe(true)
  })
})
