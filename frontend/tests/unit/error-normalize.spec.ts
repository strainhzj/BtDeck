/**
 * error-normalize.ts 归一化逻辑单元测试。
 *
 * 验证 P0-1 的核心契约：无论后端返回何种形态的错误，前端都能拿到
 * 统一的 ApiError（含 code/httpStatus/message，并兼容 msg/response getter）。
 *
 * 对应 PLANS/v1.0.5-audit.md 手动 e2e 清单第 2/3/5/6 项的自动化等价物。
 */
import {
  SUCCESS_CODES,
  extractFromDetail,
  isLoginRequest,
  buildBusinessError,
  buildNetworkError,
  buildHttpError,
  pickErrorPayload
} from '@/utils/error-normalize'
import { ApiError } from '@/types/api'

describe('SUCCESS_CODES', () => {
  it('包含 200/206/207 三个业务成功码', () => {
    expect(SUCCESS_CODES.has('200')).toBe(true)
    expect(SUCCESS_CODES.has('206')).toBe(true)
    expect(SUCCESS_CODES.has('207')).toBe(true)
  })

  it('不包含错误码', () => {
    expect(SUCCESS_CODES.has('401')).toBe(false)
    expect(SUCCESS_CODES.has('500')).toBe(false)
    expect(SUCCESS_CODES.has('422')).toBe(false)
  })
})

describe('isLoginRequest', () => {
  it('识别 /login 路径', () => {
    expect(isLoginRequest({ url: '/api/v1/auth/login' })).toBe(true)
  })

  it('非登录路径返回 false', () => {
    expect(isLoginRequest({ url: '/api/v1/torrents/getList' })).toBe(false)
  })

  it('无 url 配置返回 false', () => {
    expect(isLoginRequest(null)).toBe(false)
    expect(isLoginRequest({})).toBe(false)
  })
})

describe('extractFromDetail', () => {
  it('字符串 detail → code 取 HTTP status, message 取 detail', () => {
    const r = extractFromDetail('info_hash格式错误', 400)
    expect(r.code).toBe('400')
    expect(r.message).toBe('info_hash格式错误')
  })

  it('空字符串 detail → 走默认 message', () => {
    const r = extractFromDetail('', 404)
    expect(r.code).toBe('404')
    expect(r.message).toBe('请求错误')
  })

  it('CommonResponse envelope dict → 复用 code/msg', () => {
    // 模拟 dependencies.py:84 的 detail=CommonResponse.model_dump()
    const r = extractFromDetail(
      { status: 'error', msg: '认证失败', code: '401', data: null },
      401
    )
    expect(r.code).toBe('401')
    expect(r.message).toBe('认证失败')
  })

  it('envelope dict 缺 code → 回退到 HTTP status', () => {
    const r = extractFromDetail({ msg: '某种错误' }, 500)
    expect(r.code).toBe('500')
    expect(r.message).toBe('某种错误')
  })

  it('422 校验数组 → code=422, message 取首条 msg', () => {
    const r = extractFromDetail(
      [
        { loc: ['body', 'name'], msg: 'field required', type: 'value_error.missing' },
        { loc: ['body', 'age'], msg: 'not int', type: 'type_error.integer' }
      ],
      422
    )
    expect(r.code).toBe('422')
    expect(r.message).toBe('field required')
  })

  it('空数组 → 默认校验失败 message', () => {
    const r = extractFromDetail([], 422)
    expect(r.code).toBe('422')
    expect(r.message).toBe('参数校验失败')
  })

  it('其它 dict（非 envelope）→ JSON 序列化为 message', () => {
    const r = extractFromDetail({ foo: 'bar' }, 500)
    expect(r.code).toBe('500')
    expect(r.message).toBe('{"foo":"bar"}')
  })

  it('null/undefined → 默认请求错误', () => {
    expect(extractFromDetail(null, 500).message).toBe('请求错误')
    expect(extractFromDetail(undefined, 500).code).toBe('500')
  })
})

describe('ApiError 形态与兼容性', () => {
  it('是 Error 的实例，e.message 可读', () => {
    const err = buildBusinessError({ code: '500', msg: '服务器错误' }, 200)
    expect(err).toBeInstanceOf(Error)
    expect(err.message).toBe('服务器错误')
  })

  it('name === ApiError', () => {
    const err = buildBusinessError({ code: '404' }, 200)
    expect(err.name).toBe('ApiError')
  })

  it('兼容 e.msg getter（存量代码依赖）', () => {
    const err = buildBusinessError({ code: '422', msg: '参数错误' }, 200)
    expect(err.msg).toBe('参数错误')
  })

  it('兼容 e.response.data.msg 与 e.response.status getter', () => {
    const err = buildHttpError('未找到备份记录', 404)
    expect(err.response.status).toBe(404)
    expect(err.response.data.msg).toBe('未找到备份记录')
    expect(err.response.data.code).toBe('404')
  })

  it('保留 rawResponse 引用', () => {
    const fakeResponse = { status: 500 }
    const err = buildHttpError('错误', 500, fakeResponse)
    expect(err.rawResponse).toBe(fakeResponse)
  })

  it('instanceof ApiError 可用于类型守卫', () => {
    const err = buildNetworkError('网络断开')
    expect(err instanceof ApiError).toBe(true)
  })
})

describe('buildBusinessError', () => {
  it('HTTP 200 + code=401 业务错误', () => {
    const err = buildBusinessError({ code: '401', msg: 'token验证失败' }, 200)
    expect(err.code).toBe('401')
    expect(err.httpStatus).toBe(200)
    expect(err.message).toBe('token验证失败')
  })

  it('缺 code 时默认 500', () => {
    const err = buildBusinessError(null, 200)
    expect(err.code).toBe('500')
    expect(err.message).toBe('操作失败')
  })
})

describe('buildHttpError', () => {
  it('HTTP 401 + CommonResponse detail（P0-2 后的真实形态）', () => {
    const err = buildHttpError(
      { status: 'error', msg: '认证失败', code: '401', data: null },
      401
    )
    expect(err.code).toBe('401')
    expect(err.httpStatus).toBe(401)
    expect(err.message).toBe('认证失败')
  })

  it('HTTP 500 + 纯字符串 detail', () => {
    const err = buildHttpError('导出失败: 磁盘满', 500)
    expect(err.code).toBe('500')
    expect(err.message).toBe('导出失败: 磁盘满')
  })

  it('HTTP 422 + 数组 detail', () => {
    const err = buildHttpError([{ msg: 'age must be int' }], 422)
    expect(err.code).toBe('422')
    expect(err.message).toBe('age must be int')
  })
})

describe('pickErrorPayload', () => {
  it('平铺 envelope body（P0-3 归一化形态）→ 返回整个 body', () => {
    // P0-3 异常处理器把 HTTPException 归一化为 {status,msg,code,data}，
    // body 层没有 detail 包装。pickErrorPayload 必须识别并整体返回。
    const body = { status: 'error', msg: 'token验证失败', code: '401', data: null }
    expect(pickErrorPayload(body)).toBe(body)
  })

  it('带 message 字段的 envelope（FastAPI 默认形态）→ 返回整个 body', () => {
    const body = { detail: 'Not found', message: '资源不存在' }
    expect(pickErrorPayload(body)).toBe(body)
  })

  it('非 envelope dict（无 code/msg/message）→ 回退读 body.detail', () => {
    // 兼容未走全局处理器的旧式响应：{ detail: "..." }
    expect(pickErrorPayload({ detail: '纯字符串 detail' })).toBe('纯字符串 detail')
  })

  it('非 envelope dict 且无 detail → 返回 undefined', () => {
    expect(pickErrorPayload({ foo: 'bar' })).toBeUndefined()
  })

  it('422 detail 数组被包在 data.errors（P0-3 形态）→ 整体当 envelope', () => {
    // P0-3 把 422 数组包成 {status,msg:'field required',code:'422',data:{errors:[...]}}
    const body = {
      status: 'error',
      msg: 'field required',
      code: '422',
      data: { errors: [{ loc: ['body', 'x'], msg: 'field required' }] }
    }
    expect(pickErrorPayload(body)).toBe(body)
  })

  it('非对象入参（字符串/null）→ 原样返回', () => {
    expect(pickErrorPayload('裸字符串')).toBe('裸字符串')
    expect(pickErrorPayload(null)).toBeNull()
    expect(pickErrorPayload(undefined)).toBeUndefined()
  })
})

describe('Bug-1 集成：P0-3 平铺 401 → 前端 ApiError 保真', () => {
  // 这是 request.ts 拦截器的真实链路：pickErrorPayload(error.response.data) → buildHttpError。
  // 早期 request.ts 只读 error.response.data?.detail，但 P0-3 后 401 body 平铺无 detail，
  // 导致后端真实消息降级为通用「请求错误」。此测试锁死修复后的契约。
  it('401 平铺 envelope body → ApiError.code/message 保真', () => {
    const body = { status: 'error', msg: 'token验证失败', code: '401', data: null }
    const apiError = buildHttpError(
      pickErrorPayload(body),
      401,
      { status: 401, data: body } as any
    )
    expect(apiError.code).toBe('401')
    expect(apiError.httpStatus).toBe(401)
    expect(apiError.message).toBe('token验证失败') // 关键：不再降级为「请求错误」
  })

  it('401 旧式 {detail: string} → 仍能解包（向后兼容）', () => {
    const body = { detail: 'Invalid access token' }
    const apiError = buildHttpError(
      pickErrorPayload(body),
      401,
      { status: 401, data: body } as any
    )
    expect(apiError.code).toBe('401')
    expect(apiError.message).toBe('Invalid access token')
  })

  it('500 平铺 envelope body → ApiError 保真', () => {
    const body = {
      status: 'error',
      msg: '服务器内部错误',
      code: '500',
      data: null
    }
    const apiError = buildHttpError(pickErrorPayload(body), 500)
    expect(apiError.code).toBe('500')
    expect(apiError.message).toBe('服务器内部错误')
  })
})

describe('buildNetworkError', () => {
  it('code=0, httpStatus=0', () => {
    const err = buildNetworkError('网络连接失败')
    expect(err.code).toBe('0')
    expect(err.httpStatus).toBe(0)
    expect(err.message).toBe('网络连接失败')
  })
})
