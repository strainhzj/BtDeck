#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
从生产数据库 Schema 自动初始化数据库

确保在任何环境首次启动时，都能得到与生产环境完全一致的数据库结构
"""

import os
import sqlite3
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

# 生产数据库 schema 文件路径
SCHEMA_FILE = Path(__file__).parent.parent.parent / 'config' / 'production_complete_schema.sql'

def init_database_from_production_schema(db_path: str) -> bool:
    """
    从生产数据库 schema 初始化数据库

    Args:
        db_path: 数据库文件路径

    Returns:
        bool: 是否成功初始化
    """
    if not Path(SCHEMA_FILE).exists():
        logger.error(f"Production schema file not found: {SCHEMA_FILE}")
        return False

    try:
        # 读取生产数据库的完整 schema
        with open(SCHEMA_FILE, 'r', encoding='utf-8') as f:
            schema_sql = f.read()

        # 连接到数据库并执行 schema
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # 执行完整的 schema SQL（包含所有表、索引、约束）
        cursor.executescript(schema_sql)

        # 标记数据库为最新版本（跳过有问题的迁移链）
        cursor.execute("""
            INSERT OR IGNORE INTO alembic_version (version_num)
            VALUES ('9aea25308aff')
        """)

        conn.commit()
        conn.close()

        logger.info(f"Database initialized successfully from production schema: {db_path}")
        logger.info("Database marked as latest version (9aea25308aff)")
        return True

    except Exception as e:
        logger.error(f"Failed to initialize database: {e}")
        import traceback
        traceback.print_exc()
        return False

def is_database_empty(db_path: str) -> bool:
    """检查数据库是否为空（需要初始化）"""
    if not Path(db_path).exists():
        return True

    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # 检查alembic_version表是否有数据（已初始化且标记为最新版本）
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='alembic_version'")
        has_alembic_table = cursor.fetchone()

        if has_alembic_table:
            # 检查是否已标记为最新版本
            cursor.execute("SELECT version_num FROM alembic_version")
            version = cursor.fetchone()
            conn.close()
            # 如果已是最新版本，不需要初始化
            return version is None or version[0] != '9aea25308aff'

        # 没有alembic_version表，说明是完全空的数据库
        conn.close()
        return True

    except Exception:
        return True

def ensure_database_initialized(db_path: str) -> bool:
    """
    确保数据库已初始化（如果为空则自动初始化）
    
    Args:
        db_path: 数据库文件路径
    
    Returns:
        bool: 是否成功
    """
    if is_database_empty(db_path):
        logger.info(f"Database is empty, initializing from production schema...")
        return init_database_from_production_schema(db_path)
    
    logger.info(f"Database already exists: {db_path}")
    return True

if __name__ == '__main__':
    import sys
    
    # 测试模式
    test_db = "C:/software/full_stack/btpManager_full_stack/btpManager/config/test_init.db"
    
    if Path(test_db).exists():
        os.remove(test_db)
    
    if init_database_from_production_schema(test_db):
        print("SUCCESS: Test database initialized!")
        
        # 验证表数量
        conn = sqlite3.connect(test_db)
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = cursor.fetchall()
        conn.close()
        
        print(f"Created {len(tables)} tables")
        sys.exit(0)
    else:
        print("FAILED: Could not initialize database")
        sys.exit(1)
