# API响应格式规范

**所有前端开发者必须严格遵守以下API响应格式规范！**

## 标准API响应格式

```typescript
interface APIResponse<T = any> {
  code: string;      // 状态码 (200, 401, 403, 422, 500)
  msg: string;       // 接口返回信息
  data: T;           // 接口返回数据
  status: string;    // 接口返回状态描述
}
```

## 分页响应接口定义（强制）

```typescript
// ✅ 正确的分页响应接口定义
export interface PaginatedResponse<T> {
  total: number
  page: number
  pageSize: number   // ✅ 必须使用pageSize（驼峰命名）
  list: T[]          // ✅ 必须使用list（小写）
}
```

**分页字段定义（强制要求）**：
- **total**: 总记录数（`number`类型）
- **page**: 当前页码（`number`类型，从1开始）
- **pageSize**: 每页记录数（`number`类型）
  - ❌ **严禁使用** `page_size`、`Page_Size`等其他变体
  - ❌ **严禁使用** `limit`、`size`、`per_page`等其他命名
  - ✅ **必须使用** `pageSize`（驼峰命名）
- **list**: 数据列表数组（`Array<T>`类型）
  - ❌ **严禁使用** `items`、`data`、`results`等其他命名
  - ❌ **严禁使用** `rows`、`records`等其他变体
  - ✅ **必须使用** `list`（小写）

## 前端数据解析规范（强制）

```typescript
// ✅ 正确的前端数据解析
const res = await getSomeList(params)
if (res.code === '200') {
  this.tableData = res.data.list   // ✅ 必须使用list
  this.total = res.data.total
  this.page = res.data.page
  this.pageSize = res.data.pageSize
}

// ❌ 错误示例（严禁使用）
const res = await getSomeList(params)
if (res.code === '200') {
  this.tableData = res.data.items  // ❌ 错误：使用了items
  this.total = res.data.total
}
```

## 历史教训

- ❌ 2025-01-27: Tracker模块因使用 `items` 和 `page_size` 导致查询无数据问题
- ❌ 修复耗时：30分钟
- ❌ 影响范围：关键词管理、消息记录两个模块
