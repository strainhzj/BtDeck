import request from '@/utils/request'
import type { ApiEnvelope } from '@/utils/request'

export interface UserInfoData {
  userId?: string
  roles?: string[]
  name?: string
  avatar?: string
  introduction?: string
  twoFactorFlag?: string
  user?: UserInfoData
}

interface LoginResponseItem {
  access_token: string
  token_type: string
  user_id: string | number
}

interface LoginRequest {
  username: string
  password: string
  twofa_code?: string
}

export const getUserInfo = (data: { token: string }) =>
  request<ApiEnvelope<UserInfoData>>({
    url: '/users/info',
    method: 'post',
    data
  })

export const changePassword = (data: Record<string, unknown>) =>
  request<ApiEnvelope<unknown>>({
    url: '/user/changePassword',
    method: 'post',
    data
  })

export const login = (data: LoginRequest) =>
  request<ApiEnvelope<LoginResponseItem[]>>({
    url: '/auth/login',
    method: 'post',
    data
  })

export const logout = () =>
  request<ApiEnvelope<unknown>>({
    url: '/users/logout',
    method: 'post'
  })
