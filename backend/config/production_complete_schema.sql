CREATE TABLE users (
	id INTEGER NOT NULL, 
	username VARCHAR, 
	password VARCHAR, 
	two_factor_secret VARCHAR, 
	two_factor_flag VARCHAR, 
	is_active BOOLEAN, 
	created_at DATETIME DEFAULT CURRENT_TIMESTAMP, 
	PRIMARY KEY (id)
);
CREATE TABLE login_logs (
	id INTEGER NOT NULL, 
	user_id INTEGER, 
	username VARCHAR, 
	ip_address VARCHAR, 
	user_agent VARCHAR, 
	success BOOLEAN, 
	timestamp DATETIME DEFAULT CURRENT_TIMESTAMP, 
	PRIMARY KEY (id)
);
CREATE TABLE configs (
	id INTEGER NOT NULL, 
	"key" VARCHAR, 
	value VARCHAR, 
	description VARCHAR, 
	PRIMARY KEY (id), 
	UNIQUE ("key")
);
CREATE TABLE tracker_info (
	tracker_id VARCHAR NOT NULL, 
	torrent_info_id VARCHAR, 
	tracker_name VARCHAR, 
	tracker_url VARCHAR, 
	last_announce_succeeded INTEGER, 
	last_announce_msg VARCHAR, 
	last_scrape_succeeded INTEGER, 
	last_scrape_msg VARCHAR, 
	dr INTEGER, create_time TYPE DATETIME, update_time TYPE DATETIME, create_by TYPE VARCHAR(30), update_by TYPE VARCHAR(30), tracker_host VARCHAR(256), status VARCHAR(20), msg VARCHAR(512), seeder_count INTEGER, leecher_count INTEGER, download_count INTEGER, version INTEGER NOT NULL DEFAULT 0, 
	PRIMARY KEY (tracker_id)
);
CREATE TABLE alembic_version (
	version_num VARCHAR(32) NOT NULL, 
	CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num)
);
CREATE TABLE IF NOT EXISTS "torrent_info" (
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
                dr INTEGER DEFAULT 0, has_tracker_error BOOLEAN DEFAULT 0 NOT NULL, deleted_at DATETIME DEFAULT NULL, original_filename VARCHAR(255) DEFAULT NULL, backup_file_path VARCHAR(512), progress REAL DEFAULT 0.00, original_file_list TEXT,
                PRIMARY KEY (info_id, downloader_id, downloader_name)
            );
CREATE UNIQUE INDEX ix_users_username ON users (username);
CREATE INDEX ix_users_id ON users (id);
CREATE INDEX ix_login_logs_id ON login_logs (id);
CREATE INDEX ix_tracker_info_tracker_name ON tracker_info (tracker_name);
CREATE INDEX ix_tracker_info_last_scrape_msg ON tracker_info (last_scrape_msg);
CREATE INDEX ix_tracker_info_tracker_url ON tracker_info (tracker_url);
CREATE INDEX ix_tracker_info_tracker_id ON tracker_info (tracker_id);
CREATE INDEX ix_tracker_info_last_announce_msg ON tracker_info (last_announce_msg);
CREATE INDEX ix_tracker_info_torrent_info_id ON tracker_info (torrent_info_id);
CREATE INDEX idx_torrent_info_composite ON torrent_info(enabled, dr, category, create_time DESC);
CREATE INDEX idx_torrent_info_name ON torrent_info(name);
CREATE INDEX idx_torrent_info_tags ON torrent_info(tags);
CREATE INDEX idx_torrent_info_size ON torrent_info(size);
CREATE INDEX idx_torrent_info_downloader ON torrent_info(downloader_id, downloader_name);
CREATE INDEX idx_torrent_info_hash ON torrent_info(hash);
CREATE INDEX idx_torrent_info_dr_added_date ON torrent_info(dr, added_date DESC);
CREATE INDEX idx_torrent_info_dr_status ON torrent_info(dr, status);
CREATE INDEX idx_torrent_info_dr_size ON torrent_info(dr, size);
CREATE INDEX idx_torrent_info_dr_category ON torrent_info(dr, category);
CREATE INDEX idx_torrent_info_dr_completed_date ON torrent_info(dr, completed_date);
CREATE INDEX idx_torrent_info_status_size_added ON torrent_info(dr, status, size, added_date DESC);
CREATE INDEX idx_torrent_info_covering ON torrent_info(dr, status, category, added_date DESC, size, name);
CREATE INDEX idx_torrent_info_has_tracker_error
        ON torrent_info(has_tracker_error);
CREATE TABLE IF NOT EXISTS "tracker_keyword_config" (
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
CREATE INDEX idx_tracker_keyword_type_enabled
            ON tracker_keyword_config(keyword_type, enabled);
CREATE INDEX idx_tracker_keyword_language
            ON tracker_keyword_config(language);
CREATE INDEX idx_tracker_keyword_priority
            ON tracker_keyword_config(priority);
CREATE INDEX idx_torrent_info_deleted_dr ON torrent_info (deleted_at, dr);
CREATE INDEX idx_torrent_info_backup_path ON torrent_info (backup_file_path);
CREATE UNIQUE INDEX idx_tracker_unique_url
            ON tracker_info(torrent_info_id, tracker_url);
CREATE UNIQUE INDEX idx_torrent_hash_unique
        ON torrent_info (hash, downloader_id);
CREATE TABLE setting_templates (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name VARCHAR(100) NOT NULL UNIQUE,
            description VARCHAR(500),
            downloader_type INTEGER NOT NULL,
            template_config TEXT NOT NULL,
            is_system_default BOOLEAN NOT NULL DEFAULT 0,
            created_by INTEGER,
            path_mapping TEXT,
            created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
CREATE INDEX ix_setting_templates_name ON setting_templates (name);
CREATE INDEX ix_setting_templates_downloader_type ON setting_templates (downloader_type);
CREATE INDEX ix_setting_templates_is_system_default ON setting_templates (is_system_default);
CREATE INDEX ix_setting_templates_created_at ON setting_templates (created_at);
CREATE INDEX ix_setting_templates_updated_at ON setting_templates (updated_at);
CREATE TABLE IF NOT EXISTS "bt_downloaders" (
                downloader_id VARCHAR(255) PRIMARY KEY NOT NULL,
                nickname VARCHAR(255),
                host VARCHAR(255),
                username VARCHAR(255),
                password VARCHAR(255),
                is_search BOOLEAN DEFAULT (1),
                status VARCHAR(255),
                enabled BOOLEAN DEFAULT (1),
                downloader_type INTEGER NOT NULL DEFAULT (0),
                port VARCHAR(255),
                is_ssl BOOLEAN DEFAULT (1),
                dr INTEGER DEFAULT (0),
                path_mapping TEXT
            , path_mapping_rules TEXT, torrent_save_path VARCHAR(500));
CREATE INDEX ix_bt_downloaders_nickname ON bt_downloaders (nickname);
CREATE INDEX ix_bt_downloaders_host ON bt_downloaders (host);
CREATE INDEX ix_bt_downloaders_username ON bt_downloaders (username);
CREATE INDEX ix_bt_downloaders_port ON bt_downloaders (port);
CREATE TABLE cron_task (
	task_id INTEGER NOT NULL, 
	task_name VARCHAR(200) NOT NULL, 
	task_code VARCHAR(50) NOT NULL, 
	task_status INTEGER NOT NULL, 
	task_type INTEGER NOT NULL, 
	executor TEXT NOT NULL, 
	enabled BOOLEAN NOT NULL, 
	last_execute_time DATETIME, 
	last_execute_duration INTEGER, 
	cron_plan VARCHAR(100) NOT NULL, 
	description VARCHAR(500), 
	timeout_seconds INTEGER, 
	max_retry_count INTEGER, 
	retry_interval INTEGER, 
	dr INTEGER NOT NULL, 
	create_time DATETIME NOT NULL, 
	update_time DATETIME NOT NULL, 
	create_by VARCHAR(50) NOT NULL, 
	update_by VARCHAR(50) NOT NULL, 
	PRIMARY KEY (task_id), 
	UNIQUE (task_code)
);
CREATE TABLE task_logs (
	log_id INTEGER NOT NULL, 
	task_id INTEGER, 
	task_name VARCHAR(100) NOT NULL, 
	task_type INTEGER, 
	start_time DATETIME NOT NULL, 
	end_time DATETIME, 
	duration INTEGER, 
	success BOOLEAN NOT NULL, 
	log_detail VARCHAR(2000), 
	dr INTEGER NOT NULL, 
	PRIMARY KEY (log_id), 
	FOREIGN KEY(task_id) REFERENCES cron_task (task_id)
);
CREATE TABLE torrent_audit_log (
                log_id VARCHAR(36) PRIMARY KEY NOT NULL,
                torrent_info_id VARCHAR(36),
                operation_type VARCHAR(50),
                operation_detail TEXT,
                old_value TEXT,
                new_value TEXT,
                operator VARCHAR(50),
                operation_time DATETIME,
                operation_result VARCHAR(20),
                error_message TEXT,
                downloader_id VARCHAR(36),
                create_time DATETIME,
                ip_address VARCHAR(50),
                user_agent TEXT,
                request_id VARCHAR(36),
                session_id VARCHAR(36)
            , torrent_name VARCHAR(255), downloader_name VARCHAR(100));
CREATE INDEX idx_torrent_audit_log_operation_type
                ON torrent_audit_log(operation_type);
CREATE INDEX idx_torrent_audit_log_torrent_info_id
                ON torrent_audit_log(torrent_info_id);
CREATE INDEX idx_torrent_audit_log_operator
                ON torrent_audit_log(operator);
CREATE INDEX idx_torrent_audit_log_operation_time
                ON torrent_audit_log(operation_time);
CREATE INDEX idx_torrent_audit_log_downloader_id
                ON torrent_audit_log(downloader_id);
CREATE INDEX idx_torrent_audit_log_ip_address
                ON torrent_audit_log(ip_address);
CREATE INDEX idx_torrent_audit_log_request_id
                ON torrent_audit_log(request_id);
CREATE INDEX idx_torrent_audit_log_session_id
                ON torrent_audit_log(session_id);
CREATE INDEX idx_audit_log_type_time
            ON torrent_audit_log(operation_type, operation_time);
CREATE INDEX idx_audit_log_torrent_time
            ON torrent_audit_log(torrent_info_id, operation_time);
CREATE TABLE search_templates (
                    id VARCHAR(36) PRIMARY KEY,
                    user_id VARCHAR(36) NOT NULL,
                    name VARCHAR(100) NOT NULL,
                    description VARCHAR(500),
                    conditions TEXT NOT NULL,
                    is_default BOOLEAN DEFAULT 0,
                    is_public BOOLEAN DEFAULT 0,
                    usage_count INTEGER DEFAULT 0,
                    created_time DATETIME DEFAULT CURRENT_TIMESTAMP,
                    updated_time DATETIME DEFAULT CURRENT_TIMESTAMP
                );
CREATE TABLE torrent_tags (
	tag_id VARCHAR(36) NOT NULL, 
	downloader_id VARCHAR(36) NOT NULL, 
	tag_name VARCHAR(255) NOT NULL, 
	tag_type VARCHAR(50) NOT NULL, 
	color VARCHAR(7), 
	created_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL, 
	updated_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL, 
	dr INTEGER DEFAULT '0' NOT NULL, 
	PRIMARY KEY (tag_id)
);
CREATE INDEX ix_torrent_tags_tag_id ON torrent_tags (tag_id);
CREATE INDEX ix_torrent_tags_downloader_id ON torrent_tags (downloader_id);
CREATE INDEX ix_torrent_tags_tag_type ON torrent_tags (tag_type);
CREATE TABLE torrent_tag_relations (
	relation_id VARCHAR(36) NOT NULL, 
	downloader_id VARCHAR(36) NOT NULL, 
	torrent_hash VARCHAR(64) NOT NULL, 
	tag_id VARCHAR(36) NOT NULL, 
	assigned_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL, 
	dr INTEGER DEFAULT '0' NOT NULL, 
	PRIMARY KEY (relation_id), 
	FOREIGN KEY(tag_id) REFERENCES torrent_tags (tag_id) ON DELETE CASCADE, 
	CONSTRAINT uk_torrent_tag UNIQUE (torrent_hash, tag_id)
);
CREATE INDEX ix_torrent_tag_relations_relation_id ON torrent_tag_relations (relation_id);
CREATE INDEX ix_torrent_tag_relations_downloader_id ON torrent_tag_relations (downloader_id);
CREATE INDEX ix_torrent_tag_relations_torrent_hash ON torrent_tag_relations (torrent_hash);
CREATE INDEX ix_torrent_tag_relations_tag_id ON torrent_tag_relations (tag_id);
CREATE TABLE torrent_deletion_audit_log (
	id INTEGER NOT NULL, 
	task_id VARCHAR(64) NOT NULL, 
	downloader_id INTEGER NOT NULL, 
	downloader_type INTEGER NOT NULL, 
	torrent_hash VARCHAR(64) NOT NULL, 
	torrent_name VARCHAR(255), 
	torrent_size BIGINT, 
	delete_files BOOLEAN NOT NULL, 
	safety_check_level VARCHAR(20), 
	validation_result TEXT, 
	operator_id INTEGER, 
	operator_name VARCHAR(100), 
	operator_ip VARCHAR(50), 
	operator_user_agent VARCHAR(255), 
	caller_source VARCHAR(100) NOT NULL, 
	caller_function VARCHAR(255), 
	caller_module VARCHAR(255), 
	deletion_status VARCHAR(20) NOT NULL, 
	error_message TEXT, 
	created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL, 
	deleted_at TIMESTAMP, 
	PRIMARY KEY (id)
);
CREATE INDEX idx_deletion_audit_task_id ON torrent_deletion_audit_log (task_id);
CREATE INDEX idx_deletion_audit_downloader ON torrent_deletion_audit_log (downloader_id);
CREATE INDEX idx_deletion_audit_torrent_hash ON torrent_deletion_audit_log (torrent_hash);
CREATE INDEX idx_deletion_audit_operator ON torrent_deletion_audit_log (operator_id);
CREATE INDEX idx_deletion_audit_created_at ON torrent_deletion_audit_log (created_at);
CREATE TABLE torrent_file_backup (
	id INTEGER NOT NULL, 
	info_hash VARCHAR(40) NOT NULL, 
	file_path VARCHAR(500) NOT NULL, 
	file_size BIGINT, 
	task_name VARCHAR(500), 
	uploader_id INTEGER, 
	downloader_id INTEGER, 
	upload_time DATETIME, 
	last_used_time DATETIME, 
	use_count INTEGER DEFAULT '0' NOT NULL, 
	is_deleted BOOLEAN DEFAULT '0' NOT NULL, 
	created_at DATETIME NOT NULL, 
	updated_at DATETIME NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(downloader_id) REFERENCES bt_downloaders (downloader_id) ON DELETE CASCADE, 
	UNIQUE (info_hash)
);
CREATE TABLE seed_transfer_audit_log (
	id INTEGER NOT NULL, 
	operation_type VARCHAR(50) DEFAULT 'seed_transfer' NOT NULL, 
	operation_time DATETIME NOT NULL, 
	user_id INTEGER, 
	username VARCHAR(100), 
	source_downloader_id INTEGER, 
	source_downloader_name VARCHAR(200), 
	target_downloader_id INTEGER, 
	target_downloader_name VARCHAR(200), 
	torrent_name VARCHAR(500), 
	info_hash VARCHAR(40), 
	source_path VARCHAR(500), 
	target_path VARCHAR(500), 
	delete_source BOOLEAN DEFAULT '0' NOT NULL, 
	transfer_status VARCHAR(20) NOT NULL, 
	error_message TEXT, 
	transfer_duration BIGINT, 
	created_at DATETIME NOT NULL, 
	PRIMARY KEY (id)
);
CREATE INDEX idx_torrent_file_backup_downloader ON torrent_file_backup (downloader_id);
CREATE INDEX idx_torrent_file_backup_upload_time ON torrent_file_backup (upload_time);
CREATE INDEX idx_torrent_file_backup_is_deleted ON torrent_file_backup (is_deleted);
CREATE INDEX idx_seed_transfer_audit_log_operation_time ON seed_transfer_audit_log (operation_time);
CREATE INDEX idx_seed_transfer_audit_log_user_id ON seed_transfer_audit_log (user_id);
CREATE INDEX idx_seed_transfer_audit_log_info_hash ON seed_transfer_audit_log (info_hash);
CREATE INDEX idx_seed_transfer_audit_log_transfer_status ON seed_transfer_audit_log (transfer_status);
CREATE INDEX idx_torrent_audit_log_torrent_name ON torrent_audit_log (torrent_name);
CREATE TABLE tracker_message_log_backup(
  log_id TEXT,
  tracker_host TEXT,
  msg TEXT,
  first_seen NUM,
  last_seen NUM,
  occurrence_count INT,
  sample_torrents TEXT,
  sample_urls TEXT,
  is_processed NUM,
  keyword_type TEXT,
  create_time NUM,
  update_time NUM,
  create_by TEXT,
  update_by TEXT
);
CREATE TABLE tracker_message_log (
                log_id VARCHAR(36) NOT NULL,
                tracker_host VARCHAR(500) NOT NULL,
                msg VARCHAR(2048) NOT NULL,
                first_seen DATETIME NOT NULL,
                last_seen DATETIME NOT NULL,
                occurrence_count INTEGER NOT NULL,
                sample_torrents TEXT,
                sample_urls TEXT,
                is_processed BOOLEAN NOT NULL,
                keyword_type VARCHAR(20),
                create_time DATETIME NOT NULL,
                update_time DATETIME NOT NULL,
                create_by VARCHAR(50) NOT NULL,
                update_by VARCHAR(50) NOT NULL,
                PRIMARY KEY (log_id)
            );
CREATE UNIQUE INDEX idx_tracker_msg_unique ON tracker_message_log (tracker_host, msg);
CREATE INDEX idx_tracker_msg_first_seen ON tracker_message_log (first_seen);
CREATE INDEX idx_tracker_msg_is_processed ON tracker_message_log (is_processed);
CREATE TABLE IF NOT EXISTS "downloader_path_maintenance" (
	id INTEGER NOT NULL, 
	downloader_id VARCHAR(36) NOT NULL, 
	path_type VARCHAR(20) NOT NULL, 
	path_value VARCHAR(500) NOT NULL, 
	is_enabled BOOLEAN DEFAULT '1' NOT NULL, 
	torrent_count INTEGER DEFAULT '0' NOT NULL, 
	last_updated_time DATETIME, 
	created_at DATETIME NOT NULL, 
	updated_at DATETIME NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_downloader_path_type_value UNIQUE (downloader_id, path_type, path_value), 
	FOREIGN KEY(downloader_id) REFERENCES bt_downloaders (downloader_id) ON DELETE CASCADE
);
CREATE INDEX idx_downloader_path_maintenance_path_type ON downloader_path_maintenance (path_type);
CREATE INDEX idx_downloader_path_maintenance_downloader ON downloader_path_maintenance (downloader_id);
CREATE TABLE IF NOT EXISTS "downloader_settings" (
	id INTEGER NOT NULL, 
	downloader_id VARCHAR NOT NULL, 
	dl_speed_limit INTEGER NOT NULL, 
	ul_speed_limit INTEGER NOT NULL, 
	enable_schedule BOOLEAN NOT NULL, 
	username VARCHAR(100), 
	password VARCHAR(255), 
	advanced_settings TEXT, 
	override_local BOOLEAN NOT NULL, 
	created_at DATETIME NOT NULL, 
	updated_at DATETIME NOT NULL, 
	dl_speed_unit INTEGER DEFAULT '0' NOT NULL, 
	ul_speed_unit INTEGER DEFAULT '0' NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(downloader_id) REFERENCES bt_downloaders (downloader_id) ON DELETE CASCADE
);
CREATE INDEX ix_downloader_settings_downloader_id ON downloader_settings (downloader_id);
CREATE INDEX ix_downloader_settings_id ON downloader_settings (id);
CREATE TABLE downloader_capabilities (
	id INTEGER NOT NULL, 
	downloader_id VARCHAR NOT NULL, 
	downloader_setting_id INTEGER, 
	supports_speed_scheduling BOOLEAN DEFAULT '0' NOT NULL, 
	supports_transfer_speed BOOLEAN DEFAULT '1' NOT NULL, 
	supports_connection_limits BOOLEAN DEFAULT '1' NOT NULL, 
	supports_queue_settings BOOLEAN DEFAULT '1' NOT NULL, 
	supports_download_paths BOOLEAN DEFAULT '0' NOT NULL, 
	supports_port_settings BOOLEAN DEFAULT '1' NOT NULL, 
	supports_advanced_settings BOOLEAN DEFAULT '1' NOT NULL, 
	supports_peer_limits BOOLEAN DEFAULT '0' NOT NULL, 
	extended_capabilities TEXT, 
	synced_from_downloader BOOLEAN DEFAULT '0' NOT NULL, 
	last_sync_at DATETIME, 
	manual_override BOOLEAN DEFAULT '0' NOT NULL, 
	created_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL, 
	updated_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(downloader_id) REFERENCES bt_downloaders (downloader_id) ON DELETE CASCADE, 
	FOREIGN KEY(downloader_setting_id) REFERENCES downloader_settings (id) ON DELETE SET NULL, 
	CONSTRAINT uq_downloader_capabilities_downloader_id UNIQUE (downloader_id)
);
CREATE INDEX ix_downloader_capabilities_id ON downloader_capabilities (id);
CREATE UNIQUE INDEX ix_downloader_capabilities_downloader_id ON downloader_capabilities (downloader_id);
CREATE INDEX ix_downloader_capabilities_downloader_setting_id ON downloader_capabilities (downloader_setting_id);
CREATE INDEX ix_downloader_capabilities_manual_override ON downloader_capabilities (manual_override);
CREATE INDEX ix_downloader_capabilities_synced_from_downloader ON downloader_capabilities (synced_from_downloader);
CREATE TABLE IF NOT EXISTS "speed_schedule_rules" (
            id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
            downloader_setting_id INTEGER NOT NULL,
            start_time VARCHAR(5) NOT NULL,
            end_time VARCHAR(5) NOT NULL,
            dl_speed_limit INTEGER NOT NULL DEFAULT 0,
            ul_speed_limit INTEGER NOT NULL DEFAULT 0,
            days_of_week VARCHAR(7) NOT NULL DEFAULT '0123456',
            enabled BOOLEAN NOT NULL DEFAULT 1,
            created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP, dl_speed_unit INTEGER NOT NULL DEFAULT 0, ul_speed_unit INTEGER NOT NULL DEFAULT 0, sort_order INTEGER NOT NULL DEFAULT 0,
            FOREIGN KEY(downloader_setting_id) REFERENCES downloader_settings(id) ON DELETE CASCADE,
            CHECK(start_time < end_time),
            CHECK(days_of_week >= '0' AND days_of_week <= '6543210')
        );
CREATE INDEX ix_speed_schedule_rules_id ON speed_schedule_rules (id);
CREATE INDEX ix_speed_schedule_rules_downloader_setting_id ON speed_schedule_rules (downloader_setting_id);
CREATE INDEX ix_speed_schedule_rules_setting_order ON speed_schedule_rules (downloader_setting_id, sort_order);
CREATE INDEX idx_audit_logs_operation_time ON torrent_audit_log (operation_time);
CREATE INDEX idx_cron_task_status ON cron_task (task_status, dr);
CREATE TABLE _alembic_tmp_tracker_info (
	tracker_id VARCHAR NOT NULL, 
	torrent_info_id VARCHAR, 
	tracker_name VARCHAR, 
	tracker_url VARCHAR, 
	last_announce_succeeded INTEGER, 
	last_announce_msg VARCHAR, 
	last_scrape_succeeded INTEGER, 
	last_scrape_msg VARCHAR, 
	dr INTEGER, 
	create_time NUMERIC, 
	update_time NUMERIC, 
	create_by TEXT(30), 
	update_by TEXT(30), 
	tracker_host VARCHAR(256), 
	status VARCHAR(20), 
	msg VARCHAR(512), 
	seeder_count INTEGER, 
	leecher_count INTEGER, 
	download_count INTEGER, 
	version INTEGER DEFAULT 0 NOT NULL, 
	PRIMARY KEY (tracker_id), 
	CONSTRAINT uq_tracker_info_torrent_url UNIQUE (torrent_info_id, tracker_url)
);
