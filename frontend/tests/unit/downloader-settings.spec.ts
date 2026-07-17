import { resolveEnableSchedule } from '@/views/downloader/settings'

describe('下载器限速设置契约', () => {
  it('保留后端返回的关闭状态，即使历史规则仍然存在', () => {
    expect(resolveEnableSchedule({
      enable_schedule: false,
      schedule_rules: [{ id: 1 }]
    })).toBe(false)
  })

  it('兼容驼峰字段并保留开启状态', () => {
    expect(resolveEnableSchedule({ enableSchedule: true })).toBe(true)
  })

  it('缺少开关字段时默认关闭，不能通过规则存在性推断开启', () => {
    expect(resolveEnableSchedule({ schedule_rules: [{ id: 1 }] })).toBe(false)
  })
})
