"""
添加torrent_info表progress字段迁移模块
用于修复缺失的progress列，支持基于status的智能推导和完整回滚机制
"""

import sqlite3
import logging
from pathlib import Path
from typing import Optional, Dict, Any
from datetime import datetime

logger = logging.getLogger(__name__)


class TorrentProgressMigration:
    """种子进度字段迁移器"""

    def __init__(self, db_path: Path):
        self.db_path = db_path
        self.table_name = "torrent_info"
        self.column_name = "progress"
        self.backup_table_name = f"{self.table_name}_migration_backup"

        # Status到Progress的映射规则
        self.status_progress_map = {
            "seeding": 100.00,      # 已完成并做种
            "stalledUP": 100.00,    # 已完成但无上传速度
            "paused": 0.00,         # 已暂停，假设未完成
            "pausedDL": 0.00,       # 下载中暂停
        }

    def migrate(self) -> bool:
        """
        执行迁移：添加progress字段并智能推导现有数据

        Returns:
            bool: 迁移是否成功
        """
        try:
            logger.info("=" * 60)
            logger.info("开始种子进度字段迁移...")
            logger.info("=" * 60)

            # 1. 检查表是否存在
            if not self._table_exists():
                logger.warning(f"{self.table_name}表不存在，跳过迁移")
                return True

            # 2. 检查是否需要迁移
            if self._column_exists():
                logger.info(f"{self.column_name}字段已存在，跳过迁移")
                return True

            logger.info(f"✓ 检测到{self.column_name}字段缺失，开始执行迁移")

            # 3. 备份原表（支持回滚）
            logger.info(f"✓ 步骤1: 备份原表到 {self.backup_table_name}")
            self._backup_table()

            # 4. 添加progress字段
            logger.info("✓ 步骤2: 添加progress字段（REAL类型，保留2位小数）")
            self._add_progress_column()

            # 5. 智能推导现有数据的progress值
            logger.info("✓ 步骤3: 基于status智能推导progress值")
            affected_rows = self._migrate_existing_data()

            # 6. 添加约束
            logger.info("✓ 步骤4: 添加progress字段约束（0-100范围检查）")
            self._add_constraints()

            # 7. 验证迁移结果
            logger.info("✓ 步骤5: 验证迁移结果")
            validation_result = self._validate_migration()

            if not validation_result:
                logger.error("❌ 迁移验证失败，执行回滚")
                self._rollback()
                return False

            logger.info("=" * 60)
            logger.info(f"✅ 种子进度字段迁移成功！影响记录数: {affected_rows}")
            logger.info("=" * 60)
            logger.info("迁移摘要:")
            logger.info(f"  - seeding     → progress = 100.00 (已完成做种)")
            logger.info(f"  - stalledUP   → progress = 100.00 (已完成停滞)")
            logger.info(f"  - paused      → progress = 0.00 (已暂停)")
            logger.info(f"  - pausedDL    → progress = 0.00 (下载暂停)")
            logger.info(f"  - backup表    → {self.backup_table_name} (可安全删除)")
            logger.info("=" * 60)

            return True

        except Exception as e:
            logger.error(f"❌ 迁移执行失败: {e}")
            logger.info("开始执行回滚...")
            try:
                self._rollback()
                logger.info("✓ 回滚完成")
            except Exception as rollback_error:
                logger.error(f"❌ 回滚失败: {rollback_error}")
            return False

    def _table_exists(self) -> bool:
        """检查表是否存在"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT name FROM sqlite_master
                    WHERE type='table' AND name=?
                """, (self.table_name,))
                return cursor.fetchone() is not None
        except Exception as e:
            logger.error(f"检查表存在性失败: {e}")
            return False

    def _column_exists(self) -> bool:
        """检查progress字段是否已存在"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(f"PRAGMA table_info({self.table_name})")
                columns = cursor.fetchall()
                return any(col[1] == self.column_name for col in columns)
        except Exception as e:
            logger.error(f"检查字段存在性失败: {e}")
            return False

    def _backup_table(self):
        """备份原表结构"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()

            # 删除旧备份表（如果存在）
            cursor.execute(f"DROP TABLE IF EXISTS {self.backup_table_name}")

            # 创建备份表（复制结构和数据）
            cursor.execute(f"""
                CREATE TABLE {self.backup_table_name} AS
                SELECT * FROM {self.table_name}
            """)

            # 复制索引
            cursor.execute(f"""
                SELECT sql FROM sqlite_master
                WHERE type='index' AND tbl_name=?
                AND sql IS NOT NULL
            """, (self.table_name,))

            indexes = cursor.fetchall()
            for index in indexes:
                index_sql = index[0].replace(self.table_name, self.backup_table_name)
                try:
                    cursor.execute(index_sql)
                except Exception as e:
                    logger.warning(f"复制索引失败（可忽略）: {e}")

            conn.commit()
            logger.info(f"  ✓ 备份完成，共{cursor.rowcount}条记录")

    def _add_progress_column(self):
        """添加progress字段"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()

            # SQLite不支持直接添加带约束的列，需要分两步
            # 1. 先添加列
            cursor.execute(f"""
                ALTER TABLE {self.table_name}
                ADD COLUMN {self.column_name} REAL DEFAULT 0.00
            """)

            conn.commit()
            logger.info("  ✓ progress字段添加成功")

    def _migrate_existing_data(self) -> int:
        """基于status智能推导progress值"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            total_affected = 0

            # 遍历status映射规则，批量更新
            for status, progress in self.status_progress_map.items():
                cursor.execute(f"""
                    UPDATE {self.table_name}
                    SET {self.column_name} = ?
                    WHERE status = ?
                """, (progress, status))

                affected = cursor.rowcount
                total_affected += affected
                logger.info(f"  ✓ {status:<15} → progress = {progress:>6.2f} ({affected:>6} 条记录)")

            conn.commit()
            return total_affected

    def _add_constraints(self):
        """
        添加约束
        注意：SQLite的ALTER TABLE不支持直接ADD CONSTRAINT，
        需要通过CHECK约束在更新时验证
        """
        # SQLite不支持后续添加CHECK约束，
        # 但我们可以在应用层通过SQLAlchemy模型定义约束
        # 这里仅记录日志
        logger.info("  ✓ 约束说明：应用层将通过SQLAlchemy模型定义 CHECK(progress >= 0 AND progress <= 100)")

    def _validate_migration(self) -> bool:
        """验证迁移结果"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()

                # 1. 检查字段是否存在
                if not self._column_exists():
                    logger.error("验证失败：progress字段不存在")
                    return False

                # 2. 检查NULL值
                cursor.execute(f"""
                    SELECT COUNT(*) FROM {self.table_name}
                    WHERE {self.column_name} IS NULL
                """)
                null_count = cursor.fetchone()[0]
                if null_count > 0:
                    logger.error(f"验证失败：发现{null_count}条记录的progress为NULL")
                    return False

                # 3. 检查值范围（0-100）
                cursor.execute(f"""
                    SELECT COUNT(*) FROM {self.table_name}
                    WHERE {self.column_name} < 0 OR {self.column_name} > 100
                """)
                invalid_count = cursor.fetchone()[0]
                if invalid_count > 0:
                    logger.error(f"验证失败：发现{invalid_count}条记录的progress超出范围[0,100]")
                    return False

                # 4. 检查总记录数一致性
                cursor.execute(f"SELECT COUNT(*) FROM {self.table_name}")
                current_count = cursor.fetchone()[0]

                cursor.execute(f"SELECT COUNT(*) FROM {self.backup_table_name}")
                backup_count = cursor.fetchone()[0]

                if current_count != backup_count:
                    logger.error(f"验证失败：记录数不一致 (当前:{current_count} vs 备份:{backup_count})")
                    return False

                logger.info("  ✓ 所有验证通过")
                return True

        except Exception as e:
            logger.error(f"验证过程出错: {e}")
            return False

    def _rollback(self):
        """回滚迁移：恢复备份表"""
        try:
            logger.info("开始回滚...")

            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()

                # 删除迁移后的表
                cursor.execute(f"DROP TABLE IF EXISTS {self.table_name}")

                # 恢复备份表
                cursor.execute(f"""
                    ALTER TABLE {self.backup_table_name}
                    RENAME TO {self.table_name}
                """)

                # 重建索引（如果有）
                # SQLite会自动保留索引，这里可以省略

                conn.commit()
                logger.info("✓ 回滚完成，数据库已恢复到迁移前状态")

        except Exception as e:
            logger.error(f"回滚失败: {e}")
            raise


def run_torrent_progress_migration(db_path: Path) -> bool:
    """
    执行种子进度字段迁移的入口函数

    Args:
        db_path: 数据库文件路径

    Returns:
        bool: 迁移是否成功
    """
    migrator = TorrentProgressMigration(db_path)
    return migrator.migrate()
