# 前端环境变量配置一致性

**核心原则**: 开发环境和生产环境的环境变量配置必须保持语义一致性，避免 API 路径不匹配

## 问题原因

`.env` 和 `.env.production` 中的 `VUE_APP_BASE_API` 配置不一致，导致：
- 开发环境请求路径正确：`/api/v1/torrents/active-torrents`
- 生产环境请求路径错误：`/api/torrents/active-torrents`（缺少版本号）

## 解决方案

### 1. 统一 API 版本号

确保所有环境配置都包含相同的 API 版本号

### 2. 使用一致的路径前缀

`VUE_APP_BASE_API` 必须以版本号结尾，如 `/api/v1/`

## 配置规范

### ✅ 正确配置

```bash
# .env (开发环境)
VUE_APP_BASE_API=/api/v1/

# .env.production (生产环境)
VUE_APP_BASE_API=/api/v1/
```

### ❌ 错误配置

```bash
# .env (开发环境)
VUE_APP_BASE_API=/api/v1/

# .env.production (生产环境)
VUE_APP_BASE_API=/api  # ❌ 缺少版本号
```

## 影响范围

不一致的环境变量配置会导致：
- API 请求返回 404 错误
- 实时数据无法获取（如速度监控）
- 依赖 API 数据的功能失效

## 验证方法

### 1. 检查环境变量文件

```bash
# 检查开发环境
cat BtDeck_fronted/.env | grep VUE_APP_BASE_API

# 检查生产环境
cat BtDeck_fronted/.env.production | grep VUE_APP_BASE_API
```

### 2. 构建后验证

```bash
# 构建生产版本
npm run build

# 检查构建产物中的 API 路径
grep -r "baseURL" dist/
```

### 3. 运行时验证

在浏览器开发者工具的 Network 面板中：
- 检查 API 请求路径是否正确
- 确认响应状态码为 200 而非 404

## 相关约束

- [API响应格式规范](./api-response-format.md) - 后端 API 路径规范
- [后端环境配置](../../BtDeck/docs/constraints/) - 后端 `API_V1_STR` 配置

## 修改检查清单

修改环境变量时必须完成以下检查：

- [ ] 同时修改 `.env` 和 `.env.production`
- [ ] 确保 `VUE_APP_BASE_API` 版本号一致
- [ ] 重新构建生产版本验证
- [ ] 测试 API 请求是否成功
