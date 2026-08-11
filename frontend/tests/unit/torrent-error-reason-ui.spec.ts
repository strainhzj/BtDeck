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
  ])('%s 在名称悬浮与 Tracker 详情展示错误原因', (_label, source) => {
    expect(source).toContain(':disabled="!getTorrentErrorReason(torrent)"')
    expect(source).toContain(':content="getTorrentErrorReason(torrent)"')
    expect(source).toContain('title="种子错误原因"')
    expect(source).toContain(':description="getTorrentErrorReason(currentRow)"')
    expect(source).toContain("torrent?.errorReason || torrent?.error_reason || ''")
  })
})
