from logging import exception

import ping3
import time
import urllib3
from fastapi import APIRouter, Depends, Request, Path, Header, Query
from app.api.responseVO import CommonResponse
from sqlalchemy import text
from sqlalchemy.orm import Session
from app.database import get_db
from app.auth import utils
import uuid
import logging
from app.downloader import models
from app.downloader.models import BtDownloaders
from app.downloader.request import ListDownloader, RequestDownloader, UpdateDownloader
from typing import Annotated, List, Optional, Any
from app.downloader.responseVO import DownloaderListVO, DownloaderVO, DownloaderStatusVO, DownloaderSimpleVO
from app.utils.encryption import encrypt_password, decrypt_password
from app.models.setting_templates import DownloaderTypeEnum
from qbittorrentapi import Client as qbClient
from transmission_rpc import Client as trClient, TransmissionAuthError
from requests.exceptions import SSLError, ConnectionError

# 创建日志记录器
logger = logging.getLogger(__name__)  # Fixed for proper response handling
router = APIRouter()
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)



@router.get("/detail/{downloader_id}", summary="获取下载器明细信息", response_model=CommonResponse[List[DownloaderVO]])
def get(downloader_id: Annotated[str, Path(description="下载器id")], req: Request = None,
        db: Session = Depends(get_db)):
    try:
        token = req.headers.get("x-access-token")
        utils.verify_access_token(token)
    except Exception as e:
        response = CommonResponse(
            status="error",
            msg="token验证失败，失败原因：" + str(e),
            code="401",
            data=None
        )
        return response
    try:
        downloaders = db.execute(
            text(
                "SELECT downloader_id,nickname,host,username,is_search,status,enabled,downloader_type,port,is_ssl,path_mapping_rules,torrent_save_path FROM bt_downloaders WHERE dr = :dr AND downloader_id = :downloader_id"),
            {"dr": 0, "downloader_id": downloader_id}
        )
        downloader_list = downloaders.fetchall()
        result_list = []
        if len(downloader_list) < 1:
            response = CommonResponse(
                status="success",
                msg="该下载器已被删除或不存在",
                code="200",
            data=None
            )
        else:
            for row in downloader_list:
                # DownloaderVO 需要 password 参数，传入 None 表示不返回密码
                # 修复: 数据库返回的字段与 DownloaderVO 参数顺序对齐
                args = list(row)
                args.insert(4, None)  # 插入 password 参数占位符
                result_list.append(DownloaderVO(*args))
            response = CommonResponse(
                status="success",
                msg="获取成功",
                code="200",
                data=result_list
            )
    except Exception as e:
        response = CommonResponse(
            status="error",
            msg=str(e),
            code="400",
            data=None
        )
    return response


@router.post('/add', summary="增加下载器", response_model=CommonResponse)
async def add(
        downloader_request: RequestDownloader,
        req: Request = None,
        db: Session = Depends(get_db)
):
    try:
        token = req.headers.get("x-access-token")
        utils.verify_access_token(token)
    except Exception as e:
        response = CommonResponse(
            status="error",
            msg="token验证失败，失败原因：" + str(e),
            code="401",
            data=None
        )
        return response
    # Pydantic 验证器已将字符串 "0"/"1" 转换为布尔值
    downloader = models.BtDownloaders(
        downloader_id=str(uuid.uuid4()),
        nickname=downloader_request.nickname,
        host=downloader_request.host,
        username=downloader_request.username,
        password=downloader_request.password,
        status=True,
        is_search=downloader_request.is_search,
        enabled=downloader_request.enabled,
        downloader_type=downloader_request.downloader_type,
        port=downloader_request.port,
        is_ssl=downloader_request.is_ssl,
        dr=0,
        path_mapping_rules=downloader_request.path_mapping_rules,
        torrent_save_path=downloader_request.torrent_save_path
    )

    # 处理路径映射配置
    if downloader_request.path_mapping:
        downloader.path_mapping = downloader_request.path_mapping.model_dump_json()
    try:
        db.add(downloader)
        db.commit()

        # 立即同步到缓存（等待完成，确保立即可见）
        try:
            from app.factory import app as downloader_app
            from app.downloader.initialization import _check_and_add_new_downloader

            downloader_data = {
                "downloader_id": downloader.downloader_id,
                "nickname": downloader.nickname,
                "host": downloader.host,
                "username": downloader.username,
                "password": downloader.password,
                "port": downloader.port,
                "downloader_type": downloader.downloader_type,
                "is_ssl": downloader.is_ssl,
                "torrent_save_path": downloader.torrent_save_path
            }

            await _check_and_add_new_downloader(
                downloader_app,
                downloader_data,
                immediate=True
            )
        except Exception as cache_error:
            logger.warning(f"缓存同步失败（已写入数据库）: {cache_error}")

        response = CommonResponse(
            status="success",
            msg="添加成功",
            code="200",
            data=None
        )
        return response
    except exception as e:
        db.rollback()
        logging.error(f"Error updating database: {str(e)}")
        response = CommonResponse(
            status="error",
            msg="用户名或密码错误",
            code="400",
            data=None
        )
        return response


@router.post("/update/{downloader_id}", summary="更新下载器明细", response_model=CommonResponse)
async def update(
        downloader_request: UpdateDownloader,
        downloader_id: Annotated[str, Path(description="下载器id")],
        req: Request = None,
        db: Session = Depends(get_db)
):
    try:
        token = req.headers.get("x-access-token")
        utils.verify_access_token(token)
    except Exception as e:
        response = CommonResponse(
            status="error",
            msg="token验证失败，失败原因：" + str(e),
            code="401",
            data=None
        )
        return response

    try:
        # 读取原始请求数据以检测 path_mapping 是否被明确传递
        raw_data = await req.json()
        path_mapping_in_request = 'path_mapping' in raw_data

        # ========== 原密码验证逻辑 ==========
        # 获取当前下载器的信息
        current_downloader = db.execute(
            text("SELECT username, password FROM bt_downloaders WHERE downloader_id = :downloader_id AND dr = 0"),
            {"downloader_id": downloader_id}
        ).fetchone()

        if not current_downloader:
            response = CommonResponse(
                status="error",
                msg="下载器不存在",
                code="404",
                data=None
            )
            return response

        current_username = current_downloader[0]
        current_password_encrypted = current_downloader[1]

        # 判断是否需要验证原密码
        # 条件1：用户名发生变化
        # 条件2：提供了新密码
        username_changed = downloader_request.username is not None and downloader_request.username != current_username
        password_changing = downloader_request.password is not None and downloader_request.password.strip() != ""

        need_verify_old_password = username_changed or password_changing

        if need_verify_old_password:
            # 必须提供原密码
            if not downloader_request.old_password or downloader_request.old_password.strip() == "":
                response = CommonResponse(
                    status="error",
                    msg="修改用户名或密码时必须提供原密码",
                    code="400",
                    data=None
                )
                return response

            # 验证原密码是否正确
            if current_password_encrypted:
                try:
                    decrypted_password = decrypt_password(current_password_encrypted)
                    if decrypted_password != downloader_request.old_password:
                        response = CommonResponse(
                            status="error",
                            msg="原密码错误",
                            code="400",
                            data=None
                        )
                        return response
                except Exception as e:
                    logger.error(f"解密密码失败: {str(e)}")
                    response = CommonResponse(
                        status="error",
                        msg="验证原密码失败",
                        code="500",
                        data=None
                    )
                    return response
            else:
                # 数据库中没有密码记录（异常情况）
                response = CommonResponse(
                    status="error",
                    msg="无法验证原密码",
                    code="500",
                    data=None
                )
                return response
        # ========== 原密码验证逻辑结束 ==========

        # 构建 SQL UPDATE 语句
        update_fields = []
        params = {
            "nickname": downloader_request.nickname,
            "host": downloader_request.host,
            "username": downloader_request.username,
            "password": encrypt_password(downloader_request.password) if (downloader_request.password and downloader_request.password.strip()) else None,
            "is_search": downloader_request.is_search,
            "enabled": downloader_request.enabled,
            "downloader_type": downloader_request.downloader_type,
            "port": downloader_request.port,
            "is_ssl": downloader_request.is_ssl,
            "downloader_id": downloader_id
        }

        # 添加标准字段
        update_fields.append("nickname= case when :nickname is not null then :nickname else nickname end")
        update_fields.append("host= case when :host is not null then :host else host end")
        update_fields.append("username= case when :username is not null then :username else username end")
        # 只有在提供了新密码时才更新密码字段
        if password_changing:
            update_fields.append("password= :password")
        update_fields.append("is_search= case when :is_search is not null then :is_search else is_search end")
        update_fields.append("enabled= case when :enabled is not null then :enabled else enabled end")
        update_fields.append("downloader_type= case when :downloader_type is not null then :downloader_type else downloader_type end")
        update_fields.append("port= case when :port is not null then :port else port end")
        update_fields.append("is_ssl= case when :is_ssl is not null then :is_ssl else is_ssl end")

        # 处理路径映射配置 - 智能检测逻辑
        if path_mapping_in_request:
            if downloader_request.path_mapping is None:
                # 明确传递 null → 清除路径映射
                update_fields.append("path_mapping = NULL")
                logger.info(f"下载器 {downloader_id} 路径映射已清除")
            else:
                # 传递有效配置 → 更新路径映射（保存前进行路径标准化）
                from app.core.path_mapping import PathMappingService

                # 使用 PathMappingService 进行路径标准化
                # 创建临时实例并加载配置，会自动调用 _validate_config() 标准化路径
                try:
                    config_json = downloader_request.path_mapping.model_dump_json()
                    temp_service = PathMappingService(config_json)

                    # 获取标准化后的配置JSON
                    normalized_config = {
                        "mappings": temp_service.mappings,
                        "default_mapping": temp_service.default_mapping
                    }
                    import json
                    params["path_mapping"] = json.dumps(normalized_config, ensure_ascii=False)
                    update_fields.append("path_mapping = :path_mapping")
                    logger.info(f"下载器 {downloader_id} 路径映射已更新（路径已标准化）")
                except Exception as e:
                    logger.error(f"路径标准化失败: {str(e)}")
                    # 标准化失败时，使用原始配置保存
                    params["path_mapping"] = downloader_request.path_mapping.model_dump_json()
                    update_fields.append("path_mapping = :path_mapping")
                    logger.info(f"下载器 {downloader_id} 路径映射已更新（未标准化）")
        # 如果 path_mapping 不在请求中,则不更新该字段(保持现有值)

        # 处理路径映射规则配置
        if hasattr(downloader_request, 'path_mapping_rules') and downloader_request.path_mapping_rules is not None:
            params["path_mapping_rules"] = downloader_request.path_mapping_rules
            update_fields.append("path_mapping_rules = :path_mapping_rules")
            logger.info(f"下载器 {downloader_id} 路径映射规则已更新")

        # 处理种子保存目录配置
        if hasattr(downloader_request, 'torrent_save_path') and downloader_request.torrent_save_path is not None:
            params["torrent_save_path"] = downloader_request.torrent_save_path
            update_fields.append("torrent_save_path = :torrent_save_path")
            logger.info(f"下载器 {downloader_id} 种子保存目录已更新")

        # 执行更新
        sql = f"UPDATE bt_downloaders SET {', '.join(update_fields)} WHERE downloader_id = :downloader_id"
        db.execute(text(sql), params)
        db.commit()

        response = CommonResponse(
            status="success",
            msg="修改成功",
            code="200",
            data=None
        )
    except Exception as e:
        db.rollback()
        logging.error(f"Error updating database: {str(e)}")
        response = CommonResponse(
            status="error",
            msg=str(e),
            code="200",
            data=None
        )
    return response


@router.delete("/delete/{downloader_id}", summary="下载器删除接口", response_model=CommonResponse)
def delete(downloader_id: Annotated[str, Path(description="下载器id")], req: Request = None,
           db: Session = Depends(get_db)):
    try:
        token = req.headers.get("x-access-token")
        utils.verify_access_token(token)
    except Exception as e:
        response = CommonResponse(
            status="error",
            msg="token验证失败，失败原因：" + str(e),
            code="401",
            data=None
        )
        return response
    try:
        db.execute(text("update bt_downloaders set dr=:dr where downloader_id=:downloader_id"), {"dr": 1, "downloader_id": downloader_id})
        db.commit()
        response = CommonResponse(
            status="success",
            msg="删除成功",
            code="200",
            data=None
        )
    except Exception as e:
        db.rollback()
        logging.error(f"Error deleting database: {str(e)}")
        response = CommonResponse(
            status="error",
            msg=str(e),
            code="200",
            data=None
        )
    return response


def _get_downloader_id_from_cache(obj: Any) -> str | None:
    """
    从缓存对象中获取下载器ID（兼容多种对象类型）

    支持的对象类型：
    - DownloaderCheckVO: 有 downloader_id 属性
    - DownloaderVO: 有 id 属性
    - 其他兼容对象

    Args:
        obj: 缓存中的下载器对象

    Returns:
        str | None: 下载器ID（字符串形式），如果获取失败返回 None

    安全特性：
    - 检查obj是否为None
    - 验证属性值不为None后再转换
    - 空字符串会被正常返回（不是None）
    """
    # 防御性检查：对象为None
    if obj is None:
        return None

    # 优先尝试 downloader_id 属性（DownloaderCheckVO）
    if hasattr(obj, 'downloader_id'):
        did = getattr(obj, 'downloader_id')
        # 明确检查None，空字符串是有效值
        if did is not None:
            return str(did)

    # 降级到 id 属性（DownloaderVO）
    if hasattr(obj, 'id'):
        did = getattr(obj, 'id')
        # 明确检查None，空字符串是有效值
        if did is not None:
            return str(did)

    # 都不存在或都为None，返回 None
    return None


def _is_cache_fresh(cached_downloader: Any, threshold_seconds: int = 60) -> bool:
    """
    检查缓存数据是否新鲜（增强版时间验证）

    Args:
        cached_downloader: 缓存中的下载器对象
        threshold_seconds: 缓存新鲜度阈值（秒），默认60秒（匹配冷数据更新间隔）

    Returns:
        bool: 缓存是否新鲜

    安全特性：
    - 验证last_update属性存在且有效
    - 检查时间戳合理性（不能是未来时间）
    - 处理时间精度问题（负数、异常值）
    - 阈值设置为60秒，与冷数据更新频率保持一致
    """
    try:
        # 检查是否有last_update属性
        if not hasattr(cached_downloader, 'last_update'):
            logger.debug("缓存对象缺少last_update属性")
            return False

        last_update = getattr(cached_downloader, 'last_update')

        # 验证last_update是有效的时间戳
        if last_update is None:
            logger.warning("缓存last_update为None")
            return False

        if not isinstance(last_update, (int, float)):
            logger.warning(f"缓存last_update类型错误: {type(last_update)}")
            return False

        # 检查时间戳合理性（不能为0或负数）
        if last_update <= 0:
            logger.warning(f"缓存last_update无效: {last_update}")
            return False

        # 获取当前时间
        import time
        current_time = time.time()

        # 检查是否是未来时间（时钟被调整）
        if last_update > current_time:
            logger.warning(f"缓存last_update是未来时间: {last_update} > {current_time}")
            return False

        # 计算时间差
        time_since_update = current_time - last_update

        # 检查是否在阈值内
        is_fresh = time_since_update <= threshold_seconds

        if not is_fresh:
            nickname = getattr(cached_downloader, 'nickname', 'Unknown')
            logger.info(f"下载器 {nickname} 缓存过期: {time_since_update:.1f}秒前 (阈值: {threshold_seconds}秒)")

        return is_fresh

    except Exception as e:
        logger.error(f"检查缓存新鲜度失败: {e}")
        return False  # 出错时认为不新鲜，降级到实时查询


@router.get("/getStatusAll", summary="批量获取所有在线下载器的状态", response_model=CommonResponse[List[DownloaderStatusVO]])
async def get_all_status(
        token: str = Header(..., alias="x-access-token")):
    """批量获取所有在线下载器的状态

    从 app.state.store 缓存中一次性获取所有在线下载器的状态信息。
    相比单个查询接口，大幅减少请求次数和后端负载。

    返回数据：
    - connectStatus: "connected" (在线) 或 "disconnected" (离线)
    - 仅返回缓存中存在的下载器（在线）
    - 未在返回列表中的下载器ID视为离线

    性能优势：
    - 零数据库查询
    - 单次请求获取所有状态
    - 响应时间 < 50ms
    """
    try:
        utils.verify_access_token(token)
    except Exception as e:
        return CommonResponse(
            status="error",
            msg="token验证失败，失败原因：" + str(e),
            code="401",
            data=None
        )

    try:
        from app.factory import app as downloader_app

        # ✅ P0-2修复: 添加完整的防御性检查，确保缓存已初始化
        if not hasattr(downloader_app, 'state') or \
           not hasattr(downloader_app.state, 'store') or \
           downloader_app.state.store is None:
            return CommonResponse(
                status="success",
                msg="缓存服务未初始化",
                code="200",
                data=[]
            )

        # ✅ 使用异步方法获取缓存（避免 RuntimeWarning）
        cached_downloaders = await downloader_app.state.store.get_snapshot()

        if not cached_downloaders:
            return CommonResponse(
                status="success",
                msg="暂无在线下载器",
                code="200",
                data=[]
            )

        # 构建批量响应数据
        result_list = []
        for cached_downloader in cached_downloaders:
            # 跳过离线下载器（fail_time > 0）
            if hasattr(cached_downloader, 'fail_time') and cached_downloader.fail_time > 0:
                continue

            # 使用 _build_status_from_cache 构建状态响应
            status_vo = _build_status_from_cache(cached_downloader)

            # 简化 connectStatus：只返回 connected 或 disconnected
            if status_vo.connectStatus != "connected":
                status_vo.connectStatus = "disconnected"

            result_list.append(status_vo)

        return CommonResponse(
            status="success",
            msg="获取成功",
            code="200",
            data=result_list
        )

    except Exception as e:
        logger.error(f"批量获取下载器状态失败: {str(e)}")
        return CommonResponse(
            status="error",
            msg=f"批量获取下载器状态失败: {str(e)}",
            code="500",
            data=None
        )


@router.get("/getStatus/{downloader_id}", summary="[已废弃] 获取单个下载器的状态", response_model=CommonResponse[DownloaderStatusVO], deprecated=True)
async def get_status(downloader_id: Annotated[str, Path(description="下载器id")],
               token: str = Header(..., alias="x-access-token"),
               db: Session = Depends(get_db)):
    """获取单个下载器的实时状态 [已废弃]

    ⚠️ 该接口已废弃，请使用 /getStatusAll 批量接口替代。

    返回下载器的连接状态、速度信息、任务统计等实时数据。
    优先从缓存获取，缓存未命中时降级到实时连接查询。
    """
    try:
        utils.verify_access_token(token)
    except Exception as e:
        return CommonResponse(
            status="error",
            msg="token验证失败，失败原因：" + str(e),
            code="401",
            data=None
        )

    # 优先从缓存获取状态
    try:
        from app.factory import app as downloader_app

        if hasattr(downloader_app.state, 'store'):
            # ✅ 使用异步方法获取缓存（避免 RuntimeWarning）
            cached_downloaders = await downloader_app.state.store.get_snapshot()

            if cached_downloaders:
                # 在缓存中查找对应的下载器（兼容多种对象类型）
                cached_downloader = None
                for d in cached_downloaders:
                    # 使用统一的 ID 获取函数
                    did = _get_downloader_id_from_cache(d)
                    # 修复：必须明确检查 is not None，避免空字符串误判
                    if did is not None and did == str(downloader_id):
                        cached_downloader = d
                        break

                # 找到下载器且状态有效（fail_time=0），检查缓存新鲜度
                if cached_downloader and hasattr(cached_downloader, 'fail_time') and cached_downloader.fail_time == 0:
                    # 使用增强版新鲜度检查函数（阈值60秒，匹配冷数据更新频率）
                    if _is_cache_fresh(cached_downloader):
                        return CommonResponse(
                            status="success",
                            msg="获取成功",
                            code="200",
                            data=_build_status_from_cache(cached_downloader)
                        )

                # 下载器在缓存中但离线，直接返回离线状态
                if cached_downloader:
                    nickname = getattr(cached_downloader, 'nickname', 'Unknown')
                    return CommonResponse(
                        status="success",
                        msg="下载器离线",
                        code="200",
                        data=DownloaderStatusVO(
                            connectStatus="disconnected",
                            nickname=nickname,
                            delay=None,
                            id=downloader_id,
                            uploadSpeed="0.00",
                            downloadSpeed="0.00",
                            downloadingCount=0,
                            seedingCount=0
                        )
                    )
    except Exception as e:
        logger.warning(f"从缓存获取状态失败，降级到实时查询: {str(e)}")

    # 降级方案：实时查询
    try:
        downloader_result = query_downloader_list(db, [downloader_id])
        if not downloader_result.success:
            return CommonResponse(
                status="error",
                msg=f"数据库查询失败: {downloader_result.message}",
                code="500",
                data=None
            )

        downloaders = downloader_result.data
        if not downloaders:
            return CommonResponse(
                status="error",
                msg="该下载器已被删除或不存在",
                code="404",
                data=None
            )

        # 只取第一个下载器（单下载器查询）
        row = downloaders[0]

        # 解密密码（数据库中存储的是加密密码）
        decrypted_password = None
        if row.password:
            try:
                decrypted_password = decrypt_password(row.password)
            except Exception as e:
                logger.warning(f"解密下载器 {row.nickname} 密码失败: {str(e)}")

        downloader = DownloaderVO(
            downloader_id=row.downloader_id,
            nickname=row.nickname,
            host=row.host,
            username=row.username,
            password=decrypted_password,  # 使用解密后的密码
            is_search='1' if row.is_search else '0',
            status=str(row.status) if row.status is not None else '1',
            enabled='1' if row.enabled else '0',
            downloader_type=row.downloader_type,
            port=row.port,
            is_ssl='1' if row.is_ssl else '0'
        )

        delay = await get_delay_async(downloader)
        # 使用统一的类型转换方法
        normalized_type = DownloaderTypeEnum.normalize(downloader.downloader_type)
        if normalized_type == DownloaderTypeEnum.QBITTORRENT:
            result = get_qbittorrent_detail(delay, downloader)
        elif normalized_type == DownloaderTypeEnum.TRANSMISSION:
            result = get_transmission_detail(delay, downloader)
        else:
            result = DownloaderStatusVO(
                connectStatus="unsupported",
                nickname=downloader.nickname,
                delay=delay if delay else 0,
                id=downloader.id,  # 修复: DownloaderVO 使用 id 属性，不是 downloader_id
                uploadSpeed="0.00",
                downloadSpeed="0.00",
                downloadingCount=0,
                seedingCount=0
            )

        return CommonResponse(
            status="success",
            msg="获取成功",
            code="200",
            data=result
        )
    except Exception as e:
        logger.error(f"获取下载器状态失败: {str(e)}")
        return CommonResponse(
            status="error",
            msg=f"获取下载器状态失败: {str(e)}",
            code="500",
            data=None
        )

@router.post("/test/{downloader_id}", summary="测试下载器连接", response_model=CommonResponse)
async def test_connection(downloader_id: Annotated[str, Path(description="下载器id")],
                        token: str = Header(..., alias="x-access-token"),
                        db: Session = Depends(get_db)):
    """测试下载器连接并返回连接结果和延迟
    """
    try:
        utils.verify_access_token(token)
    except Exception as e:
        return CommonResponse(
            status="error",
            msg="token验证失败，失败原因：" + str(e),
            code="401",
            data=None
        )

    try:
        # 查询下载器信息
        downloader_result = query_downloader_list(db, [downloader_id])
        if not downloader_result.success:
            return CommonResponse(
                status="error",
                msg=f"数据库查询失败: {downloader_result.message}",
                code="500",
                data=None
            )

        downloaders = downloader_result.data
        if not downloaders:
            return CommonResponse(
                status="error",
                msg="该下载器已被删除或不存在",
                code="404",
                data=None
            )

        # 获取下载器信息
        row = downloaders[0]
        downloader = DownloaderVO(
            downloader_id=row.downloader_id,
            nickname=row.nickname,
            host=row.host,
            username=row.username,
            password=row.password,
            is_search='1' if row.is_search else '0',
            status=str(row.status) if row.status is not None else '1',
            enabled='1' if row.enabled else '0',
            downloader_type=row.downloader_type,
            port=row.port,
            is_ssl='1' if row.is_ssl else '0'
        )

        # 检测延迟
        delay = await get_delay_async(downloader)

        # 判断连接状态
        success = delay is not None and delay != False and delay != 0
        connect_status = 'connected' if success else 'disconnected'
        message = '连接成功' if success else '连接失败'

        # 返回测试结果
        return CommonResponse(
            status="success",
            msg=message,
            code="200",
            data={
                'success': success,
                'delay': safe_delay_value(delay),
                'message': message
            }
        )
    except Exception as e:
        logger.error(f"测试连接失败: {str(e)}")
        return CommonResponse(
            status="error",
            msg=f"测试连接失败: {str(e)}",
            code="500",
            data={
                'success': False,
                'delay': None,
                'message': str(e)
            }
        )


def _build_status_from_cache(cached_downloader) -> DownloaderStatusVO:
    """从缓存的下载器构建状态响应"""
    import time

    # 获取缓存的实时状态
    upload_speed_kb = getattr(cached_downloader, 'upload_speed', 0) or 0
    download_speed_kb = getattr(cached_downloader, 'download_speed', 0) or 0
    downloading_count = getattr(cached_downloader, 'downloading_count', 0) or 0
    seeding_count = getattr(cached_downloader, 'seeding_count', 0) or 0

    # 获取延迟和在线状态
    delay = getattr(cached_downloader, 'delay', None)
    # 安全获取在线状态：如果属性不存在，默认为离线（False）
    is_online = getattr(cached_downloader, 'is_online', False) if hasattr(cached_downloader, 'is_online') else False

    # 自动转换速度单位（>= 1024 KB/s 转换为 MB/s），并添加单位后缀
    if upload_speed_kb >= 1024:
        upload_speed = f"{upload_speed_kb / 1024:.2f} MB/s"
    else:
        upload_speed = f"{upload_speed_kb:.2f} KB/s"

    if download_speed_kb >= 1024:
        download_speed = f"{download_speed_kb / 1024:.2f} MB/s"
    else:
        download_speed = f"{download_speed_kb:.2f} KB/s"

    # 使用统一的 ID 获取函数
    downloader_id = _get_downloader_id_from_cache(cached_downloader)

    # 根据端口连通性判断连接状态
    connect_status = "connected" if is_online else "disconnected"

    # 处理延迟值（安全转换，避免类型错误）
    try:
        if delay is None or delay is False:
            delay_value = None
        elif isinstance(delay, (int, float)):
            delay_value = float(delay)
        else:
            delay_value = None
    except (ValueError, TypeError):
        delay_value = None

    return DownloaderStatusVO(
        connectStatus=connect_status,  # 根据is_online判断
        nickname=getattr(cached_downloader, 'nickname', 'Unknown'),
        delay=delay_value,  # 使用缓存中的延迟值
        id=downloader_id or '',  # 使用获取的 ID，如果为空则使用空字符串
        uploadSpeed=upload_speed,
        downloadSpeed=download_speed,
        downloadingCount=downloading_count,  # 新增字段
        seedingCount=seeding_count           # 新增字段
    )


def get_qbittorrent_detail(delay, downloader):
    if delay == 0 or delay == False:
        client_status = "disconnected"
        upload_speed = "0.00 KB/s"
        download_speed = "0.00 KB/s"
    else:
        # 确定协议尝试顺序
        if downloader.is_ssl == "1":
            protocols = ["https", "http"]  # 优先HTTPS，失败降级HTTP
        else:
            protocols = ["http", "https"]  # 优先HTTP，失败尝试HTTPS

        client_status = "connection_failed"
        upload_speed = "0.00 KB/s"
        download_speed = "0.00 KB/s"

        for protocol in protocols:
            try:
                host = f"{protocol}://{downloader.host}"
                logger.info(f"尝试连接qBittorrent下载器: {downloader.host}:{downloader.port} ({protocol})")

                # 创建qBittorrent客户端，禁用SSL证书验证
                client = qbClient(
                    host=host,
                    port=downloader.port,
                    username=downloader.username,
                    password=downloader.password,
                    VERIFY_WEBUI_CERTIFICATE=False,  # 禁用SSL证书验证
                    REQUESTS_ARGS={'timeout': 10}      # 设置连接超时
                )

                transfer_info = client.transfer_info()
                # 转换为KB/s，然后自动转换单位
                upload_speed_kb = transfer_info.get('up_info_speed', 0) / 1024
                download_speed_kb = transfer_info.get('dl_info_speed', 0) / 1024

                # 自动添加单位
                upload_speed = f"{upload_speed_kb / 1024:.2f} MB/s" if upload_speed_kb >= 1024 else f"{upload_speed_kb:.2f} KB/s"
                download_speed = f"{download_speed_kb / 1024:.2f} MB/s" if download_speed_kb >= 1024 else f"{download_speed_kb:.2f} KB/s"

                client_status = "connected"
                logger.info(f"qBittorrent下载器连接成功: {downloader.nickname} ({protocol})")
                break  # 连接成功，退出协议尝试循环

            except Exception as qb_error:
                logger.warning(f"qBittorrent下载器连接失败: {downloader.host}:{downloader.port} ({protocol}) - {str(qb_error)}")

                if "SSL" in str(qb_error).upper() or "CERTIFICATE" in str(qb_error).upper():
                    # SSL相关错误，尝试HTTP
                    if protocol == "https":
                        continue
                    else:
                        client_status = "SSL连接失败"
                        break
                elif "401" in str(qb_error) or "authorization" in str(qb_error).lower():
                    # 认证错误
                    client_status = "登录失败，请检查账号密码是否正确"
                    break  # 认证错误不需要尝试其他协议
                elif protocol == "https":
                    # HTTPS连接失败，尝试HTTP
                    continue
                else:
                    # HTTP也失败，标记连接失败
                    client_status = "连接失败，请检查网络和下载器配置"
                    break
    # torrents_info = client.torrents_info(status_filter="active")
    # for torrent in torrents_info:
    #     upload_speed = upload_speed + torrent['upspeed']
    #     download_speed = download_speed + torrent['dlspeed']

    return DownloaderStatusVO(
        connectStatus=client_status,
        nickname=downloader.nickname,
        delay=safe_delay_value(delay),
        id=downloader.id,  # 修复: DownloaderVO 使用 id 属性，不是 downloader_id
        uploadSpeed=upload_speed,
        downloadSpeed=download_speed,
        downloadingCount=0,
        seedingCount=0
    )


def get_transmission_detail(delay, downloader):
    if delay == 0 or delay == False:
        client_status = "disconnected"
        upload_speed = "0.00 KB/s"
        download_speed = "0.00 KB/s"
    else:
        # 确定协议尝试顺序
        if downloader.is_ssl == "1":
            protocols = ["https", "http"]  # 优先HTTPS，失败降级HTTP
        else:
            protocols = ["http", "https"]  # 优先HTTP，失败尝试HTTPS

        client_status = "connection_failed"
        upload_speed = "0.00 KB/s"
        download_speed = "0.00 KB/s"

        for protocol in protocols:
            try:
                logger.info(f"尝试连接Transmission下载器: {downloader.host}:{downloader.port} ({protocol})")

                # transmission_rpc.Client不支持verify参数，直接使用基本参数
                tr_client = trClient(
                    host=downloader.host,
                    username=downloader.username,
                    password=downloader.password,
                    port=downloader.port,
                    protocol=protocol,
                    timeout=10.0
                )

                stats = tr_client.session_stats()
                # 转换为KB/s，然后自动转换单位
                upload_speed_kb = stats.upload_speed / 1024
                download_speed_kb = stats.download_speed / 1024

                # 自动添加单位
                upload_speed = f"{upload_speed_kb / 1024:.2f} MB/s" if upload_speed_kb >= 1024 else f"{upload_speed_kb:.2f} KB/s"
                download_speed = f"{download_speed_kb / 1024:.2f} MB/s" if download_speed_kb >= 1024 else f"{download_speed_kb:.2f} KB/s"

              # 连接成功，根据协议提供详细状态信息
                ssl_security = " (SSL加密)" if protocol == "https" else " (非加密)"
                client_status = f"connected{ssl_security}"
                logger.info(f"Transmission下载器连接成功: {downloader.nickname} ({protocol})")
                break  # 连接成功，退出协议尝试循环

            except SSLError as ssl_error:
                logger.warning(f"Transmission下载器SSL连接失败: {downloader.host}:{downloader.port} ({protocol}) - {str(ssl_error)}")
                if protocol == "https" and ("WRONG_VERSION_NUMBER" in str(ssl_error) or "CERTIFICATE" in str(ssl_error).upper()):
                    # SSL版本或证书错误，继续尝试HTTP
                    continue
                else:
                    # 其他SSL错误，标记连接失败
                    client_status = f"SSL连接失败: {str(ssl_error)[:100]}"
                    break

            except TransmissionAuthError as auth_error:
                logger.warning(f"Transmission下载器认证失败: {downloader.host}:{downloader.port} - {str(auth_error)}")
                client_status = "登录失败，请检查账号密码是否正确"
                break  # 认证错误不需要尝试其他协议

            except ConnectionError as conn_error:
                logger.warning(f"Transmission下载器连接错误: {downloader.host}:{downloader.port} ({protocol}) - {str(conn_error)}")
                if protocol == "https":
                    # HTTPS连接失败，尝试HTTP
                    continue
                else:
                    # HTTP也失败，标记连接失败
                    client_status = "连接失败，请检查网络和下载器配置"
                    break

            except TypeError as param_error:
                logger.error(f"Transmission下载器参数错误: {downloader.host}:{downloader.port} ({protocol}) - {str(param_error)}")
                if "unexpected keyword argument" in str(param_error):
                    # 参数错误，标记配置问题
                    client_status = "下载器配置错误，请检查参数设置"
                else:
                    client_status = f"参数错误: {str(param_error)[:100]}"
                break

            except Exception as e:
                logger.error(f"Transmission下载器未知错误: {downloader.host}:{downloader.port} ({protocol}) - {str(e)}")
                client_status = f"未知错误: {str(e)[:100]}"
                break

    return DownloaderStatusVO(
        connectStatus=client_status,
        nickname=downloader.nickname,
        delay=safe_delay_value(delay),
        id=downloader.id,  # 修复: DownloaderVO 使用 id 属性，不是 downloader_id
        uploadSpeed=upload_speed,
        downloadSpeed=download_speed,
        downloadingCount=0,
        seedingCount=0
    )


import asyncio

def safe_delay_value(delay) -> float | None:
    """
    安全的延迟值处理函数

    处理逻辑：
    - 整数延迟（如 100）→ 返回 100.0
    - 正常延迟（>= 1ms）→ 四舍五入保留2位小数（如 123.456 → 123.46）
    - 极小延迟（< 1ms）→ 四舍五入保留最多2位小数（如 0.123 → 0.12, 0.1 → 0.1）
    - 异常值（None/False/0）→ 返回 None

    Args:
        delay: 原始延迟值（可能为float、int、bool、None）

    Returns:
        float | None: 格式化后的延迟值
    """
    if delay is None or delay == False:
        return None  # 未连接或异常

    elif isinstance(delay, (int, float)):
        if delay == 0:
            return None  # 连接失败

        # 格式化小数位数
        delay_float = float(delay)

        # 极小延迟（< 1ms）：保留最多2位小数，去除尾部无意义的0
        if abs(delay_float) < 1.0 and delay_float != 0:
            rounded = round(delay_float, 2)
            # 如果四舍五入后为整数（如 0.10 → 0.1），直接返回整数形式
            return float(int(rounded)) if rounded == int(rounded) else rounded

        # 正常延迟（>= 1ms）：四舍五入保留2位小数
        else:
            return round(delay_float, 2)

    else:
        # 尝试转换字符串或其他类型
        try:
            if str(delay).replace('.', '').replace('-', '').isdigit():
                delay_float = float(delay)
                # 应用相同的格式化逻辑
                if delay_float == 0:
                    return None
                if abs(delay_float) < 1.0:
                    rounded = round(delay_float, 2)
                    return float(int(rounded)) if rounded == int(rounded) else rounded
                else:
                    return round(delay_float, 2)
        except (ValueError, TypeError):
            pass
        return None

async def get_delay_async(downloader):
    """异步版本的延迟检测"""
    try:
        if "127.0.0.1" in downloader.host:
            delay = 1
        else:
            # 使用线程池执行ping操作，避免阻塞
            delay = await asyncio.to_thread(ping3.ping, downloader.host, 3, "ms", "0.0.0.0", seq=2)
    except Exception as e:
        print(f"连接下载器时出错: {e}")
        delay = False
    return delay

def get_delay(downloader):
    """同步版本的延迟检测（保持兼容性）"""
    try:
        if "127.0.0.1" in downloader.host:
            delay = 1
        else:
            # 使用线程池执行ping操作，避免阻塞
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as executor:
                future = executor.submit(ping3.ping, downloader.host, 3000, "ms", "0.0.0.0", seq=2)
                delay = future.result(timeout=4)  # 4秒超时
    except Exception as e:
        print(f"连接下载器时出错: {e}")
        delay = False
    return delay


def query_downloader_list(db, id_list):
    """
    Query downloaders by ID list with standardized return format

    Args:
        db: Database session
        id_list: List of downloader IDs to query

    Returns:
        DatabaseResult containing list of downloaders or error information
    """
    try:
        # 使用ORM查询方式
        query = db.query(
            BtDownloaders.downloader_id.label("downloader_id"),
            BtDownloaders.nickname,
            BtDownloaders.host,
            BtDownloaders.username,
            BtDownloaders.password,
            BtDownloaders.is_search,
            BtDownloaders.status,
            BtDownloaders.enabled,
            BtDownloaders.downloader_type,
            BtDownloaders.port,
            BtDownloaders.is_ssl
        ).filter(
            BtDownloaders.dr == 0,
            BtDownloaders.downloader_id.in_(id_list)
        )
        downloaders = query.all()

        # Import here to avoid circular imports
        from app.core.database_result import DatabaseResult

        return DatabaseResult.success_result(
            data=downloaders,
            message="Downloaders queried successfully",
            total_count=len(downloaders)
        )
    except Exception as e:
        from app.core.database_result import DatabaseResult, DatabaseError
        return DatabaseResult.database_error_result(
            message=f"Failed to query downloaders: {str(e)}"
        )


@router.get('/getList', summary="获取下载器简单列表(仅ID和名称)", response_model=CommonResponse[List[DownloaderSimpleVO]])
def get_downloader_simple_list(
        enabled: Optional[bool] = Query(True, description="是否只返回启用的下载器", examples={"default": True}),
        req: Request = None,
        db: Session = Depends(get_db)
):
    """
    获取下载器简单列表，仅返回ID和名称

    特点:
    - 实时从数据库查询，不依赖缓存
    - 只返回 downloader_id 和 nickname 字段
    - 按 nickname 字母顺序排序
    - 用于种子管理页面的下载器下拉选择

    Args:
        enabled: 是否只返回启用的下载器（默认为True）
        db: 数据库会话

    Returns:
        - downloader_id: 下载器ID
        - nickname: 下载器名称
    """
    # 1. JWT 校验
    try:
        token = req.headers.get("x-access-token")
        utils.verify_access_token(token)
    except Exception as e:
        return CommonResponse(
            status="error",
            msg="token验证失败，失败原因：" + str(e),
            code="401",
            data=None
        )

    # 2. 构建查询条件
    try:
        # 基础条件：未删除的下载器
        conditions = ["dr = 0"]
        params = {}

        # 可选条件：是否启用
        if enabled is not None:
            conditions.append("enabled = :enabled")
            params["enabled"] = 1 if enabled else 0

        # 构建 SQL 查询
        sql = f"""
            SELECT downloader_id, nickname
            FROM bt_downloaders
            WHERE {' AND '.join(conditions)}
            ORDER BY nickname ASC
        """

        result = db.execute(text(sql), params)
        downloaders = [
            DownloaderSimpleVO(
                downloader_id=row.downloader_id,
                nickname=row.nickname
            )
            for row in result
        ]

        return CommonResponse(
            status="success",
            msg="获取下载器列表成功",
            code="200",
            data=downloaders
        )

    except Exception as e:
        logger.error(f"数据库查询失败: {str(e)}")
        return CommonResponse(
            status="error",
            msg=f"数据库查询失败: {str(e)}",
            code="500",
            data=None
        )


@router.post('/getList', summary="获取下载器列表(支持多条件查询)", response_model=CommonResponse[List[DownloaderListVO]])
async def getlist_from_cache(
        downloader_request: ListDownloader = None,
        req: Request = None,
        db: Session = Depends(get_db)
):
    """
    获取所有未逻辑删除的下载器列表,并标记连通状态
    
    支持多条件模糊查询:
    - nickname: 下载器别名(模糊)
    - host: 下载器主机地址(模糊)
    - is_search: 是否启用搜索(模糊)
    - enabled: 是否启用(模糊)
    
    不传参数或传空对象: 返回所有 dr=0 的下载器
    
    返回:
    - 所有 dr=0 的下载器(可选条件过滤)
    - connectStatus: "1"=在缓存中(在线), "0"=不在缓存中(离线)
    - 按在线优先排序
    """
    # 1. JWT 校验
    try:
        token = req.headers.get("x-access-token")
        utils.verify_access_token(token)
    except Exception as e:
        return CommonResponse(
            status="error",
            msg="token验证失败，失败原因：" + str(e),
            code="401",
            data=None
        )

    # 2. 构建 SQL 查询(支持多条件模糊查询)
    try:
        # 基础 SQL
        base_sql = """
            SELECT downloader_id, host, nickname, username, status, enabled, is_search,
                   downloader_type, port, is_ssl
            FROM bt_downloaders
            WHERE dr = 0
        """
        
        # 构建查询条件
        conditions = []
        params = {}
        
        if downloader_request:
            if downloader_request.nickname:
                conditions.append("nickname LIKE :nickname")
                params["nickname"] = f"%{downloader_request.nickname}%"
            
            if downloader_request.host:
                conditions.append("host LIKE :host")
                params["host"] = f"%{downloader_request.host}%"
            
            if downloader_request.is_search:
                conditions.append("is_search LIKE :is_search")
                params["is_search"] = f"%{downloader_request.is_search}%"
            
            if downloader_request.enabled:
                conditions.append("enabled LIKE :enabled")
                params["enabled"] = f"%{downloader_request.enabled}%"
        
        # 组装 SQL
        if conditions:
            sql = base_sql + " AND " + " AND ".join(conditions)
        else:
            sql = base_sql
        
        result = db.execute(text(sql), params)
        
        # 构建 DownloaderListVO 列表(暂不设置 connectStatus)
        downloaders = [
            DownloaderListVO(
                downloader_id=row.downloader_id,
                nickname=row.nickname,
                host=row.host,
                is_search=row.is_search,
                status=row.status,
                enabled=row.enabled,
                downloader_type=row.downloader_type,
                port=str(row.port)
            )
            for row in result
        ]
    except Exception as e:
        logger.error(f"数据库查询失败: {str(e)}")
        return CommonResponse(
            status="error",
            msg=f"数据库查询失败: {str(e)}",
            code="500",
            data=None
        )

    # 3. 从缓存获取在线下载器 ID 集合
    connected_ids = set()  # 默认为空集合(缓存不可用时,所有下载器都标记为离线)

    try:
        # ✅ 修复: 从正确的 FastAPI 实例获取缓存
        from app.factory import app as downloader_app

        if hasattr(downloader_app.state, 'store'):
            # ✅ 使用异步方法获取缓存（避免 RuntimeWarning）
            cached_downloaders = await downloader_app.state.store.get_snapshot()
            
            if cached_downloaders:
                # 构建在线 ID 集合(统一转换为 str 类型,避免类型不一致)
                for cached_downloader in cached_downloaders:
                    # 使用统一的 ID 获取函数（兼容多种对象类型）
                    downloader_id = _get_downloader_id_from_cache(cached_downloader)
                    if downloader_id is not None:
                        connected_ids.add(downloader_id)
            else:
                logger.info("缓存 snapshot 为空,所有下载器标记为离线")
        else:
            logger.error("缓存 store 未初始化,所有下载器标记为离线")
    except Exception as e:
        logger.error(f"获取缓存失败: {str(e)},所有下载器标记为离线")

    # 4. 为每个下载器设置 connectStatus
    for downloader in downloaders:
        # 使用 downloaderId(VO 中的字段名)进行匹配
        if downloader.downloaderId in connected_ids:
            downloader.connectStatus = "1"  # 在线
        else:
            downloader.connectStatus = "0"  # 离线

    # 5. 按 connectStatus 排序(在线在前,离线在后)
    downloaders.sort(key=lambda d: d.connectStatus, reverse=True)

    # 6. 返回响应
    return CommonResponse(
        status="success",
        msg="获取下载器列表成功",
        code="200",
        data=downloaders
    )




# ==================== 路径映射相关接口 ====================

from pydantic import BaseModel
from app.api.schemas.path_mapping import PathMappingTestRequest


class PathMappingAdd(BaseModel):
    """添加路径映射请求"""
    downloader_id: str
    name: str
    internal: str
    external: str
    description: Optional[str] = None
    mapping_type: str = "local"


class PathMappingRemove(BaseModel):
    """删除路径映射请求"""
    downloader_id: str
    name: str



@router.get("/{downloader_id}/path-mapping", summary="获取下载器的路径映射配置")
def get_path_mappings(
    downloader_id: str,
    req: Request = None,
    db: Session = Depends(get_db)
):
    """
    获取下载器的路径映射配置

    权限: 需要登录

    Args:
        downloader_id: 下载器ID

    Returns:
        CommonResponse: 包含路径映射配置的响应
    """
    try:
        # 验证token
        token = req.headers.get("x-access-token")
        utils.verify_access_token(token)
    except Exception as e:
        return CommonResponse(
            status="error",
            msg="token验证失败",
            code="401",
            data=None
        )

    try:
        # 查询下载器
        downloader = db.query(BtDownloaders).filter(
            BtDownloaders.downloader_id == downloader_id
        ).first()

        if not downloader:
            return CommonResponse(
                status="error",
                msg="下载器不存在",
                code="404",
                data=None
            )

        # 获取路径映射
        if downloader.path_mapping:
            from app.core.path_mapping import PathMappingService
            path_mapping_service = PathMappingService(downloader.path_mapping)
            mappings = path_mapping_service.get_mappings()
            default_mapping = path_mapping_service.default_mapping

            return CommonResponse(
                status="success",
                msg="查询成功",
                code="200",
                data={
                    "mappings": mappings,
                    "default_mapping": default_mapping  # ✅ 包含默认映射
                }
            )
        else:
            return CommonResponse(
                status="success",
                msg="未配置路径映射",
                code="200",
                data={
                    "mappings": [],
                    "default_mapping": None  # ✅ 明确设置为 None
                }
            )

    except Exception as e:
        logger.error(f"查询路径映射失败: {str(e)}")
        return CommonResponse(
            status="error",
            msg=f"查询失败: {str(e)}",
            code="500",
            data=None
        )


@router.post("/path-mapping/add", summary="添加路径映射")
def add_path_mapping(
    request_data: PathMappingAdd,
    req: Request = None,
    db: Session = Depends(get_db)
):
    """
    添加路径映射

    权限: 需要登录

    Args:
        request_data: 路径映射请求数据

    Returns:
        CommonResponse: 操作结果
    """
    try:
        # 验证token
        token = req.headers.get("x-access-token")
        utils.verify_access_token(token)
    except Exception as e:
        return CommonResponse(
            status="error",
            msg="token验证失败",
            code="401",
            data=None
        )

    try:
        # 查询下载器
        downloader = db.query(BtDownloaders).filter(
            BtDownloaders.downloader_id == request_data.downloader_id
        ).first()

        if not downloader:
            return CommonResponse(
                status="error",
                msg="下载器不存在",
                code="404",
                data=None
            )

        # 加载现有配置
        from app.core.path_mapping import PathMappingService

        if downloader.path_mapping:
            path_mapping_service = PathMappingService(downloader.path_mapping)
        else:
            path_mapping_service = PathMappingService()
            path_mapping_service.mappings = []

        # 添加新映射
        path_mapping_service.add_mapping(
            name=request_data.name,
            internal=request_data.internal,
            external=request_data.external,
            description=request_data.description,
            mapping_type=request_data.mapping_type
        )

        # 保存配置
        downloader.path_mapping = path_mapping_service.to_json()
        db.commit()

        return CommonResponse(
            status="success",
            msg="添加成功",
            code="200",
            data=None
        )

    except Exception as e:
        logger.error(f"添加路径映射失败: {str(e)}")
        db.rollback()
        return CommonResponse(
            status="error",
            msg=f"添加失败: {str(e)}",
            code="500",
            data=None
        )


@router.post("/path-mapping/remove", summary="删除路径映射")
def remove_path_mapping(
    request_data: PathMappingRemove,
    req: Request = None,
    db: Session = Depends(get_db)
):
    """
    删除路径映射

    权限: 需要登录

    Args:
        request_data: 删除路径映射请求数据

    Returns:
        CommonResponse: 操作结果
    """
    try:
        # 验证token
        token = req.headers.get("x-access-token")
        utils.verify_access_token(token)
    except Exception as e:
        return CommonResponse(
            status="error",
            msg="token验证失败",
            code="401",
            data=None
        )

    try:
        # 查询下载器
        downloader = db.query(BtDownloaders).filter(
            BtDownloaders.downloader_id == request_data.downloader_id
        ).first()

        if not downloader:
            return CommonResponse(
                status="error",
                msg="下载器不存在",
                code="404",
                data=None
            )

        # 检查是否有配置
        if not downloader.path_mapping:
            return CommonResponse(
                status="error",
                msg="未配置路径映射",
                code="400",
                data=None
            )

        # 加载现有配置
        from app.core.path_mapping import PathMappingService
        path_mapping_service = PathMappingService(downloader.path_mapping)

        # 删除映射
        success = path_mapping_service.remove_mapping(request_data.name)

        if not success:
            return CommonResponse(
                status="error",
                msg=f"未找到路径映射: {request_data.name}",
                code="404",
                data=None
            )

        # 保存配置
        downloader.path_mapping = path_mapping_service.to_json()
        db.commit()

        return CommonResponse(
            status="success",
            msg="删除成功",
            code="200",
            data=None
        )

    except Exception as e:
        logger.error(f"删除路径映射失败: {str(e)}")
        db.rollback()
        return CommonResponse(
            status="error",
            msg=f"删除失败: {str(e)}",
            code="500",
            data=None
        )


@router.post("/{downloader_id}/path-mapping/test", summary="测试路径映射配置")
def test_path_mapping(
    downloader_id: str,
    request_data: PathMappingTestRequest,
    req: Request = None,
    db: Session = Depends(get_db)
):
    """
    测试路径映射配置的有效性

    权限: 需要登录

    Args:
        downloader_id: 下载器ID
        request_data: 路径映射测试请求

    Returns:
        CommonResponse: 测试结果
    """
    try:
        # 验证token
        token = req.headers.get("x-access-token")
        utils.verify_access_token(token)
    except Exception as e:
        return CommonResponse(
            status="error",
            msg="token验证失败",
            code="401",
            data=None
        )

    try:
        # 验证下载器存在
        downloader = db.query(BtDownloaders).filter(
            BtDownloaders.downloader_id == downloader_id
        ).first()

        if not downloader:
            return CommonResponse(
                status="error",
                msg="下载器不存在",
                code="404",
                data=None
            )

        # 后端验证
        backend_validation = {
            "json_format_valid": True,
            "structure_valid": True,
            "fields_complete": True,
            "no_path_conflicts": True,
            "errors": []
        }

        try:
            # 1. JSON格式验证(由Pydantic自动完成)
            config = request_data.path_mapping

            # 2. 结构验证
            if not hasattr(config, 'mappings') or not isinstance(config.mappings, list):
                backend_validation["structure_valid"] = False
                backend_validation["errors"].append("缺少mappings数组")

            # 3. 字段完整性验证
            for idx, mapping in enumerate(config.mappings):
                if not mapping.name or not mapping.internal or not mapping.external:
                    backend_validation["fields_complete"] = False
                    backend_validation["errors"].append(
                        f"映射#{idx+1}缺少必填字段"
                    )

            # 4. 路径冲突检测
            internal_paths = [m.internal for m in config.mappings]
            if len(internal_paths) != len(set(internal_paths)):
                backend_validation["no_path_conflicts"] = False
                backend_validation["errors"].append("存在重复的internal路径")

            # 5. 路径标准化验证(尝试创建PathMappingService)
            try:
                from app.core.path_mapping import PathMappingService
                service = PathMappingService(config.model_dump_json())
                # 验证路径标准化是否成功
                for mapping in config.mappings:
                    normalized_internal = service._normalize_path(mapping.internal)
                    normalized_external = service._normalize_path(mapping.external)
                    logger.debug(f"路径标准化: {mapping.internal} -> {normalized_internal}")
            except Exception as e:
                backend_validation["no_path_conflicts"] = False
                backend_validation["errors"].append(f"路径标准化失败: {str(e)}")

        except Exception as e:
            backend_validation["json_format_valid"] = False
            backend_validation["errors"].append(f"配置解析失败: {str(e)}")

        # 判断总体验证结果
        is_valid = all([
            backend_validation["json_format_valid"],
            backend_validation["structure_valid"],
            backend_validation["fields_complete"],
            backend_validation["no_path_conflicts"]
        ])

        # 构建响应
        test_response = {
            "valid": is_valid,
            "message": "配置验证通过" if is_valid else f"验证失败: {', '.join(backend_validation['errors'])}",
            "backend_validation": backend_validation,
            "frontend_validation": None  # 由前端填充
        }

        return CommonResponse(
            status="success",
            msg="测试完成",
            code="200",
            data=test_response
        )

    except Exception as e:
        logger.error(f"路径映射测试失败: {str(e)}")
        return CommonResponse(
            status="error",
            msg=f"测试失败: {str(e)}",
            code="500",
            data=None
        )
