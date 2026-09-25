/**
 * Statistics domain messages (statistics-reports W4; consumed by W5/W6 pages).
 *
 * Key set must match zh-CN/statistics.ts exactly (enforced by i18n-message-parity).
 */

export const statistics = {
  common: {
    chartEmpty: 'No data',
    periodMonth: 'Monthly',
    periodWeek: 'Weekly',
    range24h: '24 hours',
    range7d: '7 days',
    range30d: '30 days',
    count: 'Count',
    sizeBytes: 'Size',
    torrentCount: 'Torrents',
    loadFailed: 'Failed to load statistics',
    refresh: 'Refresh'
  },
  overview: {
    title: 'Library overview',
    totalTorrents: 'Total torrents',
    totalSize: 'Total size',
    avgSize: 'Average size',
    recycleBinSize: 'Recycle bin size',
    largest: 'Largest TOP 10',
    statusDist: 'Status distribution',
    categories: 'Categories',
    tags: 'Tags',
    paths: 'Directory usage',
    downloaders: 'Downloader comparison',
    liveSpeed: 'Live speed',
    uncategorized: 'Uncategorized',
    removedDownloader: 'Removed',
    buckets: {
      error: 'Error',
      downloading: 'Downloading',
      seeding: 'Seeding',
      paused: 'Paused',
      other: 'Other'
    }
  },
  trends: {
    title: 'Trends',
    addedTrend: 'Added trend',
    completedTrend: 'Completed trend',
    ageStructure: 'Library age',
    speedHistory: 'Speed history',
    ageBuckets: {
      under7d: 'Within 7 days',
      to30d: 'Within 30 days',
      to90d: 'Within 90 days',
      to180d: 'Within 180 days',
      to1y: 'Within 1 year',
      over1y: 'Over 1 year',
      unknown: 'Unknown'
    }
  },
  seeding: {
    title: 'Seeding',
    ratioDist: 'Ratio distribution',
    slackers: 'Slackers quadrant',
    auxiliary: 'Cross-seed network',
    crossSeedRate: 'Cross-seed rate',
    ratioNullCount: 'Torrents without ratio'
  },
  trackers: {
    title: 'Tracker',
    sites: 'Sites',
    health: 'Site health',
    supplyDemand: 'Supply & demand',
    errorRate: 'Error rate',
    affectedCount: 'Affected torrents',
    avgSeeders: 'Avg. seeders',
    avgLeechers: 'Avg. leechers',
    avgDownloads: 'Avg. downloads',
    validRows: 'Valid rows'
  },
  fun: {
    title: 'Fun report',
    battleReport: 'Battle report',
    yearlyReport: 'Yearly report',
    guardian: 'Fire keeper',
    fireCount: 'Fire-seed torrents',
    badges: 'Upload medals',
    shame: 'Freeloader board',
    pride: 'Philanthropist board',
    badgeTiers: {
      bronze: 'Bronze',
      silver: 'Silver',
      gold: 'Gold',
      platinum: 'Platinum',
      diamond: 'Diamond'
    },
    equivalents: {
      movies: 'Equivalent to uploading {n} HD movies',
      blurays: 'About {n} Blu-ray discs',
      tvSeasons: 'About {n} TV seasons'
    },
    yearly: {
      yearAdded: '{count} torrents added this year, {size} in total',
      busiestMonth: 'Busiest month: {key} ({count} added)',
      busiestDay: 'Busiest day: {key} ({count} added)',
      topSite: 'Top site by size: {host}',
      elder: 'Elder: {name} (seeding for {days} days)'
    }
  },
  calibers: {
    timezone: 'Time caliber follows deployment timezone (no offset under default Docker TZ=UTC)',
    samplingStart: 'Sampling started at {time}; data accumulates from launch',
    trackerCountStart: 'Tracker counts accumulate since activation',
    speedBreak: 'Gaps only appear during backend downtime; downloader offline counts as zero-speed points',
    onlineRatio: 'Online ratio covers sampled periods only (backend downtime excluded)',
    crossSiteSize: 'Cross-seed torrent size is counted once per site',
    recycleExcluded: 'Permanently deleted data is out of the library caliber',
    completedNullNote: 'Torrents added in seeding state have no completion time; the completed trend covers fewer torrents',
    ratioNullNote: 'Torrents added in seeding state on Transmission have no ratio',
    trUncategorized: 'Transmission torrents fall into the uncategorized bucket',
    uploadEstimate: 'Upload volume is an estimate (size × ratio); Transmission seeding-added torrents are systematically missing'
  }
}
