#!/usr/bin/env python3
"""把 BtDeck 后端完整资源 staging 到主仓 android 工程的服务端源集。

用法: stage-server.py [--btdeck <主仓路径>]   （默认与本脚本上溯两级）

产物（gitignored，android/app/src/server/）：
  python/app/**            ← backend/app（除 __pycache__）
  python/alembic/**        ← backend/alembic + backend/alembic.ini
  python/frontend/dist/**  ← frontend/dist（factory 候选路径 3 命中）
  python/btdeck_server.py  ← android/server-python/btdeck_server.py 副本
  server-requirements.txt  ← backend/requirements.txt + Android 覆写/DROP/追加

移植自 android-wheels 仓 scripts/stage-fullgraph.py（闸门判据 5/6 实证布局，
4096 与 ps16k AVD 均 9/9 全绿）。布局与后端锚定关系（零后端改动）：
  settings.ROOT_PATH = app/core/config.py 上溯两级 = staged python 目录 →
  migration 的 alembic.ini/alembic 绝对锚定与 factory 的 ROOT_PATH/frontend/dist
  候选路径同时命中。
"""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent  # 主仓根
ANDROID = REPO / "android"
DST = ANDROID / "app" / "src" / "server"

# Android 版本覆写：与 android-wheels 仓 stage-fullgraph.py 保持一致
# （当前为空：pydantic-core/bcrypt/greenlet/regex/pycryptodomex 已自建对齐后端 pin）
ANDROID_OVERRIDES: dict[str, str] = {}

# Android 暂不安装 pillow：自建 wheel 挂点在其自家构建后端的宿主 /usr/include 注入
# （~20 轮 CI 攻坚未破，登记 android-wheels docs/gate.md）；后端 cuser.py 已把
# qrcode/PIL 改为函数内延迟导入，完整启动链不再触碰 PIL——代价仅为 Android
# 服务端 2FA 二维码接口暂不可用（其余零影响）
ANDROID_DROP: list[str] = ["pillow"]


def copytree_clean(src: Path, dst: Path) -> int:
    n = 0
    for item in src.rglob("*"):
        if any(part in {"__pycache__", ".pytest_cache", ".mypy_cache"} for part in item.parts):
            continue
        if item.suffix in {".pyc", ".pyo"}:
            continue
        rel = item.relative_to(src)
        target = dst / rel
        if item.is_dir():
            target.mkdir(parents=True, exist_ok=True)
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(item, target)
            n += 1
    return n


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--btdeck", default=str(REPO))
    args = parser.parse_args()
    btdeck = Path(args.btdeck)
    backend = btdeck / "backend"
    frontend_dist = btdeck / "frontend" / "dist"
    bootstrap_src = ANDROID / "server-python" / "btdeck_server.py"
    for required in (backend / "app", backend / "alembic", backend / "alembic.ini", frontend_dist, bootstrap_src):
        if not required.exists():
            print(f"FAIL: 缺少 {required}" + (
                "\n      frontend/dist 需要先在 frontend/ 下 npm run build" if required == frontend_dist else ""
            ))
            return 1

    py_dst = DST / "python"
    if py_dst.exists():
        shutil.rmtree(py_dst)
    py_dst.mkdir(parents=True)

    n_app = copytree_clean(backend / "app", py_dst / "app")
    n_alembic = copytree_clean(backend / "alembic", py_dst / "alembic")
    shutil.copy2(backend / "alembic.ini", py_dst / "alembic.ini")
    # Chaquopy 源集会丢弃非包目录中的孤儿 .py（alembic/versions 整目录实证消失，
    # 而 frontend/dist 非 py 数据全量幸存）。加 __init__.py 成包又会遮蔽
    # requirements 里的真 alembic 库（run 实证 cannot import name 'command'）。
    # 方案：迁移脚本以 .pymig 数据扩展名打包（数据不被丢、目录保持命名空间形态
    # 不遮蔽真包——PEP 420 命名空间不阻断后置常规包），bootstrap 首跑物化回 .py。
    for f in (py_dst / "alembic").rglob("*.py"):
        f.rename(f.with_name(f.name + ".pymig"))
    n_dist = copytree_clean(frontend_dist, py_dst / "frontend" / "dist")
    shutil.copy2(bootstrap_src, py_dst / "btdeck_server.py")

    # 生成 requirements：逐行带出 + 覆写/DROP/追加（与 wheels 仓同规则）
    out_lines: list[str] = [
        "# 由 stage-server.py 生成——backend/requirements.txt + Android 版本覆写",
        "# 覆写原因：Chaquopy 官方仓库 cp312 现有 Android wheel 的版本差集",
    ]
    for line in (backend / "requirements.txt").read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        name = stripped.split("~")[0].split("=")[0].split(">")[0].split("<")[0].strip().lower()
        if name in ANDROID_DROP:
            out_lines.append(f"# ANDROID-DROP（自建 wheel 攻坚期）: {stripped}")
            continue
        override = ANDROID_OVERRIDES.get(name)
        if override:
            out_lines.append(f"{override}  # ANDROID-OVERRIDE（后端 pin: {stripped}）")
        else:
            out_lines.append(stripped)
    # tzdata 不在此追加：Android 平台特有补充在 app/build.gradle.kts 的
    # chaquopy pip install() 声明（同时作为 pip 配置生效锚点，见彼处注释）
    (DST / "server-requirements.txt").write_text("\n".join(out_lines) + "\n", encoding="utf-8")

    print(f"staged: app {n_app} 文件 / alembic {n_alembic} 文件 / frontend dist {n_dist} 文件")
    print(f"输出目录: {DST}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
