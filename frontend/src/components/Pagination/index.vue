<template>
  <div :class="{'hidden': hidden}" class="pagination-container">
    <el-pagination
      :background="background"
      :current-page.sync="currentPage"
      :page-size.sync="pageSize"
      :layout="layout"
      :page-sizes="pageSizes"
      :total="total"
      v-bind="$attrs"
      @size-change="handleSizeChange"
      @current-change="handleCurrentChange"
    />
  </div>
</template>

<script lang="ts">
import { Component, Prop, Vue } from 'vue-property-decorator'

@Component({
  name: 'Pagination'
})
export default class Pagination extends Vue {
  @Prop({ required: true }) total!: number
  @Prop({ default: 1 }) page!: number
  @Prop({ default: 20 }) limit!: number
  @Prop({ default: () => [10, 20, 30, 50] }) pageSizes!: number[]
  @Prop({ default: 'total, sizes, prev, pager, next, jumper' }) layout!: string
  @Prop({ default: true }) background!: boolean
  @Prop({ default: true }) autoScroll!: boolean
  @Prop({ default: false }) hidden!: boolean

  get currentPage(): number {
    return this.page
  }

  set currentPage(value: number) {
    this.$emit('update:page', value)
  }

  get pageSize(): number {
    return this.limit
  }

  set pageSize(value: number) {
    this.$emit('update:limit', value)
  }

  handleSizeChange(val: number) {
    this.$emit('pagination', { page: this.currentPage, limit: val })
    if (this.autoScroll) {
      this.scrollToTop()
    }
  }

  handleCurrentChange(val: number) {
    this.$emit('pagination', { page: val, limit: this.pageSize })
    if (this.autoScroll) {
      this.scrollToTop()
    }
  }

  scrollToTop() {
    window.scrollTo({
      top: 0,
      behavior: 'smooth'
    })
  }
}
</script>

<style scoped>
.pagination-container {
  background: #fff;
  padding: 0px 16px;
}
.pagination-container.hidden {
  display: none;
}
</style>
