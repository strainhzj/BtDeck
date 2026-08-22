import Cookies from 'js-cookie'

// App
const sidebarStatusKey = 'sidebar_status'
export const getSidebarStatus = () => Cookies.get(sidebarStatusKey)
export const setSidebarStatus = (sidebarStatus: string) => Cookies.set(sidebarStatusKey, sidebarStatus)

// User
const tokenKey = 'vue_typescript_admin_access_token'
export const getToken = () => Cookies.get(tokenKey)
export const setToken = (token: string) => Cookies.set(tokenKey, token)
export const removeToken = () => Cookies.remove(tokenKey)

// 双令牌体系（W6-1）：refresh token 用于 access token 过期后静默续期
const refreshTokenKey = 'vue_typescript_admin_refresh_token'
export const getRefreshToken = () => Cookies.get(refreshTokenKey)
export const setRefreshToken = (refreshToken: string) => Cookies.set(refreshTokenKey, refreshToken)
export const removeRefreshToken = () => Cookies.remove(refreshTokenKey)

const userIdKey = 'vue_typescript_admin_user_id'
export const getUserId = () => localStorage.getItem(userIdKey) || ''
export const setUserId = (userId: string) => localStorage.setItem(userIdKey, userId)
export const removeUserId = () => localStorage.removeItem(userIdKey)

// Generic storage helpers for view mode and other features
export const getStorage = (key: string): string | null => {
  const value = localStorage.getItem(key)
  return value ? value : null
}

export const setStorage = (key: string, value: string): void => {
  localStorage.setItem(key, value)
}
