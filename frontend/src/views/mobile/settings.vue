<template>
  <!--
    整页复用桌面设置页组件（双因素认证 + 修改密码，含锁定/失败计数/二维码
    全部状态机）：桌面页自带 768px 响应式断点，移动壳仅去除外层留白并
    承接移动内容区 12px 内边距，零重复实现。
  -->
  <div class="m-settings">
    <settings-page />
  </div>
</template>

<script lang="ts">
import { Component, Vue } from 'vue-property-decorator'
import SettingsPage from '@/views/settings/index.vue'

/**
 * 移动系统设置页：包装桌面 views/settings/index.vue（2FA 开启/停用流程、
 * 修改密码、强制改密表单同源同逻辑）；改密成功后桌面组件经 loginPathForMode
 * 分流回 /m/login。
 */
@Component({
  name: 'MobileSettings',
  components: { SettingsPage }
})
export default class MobileSettings extends Vue {
}
</script>

<style scoped>
.m-settings {
  min-height: 60vh;
}

/* 桌面页根容器自带 xl 外边距，嵌进移动内容区（已有 12px）会双重留白 */
.m-settings ::v-deep .settings-container {
  padding: 0;
}
</style>
