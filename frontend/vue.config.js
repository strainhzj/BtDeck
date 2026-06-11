const path = require('path')
const MonacoWebpackPlugin = require('monaco-editor-webpack-plugin')

const name = 'BtDeck'

module.exports = {
  // Docker部署使用根路径，如需子路径部署请修改此处
  publicPath: process.env.NODE_ENV === 'production' ? '/' : '/',
  lintOnSave: false,
  pwa: {
    name: name
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
      config.plugins.delete('fork-ts-checker')
    }

    // provide the app's title in html-webpack-plugin's options list so that
    // it can be accessed in index.html to inject the correct title.
    if (config.plugins.has('html')) {
      config.plugin('html').tap(args => {
        args[0].title = name
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
        onProxyReq: (proxyReq, req, res) => {
          console.log('[Proxy]', req.method, req.url, '→ http://127.0.0.1:5001')
        },
        onError: (err, req, res) => {
          console.error('[Proxy Error]', err.message)
        },
        onProxyReqWs: (proxyReq, req, socket, options, head) => {
          console.log('[Proxy WS]', req.url, '→ http://127.0.0.1:5001')
        }
      }
    }
  }
}
