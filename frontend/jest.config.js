/**
 * 统一的 Vue 2 + TypeScript Jest 配置。
 *
 * 同时收集 tests/unit 的纯函数测试与 src 组件目录中的组件/性能回归，
 * 防止组件测试因 roots、Node 环境或缺少 .vue transform 被静默排除。
 */
module.exports = {
  preset: '@vue/cli-plugin-unit-jest/presets/typescript-and-babel',
  testEnvironment: 'jsdom',
  roots: ['<rootDir>/tests/unit', '<rootDir>/src'],
  testMatch: ['**/*.spec.ts'],
  collectCoverageFrom: [
    '<rootDir>/src/**/*.ts',
    '<rootDir>/src/components/torrents/AdvancedMultiSelect.vue',
    '<rootDir>/src/components/torrents/AdvancedSearchBuilder.vue',
    '<rootDir>/src/views/torrents/TraditionalView.vue',
    '!<rootDir>/src/**/*.d.ts',
    '!<rootDir>/src/icons/**',
    '!<rootDir>/src/main.ts',
    '!<rootDir>/src/registerServiceWorker.ts'
  ],
  coverageDirectory: '<rootDir>/coverage',
  coverageReporters: ['text-summary', 'html', 'lcov'],
  coverageThreshold: {
    global: {
      branches: 40,
      functions: 40,
      lines: 40,
      statements: 40
    }
  },
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
