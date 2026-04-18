# API响应格式规范

**所有后端开发者必须严格遵守以下API响应格式规范！**

## 标准API响应格式（强制）

所有API接口必须遵循以下统一响应格式：

```python
from app.common.response import CommonResponse

return CommonResponse(
    status="success",
    msg="操作成功",
    code="200",
    data={...}
)
```

**响应格式说明**：
```json
{
 "code": "200",      // 状态码字符串
 "msg": "操作成功",   // 接口返回信息，用于前端显示给用户
 "data": {},         // 接口返回的数据对象
 "status": "success" // 接口返回状态描述
}
```

## 分页响应格式（强制 - 严禁修改字段名）

⚠️ **所有返回列表数据的API必须使用以下格式，字段名绝对不能修改！**

```python
from app.common.response import CommonResponse

# ✅ 正确的后端分页响应
return CommonResponse(
    status="success",
    msg="查询成功",
    code="200",
    data={
        "total": total,
        "page": page,
        "pageSize": page_size,  # ✅ 必须使用pageSize
        "list": items           # ✅ 必须使用list
    }
)
```

**分页字段定义（强制要求）**：
- **total**: 总记录数（`int`类型）
- **page**: 当前页码（`int`类型，从1开始）
- **pageSize**: 每页记录数（`int`类型）
  - ❌ **严禁使用** `page_size`、`page_size`等其他变体
  - ❌ **严禁使用** `limit`、`size`、`per_page`等其他命名
  - ✅ **必须使用** `pageSize`（驼峰命名）
- **list**: 数据列表数组（`list`类型）
  - ❌ **严禁使用** `items`、`data`、`results`等其他命名
  - ❌ **严禁使用** `rows`、`records`等其他变体
  - ✅ **必须使用** `list`（小写）

## 常见错误示例

```python
# ❌ 错误：使用了page_size和items
return CommonResponse(
    status="success",
    msg="查询成功",
    code="200",
    data={
        "total": total,
        "page": page,
        "page_size": page_size,  # ❌ 错误字段名
        "items": items           # ❌ 错误字段名
    }
)
```
