import request from '@/utils/request'
import { DashboardResponse } from '@/types/dashboard'

export const getDashboardData = (): Promise<DashboardResponse> =>
  request<DashboardResponse>({
    url: '/dashboard',
    method: 'get'
  })
