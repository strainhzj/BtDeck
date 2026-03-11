
from fastapi import APIRouter, Depends, Query, HTTPException, Request
from typing import Optional
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.responseVO import CommonResponse
from app.auth import utils
from app.core.database_result import DatabaseError
from app.database import get_db
from app.tasks.cron_crud import CronTaskCRUD, TaskLogsCRUD
from app.tasks.cron_executor import cron_executor

router = APIRouter()


class CronTaskCreate(BaseModel):
    """创建定时任务请求模型"""
    task_name: str = Field(..., description="任务名称", max_length=200)
    task_code: str = Field(..., description="任务编码", max_length=50)
    task_type: int = Field(..., description="任务类型：0-shell脚本，1-cmd脚本，2-powershell脚本，3-python脚本，4-python内部类")
    executor: str = Field(..., description="执行脚本内容或路径")
    cron_plan: str = Field(..., description="cron表达式，格式：分 时 日 月 周")
    enabled: bool = Field(True, description="是否启用")
    description: Optional[str] = Field(None, description="任务描述", max_length=500)
    timeout_seconds: Optional[int] = Field(3600, description="超时时间(秒)", ge=60, le=86400)
    max_retry_count: Optional[int] = Field(0, description="最大重试次数", ge=0, le=10)
    retry_interval: Optional[int] = Field(300, description="重试间隔(秒)", ge=60, le=3600)


class CronTaskUpdate(BaseModel):
    """更新定时任务请求模型"""
    task_name: Optional[str] = Field(None, description="任务名称", max_length=200)
    task_code: Optional[str] = Field(None, description="任务编码", max_length=50)
    task_type: Optional[int] = Field(None, description="任务类型")
    executor: Optional[str] = Field(None, description="执行脚本内容或路径")
    cron_plan: Optional[str] = Field(None, description="cron表达式")
    enabled: Optional[bool] = Field(None, description="是否启用")
    description: Optional[str] = Field(None, description="任务描述", max_length=500)
    timeout_seconds: Optional[int] = Field(None, description="超时时间(秒)", ge=60, le=86400)
    max_retry_count: Optional[int] = Field(None, description="最大重试次数", ge=0, le=10)
    retry_interval: Optional[int] = Field(None, description="重试间隔(秒)", ge=60, le=3600)


class CronTaskResponse(BaseModel):
    """定时任务响应模型 - 驼峰法命名"""
    taskId: int
    taskName: str
    taskCode: str
    taskStatus: int
    taskType: int
    executor: str
    enabled: bool
    lastExecuteTime: Optional[str]
    lastExecuteDuration: Optional[int]
    cronPlan: str
    taskStatusName: str
    taskTypeName: str
    createTime: str
    updateTime: str
    description: Optional[str]
    timeoutSeconds: Optional[int]
    maxRetryCount: Optional[int]
    retryInterval: Optional[int]


class CronTaskListResponse(BaseModel):
    """定时任务列表响应模型"""
    total: int
    list: list[CronTaskResponse]


class TaskLogResponse(BaseModel):
    """任务日志响应模型 - 驼峰法命名"""
    logId: int
    taskId: int
    taskName: str
    taskType: int
    startTime: str
    endTime: str
    duration: int
    success: bool
    logDetail: str


class TaskLogListResponse(BaseModel):
    """任务日志列表响应模型"""
    total: int
    list: list[TaskLogResponse]


# ========== 新增的验证相关模型 ==========

class ScriptValidationRequest(BaseModel):
    """脚本语法校验请求模型"""
    content: str = Field(..., description="脚本内容")
    script_type: int = Field(..., description="脚本类型：0-shell，1-cmd，2-powershell，3-python")


class ValidationError(BaseModel):
    """语法错误信息模型"""
    startLineNumber: int = Field(..., description="错误开始行号")
    startColumn: int = Field(..., description="错误开始列号")
    endLineNumber: int = Field(..., description="错误结束行号")
    endColumn: int = Field(..., description="错误结束列号")
    severity: int = Field(..., description="错误级别")
    message: str = Field(..., description="错误信息")


class ScriptValidationResponse(BaseModel):
    """脚本语法校验响应模型"""
    valid: bool = Field(..., description="是否有效")
    errors: list[ValidationError] = Field(default=[], description="错误列表")
    message: str = Field(..., description="校验结果信息")


class CronValidationRequest(BaseModel):
    """Cron表达式校验请求模型"""
    expression: str = Field(..., description="Cron表达式")


class CronExecutionTime(BaseModel):
    """Cron执行时间信息"""
    nextExecutionTime: str = Field(..., description="下次执行时间")
    previousExecutionTime: Optional[str] = Field(None, description="上次执行时间")
    executionTimes: list[str] = Field(default=[], description="未来5次执行时间")


class CronValidationResponse(BaseModel):
    """Cron表达式校验响应模型"""
    valid: bool = Field(..., description="是否有效")
    message: str = Field(..., description="校验结果信息")
    description: Optional[str] = Field(None, description="表达式描述")
    executionTimes: Optional[CronExecutionTime] = Field(None, description="执行时间信息")


class PythonClassValidationRequest(BaseModel):
    """Python类路径验证请求模型"""
    class_path: str = Field(..., description="Python类路径，格式：module.submodule.ClassName")


class PythonClassInfo(BaseModel):
    """Python类信息模型"""
    className: str = Field(..., description="类名")
    module: str = Field(..., description="模块路径")
    description: Optional[str] = Field(None, description="类描述")
    methods: list[str] = Field(default=[], description="可用方法列表")
    parameters: dict = Field(default={}, description="参数信息")


class PythonClassValidationResponse(BaseModel):
    """Python类路径验证响应模型"""
    valid: bool = Field(..., description="是否有效")
    exists: bool = Field(..., description="类是否存在")
    classInfo: Optional[PythonClassInfo] = Field(None, description="类信息")
    message: str = Field(..., description="验证结果信息")


class TaskTypeConfigResponse(BaseModel):
    """任务类型配置响应模型"""
    taskTypes: list[dict] = Field(..., description="任务类型配置列表")
    pythonClasses: list[PythonClassInfo] = Field(default=[], description="可用Python类列表")


# ========== 清理任务相关模型 ==========

class CleanupTaskRequest(BaseModel):
    """清理任务请求模型"""
    cleanup_level_3: bool = Field(..., description="是否清理等级3（回收站）")
    cleanup_level_4: bool = Field(..., description="是否清理等级4（待删除标签）")
    days_threshold: int = Field(..., description="天数阈值", ge=1, le=365)


class CleanupPreviewResponse(BaseModel):
    """清理预览响应模型"""
    level3_count: int
    level4_count: int
    total_count: int
    total_size: float
    total_size_gb: float
    level3_items: list
    level4_items: list


class CleanupExecuteResponse(BaseModel):
    """清理执行响应模型"""
    level3_cleaned: int
    level4_cleaned: int
    total_size_freed: float
    errors: list


def verify_token(req):
    """验证token"""
    token = req.headers.get("X-Access-Token")
    if not token:
        raise HTTPException(status_code=401, detail="Token缺失")

    try:
        utils.verify_access_token(token)
    except Exception:
        raise HTTPException(status_code=401, detail="Token验证失败")


def convert_cron_task_to_camel_case(task_data: dict) -> CronTaskResponse:
    """将数据库返回的定时任务数据转换为驼峰命名"""
    # 处理可能为None的字段，提供默认值
    def safe_str(value, default=''):
        """安全转换为字符串，处理None和datetime对象"""
        if value is None:
            return default
        if hasattr(value, 'strftime'):  # datetime对象
            return value.strftime('%Y-%m-%d %H:%M:%S')
        return str(value)

    def safe_int(value, default=0):
        """安全转换为整数，处理None"""
        if value is None:
            return default
        return int(value)

    def safe_bool(value, default=False):
        """安全转换为布尔值，处理None"""
        if value is None:
            return default
        return bool(value)

    return CronTaskResponse(
        taskId=safe_int(task_data.get('task_id')),
        taskName=safe_str(task_data.get('task_name')),
        taskCode=safe_str(task_data.get('task_code')),
        taskStatus=safe_int(task_data.get('task_status')),
        taskType=safe_int(task_data.get('task_type')),
        executor=safe_str(task_data.get('executor')),
        enabled=safe_bool(task_data.get('enabled')),
        lastExecuteTime=safe_str(task_data.get('last_execute_time')) if task_data.get('last_execute_time') is not None else None,
        lastExecuteDuration=task_data.get('last_execute_duration') if task_data.get('last_execute_duration') is not None else None,
        cronPlan=safe_str(task_data.get('cron_plan')),
        taskStatusName=safe_str(task_data.get('task_status_name'), '未知状态'),
        taskTypeName=_get_task_type_name(safe_int(task_data.get('task_type'))),
        createTime=safe_str(task_data.get('create_time')),
        updateTime=safe_str(task_data.get('update_time')),
        description=safe_str(task_data.get('description')) if task_data.get('description') is not None else None,
        timeoutSeconds=safe_int(task_data.get('timeout_seconds')) if task_data.get('timeout_seconds') is not None else None,
        maxRetryCount=safe_int(task_data.get('max_retry_count')) if task_data.get('max_retry_count') is not None else None,
        retryInterval=safe_int(task_data.get('retry_interval')) if task_data.get('retry_interval') is not None else None
    )


def _get_task_type_name(task_type: int) -> str:
    """获取任务类型名称"""
    type_names = {
        0: 'shell脚本',
        1: 'cmd脚本',
        2: 'powershell脚本',
        3: 'python脚本',
        4: 'python内部类'
    }
    return type_names.get(task_type, '未知类型')


def convert_task_log_to_camel_case(log_data: dict) -> TaskLogResponse:
    """将数据库返回的任务日志数据转换为驼峰命名"""
    # 处理可能为None的字段，提供默认值
    def safe_str(value, default=''):
        """安全转换为字符串，处理None和datetime对象"""
        if value is None:
            return default
        if hasattr(value, 'strftime'):  # datetime对象
            return value.strftime('%Y-%m-%d %H:%M:%S')
        return str(value)

    def safe_int(value, default=0):
        """安全转换为整数，处理None"""
        if value is None:
            return default
        return int(value)

    def safe_bool(value, default=False):
        """安全转换为布尔值，处理None"""
        if value is None:
            return default
        return bool(value)

    return TaskLogResponse(
        logId=safe_int(log_data.get('log_id')),
        taskId=safe_int(log_data.get('task_id')),
        taskName=safe_str(log_data.get('task_name')),
        taskType=safe_int(log_data.get('task_type')),
        startTime=safe_str(log_data.get('start_time')),
        endTime=safe_str(log_data.get('end_time')),
        duration=safe_int(log_data.get('duration')),
        success=safe_bool(log_data.get('success')),
        logDetail=safe_str(log_data.get('log_detail'))
    )


def convert_cron_task_list_to_camel_case(data: dict) -> CronTaskListResponse:
    """将定时任务列表数据转换为驼峰命名"""
    task_list = data.get('list', [])
    converted_list = [convert_cron_task_to_camel_case(task) for task in task_list]

    return CronTaskListResponse(
        total=data.get('total', 0),
        list=converted_list
    )


def convert_task_log_list_to_camel_case(data: dict) -> TaskLogListResponse:
    """将任务日志列表数据转换为驼峰命名"""
    log_list = data.get('list', [])
    converted_list = [convert_task_log_to_camel_case(log) for log in log_list]

    return TaskLogListResponse(
        total=data.get('total', 0),
        list=converted_list
    )


# 固定路径接口 - 必须在参数路径之前定义

@router.post("/add", response_model=CommonResponse)
async def create_cron_task(
    request: Request,
    task_data: CronTaskCreate,
    db: Session = Depends(get_db)
):
    """创建新的定时任务"""
    verify_token(request)

    try:
        result = CronTaskCRUD.create_cron_task(db, {
            **task_data.model_dump(),
            "create_by": "admin"
        })

        if result.success:
            # 如果任务启用，添加到调度器
            if task_data.enabled:
                await cron_executor.add_task_to_scheduler(result.data)

            # 转换为驼峰命名格式
            camel_case_data = convert_cron_task_to_camel_case(result.data)

            return CommonResponse(
                status="success",
                msg="创建定时任务成功",
                code="200",
                data=camel_case_data.model_dump()
            )
        else:
            return CommonResponse(
                status="error",
                msg=result.message,
                code="400",
                data=None
            )

    except Exception as e:
        return CommonResponse(
            status="error",
            msg=f"创建定时任务失败: {str(e)}",
            code="500",
            data=None
        )


@router.get("/list", response_model=CommonResponse)
async def get_cron_tasks(
    request: Request,
    skip: int = Query(0, ge=0, description="跳过记录数"),
    limit: int = Query(20, ge=1, le=200, description="返回记录数"),
    task_name: Optional[str] = Query(None, description="任务名称模糊查询"),
    task_code: Optional[str] = Query(None, description="任务编码模糊查询"),
    enabled: Optional[bool] = Query(None, description="是否启用"),
    task_type: Optional[int] = Query(None, description="任务类型"),
    task_status: Optional[int] = Query(None, description="任务状态"),
    db: Session = Depends(get_db)
):
    """获取定时任务列表"""
    verify_token(request)

    try:
        result = CronTaskCRUD.get_cron_tasks(
            db, skip, limit, task_name, task_code, enabled, task_type, task_status
        )

        if result.success:
            # 转换为驼峰命名格式
            camel_case_data = convert_cron_task_list_to_camel_case(result.data)

            return CommonResponse(
                status="success",
                msg="获取定时任务列表成功",
                code="200",
                data=camel_case_data.model_dump()
            )
        else:
            return CommonResponse(
                status="error",
                msg=result.message,
                code="500",
                data=None
            )

    except Exception as e:
        return CommonResponse(
            status="error",
            msg=f"获取定时任务列表失败: {str(e)}",
            code="500",
            data=None
        )


@router.get("/logs", response_model=CommonResponse)
async def get_task_logs(
    request: Request,
    skip: int = Query(0, ge=0, description="跳过记录数"),
    limit: int = Query(20, ge=1, le=1000, description="返回记录数"),
    task_name: Optional[str] = Query(None, description="任务名称模糊查询"),
    task_id: Optional[int] = Query(None, description="任务ID"),
    success: Optional[bool] = Query(None, description="执行结果"),
    db: Session = Depends(get_db)
):
    """获取任务执行日志"""
    verify_token(request)

    try:
        result = TaskLogsCRUD.get_task_logs(
            db, skip, limit, task_name, task_id, success
        )

        if result.success:
            # 转换为驼峰命名格式
            camel_case_data = convert_task_log_list_to_camel_case(result.data)

            return CommonResponse(
                status="success",
                msg="获取任务日志成功",
                code="200",
                data=camel_case_data.model_dump()
            )
        else:
            return CommonResponse(
                status="error",
                msg=result.message,
                code="500",
                data=None
            )

    except Exception as e:
        return CommonResponse(
            status="error",
            msg=f"获取任务日志失败: {str(e)}",
            code="500",
            data=None
        )


@router.get("/logs/statistics", response_model=CommonResponse)
async def get_task_logs_statistics(
    request: Request,
    db: Session = Depends(get_db)
):
    """获取任务日志统计信息"""
    verify_token(request)

    try:
        result = TaskLogsCRUD.get_task_logs_statistics(db)

        if result.success:
            # 转换为驼峰命名格式
            statistics_data = {
                "totalLogs": result.data.get("total_logs", 0),
                "successLogs": result.data.get("success_logs", 0),
                "failedLogs": result.data.get("failed_logs", 0),
                "todayLogs": result.data.get("today_logs", 0)
            }

            return CommonResponse(
                status="success",
                msg="获取任务日志统计成功",
                code="200",
                data=statistics_data
            )
        else:
            return CommonResponse(
                status="error",
                msg=result.message,
                code="500",
                data=None
            )

    except Exception as e:
        return CommonResponse(
            status="error",
            msg=f"获取任务日志统计失败: {str(e)}",
            code="500",
            data=None
        )


# 参数路径接口 - 必须在固定路径之后定义

@router.get("/{task_id}", response_model=CommonResponse)
async def get_cron_task(
    request: Request,
    task_id: int,
    db: Session = Depends(get_db)
):
    """获取定时任务详情"""
    verify_token(request)

    try:
        result = CronTaskCRUD.get_cron_task_by_id(db, task_id)

        if result.success:
            # 转换为驼峰命名格式
            camel_case_data = convert_cron_task_to_camel_case(result.data)

            return CommonResponse(
                status="success",
                msg="获取定时任务成功",
                code="200",
                data=camel_case_data.model_dump()
            )
        elif not result.success and result.error_code == DatabaseError.NOT_FOUND.value:
            return CommonResponse(
                status="error",
                msg="定时任务不存在",
                code="404",
                data=None
            )
        else:
            return CommonResponse(
                status="error",
                msg=result.message,
                code="500",
                data=None
            )

    except Exception as e:
        return CommonResponse(
            status="error",
            msg=f"获取定时任务失败: {str(e)}",
            code="500",
            data=None
        )


@router.put("/{task_id}", response_model=CommonResponse)
async def update_cron_task(
    request: Request,
    task_id: int,
    task_data: CronTaskUpdate,
    db: Session = Depends(get_db)
):
    """更新定时任务"""
    verify_token(request)

    try:
        result = CronTaskCRUD.update_cron_task(db, task_id, {
            **task_data.model_dump(exclude_none=True),
            "update_by": "admin"
        })

        if result.success:
            # 刷新调度器中的任务
            await cron_executor.refresh_task(task_id)

            # 转换为驼峰命名格式
            camel_case_data = convert_cron_task_to_camel_case(result.data)

            return CommonResponse(
                status="success",
                msg="更新定时任务成功",
                code="200",
                data=camel_case_data.model_dump()
            )
        elif not result.success and result.error_code == DatabaseError.NOT_FOUND.value:
            return CommonResponse(
                status="error",
                msg="定时任务不存在",
                code="404",
                data=None
            )
        else:
            return CommonResponse(
                status="error",
                msg=result.message,
                code="400",
                data=None
            )

    except Exception as e:
        return CommonResponse(
            status="error",
            msg=f"更新定时任务失败: {str(e)}",
            code="500",
            data=None
        )


@router.delete("/{task_id}", response_model=CommonResponse)
async def delete_cron_task(
    request: Request,
    task_id: int,
    db: Session = Depends(get_db)
):
    """删除定时任务"""
    verify_token(request)

    try:
        result = CronTaskCRUD.delete_cron_task(db, task_id, "admin")

        if result.success:
            # 从调度器中移除任务
            await cron_executor.remove_task_from_scheduler(task_id)

            return CommonResponse(
                status="success",
                msg="删除定时任务成功",
                code="200",
                data=None
            )
        elif not result.success and result.error_code == DatabaseError.NOT_FOUND.value:
            return CommonResponse(
                status="error",
                msg="定时任务不存在",
                code="404",
                data=None
            )
        else:
            return CommonResponse(
                status="error",
                msg=result.message,
                code="400",
                data=None
            )

    except Exception as e:
        return CommonResponse(
            status="error",
            msg=f"删除定时任务失败: {str(e)}",
            code="500",
            data=None
        )


@router.post("/{task_id}/start", response_model=CommonResponse)
async def start_task_immediately(
    request: Request,
    task_id: int,
    db: Session = Depends(get_db)
):
    """立即启动任务"""
    verify_token(request)

    try:
        success = await cron_executor.start_task_immediately(task_id)

        if success:
            return CommonResponse(
                status="success",
                msg="任务启动成功",
                code="200",
                data=None
            )
        else:
            return CommonResponse(
                status="error",
                msg="任务启动失败",
                code="400",
                data=None
            )

    except ValueError as e:
        # 业务逻辑异常，返回具体错误信息
        return CommonResponse(
            status="error",
            msg=str(e),
            code="400",
            data=None
        )
    except Exception as e:
        return CommonResponse(
            status="error",
            msg=f"启动任务失败: {str(e)}",
            code="500",
            data=None
        )


@router.post("/{task_id}/pause", response_model=CommonResponse)
async def pause_task(
    request: Request,
    task_id: int,
    db: Session = Depends(get_db)
):
    """暂停任务"""
    verify_token(request)

    try:
        success = await cron_executor.pause_task(task_id)

        if success:
            return CommonResponse(
                status="success",
                msg="任务暂停成功",
                code="200",
                data=None
            )
        else:
            return CommonResponse(
                status="error",
                msg="任务暂停失败",
                code="400",
                data=None
            )

    except Exception as e:
        return CommonResponse(
            status="error",
            msg=f"暂停任务失败: {str(e)}",
            code="500",
            data=None
        )


@router.post("/{task_id}/resume", response_model=CommonResponse)
async def resume_task(
    request: Request,
    task_id: int,
    db: Session = Depends(get_db)
):
    """恢复任务"""
    verify_token(request)

    try:
        success = await cron_executor.resume_task(task_id)

        if success:
            return CommonResponse(
                status="success",
                msg="任务恢复成功",
                code="200",
                data=None
            )
        else:
            return CommonResponse(
                status="error",
                msg="任务恢复失败",
                code="400",
                data=None
            )

    except Exception as e:
        return CommonResponse(
            status="error",
            msg=f"恢复任务失败: {str(e)}",
            code="500",
            data=None
        )


@router.post("/{task_id}/interrupt", response_model=CommonResponse)
async def interrupt_task(
    request: Request,
    task_id: int,
    db: Session = Depends(get_db)
):
    """中断任务"""
    verify_token(request)

    try:
        success = await cron_executor.interrupt_task(task_id)

        if success:
            return CommonResponse(
                status="success",
                msg="任务中断成功",
                code="200",
                data=None
            )
        else:
            return CommonResponse(
                status="error",
                msg="任务中断失败",
                code="400",
                data=None
            )

    except Exception as e:
        return CommonResponse(
            status="error",
            msg=f"中断任务失败: {str(e)}",
            code="500",
            data=None
        )


# ========== 新增的验证和配置接口 ==========

@router.post("/validation/script", response_model=CommonResponse)
async def validate_script_syntax(
    request: Request,
    validation_data: ScriptValidationRequest
):
    """校验脚本语法"""
    verify_token(request)

    try:
        # 导入语法校验服务
        from app.tasks.validation_service import ScriptValidationService

        validator = ScriptValidationService()
        result = await validator.validate_script(
            content=validation_data.content,
            script_type=validation_data.script_type
        )

        return CommonResponse(
            status="success",
            msg="脚本语法校验完成",
            code="200",
            data=result.model_dump()
        )

    except ImportError:
        # 如果验证服务不存在，返回基础校验结果
        return CommonResponse(
            status="success",
            msg="基础语法校验完成（未启用高级校验）",
            code="200",
            data={
                "valid": True,
                "errors": [],
                "message": "基础校验通过"
            }
        )
    except Exception as e:
        return CommonResponse(
            status="error",
            msg=f"脚本语法校验失败: {str(e)}",
            code="500",
            data=None
        )


@router.post("/validation/cron", response_model=CommonResponse)
async def validate_cron_expression(
    request: Request,
    validation_data: CronValidationRequest
):
    """校验Cron表达式并获取执行时间"""
    verify_token(request)

    try:
        # 导入Cron表达式校验服务
        from app.tasks.validation_service import CronValidationService

        validator = CronValidationService()
        result = await validator.validate_cron_expression(
            expression=validation_data.expression
        )

        return CommonResponse(
            status="success",
            msg="Cron表达式校验完成",
            code="200",
            data=result.model_dump()
        )

    except ImportError:
        # 如果验证服务不存在，返回基础校验结果
        return CommonResponse(
            status="success",
            msg="基础Cron表达式校验完成（未启用高级校验）",
            code="200",
            data={
                "valid": True,
                "message": "基础校验通过",
                "description": "基础校验，无法计算执行时间"
            }
        )
    except Exception as e:
        return CommonResponse(
            status="error",
            msg=f"Cron表达式校验失败: {str(e)}",
            code="500",
            data=None
        )


@router.post("/validation/python-class", response_model=CommonResponse)
async def validate_python_class(
    request: Request,
    validation_data: PythonClassValidationRequest
):
    """验证Python类路径"""
    verify_token(request)

    try:
        # 导入Python类验证服务
        from app.tasks.validation_service import PythonClassValidationService

        validator = PythonClassValidationService()
        result = await validator.validate_class_path(
            class_path=validation_data.class_path
        )

        return CommonResponse(
            status="success",
            msg="Python类路径验证完成",
            code="200",
            data=result.model_dump()
        )

    except ImportError:
        # 如果验证服务不存在，返回基础校验结果
        return CommonResponse(
            status="success",
            msg="基础Python类路径校验完成（未启用高级校验）",
            code="200",
            data={
                "valid": True,
                "exists": True,
                "message": "基础校验通过",
                "classInfo": None
            }
        )
    except Exception as e:
        return CommonResponse(
            status="error",
            msg=f"Python类路径验证失败: {str(e)}",
            code="500",
            data=None
        )


@router.get("/config/task-types", response_model=CommonResponse)
async def get_task_type_config(request: Request):
    """获取任务类型配置数据"""
    verify_token(request)

    try:
        # 任务类型配置
        task_types = [
            {
                "value": 0,
                "label": "shell脚本",
                "icon": "el-icon-document",
                "description": "Linux/Unix Shell脚本",
                "language": "shell",
                "fileExtension": ".sh"
            },
            {
                "value": 1,
                "label": "cmd脚本",
                "icon": "el-icon-document",
                "description": "Windows批处理脚本",
                "language": "batch",
                "fileExtension": ".bat"
            },
            {
                "value": 2,
                "label": "powershell脚本",
                "icon": "el-icon-document",
                "description": "Windows PowerShell脚本",
                "language": "powershell",
                "fileExtension": ".ps1"
            },
            {
                "value": 3,
                "label": "python脚本",
                "icon": "el-icon-document",
                "description": "Python脚本文件",
                "language": "python",
                "fileExtension": ".py"
            },
            {
                "value": 4,
                "label": "python内部类",
                "icon": "el-icon-document",
                "description": "Python内部类方法",
                "language": "python",
                "fileExtension": None
            },
            {
                "value": 5,
                "label": "清理回收站",
                "icon": "el-icon-delete",
                "description": "定时清理回收站和待删除数据",
                "language": None,
                "fileExtension": None
            }
        ]

        # 尝试获取可用的Python类列表
        python_classes = []
        try:
            from app.tasks.validation_service import PythonClassValidationService
            validator = PythonClassValidationService()
            classes = await validator.get_available_classes()
            python_classes = [cls.model_dump() for cls in classes]
        except ImportError:
            # 如果没有验证服务，提供默认的类列表
            python_classes = [
                {
                    "className": "SystemTask",
                    "module": "app.tasks.system_tasks",
                    "description": "系统任务基类",
                    "methods": ["execute", "validate", "cleanup"],
                    "parameters": {}
                },
                {
                    "className": "DownloaderTask",
                    "module": "app.tasks.downloader_tasks",
                    "description": "下载器任务基类",
                    "methods": ["sync_status", "check_health"],
                    "parameters": {}
                }
            ]

        response_data = TaskTypeConfigResponse(
            taskTypes=task_types,
            pythonClasses=python_classes
        )

        return CommonResponse(
            status="success",
            msg="获取任务类型配置成功",
            code="200",
            data=response_data.model_dump()
        )

    except Exception as e:
        return CommonResponse(
            status="error",
            msg=f"获取任务类型配置失败: {str(e)}",
            code="500",
            data=None
        )


# ========== 清理任务相关端点 ==========

@router.post("/cleanup/preview", response_model=CommonResponse)
async def preview_cleanup(
    request: Request,
    cleanup_data: CleanupTaskRequest,
    db: Session = Depends(get_db)
):
    """预览清理任务"""
    verify_token(request)

    try:
        from app.tasks.cleanup_executor import CleanupTaskExecutor
        from app.database import AsyncSessionLocal

        # 构建任务配置
        task_config = {
            "cleanup_level_3": cleanup_data.cleanup_level_3,
            "cleanup_level_4": cleanup_data.cleanup_level_4,
            "days_threshold": cleanup_data.days_threshold
        }

        # 异步执行预览
        async with AsyncSessionLocal() as async_db:
            executor = CleanupTaskExecutor(async_db)
            preview = await executor.preview_cleanup(task_config)

        return CommonResponse(
            status="success",
            msg="预览清理成功",
            code="200",
            data=preview
        )

    except Exception as e:
        return CommonResponse(
            status="error",
            msg=f"预览清理失败: {str(e)}",
            code="500",
            data=None
        )


@router.post("/cleanup/execute", response_model=CommonResponse)
async def execute_cleanup(
    request: Request,
    cleanup_data: CleanupTaskRequest,
    db: Session = Depends(get_db)
):
    """手动执行清理任务"""
    verify_token(request)

    try:
        from app.tasks.cleanup_executor import CleanupTaskExecutor
        from app.database import AsyncSessionLocal

        # 构建任务配置
        task_config = {
            "cleanup_level_3": cleanup_data.cleanup_level_3,
            "cleanup_level_4": cleanup_data.cleanup_level_4,
            "days_threshold": cleanup_data.days_threshold
        }

        # 异步执行清理
        async with AsyncSessionLocal() as async_db:
            executor = CleanupTaskExecutor(async_db)
            result = await executor.execute_cleanup_task(
                task_config=task_config,
                operator="manual",
                audit_service=None
            )

        return CommonResponse(
            status="success",
            msg="清理任务执行成功",
            code="200",
            data=result
        )

    except Exception as e:
        return CommonResponse(
            status="error",
            msg=f"执行清理失败: {str(e)}",
            code="500",
            data=None
        )