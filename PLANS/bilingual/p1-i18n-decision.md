# P1 依赖选型与维护风险记录（desktop-bilingual-20260918.p1）

> 记录：2026-09-18。对应主计划 §3.1「P1 验证 Vue 2 兼容国际化方案……选型时核对安全及维护状态并记录结论，不直接安装最新版」。

## 结论

**选型 vue-i18n@8.28.2（精确钉版，无 `^`），已于 2026-09-18 安装进 `frontend/package.json`。**

## 选型过程

| 候选 | 结论 |
|---|---|
| **vue-i18n@8.28.2** | ✅ 采用。v8 线终版（v8 系列最后一个维护版本），Vue 2.6 官方配套，Legacy API（`new VueI18n()` + `$t`），与现有 Options API / vue-property-decorator 风格零冲突 |
| vue-i18n@9/10/11（latest 线） | ❌ 仅支持 Vue 3（需要的 API 面完全不同），采用即框架升级，违反「不升级框架」边界 |
| 自研迷你 i18n | ❌ 复数/插值/回退链/缺译告警的自维护成本高于依赖风险；且 Element UI 集成（`ElementLocale.i18n`）按 vue-i18n 语义设计，自研反而要适配两层 |

## 维护与安全状态（风险登记）

- **v8 线已停止维护**（官方文档声明 v8 为遗留线，维护重心在 v9+）：不会再有安全补丁。这是已接受的风险，依据如下：
  - 运行面小：i18n 库不接触网络、不解析不可信输入，主要攻击面（消息内容）全部来自仓内静态文件；
  - **精确钉版** `8.28.2`（本次安装 `npm install --save-exact`），supply-chain 面冻结，依赖升级必须显式改 package.json 并过评审；
  - **单封装层缓解**：非组件层翻译全部经 `src/i18n/index.ts` 的 `translate/translateChoice/setLocale`，组件层只消费 `$t/$tc`——如未来需换引擎（含应对安全事件），改动收敛在 `src/i18n/` 一个目录；
  - **最小 API 面**：仅使用 `t / tc / locale / fallbackLocale / messages / missing`，未用 `d/n/自定义 formatter/directive/component 插槽` 等 v8 深水区 API。
- `npm audit`（2026-09-18）：安装后无指向 vue-i18n 的已知告警（仓内存量 audit 项与本依赖无关，另行归属）。

## P1 落地范围与门禁

- 新增 `frontend/src/i18n/`（types / index / element-locale.d.ts / locales/{zh-CN,en}/{navigation,time,index}）。
- 接线：main.ts（Element Locale 挂接 + 根实例注入）、router.ts（19 条桌面路由 `titleKey`，移动路由不动）、permission.ts（document.title 走 resolvePageTitle）、app store（language 状态 + SetLanguage 动作）、Navbar / 登录页（语言切换入口，自名常量，切换后显式刷新标题）、formatters.ts（相对时间七档）。
- 语言顺序：手动偏好（localStorage `btdeck-lang`）→ 浏览器语言顺序匹配（en\*→en、zh\*→zh-CN）→ 默认中文；无效存储值清除回退。
- 缺译策略：en 缺键回退 zh-CN；zh-CN 缺键（异常）返回空串 + console.warn，不渲染原始键；键集合/插值参数/复数支数一致性由 `i18n-message-parity.spec.ts` 门禁钉死（`el` 子树为 Element 官方语言包 vendor 数据，存在官方键漂移如 en 独有 `el.datepicker.week`，不在门禁范围）。
- 已知边界：Element UI 下拉菜单挂 body（popper），Navbar `.lang-active` 高亮类暂无样式作用域可达——纯视觉项，P5/P7 视觉验收统一处理。

## 验证（2026-09-18）

typecheck ✓；lint（contract:check + eslint --max-warnings 0 + vuex-action）✓；全量 Jest **115 套件 / 1622 用例全绿**（基线 112/1598，新增 i18n-message-parity / i18n-locale / navbar-language-switcher 共 24 用例 + shared-utils 钉语言，零回归）；`npm run build` ✓。
