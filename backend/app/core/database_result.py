"""
Standardized database operation results module

This module provides a unified return format for all database operations in the btpmanager application.
It ensures consistency across all database functions and improves error handling and debugging capabilities.
"""

from typing import Generic, TypeVar, Optional, Any, List, Union
from dataclasses import dataclass
from enum import Enum

# Generic type variable for different model types
T = TypeVar('T')


class DatabaseError(Enum):
    """Standardized error codes for database operations"""
    SUCCESS = "SUCCESS"
    NOT_FOUND = "NOT_FOUND"
    DUPLICATE_KEY = "DUPLICATE_KEY"
    VALIDATION_ERROR = "VALIDATION_ERROR"
    DATABASE_ERROR = "DATABASE_ERROR"
    FOREIGN_KEY_CONSTRAINT = "FOREIGN_KEY_CONSTRAINT"
    UNKNOWN_ERROR = "UNKNOWN_ERROR"


@dataclass
class DatabaseResult(Generic[T]):
    """
    Standardized return format for all database operations

    Attributes:
        success (bool): Operation success status
        data (Optional[T]): Return data (model object, list, or primitive)
        message (str): Descriptive message about the operation
        error_code (Optional[str]): Error code for failures
        affected_rows (int): Number of affected rows (for insert/update/delete operations)
        total_count (Optional[int]): Total count (for query operations)
    """
    success: bool
    data: Optional[T] = None
    message: str = ""
    error_code: Optional[str] = None
    affected_rows: int = 0
    total_count: Optional[int] = None

    @classmethod
    def success_result(cls,
                      data: Optional[T] = None,
                      message: str = "Operation completed successfully",
                      affected_rows: int = 0,
                      total_count: Optional[int] = None) -> 'DatabaseResult[T]':
        """
        Create a successful database result

        Args:
            data: The result data
            message: Success message
            affected_rows: Number of rows affected
            total_count: Total count for queries

        Returns:
            DatabaseResult with success=True
        """
        return cls(
            success=True,
            data=data,
            message=message,
            error_code=DatabaseError.SUCCESS.value,
            affected_rows=affected_rows,
            total_count=total_count
        )

    @classmethod
    def failure_result(cls,
                      message: str,
                      error_code: DatabaseError = DatabaseError.UNKNOWN_ERROR,
                      data: Optional[T] = None) -> 'DatabaseResult[T]':
        """
        Create a failure database result

        Args:
            message: Error message
            error_code: Error code from DatabaseError enum
            data: Any partial data that might be useful

        Returns:
            DatabaseResult with success=False
        """
        return cls(
            success=False,
            data=data,
            message=message,
            error_code=error_code.value,
            affected_rows=0
        )

    @classmethod
    def not_found_result(cls, message: str = "Record not found") -> 'DatabaseResult[T]':
        """
        Create a not found result

        Args:
            message: Not found message

        Returns:
            DatabaseResult indicating record not found
        """
        return cls.failure_result(message, DatabaseError.NOT_FOUND)

    @classmethod
    def validation_error_result(cls, message: str) -> 'DatabaseResult[T]':
        """
        Create a validation error result

        Args:
            message: Validation error message

        Returns:
            DatabaseResult indicating validation error
        """
        return cls.failure_result(message, DatabaseError.VALIDATION_ERROR)

    @classmethod
    def database_error_result(cls, message: str) -> 'DatabaseResult[T]':
        """
        Create a database error result

        Args:
            message: Database error message

        Returns:
            DatabaseResult indicating database error
        """
        return cls.failure_result(message, DatabaseError.DATABASE_ERROR)

    def to_dict(self) -> dict:
        """
        Convert the result to a dictionary for JSON serialization

        Returns:
            Dictionary representation of the result
        """
        return {
            "success": self.success,
            "data": self.data,
            "message": self.message,
            "error_code": self.error_code,
            "affected_rows": self.affected_rows,
            "total_count": self.total_count
        }