/**
 * Jest 单元测试配置。
 *
 * 仅用于纯逻辑模块（如 utils/error-normalize.ts）的归一化行为验证，
 * 不覆盖 Vue 组件 / Vuex store（那些依赖完整运行时，留给手动端到端清单）。
 *
 * 详见审计修复 PLANS/v1.0.5-audit.md P0-1.4。
 */
module.exports = {
  preset: 'ts-jest',
  testEnvironment: 'node',
  roots: ['<rootDir>/tests/unit'],
  testMatch: ['**/*.spec.ts'],
  moduleNameMapper: {
    '^@/(.*)$': '<rootDir>/src/$1'
  },
  transform: {
    '^.+\\.tsx?$': 'ts-jest'
  },
  globals: {
    'ts-jest': {
      tsconfig: {
        // 测试允许 any 断言，避免与业务代码的 strict 设置冲突
        strict: false,
        esModuleInterop: true,
        experimentalDecorators: true
      }
    }
  }
}
