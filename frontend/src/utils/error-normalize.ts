/**
 * API 错误归一化纯逻辑（无副作用，便于单测）。
 *
 * 从 request.ts 抽出，避免单测时引入 Vuex store / element-ui Message 副作用。
 * 详见审计修复 PLANS/v1.0.5-audit.md P0-1。
 */

import { ApiError } from '@/types/api'

/**
 * 业务成功码白名单。
 *
 * 这些 code 虽非 '200'，但属于业务级"成功/部分成功/需确认"语义，
 * 不归一化为 ApiError，直接 return res 让业务代码处理：
 * - '200'：标准成功
 * - '206'：需确认（如 setting-templates apply 的 needs_path_mapping_confirmation）
 * - '202'：请求已受理，后台异步任务已排队
 * - '207'：Multi-Status 部分成功（如批量添加种子）
 */
export const SUCCESS_CODES = new Set(['200', '202', '206', '207'])

/**
 * 从 HTTPException 的 detail 中提取 (code, message)。
 *
 * 后端 HTTPException.detail 有多种形态（审计第5节）：
 * 1. 纯字符串（如 torrent_backup.py:917）→ code 取 HTTP status，message 取 detail
 * 2. CommonResponse.model_dump() 字典（含 code/msg，如 dependencies.py:84）→ 复用
 * 3. RequestValidationError 的 array（422）→ message 取首条 msg
 * 4. 其它 → message 走 JSON 序列化兜底
 *
 * 经 P0-3 全局异常处理器后，后端已统一返回 CommonResponse body，
 * 但这里仍保留判定树以兼容任何遗漏路径。
 */
export function extractFromDetail(
  detail: unknown,
  httpStatus: number
): { code: string, message: string } {
  if (Array.isArray(detail)) {
    // 422 校验错误数组
    const first = detail[0] as Record<string, unknown> | undefined
    const message =
      (first && ((first.msg as string) || (first.message as string))) ||
      '参数校验失败'
    return { code: '422', message }
  }
  if (detail && typeof detail === 'object') {
    const d = detail as Record<string, unknown>
    // envelope dict（CommonResponse 形态）
    if ('code' in d || 'msg' in d || 'message' in d) {
      return {
        code: String(d.code ?? httpStatus),
        message: (d.msg as string) || (d.message as string) || '请求错误'
      }
    }
    return { code: String(httpStatus), message: JSON.stringify(detail) }
  }
  if (typeof detail === 'string') {
    return { code: String(httpStatus), message: detail || '请求错误' }
  }
  return { code: String(httpStatus), message: '请求错误' }
}

/**
 * 是否为登录接口请求（豁免 401 跳转逻辑）。
 *
 * 登录接口的 code=401 表达"用户名/密码错误"业务语义，不是真正的认证失效，
 * 必须保留在登录页并显示错误，而非跳转登录页（会形成死循环）。
 */
export function isLoginRequest(config: unknown): boolean {
  const url = (config as { url?: string } | null)?.url
  return !!url && url.includes('/login')
}

/**
 * 从 HTTP 错误响应体中提取交给 extractFromDetail 的载荷。
 *
 * 后端 P0-3 全局异常处理器（app/exception_handlers.py）把 HTTPException 归一化
 * 为「平铺」的 CommonResponse body：
 *   { status, msg, code, data }          ← 没有 detail 包装
 * 因此优先把整个 body 当作 envelope 交给 extractFromDetail；只有当 body 本身
 * 不像 envelope（无 code/msg 字段）时，才回退读取旧式 body.detail（兼容任何
 * 未走全局处理器的直出错误，如中间件层 4xx）。
 *
 * 这修复了 request.ts 早期只读 body.detail 的 bug：P0-3 后 401 body 平铺无 detail，
 * 导致后端真实消息（如「token验证失败」）被降级为通用「请求错误」。
 */
export function pickErrorPayload(data: unknown): unknown {
  if (data && typeof data === 'object') {
    const d = data as Record<string, unknown>
    if ('code' in d || 'msg' in d || 'message' in d) {
      return d
    }
    return d.detail
  }
  return data
}

/**
 * 构造业务码错误（HTTP 200 但 code 非 2xx 成功）的 ApiError。
 */
export function buildBusinessError(
  res: { code?: unknown, msg?: string } | null | undefined,
  httpStatus: number,
  rawResponse?: unknown
): ApiError {
  const code = String(res?.code ?? '500')
  const message = res?.msg || '操作失败'
  return new ApiError(message, { code, httpStatus, rawResponse })
}

/**
 * 构造网络层错误（无 HTTP response）的 ApiError。
 */
export function buildNetworkError(
  message: string,
  rawRequest?: unknown
): ApiError {
  return new ApiError(message, {
    code: '0',
    httpStatus: 0,
    rawRequest
  })
}

/**
 * 构造 HTTP 错误（服务器返回 4xx/5xx）的 ApiError。
 */
export function buildHttpError(
  detail: unknown,
  httpStatus: number,
  rawResponse?: unknown,
  rawRequest?: unknown
): ApiError {
  const { code, message } = extractFromDetail(detail, httpStatus)
  return new ApiError(message, { code, httpStatus, rawResponse, rawRequest })
}
