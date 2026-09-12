import fs from 'fs'

/**
 * 转移/修改路径弹窗移动端适配（源码契约）：
 * - jsdom 不应用媒体查询，布局保护走源码契约（仓内既有模式），视觉由真机兜底；
 * - 根因防回退：SetLocationDialog 曾用根 div 包 el-dialog——调用方透传的
 *   custom-class 经 $attrs 落到外层 div，94vw 收窄从未生效。断言两组件的
 *   custom-class 都打在 el-dialog 根上、模板不被 div 重新包裹；
 * - 组件自治适配（TorrentAddDialog 2026-09-12 模式）：非 scoped ≤768 块收
 *   弹窗骨架（94vw !important 压内联 width / body 64vh 内滚），scoped 块收
 *   内部布局（表单标签上堆 / 底部按钮 44px 等宽）。
 */

const readSource = (relative: string): string =>
  fs.readFileSync(relative, 'utf-8')

const transferSource = (): string =>
  readSource('src/views/torrents/components/TransferDialog.vue')

const setLocationSource = (): string =>
  readSource('src/views/torrents/components/SetLocationDialog.vue')

const mobileTorrentsSource = (): string =>
  readSource('src/views/mobile/torrents.vue')

/** 提取非 scoped 样式块（`<style lang="scss">` 精确匹配，scoped 块含 scoped 关键字）。 */
const unscopedStyleBlock = (source: string): string => {
  const match = source.match(/<style lang="scss">([\s\S]*?)<\/style>/)
  return match ? match[1] : ''
}

/** 提取 scoped 样式块。 */
const scopedStyleBlock = (source: string): string => {
  const match = source.match(/<style scoped lang="scss">([\s\S]*?)<\/style>/)
  return match ? match[1] : ''
}

describe('TransferDialog/SetLocationDialog 移动端适配（源码契约）', () => {
  it('custom-class 落在 el-dialog 开标签上（根 div 包裹防回退）', () => {
    const transfer = transferSource()
    expect(transfer).toMatch(/<el-dialog[^>]*custom-class="transfer-dialog"/s)
    // 嵌套删除确认一并收窄（append-to-body，须自有钩子类）
    expect(transfer).toMatch(/<el-dialog[^>]*custom-class="transfer-delete-confirm"/s)

    const setLocation = setLocationSource()
    expect(setLocation).toMatch(/<el-dialog[^>]*custom-class="set-location-dialog"/s)
    // $attrs 陷阱防回退：模板根不得再用 div 包裹 el-dialog
    expect(setLocation).not.toMatch(/<div>\s*<el-dialog/)
  })

  it('非 scoped ≤768 块：94vw !important 压内联宽度 + 弹窗体 64vh 内滚', () => {
    const transfer = unscopedStyleBlock(transferSource())
    expect(transfer).toContain('@media (max-width: 768px)')
    expect(transfer).toContain('.transfer-dialog')
    expect(transfer).toContain('width: 94vw !important')
    expect(transfer).toContain('max-height: 64vh')
    // 嵌套删除确认弹窗收窄（400px 桌面宽度让位 88vw）
    expect(transfer).toContain('.transfer-delete-confirm')
    expect(transfer).toContain('width: 88vw !important')

    const setLocation = unscopedStyleBlock(setLocationSource())
    expect(setLocation).toContain('@media (max-width: 768px)')
    expect(setLocation).toContain('.set-location-dialog')
    expect(setLocation).toContain('width: 94vw !important')
    expect(setLocation).toContain('max-height: 64vh')
  })

  it('scoped ≤768 块：表单标签上堆 + 底部按钮 44px 等宽触控', () => {
    for (const source of [transferSource(), setLocationSource()]) {
      const scoped = scopedStyleBlock(source)
      expect(scoped).toContain('@media (max-width: 768px)')
      // label-width 110/120px 左右布局 → 标签上堆、内容全宽
      expect(scoped).toContain('width: auto !important')
      expect(scoped).toContain('margin-left: 0 !important')
      expect(scoped).toContain('min-height: 44px')
    }
  })
})

describe('移动种子页透传清理（源码契约）', () => {
  it('转移/修改路径弹窗不再依赖 m-reuse-dialog 透传（组件自治适配）', () => {
    const source = mobileTorrentsSource()
    expect(source).not.toMatch(/<transfer-dialog[^>]*custom-class=/s)
    expect(source).not.toMatch(/<set-location-dialog[^>]*custom-class=/s)
  })

  it('m-reuse-dialog 仍服务 Tracker操作/全局替换两弹窗（组件自治后使用处恰 2）', () => {
    const source = mobileTorrentsSource()
    expect(source).toMatch(/<tracker-operation-dialog[^>]*custom-class="m-reuse-dialog"/s)
    expect(source).toMatch(/<global-replace-tracker-dialog[^>]*custom-class="m-reuse-dialog"/s)
    // 按属性使用处计数（注释提及不计），防其它弹窗悄悄回流依赖页级透传
    expect(source.match(/custom-class="m-reuse-dialog"/g)).toHaveLength(2)
  })
})
