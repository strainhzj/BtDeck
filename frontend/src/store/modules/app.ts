import { VuexModule, Module, Mutation, Action, getModule } from 'vuex-module-decorators'
import { getSidebarStatus, setSidebarStatus } from '@/utils/cookies'
import { getLocale, setLocale } from '@/i18n'
import { Locale } from '@/i18n/types'
import store from '@/store'

export enum DeviceType {
  Mobile,
  Desktop,
}

export interface IAppState {
  device: DeviceType
  sidebar: {
    opened: boolean
    withoutAnimation: boolean
  }
  language: Locale
}

@Module({ dynamic: true, store, name: 'app' })
class App extends VuexModule implements IAppState {
  public sidebar = {
    opened: getSidebarStatus() !== 'closed',
    withoutAnimation: false
  }

  public device = DeviceType.Desktop

  /** 界面语言（持久化在 i18n 层的 localStorage，此处为响应式镜像） */
  public language: Locale = getLocale()

  @Mutation
  private TOGGLE_SIDEBAR(withoutAnimation: boolean) {
    this.sidebar.opened = !this.sidebar.opened
    this.sidebar.withoutAnimation = withoutAnimation
    if (this.sidebar.opened) {
      setSidebarStatus('opened')
    } else {
      setSidebarStatus('closed')
    }
  }

  @Mutation
  private CLOSE_SIDEBAR(withoutAnimation: boolean) {
    this.sidebar.opened = false
    this.sidebar.withoutAnimation = withoutAnimation
    setSidebarStatus('closed')
  }

  @Mutation
  private TOGGLE_DEVICE(device: DeviceType) {
    this.device = device
  }

  @Mutation
  private SET_LANGUAGE(locale: Locale) {
    this.language = locale
    // i18n 层负责：i18n.locale、localStorage 持久化、document.lang
    setLocale(locale)
  }

  @Action({ rawError: true })
  public SetLanguage(locale: Locale) {
    this.SET_LANGUAGE(locale)
  }

  @Action({ rawError: true })
  public ToggleSideBar(withoutAnimation: boolean) {
    this.TOGGLE_SIDEBAR(withoutAnimation)
  }

  @Action({ rawError: true })
  public CloseSideBar(withoutAnimation: boolean) {
    this.CLOSE_SIDEBAR(withoutAnimation)
  }

  @Action({ rawError: true })
  public ToggleDevice(device: DeviceType) {
    this.TOGGLE_DEVICE(device)
  }
}

export const AppModule = getModule(App)
