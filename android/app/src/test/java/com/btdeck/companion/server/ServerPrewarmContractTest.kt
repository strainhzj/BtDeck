package com.btdeck.companion.server

import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Assume.assumeTrue
import org.junit.Test
import java.io.File

/**
 * 本机服务端启动等待优化契约（2026-09-13：prewarm 预热 + 轮询粒度收敛）：
 * Chaquopy 运行链无法在 JVM 端到端复现（Python 运行时不在单测 classpath），
 * 沿用「源码契约」模式直读实现文件钉死关键结构——每条锚点对应实测过的坑：
 * - prewarm 动了 _state → 向导把"启动服务"误判为"已在运行"（状态镜像契约破坏）；
 * - prewarm 与 _bootstrap 不串行 → 冷首跑两线程同时对同一 SQLite 跑 alembic
 *   （database is locked → 启动失败）；
 * - Kotlin 1s 轮询粒度 → running 就绪后 UI 平均白等 0.5s（最多 1s）；
 * - 并发 Python.start → Chaquopy 未承诺线程安全（预热线程与正式启动撞车）；
 * - App 冷启无条件预热 → 纯伴侣用户平白加载 Python 后端（百 MB 级内存）。
 */
class ServerPrewarmContractTest {

    private fun source(relative: String): String {
        val file = File("src/main/java/com/btdeck/companion/$relative")
        assumeTrue("源文件不可见（非模块工作目录）：$file", file.isFile)
        return file.readText()
    }

    /** 从模块目录向上找仓库级真相源 android/server-python/btdeck_server.py。 */
    private fun pythonServerSource(): String? {
        var dir: File? = File(".").absoluteFile.parentFile
        while (dir != null) {
            val candidate = File(dir, "server-python/btdeck_server.py")
            // android/app 的上级就是 android/，命中即返回
            if (candidate.isFile) return candidate.readText()
            dir = dir.parentFile
        }
        return null
    }

    @Test
    fun pythonPrewarmDoesNotTouchStateAndSerializesInit() {
        val py = pythonServerSource()
        assumeTrue("android/server-python/btdeck_server.py 不可见（独立分发的 android 子目录），跳过", py != null)
        val s = py!!
        // 入口存在且经 Chaquopy 可调用（Kotlin callAttr("prewarm", dataRoot)）
        assertTrue("prewarm(data_root) 入口缺失", s.contains("def prewarm(data_root: str)"))
        // active 态跳过：starting/running 时 _bootstrap 正在做/已做完同样的事
        assertTrue(
            "prewarm 必须在 starting/running 态跳过",
            s.contains("(STATE_STARTING, STATE_RUNNING)"),
        )
        // 不动 _state：worker 只跑 init 三段，绝不出现 STATE_RUNNING/STATE_STARTING 写入
        val worker = Regex("def _prewarm_worker[\\s\\S]*?def start\\(").find(s)?.value ?: error("worker 段缺失")
        assertFalse(
            "prewarm worker 不得写服务状态（向导据此决定启动/打开）",
            worker.contains("STATE_"),
        )
        // 串行防线：_init_lock 同时被 _bootstrap 与 _prewarm_worker 持有
        val lockHolders = Regex("with _init_lock:").findAll(s).count()
        assertTrue(
            "_init_lock 应被 _bootstrap 与 _prewarm_worker 双双持有（防双迁移竞态），实际 $lockHolders 处",
            lockHolders >= 2,
        )
        // 重活三段共用：深导入迁移顺序契约只在 _init_phases 一处定义
        assertTrue("共享 _init_phases 缺失", s.contains("def _init_phases("))
        assertTrue(
            "_bootstrap 必须经 _init_phases 走 init 三段",
            s.contains("_init_phases(root)"),
        )
    }

    @Test
    fun pythonHealthPollIntervalIsTightened() {
        val py = pythonServerSource()
        assumeTrue("android/server-python/btdeck_server.py 不可见，跳过", py != null)
        val s = py!!
        assertTrue(
            "健康自检轮询应为 0.2s（原 1s 白等量化）",
            s.contains("_HEALTH_POLL_INTERVAL_S = 0.2"),
        )
        assertTrue(
            "健康循环必须消费 _HEALTH_POLL_INTERVAL_S 常量",
            s.contains("time.sleep(_HEALTH_POLL_INTERVAL_S)"),
        )
    }

    @Test
    fun kotlinPollIntervalIsTightenedWithChangeDetection() {
        val s = source("server/ServerService.kt")
        assertTrue(
            "状态轮询应为 200ms（原 1s 粒度 UI 白等）",
            s.contains("POLL_INTERVAL_MS = 200L"),
        )
        // 200ms 粒度下不变快照重复 notify 会 5Hz 刷通知：必须变更检测
        assertTrue(
            "轮询必须做快照变更检测（snapshot != last）",
            s.contains("snapshot != last"),
        )
        // starting 期间端口先出现（state 不变 port 变）：终态判断不得吞掉中间变更
        assertTrue("变更分支须保留终态短路", s.contains("snapshot.isTerminal"))
    }

    @Test
    fun pythonStartIsCentralizedBehindBootMutex() {
        val service = source("server/ServerService.kt")
        val prewarm = source("server/ServerPrewarm.kt")
        // Chaquopy 未承诺 Python.start 线程安全：预热与正式启动并发到达必须互斥
        assertTrue(
            "ServerService 必须经 PythonBoot.ensureStarted 启动解释器",
            service.contains("PythonBoot.ensureStarted("),
        )
        assertFalse(
            "ServerService 不得再直接 Python.start（绕过互斥）",
            Regex("Python\\.start\\(").containsMatchIn(service),
        )
        assertTrue(
            "ServerPrewarm 必须经 PythonBoot.ensureStarted 启动解释器",
            prewarm.contains("PythonBoot.ensureStarted("),
        )
        assertTrue(
            "PythonBoot 必须以进程级锁串行 + isStarted 短路",
            Regex("synchronized\\(bootLock\\)[\\s\\S]*?if \\(!Python\\.isStarted\\(\\)\\)[\\s\\S]*?Python\\.start\\(")
                .containsMatchIn(prewarm),
        )
    }

    @Test
    fun prewarmIsWiredWithOnceGuardAndMemoryGate() {
        val app = source("CompanionApp.kt")
        val wizard = source("ui/WizardActivity.kt")
        val prewarm = source("server/ServerPrewarm.kt")
        // App 冷启：仅曾用过的设备（lastPort>0），纯伴侣用户不加载 Python 后端
        assertTrue(
            "App 冷启预热必须以 lastPort > 0 为门（内存防线）",
            app.contains("lastPort > 0"),
        )
        assertTrue(
            "App 冷启预热必须保留 ABI 门",
            app.contains("ServerService.isAbiSupported()"),
        )
        // 向导：点开本机服务卡片即预热（首次使用者用阅读弹窗的时间重叠）
        assertTrue(
            "showLocalServerDialog 必须触发预热",
            wizard.contains("ServerPrewarm.prewarmAsync(this)"),
        )
        // 进程内至多一次：AtomicBoolean compareAndSet 防重入
        assertTrue(
            "prewarmAsync 必须 compareAndSet 防重入",
            prewarm.contains("triggered.compareAndSet(false, true)"),
        )
        // 预热 data_root 与正式启停同源（ServerService.DATA_DIR 单一真相）
        assertTrue(
            "预热 data_root 必须复用 ServerService.DATA_DIR",
            prewarm.contains("ServerService.DATA_DIR"),
        )
        // 预热失败静默：正式启动重跑完整链路走正式错误通道
        assertTrue(
            "prewarmAsync 失败不得外溢（runCatching 包裹）",
            prewarm.contains("runCatching {"),
        )
    }
}
