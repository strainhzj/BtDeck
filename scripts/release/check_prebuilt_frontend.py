#!/usr/bin/env python3
"""校验唯一前端构建消费一致性（release-artifact-equivalence-gate W2）。

用法：python check_prebuilt_frontend.py <manifest.json> <frontend_dist_dir>

release 模式的制品构建（build-windows.bat / build-linux.sh）在消费预构建前端前
必须调用：frontend/dist 的实时 manifest 哈希与 build_frontend.py 产出的清单一致，
证明没有第二个前端构建混入。失败非零退出。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from generate_build_info import build_frontend_asset_manifest  # noqa: E402


def main() -> int:
    if len(sys.argv) != 3:
        print(__doc__, file=sys.stderr)
        return 2
    manifest_path = Path(sys.argv[1])
    dist_dir = Path(sys.argv[2])
    if not manifest_path.is_file():
        print(f"[FAIL] 前端唯一构建 manifest 缺失：{manifest_path}", file=sys.stderr)
        print("       请先运行 python scripts/release/build_frontend.py", file=sys.stderr)
        return 1
    stored = json.loads(manifest_path.read_text(encoding="utf-8"))
    try:
        _, recomputed = build_frontend_asset_manifest(dist_dir)
    except Exception as exc:  # noqa: BLE001 - dist 缺失/为空等一律阻断
        print(f"[FAIL] frontend dist 不可用：{exc}", file=sys.stderr)
        return 1
    # 比较规范形态（canonical JSON），规避宿主/容器行尾差异
    import hashlib  # noqa: PLC0415 - 就地导入保持模块头部最小

    stored_canonical = hashlib.sha256(
        json.dumps(stored, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    ).hexdigest()
    if stored_canonical != recomputed:
        print(
            f"[FAIL] frontend manifest mismatch: stored={stored_canonical} "
            f"recomputed={recomputed}（dist 与唯一构建不一致，禁止在制品构建中重建前端）",
            file=sys.stderr,
        )
        return 1
    print(f"[OK] frontend dist matches single-build manifest ({recomputed[:12]}...)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
