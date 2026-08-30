import {
  getSyncTaskStatus,
  SyncTaskStatusData
} from '@/api/downloader'

const TERMINAL_SYNC_STATES = new Set(['success', 'failed', 'cancelled'])

export type SyncTaskNoticeLevel = 'success' | 'warning' | 'error'

export interface SyncTaskNotice {
  level: SyncTaskNoticeLevel
  message: string
}

export interface SyncTaskTrackingHandle {
  cancel: () => void
}

interface SyncTaskTrackingOptions {
  intervalMs?: number
  maxAttempts?: number
  maxConsecutiveErrors?: number
  onTerminal: (task: SyncTaskStatusData) => void
  onTimeout: () => void
  onError: (error: unknown) => void
}

/** 将后台任务终态转换为下载器页面可直接展示的提示。 */
export function buildSyncTaskNotice(task: SyncTaskStatusData, fallbackName: string): SyncTaskNotice {
  const name = task.downloader_nickname || fallbackName
  const outcome = task.result?.outcome || ''
  const detail = task.result?.message || task.error || ''
  const suffix = detail ? `：${detail}` : ''

  if (task.status === 'cancelled' || outcome === 'cancelled') {
    return { level: 'warning', message: `${name} 同步已取消${suffix}` }
  }
  if (outcome === 'partial') {
    return { level: 'warning', message: `${name} 同步部分完成${suffix}` }
  }
  if (task.status === 'failed' || task.result?.status === 'failed') {
    return { level: 'error', message: `${name} 同步失败${suffix}` }
  }
  return { level: 'success', message: `${name} 同步完成${suffix}` }
}

/**
 * 跟踪 sync-single 返回的后台任务直到终态。
 *
 * 首次查询也经零延迟 timer 调度，保证调用方先保存 handle；cancel 会清理所有
 * 后续 timer，组件销毁时不会继续访问已销毁的 Vue 实例。
 */
export function trackSyncTaskStatus(
  taskId: string,
  options: SyncTaskTrackingOptions
): SyncTaskTrackingHandle {
  const intervalMs = options.intervalMs ?? 1000
  const maxAttempts = options.maxAttempts ?? 600
  const maxConsecutiveErrors = options.maxConsecutiveErrors ?? 3
  let timer: ReturnType<typeof setTimeout> | null = null
  let attempts = 0
  let consecutiveErrors = 0
  let cancelled = false

  const cancel = (): void => {
    cancelled = true
    if (timer !== null) {
      clearTimeout(timer)
      timer = null
    }
  }

  const schedule = (delayMs: number): void => {
    if (cancelled) return
    timer = setTimeout(() => {
      timer = null
      void poll()
    }, delayMs)
  }

  const poll = async(): Promise<void> => {
    if (cancelled) return
    attempts += 1

    try {
      const response = await getSyncTaskStatus(taskId)
      if (cancelled) return
      consecutiveErrors = 0
      const task = response.data

      if (TERMINAL_SYNC_STATES.has(task.status)) {
        cancel()
        options.onTerminal(task)
        return
      }
      if (attempts >= maxAttempts) {
        cancel()
        options.onTimeout()
        return
      }
      schedule(intervalMs)
    } catch (error: unknown) {
      if (cancelled) return
      consecutiveErrors += 1
      if (consecutiveErrors >= maxConsecutiveErrors || attempts >= maxAttempts) {
        cancel()
        options.onError(error)
        return
      }
      schedule(intervalMs)
    }
  }

  schedule(0)
  return { cancel }
}
