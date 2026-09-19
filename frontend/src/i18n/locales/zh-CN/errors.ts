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
 * 错误契约文案（errors 组：P2 批 M1 子集 + P4 批扩展）。
 * byCode 键 = 后端 data.reasonCode 的 camelCase 形态；未命中走 generic 兜底。
 * 前端禁止按中文 msg 匹配（主计划 §3.3）。
 */
export const errors = {
  generic: '操作失败',
  network: {
    unavailable: '网络连接失败，请检查网络连接',
    generic: '网络错误'
  },
  /** E17：422 字段校验按 pydantic type 字典化（field 为 loc 末段标识符） */
  validation: {
    missing: '必填参数缺失：{field}',
    tooShort: '参数项数不足：{field}',
    tooLong: '参数项数超出上限：{field}',
    stringType: '参数类型不正确：{field} 应为文本',
    intParsing: '参数类型不正确：{field} 应为整数',
    boolParsing: '参数类型不正确：{field} 应为布尔值',
    greaterThan: '参数取值过小：{field}',
    lessThan: '参数取值过大：{field}',
    valueError: '参数无效：{field}',
    generic: '请求参数校验失败（{field}）'
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
    downloaderDbQueryFailed: '数据库查询失败，请稍后重试',
    /* ↓ 双语 P4 扩展：种子操作 / Tracker / 查询模板 / 添加链路 */
    downloaderCacheUnavailable: '下载器缓存服务暂不可用，请稍后重试',
    downloaderOffline: '下载器已失效，请检查下载器状态后重试',
    downloaderConnectionMissing: '下载器连接不可用，请稍后重试',
    downloaderNoTorrents: '该下载器下没有种子',
    torrentHashesRequired: '请选择要操作的种子',
    torrentRecordsNotFound: '未找到任何种子记录',
    torrentOperationFailed: '种子操作失败，请稍后重试',
    torrentOperationInternal: '操作异常，请稍后重试',
    torrentFileRequired: '请选择种子文件',
    torrentFileInvalid: '种子文件无效或已损坏',
    torrentInfoTimeout: '获取种子信息超时，请检查下载器连接',
    torrentInfoUnavailable: '种子已提交，但暂时无法从下载器获取信息',
    torrentAddFailed: '添加种子失败，请稍后重试',
    torrentFilesRequired: '请至少选择一个种子文件',
    torrentStageFailed: '种子文件上传失败，请重试',
    torrentBatchSubmitFailed: '提交批量任务失败，请稍后重试',
    torrentSyncFailed: '同步失败，请稍后重试',
    trackerUrlRequired: '请填写 Tracker 地址',
    trackerNotFound: '未找到要替换的 Tracker',
    trackerOperationInternal: 'Tracker 操作异常，请稍后重试',
    searchTemplateNotFound: '查询模板不存在',
    searchTemplateForbidden: '无权操作此模板',
    searchTemplateInvalidConditions: '查询条件无效，请检查后重试',
    searchTemplateCreateFailed: '创建模板失败，请稍后重试',
    searchTemplateListFailed: '获取模板失败，请稍后重试',
    searchTemplateUpdateFailed: '更新模板失败，请稍后重试',
    searchTemplateDeleteFailed: '删除模板失败，请稍后重试',
    searchTemplateApplyFailed: '应用模板失败，请稍后重试',
    internalError: '服务器内部错误，请稍后重试',
    dbOperationFailed: '数据库操作失败，请稍后重试',
    /* ↓ 双语 P5 扩展：删除链路 / 回收站 */
    torrentDeleteAccepted: '批量删除任务已提交，正在后台执行',
    torrentDeleteAlreadyProcessed: '所选种子均已在删除任务中处理',
    torrentDeleteTaskNotFound: '删除任务不存在或已失效',
    torrentDeleteSubmitFailed: '提交删除任务失败，请稍后重试',
    torrentDeleteStatusQueryFailed: '查询删除任务状态失败，请稍后重试',
    torrentDeleteFailed: '删除种子失败，请稍后重试',
    torrentDeleteInvalidParams: '请求参数有误，请检查后重试',
    downloaderUnsupportedType: '不支持的下载器类型',
    downloaderAdapterInitFailed: '下载器适配器初始化失败，请稍后重试',
    recycleBinQueryFailed: '回收站查询失败，请稍后重试',
    recycleRestoreFailed: '还原种子失败，请稍后重试',
    recyclePreviewFailed: '清理预览失败，请稍后重试',
    recycleCleanupFailed: '清理回收站失败，请稍后重试',
    notImplemented: '该功能尚未开放，敬请期待'
  }
}
