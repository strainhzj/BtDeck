"""
Standardized tracker database operations

This module contains refactored tracker-related database operations that use
the standardized DatabaseResult return format.
"""

import uuid
from typing import List, Optional, Dict, Any
from sqlalchemy.orm import Session
from app.torrents.models import TrackerInfo
from app.core.database_result import DatabaseResult, DatabaseError


def create_tracker(db: Session, tracker_data: Dict[str, Any]) -> DatabaseResult[TrackerInfo]:
    """
    Create a new tracker record with standardized return format

    Args:
        db: Database session
        tracker_data: Tracker data dictionary

    Returns:
        DatabaseResult containing the created TrackerInfo or error information
    """
    try:
        # Validate required fields
        if not tracker_data.get('tracker_url'):
            return DatabaseResult.validation_error_result("Tracker URL is required")

        # Generate ID if not provided
        if "id_" not in tracker_data:
            tracker_data["id_"] = str(uuid.uuid4())

        db_tracker = TrackerInfo(**tracker_data)
        db.add(db_tracker)
        db.commit()
        db.refresh(db_tracker)

        return DatabaseResult.success_result(
            data=db_tracker,
            message="Tracker created successfully",
            affected_rows=1
        )
    except Exception as e:
        db.rollback()
        return DatabaseResult.database_error_result(
            message=f"Failed to create tracker: {str(e)}"
        )


def get_tracker(db: Session, tracker_id: str) -> DatabaseResult[TrackerInfo]:
    """
    Get tracker by ID with standardized return format

    Args:
        db: Database session
        tracker_id: Tracker ID

    Returns:
        DatabaseResult containing the TrackerInfo or not found information
    """
    try:
        tracker = db.query(TrackerInfo).filter(TrackerInfo.id_ == tracker_id).first()
        if tracker:
            return DatabaseResult.success_result(
                data=tracker,
                message="Tracker retrieved successfully"
            )
        else:
            return DatabaseResult.not_found_result(
                message=f"Tracker with ID {tracker_id} not found"
            )
    except Exception as e:
        return DatabaseResult.database_error_result(
            message=f"Failed to retrieve tracker: {str(e)}"
        )


def get_trackers_by_torrent(db: Session, torrent_info_id: str) -> DatabaseResult[List[TrackerInfo]]:
    """
    Get trackers by torrent ID with standardized return format

    Args:
        db: Database session
        torrent_info_id: Torrent info ID

    Returns:
        DatabaseResult containing list of TrackerInfo objects
    """
    try:
        trackers = db.query(TrackerInfo).filter(TrackerInfo.torrent_info_id == torrent_info_id).all()

        return DatabaseResult.success_result(
            data=trackers,
            message=f"Found {len(trackers)} trackers for torrent {torrent_info_id}",
            total_count=len(trackers)
        )
    except Exception as e:
        return DatabaseResult.database_error_result(
            message=f"Failed to retrieve trackers by torrent: {str(e)}"
        )


def get_trackers(db: Session, skip: int = 0, limit: int = 100) -> DatabaseResult[List[TrackerInfo]]:
    """
    Get all trackers with pagination with standardized return format

    Args:
        db: Database session
        skip: Number of records to skip
        limit: Maximum number of records to return

    Returns:
        DatabaseResult containing list of TrackerInfo objects
    """
    try:
        query = db.query(TrackerInfo)
        total_count = query.count()

        trackers = query.offset(skip).limit(limit).all()

        return DatabaseResult.success_result(
            data=trackers,
            message=f"Retrieved {len(trackers)} trackers",
            total_count=total_count
        )
    except Exception as e:
        return DatabaseResult.database_error_result(
            message=f"Failed to retrieve trackers: {str(e)}"
        )


def get_trackers_by_status(db: Session, status: str) -> DatabaseResult[List[TrackerInfo]]:
    """
    Get trackers by status with standardized return format

    Args:
        db: Database session
        status: Tracker status to filter by

    Returns:
        DatabaseResult containing list of TrackerInfo objects
    """
    try:
        trackers = db.query(TrackerInfo).filter(TrackerInfo.status == status).all()

        return DatabaseResult.success_result(
            data=trackers,
            message=f"Found {len(trackers)} trackers with status '{status}'",
            total_count=len(trackers)
        )
    except Exception as e:
        return DatabaseResult.database_error_result(
            message=f"Failed to retrieve trackers by status: {str(e)}"
        )


def update_tracker(db: Session, tracker_id: str, tracker_data: Dict[str, Any]) -> DatabaseResult[TrackerInfo]:
    """
    Update tracker with standardized return format

    Args:
        db: Database session
        tracker_id: Tracker ID
        tracker_data: Updated tracker data

    Returns:
        DatabaseResult containing the updated TrackerInfo or error information
    """
    try:
        tracker = db.query(TrackerInfo).filter(TrackerInfo.id_ == tracker_id).first()
        if not tracker:
            return DatabaseResult.not_found_result(
                message=f"Tracker with ID {tracker_id} not found"
            )

        # Update fields
        for key, value in tracker_data.items():
            if hasattr(tracker, key):
                setattr(tracker, key, value)

        db.commit()
        db.refresh(tracker)

        return DatabaseResult.success_result(
            data=tracker,
            message="Tracker updated successfully",
            affected_rows=1
        )
    except Exception as e:
        db.rollback()
        return DatabaseResult.database_error_result(
            message=f"Failed to update tracker: {str(e)}"
        )


def update_tracker_status(db: Session, tracker_id: str, status: str, msg: Optional[str] = None) -> DatabaseResult[TrackerInfo]:
    """
    Update tracker status with standardized return format

    Args:
        db: Database session
        tracker_id: Tracker ID
        status: New status
        msg: Optional status message

    Returns:
        DatabaseResult containing the updated TrackerInfo or error information
    """
    try:
        tracker = db.query(TrackerInfo).filter(TrackerInfo.id_ == tracker_id).first()
        if not tracker:
            return DatabaseResult.not_found_result(
                message=f"Tracker with ID {tracker_id} not found"
            )

        tracker.status = status
        if msg is not None:
            tracker.msg = msg

        db.commit()
        db.refresh(tracker)

        return DatabaseResult.success_result(
            data=tracker,
            message=f"Tracker status updated to '{status}' successfully",
            affected_rows=1
        )
    except Exception as e:
        db.rollback()
        return DatabaseResult.database_error_result(
            message=f"Failed to update tracker status: {str(e)}"
        )


def delete_tracker(db: Session, tracker_id: str) -> DatabaseResult[None]:
    """
    Soft delete tracker with standardized return format

    Args:
        db: Database session
        tracker_id: Tracker ID

    Returns:
        DatabaseResult indicating success or failure
    """
    try:
        tracker = db.query(TrackerInfo).filter(TrackerInfo.id_ == tracker_id).first()
        if not tracker:
            return DatabaseResult.not_found_result(
                message=f"Tracker with ID {tracker_id} not found"
            )

        # Soft delete by setting dr to 0 (assuming dr field exists)
        if hasattr(tracker, 'dr'):
            tracker.dr = 0
        else:
            # If no dr field, do hard delete
            db.delete(tracker)

        db.commit()

        return DatabaseResult.success_result(
            message="Tracker deleted successfully",
            affected_rows=1
        )
    except Exception as e:
        db.rollback()
        return DatabaseResult.database_error_result(
            message=f"Failed to delete tracker: {str(e)}"
        )


def hard_delete_tracker(db: Session, tracker_id: str) -> DatabaseResult[None]:
    """
    Hard delete tracker with standardized return format

    Args:
        db: Database session
        tracker_id: Tracker ID

    Returns:
        DatabaseResult indicating success or failure
    """
    try:
        tracker = db.query(TrackerInfo).filter(TrackerInfo.id_ == tracker_id).first()
        if not tracker:
            return DatabaseResult.not_found_result(
                message=f"Tracker with ID {tracker_id} not found"
            )

        db.delete(tracker)
        db.commit()

        return DatabaseResult.success_result(
            message="Tracker hard deleted successfully",
            affected_rows=1
        )
    except Exception as e:
        db.rollback()
        return DatabaseResult.database_error_result(
            message=f"Failed to hard delete tracker: {str(e)}"
        )


def delete_trackers_by_torrent(db: Session, torrent_info_id: str) -> DatabaseResult[int]:
    """
    Delete all trackers for a torrent with standardized return format

    Args:
        db: Database session
        torrent_info_id: Torrent info ID

    Returns:
        DatabaseResult containing the number of deleted trackers
    """
    try:
        trackers = db.query(TrackerInfo).filter(TrackerInfo.torrent_info_id == torrent_info_id).all()

        if not trackers:
            return DatabaseResult.not_found_result(
                message=f"No trackers found for torrent {torrent_info_id}"
            )

        deleted_count = 0
        for tracker in trackers:
            if hasattr(tracker, 'dr'):
                tracker.dr = 0
            else:
                db.delete(tracker)
            deleted_count += 1

        db.commit()

        return DatabaseResult.success_result(
            data=deleted_count,
            message=f"Deleted {deleted_count} trackers for torrent {torrent_info_id}",
            affected_rows=deleted_count
        )
    except Exception as e:
        db.rollback()
        return DatabaseResult.database_error_result(
            message=f"Failed to delete trackers by torrent: {str(e)}"
        )