/**
 * 统计数据域文案（statistics-reports W4 建包；W5/W6 页面消费并按需扩展）。
 *
 * 键集与 en/statistics.ts 严格一致（i18n-message-parity 钉住）。
 * 口径脚注集中在本包 calibers.*（PLANS/statistics-reports.md §3.4）。
 */

export const statistics = {
  common: {
    chartEmpty: '暂无数据',
    periodMonth: '按月',
    periodWeek: '按周',
    range24h: '24 小时',
    range7d: '7 天',
    range30d: '30 天',
    count: '数量',
    sizeBytes: '体积',
    torrentCount: '种子数',
    loadFailed: '统计数据加载失败',
    refresh: '刷新'
  },
  overview: {
    title: '库存总览',
    totalTorrents: '总种子数',
    totalSize: '总体积',
    avgSize: '平均体积',
    recycleBinSize: '回收站现占体积',
    largest: '体积最大 TOP10',
    statusDist: '状态分布',
    categories: '分类分布',
    tags: '标签分布',
    paths: '目录占用排行',
    downloaders: '下载器对比',
    liveSpeed: '实时速度',
    uncategorized: '未分类',
    removedDownloader: '已移除',
    buckets: {
      error: '错误',
      downloading: '下载中',
      seeding: '做种中',
      paused: '已暂停',
      other: '其他'
    }
  },
  trends: {
    title: '趋势',
    addedTrend: '新增趋势',
    completedTrend: '完成趋势',
    ageStructure: '库龄结构',
    speedHistory: '速度历史',
    ageBuckets: {
      under7d: '7 天内',
      to30d: '30 天内',
      to90d: '90 天内',
      to180d: '180 天内',
      to1y: '1 年内',
      over1y: '更久',
      unknown: '未知'
    }
  },
  seeding: {
    title: '做种',
    ratioDist: '分享率分布',
    slackers: '摸鱼象限',
    auxiliary: '辅种网络',
    crossSeedRate: '辅种率',
    ratioNullCount: '无分享率种子'
  },
  trackers: {
    title: 'Tracker',
    sites: '站点构成',
    health: '站点健康榜',
    supplyDemand: '站点冷热',
    errorRate: '错误率',
    affectedCount: '受影响种子',
    avgSeeders: '平均做种数',
    avgLeechers: '平均下载数',
    avgDownloads: '平均完成数',
    validRows: '有效行数'
  },
  fun: {
    title: '趣味报告',
    battleReport: '战报',
    yearlyReport: '年度报告',
    guardian: '火种守护者',
    fireCount: '火种种子',
    badges: '上传量勋章',
    shame: '白嫖榜',
    pride: '慈善榜',
    badgeTiers: {
      bronze: '铜',
      silver: '银',
      gold: '金',
      platinum: '白金',
      diamond: '钻石'
    },
    equivalents: {
      movies: '相当于上传了 {n} 部高清电影',
      blurays: '约 {n} 部蓝光原盘',
      tvSeasons: '约 {n} 季剧集'
    },
    yearly: {
      yearAdded: '今年添加了 {count} 个种子，共 {size}',
      busiestMonth: '最忙的月份是 {key}（新增 {count} 个）',
      busiestDay: '最忙的一天是 {key}（新增 {count} 个）',
      topSite: '体积占比最高的站点：{host}',
      elder: '元老：{name}（{days} 天仍在做种）'
    }
  },
  calibers: {
    timezone: '时间口径随部署时区（Docker 默认 TZ=UTC 时无偏移）',
    samplingStart: '采样已于 {time} 启动，数据自上线起积累',
    trackerCountStart: 'Tracker 计数自激活日起积累',
    speedBreak: '断点仅出现在后端停机时段；下载器离线为 0 速数据点',
    onlineRatio: '在线率为采样期间口径（后端停机时段不计入）',
    crossSiteSize: '辅种种子体积会在多个站点重复计入',
    recycleExcluded: '已彻底删除数据不在库存口径',
    completedNullNote: '做种态添加的种子无完成时间，完成趋势覆盖面偏小',
    ratioNullNote: 'Transmission 做种态添加的种子无分享率',
    trUncategorized: 'Transmission 无分类，归入未分类桶',
    uploadEstimate: '上传量为估算值（体积 × 分享率），Transmission 做种态添加种子系统性缺位'
  }
}
