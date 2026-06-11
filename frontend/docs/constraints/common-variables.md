# 公共变量先行

**原则**: 在创建新页面/组件前，先检查是否可复用现有变量

## 检查清单

- [ ] 检查 `styles/variables.scss` 是否已有所需变量
- [ ] 新增公共变量需评审是否真正"特有"
- [ ] 页面特定变量添加前缀（如 `--page-xxx-*`）

## 变量分类

### 全局公共变量（无需前缀）
```scss
// 主题色
--primary-color
--success-color
--warning-color
--danger-color

// 间距
--spacing-xs
--spacing-sm
--spacing-md
--spacing-lg

// 字体
--font-size-base
--font-size-lg
```

### 页面特定变量（需要前缀）
```scss
// 关键词管理页面
--page-keyword-card-bg
--page-keyword-border-color

// 下载器管理页面
--page-downloader-status-online
--page-downloader-status-offline
```

## 示例

```scss
// ✅ 正确：使用现有全局变量
.component {
  color: var(--primary-color);
  padding: var(--spacing-md);
}

// ✅ 正确：页面特定变量添加前缀
.keyword-page {
  background: var(--page-keyword-card-bg);
}

// ❌ 错误：重复定义已存在的全局变量
.component {
  --my-blue: #409EFF;  // 已有 --primary-color
}
```
