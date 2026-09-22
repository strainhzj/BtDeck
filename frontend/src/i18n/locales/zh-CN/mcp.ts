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
  msg: {
    saved: 'MCP 配置已保存',
    conflict: '配置已被其他会话修改，已重新加载最新配置，请确认后重试',
    saveFailed: '保存 MCP 配置失败，请稍后重试'
  }
}
