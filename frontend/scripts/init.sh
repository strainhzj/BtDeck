#!/bin/bash

# BTDeck 前端初始化脚本
# 用途: 验证环境、安装依赖、运行测试
#
# 用法:
#   ./init.sh          默认模式：安装依赖 + 环境验证
#   ./init.sh --ci     轻量模式：仅环境验证（不安装依赖、不 lint），被根 init.sh 调用
#   ./init.sh --check  等同于默认 + 额外跑 lint（兼容旧参数）

set -e

echo "=== BTDeck 前端初始化 ==="
echo ""

# 颜色定义
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

# 参数解析
MODE="default"
for arg in "$@"; do
  case "$arg" in
    --ci)   MODE="ci" ;;
    --check) MODE="check" ;;
  esac
done
echo "模式: $MODE"
echo ""

# 1. 检查 Node.js 环境
echo -e "${YELLOW}1. 检查 Node.js 环境...${NC}"
if command -v node &> /dev/null; then
    NODE_VERSION=$(node --version)
    NODE_MAJOR=$(echo $NODE_VERSION | cut -d. -f1 | sed 's/v//')

    if [ "$NODE_MAJOR" -ge 18 ]; then
        echo -e "${GREEN}✓ Node.js 版本: $NODE_VERSION (符合要求 >=18)${NC}"
    else
        echo -e "${YELLOW}⚠ Node.js 版本: $NODE_VERSION (建议 >=18)${NC}"
    fi
else
    echo -e "${RED}✗ Node.js 未安装${NC}"
    exit 1
fi

# 2. 检查 npm
echo -e "${YELLOW}2. 检查 npm...${NC}"
if command -v npm &> /dev/null; then
    NPM_VERSION=$(npm --version)
    echo -e "${GREEN}✓ npm 版本: $NPM_VERSION${NC}"
else
    echo -e "${RED}✗ npm 未安装${NC}"
    exit 1
fi

# 3. 检查依赖文件
echo -e "${YELLOW}3. 检查依赖文件...${NC}"
if [ -f "package.json" ]; then
    echo -e "${GREEN}✓ package.json 存在${NC}"
else
    echo -e "${RED}✗ package.json 不存在${NC}"
    exit 1
fi

# 4. 安装依赖（--ci 模式跳过）
if [ "$MODE" = "ci" ]; then
    echo -e "${YELLOW}4. 跳过依赖安装（--ci 模式）...${NC}"
else
    echo -e "${YELLOW}4. 安装 npm 依赖...${NC}"
    if [ ! -d "node_modules" ]; then
        echo "运行 npm install..."
        npm install -q
        echo -e "${GREEN}✓ 依赖安装完成${NC}"
    else
        echo -e "${GREEN}✓ node_modules 已存在${NC}"

        # 检查是否需要更新
        echo "检查依赖更新..."
        npm outdated || true
    fi
fi

# 5. 检查 TypeScript
echo -e "${YELLOW}5. 检查 TypeScript 配置...${NC}"
if [ -f "tsconfig.json" ]; then
    echo -e "${GREEN}✓ tsconfig.json 存在${NC}"

    # 检查 TypeScript 版本
    TSC_VERSION=$(npm list typescript --depth=0 2>/dev/null | grep typescript | awk '{print $2}')
    echo "  TypeScript 版本: $TSC_VERSION"
else
    echo -e "${YELLOW}⚠ tsconfig.json 不存在${NC}"
fi

# 6. 检查 ESLint
echo -e "${YELLOW}6. 检查代码质量工具...${NC}"
TOOLS_AVAILABLE=true

if [ -f ".eslintrc.js" ] || [ -f ".eslintrc.json" ]; then
    echo -e "${GREEN}✓ ESLint 配置存在${NC}"

    if command -v eslint &> /dev/null || npm list eslint &> /dev/null; then
        echo -e "${GREEN}✓ ESLint 已安装${NC}"
    else
        echo -e "${YELLOW}⚠ ESLint 未安装${NC}"
        TOOLS_AVAILABLE=false
    fi
else
    echo -e "${YELLOW}⚠ ESLint 配置不存在${NC}"
    TOOLS_AVAILABLE=false
fi

# 7. 运行代码检查（--check 模式执行）
echo -e "${YELLOW}7. 运行代码检查...${NC}"
if [ "$MODE" = "check" ]; then
    echo "运行 ESLint..."
    npm run lint || echo -e "${YELLOW}⚠ ESLint 检查发现问题，运行 npm run lint -- --fix 自动修复${NC}"
else
    echo "跳过代码检查（--check 模式执行检查）"
fi

# 8. 检查构建配置
echo -e "${YELLOW}8. 检查构建配置...${NC}"
if [ -f "vue.config.js" ]; then
    echo -e "${GREEN}✓ vue.config.js 存在${NC}"
else
    echo -e "${YELLOW}⚠ vue.config.js 不存在${NC}"
fi

# 9. 检查环境变量
echo -e "${YELLOW}9. 检查环境变量...${NC}"
if [ -f ".env.development" ] || [ -f ".env" ]; then
    echo -e "${GREEN}✓ 环境变量文件存在${NC}"
else
    echo -e "${YELLOW}⚠ 环境变量文件不存在${NC}"
fi

# 10. 检查 API 配置
echo -e "${YELLOW}10. 检查 API 配置...${NC}"
if [ -f "src/utils/request.js" ] || [ -f "src/utils/request.ts" ]; then
    echo -e "${GREEN}✓ request 工具存在${NC}"

    # 显示 API 基础地址
    API_BASE=$(grep -r "baseURL" src/utils/request.* 2>/dev/null | head -1 | grep -o "http://[^']*" || echo "未配置")
    echo "  API 地址: $API_BASE"
else
    echo -e "${RED}✗ request 工具不存在${NC}"
fi

# 11. 显示当前前端任务
echo -e "${YELLOW}11. 显示当前前端任务...${NC}"
# 定位项目根目录的 feature_list.json（基于脚本自身位置，不依赖 cwd）
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT_FEATURE_LIST="$SCRIPT_DIR/../../feature_list.json"
if [ -f "$ROOT_FEATURE_LIST" ]; then
    if command -v jq &> /dev/null; then
        echo ""
        echo "当前进行中的前端任务:"
        jq -r '.features[].tasks[]? | select(.status == "in-progress") | select(.file | startswith("src/") or startswith("frontend/src/")) | "  - \(.name) (\(.id))"' "$ROOT_FEATURE_LIST" 2>/dev/null || echo "  无进行中的前端任务"
        echo ""
    else
        echo -e "${YELLOW}⚠ jq 未安装，跳过任务显示${NC}"
    fi
fi

# 12. 完成提示
echo ""
echo -e "${GREEN}=== 前端初始化完成 ===${NC}"
echo ""
echo "快速启动:"
echo "  npm run serve"
echo ""
echo "其他命令:"
echo "  npm run build     # 生产构建"
echo "  npm run lint      # 代码检查"
echo "  npm run lint -- --fix  # 自动修复"
echo ""
echo "开发地址:"
echo "  本地: http://localhost:8080"
echo "  网络: http://<IP>:8080"
echo ""
echo "后端 API:"
echo "  Swagger UI: http://localhost:5001/docs"
echo "  ReDoc: http://localhost:5001/redoc"
echo ""
echo "下一步:"
echo "  1. 阅读 AGENTS.md"
echo "  2. 阅读 CLAUDE.md"
echo "  3. 查看 PROGRESS.md"
echo ""
