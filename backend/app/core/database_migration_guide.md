# Database Operations Migration Guide

This guide provides comprehensive instructions for migrating existing database operations to use the new standardized `DatabaseResult` return format.

## Overview

The btpmanager project has been refactored to use a standardized return format for all database operations. This ensures consistency across the application and improves error handling.

## New Standardized Format

All database operations now return a `DatabaseResult[T]` object with the following structure:

```python
@dataclass
class DatabaseResult(Generic[T]):
    success: bool                    # Operation success status
    data: Optional[T] = None        # Return data (model object, list, or primitive)
    message: str = ""               # Descriptive message
    error_code: Optional[str] = None  # Error code for failures
    affected_rows: int = 0          # Number of affected rows (for insert/update/delete)
    total_count: Optional[int] = None  # Total count (for query operations)
```

## Migration Steps

### 1. Import Standardized Operations

Replace old direct database imports with new standardized operation modules:

**Before:**
```python
from app.api.endpoints.torrents import create_torrent, get_torrent, update_torrent
```

**After:**
```python
from app.core.torrent_operations import create_torrent, get_torrent, update_torrent
from app.core.tracker_operations import create_tracker, get_tracker
```

### 2. Update Function Calls

Update function calls to handle the new `DatabaseResult` return format:

**Before:**
```python
def some_function(db: Session):
    torrent = get_torrent(db, torrent_id)
    if torrent:
        # Process torrent
        return process_torrent(torrent)
    else:
        return None
```

**After:**
```python
def some_function(db: Session):
    result = get_torrent(db, torrent_id)
    if result.success and result.data:
        # Process torrent
        return process_torrent(result.data)
    else:
        # Handle error/not found
        logger.error(f"Failed to get torrent: {result.message}")
        return None
```

### 3. Handle Different Return Patterns

#### For Single Record Operations:
```python
result = get_torrent(db, torrent_id)
if result.success:
    torrent = result.data
    # Use torrent
else:
    # Handle error
    if result.error_code == "NOT_FOUND":
        # Handle not found case
    else:
        # Handle other errors
```

#### For List Operations:
```python
result = search_torrents_by_name(db, query)
if result.success:
    torrents = result.data
    total_count = result.total_count
    # Use torrents list and count
else:
    # Handle error
```

#### For Create/Update/Delete Operations:
```python
result = create_torrent(db, torrent_data)
if result.success:
    created_torrent = result.data
    affected_rows = result.affected_rows
    # Use created_torrent
else:
    # Handle error
    logger.error(f"Failed to create torrent: {result.message}")
```

## Updated Function Locations

### Core Functions (Updated)
- **Downloader Operations**: `app/core/downloader.py`
  - `getDownloaders()` - Now returns `DatabaseResult[List[BtDownloaders]]`

### Torrent Operations (New Module)
- **Torrent Operations**: `app/core/torrent_operations.py`
  - `create_torrent()` - Returns `DatabaseResult[TorrentInfo]`
  - `get_torrent()` - Returns `DatabaseResult[TorrentInfo]`
  - `get_torrent_by_hash()` - Returns `DatabaseResult[TorrentInfo]`
  - `search_torrents_by_name()` - Returns `DatabaseResult[List[TorrentInfo]]`
  - `update_torrent()` - Returns `DatabaseResult[TorrentInfo]`
  - `delete_torrent()` - Returns `DatabaseResult[None]`
  - `get_torrents_by_save_path()` - Returns `DatabaseResult[List[TorrentInfo]]`
  - `get_torrents_count()` - Returns `DatabaseResult[int]`

### Tracker Operations (New Module)
- **Tracker Operations**: `app/core/tracker_operations.py`
  - `create_tracker()` - Returns `DatabaseResult[TrackerInfo]`
  - `get_tracker()` - Returns `DatabaseResult[TrackerInfo]`
  - `get_trackers_by_torrent()` - Returns `DatabaseResult[List[TrackerInfo]]`
  - `get_trackers()` - Returns `DatabaseResult[List[TrackerInfo]]`
  - `get_trackers_by_status()` - Returns `DatabaseResult[List[TrackerInfo]]`
  - `update_tracker()` - Returns `DatabaseResult[TrackerInfo]`
  - `update_tracker_status()` - Returns `DatabaseResult[TrackerInfo]`
  - `delete_tracker()` - Returns `DatabaseResult[None]`
  - `hard_delete_tracker()` - Returns `DatabaseResult[None]`
  - `delete_trackers_by_torrent()` - Returns `DatabaseResult[int]`

## Error Code Reference

### Standard Error Codes:
- `SUCCESS` - Operation completed successfully
- `NOT_FOUND` - Requested record was not found
- `DUPLICATE_KEY` - Attempt to insert duplicate record
- `VALIDATION_ERROR` - Input validation failed
- `DATABASE_ERROR` - Database operation failed
- `FOREIGN_KEY_CONSTRAINT` - Foreign key constraint violation
- `UNKNOWN_ERROR` - Unexpected error occurred

## Migration Checklist

### For Each Function:
- [ ] Update import statements to use new standardized operation modules
- [ ] Update function calls to handle `DatabaseResult` return type
- [ ] Add proper error handling for `success` flag
- [ ] Update response processing to use `result.data`
- [ ] Add logging for error messages using `result.message`
- [ ] Update unit tests to validate new return format

### For API Endpoints:
- [ ] Update endpoint logic to use new database operations
- [ ] Convert `DatabaseResult` to appropriate `CommonResponse` format
- [ ] Ensure proper HTTP status codes based on operation results
- [ ] Add error message handling for API responses

## Benefits of Migration

1. **Consistency**: All database operations return the same format
2. **Better Error Handling**: Standardized error codes and messages
3. **Improved Debugging**: Clear success/failure indicators
4. **Enhanced Logging**: Structured error information
5. **Maintainability**: Easier to maintain and extend database operations
6. **Testing**: Easier to write comprehensive tests

## Example: Complete Migration

### Original Code:
```python
def get_user_torrents(db: Session, user_id: str):
    try:
        torrents = db.query(TorrentInfo).filter(TorrentInfo.user_id == user_id).all()
        return torrents
    except Exception as e:
        return None
```

### Migrated Code:
```python
from app.core.torrent_operations import search_torrents_by_name

def get_user_torrents(db: Session, user_id: str):
    try:
        result = search_torrents_by_name(db, "", skip=0, limit=1000)
        if result.success:
            # Filter by user_id since we don't have that specific function yet
            user_torrents = [t for t in result.data if t.user_id == user_id]
            return user_torrents
        else:
            logger.error(f"Failed to get user torrents: {result.message}")
            return []
    except Exception as e:
        logger.error(f"Unexpected error getting user torrents: {str(e)}")
        return []
```

## Testing

After migration, ensure all functions:
1. Return proper `DatabaseResult` objects
2. Handle success and failure cases correctly
3. Provide meaningful error messages
4. Maintain existing functionality

Use the provided test scripts to validate the migration.