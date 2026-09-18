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

/** 系统设置 M1 范围（2FA / 修改密码 / 状态诊断；主机能力页签 M2）。 */
export const settings = {
  tabs: {
    twofa: '双因素认证',
    password: '修改密码',
    platform: '主机能力',
    diagnosis: '状态诊断'
  },
  twofa: {
    title: '双因素认证',
    statusEnabled: '已启用',
    enabledDesc: '您的双因素认证当前处于 {status} 状态。停用后账户安全性将降低，建议仅在必要时停用。',
    currentPassword: '当前密码',
    currentPasswordPlaceholder: '请输入当前密码',
    twofaCode: '双因素验证码',
    twofaCodePlaceholder: '请输入认证器中的6位验证码',
    locked: '已锁定',
    lockedVerifyDesc: '验证失败次数过多，已被锁定。',
    lockedPasswordDesc: '密码验证失败次数过多，已被锁定。',
    retryAfterSeconds: '请在 {seconds} 秒后重试。',
    attemptsWarning: '已失败 {failed} 次，还剩 {remaining} 次机会',
    disable: '停用双因素认证',
    verifyPasswordStepDesc: '为保护账户安全，开启双因素认证前需先验证当前密码。',
    verifyPassword: '验证密码',
    verifySuccess: '密码验证成功',
    verifyFailed: '验证失败',
    passwordWrong: '密码错误',
    lockedFiveMinutes: '密码错误次数过多，已被锁定5分钟',
    lockedAttemptsFiveMinutes: '验证失败次数过多，已被锁定5分钟',
    scanDesc: '请使用认证器应用（如 Google Authenticator、Authy）扫描下方二维码，然后输入应用中显示的6位验证码以完成绑定。',
    qrGenerating: '生成二维码中...',
    manualEntryHint: '当前环境不支持生成二维码（缺少图像依赖），请在认证器应用中选择「手动输入密钥」并录入：',
    copySecret: '复制密钥',
    secretCopied: '密钥已复制',
    copyFailed: '复制失败，请长按/选中密钥手动复制',
    manualEntryMeta: '账户名：{account} · 密钥类型：基于时间（TOTP）· 位数：6 位 · 更新周期：30 秒',
    code: '验证码',
    codePlaceholder: '请输入6位验证码',
    codeRequired: '请输入6位验证码',
    codeInvalid: '验证码错误，请重试',
    userInfoFailed: '用户信息获取失败，请重新登录',
    confirmBinding: '确认绑定',
    bindSuccess: '双因素认证启用成功',
    bindSuccessDesc: '您的账户现在更安全了，下次登录时需要输入验证码。',
    bindFailed: '绑定失败',
    usageTitle: '使用步骤：',
    stepDownload: '下载认证器应用（如 Google Authenticator、Authy）',
    stepScan: '扫描上方二维码',
    stepManual: '手动输入上方密钥完成添加',
    stepInput: '输入应用中显示的6位验证码',
    stepConfirm: '点击“确认绑定”完成设置',
    backupSecretTitle: '备份密钥（重要！）：',
    backupSecretWarning: '⚠️ 密钥只会显示一次，请将此密钥保存在安全的地方，如果丢失认证器应用，可以使用此密钥恢复。',
    closeSecretTitle: '确认关闭',
    closeSecretConfirm: '关闭后将无法再次查看此密钥，是否确认关闭？',
    closed: '已关闭',
    disableConfirmTitle: '确认停用双因素认证',
    disableConfirm: '停用双因素认证后，账户安全性将降低。是否继续停用？',
    confirmDisable: '确认停用',
    disableSuccess: '双因素认证已停用',
    fieldsRequired: '请填写当前密码和双因素验证码',
    codeMustBeSixDigits: '双因素验证码必须是6位数字',
    passwordRequired: '请输入密码'
  },
  password: {
    title: '修改密码',
    desc: '定期修改密码可以保护账户安全，建议使用强密码。',
    oldPassword: '旧密码',
    oldPasswordPlaceholder: '请输入旧密码',
    newPassword: '新密码',
    newPasswordPlaceholder: '请输入新密码',
    confirmPassword: '确认密码',
    confirmPasswordPlaceholder: '请再次输入新密码',
    mismatch: '两次输入的密码不一致',
    confirm: '确认修改',
    success: '密码修改成功，请使用新密码重新登录',
    failed: '密码修改失败',
    userInfoFailed: '用户信息获取失败，请重新登录'
  },
  diagnosis: {
    title: '故障转储与状态分析',
    desc: '一键生成诊断快照并导出为 JSON 文件，用于故障排查或状态分析。内容包含服务版本与构建身份、数据库/事件循环/同步任务健康检查、下载器离线告警与进程内存采样；不包含任何凭据或令牌。',
    generating: '正在生成…',
    export: '生成并导出诊断文件',
    exported: '诊断文件已导出',
    failed: '导出诊断文件失败，请稍后重试'
  }
}
