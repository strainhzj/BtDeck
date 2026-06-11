import { VuexModule, Module, Action, Mutation, getModule } from 'vuex-module-decorators'
import { login, logout, getUserInfo } from '@/api/users'
import { getToken, setToken, removeToken, getUserId, setUserId, removeUserId } from '@/utils/cookies'
import store from '@/store'

export interface IUserState {
  token: string
  userId: string
  name: string
  avatar: string
  introduction: string
  roles: string[]
  twoFactorFlag: string
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

  @Mutation
  private SET_TOKEN(token: string) {
    this.token = token
  }

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
    let { username, password, twofa_code } = userInfo
    username = username.trim()
    const response = await login({ username, password, twofa_code })
    // response 是 CommonResponse 格式: {code, msg, status, data}
    // data 是一个数组，包含 [{access_token, token_type, user_id}]
    const access_token = response.data && response.data[0] && response.data[0].access_token
    const user_id = response.data && response.data[0] && response.data[0].user_id

    if (access_token) {
      setToken(access_token)
      this.SET_TOKEN(access_token)
      // 保存 user_id，确保转换为字符串类型
      if (user_id !== undefined && user_id !== null) {
        this.SET_USER_ID(String(user_id))
      }
    } else {
      throw Error('登录失败：未获取到访问令牌')
    }
  }

  @Action({ rawError: true })
  public ResetToken() {
    removeToken()
    this.SET_TOKEN('')
    this.SET_USER_ID('')
    this.SET_ROLES([])
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
    if (this.token === '') {
      throw Error('LogOut: token is undefined!')
    }
    // 未做logout，先注释
    // await logout()
    removeToken()
    this.SET_TOKEN('')
    this.SET_USER_ID('')
    this.SET_ROLES([])
  }
}

export const UserModule = getModule(User)
