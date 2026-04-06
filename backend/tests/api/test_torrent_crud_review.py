# -*- coding: utf-8 -*-
"""
代码审查回归测试 — torrent_crud.py 边界场景

测试范围:
- C1: get_torrent_info 参数数量不匹配
"""

import pytest
import inspect
from unittest.mock import MagicMock


class TestGetTorrentInfoParams:
    """C1: get_torrent_info 定义3个参数，调用处传了4个"""

    def test_signature_has_three_params(self):
        """get_torrent_info 应该只接受 (db, info_id, downloader_id) 三个参数"""
        from app.services.torrent_crud_service import get_torrent_info

        sig = inspect.signature(get_torrent_info)
        params = list(sig.parameters.keys())
        assert params == ['db', 'info_id', 'downloader_id'], \
            f"参数列表应为 ['db', 'info_id', 'downloader_id']，实际为 {params}"

    def test_call_with_extra_param_raises_type_error(self):
        """调用时传第4个参数应抛出 TypeError"""
        from app.services.torrent_crud_service import get_torrent_info

        db = MagicMock()
        # 传4个参数（当前 bug 状态：定义只接受3个）
        with pytest.raises(TypeError):
            get_torrent_info(db, "info-001", "dl-001", "extra_name")

    def test_torrent_crud_call_site_passes_three_args(self):
        """
        验证 torrent_crud.py 中 get_torrent 端点的调用处传参数量正确
        通过静态分析调用行确认
        """
        import app.api.endpoints.torrent_crud as crud_mod
        source = inspect.getsource(crud_mod)
        lines = source.split('\n')

        # 找到 get_torrent_info 的调用行
        for i, line in enumerate(lines):
            if 'get_torrent_info(' in line and 'def ' not in line and 'import' not in line:
                # 计算逗号数量来确定参数数量
                inner = line[line.index('get_torrent_info(') + len('get_torrent_info('):]
                inner = inner[:inner.index(')')]
                commas = inner.count(',')
                # 3个参数 = 2个逗号
                assert commas == 2, \
                    f"C1 BUG at line {i+1}: get_torrent_info 传了 {commas+1} 个参数，应为 3 个。代码: {line.strip()}"
