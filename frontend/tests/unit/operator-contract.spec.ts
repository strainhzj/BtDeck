/**
 * 高级搜索操作符前后端契约守卫（v1.0.6.25）
 *
 * 背景：v1.0.5.15 红队审查发现，前端 AdvancedSearchBuilder.operatorGroups 暴露的
 * between/regex/last_days/date_range 四个操作符后端 allowed_operators 不含，
 * Pydantic 直接 422 拒整个请求。v1.0.6.1 后端补齐后，本 spec 冻结契约防止再次漂移。
 *
 * 三层契约：
 *   1. 前端暴露的全部 backendValue 必须在后端 allowed_operators 集合内（防 422）
 *   2. 特殊操作符（between/regex/last_days/date_range）的 value 结构必须与后端
 *      _build_between_filter / _build_regex_filter / _build_date_window_filter 解构逻辑对齐
 *   3. formatParamValue 各类型路径输出必须与后端 value 字段期望类型一致
 *
 * 范式：源码字符串解析（不 mount Vue 组件），与 field-types-consistency.spec.ts 一致。
 * 原因：避免触发组件 mount 副作用；能在 .vue/.ts 分散文件上统一断言。
 *
 * ⚠ 维护规则：后端新增/删除 allowed_operators 时，必须同步更新本文件的
 * BACKEND_ALLOWED_OPERATORS 常量。这是单向契约——只锁"前端暴露必须后端支持"，
 * 不强求"后端支持必须前端暴露"（后端可有未被 UI 使用的操作符）。
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

/**
 * 后端 allowed_operators 集合（来自 backend/app/api/models/advanced_search.py
 * 的 SearchCondition.validate_operator）。
 *
 * 维护点：后端增删操作符时同步更新此常量。
 */
const BACKEND_ALLOWED_OPERATORS = new Set([
  // 标量比较
  'eq', 'ne', 'gt', 'gte', 'lt', 'lte',
  // 文本
  'contains', 'not_contains', 'starts_with', 'ends_with',
  'not_starts_with', 'not_ends_with',
  // 集合
  'in', 'not_in',
  // NULL
  'is_null', 'is_not_null',
  // 多值子串（逗号分隔字符串列）
  'contains_any', 'contains_all', 'not_contains_any', 'not_contains_all',
  // 区间/窗口（v1.0.6.1 补齐）
  'between', 'regex', 'last_days', 'date_range'
])

/**
 * 从 operatorGroups 源码字符串解析出全部 (frontendValue, backendValue, fallback) 三元组。
 *
 * 解析 operatorGroups 字面量定义，匹配形如：
 *   { value: 'contains', label: '包含', backendValue: 'contains' }
 *   { value: 'regex', label: '正则匹配', backendValue: 'regex', fallback: 'contains' }
 */
interface OperatorDef {
  frontendValue: string
  backendValue: string
  fallback?: string
  group: string
}

function parseOperatorGroups(source: string): OperatorDef[] {
  const result: OperatorDef[] = []
  // 逐行解析 operatorGroups 字面量。每行形如：
  //   { value: 'contains', label: '包含', backendValue: 'contains' }
  //   { value: 'regex', label: '正则匹配', backendValue: 'regex', fallback: 'contains' }
  // 用字符串 split + 单行 match（非 /g），避免 /g 正则在 ts-jest 顶层转译时
  // lastIndex 残留导致连吃字符的坑。
  const knownGroups = new Set([
    'text', 'number', 'date', 'select', 'multiSelect', 'boolean'
  ])
  let currentGroup = ''
  for (const rawLine of source.split(/\r?\n/)) {
    const line = rawLine.trim()
    // 检测组开始：形如 "text: [" / "number: ["
    const groupStart = line.match(/^(\w+):\s*\[/)
    if (groupStart) {
      if (knownGroups.has(groupStart[1])) {
        currentGroup = groupStart[1]
      } else {
        currentGroup = ''
      }
      continue
    }
    if (line === ']' || line === '],') {
      currentGroup = ''
      continue
    }
    if (!currentGroup) continue
    // 只处理含 value: 和 backendValue: 的行
    if (!line.includes('value:') || !line.includes('backendValue:')) continue

    const valueMatch = line.match(/value:\s*'([a-z_]+)'/)
    const backendMatch = line.match(/backendValue:\s*'([a-z_]+)'/)
    const fallbackMatch = line.match(/fallback:\s*'([a-z_]+)'/)
    if (!valueMatch || !backendMatch) continue

    result.push({
      frontendValue: valueMatch[1],
      backendValue: backendMatch[1],
      fallback: fallbackMatch ? fallbackMatch[1] : undefined,
      group: currentGroup
    })
  }
  return result
}

const operators = parseOperatorGroups(builderSource)

describe('高级搜索操作符前后端契约守卫', () => {
  describe('契约 1：前端暴露的 backendValue 必须在后端 allowed_operators 集合内', () => {
    test('operatorGroups 应能解析出全部操作符定义', () => {
      // 防御性：确认解析没失败。预期至少 25 个操作符定义（6 组累计）
      expect(operators.length).toBeGreaterThanOrEqual(20)
    })

    test('每个前端操作符的 backendValue 都在后端 allowed_operators 内', () => {
      const unsupported = operators.filter(
        op => !BACKEND_ALLOWED_OPERATORS.has(op.backendValue)
      )
      if (unsupported.length > 0) {
        const detail = unsupported
          .map(op => `${op.group}.${op.frontendValue} → backendValue='${op.backendValue}'`)
          .join('; ')
        throw new Error(
          `以下前端操作符后端不支持（会触发 422 硬失败）：${detail}。\n` +
          '修复方案：在 backend/app/api/models/advanced_search.py 的 allowed_operators ' +
          '集合登记该操作符，并在 service 层实现；或前端移除该操作符入口。'
        )
      }
    })

    test('BACKEND_ALLOWED_OPERATORS 常量与后端源码一致（同步校验）', () => {
      // 读取后端 allowed_operators 源码片段，校验本文件的常量没过期
      // 注意：Jest 运行在前端目录，后端源码可能在相对路径 ../backend 下
      const backendModelPath = resolve(__dirname, '../../../backend/app/api/models/advanced_search.py')
      let backendSource: string
      try {
        backendSource = readFileSync(backendModelPath, 'utf8')
      } catch {
        // 跨仓库布局或后端路径不可达时，跳过此同步校验（不阻断前端独立测试）
        console.warn('跳过后端源码同步校验：', backendModelPath, '不可读')
        return
      }

      // 提取 allowed_operators 集合内的全部字符串字面量。
      // 注意：集合内的中文注释含 { } 字符（如 `# between={min,max}`），
      // 故不能用非贪婪 `\{([\s\S]*?)\}`（会在注释的 } 处提前结束，漏读后续操作符）。
      // 改用：从 `allowed_operators = {` 开始，到下一个 `if v not in allowed_operators` 之前。
      const startIdx = backendSource.indexOf('allowed_operators = {')
      expect(startIdx).toBeGreaterThan(-1)
      const endMarker = backendSource.indexOf('if v not in allowed_operators', startIdx)
      expect(endMarker).toBeGreaterThan(startIdx)
      const allowedBlock = backendSource.slice(startIdx, endMarker)
      // 剔除行注释（# 开头），避免注释里的字符串字面量（如 "days":N、{"start","end"}）被误读
      const codeOnly = allowedBlock
        .split(/\r?\n/)
        .filter(line => !line.trim().startsWith('#'))
        .join('\n')
      const backendOps = new Set<string>()
      const strLitRegex = /"([^"]+)"/g
      let m: RegExpExecArray | null
      while ((m = strLitRegex.exec(codeOnly)) !== null) {
        backendOps.add(m[1])
      }

      // 本文件常量必须与后端源码一致
      const missingInConst = [...backendOps].filter(op => !BACKEND_ALLOWED_OPERATORS.has(op))
      const extraInConst = [...BACKEND_ALLOWED_OPERATORS].filter(op => !backendOps.has(op))
      expect({ missingInConst, extraInConst }).toEqual({ missingInConst: [], extraInConst: [] })
    })
  })

  describe('契约 2：特殊操作符的 value 结构与后端解构逻辑对齐', () => {
    test('between 操作符在前端各字段类型的 value 结构与后端 _build_between_filter 对齐', () => {
      // 后端期望（_build_between_filter）：
      //   size:        { min: "1 GB", max: "10 GB", minUnit, maxUnit }
      //   date 字段:    { start, end } 或 { min, max }
      //   number 字段:  { min, max }
      // 前端 formatParamValue（AdvancedSearchBuilder.vue）实际产出：
      //   size:        { min: "1 GB", max: "10 GB" }（formatParamValue line 1222-1232）
      //   number+between: { min: Number, max: Number }（line 1251-1258）
      //   date+between:   date 字段非对象直接返回，对象则 JSON.stringify → 后端 json.loads

      // 校验 size between 输出含 min/max 字符串（带单位）
      expect(builderSource).toMatch(/condition\.field === 'size' && condition\.operator === 'between'/)
      expect(builderSource).toMatch(/\$\{value\.min\} \$\{value\.minUnit \|\| 'GB'\}/)

      // 校验 number between 输出 {min, max} 对象
      expect(builderSource).toMatch(/condition\.operator === 'between' && condition\.value/)
      expect(builderSource).toMatch(/min: condition\.value\.min !== null \? Number\(condition\.value\.min\) : null/)
    })

    test('regex 操作符的 value 结构 {pattern, caseSensitive} 与后端 _build_regex_filter 对齐', () => {
      // 后端期望（_build_regex_filter）：
      //   value = { pattern: str, caseSensitive: bool } 或裸 str
      // 前端 ConditionValueInput.vue 的 regex 模板产出 { pattern, caseSensitive }
      expect(conditionInputSource).toMatch(/pattern/)
      expect(conditionInputSource).toMatch(/caseSensitive/)
    })

    test('last_days 操作符的 value {"days": N} 与后端 _build_date_window_filter 对齐', () => {
      // 后端期望（_build_date_window_filter）：value 是 '{"days": 7}' JSON 字符串或 dict
      // 前端 ConditionValueInput.vue 的 lastDays 模板产出 { days: number }，
      // formatParamValue 对 date 字段 JSON.stringify → '{"days":7}'
      expect(conditionInputSource).toMatch(/days/)
      // 默认值 7 天
      expect(conditionInputSource).toMatch(/days:\s*7/)
    })

    test('date_range 操作符的 value {"start","end"} 与后端 _build_date_window_filter 对齐', () => {
      // 后端期望：value 是 '{"start": "...", "end": "..."}' JSON 字符串或 dict
      // 前端 dateRange 模板产出 { start, end }
      expect(conditionInputSource).toMatch(/start/)
      expect(conditionInputSource).toMatch(/end/)
    })

    test('四个新操作符在后端 allowed_operators 内（防再次 422）', () => {
      // 这是 v1.0.6.1 的核心修复——四个操作符必须都在后端集合内
      const newOps = ['between', 'regex', 'last_days', 'date_range']
      for (const op of newOps) {
        expect(BACKEND_ALLOWED_OPERATORS.has(op)).toBe(true)
      }
    })
  })

  describe('契约 3：formatParamValue 各类型路径输出与后端期望一致', () => {
    test('size 字段非 between 时输出 "数字 单位" 字符串', () => {
      // 后端 validate_size_string 接受 "1 GB" / "500 MB" 格式
      expect(builderSource).toMatch(/condition\.field === 'size' && condition\.operator !== 'between'/)
      expect(builderSource).toMatch(/\$\{value\.value\} \$\{value\.unit \|\| 'GB'\}/)
    })

    test('date 字段非 between 对象 value 走 JSON.stringify', () => {
      // 后端 _build_date_window_filter 对 str value 做_json.loads；date 字段需 JSON 序列化
      expect(builderSource).toMatch(/case 'date':[\s\S]*?JSON\.stringify\(condition\.value\)/)
    })

    test('number 字段非 between 输出 Number(value)', () => {
      // 后端 NUMERIC_FIELDS 分支显式 float(value)，前端必须发数值而非字符串
      expect(builderSource).toMatch(/case 'number':[\s\S]*?return Number\(condition\.value\)/)
    })

    test('multiSelect 字段输出数组（后端 in/not_in/contains_any 期望 list）', () => {
      // 后端 _normalize_multi_value 接受 list 或逗号串；前端规范发数组
      expect(builderSource).toMatch(/case 'multiSelect':[\s\S]*?Array\.isArray\(condition\.value\)/)
    })

    test('boolean 字段输出 "1"/"0" 字符串（后端 super_seeding 列是 String）', () => {
      // 后端 TorrentInfo.super_seeding 是 String 列（"0"/"1"），前端 boolean 输出字符串对齐
      expect(builderSource).toMatch(/case 'boolean':[\s\S]*?condition\.value \? '1' : '0'/)
    })
  })

  describe('降级策略（fallback）一致性', () => {
    test('带 fallback 的操作符其 fallback 目标也必须在后端 allowed_operators 内', () => {
      // 即便主操作符后端不支持，fallback 后端也必须支持，否则降级后仍会 422
      const withFallback = operators.filter(op => op.fallback)
      // fallback 在前端是 frontendValue，需先转成 backendValue
      // 查 operatorMapping：frontendValue → backendValue
      for (const op of withFallback) {
        // 找到 fallback 对应的 backendValue
        const fallbackOp = operators.find(o => o.frontendValue === op.fallback)
        if (!fallbackOp) {
          throw new Error(
            `操作符 ${op.group}.${op.frontendValue} 的 fallback '${op.fallback}' ` +
            '在 operatorGroups 内找不到对应定义'
          )
        }
        expect(BACKEND_ALLOWED_OPERATORS.has(fallbackOp.backendValue)).toBe(true)
      }
    })

    test('regex 的 fallback 是 contains（语义最近：子串匹配）', () => {
      const regexOp = operators.find(op => op.backendValue === 'regex')
      expect(regexOp).toBeDefined()
      expect(regexOp ? regexOp.fallback : undefined).toBe('contains')
    })

    test('between 的 fallback 是 greater_than（丢失上限检查，最近语义）', () => {
      // between fallback greater_than → backendValue 'gt'
      const betweenOp = operators.find(op => op.backendValue === 'between')
      expect(betweenOp).toBeDefined()
      expect(betweenOp ? betweenOp.fallback : undefined).toBe('greater_than')
      // greater_than 的 backendValue 必须在后端集合内
      const gtOp = operators.find(o => o.frontendValue === 'greater_than')
      expect(gtOp).toBeDefined()
      expect(BACKEND_ALLOWED_OPERATORS.has(gtOp ? gtOp.backendValue : '')).toBe(true)
    })
  })
})
