# 工具链矩阵：桌面 Python 3.11 × Android Python 3.12（Phase 1.4）

> 对应计划: `PLANS/dual-mode-client.md` 第 2 节"Python 工具链"行与第 4 节条目 4。
> 原则：**建立明确的双版本支持边界，不把 pyproject 的目标版本机械改成 3.12。**

## 1. 矩阵

| 环境 | Python | 由来 | 说明 |
|---|---|---|---|
| 后端 Docker 镜像 | 3.11 | `backend/Dockerfile` | 长期运行主力；代码必须兼容 3.11 语法（f-string 嵌套引号等 3.12-only 语法禁止，见 2026-08-22 启动事故） |
| Windows 桌面打包 | 3.12.4 | `deploy/build-windows.bat` 的 `.venv-packaging` | PyInstaller onefile；与 Android 同为 3.12 但无 ABI 压力 |
| Linux 桌面打包 | 容器内 python3.11 | `deploy/build-linux.sh` | fpm deb/rpm |
| **Android（Chaquopy 17）** | **3.12（cp312）** | APK 内嵌 | native 依赖需 cp312 Android wheels（Phase 0B） |
| 开发/CI 类型检查 | 最低支持版本 = 3.11 | `backend/pyproject.toml` | 见下 |

## 2. 兼容边界规则

1. **语法下限 3.11**：`app/` 内禁止 3.12-only 语法（PEP 701 f-string 嵌套同类引号、
   type parameter 语法等）。Docker 3.11 是最低运行时，破坏即启动失败。
2. **mypy `python_version` 保持 "3.11"**：类型检查按最低支持版本执行，
   保证 3.11 环境不引入仅 3.12 可解的类型构造。Android 3.12 是超集运行时，
   无需单独配置。
3. **black `target-version` 保持 `['py311']`**：格式化产物必须 3.11 可解析。
4. **运行时分支检测**：安卓环境判定用
   `app.utils.connectivity.is_android_environment()`（`sys.getandroidapilevel` /
   `BTDECK_PLATFORM=android` / `TERMUX_VERSION`），**不使用**脆弱的路径猜测
   或 `is_android()` 静态分支承载配置语义（路径一律由原生层显式注入环境变量，
   见 `config-and-paths.md`）。
5. **依赖 ABI 分层**：
   - 纯 Python 依赖：桌面与 Android 共用 `backend/requirements.txt` 版本约束；
   - native 依赖（pydantic-core/bcrypt/regex/Pillow/pycryptodomex/gmssl）：
     桌面走 PyPI 官方 wheel；Android 走 `btdeck/android-wheels` PEP 503 索引
     （Phase 0B 交付），版本与 hash 锁定。
   - 桌面专用依赖（如 `ping3` 的 ICMP 路径）在 Android 通过运行时策略禁用
     （`utils.connectivity` 已统一：安卓自动禁 ICMP，走 TCP connect 计时）。
6. **CI 演进**（Phase 0B 起）：android-wheels 仓库 CI 增加
   "backend import graph × 四 ABI" 矩阵作业；桌面 CI 不变。两侧 Python
   版本升级必须独立评审、独立推进（禁止一次提交同时改动两端目标版本）。

## 3. 已核实的当前状态（2026-08-23）

- `backend/pyproject.toml`: mypy `python_version = "3.11"`、black
  `target-version = ['py311']` —— 与本矩阵一致，**无需改动**。
- 2026-08-22 已修复 `cleanup_executor.py` 的 3.12-only f-string（Docker 3.11
  SyntaxError 启动事故），教训已写入上表规则 1。
- Phase 1.3 依赖瘦身后：pandas/numpy（无 Android wheel 压力的大头）、sympy、
  common 已从运行依赖移除，native wheel 清单相应缩短。
