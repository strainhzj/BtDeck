import { readFileSync } from 'fs'
import { resolve } from 'path'

const dialogSource = readFileSync(
  resolve(__dirname, '../../src/views/torrents/components/TrackerOperationDialog.vue'),
  'utf8'
)

describe('TrackerOperationDialog announce 状态判断契约', () => {
  it('使用共享 isTrackerAnnounceSuccess 判断中文状态文本', () => {
    expect(dialogSource).toContain("import { isTrackerAnnounceSuccess } from '../utils/torrentBatch'")
    expect(dialogSource).toContain('trackerAnnounceSuccess(scope.row.last_announce_succeeded)')
    expect(dialogSource).toContain('return isTrackerAnnounceSuccess(status)')
  })

  it('防回归：不再与 True 字面量比较', () => {
    // 旧缺陷：last_announce_succeeded 是后端映射的中文状态文本（工作中/工作失败），
    // 与 'True' 字面量比较恒为 false，所有 tracker 都显示"异常"
    expect(dialogSource).not.toContain("=== 'True'")
  })
})
