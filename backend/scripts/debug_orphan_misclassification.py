# -*- coding: utf-8 -*-
"""
根本原因验证 v2（高效）:孤儿文件是否处于「种子 save_path 之外」。
用逐级前缀 + dict 查找，O(深度) 每孤儿。
"""
import sqlite3
import os
import sys
import io
from collections import Counter

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

DB = os.environ.get("ORPHAN_DB", "E:/Users/huangzj/Desktop/app.db")
conn = sqlite3.connect(DB)
cur = conn.cursor()

SCAN = "14cf9aa0-9c0c-4b98-b80f-ab12615fa861"

NICK = {
    "b58ee7b2-b4a1-4168-9c78-3139dde684f3": "qb",
    "299c35b5-7b20-4ca1-a38f-7a53262f9112": "tr_lpan",
    "c04cc424-b16a-4265-91dc-d22e704988d8": "tr",
    "0254174a-fe30-4bc2-bc4f-b8232b133785": "tr_kpan",
}


def norm(path):
    p = str(path).replace("\\", "/")
    while "//" in p:
        p = p.replace("//", "/")
    if p != "/" and p.endswith("/"):
        p = p.rstrip("/")
    return p


def ancestors(npath):
    parts = npath.split("/")
    res = []
    for i in range(len(parts), 2, -1):
        res.append("/".join(parts[:i]))
    return res


# 种子: 名称前缀 -> 种子信息(用于判断 save_path)
# 我们以「孤儿路径命中的最深 save_path 根」为所属目录，以「孤儿路径中匹配种子 name 的段」找种子
cur.execute(
    """
    SELECT t.downloader_id, t.save_path, t.name, t.hash
    FROM torrent_info t JOIN bt_downloaders d ON d.downloader_id=t.downloader_id
    WHERE t.dr=0 AND t.enabled=1 AND t.deleted_at IS NULL AND t.save_path IS NOT NULL
      AND d.enabled=1 AND d.dr=0
    """
)
seed_rows = cur.fetchall()

# save_path 根 -> 该根下种子列表
savepath_index = {}
# 种子 name 前缀(每一级) -> [(save_path, downloader)]
name_prefix_index = {}
for dl, sp, name, hash_ in seed_rows:
    if not sp:
        continue
    sp_n = norm(sp)
    savepath_index.setdefault(sp_n, []).append((dl, name, hash_))
    if name:
        n = norm(name)
        parts = n.split("/")
        for i in range(len(parts), 0, -1):
            pfx = "/".join(parts[:i])
            name_prefix_index.setdefault(pfx, set()).add((sp_n, dl))

cur.execute(f"SELECT file_path, downloader_id, confidence FROM orphan_file WHERE scan_id='{SCAN}'")
orphans = cur.fetchall()
print(f"孤儿总数: {len(orphans)}")

savepath_sorted = sorted(savepath_index.keys(), key=len, reverse=True)

cat = Counter()
examples = {}

for path, dl_id, conf in orphans:
    npath = norm(path)
    # 1. 孤儿路径命中哪个 save_path 根(最深)
    hit_root = None
    for r in savepath_sorted:
        if npath == r or npath.startswith(r + "/"):
            hit_root = r
            break
    # 2. 孤儿路径中是否含种子 name 段(在 save_path 根之下的路径段)
    rel = npath[len(hit_root):].lstrip("/") if hit_root else npath
    # 逐级检查 rel 的前缀是否匹配某个种子的 name
    matched_seed_sps = set()
    if rel:
        rel_parts = rel.split("/")
        for i in range(len(rel_parts), 0, -1):
            pfx = "/".join(rel_parts[:i])
            if pfx in name_prefix_index:
                for sp_n, dl in name_prefix_index[pfx]:
                    matched_seed_sps.add((sp_n, dl))
                break
    if hit_root and matched_seed_sps:
        # 找到种子: 该种子的 save_path 是否 == hit_root?
        seed_sp = next(iter(matched_seed_sps))[0]
        if seed_sp == hit_root:
            cat["A_文件在所属种子save_path下"] += 1
        else:
            cat["B_文件不在所属种子save_path下(被移动/复制到其他目录)"] += 1
            if "B_文件不在所属种子save_path下(被移动/复制到其他目录)" not in examples:
                examples["B_文件不在所属种子save_path下(被移动/复制到其他目录)"] = (path, dl_id, conf, seed_sp, hit_root)
    elif hit_root:
        cat["C_在save_path根下但name不匹配(散文件)"] += 1
    else:
        cat["D_不在任何save_path根下"] += 1

print("\n=== 孤儿分类 ===")
for label, cnt in cat.most_common():
    print(f"  {label}: {cnt}")

for label, cnt in cat.most_common():
    if label.startswith("B"):
        path, dl_id, conf, seed_sp, hit_root = examples[label]
        print(f"\nB类示例:")
        print(f"  孤儿: {path}")
        print(f"    归属={NICK.get(dl_id, dl_id[:8])} | {conf}")
        print(f"    种子save_path: {seed_sp}")
        print(f"    孤儿所在目录根: {hit_root}")
        break

conn.close()
