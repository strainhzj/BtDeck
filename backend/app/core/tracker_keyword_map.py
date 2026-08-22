"""共享的 Tracker 关键词池加载器。

种子级 ``has_tracker_error`` 判定任务与展示层的 Announce/Scrape 状态覆写必须
使用同一份 ``{keyword: keyword_type}`` 映射，否则关键词池更新后一层已按新口径
判定、另一层仍按旧口径展示。本模块只做 DB 读取；策略判断由
``tracker_status_policy`` 的纯函数承担。
"""

import logging
from typing import Dict

from sqlalchemy.orm import Session

from app.torrents.models import TrackerKeywordConfig

logger = logging.getLogger(__name__)


def load_active_keyword_map(db: Session) -> Dict[str, str]:
    """加载启用的 failed/success/ignored 关键词为 ``{keyword: keyword_type}``。

    - 仅取 failed/success/ignored 三池（candidate 不参与判定）；
    - first-wins 去重：唯一索引 ``idx_tracker_keyword_unique`` 下重复关键词
      正常不可达，不再复刻判定任务历史上的 priority 重查（该分支为死代码且
      漏带三池过滤，可能把 candidate 带入映射）；
    - 异常时 log 后返回空映射：调用方按"本轮跳过判定/不覆写"降级，不中断
      请求（与判定任务历史语义一致）。
    """
    keyword_map: Dict[str, str] = {}
    try:
        keywords = (
            db.query(TrackerKeywordConfig)
            .filter(
                TrackerKeywordConfig.enabled.is_(True),
                TrackerKeywordConfig.dr == 0,
                TrackerKeywordConfig.keyword_type.in_(["failed", "success", "ignored"]),
            )
            .all()
        )
        for kw in keywords:
            keyword = str(kw.keyword)
            if keyword not in keyword_map:
                keyword_map[keyword] = str(kw.keyword_type)
    except Exception as exc:
        logger.error("加载 tracker 关键词池失败，按空池降级: %s", exc, exc_info=True)
        return {}
    return keyword_map
