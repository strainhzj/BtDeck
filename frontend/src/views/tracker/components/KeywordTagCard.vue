<template>
  <div
    class="keyword-tag-card"
    draggable="true"
    :class="{'is-dragging': isDragging}"
    @dragstart="handleDragStart"
    @dragend="handleDragEnd"
    @click="$emit('click', keyword)"
  >
    <span class="keyword-tag-card__text" :title="keyword">{{ truncatedKeyword }}</span>
    <span
      class="keyword-tag-card__close"
      @click.stop="handleDelete"
    >
      ×
    </span>
  </div>
</template>

<script lang="ts">
import { Component, Vue, Prop } from 'vue-property-decorator'

@Component({
  name: 'KeywordTagCard'
})
export default class KeywordTagCard extends Vue {
  @Prop({ required: true }) keyword!: string
  @Prop({ default: 20 }) maxLength!: number

  isDragging = false

  get truncatedKeyword(): string {
    if (!this.keyword) {
      return ''
    }
    if (this.keyword.length > this.maxLength) {
      return this.keyword.substring(0, this.maxLength) + '...'
    }
    return this.keyword
  }

  handleDragStart(event: DragEvent) {
    this.isDragging = true
    if (event.dataTransfer) {
      event.dataTransfer.effectAllowed = 'move'
      event.dataTransfer.setData('text/plain', this.keyword)
    }
    this.$emit('dragstart', { keyword: this.keyword, event })
  }

  handleDragEnd(event: DragEvent) {
    this.isDragging = false
    this.$emit('dragend', { keyword: this.keyword, event })
  }

  handleDelete() {
    this.$emit('delete', this.keyword)
  }
}
</script>

<style lang="scss" scoped>
.keyword-tag-card {
  display: inline-flex;
  align-items: center;
  background: #ffffff;
  border: 1px solid #e5e7eb;
  border-radius: 8px;
  box-shadow: 0 1px 2px rgba(0, 0, 0, 0.05);
  padding: 8px 14px;
  cursor: grab;
  transition: all 0.2s ease;
  font-size: 14px;
  font-weight: 500;
  max-width: 160px;
  user-select: none;

  &:hover {
    box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
    transform: translateY(-2px);
    border-color: #d1d5db;

    .keyword-tag-card__close {
      opacity: 1;
    }
  }

  &:active {
    cursor: grabbing;
  }

  &.is-dragging {
    opacity: 0.5;
    cursor: grabbing;
    box-shadow: 0 8px 12px rgba(0, 0, 0, 0.15);
  }
}

.keyword-tag-card__text {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: #374151;
}

.keyword-tag-card__close {
  margin-left: 10px;
  width: 22px;
  height: 22px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #9ca3af;
  cursor: pointer;
  transition: all 0.2s;
  font-size: 18px;
  line-height: 1;
  flex-shrink: 0;
  opacity: 0;

  &:hover {
    background: #ef4444;
    color: white;
    transform: scale(1.1);
  }
}
</style>
