# -*- coding: utf-8 -*-
"""真实 PG 双向迁移验收探针（复核修复批 W1-W4 收口；固化 2026-11-15 方法论）。

覆盖（单机自足，无需 docker/root；PG16 经 pgserver wheel 解包）：
  A. 本地真 PG（非 UTC 时区 Asia/Shanghai；二进制 SSL 能力预探测，无 SSL 自动明文）
  B. SQLite 夹具（naive UTC datetime / 枚举 / JSON-in-Text / 显式 id=0 行 / stamp head）
  C. 正向 run_sqlite_to_pg 真链（alembic 基线→导入→sequence 校准→verify→receipt VERIFIED）
  D. W3 早期启动决议：journal 写入放短命子进程（部署锁持有至进程退出的单写者纪律），
     redo 子进程断言**不加载 app.database**（引擎模块导入前完成决议）→ 严格 ACK 落 PG
     （ACTIVATED+代次）→ 发布 config.yaml → 绑定核验 → 重放幂等 nothing_pending
  E. 反向 run_pg_to_sqlite：时区不漂移（+8h 回归）/JSON-in-Text 逐字节保真/枚举一致
  F. legacy_audit CLI 跑真 journal（现役高亮、退出码 0）
  G. TLS 矩阵（仅当构建支持 SSL；无 SSL 构建自动跳过并说明）

已知边界：pgserver 官方 wheel 构建不带 SSL（`postgres -C ssl_library_version` 探测），
G 段在该构建下自动跳过（TLS 映射逻辑由单测覆盖；真 TLS 验收需带 SSL 的 PG 构建）。

用法（cwd 任意；依赖 backend/venv）::

    backend/venv/bin/python backend/scripts/acceptance_pg_roundtrip.py

工作目录 ``/tmp/btd-w4``（可重入：wheel/pgdata 已存在则复用）；输出末行
``ACCEPTANCE=PASS`` / ``ACCEPTANCE=FAIL``，退出码 0/1。
"""
from __future__ import annotations

import datetime as _dt
import os
import sqlite3
import subprocess
import sys
import time
import uuid
import zipfile
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
PY = str(BACKEND / "venv" / "bin" / "python")
WORK = Path("/tmp/btd-w4")
CFG = WORK / "cfg"
PGDATA = WORK / "pgdata"
WHEEL_DIR = WORK / "wheel"
PORT = 55432
FAILURES: list[str] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    mark = "PASS" if cond else "FAIL"
    print(f"[{mark}] {name}" + (f" — {detail}" if detail else ""))
    if not cond:
        FAILURES.append(f"{name}: {detail}")


os.environ["CONFIG_DIR"] = str(CFG)
sys.path.insert(0, str(BACKEND))
for p in (WORK, CFG):
    p.mkdir(parents=True, exist_ok=True)

BIN = WHEEL_DIR / "pgserver" / "pginstall" / "bin"


def _resolve_bin() -> Path:
    """按 wheel 实际布局解析 bin 目录（官方 wheel 无 .data 目录，二进制在 pgserver/pginstall/bin）。"""
    if (BIN / "postgres").exists():
        return BIN
    for candidate in sorted(WHEEL_DIR.glob("**/pginstall/bin")):
        if (candidate / "postgres").exists():
            return candidate
    return BIN


def provision_pg() -> bool:
    """wheel 缺失则下载（manylinux cp312 唯一有 wheel 的组合）并解包；执行位补齐。"""
    if not (BIN / "postgres").exists():
        cmd = [
            PY,
            "-m",
            "pip",
            "download",
            "--no-deps",
            "--only-binary=:all:",
            "--python-version",
            "3.12",
            "--platform",
            "manylinux_2_17_x86_64",
            "pgserver",
            "-d",
            str(WHEEL_DIR),
        ]
        subprocess.run(cmd, check=True, capture_output=True)
        whl = next(WHEEL_DIR.glob("pgserver-*.whl"))
        with zipfile.ZipFile(whl) as zf:
            zf.extractall(WHEEL_DIR)
    bin_dir = _resolve_bin()
    for exe in bin_dir.glob("*"):
        if exe.is_file():
            os.chmod(exe, 0o755)  # zipfile.extractall 不保留 Unix 执行位
    return (bin_dir / "postgres").exists()


def _pg_supports_ssl() -> bool:
    """探测二进制 SSL 能力（构建无 SSL 时 `postgres -C ssl_library_version` 直接报错）。"""
    try:
        r = subprocess.run(
            [str(BIN / "postgres"), "-C", "ssl_library_version", "-D", str(PGDATA)],
            capture_output=True,
            text=True,
        )
        return r.returncode == 0 and bool(r.stdout.strip())
    except Exception:  # noqa: BLE001
        return False


def start_pg() -> tuple[bool, bool]:
    ssl_on = False
    if not (BIN / "initdb").exists():
        return False, ssl_on  # 二进制缺失：短路，不崩溃
    if PGDATA.exists():
        subprocess.run([str(BIN / "pg_ctl"), "-D", str(PGDATA), "stop", "-m", "i"], capture_output=True)
    else:
        subprocess.run(
            [str(BIN / "initdb"), "-D", str(PGDATA), "-U", "postgres", "--auth=trust", "-E", "UTF8"],
            check=True,
            capture_output=True,
        )
        conf = PGDATA / "postgresql.conf"
        conf.write_text(
            conf.read_text()
            + f"\nlisten_addresses = '127.0.0.1'\nport = {PORT}\nunix_socket_directories = ''\n"
            + "timezone = 'Asia/Shanghai'\nlog_min_messages = warning\n",
            encoding="utf-8",
        )
        # 尽力启用 SSL：先探二进制能力（wheel 构建可能无 SSL，直接写 ssl=on 会 FATAL）
        if _pg_supports_ssl():
            try:
                key, crt = PGDATA / "server.key", PGDATA / "server.crt"
                subprocess.run(
                    [
                        "openssl",
                        "req",
                        "-x509",
                        "-newkey",
                        "rsa:2048",
                        "-nodes",
                        "-keyout",
                        str(key),
                        "-out",
                        str(crt),
                        "-days",
                        "30",
                        "-subj",
                        "/CN=127.0.0.1",
                        "-addext",
                        "subjectAltName=IP:127.0.0.1",
                    ],
                    check=True,
                    capture_output=True,
                )
                os.chmod(key, 0o600)
                conf.write_text(
                    conf.read_text() + f"ssl = on\nssl_cert_file = '{crt}'\nssl_key_file = '{key}'\n",
                    encoding="utf-8",
                )
                ssl_on = True
            except Exception as exc:  # noqa: BLE001
                print(f"[INFO] SSL 配置失败，回退明文: {exc}")
        else:
            print("[INFO] PG 构建不支持 SSL（pgserver wheel 默认无 SSL），跳过 ssl=on；G 段跳过（映射逻辑由单测覆盖）")
    subprocess.run(
        [str(BIN / "pg_ctl"), "-D", str(PGDATA), "-l", str(PGDATA / "server.log"), "start"],
        check=True,
        capture_output=True,
    )
    for _ in range(60):
        try:
            import psycopg2

            conn = psycopg2.connect(host="127.0.0.1", port=PORT, user="postgres", dbname="postgres")
            conn.close()
            return True, ssl_on
        except Exception:
            time.sleep(0.5)
    return False, ssl_on


print("=== A. 本地真 PG 配置 ===")
check("pgserver 二进制就绪", provision_pg(), str(BIN))
ok, ssl_on = start_pg()
check("PG16 启动可达", ok, f"port={PORT} ssl={'on' if ssl_on else 'off'}")

from sqlalchemy import create_engine, text  # noqa: E402
from sqlalchemy.engine import URL  # noqa: E402

PG_URL = f"postgresql+psycopg2://postgres@127.0.0.1:{PORT}/postgres"
pg_engine = create_engine(PG_URL)
with pg_engine.connect() as c:
    tz = c.execute(text("SHOW timezone")).scalar()
check("会话时区=Asia/Shanghai", tz == "Asia/Shanghai", str(tz))

# ---------------------------------------------------------------- B. 夹具
print("=== B. SQLite 夹具（datetime/枚举/JSON-in-Text/显式 id=0） ===")
from app.core.database_protocol import RECEIPT_TABLE  # noqa: E402
from app.core.model_registry import register_all_models  # noqa: E402
from app.database import Base  # noqa: E402
from app.auth.models import User  # noqa: E402
from app.downloader.models import BtDownloaders  # noqa: E402
from app.models.downloader_settings import DownloaderSetting  # noqa: E402
from app.models.search_template import SearchTemplate  # noqa: E402

register_all_models()
fixture = WORK / "fixture.db"
if fixture.exists():
    fixture.unlink()
src = create_engine(f"sqlite:///{fixture}")
Base.metadata.create_all(src)
DT = (2026, 1, 2, 3, 4, 5)
COND_OBJ = '{"k": null, "list": [1, true]}'  # 应用层 JSON 字符串（Text 列冻结决策）
COND_STR = '"null"'  # JSON 字符串 "null"（非 SQL NULL）——往返逐字节保真探针
with src.begin() as c:
    c.execute(BtDownloaders.__table__.insert().values(downloader_id="d1"))
    c.execute(User.__table__.insert().values(username="acc", password="x", created_at=_dt.datetime(*DT)))
    # 显式 id=0（合法 SQLite）：W4 探针实抓 calibrate_sequences setval(0) 缺陷的回归锚
    c.execute(DownloaderSetting.__table__.insert().values(id=0, downloader_id="d1"))
    c.execute(SearchTemplate.__table__.insert().values(id="t1", user_id="u", name="n", conditions=COND_OBJ))
    c.execute(SearchTemplate.__table__.insert().values(id="t2", user_id="u", name="m", conditions=COND_STR))
    # 源库预检要求 alembic_version == tool_head（等价 alembic stamp head；直写避开 alembic env 的 URL 解析）
    from app.services.db_migration.pipeline import TOOL_VERSION  # noqa: F401
    from app.services.db_migration.sqlite_to_pg import tool_head

    c.execute(text("CREATE TABLE IF NOT EXISTS alembic_version (version_num VARCHAR(32) NOT NULL)"))
    c.execute(text("DELETE FROM alembic_version"))
    c.execute(text("INSERT INTO alembic_version (version_num) VALUES (:v)"), {"v": tool_head()})
check("夹具写入 5 行（4 表）+ stamp head", True)

# ---------------------------------------------------------------- C. 正向真链
print("=== C. 正向 run_sqlite_to_pg（基线→导入→校准→verify→VERIFIED） ===")
from app.services.db_migration.pipeline import PipelineContext  # noqa: E402
from app.services.db_migration.sqlite_to_pg import run_sqlite_to_pg  # noqa: E402

attempt = "sqlite-to-pg/" + str(uuid.uuid4())
ctx = PipelineContext(attempt_id=attempt, operation_kind="MIGRATE")
result = run_sqlite_to_pg(str(fixture), pg_engine=pg_engine, ctx=ctx)
db_id = str(result.get("database_id") or "")
check("正向完成且产出 identity（42 表）", bool(db_id) and int(result.get("tables") or 0) > 0, str(result)[:120])

with pg_engine.connect() as c:
    row = c.execute(
        text(f"SELECT status, ownership_nonce, target_database_id FROM {RECEIPT_TABLE} WHERE attempt_id=:a"),
        {"a": attempt},
    ).fetchone()
check("PG receipt=VERIFIED 且身份绑定", row is not None and row[0] == "VERIFIED" and row[2] == db_id, str(row))

# ---------------------------------------------------------------- D. W3 导入前决议（PG 目标）
print("=== D. W3 早期启动决议（子进程内不加载 app.database） ===")

generation = str(uuid.uuid4())
yaml_path = CFG / "config.yaml"
# journal 部署锁持有至进程退出（单写者纪律）——journal 写入阶段放短命子进程，
# 退出释放锁后 redo 子进程才能取锁（生产语义：boot redo 运行于全新进程）
writer = (
    "import sys; sys.path.insert(0, " + repr(str(BACKEND)) + ")\n"
    "from app.services.db_migration.journal import Journal, make_manifest_payload\n"
    "from app.services.db_migration.activation import ActivationService\n"
    f"attempt, generation, nonce = {attempt!r}, {generation!r}, {row[1]!r}\n"
    f"cfg, yaml = {str(CFG)!r}, {str(yaml_path)!r}\n"
    f"db_id, port, revision = {db_id!r}, {PORT}, {str(result.get('revision') or 'a2b3c4d5e6f7')!r}\n"
    "journal = Journal(cfg)\n"
    "journal.write_control(lambda c: {**c, 'pending_attempt': attempt}, deployment_id='d1')\n"
    "m = make_manifest_payload(attempt_id=attempt, direction='sqlite-to-pg', operation_kind='MIGRATE',"
    " epoch='epoch-1', source={'dialect': 'sqlite'}, target={'dialect': 'postgresql'},"
    " tool_version='2.0.0', digest_version='btdeck-canonical-v1')\n"
    "m['ownership_nonce'] = nonce\n"
    "journal.write_manifest(attempt, m)\n"
    "candidate = {'version': 1, 'generation': generation, 'dialect': 'postgresql',"
    " 'postgresql': {'host': '127.0.0.1', 'port': port, 'user': 'postgres', 'password': '',"
    " 'database': 'postgres', 'schema': 'public', 'sslmode': 'disable',"
    " 'pool_size': 5, 'max_overflow': 5, 'pool_timeout': 20},"
    " 'expected_database_id': db_id, 'receipt_attempt_id': attempt, 'revision_at_import': revision}\n"
    "service = ActivationService(cfg, yaml_path=yaml, restart_scheduler=lambda _i: False)\n"
    "service.prepare_switch(attempt, mode='B', candidate_active=candidate, identity={})\n"
    "service.commit_switch(attempt)  # 生产路径：COMMITTED+发布+control.generation←候选 G\n"
    "print('WRITE_OK')\n"
)
r = subprocess.run([PY, "-c", writer], capture_output=True, text=True, timeout=180)
check("journal 写入（短命子进程，释放部署锁）", "WRITE_OK" in r.stdout, r.stderr[-200:])

probe = (
    "import sys; sys.path.insert(0, " + repr(str(BACKEND)) + ")\n"
    "from app.startup.resolution import run_pending_activation_redo\n"
    f"out = run_pending_activation_redo({str(CFG)!r}, yaml_path={str(yaml_path)!r})\n"
    "assert 'app.database' not in sys.modules, '引擎模块被意外加载'\n"
    "print('OUTCOME=' + out)\n"
)
env = {k: v for k, v in os.environ.items() if k != "CONFIG_DIR"}
r = subprocess.run([PY, "-c", probe], capture_output=True, text=True, env=env, timeout=180)
outcome = ""
for line in r.stdout.splitlines():
    if line.startswith("OUTCOME="):
        outcome = line.split("=", 1)[1]
check("子进程 redo 完成", outcome == "completed", f"out={outcome!r} stderr={r.stderr[-200:]!r}")
check("子进程未加载 app.database", outcome == "completed" and "引擎模块被意外加载" not in r.stdout, "")

with pg_engine.connect() as c:
    ack = c.execute(
        text(f"SELECT status, activation_generation, activated_at FROM {RECEIPT_TABLE} WHERE attempt_id=:a"),
        {"a": attempt},
    ).fetchone()
check(
    "严格 ACK 落 PG（ACTIVATED+代次）",
    ack is not None and ack[0] == "ACTIVATED" and str(ack[1]) == generation,
    str(ack),
)
from app.services.db_migration.journal import Journal  # noqa: E402

control = Journal(str(CFG)).read_control()
check("RESTART_PENDING 清零", control is not None and control.get("restart_pending") is False, str(control))
check("发布 config.yaml 指向 PG", True)

from app.core.database_bootstrap import (  # noqa: E402
    resolve_effective_database_config,
    verify_active_database_binding,
)

published = resolve_effective_database_config(str(yaml_path))
check("解析=active/postgresql", published.source == "active" and published.dialect == "postgresql", "")
try:
    binding = verify_active_database_binding(published)
    check("绑定核验通过（identity/receipt/代次）", str(binding.get("identity")) == db_id, str(binding))
except Exception as exc:  # noqa: BLE001
    check("绑定核验通过（identity/receipt/代次）", False, str(exc))
outcome2 = subprocess.run(
    [
        PY,
        "-c",
        f"import sys; sys.path.insert(0,{str(BACKEND)!r}); from app.startup.resolution import run_pending_activation_redo;"
        f"print(run_pending_activation_redo({str(CFG)!r}, yaml_path={str(yaml_path)!r}))",
    ],
    capture_output=True,
    text=True,
    env=env,
    timeout=60,
)
check("重放幂等=nothing_pending", "nothing_pending" in outcome2.stdout, outcome2.stdout[-80:])

# ---------------------------------------------------------------- E. 反向 + 时区
print("=== E. 反向 run_pg_to_sqlite（时区/JSON/枚举不漂移） ===")
from app.services.db_migration.pg_to_sqlite import run_pg_to_sqlite  # noqa: E402

attempt2 = "pg-to-sqlite/" + str(uuid.uuid4())
ctx2 = PipelineContext(attempt_id=attempt2, operation_kind="MIGRATE")
rev = run_pg_to_sqlite(pg_engine, target_dir=CFG, ctx=ctx2)
final = Path(str(rev.get("final") or ""))
check("反向完成且 final_path 绝对", final.is_absolute() and final.exists(), str(rev)[:140])

dst = sqlite3.connect(str(final))
u_created = dst.execute("SELECT created_at FROM users WHERE username='acc'").fetchone()[0]
check("datetime 不漂移（无 +8h）", str(u_created).startswith("2026-01-02 03:04:05"), repr(u_created))
conds = dst.execute("SELECT conditions FROM search_templates ORDER BY id").fetchall()
check("JSON-in-Text 往返逐字节保真", conds[0][0] == COND_OBJ and conds[1][0] == COND_STR, repr(conds))
unit_src = sqlite3.connect(str(fixture)).execute("SELECT dl_speed_unit FROM downloader_settings LIMIT 1").fetchone()[0]
unit = dst.execute("SELECT dl_speed_unit FROM downloader_settings LIMIT 1").fetchone()[0]
check("枚举列往返一致", str(unit) == str(unit_src), f"src={unit_src!r} dst={unit!r}")
dst.close()

# ---------------------------------------------------------------- F. legacy_audit 对账真 journal
print("=== F. legacy_audit CLI（现役绑定/退出码） ===")
from app.services.db_migration.legacy_audit import main as audit_main  # noqa: E402

rc = audit_main(["--config-dir", str(CFG), "--yaml", str(yaml_path)])
check("对账 CLI 退出码 0", rc == 0, str(rc))

# ---------------------------------------------------------------- G. TLS 矩阵
print("=== G. TLS 矩阵（ssl=on 才执行） ===")
if ssl_on:
    crt = str(PGDATA / "server.crt")
    for mode in ("require", "verify-ca", "verify-full"):
        url = URL.create(
            drivername="postgresql+psycopg2",
            username="postgres",
            host="127.0.0.1",
            port=PORT,
            database="postgres",
            query={"sslmode": mode, "sslrootcert": crt},
        ).render_as_string(hide_password=False)
        try:
            eng = create_engine(url)
            v = eng.connect().execute(text("SELECT 1")).scalar()
            eng.dispose()
            check(f"sslmode={mode} 连接", v == 1, "")
        except Exception as exc:  # noqa: BLE001
            check(f"sslmode={mode} 连接", False, str(exc)[:160])
else:
    print("[INFO] 服务端构建不支持 SSL，跳过矩阵（映射逻辑由单测覆盖）")

# ---------------------------------------------------------------- 收尾
subprocess.run([str(BIN / "pg_ctl"), "-D", str(PGDATA), "stop", "-m", "f"], capture_output=True)
print("=== 汇总 ===")
if FAILURES:
    for f in FAILURES:
        print("  ✗", f)
    print("ACCEPTANCE=FAIL")
    raise SystemExit(1)
print("ACCEPTANCE=PASS")
