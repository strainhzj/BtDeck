#!/bin/bash

# BTDeck 后端初始化脚本
# 用途: 验证环境、安装依赖、运行测试

set -e

echo "=== BTDeck 后端初始化 ==="
echo ""

# 颜色定义
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

# 1. 检查 Python 环境
echo -e "${YELLOW}1. 检查 Python 环境...${NC}"
if command -v python &> /dev/null; then
    PYTHON_VERSION=$(python --version 2>&1 | awk '{print $2}')
    PYTHON_MAJOR=$(echo $PYTHON_VERSION | cut -d. -f1)
    PYTHON_MINOR=$(echo $PYTHON_VERSION | cut -d. -f2)

    if [ "$PYTHON_MAJOR" -ge 3 ] && [ "$PYTHON_MINOR" -ge 11 ]; then
        echo -e "${GREEN}✓ Python 版本: $PYTHON_VERSION (符合要求 >=3.11)${NC}"
    else
        echo -e "${YELLOW}⚠ Python 版本: $PYTHON_VERSION (建议 >=3.11)${NC}"
    fi
else
    echo -e "${RED}✗ Python 未安装${NC}"
    exit 1
fi

# 2. 检查虚拟环境
echo -e "${YELLOW}2. 检查虚拟环境...${NC}"
if [[ "$VIRTUAL_ENV" != "" ]]; then
    echo -e "${GREEN}✓ 虚拟环境已激活: $VIRTUAL_ENV${NC}"
else
    echo -e "${YELLOW}⚠ 虚拟环境未激活${NC}"
    echo "建议运行: conda activate btpManager"
fi

# 3. 检查依赖文件
echo -e "${YELLOW}3. 检查依赖文件...${NC}"
if [ -f "requirements.txt" ]; then
    echo -e "${GREEN}✓ requirements.txt 存在${NC}"
else
    echo -e "${RED}✗ requirements.txt 不存在${NC}"
    exit 1
fi

# 4. 安装依赖
echo -e "${YELLOW}4. 安装 Python 依赖...${NC}"
echo "运行 pip install..."
pip install -q -r requirements.txt
echo -e "${GREEN}✓ 依赖安装完成${NC}"

# 5. 检查数据库
echo -e "${YELLOW}5. 检查数据库...${NC}"
if [ -f "config/app.db" ]; then
    echo -e "${GREEN}✓ 数据库存在${NC}"

    # 检查数据库版本
    if command -v sqlite3 &> /dev/null; then
        DB_VERSION=$(sqlite3 config/app.db "SELECT version FROM alembic_version;" 2>/dev/null || echo "未初始化")
        echo "  数据库版本: $DB_VERSION"
    fi
else
    echo -e "${YELLOW}⚠ 数据库不存在，将在首次启动时创建${NC}"
fi

# 6. 检查 Alembic
echo -e "${YELLOW}6. 检查数据库迁移...${NC}"
if [ -d "alembic" ]; then
    echo -e "${GREEN}✓ Alembic 目录存在${NC}"

    # 检查待应用的迁移
    if command -v alembic &> /dev/null; then
        echo "检查待应用的迁移..."
        alembic head 2>/dev/null || echo "  无法获取迁移版本"
    else
        echo -e "${YELLOW}⚠ Alembic 未安装${NC}"
    fi
else
    echo -e "${RED}✗ Alembic 目录不存在${NC}"
fi

# 7. 检查代码质量工具
echo -e "${YELLOW}7. 检查代码质量工具...${NC}"
TOOLS_AVAILABLE=true

if command -v mypy &> /dev/null; then
    echo -e "${GREEN}✓ mypy 已安装${NC}"
else
    echo -e "${YELLOW}⚠ mypy 未安装${NC}"
    TOOLS_AVAILABLE=false
fi

if command -v black &> /dev/null; then
    echo -e "${GREEN}✓ black 已安装${NC}"
else
    echo -e "${YELLOW}⚠ black 未安装${NC}"
    TOOLS_AVAILABLE=false
fi

if command -v flake8 &> /dev/null; then
    echo -e "${GREEN}✓ flake8 已安装${NC}"
else
    echo -e "${YELLOW}⚠ flake8 未安装${NC}"
    TOOLS_AVAILABLE=false
fi

if [ "$TOOLS_AVAILABLE" = false ]; then
    echo ""
    echo "安装代码质量工具:"
    echo "  pip install mypy black flake8"
fi

# 8. 运行代码检查（可选，传入 --check 参数时执行）
echo -e "${YELLOW}8. 运行代码检查（可选）...${NC}"
if [[ "${1:-}" == "--check" ]]; then
    echo "运行 mypy..."
    mypy app/ || echo -e "${YELLOW}⚠ mypy 检查发现问题${NC}"

    echo "运行 black --check..."
    black --check app/ || echo -e "${YELLOW}⚠ black 检查发现问题，运行 black app/ 自动修复${NC}"

    echo "运行 flake8..."
    flake8 app/ || echo -e "${YELLOW}⚠ flake8 检查发现问题${NC}"
else
    echo "跳过代码检查（传入 --check 参数执行检查）"
fi

# 9. 检查测试
echo -e "${YELLOW}9. 检查测试配置...${NC}"
if [ -d "tests" ]; then
    echo -e "${GREEN}✓ tests 目录存在${NC}"

    if command -v pytest &> /dev/null; then
        echo -e "${GREEN}✓ pytest 已安装${NC}"
    else
        echo -e "${YELLOW}⚠ pytest 未安装${NC}"
        echo "  安装: pip install pytest pytest-asyncio"
    fi
else
    echo -e "${YELLOW}⚠ tests 目录不存在${NC}"
fi

# 10. 验证应用启动
echo -e "${YELLOW}10. 验证应用配置...${NC}"
if [ -f "app/main.py" ]; then
    echo -e "${GREEN}✓ app/main.py 存在${NC}"

    # 检查配置文件
    if [ -f "app/core/config.py" ]; then
        echo -e "${GREEN}✓ app/core/config.py 存在${NC}"
    else
        echo -e "${RED}✗ app/core/config.py 不存在${NC}"
    fi
else
    echo -e "${RED}✗ app/main.py 不存在${NC}"
    exit 1
fi

# 11. 显示当前后端任务
echo -e "${YELLOW}11. 显示当前后端任务...${NC}"
if [ -f "../feature_list.json" ]; then
    if command -v jq &> /dev/null; then
        echo ""
        echo "当前进行中的后端任务:"
        jq -r '.features[].tasks[]? | select(.status == "in-progress") | select(.file | startswith("app/")) | "  - \(.name) (\(.id))"' ../feature_list.json 2>/dev/null || echo "  无进行中的后端任务"
        echo ""
    else
        echo -e "${YELLOW}⚠ jq 未安装，跳过任务显示${NC}"
    fi
fi

# 12. 完成提示
echo ""
echo -e "${GREEN}=== 后端初始化完成 ===${NC}"
echo ""
echo "快速启动:"
echo "  python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 5001"
echo ""
echo "API 文档:"
echo "  Swagger UI: http://localhost:5001/docs"
echo "  ReDoc: http://localhost:5001/redoc"
echo ""
echo "数据库迁移:"
echo "  alembic revision --autogenerate -m \"描述\""
echo "  alembic upgrade head"
echo ""
echo "代码检查:"
echo "  mypy app/"
echo "  black app/"
echo "  flake8 app/"
echo ""
echo "下一步:"
echo "  1. 阅读 AGENTS.md"
echo "  2. 阅读 CLAUDE.md"
echo "  3. 查看 PROGRESS.md"
echo ""
