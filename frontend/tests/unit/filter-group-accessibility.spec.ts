import { mount } from '@vue/test-utils'

import FilterGroup from '@/components/torrents/FilterGroup.vue'

describe('FilterGroup keyboard accessibility', () => {
  const items = [
    { icon: '●', label: '全部', value: '' },
    { icon: '▶', label: '活动中', value: '__active__' },
    { icon: '↑', label: '做种中', value: 'seeding' }
  ]

  it('uses native buttons and exposes expanded/pressed state', async() => {
    const wrapper = mount(FilterGroup, {
      propsData: {
        title: '状态',
        items,
        activeValue: '__active__'
      }
    })
    const header = wrapper.find('.filter-group-header')
    const filterItems = wrapper.findAll('.filter-item')

    expect(header.element.tagName).toBe('BUTTON')
    expect(header.attributes('aria-expanded')).toBe('true')
    expect(header.attributes('aria-controls')).toBeTruthy()
    expect(filterItems.wrappers.every(item => item.element.tagName === 'BUTTON')).toBe(true)
    expect(filterItems.at(1).attributes('aria-pressed')).toBe('true')
    expect(filterItems.at(0).attributes('aria-pressed')).toBe('false')

    // Native button preserves browser Enter/Space activation without custom key handlers.
    await header.trigger('click')
    expect(header.attributes('aria-expanded')).toBe('false')
    expect(wrapper.find('.filter-group-items').isVisible()).toBe(false)

    await header.trigger('click')
    expect(header.attributes('aria-expanded')).toBe('true')

    await filterItems.at(2).trigger('click')
    await filterItems.at(1).trigger('click')
    expect(wrapper.emitted('select')).toEqual([['seeding'], ['__active__']])

    wrapper.destroy()
  })
})
