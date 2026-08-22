# Review: fix range 5c5c167..43ea122

Reviewed commands:

- `git log --oneline -5`
- `git diff HEAD~5..HEAD --stat`
- `git diff HEAD~5..HEAD`

## Findings

1. **C2 partial gap: non-template advanced search paths still pass raw `user_info.user_id`.**
   `backend/app/api/endpoints/advanced_search.py` applies `str(user_info.user_id)` consistently to search template create/list/update/delete/apply paths, so the template ownership fix is covered. The non-template paths still pass the raw value to service methods:
   - `advanced_search_torrents()` -> `service.search_torrents(request, user_info.user_id)`
   - `batch_delete_torrents()` -> `service.delete_torrents_batch(request, user_info.user_id)`
   - `preview_advanced_search()` -> `service.search_torrents(search_request, user_info.user_id)`

   This is not a current template permission regression because those service methods only log/pass through `user_id`, but it means C2 is not literally true for all advanced search code paths.

2. **W3 remaining exception swallowing is still present in `backend/app/services/advanced_search.py`.**
   The endpoint-level `try/except Exception` wrappers were removed from `backend/app/api/endpoints/advanced_search.py`, which is correct for global error handling. However the service still catches broad exceptions and returns fallback values in several places, including `SearchTemplateModel.get_by_user()`, `get_by_id()`, `update()`, `delete()`, `increment_usage()`, and `AdvancedSearchService.search_torrents()`. If W3 meant endpoint-only behavior, it is fixed. If it meant the advanced search module as a whole, exception swallowing remains.

## Checks

- **C1 downloader_settings auth migration:** The five settings endpoints now include `Depends(require_authenticated_user)`. No `x-access-token`, `verify_access_token`, or local `get_current_user_id()` references remain in `backend/app/api/endpoints/downloader_settings.py`.
- **C2 search template `str(user_id)`:** Create/list/update/delete/apply template paths use string IDs. Permission comparisons now work for JWT int `1` vs DB string `"1"`.
- **C3 list ignores client `user_id`:** `GET /advanced-search/search-templates` accepts the query as deprecated input, logs mismatches, and always passes `str(user_info.user_id)` to the service. Other user-id accepting endpoints exist elsewhere, mostly user-management path parameters and setting template internals, but no other search template client `user_id` path remains.
- **C4 empty payload guard:** The guard exists in both the endpoint and `TaskLogsCRUD.cleanup_task_logs()`. Negative `days` is rejected in both places.
- **W1 Path import:** `from pathlib import Path` is correctly placed before the fallback path use in `backend/alembic/env.py`.
- **W4 frontend pagination fields:** Advanced search TypeScript response now uses `list/pageSize`, and `frontend/src/views/torrents/index.vue` reads `response.data.list`. No remaining `response.data.data`, `limit`, or `total_pages` references were found for the advanced search response path.

## Test Additions

Added regression tests:

- `backend/tests/api/test_downloader_settings_auth.py`
- `backend/tests/api/test_search_template_permissions.py`
- `backend/tests/api/test_cron_task_cleanup.py`
- `backend/tests/api/test_advanced_search_pagination.py`
