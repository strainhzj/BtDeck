export interface EnableScheduleSource {
  enableSchedule?: boolean
  enable_schedule?: boolean
  schedule_rules?: ReadonlyArray<unknown>
}

/**
 * 分时段开关必须以持久化字段为准，不能根据历史规则是否存在进行推断。
 */
export function resolveEnableSchedule(settings: EnableScheduleSource): boolean {
  return settings.enableSchedule ?? settings.enable_schedule ?? false
}
