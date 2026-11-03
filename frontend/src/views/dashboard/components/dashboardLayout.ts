/**
 * 仪表盘布局状态纯函数（仪表盘风格改造一期 W2）。
 *
 * 职责：widget 清单/默认顺序与列宽、预设档位可见性、宽度循环、
 * localStorage 持久化（load/save/reset）。组件层（DashboardGrid）与页面层
 * （index.vue）都只消费这里的常量与纯函数，便于单测。
 *
 * 持久化口径（计划 v2）：一期仅 localStorage，多标签页不做实时同步，
 * 行为注明为「最后保存者生效」；账号级同步属二期（新表，缓行）。
 */

/** 一期 widget 全集（示意图 13 卡去掉二期缓行的 issues 异常待办） */
export type WidgetId =
  | 'health'
  | 'spark'
  | 'statusPie'
  | 'traffic'
  | 'sites'
  | 'hot'
  | 'tasks'
  | 'activity'
  | 'quick'
  | 'radar'
  | 'tubes'
  | 'hero'

export type PresetKey = 'overview' | 'focus' | 'pulse' | 'custom'

export interface WidgetLayout {
  order: WidgetId[]
  spans: Partial<Record<WidgetId, number>>
}

export interface DashboardLayoutState extends WidgetLayout {
  preset: PresetKey
}

/** 编辑模式宽度循环档位（计划 v2：3/4/6/8/12 列循环） */
export const WIDTH_CYCLE: readonly number[] = [3, 4, 6, 8, 12]

/** 默认布局：顺序对齐示意图（issues 二期不入列） */
export const DEFAULT_ORDER: readonly WidgetId[] = [
  'health',
  'spark',
  'statusPie',
  'traffic',
  'sites',
  'hot',
  'tasks',
  'activity',
  'quick',
  'radar',
  'tubes',
  'hero'
]

export const DEFAULT_SPANS: Readonly<Record<WidgetId, number>> = {
  health: 6,
  spark: 6,
  statusPie: 3,
  traffic: 5,
  sites: 4,
  hot: 5,
  tasks: 3,
  activity: 4,
  quick: 5,
  radar: 4,
  tubes: 3,
  hero: 12
}

/** 预设档位可见卡清单（custom = 全部显示；对齐示意图 PRESETS） */
export const PRESET_WIDGETS: Readonly<Record<Exclude<PresetKey, 'custom'>, readonly WidgetId[]>> = {
  overview: ['health', 'spark', 'statusPie', 'traffic', 'sites', 'hot', 'tasks', 'activity', 'quick'],
  focus: ['hero', 'hot', 'spark', 'health'],
  pulse: ['radar', 'tubes', 'spark', 'health', 'hero']
}

/** widget 元数据：标题 i18n 键后缀 / 图标 / 角标（live=实时脉冲类） */
export interface WidgetMeta {
  icon: string
  live?: boolean
  /** 角标类型：live 实时点 / presetTag 预设归属提示（脉冲/聚焦） */
  presetTag?: 'focus' | 'pulse'
}

export const WIDGET_META: Readonly<Record<WidgetId, WidgetMeta>> = {
  health: { icon: 'server', live: true },
  spark: { icon: 'activity', live: true },
  statusPie: { icon: 'pie-chart' },
  traffic: { icon: 'bar-chart-3' },
  sites: { icon: 'globe' },
  hot: { icon: 'flame' },
  tasks: { icon: 'clock' },
  activity: { icon: 'history' },
  quick: { icon: 'zap' },
  radar: { icon: 'radar', presetTag: 'pulse' },
  tubes: { icon: 'gauge', presetTag: 'pulse' },
  hero: { icon: 'waves', live: true, presetTag: 'focus' }
}

export const STORAGE_KEY = 'btdeck.dashboard.layout.v1'

function isWidgetId(v: unknown): v is WidgetId {
  return typeof v === 'string' && Object.prototype.hasOwnProperty.call(WIDGET_META, v)
}

/** 预设 → 可见集合（custom 全部可见） */
export function visibleWidgetIds(preset: PresetKey): WidgetId[] {
  if (preset === 'custom') {
    return [...DEFAULT_ORDER]
  }
  const list = PRESET_WIDGETS[preset]
  return list ? [...list] : [...DEFAULT_ORDER]
}

/** 宽度循环：当前值在 3/4/6/8/12 中取下一档；非法当前值回退到 6 的下一档 */
export function nextWidth(current: number): number {
  const normalized = WIDTH_CYCLE.includes(current) ? current : 6
  const idx = WIDTH_CYCLE.indexOf(normalized)
  return WIDTH_CYCLE[(idx + 1) % WIDTH_CYCLE.length]
}

/** 解析持久化布局：宽容解析（未知 id 丢弃、缺失项回填默认、损坏回默认整包） */
export function parseLayout(raw: string | null): DashboardLayoutState | null {
  if (!raw) return null
  let parsed: unknown
  try {
    parsed = JSON.parse(raw)
  } catch {
    return null
  }
  if (typeof parsed !== 'object' || parsed === null) return null
  const obj = parsed as { order?: unknown, spans?: unknown, preset?: unknown }
  if (!Array.isArray(obj.order)) return null
  const order = obj.order.filter(isWidgetId)
  if (order.length === 0) return null
  // 回填持久化缺失的新卡（版本演进兜底）：追加在末尾
  for (const id of DEFAULT_ORDER) {
    if (!order.includes(id)) order.push(id)
  }
  const spans: Partial<Record<WidgetId, number>> = {}
  if (typeof obj.spans === 'object' && obj.spans !== null) {
    for (const [k, v] of Object.entries(obj.spans as Record<string, unknown>)) {
      if (isWidgetId(k) && typeof v === 'number' && WIDTH_CYCLE.includes(v)) {
        spans[k] = v
      }
    }
  }
  const preset: PresetKey =
    obj.preset === 'overview' || obj.preset === 'focus' || obj.preset === 'pulse' || obj.preset === 'custom'
      ? obj.preset
      : 'overview'
  return { order, spans, preset }
}

/** localStorage 读取（storage 注入便于测试）；损坏/缺失返回 null */
export function loadLayout(storage: Pick<Storage, 'getItem'>): DashboardLayoutState | null {
  return parseLayout(storage.getItem(STORAGE_KEY))
}

/** 默认布局（preset 归位 overview） */
export function defaultLayout(): DashboardLayoutState {
  return { order: [...DEFAULT_ORDER], spans: { ...DEFAULT_SPANS }, preset: 'overview' }
}

/** localStorage 写入：不做跨标签页同步，最后保存者生效（见模块头注释） */
export function saveLayout(storage: Pick<Storage, 'setItem'>, state: DashboardLayoutState): void {
  try {
    storage.setItem(STORAGE_KEY, JSON.stringify({ order: state.order, spans: state.spans, preset: state.preset }))
  } catch {
    // 隐私模式/容量满：静默降级为会话内布局（下次进入回默认）
  }
}

/** 移除持久化（恢复默认） */
export function clearLayout(storage: Pick<Storage, 'removeItem'>): void {
  try {
    storage.removeItem(STORAGE_KEY)
  } catch {
    // 同上，静默
  }
}
