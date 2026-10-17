<template>
  <div
    class="fun-report"
    tabindex="0"
    data-testid="fun-report-overlay"
    @keydown.left="stepSlide(-1)"
    @keydown.right="stepSlide(1)"
  >
    <!-- 顶栏：子模式切换 + 关闭（状态走 route query——决策 10：全仓无 keep-alive，返回必重挂载） -->
    <div class="fun-report__bar">
      <div class="fun-report__modes">
        <button
          type="button"
          class="fun-report__mode"
          :class="{'fun-report__mode--active': mode === 'battle'}"
          data-testid="mode-battle"
          @click="setMode('battle')"
        >
          {{ $t('statistics.fun.battleReport') }}
        </button>
        <button
          type="button"
          class="fun-report__mode"
          :class="{'fun-report__mode--active': mode === 'yearly'}"
          data-testid="mode-yearly"
          @click="setMode('yearly')"
        >
          {{ $t('statistics.fun.yearlyReport') }}
        </button>
      </div>
      <button
        type="button"
        class="fun-report__close"
        data-testid="fun-report-close"
        @click="close"
      >
        {{ $t('statistics.fun.close') }} ✕
      </button>
    </div>

    <!-- 战报（24/25/27）：滚动卡片流 -->
    <div
      v-if="mode === 'battle'"
      class="fun-report__scroll"
      data-testid="battle-panel"
    >
      <div class="fun-report__card">
        <h2 class="fun-report__card-title">🔥 {{ $t('statistics.fun.guardian') }}</h2>
        <p
          v-if="summary"
          class="fun-report__stat"
        >
          {{ $t('statistics.fun.fireCount') }}: <strong>{{ summary.guardian.fireCount }}</strong>
          <span class="fun-report__meta">（{{ $t('statistics.calibers.trackerCountStart') }}）</span>
        </p>
        <ol
          v-if="summary && summary.guardian.top10.length"
          class="fun-report__list"
        >
          <li
            v-for="item in summary.guardian.top10"
            :key="item.hash"
          >
            <span class="fun-report__name">{{ item.name }}</span>
            <span class="fun-report__rank-value">seeders ≤ {{ item.minSeeders }}</span>
          </li>
        </ol>
      </div>

      <div class="fun-report__card">
        <h2 class="fun-report__card-title">🏅 {{ $t('statistics.fun.badges') }}</h2>
        <template v-if="summary">
          <p class="fun-report__stat">
            {{ $t('statistics.fun.badgeTiers.' + summary.badges.currentTier) }}
            <span class="fun-report__rank-value">{{ formatFileSize(summary.badges.uploadedBytes) }}</span>
          </p>
          <p class="fun-report__stat">
            {{ $t('statistics.fun.equivalents.movies', {n: summary.badges.equivalents.movies}) }}
          </p>
          <p
            v-if="summary.badges.nextTier"
            class="fun-report__meta"
          >
            {{ $t('statistics.fun.nextTier', {tier: $t('statistics.fun.badgeTiers.' + summary.badges.nextTier), gap: nextTierGap}) }}
          </p>
          <p class="fun-report__meta">{{ $t('statistics.calibers.uploadEstimate') }}</p>
        </template>
      </div>

      <div class="fun-report__card">
        <h2 class="fun-report__card-title">⚖️ {{ $t('statistics.fun.shame') }} / {{ $t('statistics.fun.pride') }}</h2>
        <div
          v-if="summary"
          class="fun-report__two-col"
        >
          <div>
            <h3 class="fun-report__sub-title">{{ $t('statistics.fun.shame') }}</h3>
            <ol class="fun-report__list">
              <li
                v-for="item in summary.shame"
                :key="item.hash"
              >
                <span class="fun-report__name">{{ item.name }}</span>
                <span class="fun-report__rank-value">ratio {{ item.ratio }}</span>
              </li>
            </ol>
          </div>
          <div>
            <h3 class="fun-report__sub-title">{{ $t('statistics.fun.pride') }}</h3>
            <ol class="fun-report__list">
              <li
                v-for="item in summary.pride"
                :key="item.hash"
              >
                <span class="fun-report__name">{{ item.name }}</span>
                <span class="fun-report__rank-value">ratio {{ item.ratio }}</span>
              </li>
            </ol>
          </div>
        </div>
      </div>
    </div>

    <!-- 年度报告（26）：年份选择 + 翻页卡流 -->
    <div
      v-else
      class="fun-report__scroll fun-report__scroll--center"
      data-testid="yearly-panel"
    >
      <YearPicker
        :value="year"
        @change="setYear"
      />
      <transition
        name="fun-slide-fade"
        mode="out-in"
      >
        <FunSlide
          :key="slide"
          :badge="slideBadge"
          :title="slideTitle"
          :active="true"
        >
          <template v-if="yearly">
            <p v-if="slide === 1">{{ $t('statistics.fun.yearly.opening', {year}) }}</p>
            <p v-else-if="slide === 2">{{ $t('statistics.fun.yearly.yearAdded', {count: yearly.yearAdded.count, size: formatFileSize(yearly.yearAdded.sizeBytes)}) }}</p>
            <template v-else-if="slide === 3">
              <p v-if="yearly.busiestMonth">{{ $t('statistics.fun.yearly.busiestMonth', yearly.busiestMonth) }}</p>
              <p v-if="yearly.busiestDay">{{ $t('statistics.fun.yearly.busiestDay', yearly.busiestDay) }}</p>
            </template>
            <p v-else-if="slide === 4 && yearly.topSite">{{ $t('statistics.fun.yearly.topSite', {host: yearly.topSite.host}) }}</p>
            <p v-else-if="slide === 5 && yearly.elder">{{ $t('statistics.fun.yearly.elder', {name: yearly.elder.name, days: yearly.elder.seedingDays}) }}</p>
            <p v-else-if="slide === 6">{{ $t('statistics.fun.fireCount') }}: {{ yearly.fireCount }}</p>
            <p v-else-if="slide === 7">{{ $t('statistics.fun.equivalents.movies', {n: yearly.uploadEstimate.equivalents.movies}) }}</p>
            <p v-else-if="slide === 8">{{ $t('statistics.fun.ending') }}</p>
          </template>
          <p v-else>{{ $t('statistics.common.chartEmpty') }}</p>
        </FunSlide>
      </transition>
      <div class="fun-report__pager">
        <el-button
          size="small"
          :disabled="slide <= 1"
          data-testid="slide-prev"
          @click="stepSlide(-1)"
        >
          {{ $t('statistics.fun.prev') }}
        </el-button>
        <span class="fun-report__pager-info">{{ $t('statistics.fun.slideOf', {i: slide, n: SLIDE_COUNT}) }}</span>
        <el-button
          size="small"
          :disabled="slide >= SLIDE_COUNT"
          data-testid="slide-next"
          @click="stepSlide(1)"
        >
          {{ $t('statistics.fun.next') }}
        </el-button>
      </div>
    </div>
  </div>
</template>

<script lang="ts">
/**
 * 趣味报告沉浸页（statistics-reports W6，PLANS/statistics-reports.md §1.2/决策 10）。
 *
 * 沉浸层实现约束（决策 10，el-drawer btt 对比后定稿 fixed 方案——Element
 * PopupManager 自动 z≥2000 会压 Element 弹层，违背 <2001 约束）：
 * - 根元素即覆盖层（fixed + z-index 1200，有效区间 1002-2000：>1001 盖
 *   sidebar、<2001 不压 Element Message/MessageBox）；禁止外包 wrapper——
 *   fade-transform 祖先 transform 会使 fixed 塌陷；
 * - 状态走 route query（?mode=&year=&slide=）持久化：全仓无 keep-alive，
 *   返回必重挂载，query 恢复进度；
 * - 翻页过渡只作用于卡片内容层（不动根覆盖层 fixed 定位）。
 */
import { Component, Vue, Watch } from 'vue-property-decorator'
import { formatFileSize } from '@/utils/formatters'
import { getReportsFunSummary, getReportsFunYearly } from '@/api/reports'
import { ReportsFunSummaryData, ReportsFunYearlyData } from '@/types/reports'
import FunSlide from '../components/FunSlide.vue'
import YearPicker from '../components/YearPicker.vue'

const SLIDE_COUNT = 8

@Component({ name: 'StatisticsFunReport', components: { FunSlide, YearPicker } })
export default class StatisticsFunReport extends Vue {
  private summary: ReportsFunSummaryData | null = null
  private yearly: ReportsFunYearlyData | null = null

  private readonly SLIDE_COUNT = SLIDE_COUNT

  // ---------- route query 持久化（决策 10） ----------

  private get mode(): 'battle' | 'yearly' {
    return this.$route.query.mode === 'yearly' ? 'yearly' : 'battle'
  }

  private get year(): number {
    const raw = parseInt(String(this.$route.query.year ?? ''), 10)
    if (Number.isFinite(raw) && raw >= 2024 && raw <= new Date().getFullYear()) {
      return raw
    }
    return new Date().getFullYear()
  }

  private get slide(): number {
    const raw = parseInt(String(this.$route.query.slide ?? ''), 10)
    if (Number.isFinite(raw) && raw >= 1 && raw <= SLIDE_COUNT) {
      return raw
    }
    return 1
  }

  private replaceQuery(patch: Record<string, string>): void {
    const query: Record<string, string> = {
      mode: this.mode,
      year: String(this.year),
      slide: String(this.slide),
      ...patch
    }
    this.$router.replace({ query }).catch(() => undefined) // 重复导航静默
  }

  private setMode(mode: 'battle' | 'yearly'): void {
    if (mode !== this.mode) {
      this.replaceQuery({ mode, slide: '1' })
    }
  }

  private setYear(year: number): void {
    if (year !== this.year) {
      this.replaceQuery({ year: String(year), slide: '1' })
    }
  }

  private stepSlide(delta: number): void {
    const next = Math.min(SLIDE_COUNT, Math.max(1, this.slide + delta))
    if (next !== this.slide) {
      this.replaceQuery({ slide: String(next) })
    }
  }

  private close(): void {
    this.$router.push('/statistics/overview')
  }

  // ---------- 数据 ----------

  mounted() {
    this.fetchSummary()
    if (this.mode === 'yearly') {
      this.fetchYearly()
    }
  }

  private async fetchSummary(): Promise<void> {
    try {
      const res = await getReportsFunSummary()
      if (res.code === '200' && res.data) {
        this.summary = res.data
      }
    } catch {
      this.$message.error(this.$t('statistics.common.loadFailed').toString())
    }
  }

  private async fetchYearly(): Promise<void> {
    try {
      const res = await getReportsFunYearly(this.year)
      if (res.code === '200' && res.data) {
        this.yearly = res.data
      }
    } catch {
      this.$message.error(this.$t('statistics.common.loadFailed').toString())
    }
  }

  @Watch('$route.query.mode')
  onModeChanged(): void {
    if (this.mode === 'yearly' && !this.yearly) {
      this.fetchYearly()
    }
  }

  @Watch('$route.query.year')
  onYearChanged(): void {
    if (this.mode === 'yearly') {
      this.yearly = null
      this.fetchYearly()
    }
  }

  // ---------- 翻页卡派生 ----------

  private get slideBadge(): string {
    return ['📅', '🌱', '📆', '🌐', '👴', '🔥', '🏅', '✨'][this.slide - 1] ?? ''
  }

  private get slideTitle(): string {
    const titles = [
      this.$t('statistics.fun.yearlyReport').toString(),
      this.$t('statistics.fun.title').toString(),
      this.$t('statistics.fun.yearlyReport').toString(),
      this.$t('statistics.trackers.sites').toString(),
      this.$t('statistics.seeding.title').toString(),
      this.$t('statistics.fun.guardian').toString(),
      this.$t('statistics.fun.badges').toString(),
      this.$t('statistics.fun.ending').toString()
    ]
    return titles[this.slide - 1] ?? ''
  }

  private get nextTierGap(): string {
    const badges = this.summary?.badges
    if (!badges || badges.nextTierAtTB === null) return ''
    const gap = Math.max(0, badges.nextTierAtTB - badges.uploadedBytes / 1024 ** 4)
    return gap.toFixed(1)
  }

  private formatFileSize = formatFileSize
}
</script>

<style scoped>
/* 根元素即覆盖层（决策 10）：fixed + z-index 1200（>1001 盖 sidebar，<2001 不压 Element 弹层） */
.fun-report {
  position: fixed;
  inset: 0;
  z-index: 1200;
  display: flex;
  flex-direction: column;
  background: linear-gradient(160deg, #1f2d3d 0%, #2b3a4b 55%, #1a2530 100%);
  color: #fff;
  outline: none;
  overflow: hidden;
}

.fun-report__bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 14px 22px;
}

.fun-report__modes {
  display: flex;
  gap: 8px;
}

.fun-report__mode {
  padding: 6px 16px;
  border-radius: 999px;
  border: 1px solid rgba(255, 255, 255, 0.5);
  background: transparent;
  color: rgba(255, 255, 255, 0.85);
  font-size: 13px;
  cursor: pointer;
}

.fun-report__mode--active {
  background: #fff;
  color: #1f2d3d;
  font-weight: 600;
}

.fun-report__close {
  padding: 6px 14px;
  border-radius: 8px;
  border: 1px solid rgba(255, 255, 255, 0.5);
  background: transparent;
  color: rgba(255, 255, 255, 0.85);
  font-size: 13px;
  cursor: pointer;
}

.fun-report__scroll {
  flex: 1;
  overflow-y: auto;
  padding: 10px 22px 30px;
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.fun-report__scroll--center {
  align-items: center;
  justify-content: center;
}

.fun-report__card {
  width: min(860px, 94vw);
  padding: 20px 26px;
  border-radius: 14px;
  background: rgba(255, 255, 255, 0.96);
  color: #303133;
}

.fun-report__card-title {
  margin: 0 0 12px;
  font-size: 18px;
  font-weight: 700;
}

.fun-report__sub-title {
  margin: 0 0 6px;
  font-size: 14px;
  font-weight: 600;
  color: #606266;
}

.fun-report__stat {
  margin: 6px 0;
  font-size: 15px;
}

.fun-report__stat strong {
  font-size: 22px;
}

.fun-report__meta {
  font-size: 12px;
  color: #909399;
}

.fun-report__two-col {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 16px;
}

.fun-report__list {
  margin: 0;
  padding-left: 20px;
  font-size: 13px;
}

.fun-report__list li {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  padding: 3px 0;
}

.fun-report__name {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.fun-report__rank-value {
  flex-shrink: 0;
  color: #909399;
}

.fun-report__pager {
  display: flex;
  align-items: center;
  gap: 14px;
}

.fun-report__pager-info {
  font-size: 13px;
  color: rgba(255, 255, 255, 0.8);
}

/* 翻页过渡只作用于卡片层（不触碰根覆盖层 fixed） */
.fun-slide-fade-enter-active,
.fun-slide-fade-leave-active {
  transition: transform 0.25s ease, opacity 0.25s ease;
}

.fun-slide-fade-enter {
  transform: translateX(24px);
  opacity: 0;
}

.fun-slide-fade-leave-to {
  transform: translateX(-24px);
  opacity: 0;
}
</style>
