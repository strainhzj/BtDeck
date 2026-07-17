import { setSidebarStatus, setStorage } from '@/utils/cookies'
import { AppModule, DeviceType } from '@/store/modules/app'
import { ViewModeModule } from '@/store/modules/viewMode'

jest.mock('@/utils/cookies', () => ({
  getSidebarStatus: jest.fn(() => 'opened'),
  setSidebarStatus: jest.fn(),
  getStorage: jest.fn(() => null),
  setStorage: jest.fn(),
  getToken: jest.fn(),
  setToken: jest.fn(),
  removeToken: jest.fn(),
  getUserId: jest.fn(() => ''),
  setUserId: jest.fn(),
  removeUserId: jest.fn()
}))

const mockSetStorage = setStorage as jest.MockedFunction<typeof setStorage>
const mockSetSidebarStatus = setSidebarStatus as jest.MockedFunction<typeof setSidebarStatus>

describe('ViewModeModule 状态与持久化', () => {
  beforeEach(async() => {
    await Promise.resolve(ViewModeModule.setViewMode('list'))
    await Promise.resolve(ViewModeModule.setFilterPanelCollapsed(false))
    mockSetStorage.mockClear()
  })

  it('切换列表模式时同步写入本地存储', async() => {
    await Promise.resolve(ViewModeModule.setViewMode('traditional'))

    expect(ViewModeModule.currentMode).toBe('traditional')
    expect(mockSetStorage).toHaveBeenCalledWith('btdeck_view_mode', 'traditional')
  })

  it('切换和显式设置筛选面板状态时保持布尔值与字符串存储一致', async() => {
    await Promise.resolve(ViewModeModule.toggleFilterPanel())
    expect(ViewModeModule.filterPanelCollapsed).toBe(true)
    expect(mockSetStorage).toHaveBeenLastCalledWith('btdeck_filter_panel_collapsed', 'true')

    await Promise.resolve(ViewModeModule.setFilterPanelCollapsed(false))
    expect(ViewModeModule.filterPanelCollapsed).toBe(false)
    expect(mockSetStorage).toHaveBeenLastCalledWith('btdeck_filter_panel_collapsed', 'false')
  })
})

describe('AppModule 导航状态', () => {
  beforeEach(async() => {
    await Promise.resolve(AppModule.CloseSideBar(false))
    await Promise.resolve(AppModule.ToggleDevice(DeviceType.Desktop))
    mockSetSidebarStatus.mockClear()
  })

  it('打开和关闭侧边栏时保存状态并透传动画标志', async() => {
    await Promise.resolve(AppModule.ToggleSideBar(true))
    expect(AppModule.sidebar).toEqual({ opened: true, withoutAnimation: true })
    expect(mockSetSidebarStatus).toHaveBeenLastCalledWith('opened')

    await Promise.resolve(AppModule.CloseSideBar(false))
    expect(AppModule.sidebar).toEqual({ opened: false, withoutAnimation: false })
    expect(mockSetSidebarStatus).toHaveBeenLastCalledWith('closed')
  })

  it('设备切换只改变设备类型', async() => {
    const sidebarBefore = { ...AppModule.sidebar }
    await Promise.resolve(AppModule.ToggleDevice(DeviceType.Mobile))

    expect(AppModule.device).toBe(DeviceType.Mobile)
    expect(AppModule.sidebar).toEqual(sidebarBefore)
  })
})
