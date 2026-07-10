import fs from 'fs'
import os from 'os'
import path from 'path'

const { findViolations } = require('../../scripts/lint-vuex-action.js') as {
  findViolations: (storeDir: string) => Array<{ line: number }>
}

describe('lint-vuex-action', () => {
  let storeDir: string

  beforeEach(() => {
    storeDir = fs.mkdtempSync(path.join(os.tmpdir(), 'btdeck-vuex-lint-'))
  })

  afterEach(() => {
    fs.rmSync(storeDir, { recursive: true, force: true })
  })

  it('rejects an @Action decorator without rawError: true', () => {
    fs.writeFileSync(path.join(storeDir, 'broken.ts'), '@Action()\nmethod() {}\n')

    expect(findViolations(storeDir)).toHaveLength(1)
  })

  it('accepts an @Action decorator with rawError: true', () => {
    fs.writeFileSync(
      path.join(storeDir, 'valid.ts'),
      '@Action({ rawError: true })\nmethod() {}\n'
    )

    expect(findViolations(storeDir)).toEqual([])
  })
})
