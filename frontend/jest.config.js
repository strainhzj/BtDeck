/**
 * 统一的 Vue 2 + TypeScript Jest 配置。
 *
 * 同时收集 tests/unit 的纯函数测试与 src 组件目录中的组件/性能回归，
 * 防止组件测试因 roots、Node 环境或缺少 .vue transform 被静默排除。
 */
module.exports = {
  preset: '@vue/cli-plugin-unit-jest/presets/typescript-and-babel',
  testEnvironment: 'jsdom',
  roots: ['<rootDir>/tests/unit', '<rootDir>/src/components'],
  testMatch: ['**/*.spec.ts'],
  moduleNameMapper: {
    '^@/(.*)$': '<rootDir>/src/$1'
  },
  globals: {
    'ts-jest': {
      babelConfig: true,
      tsconfig: {
        strict: false,
        esModuleInterop: true,
        experimentalDecorators: true
      }
    }
  }
}
