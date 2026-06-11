@echo off
REM ============================================
REM BtDeck Docker 一键启动脚本 (Windows)
REM ============================================

if "%1"=="" goto start
if "%1"=="start" goto start
if "%1"=="stop" goto stop
if "%1"=="restart" goto restart
if "%1"=="status" goto status
if "%1"=="logs" goto logs
goto usage

:start
echo Starting BtDeck...
docker compose up -d --build
echo.
echo BtDeck started!
echo Visit: http://localhost:8080
goto end

:stop
echo Stopping BtDeck...
docker compose down
echo BtDeck stopped.
goto end

:restart
echo Stopping BtDeck...
docker compose down
echo Starting BtDeck...
docker compose up -d --build
echo BtDeck restarted!
goto end

:status
docker compose ps
goto end

:logs
docker compose logs -f --tail=100
goto end

:usage
echo Usage: start.bat {start^|stop^|restart^|status^|logs}
goto end

:end
