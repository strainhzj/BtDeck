from fastapi import Depends
from sqlalchemy.orm import Session
from app.database import get_db
from app.downloader import models
from app.core.database_result import DatabaseResult
from typing import List


def getDownloaders(db: Session = Depends(get_db)) -> DatabaseResult[List[models.BtDownloaders]]:
    """
    Retrieve all downloaders from the database

    Args:
        db: Database session

    Returns:
        DatabaseResult containing list of downloaders or error information
    """
    try:
        # 用 ORM 查询替代原 "SELECT *" 裸查询 + 位置参数解包。
        # 原实现 BtDownloaders(*row) 在回滚场景（DB 多列）会 TypeError 崩溃；
        # ORM 显式映射列，对多余列免疫。
        downloader_list = db.query(models.BtDownloaders).all()

        return DatabaseResult.success_result(
            data=downloader_list, message="Downloaders retrieved successfully", total_count=len(downloader_list)
        )
    except Exception as e:
        return DatabaseResult.database_error_result(message=f"Failed to retrieve downloaders: {str(e)}")
