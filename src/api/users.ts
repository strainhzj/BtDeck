import request from '@/utils/request'

export const getUserInfo = (data: any) =>
  request({
    url: '/users/info',
    method: 'post',
    data
  })

export const changePassword = (data: any) =>
  request({
    url: '/user/changePassword',
    method: 'post',
    data
  })

export const login = (data: any) =>
  request({
    url: '/auth/login',
    method: 'post',
    data
  })

export const logout = () =>
  request({
    url: '/users/logout',
    method: 'post'
  })
