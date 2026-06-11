# 前端列表排序逻辑约束

**核心原则**: 关键排序逻辑（如活跃种子优先）必须始终生效，不得因用户筛选而禁用

## 问题原因

在排序逻辑中添加 `isUserFiltering` 条件判断，导致用户使用筛选功能时排序失效：
- 用户筛选：`isUserFiltering = true`，排序被跳过
- 无筛选：`isUserFiltering = false`，排序生效

## 解决方案

### 1. 移除条件限制

关键排序逻辑不应受用户筛选状态影响

### 2. 使用复合排序

将业务优先级（如活跃状态）作为主排序，服务端排序作为次排序

## 实现规范

### ✅ 正确实现

```typescript
/** 排序后的列表（活跃种子优先，始终生效） */
private get sortedList(): any[] {
  if (!this.list || this.list.length === 0) return []
  return [...this.list].sort((a, b) => {
    // 主排序：活跃状态优先
    const aSpeed = this.getTorrentSpeed(a, 'download') || this.getTorrentSpeed(a, 'upload') || 0
    const bSpeed = this.getTorrentSpeed(b, 'download') || this.getTorrentSpeed(b, 'upload') || 0
    const aActive = aSpeed > 0 ? 1 : 0
    const bActive = bSpeed > 0 ? 1 : 0
    if (aActive !== bActive) return bActive - aActive
    if (aActive === 1) return bSpeed - aSpeed
    return 0
  })
}
```

### ❌ 错误实现

```typescript
/** 排序后的列表（活跃种子优先，用户筛选时保持服务端排序） */
private get sortedList(): any[] {
  if (!this.list || this.list.length === 0) return []
  if (this.isUserFiltering) return this.list  // ❌ 筛选时禁用排序
  return [...this.list].sort((a, b) => { /* 排序逻辑 */ })
}
```

## 适用场景

此约束适用于以下场景：
- 活跃种子优先显示
- 重要状态项置顶
- 紧急任务优先排序
- 任何涉及用户体验的关键排序逻辑

## 设计原则

### 1. 用户意图优先

用户筛选是为了缩小范围，而不是改变排序优先级

### 2. 复合排序策略

当需要同时考虑多种因素时，使用复合排序而非条件分支：

```typescript
// 主排序：业务优先级（活跃状态）
// 次排序：服务端排序（添加时间等）
// 三排序：默认排序（名称等）
```

### 3. 性能考虑

排序应使用高效的排序算法，避免频繁重复计算

## 验证方法

### 1. 功能测试

- [ ] 无筛选时，活跃种子排在最前面
- [ ] 使用筛选后，活跃种子仍排在最前面
- [ ] 清空筛选后，排序状态保持一致

### 2. 性能测试

- [ ] 列表数据量 100+ 条时，排序无明显延迟
- [ ] 1秒轮询更新时，UI 响应流畅

### 3. 边界测试

- [ ] 空列表时不报错
- [ ] 所有种子都无速度时，列表正常显示
- [ ] 所有种子都有速度时，按速度大小排序

## 相关约束

- [环境变量配置一致性](./environment-consistency.md) - 确保 API 数据获取正确
- [Vue异步操作上下文](./vue-async-context.md) - 排序逻辑中的异步数据处理

## 修改检查清单

修改排序逻辑时必须完成以下检查：

- [ ] 确认排序逻辑在所有场景下都生效
- [ ] 测试筛选 + 排序的组合场景
- [ ] 验证性能可接受（大列表无卡顿）
- [ ] 更新注释说明排序行为
