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

const userIdKey = 'vue_typescript_admin_user_id'
export const getUserId = () => localStorage.getItem(userIdKey) || ''
export const setUserId = (userId: string) => localStorage.setItem(userIdKey, userId)
export const removeUserId = () => localStorage.removeItem(userIdKey)
