import { readFileSync } from 'fs'
import { resolve } from 'path'

const readSource = (relativePath: string): string => readFileSync(
  resolve(__dirname, '../../src', relativePath),
  'utf8'
)

const templateOf = (source: string): string => {
  const templateStart = source.indexOf('<template>')
  const scriptStart = source.indexOf('<script')
  return templateStart >= 0 && scriptStart > templateStart
    ? source.slice(templateStart, scriptStart)
    : ''
}

const downloaderPage = readSource('views/downloader/index.vue')
const downloaderCard = readSource('views/downloader/components/DownloaderCard.vue')
const settingsDialog = readSource('views/downloader/components/DownloaderSettingsDialog.vue')
const speedSettingsTab = readSource('views/downloader/components/SpeedSettingsTab.vue')
const pathManagementTab = readSource('views/downloader/components/PathManagementTab.vue')
const pathMappingTab = readSource('views/downloader/components/PathMappingTab.vue')
const routerSource = readSource('router.ts')

const lucideOnlySurfaces = [
  'views/downloader/index.vue',
  'views/downloader/components/DownloaderCard.vue',
  'views/downloader/components/DownloaderSettingsDialog.vue',
  'views/downloader/components/BasicSettingsTab.vue',
  'views/downloader/components/AdvancedSettingsTab.vue',
  'views/downloader/components/SpeedSettingsTab.vue',
  'views/downloader/components/PathManagementTab.vue',
  'views/downloader/components/PathMappingTab.vue',
  'views/downloader/components/DownloaderPathManagement.vue',
  'views/downloader/components/TagManagementTab.vue',
  'views/downloader/components/TemplateSelectionDialog.vue',
  'layout/components/Sidebar/index.vue',
  'layout/components/Sidebar/SidebarItem.vue',
  'layout/components/Navbar/index.vue',
  'components/ThemeSwitcher/index.vue',
  'layout/components/NotificationDrawer/index.vue',
  'layout/components/NotificationDrawer/NotificationItem.vue'
].map((path) => [path, templateOf(readSource(path))] as const)

describe('下载器控制台视觉骨架', () => {
  it('从状态链路工具栏开始展示节点网格，并保留响应式降级', () => {
    expect(downloaderPage).toContain('class="downloader-control-room"')
    expect(downloaderPage).toContain('class="command-deck"')
    expect(downloaderPage).toContain('class="downloader-grid"')
    expect(downloaderPage).toContain('状态链路已建立')
    expect(downloaderPage).not.toContain('class="control-hero"')
    expect(downloaderPage).not.toContain('class="control-metrics"')
    expect(downloaderPage).toContain('@media (max-width: 680px)')
    expect(downloaderPage).toContain('@media (prefers-reduced-motion: reduce)')
  })

  it('节点卡片保留测试、同步、设置、启停和删除功能', () => {
    expect(downloaderCard).toContain('class="node-telemetry"')
    expect(downloaderCard).toContain("$emit('test'")
    expect(downloaderCard).toContain("$emit('sync'")
    expect(downloaderCard).toContain("$emit('settings'")
    expect(downloaderCard).toContain("$emit('delete'")
    expect(downloaderCard).toContain("$emit('toggle-enable'")
  })

  it('同步按钮跟踪后台 task_id 到真实终态，并在销毁时取消状态轮询', () => {
    expect(downloaderPage).toContain('const taskId = response.data?.task_id')
    expect(downloaderPage).toContain('startTracking(validId, taskId, nickname)')
    expect(downloaderPage).toContain('trackSyncTaskStatus(taskId')
    expect(downloaderPage).toContain('buildSyncTaskNotice(task, nickname)')
    expect(downloaderPage).toContain('this.syncTaskTrackers.forEach(tracker => tracker.cancel())')
    expect(downloaderPage).not.toContain("Message.success('执行成功')")
  })
})

describe('下载器设置工作台', () => {
  it('使用自定义标题、左侧模式导航和紧凑基础信息网格', () => {
    expect(settingsDialog).toContain('class="workspace-header"')
    expect(settingsDialog).toContain('tab-position="left"')
    expect(settingsDialog).toContain('class="workspace-basic-form"')
    expect(settingsDialog).toContain('label-position="top"')
    expect(settingsDialog).toContain('label-width="auto"')
    expect(settingsDialog).toContain('class="panel-intro"')
    expect(settingsDialog).toContain('class="workspace-footer-button')
    expect(settingsDialog).toContain('text-align: left;')
    expect(settingsDialog).toContain('flex: 1 1 auto;')
    expect(settingsDialog).toContain('justify-content: flex-start !important;')
    expect(settingsDialog).toContain('width: 0;')
    expect(settingsDialog).toContain('class="tab-content tab-content--basic"')
    expect(settingsDialog).toContain('text-align: left !important;')
    expect(settingsDialog).toContain('overflow: hidden;')
    expect(speedSettingsTab).toContain('class="speed-limit-form"')
    expect(speedSettingsTab).toContain('label-position="top"')
    expect(speedSettingsTab).toContain('text-align: left !important;')
    expect(pathManagementTab).toContain('display: flex;')
    expect(pathManagementTab).toContain('justify-content: flex-start !important;')
    expect(pathManagementTab).toContain('text-align: left;')
    expect(pathManagementTab).toContain('text-align: left !important;')
    expect(pathMappingTab).toContain('padding: 0;')
  })

  it('新增模式锁定依赖已保存下载器的子面板，并保留全部设置模块', () => {
    expect(settingsDialog).toMatch(/name="speed"[\s\S]*?:disabled="!isEdit"/)
    expect(settingsDialog).toMatch(/name="pathManagement"[\s\S]*?:disabled="!isEdit"/)
    expect(settingsDialog).toMatch(/name="tagManagement"[\s\S]*?:disabled="!isEdit"/)
    expect(settingsDialog).toContain('<speed-settings-tab')
    expect(settingsDialog).toContain('<path-management-tab')
    expect(settingsDialog).toContain('<tag-management-tab')
    expect(settingsDialog).toContain('<template-selection-dialog')
  })

  it('prevents async detail hydration from triggering validation while preserving submit validation', () => {
    expect(settingsDialog).toContain(':validate-on-rule-change="false"')
    expect(settingsDialog).toContain('@opened="handleDialogOpened"')
    expect(settingsDialog).toContain('this.basicFormRef.clearValidate()')
    expect(settingsDialog).toContain('await this.basicFormRef.validate()')
  })

  it('allows edit-mode connection tests to use the saved password while requiring a password for new downloaders', () => {
    expect(settingsDialog).toContain('hasCompleteConnectionInfo(this.formData, this.isEdit)')
    expect(settingsDialog).toContain('password: this.formData.password')
  })

  it('passes detail-hydrated path mapping rules through to the save payload', () => {
    expect(settingsDialog).toContain(':path-mapping-rules="formData.path_mapping_rules"')
    expect(pathManagementTab).toContain(':path-mapping-rules="pathMappingRules"')
    expect(pathMappingTab).toContain('@Prop({ default: undefined }) pathMappingRules!: string | undefined')
    expect(pathMappingTab).toContain('this.pathMappingRules !== undefined')
    expect(pathMappingTab).toContain('generateExternalPathFromRules(internalPath, rulesText)')
    expect(pathMappingTab).toContain('const processedMappings = this.mappings.map(mapping => {')
    expect(pathMappingTab).toContain('external: generatedExternal')
    expect(pathMappingTab).toContain('外部路径不能为空（无法根据 path_mapping_rules 自动生成，请手动填写）')
    expect(settingsDialog).toMatch(/const pathMappingData[\s\S]*basicData\['path_mapping'\] = pathMappingData/)
  })

  it('keeps scheduled speed controls shrinkable and stacks them on narrow viewports', () => {
    expect(speedSettingsTab).toContain('grid-template-columns: repeat(2, minmax(0, 1fr));')
    expect(speedSettingsTab).toContain('class="speed-value-input"')
    expect(speedSettingsTab).toContain('class="speed-unit-select"')
    expect(speedSettingsTab).toMatch(/\.speed-value-input\s*\{[\s\S]*?flex: 1 1 0;[\s\S]*?width: 0;[\s\S]*?min-width: 0;/)
    expect(speedSettingsTab).toMatch(/\.speed-unit-select\s*\{[\s\S]*?flex: 0 1 100px;[\s\S]*?min-width: 0;[\s\S]*?max-width: 100%;/)
    expect(speedSettingsTab).toContain('grid-template-columns: minmax(0, 1fr);')
    expect(speedSettingsTab).toContain('style="width: 100%;"')
  })
})

describe.each(lucideOnlySurfaces)('%s 图标契约', (_path, template) => {
  it('模板不直接绘制 SVG、不引用 Element 图标且不含表情符号', () => {
    expect(template).not.toContain('<svg')
    expect(template).not.toContain('el-icon-')
    expect(template).not.toMatch(/[\u{1F300}-\u{1FAFF}\u{2600}-\u{27BF}]/u)
  })
})

describe('全局导航 Lucide 化', () => {
  it('路由元数据使用 Lucide 名称且侧栏不再消费旧 svg-icon', () => {
    expect(routerSource).toContain("icon: 'layout-dashboard'")
    expect(routerSource).toContain("icon: 'server'")
    expect(routerSource).toContain("icon: 'download'")
    expect(routerSource).toContain("icon: 'panels-top-left'")

    const sidebarItem = readSource('layout/components/Sidebar/SidebarItem.vue')
    expect(sidebarItem).toContain('<LucideIcon')
    expect(sidebarItem).not.toContain('<svg-icon')
  })
})
