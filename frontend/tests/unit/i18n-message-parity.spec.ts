/**
 * 中英双语消息树一致性门禁（desktop-bilingual-20260918.p1，验收矩阵 L05）。
 *
 * 钉死三条硬约束（PLANS/desktop-bilingual.md §3.1 / §7）：
 * 1. zh-CN 与 en 的键集合完全一致（en 缺键允许运行时回退中文，但门禁必须失败）；
 * 2. 每个键的插值参数集合一致（如 {n}），参数名漂移在运行时静默出错，只能静态拦截；
 * 3. 复数文案「单|复」两侧支数一致，避免切换语言后复数行为漂移。
 *
 * 另：zh-CN 源语言文案不允许空串（源语言完整性）。
 */

import zhCN from '@/i18n/locales/zh-CN'
import en from '@/i18n/locales/en'
import { MessageTree } from '@/i18n/types'

/**
 * el 子树（Element UI 官方语言包）不在本门禁范围：
 * 两个官方包之间存在键漂移（实测 en 独有 el.datepicker.week），属 vendor 数据，
 * 不由本仓修复；本门禁只钉本项目自有的 navigation / time / 及后续分组。
 */
function userGroups(tree: MessageTree): MessageTree {
  const groups: MessageTree = {}
  Object.keys(tree).forEach((key) => {
    if (key !== 'el') {
      const value = tree[key]
      if (typeof value !== 'string') {
        groups[key] = value
      }
    }
  })
  return groups
}

const INTERPOLATION_PATTERN = /\{(\w+)\}/g

function collectKeys(tree: MessageTree, prefix = ''): string[] {
  return Object.keys(tree).reduce<string[]>((acc, key) => {
    const path = prefix ? `${prefix}.${key}` : key
    const value = tree[key]
    if (typeof value === 'string') {
      acc.push(path)
    } else {
      acc.push(...collectKeys(value, path))
    }
    return acc
  }, [])
}

function collectParams(value: string): string[] {
  const params: string[] = []
  INTERPOLATION_PATTERN.lastIndex = 0
  let match: RegExpExecArray | null = INTERPOLATION_PATTERN.exec(value)
  while (match !== null) {
    params.push(match[1])
    match = INTERPOLATION_PATTERN.exec(value)
  }
  return params
}

function paramSet(tree: MessageTree): Map<string, string[]> {
  const result = new Map<string, string[]>()
  collectKeys(tree).forEach((key) => {
    const segments = key.split('.')
    let node: string | MessageTree = tree
    for (const segment of segments) {
      if (typeof node === 'string') {
        return
      }
      const next: string | MessageTree | undefined = node[segment]
      if (next === undefined) {
        return
      }
      node = next
    }
    if (typeof node === 'string') {
      result.set(key, collectParams(node))
    }
  })
  return result
}

function formatSet(values: string[]): string {
  return [...new Set(values)].sort().join(',')
}

describe('中英双语消息树一致性（L05 自动化门禁）', () => {
  const zhUser = userGroups(zhCN)
  const enUser = userGroups(en)

  it('zh-CN 与 en 键集合完全一致', () => {
    const zhKeys = collectKeys(zhUser).sort()
    const enKeys = collectKeys(enUser).sort()
    const zhOnly = zhKeys.filter((k) => !enKeys.includes(k))
    const enOnly = enKeys.filter((k) => !zhKeys.includes(k))
    expect({
      equal: zhKeys.length === enKeys.length && zhOnly.length === 0 && enOnly.length === 0,
      zhOnly: zhOnly.join(','),
      enOnly: enOnly.join(',')
    }).toEqual({ equal: true, zhOnly: '', enOnly: '' })
  })

  it('每个键的插值参数集合一致', () => {
    const zhParams = paramSet(zhUser)
    const enParams = paramSet(enUser)
    const mismatches: string[] = []
    zhParams.forEach((_, key) => {
      const zhSet = formatSet(zhParams.get(key) || [])
      const enSet = formatSet(enParams.get(key) || [])
      if (zhSet !== enSet) {
        mismatches.push(`${key}: zh=[${zhSet}] en=[${enSet}]`)
      }
    })
    expect({ mismatchCount: mismatches.length, detail: mismatches.join('；') }).toEqual({
      mismatchCount: 0,
      detail: ''
    })
  })

  it('复数文案两侧支数一致', () => {
    const mismatches: string[] = []
    collectKeys(zhUser).forEach((key) => {
      const segments = key.split('.')
      let zhNode: string | MessageTree = zhUser
      let enNode: string | MessageTree = enUser
      for (const segment of segments) {
        if (typeof zhNode === 'string' || typeof enNode === 'string') {
          return
        }
        const zhNext: string | MessageTree | undefined = zhNode[segment]
        const enNext: string | MessageTree | undefined = enNode[segment]
        if (zhNext === undefined || enNext === undefined) {
          return
        }
        zhNode = zhNext
        enNode = enNext
      }
      if (typeof zhNode === 'string' && typeof enNode === 'string') {
        if (zhNode.split('|').length !== enNode.split('|').length) {
          mismatches.push(key)
        }
      }
    })
    expect({ mismatchCount: mismatches.length, keys: mismatches.join(',') }).toEqual({
      mismatchCount: 0,
      keys: ''
    })
  })

  it('zh-CN 源语言文案无空串', () => {
    const empties = collectKeys(zhUser).filter((key) => {
      const segments = key.split('.')
      let node: string | MessageTree = zhUser
      for (const segment of segments) {
        if (typeof node === 'string') {
          return false
        }
        const next: string | MessageTree | undefined = node[segment]
        if (next === undefined) {
          return false
        }
        node = next
      }
      return typeof node === 'string' && node.trim() === ''
    })
    expect({ emptyCount: empties.length, keys: empties.join(',') }).toEqual({
      emptyCount: 0,
      keys: ''
    })
  })
})
