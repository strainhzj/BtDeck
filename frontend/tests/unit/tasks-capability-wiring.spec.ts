/**
 * 桌面任务页主机能力接线源码契约（dual-mode-client Phase 4 批次 C）。
 *
 * 桌面 tasks/index.vue 体量大不做全挂载，按项目先例（api-contracts.spec.ts
 * 源码锁定风格）断言降级接线四处均在位：
 * 1. 选项禁用绑定（el-option :disabled="isTaskTypeDisabled(...)"）；
 * 2. 禁用说明文案（当前主机形态不支持）；
 * 3. 提交兜底拦截（服务端同款判定双保险）；
 * 4. created 预热矩阵缓存 import + 调用。
 */
import { readFileSync } from 'fs'
import { resolve } from 'path'

const source = readFileSync(resolve(__dirname, '../../src/views/tasks/index.vue'), 'utf8')

describe('任务类型降级接线（源码契约）', () => {
  it('el-option 绑定 isTaskTypeDisabled', () => {
    expect(source).toContain(':disabled="isTaskTypeDisabled(option.value)"')
  })

  it('禁用项显示形态说明', () => {
    expect(source).toContain('当前主机形态不支持')
  })

  it('提交前兜底拦截（与服务端判定同款）', () => {
    expect(source).toContain('this.isTaskTypeDisabled(this.taskForm.task_type)')
  })

  it('created 预热能力缓存', () => {
    expect(source).toMatch(/created\(\) \{[\s\S]*?loadPlatformCapabilities\(\)/)
  })

  it('判定逻辑：仅 0-3 且 customScriptsUnsupported 时禁用', () => {
    expect(source).toContain('value <= 3 && customScriptsUnsupported()')
  })

  it('移动任务页提示条仅 android-server degraded 显示', () => {
    const mobile = readFileSync(resolve(__dirname, '../../src/views/mobile/tasks.vue'), 'utf8')
    expect(mobile).toContain('v-if="scheduledTasksDegraded"')
    expect(mobile).toContain("cachedCapabilityLevel('scheduled_tasks') === 'degraded'")
  })
})
