/**
 * dashboardLayout 纯函数单测（仪表盘一期 W2/W5）。
 *
 * 覆盖：预设可见性、宽度循环（3/4/6/8/12）、localStorage 解析宽容性
 * （损坏 JSON/未知 id/非法 span 回退）、保存-读取 roundtrip、恢复默认。
 */
import {
  DashboardLayoutState,
  DEFAULT_ORDER,
  DEFAULT_SPANS,
  STORAGE_KEY,
  WIDTH_CYCLE,
  WidgetId,
  clearLayout,
  defaultLayout,
  loadLayout,
  nextWidth,
  parseLayout,
  saveLayout,
  visibleWidgetIds
} from '@/views/dashboard/components/dashboardLayout'

function makeStorage(): { getItem: (k: string) => string | null; setItem: (k: string, v: string) => void; removeItem: (k: string) => void } {
  const store = new Map<string, string>()
  return {
    getItem: k => (store.has(k) ? (store.get(k) as string) : null),
    setItem: (k, v) => store.set(k, v),
    removeItem: k => store.delete(k)
  }
}

describe('visibleWidgetIds 预设可见性', () => {
  it('overview 显示 9 张卡（不含 radar/tubes/hero）', () => {
    const vis = visibleWidgetIds('overview')
    expect(vis).toHaveLength(9)
    expect(vis).not.toContain('hero')
    expect(vis).not.toContain('radar')
    expect(vis).not.toContain('tubes')
  })

  it('focus/pulse 按示意图档位', () => {
    expect(visibleWidgetIds('focus')).toEqual(['hero', 'hot', 'spark', 'health'])
    expect(visibleWidgetIds('pulse')).toEqual(['radar', 'tubes', 'spark', 'health', 'hero'])
  })

  it('custom 显示全部 12 张（无二期 issues 卡）', () => {
    const vis = visibleWidgetIds('custom')
    expect(vis).toHaveLength(12)
    expect(vis).not.toContain('issues' as unknown as WidgetId)
  })
})

describe('nextWidth 宽度循环', () => {
  it('按 3→4→6→8→12→3 循环', () => {
    expect(nextWidth(3)).toBe(4)
    expect(nextWidth(4)).toBe(6)
    expect(nextWidth(6)).toBe(8)
    expect(nextWidth(8)).toBe(12)
    expect(nextWidth(12)).toBe(3)
  })

  it('非法当前值回退 6 的下一档（8）', () => {
    expect(nextWidth(5)).toBe(8)
    expect(nextWidth(0)).toBe(8)
  })
})

describe('parseLayout / loadLayout 宽容解析', () => {
  it('损坏 JSON 返回 null', () => {
    expect(parseLayout('{not-json')).toBeNull()
    expect(parseLayout(null)).toBeNull()
    expect(parseLayout('42')).toBeNull()
  })

  it('未知 id 丢弃、缺失卡回填默认末尾', () => {
    const state = parseLayout(
      JSON.stringify({ order: ['health', 'bogus-widget', 'hot'], spans: {}, preset: 'overview' })
    )
    expect(state).not.toBeNull()
    expect(state?.order).not.toContain('bogus-widget' as unknown as WidgetId)
    for (const id of DEFAULT_ORDER) {
      expect(state?.order).toContain(id)
    }
    expect(state?.order[0]).toBe('health')
    expect(state?.order[1]).toBe('hot')
  })

  it('非法 span（不在循环档位）被剔除', () => {
    const state = parseLayout(
      JSON.stringify({ order: ['health', 'hot'], spans: { health: 7, hot: 12 }, preset: 'custom' })
    )
    expect(state?.spans.health).toBeUndefined()
    expect(state?.spans.hot).toBe(12)
  })

  it('非法 preset 回退 overview', () => {
    const state = parseLayout(JSON.stringify({ order: ['health'], spans: {}, preset: 'hacker' }))
    expect(state?.preset).toBe('overview')
  })

  it('save → load roundtrip 保持顺序/列宽/预设', () => {
    const storage = makeStorage()
    const state: DashboardLayoutState = {
      order: ['hero', 'health'],
      spans: { hero: 12, health: 3 },
      preset: 'focus'
    }
    saveLayout(storage, state)
    expect(storage.getItem(STORAGE_KEY)).not.toBeNull()
    const loaded = loadLayout(storage)
    expect(loaded?.order.slice(0, 2)).toEqual(['hero', 'health'])
    expect(loaded?.spans.hero).toBe(12)
    expect(loaded?.spans.health).toBe(3)
    expect(loaded?.preset).toBe('focus')
  })

  it('clearLayout 后 loadLayout 返回 null', () => {
    const storage = makeStorage()
    saveLayout(storage, defaultLayout())
    clearLayout(storage)
    expect(loadLayout(storage)).toBeNull()
  })

  it('defaultLayout 返回完整默认（12 卡 + 全默认列宽 + overview）', () => {
    const d = defaultLayout()
    expect(d.order).toEqual([...DEFAULT_ORDER])
    expect(d.spans).toEqual({ ...DEFAULT_SPANS })
    expect(d.preset).toBe('overview')
    expect(WIDTH_CYCLE).toEqual([3, 4, 6, 8, 12])
  })
})
