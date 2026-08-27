/**
 * 移动系统设置页契约：整页复用桌面设置页组件（双因素认证 + 修改密码同源），
 * 桌面组件以 stub 替身（真实 2FA/改密状态机由桌面侧 spec 覆盖）。
 */

import { shallowMount, Wrapper } from '@vue/test-utils'
import fs from 'fs'
import path from 'path'
import MobileSettings from '@/views/mobile/settings.vue'

jest.mock('@/views/settings/index.vue', () => ({
  name: 'SettingsPage',
  template: '<div class="settings-page-stub" />'
}))

const mountPage = (): Wrapper<Vue> => shallowMount(MobileSettings)

const readMobileSettingsSource = (): string =>
  fs.readFileSync(path.resolve(__dirname, '../../src/views/mobile/settings.vue'), 'utf-8')

const readDesktopSettingsSource = (): string =>
  fs.readFileSync(path.resolve(__dirname, '../../src/views/settings/index.vue'), 'utf-8')

describe('views/mobile/MobileSettings', () => {
  it('渲染桌面设置页组件（整页复用，双因素认证/修改密码同源）', () => {
    const wrapper = mountPage()
    expect(wrapper.find('.m-settings').exists()).toBe(true)
    expect(wrapper.find('settings-page-stub').exists()).toBe(true)
  })

  it('源码契约：复用桌面设置组件并剥离外层留白（避免与移动内容区双重 padding）', () => {
    const source = readMobileSettingsSource()
    expect(source).toContain("@/views/settings/index.vue")
    expect(source).toContain('.settings-container')
  })

  it('桌面设置页契约：改密成功登录跳转按 UI 模式分流（移动模式回 /m/login）', () => {
    const source = readDesktopSettingsSource()
    expect(source).toContain('loginPathForMode')
    // 禁回流：不得再硬编码桌面登录路径
    expect(source).not.toContain("push('/login')")
  })
})
