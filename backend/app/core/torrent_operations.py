"""
Standardized torrent database operations

This module contains refactored torrent-related database operations that use
the standardized DatabaseResult return format.
"""

import uuid
from typing import List, Optional, Dict, Any
from sqlalchemy.orm import Session
from app.torrents.models import TorrentInfo, TrackerInfo
from app.core.database_result import DatabaseResult, DatabaseError


def create_torrent(db: Session, torrent_data: Dict[str, Any]) -> DatabaseResult[TorrentInfo]:
    """
    Create a new torrent record with standardized return format

    Args:
        db: Database session
        torrent_data: Torrent data dictionary

    Returns:
        DatabaseResult containing the created TorrentInfo or error information
    """
    try:
        # Validate required fields
        if not torrent_data.get('hash'):
            return DatabaseResult.validation_error_result("Torrent hash is required")

        # Check for duplicate hash
        existing = db.query(TorrentInfo).filter(TorrentInfo.hash == torrent_data['hash']).first()
        if existing:
            return DatabaseResult.failure_result(
                message="Torrent with this hash already exists",
                error_code=DatabaseError.DUPLICATE_KEY
            )

        # Generate ID if not provided
        if "id_" not in torrent_data:
            torrent_data["id_"] = str(uuid.uuid4())

        db_torrent = TorrentInfo(**torrent_data)
        db.add(db_torrent)
        db.commit()
        db.refresh(db_torrent)

        return DatabaseResult.success_result(
            data=db_torrent,
            message="Torrent created successfully",
            affected_rows=1
        )
    except Exception as e:
        db.rollback()
        return DatabaseResult.database_error_result(
            message=f"Failed to create torrent: {str(e)}"
        )


def get_torrent(db: Session, torrent_id: str) -> DatabaseResult[TorrentInfo]:
    """
    Get torrent by ID with standardized return format

    Args:
        db: Database session
        torrent_id: Torrent ID

    Returns:
        DatabaseResult containing the TorrentInfo or not found information
    """
    try:
        torrent = db.query(TorrentInfo).filter(TorrentInfo.info_id == torrent_id).first()
        if torrent:
            return DatabaseResult.success_result(
                data=torrent,
                message="Torrent retrieved successfully"
            )
        else:
            return DatabaseResult.not_found_result(
                message=f"Torrent with ID {torrent_id} not found"
            )
    except Exception as e:
        return DatabaseResult.database_error_result(
            message=f"Failed to retrieve torrent: {str(e)}"
        )


def get_torrent_by_hash(db: Session, hash_value: str) -> DatabaseResult[TorrentInfo]:
    """
    Get torrent by hash with standardized return format

    Args:
        db: Database session
        hash_value: Torrent hash value

    Returns:
        DatabaseResult containing the TorrentInfo or not found information
    """
    try:
        torrent = db.query(TorrentInfo).filter(TorrentInfo.hash == hash_value).first()
        if torrent:
            return DatabaseResult.success_result(
                data=torrent,
                message="Torrent retrieved successfully by hash"
            )
        else:
            return DatabaseResult.not_found_result(
                message=f"Torrent with hash {hash_value} not found"
            )
    except Exception as e:
        return DatabaseResult.database_error_result(
            message=f"Failed to retrieve torrent by hash: {str(e)}"
        )


def search_torrents_by_name(db: Session, name_query: str, skip: int = 0, limit: int = 100) -> DatabaseResult[List[TorrentInfo]]:
    """
    Search torrents by name with standardized return format

    Args:
        db: Database session
        name_query: Name search query
        skip: Number of records to skip
        limit: Maximum number of records to return

    Returns:
        DatabaseResult containing list of TorrentInfo objects
    """
    try:
        query = db.query(TorrentInfo).filter(TorrentInfo.name.contains(name_query))
        total_count = query.count()

        torrents = query.offset(skip).limit(limit).all()

        return DatabaseResult.success_result(
            data=torrents,
            message=f"Found {len(torrents)} torrents matching '{name_query}'",
            total_count=total_count
        )
    except Exception as e:
        return DatabaseResult.database_error_result(
            message=f"Failed to search torrents: {str(e)}"
        )


def update_torrent(db: Session, torrent_id: str, torrent_data: Dict[str, Any]) -> DatabaseResult[TorrentInfo]:
    """
    Update torrent with standardized return format

    Args:
        db: Database session
        torrent_id: Torrent ID
        torrent_data: Updated torrent data

    Returns:
        DatabaseResult containing the updated TorrentInfo or error information
    """
    try:
        torrent = db.query(TorrentInfo).filter(TorrentInfo.info_id == torrent_id).first()
        if not torrent:
            return DatabaseResult.not_found_result(
                message=f"Torrent with ID {torrent_id} not found"
            )

        # Update fields
        for key, value in torrent_data.items():
            if hasattr(torrent, key):
                setattr(torrent, key, value)

        db.commit()
        db.refresh(torrent)

        return DatabaseResult.success_result(
            data=torrent,
            message="Torrent updated successfully",
            affected_rows=1
        )
    except Exception as e:
        db.rollback()
        return DatabaseResult.database_error_result(
            message=f"Failed to update torrent: {str(e)}"
        )


def delete_torrent(db: Session, torrent_id: str) -> DatabaseResult[None]:
    """
    Delete torrent with standardized return format

    Args:
        db: Database session
        torrent_id: Torrent ID

    Returns:
        DatabaseResult indicating success or failure
    """
    try:
        torrent = db.query(TorrentInfo).filter(TorrentInfo.info_id == torrent_id).first()
        if not torrent:
            return DatabaseResult.not_found_result(
                message=f"Torrent with ID {torrent_id} not found"
            )

        db.delete(torrent)
        db.commit()

        return DatabaseResult.success_result(
            message="Torrent deleted successfully",
            affected_rows=1
        )
    except Exception as e:
        db.rollback()
        return DatabaseResult.database_error_result(
            message=f"Failed to delete torrent: {str(e)}"
        )


def get_torrents_by_save_path(db: Session, path: str, skip: int = 0, limit: int = 100) -> DatabaseResult[List[TorrentInfo]]:
    """
    Get torrents by save path with standardized return format

    Args:
        db: Database session
        path: Save path to filter by
        skip: Number of records to skip
        limit: Maximum number of records to return

    Returns:
        DatabaseResult containing list of TorrentInfo objects
    """
    try:
        query = db.query(TorrentInfo).filter(TorrentInfo.save_path == path)
        total_count = query.count()

        torrents = query.offset(skip).limit(limit).all()

        return DatabaseResult.success_result(
            data=torrents,
            message=f"Found {len(torrents)} torrents in path '{path}'",
            total_count=total_count
        )
    except Exception as e:
        return DatabaseResult.database_error_result(
            message=f"Failed to retrieve torrents by path: {str(e)}"
        )


def get_torrents_count(db: Session, status: Optional[str] = None, category: Optional[str] = None) -> DatabaseResult[int]:
    """
    Get torrent count with optional filtering with standardized return format

    Args:
        db: Database session
        status: Filter by status
        category: Filter by category

    Returns:
        DatabaseResult containing the count of torrents
    """
    try:
        query = db.query(TorrentInfo)

        if status:
            query = query.filter(TorrentInfo.status == status)
        if category:
            query = query.filter(TorrentInfo.category == category)

        count = query.count()

        return DatabaseResult.success_result(
            data=count,
            message=f"Found {count} torrents matching criteria",
            total_count=count
        )
    except Exception as e:
        return DatabaseResult.database_error_result(
            message=f"Failed to count torrents: {str(e)}"
        )