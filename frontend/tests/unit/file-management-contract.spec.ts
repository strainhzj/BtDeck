import { readFileSync } from 'fs'
import { resolve } from 'path'

const viewSource = readFileSync(
  resolve(__dirname, '../../src/views/torrents/FileManagement.vue'),
  'utf8'
)
const apiSource = readFileSync(
  resolve(__dirname, '../../src/api/torrents.ts'),
  'utf8'
)

describe('种子文件管理页面契约', () => {
  it('备份列表使用接口批量返回的当前昵称，不展示下载器 ID', () => {
    expect(apiSource).toContain('downloader_nickname?: string | null')
    expect(viewSource).toContain('{{ getBackupDownloaderName(row) }}')
    expect(viewSource).toContain('backup.downloader_nickname || this.getDownloaderName')
    expect(viewSource).toContain(':label="downloader.nickname"')
    expect(viewSource).not.toContain('`下载器${downloaderId}`')
  })

  it('下载器列表按真实数组响应读取', () => {
    expect(viewSource).toContain(
      'this.downloaderList = Array.isArray(res.data) ? res.data : []'
    )
    expect(viewSource).not.toContain('res.data.list || []')
  })

  it('搜索栏只使用项目共享 management-filter 样式', () => {
    expect(viewSource).toContain(
      'class="app-container management-page file-management-page"'
    )
    expect(viewSource).not.toContain('file-mgmt-input')
    expect(viewSource).not.toContain('file-mgmt-actions')
    expect(viewSource).not.toContain('file-mgmt-daterange')
  })
})
