/*
 * Copyright (C) 2025 BTDeck Contributors
 *
 * This program is free software: you can redistribute it and/or modify
 * it under the terms of the GNU General Public License as published by
 * the Free Software Foundation, either version 3 of the License, or
 * (at your option) any later version.
 *
 * This program is distributed in the hope that it will be useful,
 * but WITHOUT ANY WARRANTY; without even the implied warranty of
 * MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
 * GNU General Public License for more details.
 *
 * You should have received a copy of the GNU General Public License
 * along with this program.  If not, see <https://www.gnu.org/licenses/>.
 */

import Vue from 'vue'

import 'normalize.css'
import ElementUI from 'element-ui'
import SvgIcon from 'vue-svgicon'

import '@/styles/element-variables.scss'
import '@/styles/index.scss'
import '@/styles/management-list-page.scss'

import { initTheme } from '@/utils/theme'

// 初始化主题
initTheme()

import App from '@/App.vue'
import store from '@/store'
import router from '@/router'
import '@/icons/components/index'
import '@/permission'
import waves from '@/directive/waves' // waves directive
import LucideIcon from '@/components/common/LucideIcon.vue'
import {
  clearChunkRecoveryQuery,
  retireLegacyServiceWorkers
} from '@/utils/deployment-recovery'
import { initSessionWatch } from '@/utils/session'
import { isDemoMode } from '@/demo/config'
import { UserModule } from '@/store/modules/user'

Vue.use(ElementUI)

// 全局注册 Lucide 图标组件，统一替换界面中的 emoji / el-icon-* / 自绘 SVG。
Vue.component('LucideIcon', LucideIcon)
// 全局注册通用可折叠面板（W8：各页面展开/收缩 + 用户习惯持久化）
Vue.component('CollapsiblePanel', () => import('@/components/CollapsiblePanel.vue'))
Vue.use(SvgIcon, {
  tagName: 'svg-icon',
  defaultWidth: '1em',
  defaultHeight: '1em'
})

// 注册waves指令
Vue.directive('waves', waves)

Vue.config.productionTip = false

if (isDemoMode()) {
  UserModule.InitializeDemoSession()
}

// PWA（v1.0.6 移动独有优化）：先退休模板时代的遗留 SW（裸 service-worker.js
// 无标记注册 + 模板前缀缓存），再注册本版 SW（脚本带 src=btdeck 标记，
// 二者互不干扰）；skipWaiting=false，新版本经 RefreshPrompt 用户确认后激活。
void retireLegacyServiceWorkers().finally(() => {
  import('@/registerServiceWorker').catch(() => undefined)
})

// 双令牌会话监听（W6 伴随修复）：标签页重新可见时从 cookie 同步最新令牌，
// 检测到会话已在别处结束时统一走登出跳转
if (!isDemoMode()) {
  initSessionWatch()
}

// Keep the reload-loop marker until the initial lazy route loaded successfully.
router.onReady(() => clearChunkRecoveryQuery())

new Vue({
  router,
  store,
  render: (h) => h(App)
}).$mount('#app')
