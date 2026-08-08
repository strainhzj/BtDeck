# 正式机孤儿数据清理 / 损坏处置操作清单

> 背景：桌面副本 `app.db` 经检查存在多表物理损坏（orphan_file、
> orphan_current_candidate、task_logs、notification 及部分索引），DELETE/DROP
> 均因 `malformed` 失败。该副本是从正式机拷贝而来，**在副本上操作对正式环境
> 无影响**。本清单用于在**正式机原件**上操作。

---

## 第 0 步：定位正式机数据库（Docker 部署）

```bash
# 正式机上，找到 btdeck-backend 容器挂载的宿主库路径
docker inspect btdeck-backend --format \
  '{{range .Mounts}}{{.Source}}::{{.Destination}}{{println}}{{end}}' \
  | grep config

# 通常结果是：<某路径>/data/backend/config/app.db
# 记作 $DB，下文沿用
DB=/正式机实际路径/data/backend/config/app.db
```

---

## 第 1 步：先判断正式机原件是否损坏（决定走哪条路径）

> ⚠️ 这一步只读，不改库。但**必须先停后端容器**再检查，避免运行中的写入干扰判断。

```bash
docker stop btdeck-backend
```

### 1a. 跑完整性检查

```bash
python3 -c "
import sqlite3
db = sqlite3.connect('$DB')
rows = db.execute('PRAGMA integrity_check').fetchall()
print('结果:', rows[:3] if rows else '空')
print('OK' if rows == [('ok',)] else '损坏')
db.close()
"
```

### 1b. 逐表确认孤儿表能否读取

```bash
python3 -c "
import sqlite3
db = sqlite3.connect('$DB')
for t in ['orphan_file','orphan_scan_result','orphan_current_candidate','orphan_operation_lease']:
    try:
        n = db.execute(f'SELECT COUNT(*) FROM {t}').fetchone()[0]
        print(f'{t}: {n}  OK')
    except Exception as e:
        print(f'{t}: 损坏 -> {e}')
db.close()
"
```

### 根据结果分路径：

- **1b 显示全部 OK**（原件未损坏）→ 走 **路径 A（DELETE 清理）**
- **任一表损坏**（原件也坏了）→ 走 **路径 B（.recover 重建）**

---

## 路径 A：原件未损坏 → DELETE 清理（推荐，最简单）

直接用已验证的清理脚本：

```bash
# 把 tools/cleanup_orphan_data.py 传到正式机
python3 cleanup_orphan_data.py --db "$DB"

# 脚本会自动：备份 → 事务内删 4 张表 → 验证行数/外键/参照数据
```

清理完成后启动后端：

```bash
docker start btdeck-backend
```

---

## 路径 B：原件也损坏 → .recover 灾难重建

> 仅当第 1 步确认原件也损坏时才走此路径。会重建整个库文件。

### B1. 备份原件（务必）

```bash
cp "$DB" "$DB.bak.$(date +%Y%m%d_%H%M%S)"
```

### B2. 用 .recover 导出可救数据到新库

```bash
# 需要完整版 sqlite3 CLI（带 .recover），若正式机没有：
#   Debian/Ubuntu: apt-get install sqlite3
#   或用 Python 见 B2-alt
sqlite3 "$DB" ".recover" > /tmp/recover.sql

# 若 .recover 输出正常，导入到全新干净库
rm -f "$DB.new"
sqlite3 "$DB.new" < /tmp/recover.sql

# 验证新库完整性
sqlite3 "$DB.new" "PRAGMA integrity_check;"
```

### B2-alt. 若无 sqlite3 CLI，用 Python 抢救（逐表导出）

```bash
python3 -c "
import sqlite3, json
SRC='$DB'; DST='$DB.new'
import os
if os.path.exists(DST): os.remove(DST)
src = sqlite3.connect(SRC); dst = sqlite3.connect(DST)
# 复制 schema
schema = src.execute(\"SELECT sql FROM sqlite_master WHERE sql IS NOT NULL\").fetchall()
for (s,) in schema:
    try: dst.execute(s)
    except Exception as e: print('schema skip:', e)
dst.commit()
# 逐表复制数据（损坏表会跳过坏页，救多少算多少）
tables = [r[0] for r in src.execute(\"SELECT name FROM sqlite_master WHERE type='table'\").fetchall()]
for t in tables:
    try:
        rows = src.execute(f'SELECT * FROM \"{t}\"').fetchall()
        if rows:
            cols = [d[0] for d in src.execute(f'SELECT * FROM \"{t}\" LIMIT 0').description]
            ph = ','.join('?'*len(cols))
            dst.executemany(f'INSERT OR IGNORE INTO \"{t}\" ({','.join(cols)}) VALUES ({ph})', rows)
            dst.commit()
        print(f'{t}: {len(rows)} 行已复制')
    except Exception as e:
        print(f'{t}: 部分损坏跳过 -> {e}')
dst.execute('PRAGMA integrity_check')
print('新库完整性:', dst.execute('PRAGMA integrity_check').fetchall()[:3])
src.close(); dst.close()
"
```

### B3. 替换并验证

```bash
# 新库通过完整性检查后，替换原件（原件已备份）
mv "$DB.new" "$DB"

# 启动后端（应用启动时会自动跑 alembic 迁移，补回任何缺失的表/索引）
docker start btdeck-backend

# 观察启动日志，确认迁移无误
docker logs -f btdeck-backend | head -50
```

---

## 路径 B 后的清理（可选）

.recover 重建后，孤儿表已清空（损坏数据被丢弃）。若想确保干净，再跑一次：

```bash
python3 cleanup_orphan_data.py --db "$DB"
```

---

## ⚠️ 关键提醒

1. **每一步都先 `docker stop btdeck-backend`**，避免运行中写入与操作冲突
2. **任何替换前先备份原件**（路径 B 的 B1）
3. **原件很可能没坏**——桌面副本的损坏大概率是拷贝时正式服务还在写、WAL 未合并所致。
   所以大概率走简单的**路径 A**。先做第 1 步判断，别假设最坏。
4. 清理/修复完成后，**孤儿扫描仍会因 lpan 等路径映射为空而 fail-closed**。
   需在 BtDeck 前端「下载器设置 → 路径映射」补全 `/Downloads/lpan/Downloads/`
   等空 external 映射后，扫描才能成功并重新生成准确的孤儿列表。

---

## 附：损坏副本的诊断结论（供参考，无需操作）

桌面副本 `app.db` 损坏区域：
- `orphan_file` 表 + 其索引（rootpage 25247/25248/25250）
- `orphan_current_candidate` 表（rootpage 25305）
- `task_logs` 表（rootpage 114）
- `notification` 表（rootpage 17827）
- `ix_tracker_info_last_announce_msg` / `last_scrape_msg` 索引（rootpage 76/77）

核心业务表 `torrent_info`(22492 条)、`bt_downloaders`(4 条)、schema 均完好。
WAL checkpoint 返回正常 (0,0,0)，说明是数据页物理损坏而非 WAL 不一致。
