import { UserModule } from '@/store/modules/user'
import { demoStore } from '@/demo/demo-store'
import { DEMO_ACCESS_TOKEN, DEMO_USER_ID } from '@/demo/types'

describe('demo authentication bypass', () => {
  const originalDemoMode = process.env.VUE_APP_DEMO_MODE

  beforeEach(() => {
    demoStore.reset()
    process.env.VUE_APP_DEMO_MODE = 'true'
  })

  afterEach(() => {
    if (originalDemoMode === undefined) {
      delete process.env.VUE_APP_DEMO_MODE
    } else {
      process.env.VUE_APP_DEMO_MODE = originalDemoMode
    }
  })

  it('initializes, refreshes and clears only the local demo session', async() => {
    await UserModule.InitializeDemoSession()
    expect(UserModule.token).toBe(DEMO_ACCESS_TOKEN)
    expect(UserModule.userId).toBe(DEMO_USER_ID)

    await UserModule.Login({ username: 'demo-user', password: 'not-sent' })
    await UserModule.GetUserInfo()
    expect(UserModule.name).toBe('演示管理员')
    expect(UserModule.roles).toContain('admin')

    await UserModule.LogOut()
    expect(UserModule.token).toBe('')
    expect(UserModule.userId).toBe('')

    await UserModule.InitializeDemoSession()
    expect(UserModule.token).toBe(DEMO_ACCESS_TOKEN)
  })
})
