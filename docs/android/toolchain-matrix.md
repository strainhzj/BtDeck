# 工具链矩阵：统一 Python 3.12 契约（2026-09-23 修订）

> 对应计划: `PLANS/dual-mode-client.md` 第 2 节"Python 工具链"行与第 4 节条目 4。
> 原则：**单一契约版本 3.12——最低支持版本 = 制品运行时 = CI 检查目标，三位一体。
> 不再维护多版本支持边界。**
>
> ## 决策记录（2026-09-23，用户批准）
>
> - **废止**前版"桌面 3.11 × Android 3.12 双版本边界"及"禁止机械改 pyproject 到
>   3.12"决策（原决策背景：当时 Docker/Linux 制品仍运行 3.11）。
> - **动因**：制品（Docker 3.11 / W0 bullseye 3.11 / 本地 Linux 打包 3.11）与检查
>   （CI 3.11 / mypy 3.11 / black py311）落后于已达标面（Windows 3.12.4、
>   Android Chaquopy 3.12、依赖锁以 3.12 生成），版本号并存 = 持续技术债：
>   双目标维护负担、语法禁令靠人肉约束（2026-08-22 启动事故）、未来升级路径翻倍、
>   制品与检查漂移窗口永存。
> - **语义**：3.11 **正式退役**——语法下限升为 3.12，mypy/black 按真实运行时检查，
>   PEP 701 嵌套 f-string 等 3.12 语法解禁。
> - **镜像核实**（Docker Hub API，2026-09-23）：`python:3.12-slim`
>   @ `sha256:2f17fc04…bbe06a9`（活跃更新）；`python:3.12-bullseye`
>   @ `sha256:7cc92904…5eea1c`（存在；bullseye 变体已冻结但与原 3.11-bullseye
>   冻结语义一致，非倒退；保留 bullseye 为 glibc 2.31 下限兼容 Rocky Linux 9）。

## 1. 矩阵

| 环境 | Python | 由来 | 说明 |
|---|---|---|---|
| 后端 Docker 镜像 | 3.12 | `backend/Dockerfile`（digest 锁定） | 长期运行主力 |
| Windows 桌面打包 | 3.12.4 | `deploy/build-windows.bat` 的 `.venv-packaging` | PyInstaller onefile（wine 构建容器 `btdeck-windows-builder` 的 winpython 版本由用户侧自行核验对齐） |
| Linux 桌面打包 | 3.12 | `deploy/build-linux.sh`（`BTDECK_PACKAGE_PYTHON_VERSION` 默认值）；CI W0 在 `python:3.12-bullseye` 构建 | fpm deb/rpm；glibc 2.31 下限兼容 Debian 12 / Rocky Linux 9 |
| **Android（Chaquopy 17）** | **3.12（cp312）** | APK 内嵌 | native 依赖需 cp312 Android wheels（Phase 0B） |
| CI 回归 / 发布门禁 | 3.12 | `.github/workflows/regression.yml`、`release-gate.yml` | 与制品运行时一致 |
| 开发/类型检查/格式化 | 契约版本 = 3.12 | `backend/pyproject.toml`（mypy `python_version="3.12"`、black `py312`） | 按真实运行时检查，不再按最弱目标 |
| 本机开发 venv | 3.12 | `backend/.venv`（uv 创建） | `backend/scripts/init.sh` 门槛 >=3.12 |

## 2. 兼容边界规则

1. **语法下限 3.12**：`app/` 内可使用 3.12 及以下全部语法（含 PEP 701 f-string
   嵌套同类引号、type parameter 语法）。禁止 3.13-only 语法（3.11 的
   `asyncio.timeout` 等既有 API 继续可用）。
2. **mypy `python_version` = "3.12"**：类型检查目标与制品运行时一致。
3. **black `target-version` = `['py312']`**：格式化产物 3.12 可解析。
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
   "backend import graph × 四 ABI" 矩阵作业。桌面与 Android 现已同为 3.12，
   后续若再升级 Python 版本，仍须**独立评审、独立推进**（禁止一次提交同时改动
   两端目标版本）。

## 3. 历史注记

- 2026-08-22 曾发生 `cleanup_executor.py` 3.12-only f-string 导致 Docker 3.11
  SyntaxError 启动事故——该约束随 3.11 退役而消失，事故教训保留于此。
- `tests/mcp/evidence/sdk-probe-py3.11-*.json` 为退役版本历史证据，继续锚定
  防篡改，不再作为现行矩阵缺口要求。
- 上一版矩阵（3.11×3.12 双版本）见 git 历史（2026-08-23 核实版）。
