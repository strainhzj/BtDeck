import { DirectiveOptions } from 'vue'

interface HTMLElementWithWave extends HTMLElement {
  style: CSSStyleDeclaration & {
    position?: string
    overflow?: string
  }
}

const waves: DirectiveOptions = {
  bind(el: HTMLElementWithWave, binding) {
    el.addEventListener('click', function(e: MouseEvent) {
      const customOpts = Object.assign({}, binding.value)
      const opts = Object.assign({
        ele: el, // 波纹作用元素
        type: 'hit', // hit 点击位置扩散 center中心扩散
        color: 'rgba(0, 0, 0, 0.15)', // 波纹颜色
        duration: 1000, // 波纹持续时间（毫秒）
        radius: 0 // 最大波纹半径
      }, customOpts)

      const target = opts.ele
      if (target) {
        target.style.position = 'relative'
        target.style.overflow = 'hidden'
        const rect = target.getBoundingClientRect()
        let ripple = target.querySelector('.waves-ripple') as HTMLElement
        if (!ripple) {
          ripple = document.createElement('span')
          ripple.className = 'waves-ripple'
          ripple.style.height = ripple.style.width = Math.max(rect.width, rect.height) + 'px'
          target.appendChild(ripple)
        } else {
          ripple.className = 'waves-ripple'
        }
        ripple.style.cssText = `
          top: ${(e.pageY - rect.top - ripple.offsetHeight / 2 - document.documentElement.scrollTop || document.body.scrollTop)}px;
          left: ${(e.pageX - rect.left - ripple.offsetWidth / 2 - document.documentElement.scrollLeft || document.body.scrollLeft)}px;
          background-color: ${opts.color};
          z-index: 9999;
          position: absolute;
          border-radius: 50%;
          transform: scale(0);
          animation: ripple ${opts.duration}ms ease-out;
        `
      }
    }, false)
  }
}

export default waves

// 添加必要的CSS样式
const style = document.createElement('style')
style.textContent = `
@keyframes ripple {
  to {
    transform: scale(4);
    opacity: 0;
  }
}
.waves-ripple {
  position: absolute;
  border-radius: 50%;
  background-color: rgba(0, 0, 0, 0.15);
  transform: scale(0);
  animation: ripple 1s ease-out;
  pointer-events: none;
}
`
document.head.appendChild(style)