#!/usr/bin/env node
/**
 * 检查 vuex-module-decorators @Action 装饰器是否包含 rawError: true
 *
 * 原因：@Action 默认会包装错误，产生误导性的 ERR_ACTION_ACCESS_UNDEFINED
 * 用法：npm run lint:vuex-action
 */

const fs = require('fs')
const path = require('path')

const STORE_DIR = path.join(__dirname, '..', 'src', 'store')

const results = []

function scanDir(dir) {
  const entries = fs.readdirSync(dir, { withFileTypes: true })
  for (const entry of entries) {
    const fullPath = path.join(dir, entry.name)
    if (entry.isDirectory()) {
      scanDir(fullPath)
    } else if (entry.isFile() && /\.(ts|vue)$/.test(entry.name)) {
      checkFile(fullPath)
    }
  }
}

function checkFile(filePath) {
  const content = fs.readFileSync(filePath, 'utf-8')
  const lines = content.split('\n')
  const relativePath = path.relative(path.join(__dirname, '..'), filePath).replace(/\\/g, '/')

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i]

    // 匹配裸 @Action（后面不跟括号）
    if (/^\s*@Action\s*$/.test(line)) {
      results.push({ file: relativePath, line: i + 1, code: line.trim() })
      continue
    }

    // 匹配 @Action()（空参数）
    if (/^\s*@Action\s*\(\s*\)\s*$/.test(line)) {
      results.push({ file: relativePath, line: i + 1, code: line.trim() })
      continue
    }

    // 匹配 @Action({...}) 但不含 rawError: true
    const actionMatch = line.match(/^\s*@Action\s*\(\s*\{/)
    if (actionMatch) {
      // 找到完整的 @Action({...}) — 可能跨多行
      let block = line
      let j = i
      while (!block.includes('}') && j < lines.length - 1) {
        j++
        block += '\n' + lines[j]
      }
      if (!/rawError\s*:\s*true/.test(block)) {
        results.push({ file: relativePath, line: i + 1, code: line.trim() })
      }
    }
  }
}

scanDir(STORE_DIR)

if (results.length > 0) {
  console.error('❌ 错误：以下 @Action 缺少 { rawError: true } 配置\n')
  for (const r of results) {
    console.error(`  ${r.file}:${r.line}  ${r.code}`)
  }
  console.error('')
  console.error('原因：@Action 默认会包装错误，导致原始错误信息丢失，')
  console.error('产生误导性的 ERR_ACTION_ACCESS_UNDEFINED 错误。')
  console.error('')
  console.error('修复：将 @Action 改为 @Action({ rawError: true })')
  process.exit(1)
}

console.log('✅ 所有 @Action 装饰器均已正确配置 rawError: true')
process.exit(0)
