const path = require('path')
const MonacoWebpackPlugin = require('monaco-editor-webpack-plugin')

const isDemoBuild = process.env.VUE_APP_DEMO_MODE === 'true'
const name = isDemoBuild ? 'BtDeck Demo' : 'BtDeck'

module.exports = {
  // Docker部署使用根路径，如需子路径部署请修改此处
  publicPath: process.env.NODE_ENV === 'production' ? '/' : '/',
  // 静态资源统一输出到 dist/assets/ 目录（JS/CSS/字体/图片）
  // 与后端 factory.py 的 mount("/assets", frontend_dist/assets) 对齐
  assetsDir: 'assets',
  lintOnSave: false,
  pwa: {
    name: name,
    // 品牌主题色与前端主题同源（theme-variables.scss --color-primary #059669）
    themeColor: '#059669',
    msTileColor: '#059669',
    // iOS 添加到主屏幕后独立全屏运行（配合移动版 UI）；
    // v5 插件为扁平选项（v4 的 appleMobileWebAppOptions 对象不生效）
    appleMobileWebAppCapable: 'yes',
    appleMobileWebAppStatusBarStyle: 'default',
    appleMobileWebAppTitle: name,
    workboxOptions: {
      // 缓存前缀品牌化：默认值是包名 vue-typescript-admin-template，
      // 恰为 deployment-recovery 的遗留清理前缀，必须区分开
      cacheId: 'btdeck',
      // 首装立即接管已打开页面；版本更新保持 waiting，由页面内
      // RefreshPrompt 提示用户 SKIP_WAITING + 刷新（防止旧壳钉死）
      clientsClaim: true,
      skipWaiting: false
    }
  },
  pluginOptions: {
    'style-resources-loader': {
      preProcessor: 'scss',
      patterns: [
        path.resolve(__dirname, 'src/styles/_variables.scss'),
        path.resolve(__dirname, 'src/styles/_mixins.scss')
      ]
    }
  },

  configureWebpack: {
    plugins: [
      new MonacoWebpackPlugin({
        languages: ['javascript', 'typescript', 'css', 'html', 'json', 'python']
      })
    ]
  },

  chainWebpack(config) {
    // Configure webpack to handle missing core-js modules with empty polyfills
    const missingModules = [
      'core-js/modules/es.array.push.js',
      'core-js/modules/es.error.cause.js',
      'core-js/modules/es.iterator.constructor.js',
      'core-js/modules/es.iterator.filter.js',
      'core-js/modules/es.iterator.reduce.js',
      'core-js/modules/es.object.proto.js',
      'core-js/modules/web.btoa.js',
      'core-js/modules/web.dom-exception.constructor.js',
      'core-js/modules/web.dom-exception.stack.js',
      'core-js/modules/web.dom-exception.to-string-tag.js'
    ]

    missingModules.forEach(module => {
      config.resolve.alias.set(module, path.resolve(__dirname, 'src/utils/empty-polyfill.js'))
    })

    config.resolve.alias.set('path', require.resolve('path-browserify'))

    if (config.plugins.has('fork-ts-checker')) {
      config.plugin('fork-ts-checker').tap(args => {
        // 保留生产构建中的 TypeScript 门禁。历史 Vue SFC 尚有独立类型债务，当前先由
        // tsc 严格覆盖全部 .ts/.tsx；SFC 通过 Jest 的 vue-jest 与 webpack 编译验证。
        args[0].typescript.extensions.vue.enabled = false
        return args
      })
    }

    // provide the app's title in html-webpack-plugin's options list so that
    // it can be accessed in index.html to inject the correct title.
    if (config.plugins.has('html')) {
      config.plugin('html').tap(args => {
        args[0].title = process.env.VUE_APP_TITLE || name
        return args
      })
    }
  },
  devServer: {
    allowedHosts: ["main.btpmanager.top"],
    host: '0.0.0.0',
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:5001',
        changeOrigin: true,
        secure: false,
        ws: false,
        pathRewrite: {
          '^/api': '/api'
        },
        onProxyReq: (proxyReq, req, _res) => {
          console.log('[Proxy]', req.method, req.url, '→ http://127.0.0.1:5001')
        },
        onError: (err, _req, _res) => {
          console.error('[Proxy Error]', err.message)
        },
        onProxyReqWs: (proxyReq, req, _socket, _options, _head) => {
          console.log('[Proxy WS]', req.url, '→ http://127.0.0.1:5001')
        }
      }
    }
  }
}
