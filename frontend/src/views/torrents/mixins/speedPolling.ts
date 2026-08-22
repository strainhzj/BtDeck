/**
 * 实时速度轮询 Mixin
 *
 * 两视图（index.vue / TraditionalView.vue）的 1 秒链式轮询逐字重复，
 * 抽到本 mixin 单点维护。loadActiveSpeed 由子类实现（两视图各有私有实现）。
 *
 * 防回归要点：
 * - 链式轮询在 await loadActiveSpeed 前后都检查 speedPollingActive，
 *   暂停/销毁期间在途请求返回后不会重新 arm 定时器。
 * - 后台标签页暂停（visibilitychange）：document.hidden 时停止轮询，
 *   恢复可见时先补一次刷新再重启轮询；监听器随 start/stop 成对注册/移除，
 *   组件销毁后不会再触发恢复逻辑。
 */
import Component from 'vue-class-component'
import { Vue } from 'vue-property-decorator'

@Component({ name: 'SpeedPollingMixin' })
export default class SpeedPollingMixin extends Vue {
  // ====== 轮询状态（子类不再各自声明） ======
  protected speedTimer: number | null = null
  protected speedPollingActive = false

  // ====== 子类覆写的活跃速度加载（两视图各有实现；基类默认空实现） ======
  protected async loadActiveSpeed(): Promise<boolean> {
    return false
  }

  /** 启动速度轮询（请求完成后等待1秒再发下一次）；注册后台可见性监听 */
  protected startSpeedPolling() {
    this.registerVisibilityListener()
    if (this.speedPollingActive) return
    this.speedPollingActive = true
    const poll = async() => {
      if (!this.speedPollingActive) return
      await this.loadActiveSpeed()
      if (!this.speedPollingActive) return
      // 请求完成后等待1秒再发下一次
      this.speedTimer = window.setTimeout(poll, 1000)
    }
    poll()
  }

  /** 停止速度轮询并移除可见性监听（组件销毁时调用） */
  protected stopSpeedPolling() {
    this.speedPollingActive = false
    if (this.speedTimer) {
      clearTimeout(this.speedTimer)
      this.speedTimer = null
    }
    this.removeVisibilityListener()
  }

  /** 后台标签页暂停：仅停轮询，保留监听以便恢复 */
  private pauseSpeedPolling() {
    this.speedPollingActive = false
    if (this.speedTimer) {
      clearTimeout(this.speedTimer)
      this.speedTimer = null
    }
  }

  /** 后台标签页恢复：重启链式轮询（startSpeedPolling 的首个 poll 即补一次刷新，避免双发） */
  private resumeSpeedPolling() {
    this.startSpeedPolling()
  }

  private onVisibilityChange = () => {
    if (document.hidden) {
      this.pauseSpeedPolling()
    } else {
      this.resumeSpeedPolling()
    }
  }

  private registerVisibilityListener() {
    document.addEventListener('visibilitychange', this.onVisibilityChange)
  }

  private removeVisibilityListener() {
    document.removeEventListener('visibilitychange', this.onVisibilityChange)
  }
}
