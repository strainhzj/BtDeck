#!/bin/bash

# BTDeck 项目初始化脚本
# 用途: 验证环境、运行测试、确保可启动

set -e  # 遇到错误立即退出

echo "=== BTDeck 项目初始化 ==="
echo ""

# 颜色定义
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# 1. 检查 Python 环境
echo -e "${YELLOW}1. 检查 Python 环境...${NC}"
if command -v python &> /dev/null; then
    PYTHON_VERSION=$(python --version 2>&1 | awk '{print $2}')
    echo -e "${GREEN}✓ Python 版本: $PYTHON_VERSION${NC}"
else
    echo -e "${RED}✗ Python 未安装${NC}"
    exit 1
fi

# 2. 检查 Node.js 环境
echo -e "${YELLOW}2. 检查 Node.js 环境...${NC}"
if command -v node &> /dev/null; then
    NODE_VERSION=$(node --version)
    echo -e "${GREEN}✓ Node.js 版本: $NODE_VERSION${NC}"
else
    echo -e "${RED}✗ Node.js 未安装${NC}"
    exit 1
fi

# 3. 检查后端依赖
echo -e "${YELLOW}3. 检查后端依赖...${NC}"
cd BtDeck
if [ -f "requirements.txt" ]; then
    echo -e "${GREEN}✓ requirements.txt 存在${NC}"
    echo "运行 pip install..."
    pip install -q -r requirements.txt
    echo -e "${GREEN}✓ 后端依赖安装完成${NC}"
else
    echo -e "${RED}✗ requirements.txt 不存在${NC}"
    cd ..
    exit 1
fi

# 4. 检查前端依赖
echo -e "${YELLOW}4. 检查前端依赖...${NC}"
cd ../BtDeck_fronted
if [ -f "package.json" ]; then
    echo -e "${GREEN}✓ package.json 存在${NC}"
    if [ ! -d "node_modules" ]; then
        echo "运行 npm install..."
        npm install -q
        echo -e "${GREEN}✓ 前端依赖安装完成${NC}"
    else
        echo -e "${GREEN}✓ node_modules 已存在${NC}"
    fi
else
    echo -e "${RED}✗ package.json 不存在${NC}"
    cd ..
    exit 1
fi

# 5. 检查数据库
echo -e "${YELLOW}5. 检查数据库...${NC}"
cd ../BtDeck
if [ -f "config/app.db" ]; then
    echo -e "${GREEN}✓ 数据库存在${NC}"
else
    echo -e "${YELLOW}⚠ 数据库不存在，将在首次启动时创建${NC}"
fi

# 6. 检查 Harness 文件
echo -e "${YELLOW}6. 检查 Harness 文件...${NC}"
cd ..
if [ -f "AGENTS.md" ]; then
    echo -e "${GREEN}✓ AGENTS.md 存在${NC}"
else
    echo -e "${RED}✗ AGENTS.md 不存在${NC}"
    exit 1
fi

if [ -f "feature_list.json" ]; then
    echo -e "${GREEN}✓ feature_list.json 存在${NC}"
else
    echo -e "${RED}✗ feature_list.json 不存在${NC}"
    exit 1
fi

if [ -f "progress.md" ]; then
    echo -e "${GREEN}✓ progress.md 存在${NC}"
else
    echo -e "${RED}✗ progress.md 不存在${NC}"
    exit 1
fi

# 7. 验证后端启动
echo -e "${YELLOW}7. 验证后端启动...${NC}"
cd BtDeck
echo "检查后端配置..."
if [ -f "app/main.py" ]; then
    echo -e "${GREEN}✓ app/main.py 存在${NC}"
else
    echo -e "${RED}✗ app/main.py 不存在${NC}"
    cd ..
    exit 1
fi

# 8. 验证前端启动
echo -e "${YELLOW}8. 验证前端启动...${NC}"
cd ../BtDeck_fronted
if [ -f "src/main.js" ]; then
    echo -e "${GREEN}✓ src/main.js 存在${NC}"
else
    echo -e "${RED}✗ src/main.js 不存在${NC}"
    cd ..
    exit 1
fi

# 9. 显示当前功能状态
echo -e "${YELLOW}9. 显示当前功能状态...${NC}"
cd ..
if command -v jq &> /dev/null; then
    echo ""
    echo "当前进行中的功能:"
    jq -r '.features[] | select(.status == "in-progress") | "  - \(.name) (\(.id))"' feature_list.json
    echo ""
    echo "待开始的功能:"
    jq -r '.features[] | select(.status == "pending") | "  - \(.name) (\(.id))"' feature_list.json
    echo ""
else
    echo -e "${YELLOW}⚠ jq 未安装，跳过功能状态显示${NC}"
    echo "安装 jq: apt-get install jq (Linux) 或 brew install jq (macOS)"
fi

# 10. 完成提示
echo ""
echo -e "${GREEN}=== 初始化完成 ===${NC}"
echo ""
echo "快速启动:"
echo "  后端: cd BtDeck && python -m uvicorn app.main:app --reload --port 5001"
echo "  前端: cd BtDeck_fronted && npm run serve"
echo ""
echo "API 文档: http://localhost:5001/docs"
echo "前端地址: http://localhost:8080"
echo ""
echo "下一步:"
echo "  1. 阅读 AGENTS.md"
echo "  2. 阅读 PLANS/v1.0.4.md"
echo "  3. 查看 progress.md"
echo ""
