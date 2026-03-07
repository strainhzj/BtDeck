"""
数据库迁移功能模块
用于处理数据库结构的升级和数据迁移
"""

import sqlite3
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional
from app.core.config import settings
from app.database import SessionLocal, Base
from sqlalchemy import text
from gmssl import sm4, func

# 导入关键词池迁移模块
from app.migrations.keyword_pools_migration import run_keyword_pools_migration
from app.migrations.add_torrent_progress_migration import run_torrent_progress_migration

logger = logging.getLogger(__name__)


class DatabaseMigrator:
    """数据库迁移器"""

    def __init__(self):
        self.db_path = settings.DATABASE_PATH
        self.config_path = settings.YAML_PATH
        self.migration_table = "schema_migrations"  # 迁移记录表

    def run_migrations(self) -> bool:
        """
        执行所有必要的数据库迁移

        Returns:
            bool: 迁移是否成功
        """
        try:
            logger.info("开始数据库迁移...")

            # 检查数据库是否存在
            if not self.db_path.exists():
                logger.info("数据库文件不存在，跳过迁移")
                return True

            # 创建迁移记录表
            self._create_migration_table()

            success = True

            # 1. 修改字段类型迁移
            if not self._is_migration_completed("field_types_migration_v1"):
                success &= self._migrate_field_types()
                if success:
                    self._mark_migration_completed("field_types_migration_v1")

            # 2. 修改删除标记逻辑迁移
            if not self._is_migration_completed("delete_logic_migration_v1"):
                success &= self._migrate_delete_logic()
                if success:
                    self._mark_migration_completed("delete_logic_migration_v1")

            # 3. 加密敏感字段迁移
            if not self._is_migration_completed("encryption_migration_v1"):
                success &= self._migrate_encrypted_fields()
                if success:
                    self._mark_migration_completed("encryption_migration_v1")

            # 4. 扩展tracker_keyword_config表keyword_type字段支持四池子
            if not self._is_migration_completed("keyword_type_pools_migration_v1"):
                success &= run_keyword_pools_migration(self.db_path)
                if success:
                    self._mark_migration_completed("keyword_type_pools_migration_v1")
            # 5. 添加torrent_info表progress字段
            if not self._is_migration_completed("add_torrent_progress_column_v1"):
                success &= run_torrent_progress_migration(self.db_path)
                if success:
                    self._mark_migration_completed("add_torrent_progress_column_v1")


            if success:
                logger.info("数据库迁移完成")
            else:
                logger.error("数据库迁移失败")

            return success

        except Exception as e:
            logger.error(f"数据库迁移过程中发生错误: {e}")
            return False

    def _create_migration_table(self):
        """创建迁移记录表"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS schema_migrations (
                    migration_name TEXT PRIMARY KEY,
                    executed_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    success BOOLEAN DEFAULT 1
                )
            """)
            conn.commit()

    def _is_migration_completed(self, migration_name: str) -> bool:
        """检查迁移是否已完成"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT success FROM schema_migrations WHERE migration_name = ?",
                    (migration_name,)
                )
                result = cursor.fetchone()
                return result is not None and result[0] == 1
        except Exception as e:
            logger.error(f"检查迁移状态失败: {e}")
            return False

    def _mark_migration_completed(self, migration_name: str):
        """标记迁移已完成"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "INSERT OR REPLACE INTO schema_migrations (migration_name, success) VALUES (?, ?)",
                    (migration_name, True)
                )
                conn.commit()
                logger.info(f"标记迁移完成: {migration_name}")
        except Exception as e:
            logger.error(f"标记迁移状态失败: {e}")

    def _mark_migration_failed(self, migration_name: str):
        """标记迁移失败"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "INSERT OR REPLACE INTO schema_migrations (migration_name, success) VALUES (?, ?)",
                    (migration_name, False)
                )
                conn.commit()
                logger.info(f"标记迁移失败: {migration_name}")
        except Exception as e:
            logger.error(f"标记迁移失败状态失败: {e}")

    def _migrate_field_types(self) -> bool:
        """
        迁移字段类型：
        - bt_downloaders: is_search, enabled, is_ssl 从 String 改为 Boolean
        - torrent_info: enabled 从 Integer 改为 Boolean
        """
        try:
            logger.info("开始字段类型迁移...")

            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()

                # 检查表结构
                cursor.execute("PRAGMA table_info(bt_downloaders)")
                columns = cursor.fetchall()

                # 检查是否需要迁移 bt_downloaders 表
                bt_columns = {col[1]: col[2] for col in columns}

                # 迁移 bt_downloaders 表
                if self._needs_bt_downloaders_migration(bt_columns):
                    logger.info("迁移 bt_downloaders 表字段类型...")
                    self._migrate_bt_downloaders_table(cursor, conn)

                # 检查并迁移 torrent_info 表
                cursor.execute("PRAGMA table_info(torrent_info)")
                ti_columns = cursor.fetchall()
                ti_column_types = {col[1]: col[2] for col in ti_columns}

                if self._needs_torrent_info_migration(ti_column_types):
                    logger.info("迁移 torrent_info 表字段类型...")
                    self._migrate_torrent_info_table(cursor, conn)

                conn.commit()
                logger.info("字段类型迁移完成")
                return True

        except Exception as e:
            logger.error(f"字段类型迁移失败: {e}")
            return False

    def _migrate_delete_logic(self) -> bool:
        """
        迁移删除标记逻辑：
        - 将 dr 字段从 0=已删除 改为 0=未删除, 1=逻辑删除
        """
        try:
            logger.info("开始删除逻辑迁移...")

            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()

                # 检查是否有数据需要更新
                total_updated = 0

                # 检查 bt_downloaders 表
                cursor.execute("SELECT COUNT(*) FROM bt_downloaders WHERE dr IS NOT NULL AND dr IN (0, 1)")
                count = cursor.fetchone()[0]

                if count > 0:
                    logger.info(f"发现 bt_downloaders 表 {count} 条记录需要更新删除标记")
                    # 反转删除逻辑：原来的1（已删除）改为0（未删除），原来的0（未删除）改为1（逻辑删除）
                    cursor.execute("""
                        UPDATE bt_downloaders
                        SET dr = CASE
                            WHEN dr = 1 THEN 0
                            WHEN dr = 0 THEN 1
                            ELSE dr
                        END
                        WHERE dr IN (0, 1)
                    """)
                    total_updated += count

                # 检查 torrent_info 表
                cursor.execute("SELECT COUNT(*) FROM torrent_info WHERE dr IS NOT NULL AND dr IN (0, 1)")
                ti_count = cursor.fetchone()[0]

                if ti_count > 0:
                    logger.info(f"发现 torrent_info 表 {ti_count} 条记录需要更新删除标记")
                    cursor.execute("""
                        UPDATE torrent_info
                        SET dr = CASE
                            WHEN dr = 1 THEN 0
                            WHEN dr = 0 THEN 1
                            ELSE dr
                        END
                        WHERE dr IN (0, 1)
                    """)
                    total_updated += ti_count

                # 检查 tracker_info 表
                cursor.execute("SELECT COUNT(*) FROM tracker_info WHERE dr IS NOT NULL AND dr IN (0, 1)")
                tracker_count = cursor.fetchone()[0]

                if tracker_count > 0:
                    logger.info(f"发现 tracker_info 表 {tracker_count} 条记录需要更新删除标记")
                    cursor.execute("""
                        UPDATE tracker_info
                        SET dr = CASE
                            WHEN dr = 1 THEN 0
                            WHEN dr = 0 THEN 1
                            ELSE dr
                        END
                        WHERE dr IN (0, 1)
                    """)
                    total_updated += tracker_count

                if total_updated > 0:
                    conn.commit()
                    logger.info(f"删除逻辑迁移完成，更新了 {total_updated} 条记录")
                else:
                    logger.info("没有需要更新删除标记的记录")

                return True

        except Exception as e:
            logger.error(f"删除逻辑迁移失败: {e}")
            return False

    def _migrate_encrypted_fields(self) -> bool:
        """
        迁移需要加密的字段：
        - bt_downloaders.password: 使用SM4加密
        - tracker_info.tracker_url: 使用SM4加密
        """
        try:
            logger.info("开始加密字段迁移...")

            sm4_key = self._get_sm4_key()
            if not sm4_key:
                logger.error("无法获取SM4密钥，跳过加密迁移")
                return False

            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()

                # 迁移 bt_downloaders.password 字段
                password_updated = self._encrypt_passwords(cursor, conn, sm4_key)

                # 迁移 tracker_info.tracker_url 字段
                tracker_updated = self._encrypt_tracker_urls(cursor, conn, sm4_key)

                if password_updated or tracker_updated:
                    conn.commit()
                    logger.info("加密字段迁移完成")
                else:
                    logger.info("没有需要加密的字段")

                return True

        except Exception as e:
            logger.error(f"加密字段迁移失败: {e}")
            return False

    def _needs_bt_downloaders_migration(self, columns: Dict[str, str]) -> bool:
        """检查 bt_downloaders 表是否需要迁移"""
        return (
            columns.get('is_search') == 'TEXT' or
            columns.get('enabled') == 'TEXT' or
            columns.get('is_ssl') == 'TEXT'
        )

    def _needs_torrent_info_migration(self, columns: Dict[str, str]) -> bool:
        """检查 torrent_info 表是否需要迁移"""
        return columns.get('enabled') == 'INTEGER'

    def _needs_tracker_info_migration(self, columns: Dict[str, str]) -> bool:
        """检查 tracker_info 表是否需要迁移"""
        # 检查是否有未加密的tracker_url
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT COUNT(*) FROM tracker_info
                    WHERE tracker_url IS NOT NULL
                    AND tracker_url NOT LIKE 'sm4:%'
                    AND tracker_url != ''
                """)
                count = cursor.fetchone()[0]
                return count > 0
        except Exception:
            return True  # 如果检查失败，保守地认为需要迁移

    def _migrate_bt_downloaders_table(self, cursor, conn):
        """迁移 bt_downloaders 表"""
        # 创建临时表
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS bt_downloaders_temp (
                downloader_id TEXT PRIMARY KEY,
                nickname TEXT,
                host TEXT,
                username TEXT,
                password TEXT,
                is_search BOOLEAN DEFAULT 1,
                status TEXT,
                enabled BOOLEAN DEFAULT 1,
                downloader_type TEXT,
                port TEXT,
                is_ssl BOOLEAN DEFAULT 1,
                dr INTEGER DEFAULT 0
            )
        """)

        # 复制数据，转换数据类型
        cursor.execute("""
            INSERT INTO bt_downloaders_temp
            SELECT
                downloader_id,
                nickname,
                host,
                username,
                password,
                CASE
                    WHEN is_search IN ('True', 'true', '1', 'yes') THEN 1
                    ELSE 0
                END as is_search,
                status,
                CASE
                    WHEN enabled IN ('True', 'true', '1', 'yes') THEN 1
                    ELSE 0
                END as enabled,
                downloader_type,
                port,
                CASE
                    WHEN is_ssl IN ('True', 'true', '1', 'yes') THEN 1
                    ELSE 0
                END as is_ssl,
                COALESCE(dr, 0) as dr
            FROM bt_downloaders
        """)

        # 删除原表，重命名临时表
        cursor.execute("DROP TABLE bt_downloaders")
        cursor.execute("ALTER TABLE bt_downloaders_temp RENAME TO bt_downloaders")

    def _migrate_torrent_info_table(self, cursor, conn):
        """迁移 torrent_info 表"""
        # 创建临时表
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS torrent_info_temp (
                info_id TEXT,
                downloader_id TEXT,
                downloader_name TEXT,
                torrent_id TEXT,
                hash TEXT,
                name TEXT,
                save_path TEXT,
                size REAL,
                status TEXT,
                torrent_file TEXT,
                added_date DATETIME,
                completed_date DATETIME,
                ratio TEXT,
                ratio_limit TEXT,
                tags TEXT,
                category TEXT,
                super_seeding TEXT,
                enabled BOOLEAN DEFAULT 1,
                create_time DATETIME,
                create_by TEXT,
                update_time DATETIME,
                update_by TEXT,
                dr INTEGER DEFAULT 0,
                PRIMARY KEY (info_id, downloader_id, downloader_name)
            )
        """)

        # 复制数据，转换数据类型
        cursor.execute("""
            INSERT INTO torrent_info_temp
            SELECT
                info_id,
                downloader_id,
                downloader_name,
                torrent_id,
                hash,
                name,
                save_path,
                size,
                status,
                torrent_file,
                added_date,
                completed_date,
                ratio,
                ratio_limit,
                tags,
                category,
                super_seeding,
                CASE
                    WHEN enabled = 1 THEN 1
                    ELSE 0
                END as enabled,
                create_time,
                create_by,
                update_time,
                update_by,
                COALESCE(dr, 0) as dr
            FROM torrent_info
        """)

        # 删除原表，重命名临时表
        cursor.execute("DROP TABLE torrent_info")
        cursor.execute("ALTER TABLE torrent_info_temp RENAME TO torrent_info")

    def _migrate_tracker_info_table(self, cursor, conn, sm4_key: str):
        """迁移 tracker_info 表并加密 tracker_url 字段"""
        # 创建临时表
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS tracker_info_temp (
                tracker_id TEXT PRIMARY KEY,
                torrent_info_id TEXT,
                tracker_name TEXT,
                tracker_url TEXT,
                last_announce_succeeded INTEGER,
                last_announce_msg TEXT,
                last_scrape_succeeded INTEGER,
                last_scrape_msg TEXT,
                create_time DATETIME,
                create_by TEXT,
                update_time DATETIME,
                update_by TEXT,
                dr INTEGER DEFAULT 0
            )
        """)

        # 获取所有数据并加密 tracker_url
        cursor.execute("SELECT * FROM tracker_info")
        rows = cursor.fetchall()

        sm4_crypt = sm4.CryptSM4()
        sm4_crypt.set_key(sm4_key, sm4.SM4_ENCRYPT)

        updated_count = 0
        for row in rows:
            tracker_url = row[3]  # tracker_url 是第4个字段
            if tracker_url and not tracker_url.startswith(('encrypted:', 'sm4:')):
                # 加密 tracker_url
                encrypted_url = sm4_crypt.crypt_ecb(tracker_url.encode()).hex()
                encrypted_url = f"sm4:{encrypted_url}"
                updated_count += 1

                # 插入加密后的数据
                cursor.execute("""
                    INSERT INTO tracker_info_temp
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (row[0], row[1], row[2], encrypted_url, row[4], row[5], row[6], row[7], row[8], row[9], row[10], row[11], row[12]))
            else:
                # 如果已经加密或为空，直接插入
                cursor.execute("""
                    INSERT INTO tracker_info_temp
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, row)

        if updated_count > 0:
            logger.info(f"加密了 {updated_count} 个tracker_url字段")

        # 删除原表，重命名临时表
        cursor.execute("DROP TABLE tracker_info")
        cursor.execute("ALTER TABLE tracker_info_temp RENAME TO tracker_info")

    def _encrypt_passwords(self, cursor, conn, sm4_key: str) -> bool:
        """加密 bt_downloaders 表中的密码字段"""
        cursor.execute("""
            SELECT downloader_id, password FROM bt_downloaders
            WHERE password IS NOT NULL
            AND password NOT LIKE 'sm4:%'
            AND password != ''
        """)
        rows = cursor.fetchall()

        if not rows:
            return False

        # 使用修复后的加密工具
        from app.utils.encryption import encrypt_password

        updated_count = 0
        for downloader_id, password in rows:
            # 使用修复后的加密函数
            encrypted_password = encrypt_password(password)

            # 更新数据库
            cursor.execute(
                "UPDATE bt_downloaders SET password = ? WHERE downloader_id = ?",
                (encrypted_password, downloader_id)
            )
            updated_count += 1

        if updated_count > 0:
            logger.info(f"加密了 {updated_count} 个密码字段")
        return updated_count > 0

    def _encrypt_tracker_urls(self, cursor, conn, sm4_key: str) -> bool:
        """加密 tracker_info 表中的 tracker_url 字段"""
        cursor.execute("""
            SELECT tracker_id, tracker_url FROM tracker_info
            WHERE tracker_url IS NOT NULL
            AND tracker_url NOT LIKE 'sm4:%'
            AND tracker_url != ''
        """)
        rows = cursor.fetchall()

        if not rows:
            return False

        # 使用修复后的加密工具
        from app.utils.encryption import encrypt_tracker_url

        updated_count = 0
        for tracker_id, tracker_url in rows:
            # 使用修复后的加密函数
            encrypted_url = encrypt_tracker_url(tracker_url)

            # 更新数据库
            cursor.execute(
                "UPDATE tracker_info SET tracker_url = ? WHERE tracker_id = ?",
                (encrypted_url, tracker_id)
            )
            updated_count += 1

        if updated_count > 0:
            logger.info(f"加密了 {updated_count} 个tracker_url字段")
        return updated_count > 0

    def _get_sm4_key(self) -> Optional[str]:
        """从配置文件获取SM4密钥"""
        try:
            import yaml

            if not self.config_path.exists():
                logger.error(f"配置文件不存在: {self.config_path}")
                return None

            with open(self.config_path, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)

            sm4_key = config.get('security', {}).get('secret_key')
            if not sm4_key:
                logger.error("配置文件中未找到 SM4 密钥")
                return None

            return sm4_key

        except Exception as e:
            logger.error(f"获取SM4密钥失败: {e}")
            return None

    def generate_migration_sql(self) -> str:
        """
        生成手动执行的SQL语句

        Returns:
            str: SQL语句
        """
        sql_statements = []

        # 1. 字段类型迁移SQL
        sql_statements.append("""
-- bt_downloaders 表字段类型迁移
CREATE TABLE bt_downloaders_temp (
    downloader_id TEXT PRIMARY KEY,
    nickname TEXT,
    host TEXT,
    username TEXT,
    password TEXT,
    is_search BOOLEAN DEFAULT 1,
    status TEXT,
    enabled BOOLEAN DEFAULT 1,
    downloader_type TEXT,
    port TEXT,
    is_ssl BOOLEAN DEFAULT 1,
    dr INTEGER DEFAULT 0
);

INSERT INTO bt_downloaders_temp
SELECT
    downloader_id,
    nickname,
    host,
    username,
    password,
    CASE
        WHEN is_search IN ('True', 'true', '1', 'yes') THEN 1
        ELSE 0
    END as is_search,
    status,
    CASE
        WHEN enabled IN ('True', 'true', '1', 'yes') THEN 1
        ELSE 0
    END as enabled,
    downloader_type,
    port,
    CASE
        WHEN is_ssl IN ('True', 'true', '1', 'yes') THEN 1
        ELSE 0
    END as is_ssl,
    COALESCE(dr, 0) as dr
FROM bt_downloaders;

DROP TABLE bt_downloaders;
ALTER TABLE bt_downloaders_temp RENAME TO bt_downloaders;
        """)

        # 2. torrent_info 表字段类型迁移SQL
        sql_statements.append("""
-- torrent_info 表字段类型迁移
CREATE TABLE torrent_info_temp (
    info_id TEXT,
    downloader_id TEXT,
    downloader_name TEXT,
    torrent_id TEXT,
    hash TEXT,
    name TEXT,
    save_path TEXT,
    size REAL,
    status TEXT,
    torrent_file TEXT,
    added_date DATETIME,
    completed_date DATETIME,
    ratio TEXT,
    ratio_limit TEXT,
    tags TEXT,
    category TEXT,
    super_seeding TEXT,
    enabled BOOLEAN DEFAULT 1,
    create_time DATETIME,
    create_by TEXT,
    update_time DATETIME,
    update_by TEXT,
    dr INTEGER DEFAULT 0,
    PRIMARY KEY (info_id, downloader_id, downloader_name)
);

INSERT INTO torrent_info_temp
SELECT
    info_id,
    downloader_id,
    downloader_name,
    torrent_id,
    hash,
    name,
    save_path,
    size,
    status,
    torrent_file,
    added_date,
    completed_date,
    ratio,
    ratio_limit,
    tags,
    category,
    super_seeding,
    CASE
        WHEN enabled = 1 THEN 1
        ELSE 0
    END as enabled,
    create_time,
    create_by,
    update_time,
    update_by,
    COALESCE(dr, 0) as dr
FROM torrent_info;

DROP TABLE torrent_info;
ALTER TABLE torrent_info_temp RENAME TO torrent_info;
        """)

        # 3. 删除逻辑反转SQL
        sql_statements.append("""
-- 删除逻辑反转（0=未删除, 1=逻辑删除）
UPDATE bt_downloaders
SET dr = CASE
    WHEN dr = 1 THEN 0
    WHEN dr = 0 THEN 1
    ELSE dr
END
WHERE dr IN (0, 1);

UPDATE torrent_info
SET dr = CASE
    WHEN dr = 1 THEN 0
    WHEN dr = 0 THEN 1
    ELSE dr
END
WHERE dr IN (0, 1);

UPDATE tracker_info
SET dr = CASE
    WHEN dr = 1 THEN 0
    WHEN dr = 0 THEN 1
    ELSE dr
END
WHERE dr IN (0, 1);
        """)

        # 4. 加密字段SQL（需要手动获取SM4密钥）
        sql_statements.append("""
-- 密码和tracker_url加密需要在Python环境中执行
-- 请使用应用启动时的自动迁移功能
        """)

        return "\n".join(sql_statements)


def run_database_migrations() -> bool:
    """
    运行数据库迁移的便捷函数

    Returns:
        bool: 迁移是否成功
    """
    migrator = DatabaseMigrator()
    return migrator.run_migrations()