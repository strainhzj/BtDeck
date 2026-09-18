#!/usr/bin/env python3
"""P0 静态盘点脚本：桌面端中文文案提取去重 + M1 归属标记。
用法: cd PLANS/bilingual && python3 p0_extract.py
输出: copy-catalog.json + stdout 汇总
口径: 排除 views/mobile、demo、__tests__、tests、*.spec.*；整行注释不计；行内注释无法剥离（文档已说明）。
"""
import json
import os
import re
from collections import defaultdict

SRC = os.path.normpath(os.path.join(os.path.dirname(__file__), "../../frontend/src"))
OUT = os.path.join(os.path.dirname(__file__), "copy-catalog.json")

EXCLUDE_DIR_PARTS = ("views/mobile", "demo", "__tests__", "tests", "icons", "node_modules")
EXCLUDE_FILE_RE = re.compile(r"(\.spec\.|\.d\.ts$)")

ZH_PIECE = re.compile(
    r"[\u4e00-\u9fff][\u4e00-\u9fffA-Za-z0-9_%+\-]*"
    r"(?:[ \u3000]?[\u4e00-\u9fffA-Za-z0-9（()）％%./、，,：:；;！!？?…·\-\+～~×*]+)*"
    r"[\u4e00-\u9fff0-9A-Za-z%）)】」\]]?"
)
COMMENT_FULL = re.compile(r"^\s*(//|/\*|\*|<!--)")


def group_of(rel):
    p = rel.replace("\\", "/")
    if p.startswith("views/login"):
        return "auth"
    if p.startswith("views/dashboard"):
        return "dashboard"
    if p.startswith("views/downloader"):
        return "downloader"
    if p.startswith("views/tracker"):
        return "tracker"
    if p.startswith("views/recycle-bin"):
        return "recycleBin"
    if p.startswith("views/orphan-files"):
        return "orphanFiles"
    if p.startswith("views/tasks"):
        return "tasks"
    if p.startswith("views/logs"):
        return "logs"
    if p.startswith("views/query-templates"):
        return "search"          # 查询模板并入 search 域（P1 可拆）
    if p.startswith("views/settings"):
        return "settings"
    if p.startswith("views/torrents"):
        return "torrent"
    if p.startswith("components/torrents"):
        return "torrent"
    if p.startswith("components/tasks"):
        return "tasks"
    if p.startswith("layout/components/NotificationDrawer"):
        return "notifications"
    if p.startswith("layout"):
        return "navigation"
    if p in ("router.ts", "permission.ts", "App.vue", "main.ts") or p.startswith("views/404"):
        return "navigation"
    if p.startswith("types/scheduled-tasks") or p.startswith("types/task-logs"):
        return "tasks"
    if p.startswith("types/torrent"):
        return "torrent"
    if p.startswith("utils/request") or p.startswith("utils/error-normalize") or p.startswith("api/"):
        return "errors"
    if p.startswith("components"):
        return "common"
    if p.startswith(("types/", "utils", "filters", "store", "directive", "constants")):
        return "common"
    return "other"


# M1 归属：core=M1 必须完整；partial=文件部分范围；m2=M2 批次；generated=生成文件不直译
M1_CORE_EXACT = {
    "views/login/index.vue", "views/404.vue", "App.vue", "main.ts", "router.ts", "permission.ts",
    "views/dashboard/index.vue",
    "views/downloader/index.vue",
    "views/downloader/components/DownloaderCard.vue",
    "views/downloader/components/BasicSettingsTab.vue",
    "views/torrents/index.vue", "views/torrents/TorrentViewSwitcher.vue",
    "views/torrents/components/TorrentAddDialog.vue",
    "views/torrents/components/TorrentDetailDialog.vue",
    "views/torrents/components/TrackerDetailCard.vue",
    "views/torrents/components/TrackerOperationDialog.vue",
    "views/torrents/components/BatchOperationDialog.vue",
    "components/torrents/AdvancedSearchBuilder.vue",
    "components/torrents/AdvancedSearchWorkspace.vue",
    "components/torrents/AdvancedMultiSelect.vue",
    "components/torrents/CompactTable.vue",
    "components/torrents/ConditionValueInput.vue",
    "components/torrents/FilterGroup.vue",
    "components/torrents/PageSizeCombobox.vue",
    "components/torrents/SizeRangeFilter.vue",
    "components/torrents/VirtualScrollList.vue",
    "components/torrents/advancedSearchFields.ts",
    "components/torrents/advancedSearchState.ts",
    "views/query-templates/index.vue",
    "views/query-templates/components/QueryTemplateDialog.vue",
    "views/recycle-bin/index.vue",
    "views/torrents/utils/torrentBatch.ts",
    "views/torrents/mixins/torrentBatch.ts",
    "views/torrents/mixins/columnResize.ts",
    "views/torrents/mixins/detailTabsData.ts",
    "views/torrents/mixins/errorTooltipDismiss.ts",
    "views/torrents/mixins/speedPolling.ts",
    "utils/formatters.ts", "utils/request.ts", "utils/error-normalize.ts",
}
M1_PARTIAL_PREFIX = ("views/settings/", "layout/", "views/torrents/mixins/" "components/Pagination", "components/common",
                     "components/BatchButton", "components/ThemeSwitcher", "components/Hamburger",
                     "components/CollapsiblePanel", "types/", "store/", "api/")
M1_PARTIAL_EXACT = {
    "views/downloader/components/DownloaderSettingsDialog.vue",
    "components/torrents/DuplicateTorrentsDialog.vue",
    "components/torrents/QuickDeleteDuplicatesDialog.vue",
}


def m1_of(rel):
    p = rel.replace("\\", "/")
    if p.startswith("contracts/") and p.endswith(".generated.ts"):
        return "generated"
    if p in M1_CORE_EXACT or p.startswith("layout/"):
        return "core"
    if p in M1_PARTIAL_EXACT:
        return "partial"
    if p.startswith(M1_PARTIAL_PREFIX):
        return "partial"
    return "m2"


def scan_file(path, rel):
    entries = []
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            for lineno, line in enumerate(f, 1):
                if not ZH_PIECE.search(line):
                    continue
                if COMMENT_FULL.match(line):
                    continue  # 整行注释不计入文案
                for piece in ZH_PIECE.findall(line):
                    piece = piece.strip()
                    if piece and re.search(r"[\u4e00-\u9fff]", piece):
                        entries.append((piece, rel, lineno))
    except Exception as e:  # noqa: BLE001
        print(f"[warn] {rel}: {e}")
    return entries


def main():
    catalog = defaultdict(lambda: {"locations": [], "count": 0})
    file_stats = defaultdict(int)
    total_raw = 0
    for root, dirs, files in os.walk(SRC):
        dirs[:] = [d for d in dirs if d != "node_modules"]
        for fn in files:
            if not fn.endswith((".vue", ".ts", ".js")):
                continue
            full = os.path.join(root, fn)
            rel = os.path.relpath(full, SRC).replace("\\", "/")
            if any(part in rel for part in EXCLUDE_DIR_PARTS) or EXCLUDE_FILE_RE.search(fn):
                continue
            for piece, r, lineno in scan_file(full, rel):
                total_raw += 1
                rec = catalog[piece]
                rec["count"] += 1
                if len(rec["locations"]) < 12:
                    rec["locations"].append(f"{r}:{lineno}")
                file_stats[r] += 1

    items = []
    for zh, rec in catalog.items():
        loc0 = rec["locations"][0].split(":")[0] if rec["locations"] else ""
        items.append({
            "zh": zh,
            "count": rec["count"],
            "group": group_of(loc0) if loc0 else "other",
            "m1": m1_of(loc0) if loc0 else "other",
            "locations": rec["locations"],
        })
    items.sort(key=lambda x: (-x["count"], x["zh"]))

    with open(OUT, "w", encoding="utf-8") as f:
        json.dump({
            "generated_note": "P0 static scan; comment lines excluded; inline comments NOT stripped; "
                              "interpolation fragments appear split (e.g. 共/项); generated *.generated.ts "
                              "kept but flagged m1=generated",
            "scope": "frontend/src desktop files (views/mobile, demo, tests, *.spec.* excluded)",
            "raw_hits": total_raw,
            "unique_strings": len(items),
            "items": items,
        }, f, ensure_ascii=False, indent=1)

    by_group = defaultdict(lambda: [0, 0])
    by_m1 = defaultdict(lambda: [0, 0])
    m1g = defaultdict(int)
    for it in items:
        by_group[it["group"]][0] += 1
        by_group[it["group"]][1] += it["count"]
        by_m1[it["m1"]][0] += 1
        by_m1[it["m1"]][1] += it["count"]
        if it["m1"] in ("core", "partial"):
            m1g[it["group"]] += 1

    print(f"raw_hits={total_raw}  unique={len(items)}")
    print("\n[group] unique / occurrences")
    for g, (u, c) in sorted(by_group.items(), key=lambda kv: -kv[1][0]):
        print(f"  {g:<14} {u:>5} / {c:>6}")
    print("\n[m1] unique / occurrences")
    for g, (u, c) in sorted(by_m1.items(), key=lambda kv: -kv[1][0]):
        print(f"  {g:<10} {u:>5} / {c:>6}")
    print("\n[m1 core+partial by group]")
    for g, u in sorted(m1g.items(), key=lambda kv: -kv[1]):
        print(f"  {g:<14} {u:>5}")
    print("\n[top files by hits]")
    for r, c in sorted(file_stats.items(), key=lambda kv: -kv[1])[:20]:
        print(f"  {c:>5}  {r}")


if __name__ == "__main__":
    main()
