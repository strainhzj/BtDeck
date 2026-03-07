"""
Tracker测试工具API接口

提供关键词匹配测试功能
"""

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session
import logging

from app.database import get_db
from app.api.responseVO import CommonResponse
from app.api.schemas.tracker_messages import MatchTestRequest, MatchTestResponse
from app.torrents.models import TrackerKeywordConfig
from app.core.tracker_judgment import TrackerJudgmentEngine
from app.auth import utils

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/match", summary="测试关键词匹配")
def test_match(
    test_req: MatchTestRequest,
    request: Request,
    db: Session = Depends(get_db)
):
    """
    测试关键词匹配

    返回给定消息的匹配结果,包括:
    - 最终判定的状态
    - 匹配到的关键词列表
    - 匹配类型(success/failure/none)
    """
    # JWT验证
    token = request.headers.get("x-access-token")
    try:
        utils.verify_access_token(token)
    except Exception as e:
        logger.warning(f"Token验证失败: {str(e)}")
        return CommonResponse(
            status="error",
            msg="token验证失败",
            code="401",
            data=None
        )

    try:
        # 使用判断引擎
        judgment_engine = TrackerJudgmentEngine()
        final_status = judgment_engine.judge_status(
            original_status=test_req.originalStatus,
            msg=test_req.msg,
            language=test_req.language
        )

        # 查询匹配到的关键词
        matched_keywords = []
        match_type = "none"

        # 查询所有启用的关键词
        keywords = db.query(TrackerKeywordConfig).filter(
            TrackerKeywordConfig.enabled == True,
            TrackerKeywordConfig.dr == 0
        ).all()

        test_msg_lower = test_req.msg.lower()

        for keyword in keywords:
            if keyword.keyword.lower() in test_msg_lower:
                matched_keywords.append(keyword.keyword)
                if keyword.keyword_type == "failure":
                    match_type = "failure"
                elif match_type != "failure" and keyword.keyword_type == "success":
                    match_type = "success"

        logger.info(f"测试关键词匹配: msg='{test_req.msg[:50]}...', matched={len(matched_keywords)}, type={match_type}")

        return CommonResponse(
            status="success",
            msg="测试完成",
            code="200",
            data=MatchTestResponse(
                originalStatus=test_req.originalStatus,
                finalStatus=final_status,
                matchedKeywords=matched_keywords,
                matchType=match_type
            ).model_dump()
        )

    except Exception as e:
        logger.error(f"测试关键词匹配失败: {str(e)}")
        return CommonResponse(
            status="error",
            msg=f"测试失败: {str(e)}",
            code="500",
            data=None
        )
