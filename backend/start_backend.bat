@echo off
REM BTDeck后端启动脚本（带环境变量配置）
REM 用于解决tracker同步时间窗口过滤问题

echo ========================================
echo BTDeck 后端服务启动脚本
echo ========================================
echo.

REM 设置环境变量（解决tracker同步问题）
REM TR_ACTIVE_WINDOW_SECONDS: 活跃时间窗口（秒），默认300秒(5分钟)，改为43200秒(12小时)
REM TR_FULL_SYNC_INTERVAL_SECONDS: 全量同步间隔（秒），默认43200秒(12小时)
set TR_ACTIVE_WINDOW_SECONDS=43200
set TR_FULL_SYNC_INTERVAL_SECONDS=43200

echo [INFO] 环境变量已配置:
echo   - TR_ACTIVE_WINDOW_SECONDS=%TR_ACTIVE_WINDOW_SECONDS% (12小时)
echo   - TR_FULL_SYNC_INTERVAL_SECONDS=%TR_FULL_SYNC_INTERVAL_SECONDS% (12小时)
echo.

echo [INFO] 正在启动后端服务...
echo.

REM 激活conda环境并启动服务
call conda activate btpManager
python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 5001

pause
