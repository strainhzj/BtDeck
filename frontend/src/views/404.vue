<template>
  <div class="not-found-container">
    <!-- 背景装饰 -->
    <div class="background-decoration">
      <div class="decoration-circle decoration-circle-1"></div>
      <div class="decoration-circle decoration-circle-2"></div>
      <div class="decoration-circle decoration-circle-3"></div>
    </div>

    <!-- 404内容 -->
    <div class="not-found-content">
      <!-- 错误代码 -->
      <div class="error-code">404</div>

      <!-- 错误标题 -->
      <h1 class="error-title">页面未找到</h1>

      <!-- 错误描述 -->
      <p class="error-description">
        抱歉，您访问的页面不存在或已被删除。<br />
        请检查URL或返回首页继续浏览。
      </p>

      <!-- 操作按钮 -->
      <div class="action-buttons">
        <el-button
          type="primary"
          size="large"
          class="back-button"
          @click="goBack"
        >
          <i class="el-icon-back"></i>
          返回上一页
        </el-button>
        <el-button
          size="large"
          class="home-button"
          @click="goHome"
        >
          <i class="el-icon-s-home"></i>
          返回首页
        </el-button>
      </div>

      <!-- 帮助信息 -->
      <div class="help-section">
        <p class="help-text">需要帮助？</p>
        <el-link type="primary" :underline="false" @click="contactSupport">
          <i class="el-icon-service"></i>
          联系支持团队
        </el-link>
      </div>
    </div>

    <!-- 版权信息 -->
    <div class="copyright">
      <p>© 2025 BtDeck. All rights reserved.</p>
    </div>
  </div>
</template>

<script lang="ts">
import { Component, Vue } from 'vue-property-decorator'

@Component({
  name: 'Page404'
})
export default class extends Vue {
  /**
   * 返回上一页
   */
  private goBack() {
    if (window.history.length > 1) {
      this.$router.go(-1)
    } else {
      this.$router.push('/')
    }
  }

  /**
   * 返回首页
   */
  private goHome() {
    this.$router.push('/')
  }

  /**
   * 联系支持
   */
  private contactSupport() {
    this.$message.info('支持功能开发中，敬请期待')
  }
}
</script>

<style lang="scss" scoped>
.not-found-container {
  min-height: 100vh;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  position: relative;
  overflow: hidden;
  background: var(--color-bg-primary);
}

// 背景装饰
.background-decoration {
  position: absolute;
  top: 0;
  left: 0;
  width: 100%;
  height: 100%;
  z-index: 0;
  overflow: hidden;
  pointer-events: none;
}

.decoration-circle {
  position: absolute;
  border-radius: 50%;
  opacity: 0.05;
  background: var(--color-primary);
  filter: blur(80px);
  animation: float 20s infinite ease-in-out;
}

.decoration-circle-1 {
  width: 500px;
  height: 500px;
  top: -150px;
  right: -150px;
  animation-delay: 0s;
}

.decoration-circle-2 {
  width: 400px;
  height: 400px;
  bottom: -100px;
  left: -100px;
  animation-delay: 7s;
}

.decoration-circle-3 {
  width: 300px;
  height: 300px;
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%);
  animation-delay: 14s;
}

@keyframes float {
  0%, 100% {
    transform: translate(0, 0) scale(1);
  }
  33% {
    transform: translate(40px, -40px) scale(1.1);
  }
  66% {
    transform: translate(-30px, 30px) scale(0.9);
  }
}

// 404内容
.not-found-content {
  position: relative;
  z-index: 1;
  text-align: center;
  padding: var(--spacing-2xl);
  animation: fadeInUp 0.8s ease-out;
}

@keyframes fadeInUp {
  from {
    opacity: 0;
    transform: translateY(30px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

// 错误代码
.error-code {
  font-size: var(--font-size-display);
  font-weight: var(--font-weight-bold);
  color: var(--color-primary);
  line-height: 1;
  margin-bottom: var(--spacing-lg);
  letter-spacing: -0.05em;
  background: linear-gradient(
    135deg,
    var(--color-primary) 0%,
    var(--color-primary-light) 100%
  );
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
  animation: scaleIn 1s ease-out;
}

@keyframes scaleIn {
  from {
    opacity: 0;
    transform: scale(0.5);
  }
  to {
    opacity: 1;
    transform: scale(1);
  }
}

// 错误标题
.error-title {
  font-size: var(--font-size-4xl);
  font-weight: var(--font-weight-bold);
  color: var(--color-text-primary);
  margin-bottom: var(--spacing-md);
  letter-spacing: -0.5px;
}

// 错误描述
.error-description {
  font-size: var(--font-size-md);
  color: var(--color-text-secondary);
  line-height: 1.8;
  margin-bottom: var(--spacing-2xl);
  max-width: 500px;
}

// 操作按钮
.action-buttons {
  display: flex;
  gap: var(--spacing-md);
  justify-content: center;
  flex-wrap: wrap;
  margin-bottom: var(--spacing-xl);
}

.back-button {
  min-width: 140px;
  height: 48px;
  font-size: var(--font-size-md);
  font-weight: var(--font-weight-semibold);
  border-radius: var(--radius-md);
  background: linear-gradient(
    135deg,
    var(--color-primary) 0%,
    var(--color-primary-light) 100%
  );
  border: none;
  box-shadow: var(--shadow-md);
  transition: all var(--transition-base);

  &:hover {
    transform: translateY(-2px);
    box-shadow: var(--shadow-lg);
  }

  &:active {
    transform: translateY(0);
  }
}

.home-button {
  min-width: 140px;
  height: 48px;
  font-size: var(--font-size-md);
  font-weight: var(--font-weight-medium);
  border-radius: var(--radius-md);
  border: 2px solid var(--color-border-primary);
  background: var(--color-bg-primary);
  color: var(--color-text-primary);
  transition: all var(--transition-base);

  &:hover {
    border-color: var(--color-primary);
    color: var(--color-primary);
    background: var(--color-bg-secondary);
  }
}

// 帮助部分
.help-section {
  padding-top: var(--spacing-lg);
  border-top: 1px solid var(--color-border-secondary);
}

.help-text {
  font-size: var(--font-size-sm);
  color: var(--color-text-secondary);
  margin: 0 0 var(--spacing-sm);
}

// 版权信息
.copyright {
  position: absolute;
  bottom: var(--spacing-lg);
  left: 0;
  right: 0;
  text-align: center;
  color: var(--color-text-tertiary);
  font-size: var(--font-size-xs);
  z-index: 1;
}

.copyright p {
  margin: 0;
}

// 响应式设计
@media (max-width: 768px) {
  .error-code {
    font-size: calc(var(--font-size-display) * 0.75);
  }

  .error-title {
    font-size: var(--font-size-3xl);
  }

  .error-description {
    font-size: var(--font-size-sm);
  }

  .action-buttons {
    flex-direction: column;
    align-items: stretch;
  }

  .back-button,
  .home-button {
    width: 100%;
    max-width: 280px;
    margin: 0 auto;
  }
}
</style>
