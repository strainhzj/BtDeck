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

describe('种子错误原因展示契约', () => {
  it('API 类型同时兼容 camelCase 与 snake_case', () => {
    expect(apiSource).toContain('errorReason?: string | null')
    expect(apiSource).toContain('error_reason?: string | null')
  })

  it.each([
    ['列表视图', listSource],
    ['传统视图', traditionalSource]
  ])('%s 在名称悬浮展示错误原因并透传给 Tracker 详情卡', (_label, source) => {
    expect(source).toContain(':disabled="!getTorrentErrorReason(torrent)"')
    expect(source).toContain(':content="getTorrentErrorReason(torrent)"')
    expect(source).toContain(':error-reason="getTorrentErrorReason(currentRow)"')
    expect(source).toContain("torrent?.errorReason || torrent?.error_reason || ''")
  })

  it('Tracker 详情卡以统一标题展示错误原因', () => {
    expect(trackerCardSource).toContain('@Prop({ type: String, default: \'\' }) errorReason!: string')
    expect(trackerCardSource).toContain('title="种子错误原因"')
    expect(trackerCardSource).toContain(':description="errorReason"')
  })
})
