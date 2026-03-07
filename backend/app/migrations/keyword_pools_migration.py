"""
Tracker关键词池迁移模块
扩展keyword_type字段支持四个池子：candidate, ignored, success, failed
"""

import sqlite3
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


class KeywordPoolsMigration:
    """关键词池迁移器"""

    def __init__(self, db_path: Path):
        self.db_path = db_path

    def migrate(self) -> bool:
        """
        执行迁移：扩展keyword_type字段支持四池子

        Returns:
            bool: 迁移是否成功
        """
        try:
            logger.info("开始关键词池迁移...")

            # 检查表是否存在
            if not self._table_exists():
                logger.info("tracker_keyword_config表不存在，跳过迁移")
                return True

            # 检查是否需要迁移
            if not self._needs_migration():
                logger.info("keyword_type字段已是新结构，跳过迁移")
                return True

            # 执行迁移
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()

                # 1. 创建新表结构
                self._create_new_table(cursor)

                # 2. 迁移数据（将'failure'映射为'failed'）
                self._migrate_data(cursor)

                # 3. 替换表
                self._replace_table(cursor)

                # 4. 重建索引
                self._recreate_indexes(cursor)

                conn.commit()

            logger.info("✅ 关键词池迁移完成")
            logger.info("✅ keyword_type字段已扩展为：candidate, ignored, success, failed")
            logger.info("✅ 现有'failure'数据已自动映射为'failed'")
            return True

        except Exception as e:
            logger.error(f"关键词池迁移失败: {e}")
            return False

    def _table_exists(self) -> bool:
        """检查表是否存在"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT name FROM sqlite_master
                    WHERE type='table' AND name='tracker_keyword_config'
                """)
                return cursor.fetchone() is not None
        except Exception as e:
            logger.error(f"检查表存在性失败: {e}")
            return False

    def _needs_migration(self) -> bool:
        """检查是否需要迁移"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()

                # 检查keyword_type字段的CHECK约束
                cursor.execute("PRAGMA table_info(tracker_keyword_config)")
                columns = cursor.fetchall()

                # 查找keyword_type列
                for col in columns:
                    if col[1] == 'keyword_type':
                        # 检查是否有CHECK约束包含'failure'
                        sql = f"SELECT sql FROM sqlite_master WHERE type='table' AND name='tracker_keyword_config'"
                        cursor.execute(sql)
                        table_sql = cursor.fetchone()[0] if cursor.fetchone() else ""

                        # 如果包含'failure'但不包含'candidate'，则需要迁移
                        return 'failure' in table_sql and 'candidate' not in table_sql

                return False

        except Exception as e:
            logger.error(f"检查迁移需求失败: {e}")
            return True  # 保守策略：检查失败时认为需要迁移

    def _create_new_table(self, cursor):
        """创建新表结构"""
        cursor.execute("""
            CREATE TABLE tracker_keyword_config_new (
                keyword_id VARCHAR(36) PRIMARY KEY NOT NULL,
                keyword_type VARCHAR(20) NOT NULL CHECK(keyword_type IN ('candidate', 'ignored', 'success', 'failed')),
                keyword VARCHAR(200) NOT NULL,
                language VARCHAR(10),
                priority INTEGER NOT NULL DEFAULT 100,
                enabled BOOLEAN NOT NULL DEFAULT 1,
                category VARCHAR(50),
                description VARCHAR(500),
                create_time DATETIME NOT NULL,
                update_time DATETIME NOT NULL,
                create_by VARCHAR(50) NOT NULL DEFAULT 'admin',
                update_by VARCHAR(50) NOT NULL DEFAULT 'admin',
                dr INTEGER NOT NULL DEFAULT 0
            );
        """)
        logger.info("创建新表结构完成")

    def _migrate_data(self, cursor):
        """迁移数据，将'failure'映射为'failed'"""
        cursor.execute("""
            INSERT INTO tracker_keyword_config_new
            SELECT
                keyword_id,
                CASE
                    WHEN keyword_type = 'failure' THEN 'failed'
                    ELSE keyword_type
                END as keyword_type,
                keyword,
                language,
                priority,
                enabled,
                category,
                description,
                create_time,
                update_time,
                create_by,
                update_by,
                dr
            FROM tracker_keyword_config
            WHERE dr = 0;
        """)

        # 统计迁移的数据量
        cursor.execute("SELECT COUNT(*) FROM tracker_keyword_config_new")
        count = cursor.fetchone()[0]
        logger.info(f"迁移了 {count} 条关键词数据")

    def _replace_table(self, cursor):
        """替换旧表"""
        # 删除旧表
        cursor.execute("DROP TABLE tracker_keyword_config;")
        logger.info("删除旧表完成")

        # 重命名新表
        cursor.execute("ALTER TABLE tracker_keyword_config_new RENAME TO tracker_keyword_config;")
        logger.info("重命名新表完成")

    def _recreate_indexes(self, cursor):
        """重建索引"""
        # 删除可能存在的临时索引
        cursor.execute("DROP INDEX IF EXISTS idx_tracker_keyword_type_enabled_new;")
        cursor.execute("DROP INDEX IF EXISTS idx_tracker_keyword_language_new;")
        cursor.execute("DROP INDEX IF EXISTS idx_tracker_keyword_priority_new;")

        # 创建正式索引
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_tracker_keyword_type_enabled
            ON tracker_keyword_config(keyword_type, enabled);
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_tracker_keyword_language
            ON tracker_keyword_config(language);
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_tracker_keyword_priority
            ON tracker_keyword_config(priority);
        """)

        logger.info("重建索引完成")


def run_keyword_pools_migration(db_path: Path) -> bool:
    """
    执行关键词池迁移的便捷函数

    Args:
        db_path: 数据库文件路径

    Returns:
        bool: 迁移是否成功
    """
    migrator = KeywordPoolsMigration(db_path)
    return migrator.migrate()
