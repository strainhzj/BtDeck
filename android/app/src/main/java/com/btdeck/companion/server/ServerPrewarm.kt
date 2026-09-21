package com.btdeck.companion.server

import android.content.Context
import com.chaquo.python.Python
import com.chaquo.python.android.AndroidPlatform
import java.io.File
import java.util.concurrent.atomic.AtomicBoolean

/**
 * Python 解释器进程级启动互斥（prewarm 与 ServerService 并发 Python.start 防线）。
 *
 * Chaquopy 未承诺 Python.start 线程安全：预热线程与正式启动线程可能同时到达，
 * 以进程级锁串行 + isStarted 短路，后到者等待先到者完成后直接复用实例。
 */
object PythonBoot {
    private val bootLock = Any()

    fun ensureStarted(context: Context) {
        synchronized(bootLock) {
            if (!Python.isStarted()) {
                Python.start(AndroidPlatform(context.applicationContext))
            }
        }
    }
}

/**
 * 本机服务端预热（启动等待优化 2026-09-13）。
 *
 * 冷启动十几秒的大头是"迁移+深导入整个后端"在手机 CPU 上现场执行；
 * 本对象在用户尚未点"启动"时后台先做完这段（btdeck_server.prewarm：
 * 只做 init 三段，不动服务状态、不占端口），正式启动只剩端口绑定+
 * lifespan+健康自检（桌面实证 3.4s → 1.3s）。
 *
 * 触发点（进程内至多一次，[triggered] 防重入）：
 * - App 冷启（CompanionApp）：仅曾用过本机服务端的设备（lastPort>0）——
 *   纯伴侣用户不为此平白加载 Python 后端（百 MB 级内存代价）；
 * - 向导点开"本机服务端"卡片（WizardActivity）：首次使用者也能用阅读
 *   配置弹窗的时间做预热重叠。
 *
 * 预热失败只打日志：正式启动会重跑完整链路并走正式错误通道。
 */
object ServerPrewarm {
    private val triggered = AtomicBoolean(false)

    fun prewarmAsync(context: Context) {
        if (!ServerService.isAbiSupported()) return
        if (!triggered.compareAndSet(false, true)) return
        val app = context.applicationContext
        Thread(
            {
                runCatching {
                    PythonBoot.ensureStarted(app)
                    Python.getInstance()
                        .getModule(ServerService.MODULE)
                        .callAttr("prewarm", dataRoot(app))
                }.onFailure {
                    it.printStackTrace() // logcat 归因；预热尽力而为，不阻断正式启动
                }
            },
            "btdeck-prewarm",
        ).start()
    }

    fun dataRoot(context: Context): String =
        File(context.filesDir, ServerService.DATA_DIR).absolutePath
}
