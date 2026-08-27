/**
 * ui-mode 工具契约（dual-mode-client Phase 4 M1）：
 * 偏好持久化、视口判定、模式合成与登录分流——移动/桌面视图选择的三条
 * 原则（非 UA 唯一依据 / 显式选择优先 / 移动版可切回桌面）的行为锁定。
 */

describe('utils/ui-mode', () => {
  let uiMode: typeof import('@/utils/ui-mode')

  beforeEach(() => {
    localStorage.clear()
    jest.resetModules()
    // eslint-disable-next-line @typescript-eslint/no-var-requires
    uiMode = require('@/utils/ui-mode')
  })

  describe('偏好存取', () => {
    it('默认 auto', () => {
      expect(uiMode.getStoredUiMode()).toBe('auto')
    })

    it('显式选择持久化并可读回', () => {
      uiMode.setStoredUiMode('mobile')
      expect(uiMode.getStoredUiMode()).toBe('mobile')
      uiMode.setStoredUiMode('desktop')
      expect(uiMode.getStoredUiMode()).toBe('desktop')
    })

    it('非法存储值回退 auto', () => {
      localStorage.setItem('btdeck_ui_mode', 'bogus')
      expect(uiMode.getStoredUiMode()).toBe('auto')
    })
  })

  describe('视口判定', () => {
    it('767px 为窄视口，768px 起为宽视口', () => {
      expect(uiMode.isNarrowViewport(320)).toBe(true)
      expect(uiMode.isNarrowViewport(767)).toBe(true)
      expect(uiMode.isNarrowViewport(768)).toBe(false)
      expect(uiMode.isNarrowViewport(1920)).toBe(false)
    })
  })

  describe('模式合成', () => {
    it('显式 mobile/desktop 优先于视口', () => {
      expect(uiMode.resolveUiMode('mobile', 1920)).toBe('mobile')
      expect(uiMode.resolveUiMode('desktop', 320)).toBe('desktop')
    })

    it('auto 按视口判定', () => {
      expect(uiMode.resolveUiMode('auto', 375)).toBe('mobile')
      expect(uiMode.resolveUiMode('auto', 1280)).toBe('desktop')
    })
  })

  describe('路径映射', () => {
    it('桌面顶层页映射到移动对应页', () => {
      expect(uiMode.toMobilePath('/dashboard')).toBe('/m/dashboard')
      expect(uiMode.toMobilePath('/torrents')).toBe('/m/torrents')
      expect(uiMode.toMobilePath('/torrents/traditional')).toBe('/m/torrents')
    })

    it('M2 已移动化管理页映射到对应移动页；查询模板裁撤后落高级搜索', () => {
      expect(uiMode.toMobilePath('/recycle-bin')).toBe('/m/recycle-bin')
      expect(uiMode.toMobilePath('/recycle-bin/index')).toBe('/m/recycle-bin')
      expect(uiMode.toMobilePath('/logs/audit')).toBe('/m/logs')
      // 移动端查询模板页已裁撤（仅保留高级搜索）：模板能力收敛进 /m/search 工作区
      expect(uiMode.toMobilePath('/query-templates')).toBe('/m/search')
      expect(uiMode.toMobilePath('/query-templates/index')).toBe('/m/search')
    })

    it('系统设置映射到移动设置页（整页复用桌面设置组件）', () => {
      expect(uiMode.toMobilePath('/settings')).toBe('/m/settings')
      expect(uiMode.toMobilePath('/settings/index')).toBe('/m/settings')
    })

    it('M3 定时任务整页映射到移动任务页', () => {
      expect(uiMode.toMobilePath('/tasks')).toBe('/m/tasks')
      expect(uiMode.toMobilePath('/tasks/index')).toBe('/m/tasks')
    })

    it('M4 孤儿文件整页映射到移动孤儿文件页', () => {
      expect(uiMode.toMobilePath('/orphan-files')).toBe('/m/orphan-files')
      expect(uiMode.toMobilePath('/orphan-files/index')).toBe('/m/orphan-files')
    })

    it('M3 Tracker 仅看板/搜索两子页映射；汇报配置与测试工具保留桌面直达', () => {
      expect(uiMode.toMobilePath('/tracker')).toBe('/m/tracker/keywords-board')
      expect(uiMode.toMobilePath('/tracker/keywords-board')).toBe('/m/tracker/keywords-board')
      expect(uiMode.toMobilePath('/tracker/keywords-search')).toBe('/m/tracker/keywords-board')
      // 未移动化的 Tracker 子页不走移动分流（抽屉桌面组直达）
      expect(uiMode.toMobilePath('/tracker/reannounce-config')).toBe('/m/dashboard')
      expect(uiMode.toMobilePath('/tracker/test')).toBe('/m/dashboard')
    })

    it('无对应关系的路径兜底移动仪表盘（不落到空白页）', () => {
      expect(uiMode.toMobilePath('/downloader')).toBe('/m/dashboard')
      expect(uiMode.toMobilePath('/tracker/reannounce-config')).toBe('/m/dashboard')
    })
  })

  describe('登录页分流', () => {
    it('移动模式跳移动登录并保留 redirect', () => {
      uiMode.setStoredUiMode('mobile')
      expect(uiMode.loginPathForMode('/torrents')).toBe('/m/login?redirect=%2Ftorrents')
    })

    it('桌面模式跳桌面登录', () => {
      uiMode.setStoredUiMode('desktop')
      expect(uiMode.loginPathForMode('/torrents')).toBe('/login?redirect=%2Ftorrents')
    })

    it('无 redirect 时裸登录路径', () => {
      uiMode.setStoredUiMode('mobile')
      expect(uiMode.loginPathForMode()).toBe('/m/login')
    })
  })
})
