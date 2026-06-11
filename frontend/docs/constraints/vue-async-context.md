# Vue异步操作中this上下文的易变性

**核心原则**: 在异步操作中，`this` 上下文可能失效，需要提前保存快照

## 问题原因

Vue 2中，`async/await` 操作后 `this` 可能不再指向原始组件实例，导致属性访问失败

## 解决方案

### 1. 异步操作前保存快照

在第一个 `await` 前保存所有需要的 `this` 属性

### 2. 避免跨 await 使用 this

每个 `await` 块后重新读取 `this` 或使用局部变量

## 示例

```typescript
// ❌ 错误：跨await使用this
async handleSubmit() {
  await validateForm()
  this.formData.name = 'test'  // this可能已失效
  await submitForm()
  this.loading = false  // 可能报错
}

// ✅ 正确：异步操作前保存快照
async handleSubmit() {
  const form = this.formData  // 保存快照
  const loading = this.loading

  await validateForm()
  form.name = 'test'

  await submitForm()
  this.loading = false  // 重新读取this
}

// ✅ 更好：使用局部变量
async handleSubmit() {
  const { formData, loading } = this

  await validateForm()
  formData.name = 'test'

  await submitForm()
  this.loading = false
}
```

## 适用场景

- 所有包含 `async/await` 的方法
- `setTimeout`/`setInterval` 回调
- Promise 链式调用
- 事件监听器中的异步操作

## Vue 3 注意事项

使用函数式组件 + Composition API 天然解决此类问题，推荐使用
