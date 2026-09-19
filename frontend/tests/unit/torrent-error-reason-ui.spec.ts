import { readFileSync } from 'fs'
import { resolve } from 'path'

const listSource = readFileSync(
  resolve(__dirname, '../../src/views/torrents/index.vue'),
  'utf8'
)
const traditionalSource = readFileSync(
  resolve(__dirname, '../../src/views/torrents/TraditionalView.vue'),
  'utf8'
)
// 5c297b5 统一 Tracker 详情弹层后，错误原因标题与描述渲染收敛到 TrackerDetailCard
const trackerCardSource = readFileSync(
  resolve(__dirname, '../../src/views/torrents/components/TrackerDetailCard.vue'),
  'utf8'
)
const apiSource = readFileSync(
  resolve(__dirname, '../../src/api/torrents.ts'),
  'utf8'
)
// 展示对齐判定：错误原因回退链抽到共享 utils（两视图委托调用）
const batchSource = readFileSync(
  resolve(__dirname, '../../src/views/torrents/utils/torrentBatch.ts'),
  'utf8'
)
// 双语化（P3-2）：回退链文案与错误标题已迁入语言包，锚定键引用 + zh-CN 值（防丢文案）
const trackerLocaleZhSource = readFileSync(
  resolve(__dirname, '../../src/i18n/locales/zh-CN/tracker.ts'),
  'utf8'
)
const tooltipDismissSource = readFileSync(
  resolve(__dirname, '../../src/views/torrents/mixins/errorTooltipDismiss.ts'),
  'utf8'
)

describe('种子错误原因展示契约', () => {
  it('API 类型同时兼容 camelCase 与 snake_case', () => {
    expect(apiSource).toContain('errorReason?: string | null')
    expect(apiSource).toContain('error_reason?: string | null')
  })

  it('API 类型暴露 tracker 判定标记（camel/snake 兼容）', () => {
    expect(apiSource).toContain('hasTrackerError?: boolean | null')
    expect(apiSource).toContain('has_tracker_error?: boolean | null')
  })

  it.each([
    ['列表视图', listSource],
    ['传统视图', traditionalSource]
  ])('%s 在名称悬浮展示错误原因并透传给 Tracker 详情卡', (_label, source) => {
    expect(source).toContain(':disabled="!getTorrentErrorReason(torrent)"')
    expect(source).toContain(':content="getTorrentErrorReason(torrent)"')
    expect(source).toContain('ref="torrentErrorTooltips"')
    expect(source).toContain(':enterable="false"')
    expect(source).toContain(':error-reason="getTorrentErrorReason(currentRow)"')
    // 回退链收敛到共享 helper，视图保留薄包装委托（防回归：不再各自复制实现）
    expect(source).toContain('return sharedErrorReason(torrent)')
  })

  it('共享 helper 提供错误原因回退链与 Tracker 异常标签判定', () => {
    // errorReason 优先，tracker 异常时回退到宣告失败消息，兜底提示
    expect(batchSource).toContain('export function getTorrentErrorReason')
    expect(batchSource).toContain('export function hasTrackerError')
    expect(batchSource).toContain('export function showTrackerErrorTag')
    expect(batchSource).toContain('torrent.status !== \'error\'')
    // 双语化（P3-2）：兑底文案按 tracker.errorReason.* 键本地化，中文值与历史内联一致
    expect(batchSource).toContain("tracker.errorReason.withMessage")
    expect(batchSource).toContain("tracker.errorReason.fallback")
    expect(trackerLocaleZhSource).toContain("withMessage: 'Tracker 宣告失败：{message}'")
    expect(trackerLocaleZhSource).toContain("fallback: 'Tracker 宣告失败，详见 Tracker 标签页'")
  })

  it.each([
    ['列表视图', listSource],
    ['传统视图', traditionalSource]
  ])('%s 查询期间使用全屏蒙版并锁定页面滚动', (_label, source) => {
    expect(source).toContain('v-loading.fullscreen.lock="listLoading"')
    expect(source).toContain("import TorrentErrorTooltipDismissMixin from './mixins/errorTooltipDismiss'")
    expect(source).toContain('TorrentErrorTooltipDismissMixin')
  })

  it('错误提示收起 mixin 同时监听滚轮与捕获阶段滚动，并在销毁时解绑', () => {
    expect(tooltipDismissSource).toContain("window.addEventListener('scroll', this.tooltipDismissListener, true)")
    expect(tooltipDismissSource).toContain("window.addEventListener('wheel', this.tooltipDismissListener")
    expect(tooltipDismissSource).toContain("window.removeEventListener('scroll', this.tooltipDismissListener, true)")
    expect(tooltipDismissSource).toContain("window.removeEventListener('wheel', this.tooltipDismissListener, true)")
    expect(tooltipDismissSource).toContain('tooltip.hide()')
  })

  it.each([
    ['列表视图', listSource],
    ['传统视图', traditionalSource]
  ])('%s 状态列叠加 Tracker异常 标签', (_label, source) => {
    expect(source).toContain('v-if="showTrackerErrorTag(torrent)"')
    expect(source).toContain('class="tracker-error-tag"')
  })

  it('Tracker 详情卡以统一标题展示错误原因', () => {
    expect(trackerCardSource).toContain('@Prop({ type: String, default: \'\' }) errorReason!: string')
    // 双语化（P3-2）：标题走 tracker.detail.errorTitle 键，中文值与历史内联一致
    expect(trackerCardSource).toContain(":title=\"$t('tracker.detail.errorTitle')\"")
    expect(trackerCardSource).toContain(':description="errorReason"')
    expect(trackerLocaleZhSource).toContain("errorTitle: '种子错误原因'")
  })
})
