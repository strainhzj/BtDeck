#!/usr/bin/env python3
"""BtDeck runtime diagnostics.

This script intentionally uses only the Python standard library for its own
diagnostics path. Project imports are attempted where useful, but failures are
reported and never stop the rest of the report.
"""

from __future__ import annotations

import ast
import datetime as dt
import hashlib
import importlib
import importlib.metadata
import os
import re
import sqlite3
import subprocess
import sys
import traceback
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple


SCRIPT_PATH = Path(__file__).resolve()
BACKEND_ROOT = SCRIPT_PATH.parents[1]
REPO_ROOT = BACKEND_ROOT.parent
APP_ROOT = BACKEND_ROOT / "app"
REPORT_PATH = BACKEND_ROOT / "docs" / "diagnostic-report.md"
# 历史幽灵版本（production schema 初始化遗留，不在迁移链）。
# 仅用于诊断报告展示；治理后新库不会再产生此版本（由 migrate_database 救援）。
PRODUCTION_SCHEMA_VERSION = "9aea25308aff"


def rel(path: Path | str) -> str:
    try:
        return str(Path(path).resolve().relative_to(REPO_ROOT))
    except Exception:
        return str(path)


def safe_str(value: Any) -> str:
    if value is None:
        return "(none)"
    text = str(value)
    return text.replace("\n", "\\n")


def truncate(value: Any, limit: int = 100) -> str:
    text = safe_str(value)
    return text if len(text) <= limit else text[:limit] + "..."


def read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return path.read_text(encoding="utf-8", errors="replace")


def md_escape(value: Any) -> str:
    text = safe_str(value)
    return text.replace("|", "\\|")


def table(headers: Sequence[str], rows: Sequence[Sequence[Any]]) -> str:
    if not rows:
        rows = [["(none)" for _ in headers]]
    lines = [
        "| " + " | ".join(md_escape(h) for h in headers) + " |",
        "| " + " | ".join("---" for _ in headers) + " |",
    ]
    for row in rows:
        padded = list(row) + [""] * (len(headers) - len(row))
        lines.append("| " + " | ".join(md_escape(v) for v in padded[: len(headers)]) + " |")
    return "\n".join(lines)


def bullets(items: Iterable[Any]) -> str:
    item_list = list(items)
    if not item_list:
        return "- (none)"
    return "\n".join(f"- {md_escape(item)}" for item in item_list)


def run_cmd(args: Sequence[str], cwd: Path = REPO_ROOT) -> Tuple[int, str, str]:
    try:
        proc = subprocess.run(
            list(args),
            cwd=str(cwd),
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=15,
            check=False,
        )
        return proc.returncode, proc.stdout.strip(), proc.stderr.strip()
    except Exception as exc:
        return 1, "", f"{type(exc).__name__}: {exc}"


def iter_py_files(*roots: Path) -> Iterable[Path]:
    for root in roots:
        if not root.exists():
            continue
        for path in root.rglob("*.py"):
            if any(part in {".venv", "__pycache__", ".pytest_cache"} for part in path.parts):
                continue
            yield path


def grep_py(pattern: str, *roots: Path) -> List[Path]:
    regex = re.compile(pattern)
    matches: List[Path] = []
    for path in iter_py_files(*roots):
        try:
            if regex.search(read_text(path)):
                matches.append(path)
        except Exception:
            continue
    return sorted(set(matches))


def ast_literal_values(path: Path) -> Dict[str, Any]:
    """Extract simple Settings class defaults without importing the module."""
    values: Dict[str, Any] = {}
    try:
        tree = ast.parse(read_text(path), filename=str(path))
    except Exception as exc:
        return {"__error__": f"{type(exc).__name__}: {exc}"}

    def eval_node(node: ast.AST) -> Any:
        try:
            return ast.literal_eval(node)
        except Exception:
            pass
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name) and node.func.id == "Field":
                for kw in node.keywords:
                    if kw.arg == "default":
                        return eval_node(kw.value)
            if isinstance(node.func, ast.Attribute):
                dotted = ast.unparse(node.func) if hasattr(ast, "unparse") else ""
                if dotted == "os.getenv" and node.args:
                    key = eval_node(node.args[0])
                    default = eval_node(node.args[1]) if len(node.args) > 1 else None
                    return os.getenv(str(key), default)
        if isinstance(node, ast.Attribute) and hasattr(ast, "unparse"):
            return ast.unparse(node)
        if hasattr(ast, "unparse"):
            return ast.unparse(node)
        return "<dynamic>"

    for item in tree.body:
        if isinstance(item, ast.ClassDef) and item.name == "Settings":
            for stmt in item.body:
                target_name = None
                value_node = None
                if isinstance(stmt, ast.AnnAssign) and isinstance(stmt.target, ast.Name):
                    target_name = stmt.target.id
                    value_node = stmt.value
                elif isinstance(stmt, ast.Assign) and stmt.targets and isinstance(stmt.targets[0], ast.Name):
                    target_name = stmt.targets[0].id
                    value_node = stmt.value
                if target_name and value_node is not None:
                    values[target_name] = eval_node(value_node)
    return values


def import_settings(module_name: str) -> Tuple[Optional[Any], Optional[str]]:
    sys.path.insert(0, str(BACKEND_ROOT))
    try:
        module = importlib.import_module(module_name)
        return getattr(module, "settings", None), None
    except Exception:
        return None, traceback.format_exc(limit=5).strip()
    finally:
        try:
            sys.path.remove(str(BACKEND_ROOT))
        except ValueError:
            pass


def settings_snapshot(module_name: str, path: Path) -> Tuple[List[List[Any]], List[str]]:
    imported, error = import_settings(module_name)
    static_values = ast_literal_values(path)
    rows: List[List[Any]] = []
    notes: List[str] = []
    for key in ("SECRET_KEY", "ACCESS_TOKEN_EXPIRE_MINUTES", "ALGORITHM"):
        static_value = static_values.get(key, "(unknown)")
        if imported is not None:
            actual_value = getattr(imported, key, None)
            source = "imported"
        else:
            actual_value = static_value
            source = "static fallback"
        rows.append([module_name, key, actual_value, source, static_value])
    if imported is not None:
        db_path = getattr(imported, "DATABASE_PATH", None)
        if db_path is not None:
            rows.append([module_name, "DATABASE_PATH", db_path, "imported", "(property/dynamic)"])
        allowed_hosts = getattr(imported, "ALLOWED_HOSTS", None)
        if allowed_hosts is not None:
            rows.append([module_name, "ALLOWED_HOSTS", allowed_hosts, "imported", static_values.get("ALLOWED_HOSTS", "(unknown)")])
    if error:
        notes.append(f"{module_name} import failed: {error.splitlines()[-1] if error else error}")
    return rows, notes


def derive_database_path() -> Tuple[Path, List[str]]:
    notes: List[str] = []
    settings, error = import_settings("app.core.config")
    if settings is not None:
        try:
            return Path(getattr(settings, "DATABASE_PATH")).resolve(), notes
        except Exception as exc:
            notes.append(f"app.core.config.settings.DATABASE_PATH read failed: {type(exc).__name__}: {exc}")
    elif error:
        notes.append(f"app.core.config import failed while deriving DB path: {error.splitlines()[-1]}")

    static_values = ast_literal_values(APP_ROOT / "core" / "config.py")
    config_dir = os.getenv("CONFIG_DIR") or static_values.get("CONFIG_DIR") or str(BACKEND_ROOT / "config")
    database_name = static_values.get("DATABASE_NAME") or "app.db"
    return (Path(config_dir) / str(database_name)).resolve(), notes


def sqlite_connect_readonly(db_path: Path) -> Tuple[Optional[sqlite3.Connection], Optional[str]]:
    if not db_path.exists():
        return None, "database file does not exist"
    try:
        uri = f"file:{db_path}?mode=ro"
        conn = sqlite3.connect(uri, uri=True)
        conn.row_factory = sqlite3.Row
        return conn, None
    except Exception as exc:
        return None, f"{type(exc).__name__}: {exc}"


def table_exists(conn: sqlite3.Connection, name: str) -> bool:
    row = conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)).fetchone()
    return row is not None


def table_columns(conn: sqlite3.Connection, name: str) -> List[str]:
    try:
        return [row["name"] for row in conn.execute(f"PRAGMA table_info({quote_ident(name)})").fetchall()]
    except Exception:
        return []


def quote_ident(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def get_scalar(conn: sqlite3.Connection, sql: str, params: Sequence[Any] = ()) -> Any:
    row = conn.execute(sql, params).fetchone()
    if row is None:
        return None
    return row[0]


def detect_schema_hash() -> str:
    schema_path = BACKEND_ROOT / "config" / "production_complete_schema.sql"
    if not schema_path.exists():
        return "schema file missing"
    digest = hashlib.sha1(read_text(schema_path).encode("utf-8")).hexdigest()[:12]
    return f"file exists, sha1={digest}"


def database_diagnostics(db_path: Path) -> Tuple[str, List[str]]:
    notes: List[str] = []
    rows = [
        ["Path", db_path],
        ["Exists", db_path.exists()],
        ["Size", f"{db_path.stat().st_size} bytes" if db_path.exists() else "(missing)"],
    ]
    conn, error = sqlite_connect_readonly(db_path)
    if conn is None:
        rows.append(["Open read-only", error])
        return table(["Item", "Value"], rows), notes
    try:
        rows.append(["Open read-only", "ok"])
        rows.append(["PRAGMA journal_mode", get_scalar(conn, "PRAGMA journal_mode")])
        rows.append(["WAL enabled", str(get_scalar(conn, "PRAGMA journal_mode")).lower() == "wal"])
        if table_exists(conn, "alembic_version"):
            versions = [row[0] for row in conn.execute("SELECT version_num FROM alembic_version").fetchall()]
            rows.append(["alembic_version", ", ".join(versions) if versions else "(empty)"])
            rows.append([f"Contains {PRODUCTION_SCHEMA_VERSION}", PRODUCTION_SCHEMA_VERSION in versions])
        else:
            rows.append(["alembic_version", "table missing"])
            rows.append([f"Contains {PRODUCTION_SCHEMA_VERSION}", False])
        rows.append(["production_complete_schema.sql", detect_schema_hash()])
    except Exception as exc:
        notes.append(f"Database metadata query failed: {type(exc).__name__}: {exc}")
    finally:
        conn.close()
    return table(["Item", "Value"], rows), notes


def database_tables(db_path: Path) -> Tuple[str, List[str]]:
    conn, error = sqlite_connect_readonly(db_path)
    if conn is None:
        return table(["Table", "Rows"], [["(database unavailable)", error]]), []
    rows: List[List[Any]] = []
    notes: List[str] = []
    try:
        table_names = [
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
            ).fetchall()
        ]
        for name in table_names:
            try:
                count = get_scalar(conn, f"SELECT COUNT(*) FROM {quote_ident(name)}")
            except Exception as exc:
                count = f"count failed: {type(exc).__name__}: {exc}"
            marker = "key" if name in {"users", "cron_task", "task_logs", "bt_downloaders", "configs", "setting_templates"} else ""
            rows.append([name, count, marker])
    except Exception as exc:
        notes.append(f"Table listing failed: {type(exc).__name__}: {exc}")
    finally:
        conn.close()
    return table(["Table", "Rows", "Marker"], rows), notes


def cron_diagnostics(db_path: Path) -> Tuple[str, str, str, List[str]]:
    conn, error = sqlite_connect_readonly(db_path)
    if conn is None:
        unavailable = table(["Item", "Value"], [["cron_task", error]])
        return unavailable, unavailable, unavailable, []
    notes: List[str] = []
    all_rows: List[List[Any]] = []
    grouped: List[List[Any]] = []
    typed: List[List[Any]] = []
    try:
        if not table_exists(conn, "cron_task"):
            missing = table(["Item", "Value"], [["cron_task", "table missing"]])
            return missing, missing, missing, notes
        columns = table_columns(conn, "cron_task")
        select_cols = [c for c in ["task_id", "task_name", "task_code", "task_type", "task_status", "enabled", "executor", "last_execute_time", "dr"] if c in columns]
        for row in conn.execute(f"SELECT {', '.join(quote_ident(c) for c in select_cols)} FROM cron_task ORDER BY task_id").fetchall():
            all_rows.append([row[c] if c in row.keys() else "" for c in select_cols])
        for row in conn.execute("SELECT task_type, COUNT(*) FROM cron_task GROUP BY task_type ORDER BY task_type").fetchall():
            grouped.append([row[0], row[1]])
        for row in conn.execute(
            "SELECT task_name, task_type, enabled, executor, last_execute_time FROM cron_task WHERE task_type IN (0,1,2,3,4) ORDER BY task_type, task_id"
        ).fetchall():
            if row["task_type"] in (0, 1, 2, 3):
                typed.append([row["task_type"], row["task_name"], row["enabled"], truncate(row["executor"], 100), row["last_execute_time"]])
            elif row["task_type"] == 4:
                typed.append([row["task_type"], row["task_name"], row["enabled"], truncate(row["executor"], 180), row["last_execute_time"]])
        enhanced = conn.execute(
            "SELECT task_id, task_name, task_type, executor FROM cron_task WHERE lower(executor) LIKE '%enhanced_python_executor%' ORDER BY task_id"
        ).fetchall()
        if enhanced:
            notes.append("Tasks using enhanced_python_executor: " + ", ".join(f"{r['task_id']}:{r['task_name']}" for r in enhanced))
        else:
            notes.append("Tasks using enhanced_python_executor: none")
    except Exception as exc:
        notes.append(f"cron_task query failed: {type(exc).__name__}: {exc}")
    finally:
        conn.close()
    return (
        table(select_cols or ["cron_task"], all_rows),
        table(["task_type", "count"], grouped),
        table(["task_type", "task_name", "enabled", "executor/class path preview", "last_execute_time"], typed),
        notes,
    )


def package_version(names: Sequence[str]) -> List[List[Any]]:
    rows = []
    for name in names:
        try:
            rows.append([name, importlib.metadata.version(name), "installed"])
        except importlib.metadata.PackageNotFoundError:
            rows.append([name, "(not installed)", "missing"])
        except Exception as exc:
            rows.append([name, f"{type(exc).__name__}: {exc}", "error"])
    return rows


def requirements_diagnostics() -> Tuple[str, str]:
    req_path = BACKEND_ROOT / "requirements.txt"
    rows: List[List[Any]] = []
    jwt_libs: List[str] = []
    if req_path.exists():
        for line in read_text(req_path).splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            name = re.split(r"[<>=~!;\[]", stripped, maxsplit=1)[0].strip().lower()
            if name in {"python-jose", "jose", "pyjwt"}:
                jwt_libs.append(stripped)
        rows.append(["requirements.txt", rel(req_path), "exists"])
        rows.append(["JWT packages", ", ".join(jwt_libs) if jwt_libs else "(none)", "conflict" if len(jwt_libs) > 1 else "ok"])
    else:
        rows.append(["requirements.txt", rel(req_path), "missing"])

    lock_patterns = ["requirements.lock", "*requirements*.lock", "Pipfile.lock", "poetry.lock", "uv.lock", "*.lock"]
    lock_files: List[str] = []
    for pattern in lock_patterns:
        lock_files.extend(rel(p) for p in BACKEND_ROOT.rglob(pattern) if p.is_file())
    rows.append(["Lock files", ", ".join(sorted(set(lock_files))) if lock_files else "(none)", ""])
    return table(["Item", "Value", "Status"], rows), ", ".join(jwt_libs)


def git_tracked(path: Path) -> str:
    code, out, err = run_cmd(["git", "ls-files", "--", str(path.relative_to(REPO_ROOT))])
    if code != 0:
        return f"git check failed: {err or out}"
    return "yes" if out.strip() else "no"


def cors_diagnostics() -> str:
    rows: List[List[Any]] = []
    factory = APP_ROOT / "factory.py"
    main = APP_ROOT / "main.py"
    for path in [factory, main]:
        if not path.exists():
            continue
        text = read_text(path)
        if "CORSMiddleware" in text or "allow_origins" in text:
            allow_lines = [line.strip() for line in text.splitlines() if "allow_origins" in line or "allow_credentials" in line or "allow_methods" in line or "allow_headers" in line]
            rows.append([rel(path), "<br>".join(allow_lines)])
    settings, _ = import_settings("app.core.config")
    if settings is not None:
        rows.append(["app.core.config.settings.ALLOWED_HOSTS", getattr(settings, "ALLOWED_HOSTS", "(missing)")])
    else:
        static_values = ast_literal_values(APP_ROOT / "core" / "config.py")
        rows.append(["app.core.config static ALLOWED_HOSTS", static_values.get("ALLOWED_HOSTS", "(unknown)")])
    return table(["Source", "CORS value/code"], rows)


def admin_diagnostics(db_path: Path) -> Tuple[str, List[str]]:
    conn, error = sqlite_connect_readonly(db_path)
    if conn is None:
        return table(["Check", "Value"], [["users table", error]]), []
    rows: List[List[Any]] = []
    notes: List[str] = []
    try:
        if not table_exists(conn, "users"):
            return table(["Check", "Value"], [["users", "table missing"]]), notes
        columns = table_columns(conn, "users")
        if "username" not in columns:
            return table(["Check", "Value"], [["users.username", "column missing"]]), notes
        user = conn.execute("SELECT * FROM users WHERE username='admin' LIMIT 1").fetchone()
        rows.append(["admin user exists", user is not None])
        if user is not None:
            rows.append(["admin is_active", user["is_active"] if "is_active" in user.keys() else "(unknown)"])
            password_value = user["password"] if "password" in user.keys() else None
            rows.append(["password stored", bool(password_value)])
            rows.append(["admin/admin verified", verify_admin_password(password_value)])
    except Exception as exc:
        notes.append(f"Admin account query failed: {type(exc).__name__}: {exc}")
    finally:
        conn.close()
    return table(["Check", "Value"], rows), notes


def verify_admin_password(stored: Optional[str]) -> str:
    if not stored:
        return "no password value"
    try:
        from passlib.context import CryptContext  # type: ignore

        ctx = CryptContext(schemes=["bcrypt"], deprecated="auto")
        if stored.startswith("$2"):
            return str(ctx.verify("admin", stored))
    except Exception:
        pass
    try:
        import base64
        from Cryptodome.Cipher import AES  # type: ignore
        from Cryptodome.Util.Padding import unpad  # type: ignore

        yaml_secret = read_yaml_security_secret(BACKEND_ROOT / "config" / "config.yaml")
        if not yaml_secret:
            return "admin exists; cannot verify password (missing security.secret_key)"
        cipher = AES.new(str(yaml_secret).encode("utf-8"), AES.MODE_ECB)
        decrypted = unpad(cipher.decrypt(base64.b64decode(stored)), AES.block_size).decode("utf-8")
        decoded = base64.b64decode(decrypted).decode("utf-8")
        return str(decoded == "admin")
    except Exception as exc:
        return f"admin exists; verification failed: {type(exc).__name__}: {exc}"


def read_yaml_security_secret(path: Path) -> Optional[str]:
    if not path.exists():
        return None
    lines = read_text(path).splitlines()
    in_security = False
    for raw in lines:
        line = raw.rstrip()
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if not raw.startswith((" ", "\t")):
            in_security = line.split(":", 1)[0].strip() == "security"
            continue
        if in_security and line.strip().startswith("secret_key:"):
            value = line.split(":", 1)[1].strip().strip("'\"")
            return value or None
    return None


def build_report() -> str:
    generated = dt.datetime.now().astimezone().isoformat(timespec="seconds")
    sections: List[str] = [
        "# BtDeck Diagnostic Report",
        "",
        f"- Generated: {generated}",
        f"- Repository: `{REPO_ROOT}`",
        f"- Backend: `{BACKEND_ROOT}`",
    ]

    config_rows: List[List[Any]] = []
    config_notes: List[str] = []
    for module_name, path in [("app.config", APP_ROOT / "config.py"), ("app.core.config", APP_ROOT / "core" / "config.py")]:
        rows, notes = settings_snapshot(module_name, path)
        config_rows.extend(rows)
        config_notes.extend(notes)
    db_path, db_notes = derive_database_path()
    config_notes.extend(db_notes)

    database_url_consumers = grep_py(r"(?<![A-Z0-9_])DATABASE_URL(?![A-Z0-9_])", APP_ROOT)
    app_config_importers = grep_py(r"from\s+app\.config\s+import\s+settings|import\s+app\.config", APP_ROOT, BACKEND_ROOT / "tests")
    core_config_importers = grep_py(r"from\s+app\.core\.config\s+import\s+settings|import\s+app\.core\.config", APP_ROOT, BACKEND_ROOT / "tests")

    sections.extend(
        [
            "",
            "## 1. 配置系统诊断",
            "",
            table(["Module", "Key", "Actual value", "Source", "Static/default value"], config_rows),
            "",
            table(
                ["Item", "Value"],
                [
                    ["SECRET_KEY env set", "SECRET_KEY" in os.environ],
                    ["DATABASE_URL env set", "DATABASE_URL" in os.environ],
                    ["DATABASE_URL env value", os.getenv("DATABASE_URL", "(not set)")],
                    ["DATABASE_URL consumed by Python code", bool(database_url_consumers)],
                    ["Actual DATABASE_PATH", db_path],
                ],
            ),
            "",
            "### app.config importers",
            bullets(rel(p) for p in app_config_importers),
            "",
            "### app.core.config importers",
            bullets(rel(p) for p in core_config_importers),
            "",
            "### DATABASE_URL consumers",
            bullets(rel(p) for p in database_url_consumers),
        ]
    )
    if config_notes:
        sections.extend(["", "### 配置诊断备注", bullets(config_notes)])

    db_summary, db_summary_notes = database_diagnostics(db_path)
    db_tables, db_table_notes = database_tables(db_path)
    sections.extend(["", "## 2. 数据库诊断", "", db_summary, "", "### Tables and Row Counts", db_tables])
    db_notes_all = db_summary_notes + db_table_notes
    if db_notes_all:
        sections.extend(["", "### 数据库诊断备注", bullets(db_notes_all)])

    cron_all, cron_grouped, cron_typed, cron_notes = cron_diagnostics(db_path)
    sections.extend(
        [
            "",
            "## 3. 定时任务诊断",
            "",
            "### All cron_task Records",
            cron_all,
            "",
            "### Count by task_type",
            cron_grouped,
            "",
            "### Script/Internal Class Tasks",
            cron_typed,
            "",
            "### enhanced_python_executor",
            bullets(cron_notes),
        ]
    )

    x_access_files = grep_py(r"X-Access-Token|x-access-token", APP_ROOT / "api")
    depends_files = grep_py(r"Depends\s*\(\s*get_current_user\s*\)", APP_ROOT / "api")
    auth_rows = package_version(["python-jose", "jose", "PyJWT"])
    sections.extend(
        [
            "",
            "## 4. 认证诊断",
            "",
            table(["Package", "Version", "Status"], auth_rows),
            "",
            "### 手动读取 X-Access-Token 的 endpoint 文件",
            bullets(rel(p) for p in x_access_files),
            "",
            "### 使用 Depends(get_current_user) 的 endpoint 文件",
            bullets(rel(p) for p in depends_files),
        ]
    )

    admin_table, admin_notes = admin_diagnostics(db_path)
    sections.extend(
        [
            "",
            "## 5. 安全检查",
            "",
            "### 默认管理员账号",
            admin_table,
            "",
            "### CORS 配置",
            cors_diagnostics(),
            "",
            "### Git Tracking",
            table(
                ["Path", "Tracked"],
                [
                    [".env", git_tracked(REPO_ROOT / ".env")],
                    ["backend/.env", git_tracked(BACKEND_ROOT / ".env")],
                    ["backend/config/config.yaml", git_tracked(BACKEND_ROOT / "config" / "config.yaml")],
                ],
            ),
        ]
    )
    if admin_notes:
        sections.extend(["", "### 安全检查备注", bullets(admin_notes)])

    req_table, _ = requirements_diagnostics()
    sections.extend(["", "## 6. 依赖诊断", "", req_table])

    return "\n".join(sections) + "\n"


def main() -> int:
    report = build_report()
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(report, encoding="utf-8")
    print(report)
    print(f"Report saved to: {REPORT_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
