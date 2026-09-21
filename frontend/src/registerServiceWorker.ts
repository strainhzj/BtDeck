/* eslint-disable no-console */

import { register } from 'register-service-worker'

import { PWA_SW_SCRIPT_MARKER } from '@/utils/deployment-recovery'

// SW 脚本带 src=btdeck 标记注册：deployment-recovery.retireLegacyServiceWorkers
// 只清理无标记的模板时代注册，二者在同一次启动里共存互不干扰。
const SERVICE_WORKER_URL = `${process.env.BASE_URL}service-worker.js?${PWA_SW_SCRIPT_MARKER}`

// 与 RefreshPrompt 组件的通信：SW 检测到新版本处于 waiting 时派发，
// detail 携带 registration 供组件 postMessage SKIP_WAITING。
export const SW_UPDATED_EVENT = 'btdeck-sw-updated'

export interface SwUpdatedDetail {
  registration: ServiceWorkerRegistration
}

function notifyUpdate(registration: ServiceWorkerRegistration): void {
  window.dispatchEvent(
    new CustomEvent<SwUpdatedDetail>(SW_UPDATED_EVENT, { detail: { registration } })
  )
}

if (process.env.NODE_ENV === 'production') {
  register(SERVICE_WORKER_URL, {
    ready() {
      console.log('App is being served from cache by a service worker.')
    },
    registered() {
      console.log('Service worker has been registered.')
    },
    cached() {
      console.log('Content has been cached for offline use.')
    },
    updatefound() {
      console.log('New content is downloading.')
    },
    updated(registration) {
      console.log('New content is available; please refresh.')
      notifyUpdate(registration)
    },
    offline() {
      console.log('No internet connection found. App is running in offline mode.')
    },
    error(error) {
      console.error('Error during service worker registration:', error)
    }
  })
}
