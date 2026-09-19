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
 * 种子域文案（torrent 组，P3-1：列表骨架 + 操作反馈 + 添加弹窗 + 批量弹窗 + 删重两弹窗；
 * P3-2 增 detail 子树：种子详情弹窗）。
 *
 * 注意：四级删除确认/结果链路（utils/torrentBatch.ts 的 DELETE_LEVEL_NAMES、
 * buildDeleteConfirmMessage、parseDeleteTaskResult、parseSyncDeleteResponse 及
 * index.vue 同名遗留路径）属 P5 高风险审校范围，本批不翻译。
 */
export const torrent = {
  status: {
    seeding: '做种中',
    downloading: '下载中',
    completed: '已完成',
    paused: '已暂停',
    queuedDL: '下载队列',
    error: '错误',
    checking: '检查中',
    unknown: '未知'
  },
  list: {
    searchPlaceholder: '搜索种子名称...',
    downloaderPlaceholder: '请选择下载器',
    statusPlaceholder: '请选择种子状态',
    trackerPlaceholder: '请选择tracker',
    activeOnly: '仅显示活动种子',
    search: '搜索',
    advancedSearch: '高级搜索',
    duplicateSwitch: '查找重复任务',
    clear: '清空',
    refresh: '刷新',
    alert: {
      sameContent: '辅种异常排查：当前列表仅显示名称、大小相同但 InfoHash 不同的种子',
      singleError: '错误单种排查：当前列表仅显示错误且全局同内容唯一的种子',
      exit: '退出排查并返回普通列表'
    },
    toolbar: {
      start: '开始',
      pause: '暂停',
      delete: '删除',
      recheck: '重检',
      trackerOps: 'Tracker操作',
      reannounce: 'Tracker汇报',
      globalReplace: '全局替换',
      transfer: '转移',
      setLocation: '修改路径',
      quickActions: '快捷操作',
      add: '添加种子',
      columns: '列设置'
    },
    deleteMenu: {
      level4: '等级4: 标记为待删除(推荐)',
      level3: '等级3: 移至回收站',
      level2: '等级2: 删除任务(保留数据)',
      level1: '等级1: 完全删除'
    },
    quickMenu: {
      sameContent: '辅种异常排查',
      singleError: '错误单种排查',
      deleteDuplicates: '快捷删除重复种子'
    },
    column: {
      name: '种子名称',
      downloadSpeed: '下载速度',
      uploadSpeed: '上传速度',
      size: '大小',
      auxiliarySeedCount: '辅种数量',
      progress: '进度',
      status: '状态',
      downloader: '所属下载器',
      ratio: '比率',
      category: '分类/标签',
      savePath: '保存路径',
      addedDate: '添加时间',
      actions: '操作'
    },
    sortTitle: {
      name: '按种子名称排序',
      size: '按大小排序',
      status: '按状态排序',
      ratio: '按比率排序',
      addedDate: '按添加时间排序'
    },
    resizeHint: '拖拽调整列宽，双击恢复默认',
    loading: '加载中...',
    trackerError: 'Tracker异常',
    trackerErrorTitle: '{status}（Tracker异常）',
    action: {
      recheck: '重新检查',
      setLocation: '修改保存路径'
    },
    view: {
      list: '列表模式',
      traditional: '传统模式'
    },
    pagination: {
      summary: '共 {total} 条，第 {page}/{pages} 页'
    },
    columnSettings: {
      title: '列设置',
      reset: '重置',
      resetWidths: '重置列宽',
      apply: '应用',
      saved: '列设置已保存',
      widthsReset: '列宽已重置为默认'
    }
  },
  msg: {
    getListFailed: '获取种子列表失败',
    applyTemplateFailed: '应用模板失败',
    applyTemplateFailedWith: '应用模板失败：{message}',
    inspectSameContentDone: '排查完成，共找到 {count} 条同内容种子',
    inspectSingleErrorDone: '排查完成，共找到 {count} 条错误单种',
    duplicatesFound: '查找完成，共找到 {count} 条重复种子',
    duplicateFetchFailed: '查找失败',
    duplicateFetchFailedRetry: '查找失败，请稍后重试',
    reannounceSuccess: 'Tracker汇报成功',
    reannounceFailed: 'Tracker汇报失败',
    reannounceIncomplete: '种子信息不完整，无法汇报',
    reannouncePartial: 'Tracker汇报部分完成：成功{succeeded}个下载器，失败{failed}个下载器（共{total}个种子）',
    reannounceBatchSuccess: 'Tracker汇报成功({total}个种子, {downloaderCount}个下载器)',
    reannounceBatchFailed: 'Tracker汇报失败，请查看控制台',
    startSuccess: '开始下载成功',
    pauseSuccess: '暂停下载成功',
    recheckSuccess: '重新检查成功',
    opFailed: '操作失败，请稍后重试',
    recheckFailed: '重新检查失败，请稍后重试',
    advancedDone: '高级搜索完成，找到 {count} 条结果',
    searchFailed: '搜索失败',
    advancedFailed: '高级搜索失败，请检查搜索条件',
    invalidSearchParams: '搜索条件格式错误',
    templateInvalid: '模板条件格式无效',
    templateApplied: '已应用查询模板',
    advancedTemplateApplied: '已应用高级搜索模板',
    unsupportedTemplate: '不支持的模板类型',
    conditionsReset: '搜索条件已重置',
    trackerOpSuccess: 'Tracker操作成功',
    globalReplaceSuccess: '全局替换Tracker成功',
    selectFirstAction: '请先选择要操作的种子',
    selectFirstTransfer: '请先选择要转移的种子',
    selectFirst: '请先选择种子',
    missingDownloader: '选中种子缺少下载器信息，请刷新后重试',
    transferSingleDownloaderOnly: '批量转移只支持同一下载器的种子，请重新选择',
    setLocationSingleDownloaderOnly: '选中的种子必须属于同一下载器',
    transferDone: '批量转移操作完成'
  },
  addDialog: {
    title: '添加种子',
    fileLabel: '种子文件',
    filePlaceholder: '点击选择 .torrent 文件（数量不限）',
    filesSelected: '已选择 {count} 个文件',
    fileHint: '只支持 .torrent 文件，提交后将在后台异步处理',
    downloaderLabel: '下载器',
    downloaderPlaceholder: '选择下载器',
    pathLabel: '保存路径',
    pathPlaceholder: '输入或选择保存路径',
    pathTypeDefault: '默认路径',
    pathTypeInUse: '在用路径',
    pathCount: '{count}个种子',
    checkPolicy: '校验策略',
    skipCheck: '跳过校验（数据已完整时直接做种）',
    skipCheckHint: '保存路径已有完整数据（辅种/续种）时勾选可跳过 qBittorrent 本地校验，避免 CheckingDL；全新下载请勿勾选（会被当作已完成，无法正常下载）。仅对 qBittorrent 生效。',
    category: '分类',
    categoryPlaceholder: '选择分类（可选）',
    tags: '标签',
    tagsPlaceholder: '选择标签（可选）',
    confirm: '确定',
    adding: '添加中...',
    error: {
      chooseFile: '请选择种子文件',
      chooseDownloader: '请选择下载器',
      enterPath: '请输入保存路径',
      onlyTorrent: '只能选择 .torrent 文件'
    },
    msg: {
      submitted: '已提交 {count} 个种子到后台处理',
      success: '成功添加 {count} 个种子',
      failed: '种子添加失败',
      failedWith: '种子添加失败：{detail}',
      partial: '部分成功：成功 {success} 个，失败 {failed} 个',
      failureItem: '{name}：{error}',
      unknownError: '未知错误',
      moreFailures: '；其余 {count} 个失败项请查看详情',
      retry: '种子添加失败，请稍后重试'
    }
  },
  batchDialog: {
    title: {
      delete: '批量删除确认',
      pause: '批量暂停确认',
      resume: '批量恢复确认',
      start: '批量开始确认',
      fallback: '批量操作确认'
    },
    op: {
      delete: '删除',
      pause: '暂停',
      resume: '恢复',
      start: '开始',
      fallback: '操作'
    },
    message: {
      delete: '您确定要删除这些种子吗？此操作不可撤销！',
      pause: '您确定要暂停这些种子吗？',
      resume: '您确定要恢复这些种子吗？',
      start: '您确定要开始这些种子吗？',
      fallback: '您确定要执行此操作吗？'
    },
    opType: '操作类型：',
    affectCount: '影响数量：',
    countTorrents: '{count} 个种子',
    affected: '受影响的种子：',
    confirmAction: '确认{op}'
  },
  batch: {
    action: {
      start: '开始',
      pause: '暂停',
      recheck: '重检'
    },
    partial: '批量{action}部分完成：成功{succeeded}个下载器，失败{failed}个下载器（共{total}个种子）',
    success: '批量{action}成功({total}个种子, {downloaderCount}个下载器)',
    failed: {
      start: '批量开始失败，请查看控制台',
      pause: '批量暂停失败，请查看控制台',
      recheck: '批量重检失败，请查看控制台'
    }
  },
  /** 种子详情弹窗（TorrentDetailDialog，P3-2；转移弹窗本体属 P6 不译） */
  detail: {
    title: '种子详情',
    nameLabel: '种子名称',
    status: '状态',
    size: '文件大小',
    progress: '进度',
    downloadSpeed: '下载速度',
    uploadSpeed: '上传速度',
    addedDate: '添加时间',
    completedDate: '完成时间',
    ratio: '分享比率',
    savePath: '保存路径',
    tags: '标签',
    notCompleted: '未完成',
    trackerSection: 'Tracker信息',
    trackerColName: '名称',
    trackerColStatus: '状态',
    statusNormal: '正常',
    statusAbnormal: '异常',
    transfer: '转移'
  },
  duplicates: {
    quick: {
      title: '快捷删除重复种子',
      detectLabel: '待检测下载器',
      detectHint: '选择 2 个及以上下载器，用于在其间查找重复种子',
      keepLabel: '保留下载器',
      keepHint: '这些下载器中的重复种子将被保留，其余下载器中的重复种子将被删除（只删种子、不删文件）',
      autoHint: '完成待检测与保留下载器选择后将自动预览重复结果',
      analyzing: '正在分析重复种子...',
      groupsPrefix: '共',
      groupsSuffix: '组重复',
      deletePrefix: '将删除',
      deleteSuffix: '个种子',
      skippedNote: '⚠ 另有 {count} 组已跳过（无保留副本）',
      skippedTooltip: '这些重复仅在待删下载器间存在、无保留副本，为避免丢失最后一份数据已跳过，不会删除',
      empty: '未在所选下载器间发现可删除的重复种子',
      noName: '（无名称）',
      skippedBadge: '已跳过',
      skippedBody: '这些副本仅在待删下载器间存在，无保留副本，为避免丢失最后一份数据已跳过（不会删除）',
      colDelete: '将被删除',
      colKeep: '保留副本',
      confirmDelete: '确认删除',
      confirmDeleteCount: '确认删除（{count}个）',
      msg: {
        queryFailed: '查询失败',
        submitFailed: '提交删除任务失败',
        noDeletable: '未发现可删除的重复种子',
        submitted: '已提交删除任务（共 {total} 个种子，跳过处理中 {skipped} 个）',
        submittedPlain: '已提交删除任务（共 {total} 个种子）',
        taskDone: '删除任务完成：成功 {success}，失败 {failed}',
        taskPartial: '删除任务部分完成：成功 {success}，失败 {failed}',
        taskFailed: '删除任务失败：成功 {success}，失败 {failed}',
        stillRunning: '删除任务仍在后台执行，可稍后在通知中心查看结果'
      }
    },
    scan: {
      title: '重复种子查询',
      loading: '正在查询重复种子...',
      col: {
        hash: 'Hash值',
        name: '任务名称',
        size: '大小',
        downloader: '所在下载器',
        status: '状态',
        path: '保存路径'
      },
      groupsPrefix: '共找到',
      groupsSuffix: '组重复种子',
      tasksPrefix: '总计',
      tasksSuffix: '个任务',
      empty: '未发现重复种子',
      queryFailed: '查询失败'
    }
  }
}
