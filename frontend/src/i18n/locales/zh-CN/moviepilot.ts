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
 * MoviePilot 集成域（设置页面板 + 种子详情「媒体库」页签 + 关联反查；v1.0.7 合入后双语化批次）。
 * shared 子树为面板反查卡与 TrackerDetailCard 媒体库页签共用的展示值。
 */
export const moviepilot = {
  panel: {
    title: 'MoviePilot 集成',
    description: '通过 MoviePilot 插件 BtDeckBridge 将其整理历史同步为只读镜像，建立「媒体库文件 ↔ 整理源文件 ↔ BT 任务」关联。本功能不产生任何对生产任务或 MoviePilot 侧的写操作；MoviePilot 历史消失不会触发本地清理。',
    loading: '加载中…',
    loadFailed: 'MoviePilot 集成配置加载失败。',
    retry: '重试',
    globalSwitch: '集成开关',
    stateOn: '已开启',
    stateOff: '已关闭',
    offHint: '关闭后插件握手与同步会被拒绝（403）；已同步的镜像数据保留。插件侧需配置 BtDeck 地址与专用集成账号（建议单独创建账号，勿开启两步验证）。',
    neverSaved: '尚未保存过配置',
    revisionInfo: '当前 revision {revision} · {time}{by}',
    bySuffix: '（{by}）',
    discard: '放弃更改',
    save: '保存配置',
    instancesTitle: '已注册实例',
    refresh: '刷新',
    instancesDesc: 'MoviePilot 插件首次握手后自动注册。配置「MoviePilot 下载器 → BtDeck 下载器」映射后，同步的历史才能按 (下载器, Hash) 关联到任务；映射名须与 MoviePilot 侧下载器名称一致。',
    noInstance: '暂无实例。在 MoviePilot 中安装 BtDeckBridge 插件并完成握手后，此处会出现实例。',
    instanceEnabled: '已启用',
    instanceDisabled: '已禁用',
    allowSync: '允许同步',
    deleteInstance: '删除实例',
    instanceIds: '实例 {instanceId} · 绑定账号 {username}',
    moviepilotVersionSuffix: '· MoviePilot {version}',
    pluginVersionSuffix: '· 插件 {version}',
    lastErrorPrefix: '最近错误：{error}',
    syncedCount: '已同步 {count} 条',
    notSyncedYet: '尚未同步',
    mapping: {
      title: '下载器映射',
      edit: '编辑映射',
      cancel: '取消',
      save: '保存映射',
      mpPlaceholder: 'MoviePilot 下载器名',
      btPlaceholder: 'BtDeck 下载器',
      remove: '删除',
      add: '+ 添加映射',
      reparseNotice: '保存后该实例全部历史会立即按新映射重新解析关联状态。',
      notConfigured: '尚未配置映射（历史将标记为未映射）。',
      saved: '映射已保存，历史关联状态已重新解析',
      saveFailed: '保存映射失败',
      rowInvalid: '映射行的 MoviePilot 下载器名与 BtDeck 下载器均不能为空',
      duplicateName: '存在重复的 MoviePilot 下载器名'
    },
    msg: {
      saved: 'MoviePilot 集成配置已保存',
      conflict: '配置已被其他会话修改，已重新加载最新配置，请确认后重试',
      saveFailed: '保存失败，请稍后重试',
      instanceEnabled: '实例已启用',
      instanceDisabled: '实例已禁用（握手/同步将被拒绝）',
      instanceUpdateFailed: '更新实例失败',
      deleteTitle: '删除实例',
      deleteConfirm: '删除实例「{name}」将连带删除其 {count} 条同步历史，且不可恢复。确定删除？',
      deleteConfirmButton: '删除',
      instanceDeleted: '实例已删除',
      instanceDeleteFailed: '删除实例失败'
    }
  },
  reverse: {
    title: '关联反查',
    description: '输入媒体库文件/目录或源文件路径，反查关联的整理历史与 BT 任务。目录会按前缀匹配其下文件；无 Hash 的历史标记为未关联。',
    placeholder: '如 /data/media/电影 或 /data/downloads/xxx.mkv',
    modeAll: '全部路径',
    modeSrc: '仅源文件',
    modeDest: '仅媒体库',
    query: '查询',
    pathRequired: '请输入要反查的路径',
    notFound: '未找到匹配的整理历史。',
    failed: '反查失败，请稍后重试',
    colTitle: '媒体标题',
    colSeason: '季 / 集',
    colMode: '整理方式',
    colDest: '媒体库路径',
    colSrc: '源文件路径',
    colTask: '关联任务'
  },
  shared: {
    transferMode: {
      copy: '复制',
      move: '移动',
      link: '软链接',
      hardlink: '硬链接'
    },
    association: {
      linked: '已关联',
      unmapped: '未映射',
      unassociated: '未关联'
    },
    unknownTitle: '未知标题'
  },
  media: {
    tab: '媒体库',
    loading: '媒体库关联加载中...',
    loadFailed: '媒体库关联加载失败',
    empty: '未找到 MoviePilot 整理记录（需已同步且配置下载器映射）',
    count: '共 {count} 条整理记录',
    refresh: '刷新',
    stale: '更新失败，显示上次数据',
    failedTag: '整理失败',
    loadFailedFallback: '获取媒体库关联失败',
    colTitle: '媒体标题',
    colSeason: '季 / 集',
    colMode: '整理方式',
    colDest: '媒体库路径',
    colSrc: '源文件路径',
    colInstance: '实例'
  }
}
