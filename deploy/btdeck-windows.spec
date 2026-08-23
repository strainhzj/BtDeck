# -*- mode: python ; coding: utf-8 -*-
# BtDeck PyInstaller 打包配置
# 打包后端 + 前端静态文件为单个可执行文件

import os
import sys
from pathlib import Path

block_cipher = None

# 项目根目录
PROJECT_ROOT = os.path.abspath(SPECPATH + '/..')
BACKEND_DIR = os.path.join(PROJECT_ROOT, 'backend')
FRONTEND_DIST = os.path.join(PROJECT_ROOT, 'frontend', 'dist')

# 收集前端静态文件（如果存在）
datas = [
    # 后端 alembic 迁移文件
    (os.path.join(BACKEND_DIR, 'alembic'), 'alembic'),
    (os.path.join(BACKEND_DIR, 'alembic.ini'), '.'),
    # 运行时数据文件：app.contracts 在 import 时读取契约 JSON（缺失即启动崩溃，
    # 2026-08-19 桌面打包实测发现）；schema 快照供 init_schema_from_production 运维工具使用
    (os.path.join(BACKEND_DIR, 'app', 'contracts', 'advanced_search_contract.json'), 'app/contracts'),
    (os.path.join(BACKEND_DIR, 'config', 'production_complete_schema.sql'), 'config'),
    # 后端配置模板
    # 安全修复（W12）：不再打包 backend/config 目录——其中含真实 config.yaml
    # （密钥）与开发库 app.db（历史构建已实证泄露，TOC 可查）。运行时
    # CONFIG_PATH 为 exe 同级 config/，首启由 init_config_file 自动生成。
]

# 如果前端已构建，包含静态文件
FRONTEND_INDEX = os.path.join(FRONTEND_DIST, 'index.html')
FRONTEND_ASSETS = os.path.join(FRONTEND_DIST, 'assets')

if not os.path.isfile(FRONTEND_INDEX):
    raise FileNotFoundError(f"Frontend index.html not found: {FRONTEND_INDEX}")
if not os.path.isdir(FRONTEND_ASSETS):
    raise FileNotFoundError(f"Frontend assets directory not found: {FRONTEND_ASSETS}")

datas.append((FRONTEND_DIST, 'frontend_dist'))
print(f"[INFO] Including frontend dist: {FRONTEND_DIST}")

# 隐式导入（PyInstaller 可能检测不到的模块）
hiddenimports = [
    # === ASGI / 服务器 ===
    'uvicorn.logging',
    'uvicorn.loops',
    'uvicorn.loops.auto',
    'uvicorn.protocols',
    'uvicorn.protocols.http',
    'uvicorn.protocols.http.auto',
    'uvicorn.protocols.websockets',
    'uvicorn.protocols.websockets.auto',
    'uvicorn.lifespan',
    'uvicorn.lifespan.on',
    'uvicorn.lifespan.off',
    # === 数据库 ===
    'sqlalchemy.dialects.sqlite',
    'sqlalchemy.sql.default_comparator',
    'aiosqlite',
    # === Alembic（frozen 模式 migrate_database 用编程式 API）===
    'alembic',
    'alembic.config',
    'alembic.command',
    'alembic.migration',
    'alembic.operations',
    'alembic.autogenerate',
    'alembic.runtime.migration',
    'alembic.script',
    'alembic.util',
    # === 配置 / 数据校验 ===
    'pydantic',
    'pydantic.deprecated',
    'pydantic.deprecated.decorator',
    'pydantic_settings',
    'email_validator',
    # === 安全 / 认证 ===
    'passlib',
    'passlib.handlers',
    'passlib.handlers.bcrypt',
    'pyotp',
    'gmssl',  # 国密 SM4 加密，app.database 模块级 import，PyInstaller 可能漏追踪
    'Cryptodome',
    'Cryptodome.Cipher',
    'Cryptodome.Cipher.AES',
    'Cryptodome.Util.Padding',
    # === 下载器客户端 ===
    'qbittorrentapi',
    'transmissionrpc',
    'transmission_rpc',
    # === 定时任务 ===
    'apscheduler',
    'croniter',
    # === 其他第三方隐式依赖 ===
    'yaml',
    'bencodepy',  # torrent 解析
    'ping3',  # 网络探测
    'requests',
    # qrcode 延迟导入 PIL 生成二维码图片，PyInstaller 静态分析检测不到，需显式声明
    'PIL',
    'PIL.Image',
    'qrcode',
    'qrcode.image',
    'qrcode.image.pil',
    # 审计日志 Excel 导出用 openpyxl 直写（延迟导入），PyInstaller 静态分析检测不到
    'openpyxl',
    # === app 包及其子包（确保 PyInstaller 收集所有子模块）===
    'app',
    'app.api',
    'app.api.endpoints',
    'app.api.models',
    'app.api.schemas',
    'app.auth',
    'app.core',
    'app.data',
    'app.downloader',
    'app.enums',
    'app.migrations',
    'app.models',
    'app.models.response',
    'app.repositories',
    'app.schemas',
    'app.services',
    'app.services.downloader_adapters',
    'app.services.tag_adapters',
    'app.startup',
    'app.tasks',
    'app.tasks.scheduler',
    'app.tasks.scheduler.torrent_sync',
    'app.torrents',
    'app.tracker',
    'app.user',
    'app.utils',
    'app.database',
    'app.factory',
    # === app.models 子模块（alembic env.py 和 ORM 依赖，确保 frozen 下可加载）===
    'app.models.search_template',
    'app.models.notification',
    'app.models.setting_templates',
    'app.models.torrent_tags',
    'app.models.downloader_capabilities',
    'app.models.downloader_settings',
    'app.models.downloader_path_maintenance',
    'app.models.speed_schedule_rules',
    'app.models.torrent_deletion_audit_log',
    'app.models.torrent_file_backup',
    'app.models.seed_transfer_audit_log',
]

a = Analysis(
    [os.path.join(BACKEND_DIR, 'app', 'desktop_main.py')],
    pathex=[BACKEND_DIR],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'tkinter',
        'matplotlib',
        'scipy',
        # 注意：以下模块不能排除——
        # PIL (Pillow): qrcode 生成二维码图片时依赖它
        # pandas/numpy 已随 dual-mode-client Phase 1.3 移除（Excel 导出改
        # openpyxl 直写，全仓零 import 已核实），显式排除防止传递依赖回流
        'pandas',
        'numpy',
        'PyQt5',
        'PyQt6',
        'pytest',
        'IPython',
        'jupyter',
        'notebook',
        'sphinx',
        'torch',
        'torchvision',
        'torchaudio',
        'transformers',
        'cv2',
        'panel',
        'bokeh',
        'llvmlite',
        'numba',
        'sklearn',
        'tensorflow',
        'pydantic_ai',
        'fastmcp',
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='btdeck',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,  # TODO: 添加应用图标
)
