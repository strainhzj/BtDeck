#!/bin/bash

# BtDeck 全栈环境验证脚本
# 用途: 验证 git 状态、harness 文件完整性、前后端环境
#
# 用法:
#   ./init.sh          轻量模式（默认）：仅验证，不安装依赖、不跑 lint
#   ./init.sh --full   完整模式：调用两端 init.sh 安装依赖 + 验证 + lint
#   ./init.sh --help   显示帮助

set -e

# 颜色定义
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

MODE="ci"
for arg in "$@"; do
  case "$arg" in
    --full) MODE="full" ;;
    --ci)   MODE="ci" ;;
    --help|-h)
      echo "用法: ./init.sh [--full|--ci|--help]"
      echo "  默认/--ci  轻量模式，仅验证（不安装依赖、不 lint）"
      echo "  --full     完整模式（安装依赖 + 验证 + lint）"
      echo "  --help     显示本帮助"
      exit 0 ;;
    *) echo -e "${RED}未知参数: $arg${NC}"; exit 1 ;;
  esac
done

echo "=== BtDeck 全栈环境验证 ==="
echo ""

# 1. 检查工作目录（必须在仓库根）
echo -e "${YELLOW}1. 检查工作目录...${NC}"
if [ ! -f "AGENTS.md" ] || [ ! -d "backend" ] || [ ! -d "frontend" ]; then
    echo -e "${RED}✗ 必须在仓库根目录运行（应包含 AGENTS.md / backend/ / frontend/）${NC}"
    exit 1
fi
echo -e "${GREEN}✓ 工作目录正确${NC}"

# 2. 检查 harness 文件完整性
echo -e "${YELLOW}2. 检查 harness 文件完整性...${NC}"
HARNESS_FILES=("AGENTS.md" "feature_list.json" "progress.md" "session-handoff.md" "init.sh" "HARNESS_GUIDE.md")
HARNESS_OK=true
for f in "${HARNESS_FILES[@]}"; do
    if [ -f "$f" ]; then
        echo -e "${GREEN}✓ $f${NC}"
    else
        echo -e "${RED}✗ $f 缺失${NC}"
        HARNESS_OK=false
    fi
done
if [ "$HARNESS_OK" = false ]; then
    echo -e "${RED}✗ harness 文件不完整${NC}"
    exit 1
fi

# 3. Git 状态检查
echo -e "${YELLOW}3. 检查 Git 状态...${NC}"
if command -v git &> /dev/null; then
    BRANCH=$(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo "unknown")
    echo -e "${GREEN}✓ 当前分支: $BRANCH${NC}"
    DIRTY=$(git status --porcelain 2>/dev/null | wc -l)
    if [ "$DIRTY" -gt 0 ]; then
        echo -e "${YELLOW}⚠ 有 $DIRTY 个未提交变更${NC}"
    else
        echo -e "${GREEN}✓ 工作区干净${NC}"
    fi
else
    echo -e "${YELLOW}⚠ git 不可用${NC}"
fi

# 4. 显示当前开发版本
echo -e "${YELLOW}4. 当前开发版本...${NC}"
if command -v jq &> /dev/null; then
    CURRENT=$(jq -r '.current_dev_version // "未知"' feature_list.json 2>/dev/null)
    echo -e "${GREEN}✓ current_dev_version: $CURRENT${NC}"
else
    echo -e "${YELLOW}⚠ jq 未安装，跳过版本显示${NC}"
fi

# 5. 后端环境验证
echo ""
echo -e "${YELLOW}5. 后端环境验证...${NC}"
if [ -d "backend/scripts" ] && [ -f "backend/scripts/init.sh" ]; then
    if [ "$MODE" = "full" ]; then
        ( cd backend && bash scripts/init.sh ) || echo -e "${YELLOW}⚠ 后端 init.sh 有警告${NC}"
    else
        ( cd backend && bash scripts/init.sh --ci ) || echo -e "${YELLOW}⚠ 后端 init.sh --ci 有警告${NC}"
    fi
else
    echo -e "${RED}✗ backend/scripts/init.sh 不存在${NC}"
fi

# 6. 前端环境验证
echo ""
echo -e "${YELLOW}6. 前端环境验证...${NC}"
if [ -d "frontend/scripts" ] && [ -f "frontend/scripts/init.sh" ]; then
    if [ "$MODE" = "full" ]; then
        ( cd frontend && bash scripts/init.sh ) || echo -e "${YELLOW}⚠ 前端 init.sh 有警告${NC}"
    else
        ( cd frontend && bash scripts/init.sh --ci ) || echo -e "${YELLOW}⚠ 前端 init.sh --ci 有警告${NC}"
    fi
else
    echo -e "${RED}✗ frontend/scripts/init.sh 不存在${NC}"
fi

# 7. 完成提示
echo ""
echo -e "${GREEN}=== 全栈环境验证完成（模式: $MODE）===${NC}"
echo ""
echo "快速启动:"
echo "  后端: cd backend && python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 5001"
echo "  前端: cd frontend && npm run serve"
echo "  Docker: docker compose up -d --build"
echo ""
echo "访问: http://localhost:8080 | API文档: http://localhost:5001/docs"
echo ""
echo "下一步:"
echo "  1. 阅读 AGENTS.md（全栈工作流）"
echo "  2. 查看 feature_list.json（功能状态）"
echo "  3. 查看 progress.md（进度日志）"
echo ""
