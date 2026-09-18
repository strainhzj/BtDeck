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

/**
 * 错误契约文案（errors 组，P2 批含 M1 子集）。
 * byCode 键 = 后端 data.reasonCode 的 camelCase 形态；未命中走 generic 兜底。
 * 前端禁止按中文 msg 匹配（主计划 §3.3）。
 */
export const errors = {
  generic: '操作失败',
  network: {
    unavailable: '网络连接失败，请检查网络连接',
    generic: '网络错误'
  },
  byCode: {
    authRateLimited: '尝试次数过多，请稍后再试',
    authInvalidCredentials: '用户名或密码错误',
    authTotpRequired: '请填写两步验证码',
    authTotpInvalid: '验证码错误，请重试',
    authInternal: '系统异常，请稍后重试',
    authRefreshInvalid: '登录状态已过期，请重新登录',
    userNotFound: '用户不存在',
    userOrigPasswordInvalid: '原密码错误',
    userPasswordUpdateFailed: '密码修改失败，请稍后重试',
    twofaForbidden: '无权操作其他用户的2FA设置',
    twofaInvalidOperation: '无效的2FA操作',
    twofaAlreadyEnabled: '用户已启用双因素认证，无需重复绑定',
    twofaPasswordRequired: '停用双因素认证需要提供当前密码',
    twofaPasswordInvalid: '密码错误',
    twofaTotpRequired: '停用双因素认证需要提供双因素验证码',
    twofaTotpInvalid: '双因素验证码错误',
    downloaderAuthFailed: '下载器拒绝了用户名或密码',
    downloaderNotFound: '该下载器已被删除或不存在',
    downloaderOrigPasswordRequired: '修改用户名或密码时必须提供原密码',
    downloaderOrigPasswordInvalid: '原密码错误',
    downloaderOrigPasswordUnverified: '无法验证原密码，请稍后重试',
    downloaderTestFailed: '测试连接失败',
    downloaderDbQueryFailed: '数据库查询失败，请稍后重试'
  }
}
