/**
 * 字段类型与生成契约一致性守卫
 *
 * 后端 JSON 是字段与操作符的唯一协议源，前端生成
 * ADVANCED_SEARCH_FIELDS。字段 UI 展示元数据（label/type/matchMode）集中维护在
 * advancedSearchFields.ts（桌面 AdvancedSearchBuilder 与移动端
 * MobileAdvancedSearch/ConditionEditSheet 共享同源），模板搜索必须读取生成
 * 契约，不能再维护 ADVANCED_FIELD_TYPES 副本。
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
import { ADVANCED_SEARCH_FIELDS } from '@/contracts/advancedSearch.generated'

const fieldsSource = readFileSync(
  resolve(__dirname, '../../src/components/torrents/advancedSearchFields.ts'),
  'utf8'
)
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

/** 从源码字符串里提取某字段在 advancedSearchFields 字段块中的 type 值 */
function extractFieldType(source: string, field: string, typeQuote: "'" | '"' = "'"): string | null {
  // 匹配 `key: 'field'` 后面（允许跨行，非贪婪）跟 `type: 'yyy'`
  const re = new RegExp(`key\\s*:\\s*${typeQuote}${field}${typeQuote}[\\s\\S]*?type\\s*:\\s*${typeQuote}(\\w+)${typeQuote}`)
  const m = source.match(re)
  return m ? m[1] : null
}

describe('字段类型三表一致性（多选字段与超级做种）', () => {
  // 三表对三个关键字段的期望类型
  const cases: Array<{ field: string, expected: string }> = [
    { field: 'status', expected: 'multiSelect' },
    { field: 'category', expected: 'multiSelect' },
    { field: 'downloader_name', expected: 'multiSelect' },
    { field: 'tags', expected: 'multiSelect' },
    { field: 'super_seeding', expected: 'select' }
  ]

  describe.each(cases)('$field', ({ field, expected }) => {
    it(`共享字段配置（advancedSearchFields）声明为 ${expected}`, () => {
      const type = extractFieldType(fieldsSource, field)
      expect(type).toBe(expected)
    })

    it(`ConditionValueInput.fieldTypeMap 声明为 ${expected}`, () => {
      // fieldTypeMap 是 `key: 'type'` 单行形态（如 `category: 'multiSelect',`）
      const re = new RegExp(`${field}\\s*:\\s*'(\\w+)'`)
      const m = conditionInputSource.match(re)
      expect(m ? m[1] : null).toBe(expected)
    })

    it(`生成契约声明为 ${expected}`, () => {
      expect(ADVANCED_SEARCH_FIELDS[field].kind).toBe(expected)
    })
  })

  it('模板搜索直接读取生成契约且不维护字段类型副本', () => {
    expect(torrentBatchSource).toContain('ADVANCED_SEARCH_FIELDS')
    expect(torrentBatchSource).not.toContain('ADVANCED_FIELD_TYPES')
  })

  it('字段配置唯一来源在共享层：桌面构建器消费 advancedSearchFields（禁本地副本回流）', () => {
    expect(builderSource).toContain("from './advancedSearchFields'")
    // 字段块定义已全部下沉：构建器内不得再出现字段 key 直定义
    expect(extractFieldType(builderSource, 'status')).toBeNull()
    expect(extractFieldType(builderSource, 'category')).toBeNull()
  })

  it('共享字段配置对 category/downloader_name 标注 matchMode=exact，tags 标注 substring', () => {
    // 这决定 UI 操作符过滤：单值列只暴露 in/not_in，逗号串列只暴露 contains_*
    // 用源码字符串断言 matchMode 存在，防止被误删
    expect(fieldsSource).toContain("matchMode: 'exact'")
    expect(fieldsSource).toContain("matchMode: 'substring'")
    // category 和 downloader_name 应有 exact 标注（在各自字段块内）
    const catBlock = fieldsSource.match(/key: 'category'[\s\S]*?options: \[\]/)
    const dlBlock = fieldsSource.match(/key: 'downloader_name'[\s\S]*?options: \[\]/)
    expect(catBlock?.[0]).toContain("matchMode: 'exact'")
    expect(dlBlock?.[0]).toContain("matchMode: 'exact'")
  })
})
