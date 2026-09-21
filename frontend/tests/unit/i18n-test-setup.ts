/**
 * Jest 全局 setup：钉扎界面语言为 zh-CN（双语 P2）。
 *
 * jsdom 的 navigator.language 为 en-US；src/i18n 单例在模块 import 时按
 * 「手动偏好 > 浏览器语言」解析，无存储偏好时会解析出 en，导致运行时
 * 翻译类断言（request 层 toast / 守卫提示 / 组件 $t 渲染）漂移成英文。
 * 测试套件统一以中文为基准语言；需要其它语言的用例（i18n-locale.spec 的
 * 解析矩阵等）在自身内显式操作 localStorage，不受本 setup 影响。
 */
try {
  window.localStorage.setItem('btdeck-lang', 'zh-CN')
} catch {
  // 存储不可用时保持默认解析行为
}
