import { mount } from '@vue/test-utils'
import AppLogo from '../AppLogo.vue'

describe('AppLogo 组件', () => {
  it.each([
    [{ variant: 'full' }, 'btdeck-logo.png'],
    [{ variant: 'full', tone: 'inverse' }, 'btdeck-logo-inverse.png'],
    [{ variant: 'mark' }, 'btdeck-mark.png'],
    [{ variant: 'micro' }, 'btdeck-mark-micro.png'],
    [{ variant: 'mark', tone: 'inverse' }, 'btdeck-mark-inverse.png'],
    [{ variant: 'micro', tone: 'inverse' }, 'btdeck-mark-micro-inverse.png']
  ])('根据 %o 选择对应的光学尺寸与色调资源', (props, filename) => {
    const wrapper = mount(AppLogo, { propsData: props })

    expect(wrapper.find('img').attributes('src')).toContain(`/img/brand/${filename}`)
    wrapper.destroy()
  })
})
