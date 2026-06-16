import { VuexModule, Module, Mutation, Action, getModule } from 'vuex-module-decorators'
import store from '@/store'
import {
  getNotificationList,
  getUnreadCount,
  markAsRead,
  markAsUnread,
  markAllAsRead,
  deleteNotification,
  NotificationItem
} from '@/api/notification'

export interface INotificationState {
  drawerVisible: boolean
  unreadCount: number
  notifications: NotificationItem[]
  total: number
  page: number
  loading: boolean
  currentFilter: { page?: number; type?: string; is_read?: boolean }
}

@Module({ dynamic: true, store, name: 'notification' })
class Notification extends VuexModule implements INotificationState {
  public drawerVisible = false
  public unreadCount = 0
  public notifications: NotificationItem[] = []
  public total = 0
  public page = 1
  public loading = false
  public currentFilter: { page?: number; type?: string; is_read?: boolean } = {}

  @Mutation
  private SET_DRAWER_VISIBLE(visible: boolean) {
    this.drawerVisible = visible
  }

  @Mutation
  private SET_UNREAD_COUNT(count: number) {
    this.unreadCount = count
  }

  @Mutation
  private SET_NOTIFICATIONS(payload: { list: NotificationItem[]; total: number }) {
    this.notifications = payload.list
    this.total = payload.total
  }

  @Mutation
  private SET_LOADING(loading: boolean) {
    this.loading = loading
  }

  @Mutation
  private SET_CURRENT_FILTER(filter: { page?: number; type?: string; is_read?: boolean }) {
    this.currentFilter = filter
  }

  @Action({ rawError: true })
  public ToggleDrawer(visible?: boolean) {
    this.SET_DRAWER_VISIBLE(visible !== undefined ? visible : !this.drawerVisible)
  }

  @Action({ rawError: true })
  public async FetchUnreadCount() {
    try {
      const res = await getUnreadCount()
      if (res.code === '200') {
        this.SET_UNREAD_COUNT(res.data.count)
      }
    } catch (e) {
      // 静默失败，不影响用户体验
    }
  }

  @Action({ rawError: true })
  public async FetchNotifications(payload?: { page?: number; type?: string; is_read?: boolean }) {
    // 保存当前筛选条件
    if (payload) {
      this.SET_CURRENT_FILTER(payload)
    }
    this.SET_LOADING(true)
    try {
      const res = await getNotificationList({
        page: payload?.page || 1,
        pageSize: 20,
        type: payload?.type,
        is_read: payload?.is_read
      })
      if (res.code === '200') {
        this.SET_NOTIFICATIONS({ list: res.data.list, total: res.data.total })
      }
    } catch (e) {
      // 静默失败
    } finally {
      this.SET_LOADING(false)
    }
  }

  @Action({ rawError: true })
  public async RefreshNotifications() {
    // 使用当前保存的筛选条件刷新列表
    await this.FetchNotifications(this.currentFilter)
  }

  @Action({ rawError: true })
  public async MarkAsRead(id: number) {
    try {
      const res = await markAsRead(id)
      if (res.code === '200') {
        // 使用当前筛选条件刷新列表
        await this.RefreshNotifications()
        await this.FetchUnreadCount()
      }
    } catch (e) {
      // 静默失败
    }
  }

  @Action({ rawError: true })
  public async MarkAllAsRead() {
    try {
      const res = await markAllAsRead()
      if (res.code === '200') {
        await this.RefreshNotifications()
        await this.FetchUnreadCount()
      }
    } catch (e) {
      // 静默失败
    }
  }

  @Action({ rawError: true })
  public async MarkAsUnread(id: number) {
    try {
      const res = await markAsUnread(id)
      if (res.code === '200') {
        await this.RefreshNotifications()
        await this.FetchUnreadCount()
      }
    } catch (e) {
      // 静默失败
    }
  }

  @Action({ rawError: true })
  public async DeleteNotification(id: number) {
    try {
      const res = await deleteNotification(id)
      if (res.code === '200') {
        await this.RefreshNotifications()
        await this.FetchUnreadCount()
      }
    } catch (e) {
      // 静默失败
    }
  }
}

export const NotificationModule = getModule(Notification)
