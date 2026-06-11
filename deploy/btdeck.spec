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
    # 后端配置模板
    (os.path.join(BACKEND_DIR, 'config'), 'config'),
]

# 如果前端已构建，包含静态文件
if os.path.exists(FRONTEND_DIST):
    datas.append((FRONTEND_DIST, 'frontend_dist'))
    print(f"[INFO] Including frontend dist: {FRONTEND_DIST}")
else:
    print(f"[WARN] Frontend dist not found at {FRONTEND_DIST}, skipping")

# 隐式导入（PyInstaller 可能检测不到的模块）
hiddenimports = [
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
    'sqlalchemy.dialects.sqlite',
    'sqlalchemy.sql.default_comparator',
    'aiosqlite',
    'alembic',
    'alembic.config',
    'alembic.command',
    'alembic.migration',
    'alembic.operations',
    'alembic.autogenerate',
    'pydantic',
    'pydantic.deprecated',
    'pydantic.deprecated.decorator',
    'pydantic_settings',
    'email_validator',
    'passlib',
    'passlib.handlers',
    'passlib.handlers.bcrypt',
    'jose',
    'pyotp',
    'qbittorrentapi',
    'transmissionrpc',
    'apscheduler',
    'yaml',
    'app',
    'app.api',
    'app.api.endpoints',
    'app.core',
    'app.models',
    'app.schemas',
    'app.services',
    'app.database',
    'app.factory',
]

a = Analysis(
    [os.path.join(BACKEND_DIR, 'app', 'main.py')],
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
        'numpy',
        'pandas',
        'scipy',
        'PIL',
        'PyQt5',
        'PyQt6',
        'pytest',
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
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,  # TODO: 添加应用图标
)
