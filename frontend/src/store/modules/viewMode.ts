import { VuexModule, Module, Mutation, Action, getModule } from 'vuex-module-decorators'
import { getStorage, setStorage } from '@/utils/cookies'
import store from '@/store'

export type ViewModeType = 'list' | 'traditional'

export interface IViewModeState {
  currentMode: ViewModeType
  filterPanelCollapsed: boolean
}

const VIEW_MODE_STORAGE_KEY = 'btdeck_view_mode'
const FILTER_PANEL_STORAGE_KEY = 'btdeck_filter_panel_collapsed'

@Module({ dynamic: true, store, name: 'viewMode' })
class ViewMode extends VuexModule implements IViewModeState {
  public currentMode: ViewModeType = (getStorage(VIEW_MODE_STORAGE_KEY) as ViewModeType) || 'list'
  public filterPanelCollapsed: boolean = getStorage(FILTER_PANEL_STORAGE_KEY) === 'true'

  @Mutation
  private SET_VIEW_MODE(mode: ViewModeType) {
    this.currentMode = mode
    setStorage(VIEW_MODE_STORAGE_KEY, mode)
  }

  @Mutation
  private TOGGLE_FILTER_PANEL() {
    this.filterPanelCollapsed = !this.filterPanelCollapsed
    setStorage(FILTER_PANEL_STORAGE_KEY, String(this.filterPanelCollapsed))
  }

  @Mutation
  private SET_FILTER_PANEL_COLLAPSED(collapsed: boolean) {
    this.filterPanelCollapsed = collapsed
    setStorage(FILTER_PANEL_STORAGE_KEY, String(collapsed))
  }

  @Action({ rawError: true })
  public setViewMode(mode: ViewModeType) {
    this.SET_VIEW_MODE(mode)
  }

  @Action({ rawError: true })
  public toggleFilterPanel() {
    this.TOGGLE_FILTER_PANEL()
  }

  @Action({ rawError: true })
  public setFilterPanelCollapsed(collapsed: boolean) {
    this.SET_FILTER_PANEL_COLLAPSED(collapsed)
  }
}

export const ViewModeModule = getModule(ViewMode)
