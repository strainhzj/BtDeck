<template>
  <el-breadcrumb
    class="app-breadcrumb"
    separator="/"
  >
    <transition-group name="breadcrumb">
      <el-breadcrumb-item
        v-for="(item, index) in breadcrumbs"
        :key="item.path"
      >
        <span
          v-if="item.redirect === 'noredirect' || index === breadcrumbs.length-1"
          class="no-redirect"
        >{{ titleText(item.meta) }}</span>
        <a
          v-else
          @click.prevent="handleLink(item)"
        >{{ titleText(item.meta) }}</a>
      </el-breadcrumb-item>
    </transition-group>
  </el-breadcrumb>
</template>

<script lang="ts">
import { compile } from 'path-to-regexp'
import { Component, Vue, Watch } from 'vue-property-decorator'
import { RouteRecord, Route } from 'vue-router'
import { routeTitle } from '@/i18n'

@Component({
  name: 'Breadcrumb'
})
export default class extends Vue {
  private breadcrumbs: RouteRecord[] = [];

  @Watch('$route')
  private onRouteChange(route: Route) {
    // if you go to the redirect page, do not update the breadcrumbs
    if (route.path.startsWith('/redirect/')) {
      return
    }
    this.getBreadcrumb()
  }

  created() {
    this.getBreadcrumb()
  }

  private getBreadcrumb() {
    let matched = this.$route.matched.filter(
      item => item.meta && item.meta.title
    )
    const hasDashboard = matched.some(item => this.isDashboard(item))
    if (!hasDashboard) {
      matched = [
		{ path: '/dashboard', meta: { title: 'Dashboard', titleKey: 'navigation.routes.dashboard' } } as unknown as RouteRecord
      ].concat(matched)
    }
    this.breadcrumbs = matched.filter(item => {
      return item.meta && item.meta.title && item.meta.breadcrumb !== false
    })
  }

  private isDashboard(route: RouteRecord) {
    if (!route) {
      return false
    }
    return route.path === '/dashboard' || route.path === 'dashboard'
  }

  /** 面包屑标题：titleKey（桌面双语键）优先，回退 meta.title 中文原值 */
  private titleText(meta: unknown) {
    return routeTitle(meta)
  }

  private pathCompile(path: string) {
    // To solve this problem https://github.com/PanJiaChen/vue-element-admin/issues/561
    const { params } = this.$route
    const toPath = compile(path)
    return toPath(params)
  }

  private handleLink(item: any) {
    const { redirect, path } = item
    if (redirect) {
      this.$router.push(redirect)
      return
    }
    this.$router.push(this.pathCompile(path))
  }
}
</script>

<style lang="scss" scoped>
.el-breadcrumb__inner,
.el-breadcrumb__inner a {
  font-weight: 400 !important;
}

.app-breadcrumb.el-breadcrumb {
  display: inline-block;
  font-size: 14px;
  line-height: 50px;
  margin-left: 8px;

  .no-redirect {
    color: #97a8be;
    cursor: text;
  }
}
</style>
