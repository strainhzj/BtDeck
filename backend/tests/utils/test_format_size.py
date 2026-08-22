# -*- coding: utf-8 -*-
"""
format_size 字节大小格式化工具单元测试

测试 app/utils/format_size.py 的 format_size：
- 自动选最近单位（值落在 [1, 1024)）
- 2 位小数
- 单位序列 B/KB/MB/GB/TB/PB，达到 PB 后不再升单位
- 0 / 负数 / 大数边界
"""

from app.utils.format_size import format_size


class TestFormatSize:
    def test_zero_returns_bytes(self) -> None:
        assert format_size(0) == "0 B"

    def test_one_byte(self) -> None:
        assert format_size(1) == "1.00 B"

    def test_sub_kib_stays_bytes(self) -> None:
        assert format_size(1023) == "1023.00 B"

    def test_kib_boundary(self) -> None:
        assert format_size(1024) == "1.00 KB"

    def test_mib_boundary(self) -> None:
        assert format_size(1024 * 1024) == "1.00 MB"

    def test_gib_value_two_decimals(self) -> None:
        # 用户原始诉求示例：57286409241 字节 -> 53.35 GB
        assert format_size(57286409241) == "53.35 GB"

    def test_tib_boundary(self) -> None:
        assert format_size(1024**4) == "1.00 TB"

    def test_pib_boundary(self) -> None:
        assert format_size(1024**5) == "1.00 PB"

    def test_above_pib_does_not_promote(self) -> None:
        # 超过 PB 后单位不再升，仍以 PB 展示
        assert format_size(1024**6) == "1024.00 PB"

    def test_negative_returns_bytes(self) -> None:
        assert format_size(-1) == "0 B"
        assert format_size(-100) == "0 B"

    def test_user_example_release_space(self) -> None:
        """回归保护：用户报告的『释放空间：57286409241 字节』应展示为 53.35 GB。"""
        assert format_size(57286409241) == "53.35 GB"
