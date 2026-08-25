<template>
  <img
    class="app-logo"
    :class="`app-logo--${variant}`"
    :src="imageSrc"
    :alt="alt"
    draggable="false"
  >
</template>

<script lang="ts">
import { Component, Prop, Vue } from 'vue-property-decorator'

type LogoVariant = 'full' | 'mark'

@Component({ name: 'AppLogo' })
export default class AppLogo extends Vue {
  @Prop({ type: String, default: 'mark' })
  readonly variant!: LogoVariant

  @Prop({ type: String, default: 'BtDeck' })
  readonly alt!: string

  get imageSrc(): string {
    const baseUrl = process.env.BASE_URL || '/'
    const prefix = baseUrl.endsWith('/') ? baseUrl : `${baseUrl}/`
    const filename = this.variant === 'full' ? 'btdeck-logo.png' : 'btdeck-mark.png'
    return `${prefix}img/brand/${filename}`
  }
}
</script>

<style scoped>
.app-logo {
  display: block;
  max-width: 100%;
  max-height: 100%;
  object-fit: contain;
  user-select: none;
}
</style>
