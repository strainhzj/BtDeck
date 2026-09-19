/**
 * 双语 P4：错误契约前端入口（i18n apiErrorMessage / apiResponseMessage）扩展契约。
 *
 * P2 批已建立 reasonCode → errors.byCode.camelCase 本地化骨架；本批锁定：
 * - P4 新增 reasonCode（种子操作 / Tracker / 查询模板 / 添加链路）两语言可用；
 * - E17：422 校验错误（data.errors 数组）按 pydantic type/loc 字典化，不透传英文原文；
 * - apiResponseMessage：resolved 业务错误响应优先 reasonCode，其余回退原始 msg；
 * - 兜底语义不回退：未知 reasonCode → fallback（英文界面不透中文 msg）。
 */

import i18n, { apiErrorMessage, apiResponseMessage, setLocale } from '@/i18n'

const originalLocale = i18n.locale

afterAll(() => {
  setLocale(originalLocale as 'zh-CN' | 'en')
})

/** 构造携带信封的 ApiError 形态（rawResponse.data 即拦截器保留的业务/HTTP 信封） */
function envelopeError(envelope: { code: string, msg: string, data: unknown }): Error & {
  rawResponse: { data: typeof envelope }
} {
  const err = new Error(envelope.msg) as Error & { rawResponse: { data: typeof envelope } }
  err.rawResponse = { data: envelope }
  return err
}

describe('apiErrorMessage：P4 reasonCode 本地化（zh-CN）', () => {
  beforeEach(() => {
    setLocale('zh-CN')
  })

  it.each([
    ['DOWNLOADER_CACHE_UNAVAILABLE', 'downloaderCacheUnavailable', '下载器缓存服务暂不可用，请稍后重试'],
    ['DOWNLOADER_OFFLINE', 'downloaderOffline', '下载器已失效，请检查下载器状态后重试'],
    ['DOWNLOADER_CONNECTION_MISSING', 'downloaderConnectionMissing', '下载器连接不可用，请稍后重试'],
    ['DOWNLOADER_NO_TORRENTS', 'downloaderNoTorrents', '该下载器下没有种子'],
    ['TORRENT_HASHES_REQUIRED', 'torrentHashesRequired', '请选择要操作的种子'],
    ['TORRENT_RECORDS_NOT_FOUND', 'torrentRecordsNotFound', '未找到任何种子记录'],
    ['TORRENT_OPERATION_FAILED', 'torrentOperationFailed', '种子操作失败，请稍后重试'],
    ['TORRENT_OPERATION_INTERNAL', 'torrentOperationInternal', '操作异常，请稍后重试'],
    ['TORRENT_FILE_REQUIRED', 'torrentFileRequired', '请选择种子文件'],
    ['TORRENT_FILE_INVALID', 'torrentFileInvalid', '种子文件无效或已损坏'],
    ['TORRENT_ADD_FAILED', 'torrentAddFailed', '添加种子失败，请稍后重试'],
    ['TORRENT_BATCH_SUBMIT_FAILED', 'torrentBatchSubmitFailed', '提交批量任务失败，请稍后重试'],
    ['TRACKER_URL_REQUIRED', 'trackerUrlRequired', '请填写 Tracker 地址'],
    ['TRACKER_NOT_FOUND', 'trackerNotFound', '未找到要替换的 Tracker'],
    ['SEARCH_TEMPLATE_NOT_FOUND', 'searchTemplateNotFound', '查询模板不存在'],
    ['SEARCH_TEMPLATE_FORBIDDEN', 'searchTemplateForbidden', '无权操作此模板'],
    ['SEARCH_TEMPLATE_INVALID_CONDITIONS', 'searchTemplateInvalidConditions', '查询条件无效，请检查后重试'],
    ['INTERNAL_ERROR', 'internalError', '服务器内部错误，请稍后重试'],
    ['DB_OPERATION_FAILED', 'dbOperationFailed', '数据库操作失败，请稍后重试']
  ])('%s → errors.byCode.%s 中文文案', (code, _key, expected) => {
    const err = envelopeError({
      code: '500',
      msg: '后端固定中文 msg（前端不读）',
      data: { reasonCode: code }
    })
    expect(apiErrorMessage(err, '兜底文案')).toBe(expected)
  })

  it('英文语言下同批 reasonCode 均有英文文案（抽样）', () => {
    setLocale('en')
    const err = envelopeError({
      code: '404',
      msg: '未找到任何种子记录',
      data: { reasonCode: 'TORRENT_RECORDS_NOT_FOUND' }
    })
    expect(apiErrorMessage(err, 'fallback')).toBe('No matching torrent records were found.')
    setLocale('zh-CN')
  })

  it('未登记 reasonCode → fallback（英文界面不透出中文 msg）', () => {
    const err = envelopeError({
      code: '500',
      msg: '某个未契约化路径的中文消息',
      data: { reasonCode: 'NOT_YET_CONTRACTED' }
    })
    expect(apiErrorMessage(err, '兜底文案')).toBe('兜底文案')
  })

  it('无 reasonCode → error.message 透传（未契约化路径保留原始信息）', () => {
    const err = envelopeError({ code: '500', msg: '原始消息', data: null })
    expect(apiErrorMessage(err, '兜底文案')).toBe('原始消息')
  })
})

describe('apiErrorMessage：E17 422 校验错误按 type/loc 字典化', () => {
  beforeEach(() => {
    setLocale('zh-CN')
  })

  it('type=missing + loc 末段字段名 → 必填参数缺失', () => {
    const err = envelopeError({
      code: '422',
      msg: 'Field required',
      data: { errors: [{ type: 'missing', loc: ['body', 'torrent_files'], msg: 'Field required' }] }
    })
    expect(apiErrorMessage(err, '兜底')).toBe('必填参数缺失：torrent_files')
  })

  it('type=too_short → 参数项数不足（pydantic v2 列表 min_length）', () => {
    const err = envelopeError({
      code: '422',
      msg: 'List should have at least 1 item',
      data: { errors: [{ type: 'too_short', loc: ['body', 'hashes'], msg: 'too short' }] }
    })
    expect(apiErrorMessage(err, '兜底')).toBe('参数项数不足：hashes')
  })

  it('type=value_error → 参数无效（业务条件校验经 pydantic 包装）', () => {
    const err = envelopeError({
      code: '422',
      msg: 'Value error, template source must be simple or advanced',
      data: {
        errors: [{ type: 'value_error', loc: ['body', 'conditions'], msg: 'Value error, ...' }]
      }
    })
    expect(apiErrorMessage(err, '兜底')).toBe('参数无效：conditions')
  })

  it('多条校验错误至多取前 2 条拼接；未知 type 回退 generic', () => {
    const err = envelopeError({
      code: '422',
      msg: 'x',
      data: {
        errors: [
          { type: 'weird_future_type', loc: ['body', 'a'], msg: 'x' },
          { type: 'missing', loc: ['body', 'b'], msg: 'y' },
          { type: 'missing', loc: ['body', 'c'], msg: 'z' }
        ]
      }
    })
    expect(apiErrorMessage(err, '兜底')).toBe('请求参数校验失败（a）；必填参数缺失：b')
  })

  it('英文语言下 422 文案同步英文', () => {
    setLocale('en')
    const err = envelopeError({
      code: '422',
      msg: 'Field required',
      data: { errors: [{ type: 'missing', loc: ['body', 'torrent_files'], msg: 'Field required' }] }
    })
    expect(apiErrorMessage(err, 'fallback')).toBe('Missing required field: torrent_files')
    setLocale('zh-CN')
  })

  it('reasonCode 优先于 422 数组（两者同现时按契约码走）', () => {
    const err = envelopeError({
      code: '422',
      msg: 'x',
      data: {
        reasonCode: 'SEARCH_TEMPLATE_INVALID_CONDITIONS',
        errors: [{ type: 'missing', loc: ['body', 'x'], msg: 'y' }]
      }
    })
    expect(apiErrorMessage(err, '兜底')).toBe('查询条件无效，请检查后重试')
  })
})

describe('apiResponseMessage：resolved 业务错误响应（拦截器未拒绝分支）', () => {
  beforeEach(() => {
    setLocale('zh-CN')
  })

  it('携带 reasonCode 的响应优先本地化', () => {
    const response = {
      code: '206',
      msg: '部分失败：后端中文 msg',
      data: { reasonCode: 'DOWNLOADER_NO_TORRENTS' }
    }
    expect(apiResponseMessage(response, '兜底')).toBe('该下载器下没有种子')
  })

  it('无 reasonCode 回退原始 msg；空响应回退 fallback', () => {
    expect(apiResponseMessage({ code: '500', msg: '原始消息', data: null }, '兜底')).toBe('原始消息')
    expect(apiResponseMessage(null, '兜底')).toBe('兜底')
  })
})
