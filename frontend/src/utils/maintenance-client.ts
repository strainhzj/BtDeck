/**
 * 维护模式独立 HTTP 通道（database-migration-ui W4-1，PLANS §9/§11 T21）。
 *
 * 评审要求：普通 axios 通道（utils/request.ts）在维护模式下 503 洪泛会触发
 * 无限 refresh / redirectToLogin / 注销会话——维护页必须走本独立通道：
 *
 * - 独立 axios 实例：不经过 request.ts 拦截器（不弹网络 toast、不做幂等 GET
 *   瞬态重试、401 不静默续期不重放、绝不 redirectToLogin）；
 * - 维护 token 仅存模块级内存变量：绝不写 localStorage/sessionStorage/URL，
 *   页面刷新后自然失效，从服务端重新认证重建；
 * - 401（HTTP 401 或业务码 401）派发订阅制 onMaintenanceAuthExpired 回调，
 *   由 UI 决定呈现重认证界面；本通道不清除任何其他会话状态（Vuex/cookie）；
 * - 503（维护屏障/网关）静默：不重试、不弹 toast，以 ApiError 拒绝。
 *
 * 错误统一归一化为 ApiError（复用 error-normalize 纯函数，无 UI 副作用）。
 */

import axios, { AxiosRequestConfig, AxiosResponse } from 'axios'
import type { ApiEnvelope } from '@/utils/request'
import { ApiError } from '@/types/api'
import {
  SUCCESS_CODES,
  buildBusinessError,
  buildHttpError,
  buildNetworkError,
  pickErrorPayload
} from '@/utils/error-normalize'
import { translate } from '@/i18n'

/**
 * 维护专用 axios 实例：与 request.ts 完全隔离（无共享拦截器/无共享 token 注入）。
 * baseURL 与主通道同源（VUE_APP_BASE_API=/api/v1），仅 url 前缀不同。
 */
const maintenanceHttp = axios.create({
  baseURL: process.env.VUE_APP_BASE_API,
  timeout: 20000
})

// ---------------------------------------------------------------------------
// 维护 token 内存存储（模块级；页面刷新即失效）
// ---------------------------------------------------------------------------

/** 维护 token（仅内存；绝不持久化到 localStorage/URL） */
let maintenanceToken: string | null = null

/** 读取内存中的维护 token（测试与 UI 展示脱敏前缀用） */
export function getMaintenanceToken(): string | null {
  return maintenanceToken
}

/** 清除内存维护 token（不触碰普通会话状态；重认证/退出维护页时调用） */
export function clearMaintenanceToken(): void {
  maintenanceToken = null
}

// ---------------------------------------------------------------------------
// onMaintenanceAuthExpired 订阅（401 → 通知 UI，而非注销/跳转）
// ---------------------------------------------------------------------------

/** 维护会话失效回调（由维护页订阅：呈现重新认证入口） */
export type MaintenanceAuthExpiredHandler = () => void

const authExpiredHandlers = new Set<MaintenanceAuthExpiredHandler>()

/**
 * 订阅维护认证失效事件；返回退订函数。
 * 401 逐次派发（无节流）：订阅方通常首次收到后自停轮询或退订。
 */
export function subscribeAuthExpired(handler: MaintenanceAuthExpiredHandler): () => void {
  authExpiredHandlers.add(handler)
  return () => {
    authExpiredHandlers.delete(handler)
  }
}

function notifyAuthExpired(): void {
  authExpiredHandlers.forEach((handler) => {
    handler()
  })
}

// ---------------------------------------------------------------------------
// 信封解包 + 错误归一化（无 toast/无重试/无跳转）
// ---------------------------------------------------------------------------

function isSuccessEnvelope(value: unknown): value is ApiEnvelope {
  return (
    Boolean(value) &&
    typeof value === 'object' &&
    SUCCESS_CODES.has(String((value as { code?: unknown }).code))
  )
}

interface TransportErrorShape {
  response?: { status?: number, data?: unknown }
  request?: unknown
  message?: string
}

/**
 * 传输层错误（HTTP 4xx/5xx 或网络层）→ ApiError。
 * - HTTP 401 → 派发 auth expired（维护 token 失效/过期）；
 * - 503 等维护态错误 → 静默（无重试无 toast），直接以 ApiError 返回。
 */
function normalizeTransportError(error: unknown, notifyExpired: boolean): ApiError {
  const err = error as TransportErrorShape
  if (err.response) {
    const httpStatus = Number(err.response.status) || 0
    const apiError = buildHttpError(
      pickErrorPayload(err.response.data),
      httpStatus,
      err.response,
      err.request
    )
    if (notifyExpired && httpStatus === 401) {
      notifyAuthExpired()
    }
    return apiError
  }
  const message = err.request
    ? translate('errors.network.unavailable')
    : err.message || translate('errors.network.generic')
  return buildNetworkError(message, err.request)
}

/**
 * 通道核心：发起请求 → 解包 CommonResponse 信封 → 成功返回 data 体；
 * 业务错误（HTTP 200 但 code 非 2xx 成功）与传输错误统一以 ApiError 拒绝。
 */
async function requestEnvelope<T>(
  config: AxiosRequestConfig,
  options: { notifyAuthExpired: boolean }
): Promise<T> {
  let response: AxiosResponse
  try {
    response = await maintenanceHttp.request(config)
  } catch (error) {
    throw normalizeTransportError(error, options.notifyAuthExpired)
  }
  const res = response.data
  if (isSuccessEnvelope(res)) {
    return res.data as T
  }
  const businessError = buildBusinessError(
    res as { code?: unknown, msg?: string } | null | undefined,
    response.status,
    response
  )
  // 业务码 401（如 MAINTENANCE_TOKEN_INVALID 以 HTTP 200 信封返回时）同样视为
  // 维护会话失效；登录请求自身（notifyAuthExpired=false）的 401 是凭据错误，
  // 不派发（尚无维护会话可言）
  if (options.notifyAuthExpired && businessError.code === '401') {
    notifyAuthExpired()
  }
  throw businessError
}

// ---------------------------------------------------------------------------
// 公开 API
// ---------------------------------------------------------------------------

/** POST /maintenance/auth 成功数据体（后端 maintenance.py 契约） */
export interface MaintenanceAuthData {
  /** 维护 token 本体（仅存内存；过期前用于维护通道 Bearer 注入） */
  maintenanceToken: string
  tokenType: string
  /** 有效秒数（供 UI 调度 /auth/renew 续期） */
  expiresIn: number
}

/**
 * 维护认证：账户+密码+可选 TOTP → 独立短期维护 token。
 * 凭据错误（业务 401/423）以 ApiError 拒绝且不派发 auth expired。
 */
export async function maintenanceLogin(
  username: string,
  password: string,
  twofaCode?: string
): Promise<MaintenanceAuthData> {
  const data = await requestEnvelope<MaintenanceAuthData>(
    {
      url: '/maintenance/auth',
      method: 'post',
      data: { username, password, twofa_code: twofaCode ?? null }
    },
    { notifyAuthExpired: false }
  )
  maintenanceToken = data.maintenanceToken
  return data
}

/** 维护通道请求方法集 */
export type MaintenanceMethod = 'get' | 'post' | 'put' | 'delete'

/**
 * 维护通道通用请求：注入 `Authorization: Bearer <maintenanceToken>`，
 * 成功返回信封 data 体（T）；401 派发 onMaintenanceAuthExpired；
 * 503/网络错误静默以 ApiError 拒绝（不重试、不 toast、不触碰其他会话状态）。
 */
export function maintenanceRequest<T = Record<string, unknown>>(
  method: MaintenanceMethod,
  url: string,
  data?: unknown
): Promise<T> {
  const headers: Record<string, string> = {}
  if (maintenanceToken) {
    headers['Authorization'] = `Bearer ${maintenanceToken}`
  }
  return requestEnvelope<T>({ url, method, data, headers }, { notifyAuthExpired: true })
}

/**
 * GET /maintenance/status 的宽松映射：
 * 已知字段（state/attemptId/epoch/reasonCode）显式收敛，其余扩展字段
 * （heldReason/activeLeases/cancelRequested/bootRecovery…）统一收进 extra，
 * 避免随后端状态面演进频繁改前端类型。
 */
export interface MaintenanceStatusData {
  /** 错误载荷中的原因码（成功响应无此字段，如 NOT_MAINTENANCE） */
  reasonCode?: string
  /** 粗粒度维护状态（PREPARING/DRAINING/FROZEN/…；成功响应必有） */
  state: string
  attemptId?: string
  epoch?: string
  /** 未知扩展字段收敛（值类型由消费方按需收窄） */
  extra: Record<string, unknown>
}

const KNOWN_STATUS_KEYS: readonly string[] = ['state', 'attemptId', 'epoch', 'reasonCode']

/** 纯映射：/maintenance/status 原始 data → MaintenanceStatusData */
export function mapMaintenanceStatusData(raw: Record<string, unknown>): MaintenanceStatusData {
  const extra: Record<string, unknown> = {}
  Object.keys(raw).forEach((key) => {
    if (!KNOWN_STATUS_KEYS.includes(key)) {
      extra[key] = raw[key]
    }
  })
  return {
    reasonCode: typeof raw.reasonCode === 'string' ? raw.reasonCode : undefined,
    state: typeof raw.state === 'string' ? raw.state : '',
    attemptId: typeof raw.attemptId === 'string' ? raw.attemptId : undefined,
    epoch: typeof raw.epoch === 'string' ? raw.epoch : undefined,
    extra
  }
}

/** 粗粒度维护状态（需维护 token；401 → onMaintenanceAuthExpired） */
export async function getMaintenanceStatus(): Promise<MaintenanceStatusData> {
  const data = await maintenanceRequest<Record<string, unknown>>('get', '/maintenance/status')
  return mapMaintenanceStatusData(data)
}
