<script lang="ts">
/**
 * LucideIcon —— 轻量 Vue 2 包装器，统一渲染 Lucide 图标。
 *
 * 设计要点（经实测 lucide@1.27.0 IconNode 形状）：
 * - 每个 Lucide 图标导出为 IconNode = [child, ...]，child = [tag, attrs] 或 [tag, attrs, children]。
 * - 不使用 lucide 内置 createElement（其内部调用 document.createElementNS，仅适浏览器 DOM，
 *   Vue 2 的 render(h) 需要的是 VNode 而非 DOM 节点）。
 * - 此处仅静态具名导入本项目用到的图标，webpack 5 + sideEffects 自动 tree-shake，
 *   只打包用到的那几个图标，避免整个 ~2000 图标集入包。
 * - stroke 跟随 currentColor，size/strokeWidth 通过 prop 透传，主题切换自然生效。
 */
import Vue from 'vue'
import { Component, Prop } from 'vue-property-decorator'
import {
  Search,
  Plus,
  SlidersHorizontal,
  CheckCheck,
  Square,
  ListChecks,
  Trash2,
  ClipboardPaste,
  ArrowUpDown,
  ArrowUp,
  ArrowDown,
  X,
  Play,
  Pause,
  RefreshCw,
  FolderOpen,
  Settings,
  BarChart3,
  ChevronLeft,
  ChevronRight,
  ChevronUp,
  RotateCcw,
  TrendingUp,
  TrendingDown,
  Clock,
  AlertTriangle,
  HelpCircle,
  Activity,
  Inbox,
  Server,
  Folder,
  Tag,
  Tags,
  Circle,
  Network,
  Waypoints,
  LayoutDashboard,
  Download,
  List,
  Timer,
  Link,
  PanelsTopLeft,
  Wrench,
  FileText,
  FolderSearch,
  ChevronsLeft,
  ChevronsRight,
  MessageCircle,
  Bell,
  UserRound,
  ChevronDown,
  House,
  LogOut,
  Check,
  Palette,
  ShieldCheck,
  ShieldOff,
  Upload,
  Radio,
  Zap,
  Gauge,
  Route,
  LockKeyhole,
  Power,
  Database,
  FolderCog,
  Info,
  CircleCheckBig,
  CircleX,
  LayoutTemplate,
  Save,
  ExternalLink,
  Wifi,
  WifiOff,
  EllipsisVertical,
  Eye,
  Pencil,
  HardDrive,
  Monitor,
  Container,
  PanelLeftClose,
  PanelLeftOpen,
  BadgeCheck,
  Cable,
  KeyRound,
  Orbit,
  SearchX,
  Copy,
  FolderSync,
  TestTube2,
  Sparkles,
  PlugZap,
  Tags,
  ClipboardList,
  Forward,
  FileUp,
  CalendarDays,
  CalendarRange,
  ArrowDownAZ,
  ListFilter,
  WandSparkles,
  ArrowLeft
} from 'lucide'

// Lucide 默认根 <svg> 属性（与 lucide 源码 defaultAttributes 一致）。
const DEFAULT_ATTRS: Record<string, string | number> = {
  xmlns: 'http://www.w3.org/2000/svg',
  width: 24,
  height: 24,
  viewBox: '0 0 24 24',
  fill: 'none',
  stroke: 'currentColor',
  'stroke-width': 2,
  'stroke-linecap': 'round',
  'stroke-linejoin': 'round'
}

// 仅注册本项目实际使用的图标；新增图标时在此补一行具名导入 + 注册项即可。
const ICONS: Record<string, unknown> = {
  search: Search,
  plus: Plus,
  'sliders-horizontal': SlidersHorizontal,
  'check-check': CheckCheck,
  square: Square,
  'list-checks': ListChecks,
  trash: Trash2,
  'clipboard-paste': ClipboardPaste,
  'arrow-up-down': ArrowUpDown,
  'arrow-up': ArrowUp,
  'arrow-down': ArrowDown,
  x: X,
  play: Play,
  pause: Pause,
  'refresh-cw': RefreshCw,
  'folder-open': FolderOpen,
  settings: Settings,
  'bar-chart-3': BarChart3,
  'chevron-left': ChevronLeft,
  'chevron-right': ChevronRight,
  'chevron-up': ChevronUp,
  'rotate-ccw': RotateCcw,
  'trending-up': TrendingUp,
  'trending-down': TrendingDown,
  clock: Clock,
  'alert-triangle': AlertTriangle,
  'help-circle': HelpCircle,
  activity: Activity,
  inbox: Inbox,
  server: Server,
  folder: Folder,
  tag: Tag,
  tags: Tags,
  circle: Circle,
  network: Network,
  waypoints: Waypoints,
  'layout-dashboard': LayoutDashboard,
  download: Download,
  list: List,
  timer: Timer,
  link: Link,
  'panels-top-left': PanelsTopLeft,
  wrench: Wrench,
  'file-text': FileText,
  'folder-search': FolderSearch,
  'chevrons-left': ChevronsLeft,
  'chevrons-right': ChevronsRight,
  'message-circle': MessageCircle,
  bell: Bell,
  'user-round': UserRound,
  'chevron-down': ChevronDown,
  house: House,
  'log-out': LogOut,
  check: Check,
  palette: Palette,
  'shield-check': ShieldCheck,
  'shield-off': ShieldOff,
  upload: Upload,
  radio: Radio,
  zap: Zap,
  gauge: Gauge,
  route: Route,
  'lock-keyhole': LockKeyhole,
  power: Power,
  database: Database,
  'folder-cog': FolderCog,
  info: Info,
  'circle-check-big': CircleCheckBig,
  'circle-x': CircleX,
  'layout-template': LayoutTemplate,
  save: Save,
  'external-link': ExternalLink,
  wifi: Wifi,
  'wifi-off': WifiOff,
  'ellipsis-vertical': EllipsisVertical,
  eye: Eye,
  pencil: Pencil,
  'hard-drive': HardDrive,
  monitor: Monitor,
  container: Container,
  'panel-left-close': PanelLeftClose,
  'panel-left-open': PanelLeftOpen,
  'badge-check': BadgeCheck,
  cable: Cable,
  'key-round': KeyRound,
  orbit: Orbit,
  'search-x': SearchX,
  copy: Copy,
  'folder-sync': FolderSync,
  'test-tube-2': TestTube2,
  sparkles: Sparkles,
  'plug-zap': PlugZap,
  'trash-2': Trash2,
  tags: Tags,
  'clipboard-list': ClipboardList,
  forward: Forward,
  'file-up': FileUp,
  'calendar-days': CalendarDays,
  'calendar-range': CalendarRange,
  'arrow-down-a-z': ArrowDownAZ,
  'list-filter': ListFilter,
  'wand-sparkles': WandSparkles,
  'arrow-left': ArrowLeft
}

// IconNode 子节点：[tag, attrs] 或 [tag, attrs, children]
type IconChild = [string, Record<string, string | number>, IconChild[]?]

@Component({ name: 'LucideIcon' })
export default class LucideIcon extends Vue {
  @Prop({ type: String, required: true }) name!: string
  @Prop({ type: Number, default: 24 }) size!: number
  @Prop({ type: [String, Number], default: 2 }) strokeWidth!: string | number
  @Prop({ type: String, default: '' }) color!: string

  private get iconNode(): IconChild[] | null {
    const node = ICONS[this.name] as IconChild[] | undefined
    return node && Array.isArray(node) ? node : null
  }

  get wrapperStyle(): Record<string, string> {
    // 让外层 span 占据图标尺寸并继承 currentColor，方便布局对齐。
    const style: Record<string, string> = {
      display: 'inline-flex',
      alignItems: 'center',
      justifyContent: 'center',
      width: `${this.size}px`,
      height: `${this.size}px`,
      lineHeight: 0
    }
    if (this.color) {
      style.color = this.color
    }
    return style
  }

  // 将 IconNode 子节点递归映射为 Vue 2 VNode。
  private renderChild(h: typeof Vue.prototype.$createElement, child: IconChild) {
    const [tag, attrs, children] = child
    return h(
      tag,
      { attrs: { ...attrs } },
      Array.isArray(children) ? children.map((c) => this.renderChild(h, c)) : undefined
    )
  }

  render(h: typeof Vue.prototype.$createElement) {
    const node = this.iconNode
    if (!node) {
      // 未知图标：渲染空 span，避免整棵树崩溃。
      return h('span', { class: 'lucide-icon lucide-icon--missing' })
    }

    const rootAttrs: Record<string, string | number> = {
      ...DEFAULT_ATTRS,
      width: this.size,
      height: this.size,
      'stroke-width': this.strokeWidth,
      // stroke 始终跟随 currentColor 以支持主题与悬停态着色。
      stroke: 'currentColor'
    }

    const svgVNode = h(
      'svg',
      {
        attrs: rootAttrs,
        class: 'lucide-icon__svg'
      },
      node.map((child) => this.renderChild(h, child))
    )

    return h(
      'span',
      {
        class: 'lucide-icon',
        style: this.wrapperStyle,
        attrs: { 'aria-hidden': 'true' }
      },
      [svgVNode]
    )
  }
}
</script>

<style lang="scss" scoped>
.lucide-icon {
  pointer-events: none;
  user-select: none;
  vertical-align: middle;
  flex-shrink: 0;

  &__svg {
    display: block;
    width: 100%;
    height: 100%;
  }

  &--missing {
    // 未知图标占位：1px 虚线圆角框，仅在开发期可视。
    outline: 1px dashed var(--color-text-quaternary, #d1d5db);
    outline-offset: -1px;
    border-radius: var(--radius-sm, 4px);
  }
}
</style>
