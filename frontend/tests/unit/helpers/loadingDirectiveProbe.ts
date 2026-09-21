import Vue, { VNodeDirective, VueConstructor } from 'vue'

export interface LoadingDirectiveSnapshot {
  value: boolean
  modifiers: Record<string, boolean>
}

const snapshots = new WeakMap<HTMLElement, LoadingDirectiveSnapshot>()

function recordSnapshot(el: HTMLElement, binding: VNodeDirective): void {
  snapshots.set(el, {
    value: Boolean(binding.value),
    modifiers: { ...(binding.modifiers || {}) }
  })
}

export function installLoadingDirectiveProbe(localVue: VueConstructor<Vue>): void {
  localVue.directive('loading', {
    bind: recordSnapshot,
    update: recordSnapshot,
    unbind(el: HTMLElement) {
      snapshots.delete(el)
    }
  })
}

export function getLoadingDirectiveSnapshot(element: Element): LoadingDirectiveSnapshot | undefined {
  return snapshots.get(element as HTMLElement)
}
