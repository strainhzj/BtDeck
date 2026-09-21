import request from '@/utils/request'

/**
 * 导出故障转储/排查/状态分析快照（axios blob，携带认证头）
 *
 * 后端 GET /api/v1/health/diagnosis 以 attachment 返回诊断 JSON
 * （版本/构建身份 + readiness 检查 + 同步任务健康 + 进程 RSS）。
 * 文件名由前端生成：blob 响应经拦截器只回传原始数据，读不到响应头。
 */
export function exportDiagnosisFile() {
  return request<Blob>({
    url: '/health/diagnosis',
    method: 'get',
    responseType: 'blob'
  })
}
