# -*- coding: utf-8 -*-
"""Android/桌面打包契约测试（dual-mode-client Phase 1.5）。

APK/exe 必须显式打包并测试 Alembic 资源、契约 JSON、frontend dist。
本文件锁定"包内资源存在性"与"spec 声明"两层契约：

1. 仓库资源：alembic.ini / alembic 迁移链（单 head）/ 契约 JSON /
   production_complete_schema.sql 必须存在且有效；
2. 两个 PyInstaller spec（Windows/Linux）的 datas 必须覆盖上述资源，
   frontend_dist 必须进入 datas；
3. 依赖瘦身回归：pandas/numpy 必须停留在 excludes（Phase 1.3），
   运行依赖文件不得再引入 pandas/sympy/common。

Chaquopy（Phase 3）将复用同一契约清单打 APK 包。
"""

import json
import re
from pathlib import Path

REPO_ROOT = Path(__file__).parents[3]  # tests/architecture/ → tests/ → backend/ → 仓库根
BACKEND_DIR = REPO_ROOT / "backend"
DEPLOY_DIR = REPO_ROOT / "deploy"
FRONTEND_PUBLIC_DIR = REPO_ROOT / "frontend" / "public"


class TestRepositoryPackageResources:
    def test_alembic_ini_exists_with_script_location(self):
        ini = BACKEND_DIR / "alembic.ini"
        assert ini.is_file(), "alembic.ini 缺失：迁移启动（frozen/Android）依赖它"
        content = ini.read_text(encoding="utf-8")
        match = re.search(r"script_location\s*=\s*(\S+)", content)
        assert match, "alembic.ini 未声明 script_location"
        assert (BACKEND_DIR / match.group(1)).is_dir()

    def test_migration_chain_single_head(self):
        from alembic.config import Config
        from alembic.script import ScriptDirectory

        cfg = Config(str(BACKEND_DIR / "alembic.ini"))
        cfg.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
        script = ScriptDirectory.from_config(cfg)
        heads = script.get_heads()
        assert len(heads) == 1, f"迁移链必须单 head，当前: {heads}"

    def test_contract_jsons_present_and_valid(self):
        contracts_dir = BACKEND_DIR / "app" / "contracts"
        json_files = list(contracts_dir.glob("*.json"))
        assert json_files, "契约 JSON 缺失：app.contracts import 时读取，缺失即启动崩溃"
        for json_file in json_files:
            payload = json.loads(json_file.read_text(encoding="utf-8"))
            assert isinstance(payload, dict)

    def test_production_schema_snapshot_exists(self):
        snapshot = BACKEND_DIR / "config" / "production_complete_schema.sql"
        assert snapshot.is_file(), "production_complete_schema.sql 缺失（init_schema_from_production 运维工具依赖）"


class TestSpecDatasContract:
    """两个 spec 的 datas/excludes 必须同步演进——历史上 Windows 修了 Linux 漏掉的先例多次。"""

    SPECS = ["btdeck-windows.spec", "btdeck.spec"]

    def test_both_specs_exist(self):
        for name in self.SPECS:
            assert (DEPLOY_DIR / name).is_file()

    def _spec_text(self, name: str) -> str:
        return (DEPLOY_DIR / name).read_text(encoding="utf-8")

    def test_datas_cover_runtime_resources(self):
        required_tokens = [
            "advanced_search_contract.json",  # app.contracts import 时读取
            "production_complete_schema.sql",
            "alembic.ini",
        ]
        for name in self.SPECS:
            text = self._spec_text(name)
            for token in required_tokens:
                assert token in text, f"{name} datas 缺少运行时资源: {token}"
            # alembic 目录以 (源, 'alembic') 形式进 datas
            assert "os.path.join(BACKEND_DIR, 'alembic'), 'alembic'" in text, f"{name} 未打包 alembic 迁移目录"

    def test_frontend_dist_packaged(self):
        for name in self.SPECS:
            text = self._spec_text(name)
            assert "frontend_dist" in text, f"{name} 未打包 frontend_dist"
            assert "Frontend index.html not found" in text, f"{name} 缺少前端缺失时的显式报错"

    def test_pandas_numpy_stay_excluded(self):
        """Phase 1.3 依赖瘦身回归：Excel 导出已 openpyxl 直写，pandas/numpy 不得回流打包。"""
        for name in self.SPECS:
            text = self._spec_text(name)
            excludes_block = text.split("excludes=[", 1)[1].split("],", 1)[0]
            for banned in ("'pandas'", "'numpy'"):
                assert banned in excludes_block, f"{name} excludes 缺少 {banned}"
            hiddenimports_block = text.split("hiddenimports = [", 1)[1].split("\n]", 1)[0]
            for banned in ("'pandas'", "'numpy'"):
                assert banned not in hiddenimports_block, f"{name} hiddenimports 重新引入 {banned}"


class TestWindowsBrandIconContract:
    """Windows 主程序、运行窗口、安装器和快捷方式必须复用同一品牌 ICO。"""

    def test_brand_ico_contains_shell_and_high_dpi_sizes(self):
        from PIL import Image

        icon_path = FRONTEND_PUBLIC_DIR / "favicon.ico"
        assert icon_path.is_file(), "Windows 品牌图标缺失"
        with Image.open(icon_path) as icon:
            assert icon.format == "ICO"
            sizes = set(icon.info.get("sizes", set()))

        required_sizes = {(16, 16), (32, 32), (48, 48), (256, 256)}
        assert required_sizes <= sizes, f"Windows ICO 缺少常用/高 DPI 尺寸: {required_sizes - sizes}"

    def test_pyinstaller_embeds_brand_icon(self):
        spec = (DEPLOY_DIR / "btdeck-windows.spec").read_text(encoding="utf-8")
        assert "WINDOWS_ICON" in spec
        assert "favicon.ico" in spec
        assert "icon=WINDOWS_ICON" in spec
        assert "icon=None" not in spec

    def test_inno_installer_and_shortcuts_use_brand_icon(self):
        inno = (DEPLOY_DIR / "btdeck.iss").read_text(encoding="utf-8")
        assert r"SetupIconFile=..\frontend\public\favicon.ico" in inno
        assert r"UninstallDisplayIcon={app}\{#AppExeName}" in inno
        shortcut_lines = [line for line in inno.splitlines() if line.startswith("Name:")]
        btdeck_shortcuts = [line for line in shortcut_lines if "{#AppName}" in line]
        assert len(btdeck_shortcuts) == 3
        assert all(r'IconFilename: "{app}\{#AppExeName}"' in line for line in btdeck_shortcuts)


class TestRuntimeRequirementsSlimming:
    """运行依赖不得再引入已移除的重型包（Phase 1.3 语义的防回归）。"""

    FILES = [
        BACKEND_DIR / "requirements.txt",
        DEPLOY_DIR / "requirements-linux-package.txt",
        DEPLOY_DIR / "requirements-windows-package.txt",
    ]
    BANNED = ("pandas", "numpy", "sympy", "common~")

    def test_no_banned_runtime_deps(self):
        for req_file in self.FILES:
            assert req_file.is_file()
            for line in req_file.read_text(encoding="utf-8").splitlines():
                stripped = line.strip()
                if not stripped or stripped.startswith("#"):
                    continue
                for banned in self.BANNED:
                    assert not stripped.startswith(banned), f"{req_file.name} 引入已移除依赖: {stripped}"

    def test_openpyxl_kept_for_excel_export(self):
        """W1/W2 架构（2026-08-28 起）：公共运行依赖统一由 requirements-lock
        供应（deploy 构建两段式安装的第一段），deploy 平台增量文件只允许
        PLATFORM_EXTRAS_WHITELIST 白名单。openpyxl 须保留在主清单与锁
        （打包制品的实际安装源）；复制进平台文件反而违反白名单契约
        （backend/tests/release/test_dependency_lock.py 强制）。历史版本本
        断言要求三个文件都含 openpyxl，系 deploy 文件曾是全量拷贝时代的
        旧口径（8/27 前后两批改造交叠期遗留）。
        """
        main_req = (BACKEND_DIR / "requirements.txt").read_text(encoding="utf-8")
        assert "openpyxl" in main_req, "backend/requirements.txt 缺少 openpyxl"
        lock = (BACKEND_DIR / "requirements-lock.txt").read_text(encoding="utf-8")
        assert re.search(r"^openpyxl==", lock, re.M), "requirements-lock.txt 缺少 openpyxl 精确锁定"
        for req_file in self.FILES[1:]:
            content = req_file.read_text(encoding="utf-8")
            assert "openpyxl" not in content, f"{req_file.name} 不应复制公共依赖 openpyxl（平台增量白名单架构）"
