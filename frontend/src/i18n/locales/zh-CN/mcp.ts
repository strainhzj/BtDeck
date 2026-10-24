/*
 * Copyright (C) 2025 BTDeck Contributors
 *
 * This program is free software: you can redistribute it and/or modify
 * it under the terms of the GNU General Public License as published by
 * the Free Software Foundation, either version 3 of the License, or
 * (at your option) any later version.
 *
 * This program is distributed in the hope that it will be useful,
 * but WITHOUT ANY WARRANTY; without even implied warranty of
 * MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
 * GNU General Public License for more details.
 *
 * You should have received a copy of the GNU General Public License
 * along with this program.  If not, see <https://www.gnu.org/licenses/>.
 */

/**
 * MCP 服务域（设置页面板；v1.0.7 合入后双语化批次）。
 * 能力目录文案（工具名/说明）来自后端 GET 下发，服务端原文透传（E03 语义），
 * 不在本包维护。
 */
export const mcp = {
  panel: {
    title: 'MCP 服务',
    description: 'MCP（Model Context Protocol）服务允许外部 AI 客户端在通过认证后调用受控的种子查询、标记与任务触发能力。服务与全部能力默认关闭；关闭的能力对客户端不可发现，缓存旧定义直调也会被服务端拒绝。',
    loading: '加载中…',
    loadFailed: 'MCP 配置加载失败。',
    retry: '重试',
    forceDisabledTitle: '环境紧急开关已强制关闭 MCP 服务（BTDECK_MCP_FORCE_DISABLED=True）',
    forceDisabledDesc: '以下配置暂不生效；保存会保留配置意图，待紧急处置解除后按存储值恢复。',
    globalSwitch: '全局开关',
    stateOn: '已开启',
    stateOff: '已关闭',
    forceEffectiveOff: '（当前实际生效：关闭）',
    capabilityHint: '开启全局开关后还需单独启用所需能力；未启用任何能力时工具列表为空。',
    neverSaved: '尚未保存过配置',
    revisionInfo: '当前 revision {revision} · {time}{by}',
    bySuffix: '（{by}）',
    discard: '放弃更改',
    save: '保存配置'
  },
  risk: {
    high: '高风险',
    write: '写入',
    read: '只读',
    noteHigh: '高风险能力：外部副作用或任务执行，调用需要显式确认与幂等键并强制审计，启用前请确认信任调用方。',
    noteWrite: '写操作：调用需要显式确认与幂等键，并记录审计日志。'
  },
  apikey: {
    title: '服务密钥（API Key）',
    description: '外部 AI 客户端（Agent）使用该专用密钥对接 MCP 服务，与登录会话相互独立；密钥长期有效，刷新后旧密钥立即失效。',
    endpointLabel: '服务端点',
    endpointHint: '{origin}/mcp/（Streamable HTTP）',
    authLabel: '认证方式',
    authHint: '请求头携带 Authorization: Bearer <密钥>（或 X-Access-Token: <密钥>）',
    loading: '加载中…',
    statusAbsent: '尚未生成服务密钥。生成后即可供外部 Agent 对接 MCP 服务。',
    statusUnreadable: '服务密钥已生成，但当前无法读取（实例安全密钥可能已轮换）；刷新生成新密钥后，旧密钥立即失效。',
    generate: '生成服务密钥',
    rotate: '刷新服务密钥',
    copy: '复制',
    copied: '密钥已复制到剪贴板',
    copyFailed: '复制失败，请手动选择密钥文本复制',
    createdInfo: '创建于 {time}（{by}）',
    updatedInfo: '最近刷新 {time}（{by}）',
    securityNote: '安全提示：密钥经可逆加密存储于本机数据库，泄露数据库文件或实例配置密钥等同于泄露该密钥；密钥仅在当前页面内存中展示，不会写入浏览器存储。刷新会使旧密钥立即失效，正在使用旧密钥的 Agent 将全部断联。',
    confirmRotateTitle: '刷新 MCP 服务密钥',
    confirmRotateMessage: '刷新后新密钥立即生效、旧密钥同时失效，正在使用旧密钥的 Agent 将全部断联。确认刷新？',
    confirmGenerateTitle: '生成 MCP 服务密钥',
    confirmGenerateMessage: '将生成新的服务密钥并显示在本页面，用于外部 Agent 对接 MCP 服务。确认生成？'
  },
  msg: {
    saved: 'MCP 配置已保存',
    conflict: '配置已被其他会话修改，已重新加载最新配置，请确认后重试',
    saveFailed: '保存 MCP 配置失败，请稍后重试',
    generated: '服务密钥已生成',
    rotated: '服务密钥已刷新，旧密钥已失效',
    rotateFailed: '服务密钥刷新失败，请稍后重试',
    apikeyConflict: '服务密钥已被其他会话变更，已重新加载，请确认后重试'
  }
}
