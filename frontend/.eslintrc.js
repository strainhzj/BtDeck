module.exports = {
  root: true,
  env: {
    node: true,
    browser: true,
    es6: true
  },
  parser: 'vue-eslint-parser',
  parserOptions: {
    parser: '@typescript-eslint/parser',
    ecmaVersion: 2020,
    sourceType: 'module',
    ecmaFeatures: {
      jsx: false
    },
    project: undefined,
    extraFileExtensions: ['.vue']
  },
  extends: [
    'plugin:vue/essential',
    'plugin:@typescript-eslint/recommended'
  ],
  plugins: [
    '@typescript-eslint'
  ],
  rules: {
    '@typescript-eslint/ban-types': 'off',
    '@typescript-eslint/explicit-module-boundary-types': 'off',
    // 防回归 Bug#9：未用 import 检查
    // 全仓有 117 个既存未用变量（历史债，与本轮 bug 无关），强制 error 会让 CI 变红，
    // 故降为 warn（提示但不阻断）；no-restricted-syntax（fetch/token）仍为 error 强拦。
    // 历史债由后续专项清理，新代码未用变量会以 warning 形式可见。
    '@typescript-eslint/no-unused-vars': ['warn', {
      argsIgnorePattern: '^_',
      varsIgnorePattern: '^_',
      ignoreRestSiblings: true
    }],
    // 防回归 Bug#3：禁止原生 fetch / 直接读 token，强制走 utils/request.ts 的 axios 封装
    // selector 已用项目实际 esquery 1.7.0 实测有效（dry-run 全仓 0 误伤）
    // 注意：arguments.0.value 是 esquery 正确语法，firstArgument 不存在（会静默失效）
    'no-restricted-syntax': ['error',
      // 裸 fetch() 调用（callee 是 Identifier，仅匹配名为 fetch，不误伤 fetchList）
      {
        selector: "CallExpression[callee.type='Identifier'][callee.name='fetch']",
        message: '禁止原生 fetch，请用 @/utils/request 封装 API（token 由拦截器统一注入）'
      },
      // 成员调用 fetch()：this.fetch / window.fetch / xxx.fetch（精确名=fetch，不误伤 this.fetchList）
      {
        selector: "CallExpression[callee.type='MemberExpression'][callee.property.name='fetch']",
        message: '禁止原生 fetch，请用 @/utils/request 封装 API'
      },
      // localStorage.getItem('token') —— 字面量 key（变量 key 如 tokenKey 拦不住，需 review 兜底）
      {
        selector: "CallExpression[callee.type='MemberExpression'][callee.property.name='getItem'][arguments.0.value='token']",
        message: '禁止从 localStorage 直接读 token，请用 getToken() 或 UserModule.token'
      },
      // Cookies.get('token') 字面量 key
      {
        selector: "CallExpression[callee.type='MemberExpression'][callee.property.name='get'][arguments.0.value='token']",
        message: '禁止硬编码 key 读 token，请在 utils/cookies.ts 内部管理'
      }
    ],
    '@typescript-eslint/member-delimiter-style': ['error',
      {
        multiline: {
          delimiter: 'none'
        },
        singleline: {
          delimiter: 'comma'
        }
      }],
    '@typescript-eslint/no-explicit-any': 'off',
    '@typescript-eslint/no-var-requires': 'off',
    'no-console': process.env.NODE_ENV === 'production' ? 'error' : 'off',
    'no-debugger': process.env.NODE_ENV === 'production' ? 'error' : 'off',
    'space-before-function-paren': ['error', 'never'],
    'vue/array-bracket-spacing': 'error',
    'vue/arrow-spacing': 'error',
    'vue/block-spacing': 'error',
    'vue/brace-style': 'error',
    'vue/camelcase': 'error',
    'vue/comma-dangle': 'error',
    'vue/component-name-in-template-casing': ['error', 'kebab-case'],
    'vue/eqeqeq': 'error',
    'vue/key-spacing': 'error',
    'vue/match-component-file-name': 'error',
    'vue/object-curly-spacing': 'error'
  },
  overrides: [
    {
      files: [
        '**/__tests__/*.{j,t}s?(x)',
        '**/tests/unit/**/*.spec.{j,t}s?(x)'
      ],
      env: {
        jest: true
      }
    },
    {
      // FileManagement.vue 给 el-upload 的 uploadHeaders 手动注入 token（el-upload 不走 axios 拦截器）
      // 这是合法用途，文件级豁免（比行内 eslint-disable 稳，防行号漂移/规则名笔误导致静默失效）
      files: ['**/torrents/FileManagement.vue'],
      rules: {
        'no-restricted-syntax': 'off'
      }
    }
  ]
}
