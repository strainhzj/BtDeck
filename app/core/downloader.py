from fastapi import Depends
from sqlalchemy import Boolean, text
from sqlalchemy.orm import Session
from app.database import get_db
from app.downloader import models
from app.core.database_result import DatabaseResult, DatabaseError
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
        s = text("select * from bt_downloaders")
        downloader_list = db.execute(s)
        downloader_models = []
        for row in downloader_list.fetchall():
            downloader_models.append(models.BtDownloaders(*row))

        return DatabaseResult.success_result(
            data=downloader_models,
            message="Downloaders retrieved successfully",
            total_count=len(downloader_models)
        )
    except Exception as e:
        return DatabaseResult.database_error_result(
            message=f"Failed to retrieve downloaders: {str(e)}"
        )
