import request from '@/utils/request'
import { DashboardResponse } from '@/types/dashboard'

export const getDashboardData = (): Promise<DashboardResponse> =>
  request({
    url: '/dashboard',
    method: 'get'
  })
