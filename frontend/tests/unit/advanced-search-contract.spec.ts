/**
 * advanced-search contract 生成器行尾规范化回归（CRLF checkout 误判 stale 修复）：
 * - core.autocrlf=true 检出下脚本与产物均为 CRLF，而模板内 JSON.stringify 段恒为
 *   LF——原始字节比较必然误判 stale；修复后比较与写出统一 LF 规范化。
 * - 门禁强度不降：LF/CRLF 两种检出形态下，语义内容漂移（变异）必须仍判 stale。
 */

import { spawnSync } from 'child_process'
import fs from 'fs'
import os from 'os'
import path from 'path'

const { buildGeneratedContent, toLf } = require('../../scripts/generate-advanced-search-contract.js') as {
  buildGeneratedContent: (contract: unknown) => string
  toLf: (text: string) => string
}

const scriptPath = path.resolve(__dirname, '../../scripts/generate-advanced-search-contract.js')
const contractPath = path.resolve(
  __dirname,
  '../../../backend/app/contracts/advanced_search_contract.json'
)

function runCli(args: string[]): { status: number | null, stdout: string, stderr: string } {
  const result = spawnSync(process.execPath, [scriptPath, ...args], { encoding: 'utf8' })
  return { status: result.status, stdout: result.stdout, stderr: result.stderr }
}

describe('generate-advanced-search-contract 行尾规范化', () => {
  let workDir: string
  let generated: string

  beforeEach(() => {
    workDir = fs.mkdtempSync(path.join(os.tmpdir(), 'btdeck-contract-eol-'))
    generated = buildGeneratedContent(JSON.parse(fs.readFileSync(contractPath, 'utf8')))
  })

  afterEach(() => {
    fs.rmSync(workDir, { recursive: true, force: true })
  })

  describe('toLf', () => {
    it('把 CRLF 规范化为 LF', () => {
      expect(toLf('a\r\nb\r\nc')).toBe('a\nb\nc')
    })

    it('LF 内容保持不变', () => {
      expect(toLf('a\nb\nc')).toBe('a\nb\nc')
    })
  })

  describe('buildGeneratedContent', () => {
    it('产出恒为纯 LF（不含任何 CR 字节）', () => {
      expect(generated.includes('\r')).toBe(false)
    })

    it('契约内容漂移必须改变产出（变异敏感性）', () => {
      const contract = JSON.parse(fs.readFileSync(contractPath, 'utf8'))
      contract.version = Number(contract.version) + 1
      expect(buildGeneratedContent(contract)).not.toBe(generated)
    })

    it('畸形契约必须抛错', () => {
      expect(() => buildGeneratedContent({})).toThrow('operatorGroups')
    })
  })

  describe('CLI --check 两种检出形态', () => {
    it('LF 产物判定 current（exit 0）', () => {
      const out = path.join(workDir, 'lf.ts')
      fs.writeFileSync(out, generated, 'utf8')
      const result = runCli(['--check', '--contract', contractPath, '--out', out])
      expect(result.status).toBe(0)
    })

    it('CRLF 产物判定 current（exit 0，核心回归）', () => {
      const out = path.join(workDir, 'crlf.ts')
      fs.writeFileSync(out, generated.replace(/\n/g, '\r\n'), 'utf8')
      const result = runCli(['--check', '--contract', contractPath, '--out', out])
      expect(result.status).toBe(0)
    })

    it('LF 形态内容变异必须判 stale（exit 1）', () => {
      const out = path.join(workDir, 'tamper-lf.ts')
      fs.writeFileSync(out, generated.replace('ADVANCED_SEARCH_CONTRACT_VERSION', 'DRIFTED_VERSION'), 'utf8')
      const result = runCli(['--check', '--contract', contractPath, '--out', out])
      expect(result.status).toBe(1)
      expect(result.stderr).toContain('stale')
    })

    it('CRLF 形态内容变异必须判 stale（exit 1）', () => {
      const out = path.join(workDir, 'tamper-crlf.ts')
      const tampered = generated
        .replace('ADVANCED_SEARCH_CONTRACT_VERSION', 'DRIFTED_VERSION')
        .replace(/\n/g, '\r\n')
      fs.writeFileSync(out, tampered, 'utf8')
      const result = runCli(['--check', '--contract', contractPath, '--out', out])
      expect(result.status).toBe(1)
      expect(result.stderr).toContain('stale')
    })

    it('产物缺失必须失败（exit 1）', () => {
      const result = runCli(['--check', '--contract', contractPath, '--out', path.join(workDir, 'missing.ts')])
      expect(result.status).toBe(1)
      expect(result.stderr).toContain('missing')
    })

    it('仓库默认路径 --check 通过（真实工作区接线）', () => {
      const result = runCli(['--check'])
      expect(result.status).toBe(0)
    })
  })

  describe('CLI 生成模式', () => {
    it('写出纯 LF 产物且幂等（生成后 --check 通过）', () => {
      const out = path.join(workDir, 'generated.ts')
      const writeResult = runCli(['--contract', contractPath, '--out', out])
      expect(writeResult.status).toBe(0)

      const written = fs.readFileSync(out, 'utf8')
      expect(written).toBe(generated)
      expect(written.includes('\r')).toBe(false)

      const checkResult = runCli(['--check', '--contract', contractPath, '--out', out])
      expect(checkResult.status).toBe(0)
    })

    it('对 CRLF 检出态的既有产物重写为 LF 后内容语义不变', () => {
      const out = path.join(workDir, 'rewrite.ts')
      fs.writeFileSync(out, generated.replace(/\n/g, '\r\n'), 'utf8')

      const rewriteResult = runCli(['--contract', contractPath, '--out', out])
      expect(rewriteResult.status).toBe(0)
      expect(fs.readFileSync(out, 'utf8')).toBe(generated)
    })
  })

  describe('源码契约（防退回原始字节比较）', () => {
    it('--check 分支必须经 toLf 规范化后比较', () => {
      const source = fs.readFileSync(scriptPath, 'utf8')
      expect(source).toContain('toLf(fs.readFileSync(outputPath')
      expect(source).toContain("argv.includes('--check')")
    })
  })
})
