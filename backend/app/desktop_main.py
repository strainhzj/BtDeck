import logging
import os
import threading
import time
import urllib.request

import uvicorn
import webview
from uvicorn import Config

os.environ.setdefault("DEV", "false")
os.environ.setdefault("ALLOWED_HOSTS", '["http://127.0.0.1:5001", "http://localhost:5001"]')

from app.core.config import settings
from app.core.migration import migrate_database
from app.database import init_config_file
from app.factory import app

logger = logging.getLogger(__name__)
server: uvicorn.Server | None = None


def configure_logging() -> None:
    try:
        logging.basicConfig(level=logging.INFO, format="%(levelname)s:%(name)s:%(message)s", force=True)
    except Exception as exc:
        print(f"[WARN] Failed to configure logging: {exc}")
        print("[WARN] Using default logging configuration")


def initialize_app_data() -> None:
    init_config_file()

    from app.yamlConfig import yaml

    yaml.reload()
    logger.info("Database path: %s", settings.DATABASE_PATH)
    if not migrate_database():
        raise RuntimeError("数据库迁移未完成，拒绝启动桌面服务")


def run_server() -> None:
    global server
    server = uvicorn.Server(
        Config(
            app,
            host=settings.HOST,
            port=settings.PORT,
            reload=False,
            workers=1,
            timeout_graceful_shutdown=5,
            loop="asyncio",
        )
    )
    server.run()


def wait_for_server_ready() -> str:
    url = f"http://127.0.0.1:{settings.PORT}/"
    last_error: Exception | None = None
    for _ in range(90):
        try:
            with urllib.request.urlopen(url, timeout=2):
                return url
        except Exception as exc:
            last_error = exc
            time.sleep(1)
    raise RuntimeError(f"BtDeck server did not become ready: {last_error}")


def stop_server() -> None:
    if server is not None:
        server.should_exit = True


def should_start_desktop_window() -> bool:
    window_flag = os.getenv("BTDECK_DESKTOP_WINDOW", "").strip().lower()
    if window_flag in {"0", "false", "no", "off"}:
        return False
    if window_flag in {"1", "true", "yes", "on"}:
        return True

    return os.getenv("SESSIONNAME", "").strip().lower() != "services"


def main() -> None:
    configure_logging()
    initialize_app_data()

    if not should_start_desktop_window():
        run_server()
        return

    server_thread = threading.Thread(target=run_server, name="btdeck-api-server", daemon=True)
    server_thread.start()

    url = wait_for_server_ready()
    window = webview.create_window("BtDeck", url, width=1280, height=820, min_size=(1024, 680))
    window.events.closed += stop_server
    webview.start()


if __name__ == "__main__":
    main()
