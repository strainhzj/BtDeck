import { copyTextToClipboard } from '@/utils/clipboard'

describe('copyTextToClipboard', () => {
  const clipboardDescriptor = Object.getOwnPropertyDescriptor(window.navigator, 'clipboard')
  const execCommandDescriptor = Object.getOwnPropertyDescriptor(document, 'execCommand')

  function setClipboard(writeText?: (text: string) => Promise<void>): void {
    Object.defineProperty(window.navigator, 'clipboard', {
      configurable: true,
      value: writeText ? { writeText } : undefined
    })
  }

  function setExecCommand(implementation: (command: string) => boolean): jest.Mock<boolean, [string]> {
    const mock = jest.fn(implementation)
    Object.defineProperty(document, 'execCommand', {
      configurable: true,
      value: mock
    })
    return mock
  }

  afterEach(() => {
    document.body.innerHTML = ''
    if (clipboardDescriptor) {
      Object.defineProperty(window.navigator, 'clipboard', clipboardDescriptor)
    } else {
      Reflect.deleteProperty(window.navigator, 'clipboard')
    }
    if (execCommandDescriptor) {
      Object.defineProperty(document, 'execCommand', execCommandDescriptor)
    } else {
      Reflect.deleteProperty(document, 'execCommand')
    }
  })

  it('安全上下文优先使用 Clipboard API', async() => {
    const writeText = jest.fn().mockResolvedValue(undefined)
    const execCommand = setExecCommand(() => true)
    setClipboard(writeText)

    await copyTextToClipboard('{"ok":true}')

    expect(writeText).toHaveBeenCalledWith('{"ok":true}')
    expect(execCommand).not.toHaveBeenCalled()
  })

  it('Clipboard API 不存在时回退到隐藏 textarea', async() => {
    setClipboard()
    const execCommand = setExecCommand(() => true)

    await copyTextToClipboard('局域网 HTTP 文本')

    expect(execCommand).toHaveBeenCalledWith('copy')
    expect(document.querySelector('textarea')).toBeNull()
  })

  it('Clipboard API 被拒绝时继续尝试 DOM 回退', async() => {
    const writeText = jest.fn().mockRejectedValue(new Error('permission denied'))
    setClipboard(writeText)
    const execCommand = setExecCommand(() => true)

    await copyTextToClipboard('fallback')

    expect(writeText).toHaveBeenCalledWith('fallback')
    expect(execCommand).toHaveBeenCalledWith('copy')
  })

  it('所有复制能力均失败时向调用方抛出错误', async() => {
    setClipboard()
    setExecCommand(() => false)

    await expect(copyTextToClipboard('nope')).rejects.toThrow('浏览器拒绝复制命令')
    expect(document.querySelector('textarea')).toBeNull()
  })
})
