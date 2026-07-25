/**
 * 字段类型三表一致性守卫（v1.0.5.14）
 *
 * 背景：前端存在三份独立的"字段类型映射表"，分别服务不同链路：
 *   1. AdvancedSearchBuilder.statusFields/advancedFields —— UI 字段定义 + 操作符路由
 *   2. ConditionValueInput.fieldTypeMap —— 输入控件渲染分支（select vs multiSelect）
 *   3. torrentBatch.ADVANCED_FIELD_TYPES —— 模板搜索的请求构造
 *
 * 历史上三表曾出现分歧（如 category 在 #1#2 是 select、#3 缺 downloader_name），
 * 导致即时搜索与模板搜索语义不一致。本 spec 锁定三表对关键字段的一致性，
 * 是最便宜的高价值防回归（参考 management-pages-ui.spec.ts 源码字符串契约范式）。
 *
 * 注意：用源码字符串解析而非模块导入——避免触发 Vue 组件 mount 的副作用，
 * 且能在三表分散于不同类型文件（.vue/.ts）时统一断言。
 */
import { readFileSync } from 'fs'
import { resolve } from 'path'

const builderSource = readFileSync(
  resolve(__dirname, '../../src/components/torrents/AdvancedSearchBuilder.vue'),
  'utf8'
)
const conditionInputSource = readFileSync(
  resolve(__dirname, '../../src/components/torrents/ConditionValueInput.vue'),
  'utf8'
)
const torrentBatchSource = readFileSync(
  resolve(__dirname, '../../src/views/torrents/utils/torrentBatch.ts'),
  'utf8'
)

/** 从源码字符串里提取某字段在 AdvancedSearchBuilder 字段块中的 type 值 */
function extractFieldType(source: string, field: string, typeQuote: "'" | '"' = "'"): string | null {
  // 匹配 `key: 'field'` 后面（允许跨行，非贪婪）跟 `type: 'yyy'`
  const re = new RegExp(`key\\s*:\\s*${typeQuote}${field}${typeQuote}[\\s\\S]*?type\\s*:\\s*${typeQuote}(\\w+)${typeQuote}`)
  const m = source.match(re)
  return m ? m[1] : null
}

describe('字段类型三表一致性（category / downloader_name / tags）', () => {
  // 三表对三个关键字段的期望类型
  const cases: Array<{ field: string, expected: string }> = [
    { field: 'category', expected: 'multiSelect' },
    { field: 'downloader_name', expected: 'multiSelect' },
    { field: 'tags', expected: 'multiSelect' }
  ]

  describe.each(cases)('$field', ({ field, expected }) => {
    it(`AdvancedSearchBuilder 声明为 ${expected}`, () => {
      const type = extractFieldType(builderSource, field)
      expect(type).toBe(expected)
    })

    it(`ConditionValueInput.fieldTypeMap 声明为 ${expected}`, () => {
      // fieldTypeMap 是 `key: 'type'` 单行形态（如 `category: 'multiSelect',`）
      const re = new RegExp(`${field}\\s*:\\s*'(\\w+)'`)
      const m = conditionInputSource.match(re)
      expect(m ? m[1] : null).toBe(expected)
    })

    it(`torrentBatch.ADVANCED_FIELD_TYPES 声明为 ${expected}`, () => {
      const re = new RegExp(`${field}\\s*:\\s*'(\\w+)'`)
      const m = torrentBatchSource.match(re)
      expect(m ? m[1] : null).toBe(expected)
    })
  })

  it('AdvancedSearchBuilder 对 category/downloader_name 标注 matchMode=exact，tags 标注 substring', () => {
    // 这决定 UI 操作符过滤：单值列只暴露 in/not_in，逗号串列只暴露 contains_*
    // 用源码字符串断言 matchMode 存在，防止被误删
    expect(builderSource).toContain("matchMode: 'exact'")
    expect(builderSource).toContain("matchMode: 'substring'")
    // category 和 downloader_name 应有 exact 标注（在各自字段块内）
    const catBlock = builderSource.match(/key: 'category'[\s\S]*?options: \[\]/)
    const dlBlock = builderSource.match(/key: 'downloader_name'[\s\S]*?options: \[\]/)
    expect(catBlock?.[0]).toContain("matchMode: 'exact'")
    expect(dlBlock?.[0]).toContain("matchMode: 'exact'")
  })
})
