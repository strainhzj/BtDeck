import { VuexModule, Module, Action, Mutation, getModule } from 'vuex-module-decorators'
import { login, logout, getUserInfo } from '@/api/users'
import {
  getToken,
  setToken,
  removeToken,
  setRefreshToken,
  removeRefreshToken,
  getUserId,
  setUserId,
  removeUserId
} from '@/utils/cookies'
import store from '@/store'

export interface IUserState {
  token: string
  userId: string
  name: string
  avatar: string
  introduction: string
  roles: string[]
  twoFactorFlag: string
  mustChangePassword: boolean
}

interface ILoginPayload {
  username: string
  password: string
  twofa_code?: string
}

@Module({ dynamic: true, store, name: 'user' })
class User extends VuexModule implements IUserState {
  public token = getToken() || ''
  public userId = getUserId() || ''
  public name = ''
  public avatar = ''
  public introduction = ''
  public roles: string[] = []
  public twoFactorFlag = '0'
  public mustChangePassword = false

  @Mutation
  private SET_TOKEN(token: string) {
    this.token = token
  }

  @Mutation
  private SET_MUST_CHANGE_PASSWORD(flag: boolean) {
    this.mustChangePassword = flag
  }

  /**
   * 设置/清除强制改密标志（安全修复 W9）。
   * 登录响应携带 must_change_password；改密成功后由设置页清除。
   */
  @Action({ rawError: true })
  public SetMustChangePassword(flag: boolean) {
    this.SET_MUST_CHANGE_PASSWORD(flag)
  }

  /**
   * 静默续期后更新令牌（双令牌体系 W6-1）。
   * 请求拦截器在发请求时读 UserModule.token，401 刷新成功后必须
   * 更新内存 + cookie，重放请求才能携带新 token。
   */
  @Action({ rawError: true })
  public SetToken(token: string) {
    setToken(token)
    this.SET_TOKEN(token)
  }

  // 注：refresh token 的读取不走 store——getModule 只代理 @Action/@Mutation/
  // getter，未装饰的普通方法在访问器上不存在（曾导致 401 续期链路抛
  // TypeError 全链中断）。request.ts 的 refreshDeps 直接读 cookie。

  @Mutation
  private SET_USER_ID(userId: string) {
    this.userId = userId
    setUserId(userId)
  }

  @Mutation
  private SET_NAME(name: string) {
    this.name = name
  }

  @Mutation
  private SET_AVATAR(avatar: string) {
    this.avatar = avatar
  }

  @Mutation
  private SET_INTRODUCTION(introduction: string) {
    this.introduction = introduction
  }

  @Mutation
  private SET_ROLES(roles: string[]) {
    this.roles = roles
  }

  @Mutation
  private SET_TWO_FACTOR_FLAG(flag: string) {
    this.twoFactorFlag = flag
  }

  @Action({ rawError: true })
  public async Login(userInfo: ILoginPayload) {
    let { username } = userInfo
    const { password, twofa_code } = userInfo
    username = username.trim()
    const response = await login({ username, password, twofa_code })
    // response 是 CommonResponse 格式: {code, msg, status, data}
    // data 是一个数组，包含 [{access_token, refresh_token, token_type, user_id}]
    const access_token = response.data && response.data[0] && response.data[0].access_token
    const refresh_token = response.data && response.data[0] && response.data[0].refresh_token
    const user_id = response.data && response.data[0] && response.data[0].user_id
    const must_change_password = response.data && response.data[0] && response.data[0].must_change_password

    if (access_token) {
      setToken(access_token)
      this.SET_TOKEN(access_token)
      // 双令牌体系（W6-1）：持久化 refresh token 供 401 静默续期。
      // 响应缺失时必须清除旧值：旧 token 已被后端轮换/撤销，残留会让
      // 此后每次静默续期都失败，表现为反复被踢回登录页
      if (refresh_token) {
        setRefreshToken(refresh_token)
      } else {
        removeRefreshToken()
      }
      // 保存 user_id，确保转换为字符串类型
      if (user_id !== undefined && user_id !== null) {
        this.SET_USER_ID(String(user_id))
      }
      // 强制改密标志（安全修复 W9）：路由守卫据此拦截非改密页面
      this.SET_MUST_CHANGE_PASSWORD(Boolean(must_change_password))
    } else {
      throw Error('登录失败：未获取到访问令牌')
    }
  }

  @Action({ rawError: true })
  public ResetToken() {
    removeToken()
    removeRefreshToken()
    removeUserId()
    this.SET_TOKEN('')
    this.SET_USER_ID('')
    this.SET_ROLES([])
    // 登出/失效时清除强制改密标志，避免切换账号残留上一账号的强制状态
    this.SET_MUST_CHANGE_PASSWORD(false)
  }

  /**
   * 更新双因素认证标记状态。
   *
   * SET_TWO_FACTOR_FLAG 是 private Mutation，getModule 实例外部不可直接调用，
   * 组件必须通过此 Action 修改，避免绕过 Vuex 单向数据流（如原
   * settings/index.vue:610 的 (UserModule as any).twoFactorFlag = '0' 直改）。
   *
   * 审计依据：backend/docs/style-and-contract-audit.md 第4节"组件直接改写模块状态"。
   */
  @Action({ rawError: true })
  public SetTwoFactorFlag(flag: string) {
    this.SET_TWO_FACTOR_FLAG(flag)
  }

  @Action({ rawError: true })
  public async GetUserInfo() {
    // 🔧 防御性检查：更详细的 token 验证
    if (!this.token || this.token.trim() === '') {
      throw Error('Token为空，请重新登录')
    }

    try {
      // 尝试调用后端API获取用户信息
      const response = await getUserInfo({ token: this.token })

      // 🔧 防御性检查：验证响应状态
      if (response.code !== '200') {
        throw Error(response.msg || '获取用户信息失败')
      }

      if (!response || !response.data) {
        throw Error('Verification failed, please Login again.')
      }

      // response 是 CommonResponse 格式: {code, msg, status, data}
      // data 字段包含用户信息
      const data = response.data

      // 检查API返回的数据结构
      let roles, name, avatar, introduction, userId, twoFactorFlag
      if (data.user) {
        // 如果API返回 {user: {roles, name, avatar, introduction}} 格式
        const userData = data.user
        userId = userData.userId || ''
        roles = userData.roles || ['admin']
        name = userData.name || 'admin'
        avatar = userData.avatar || 'https://www.baidu.com/img/PCtm_d9c8750bed0b3c7d089fa7d55720d6cf.png'
        introduction = userData.introduction || ''
        twoFactorFlag = userData.twoFactorFlag || '0'
      } else {
        // 如果API直接返回用户信息
        userId = data.userId || ''
        roles = data.roles || ['admin']
        name = data.name || 'admin'
        avatar = data.avatar || 'https://www.baidu.com/img/PCtm_d9c8750bed0b3c7d089fa7d55720d6cf.png'
        introduction = data.introduction || ''
        twoFactorFlag = data.twoFactorFlag || '0'
      }

      // roles must be a non-empty array
      if (!roles || roles.length <= 0) {
        roles = ['admin'] // 默认角色
      }

      this.SET_ROLES(roles)
      this.SET_NAME(name)
      this.SET_AVATAR(avatar)
      this.SET_INTRODUCTION(introduction)
      this.SET_TWO_FACTOR_FLAG(twoFactorFlag)
      // 如果userId存在且不为空，保存到状态和localStorage
      if (userId) {
        this.SET_USER_ID(userId)
      }

    } catch (error) {
      // 如果API调用失败，抛出错误让用户重新登录
      console.error('getUserInfo API调用失败:', error)
      throw Error('获取用户信息失败，请重新登录')
    }
  }

  @Action({ rawError: true })
  public async LogOut() {
    // token 已被清空（如过期登出已执行 ResetToken）时仍要完成本地清理：
    // 直接跳过后端撤销调用，保证登出入口（Navbar）在任何状态下都可用，
    // 不因 throw 中断后续的页面跳转
    if (this.token !== '') {
      // 通知后端登出（POST /users/logout，require_authenticated_user 保护）。
      // 即使后端调用失败（如 token 已过期返回 401），仍本地清除 token，
      // 保证登出 UX 不被服务端错误阻塞。后端当前无 token 黑名单，登出后旧
      // token 在过期前仍有效是已知安全隐患（见 PLANS/v1.0.5-audit P1-A.3）。
      try {
        await logout()
      } catch (e) {
        console.warn('后端登出调用失败，仅本地清除 token:', e)
      }
    }
    removeToken()
    removeRefreshToken()
    removeUserId()
    this.SET_TOKEN('')
    this.SET_USER_ID('')
    this.SET_ROLES([])
    // 与 ResetToken 对齐：清除强制改密标志，避免残留上一账号的强制状态
    this.SET_MUST_CHANGE_PASSWORD(false)
  }
}

export const UserModule = getModule(User)
