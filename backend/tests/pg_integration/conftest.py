"""pg_integration 共享 fixture 再导出。

``fresh_pg_db``/``_make_cfg`` 实体定义在 test_pg_smoke.py（v1.0.8 任务4.3 原始交付），
经 conftest 再导出供本目录新增用例（test_pg_endpoints.py 等）自动发现，
避免用例文件直接 import 与同名 fixture 参数产生 F401/F811。
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from test_pg_smoke import _make_cfg, fresh_pg_db  # noqa: F401  (pytest fixture 再导出)
