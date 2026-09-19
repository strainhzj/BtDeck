/*
 * Copyright (C) 2025 BTDeck Contributors
 *
 * This program is free software: you can redistribute it and/or modify
 * it under the terms of the GNU General Public License as published by
 * the Free Software Foundation, either version 3 of the License, or
 * (at your option) any later version.
 *
 * This program is distributed in the hope that it will be useful,
 * but WITHOUT ANY WARRANTY; without even the implied warranty of
 * MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
 * GNU General Public License for more details.
 *
 * You should have received a copy of the GNU General Public License
 * along with this program.  If not, see <https://www.gnu.org/licenses/>.
 */

/** 登录与会话（auth 组，P2 首次使用闭环）。 */
export const auth = {
  subtitle: '统一管理您的下载器',
  usernamePlaceholder: '用户名',
  passwordPlaceholder: '密码',
  twofaPlaceholder: '双因素验证码（如有设置必须填写）',
  rememberMe: '记住我',
  forgotPassword: '忘记密码？',
  loggingIn: '登录中...',
  login: '登录',
  loginSuccess: '登录成功',
  loginFailed: '登录失败，请重试',
  enterDemo: '进入演示模式',
  demoEntered: '已进入演示模式',
  noAccount: '还没有账号？',
  registerNow: '立即注册',
  tokenMissing: '令牌为空，请重新登录',
  /* ↓ 双语遗留补译：user store Login/GetUserInfo 抛出文案 */
  noAccessToken: '登录失败：未获取到访问令牌',
  tokenEmpty: 'Token为空，请重新登录',
  getUserInfoFailed: '获取用户信息失败',
  getUserInfoFailedRelogin: '获取用户信息失败，请重新登录',
  validation: {
    username: '请输入正确的用户名',
    passwordMin: '密码长度不能少于5位',
    twofaDigits: '双因素验证码必须是6位数字'
  }
}
