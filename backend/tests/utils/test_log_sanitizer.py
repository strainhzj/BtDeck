"""
日志脱敏工具单元测试

测试 app/utils/log_sanitizer.py 中的函数：
- sanitize_ip: IP 地址脱敏
- sanitize_username: 用户名脱敏
- sanitize_log_message: 日志消息脱敏
- format_connection_log: 连接日志格式化
- should_sanitize: 环境判断
"""

import pytest
from app.utils.log_sanitizer import (
    sanitize_ip,
    sanitize_username,
    sanitize_log_message,
    format_connection_log,
    should_sanitize,
)


class TestSanitizeIp:
    """IP 地址脱敏测试"""

    def test_normal_ipv4(self):
        """标准 IPv4 地址应隐藏最后一段"""
        assert sanitize_ip("192.168.1.100") == "192.168.1.***"

    def test_localhost(self):
        """127.0.0.1 应正确脱敏"""
        assert sanitize_ip("127.0.0.1") == "127.0.0.***"

    def test_all_zeros(self):
        """0.0.0.0 应正确脱敏"""
        assert sanitize_ip("0.0.0.0") == "0.0.0.***"

    def test_empty_string(self):
        """空字符串应返回 ***"""
        assert sanitize_ip("") == "***"

    def test_none_input(self):
        """None 输入应返回 ***"""
        assert sanitize_ip(None) == "***"

    def test_non_ip_text(self):
        """非 IP 文本应返回 ***"""
        assert sanitize_ip("not-an-ip") == "***"

    def test_ip_with_spaces(self):
        """带空格的 IP 应保留前导空格（split 按原始字符串拆分）"""
        result = sanitize_ip("  10.0.0.1  ")
        assert "10.0.0.***" in result

    def test_partial_ip(self):
        """不完整的 IP 应返回 ***"""
        assert sanitize_ip("192.168.1") == "***"


class TestSanitizeUsername:
    """用户名脱敏测试"""

    def test_normal_username(self):
        """普通用户名应保留首尾字符"""
        assert sanitize_username("admin") == "a***n"

    def test_short_username_two_chars(self):
        """两个字符的用户名应返回 ***"""
        assert sanitize_username("ab") == "***"

    def test_single_char(self):
        """单字符用户名应返回 ***"""
        assert sanitize_username("a") == "***"

    def test_empty_string(self):
        """空字符串应返回 ***"""
        assert sanitize_username("") == "***"

    def test_none_input(self):
        """None 输入应返回 ***"""
        assert sanitize_username(None) == "***"

    def test_three_chars(self):
        """三个字符的用户名应保留首尾"""
        assert sanitize_username("abc") == "a***c"

    def test_long_username(self):
        """长用户名应保留首尾"""
        assert sanitize_username("administrator") == "a***r"

    def test_chinese_username(self):
        """中文用户名应保留首尾"""
        assert sanitize_username("测试用户") == "测***户"


class TestSanitizeLogMessage:
    """日志消息脱敏测试"""

    def test_sanitize_ip_in_message(self):
        """消息中的 IP 应被脱敏"""
        msg = "用户从 192.168.1.100 登录"
        result = sanitize_log_message(msg)
        assert "192.168.1.***" in result
        assert "192.168.1.100" not in result

    def test_sanitize_username_in_message(self):
        """消息中的用户名键值对应被脱敏"""
        msg = "login username=admin123 failed"
        result = sanitize_log_message(msg)
        assert "username=***" in result

    def test_sanitize_user_in_message(self):
        """消息中的 user 键值对应被脱敏"""
        msg = "认证 user=testuser 失败"
        result = sanitize_log_message(msg)
        assert "user=***" in result

    def test_sanitize_account_in_message(self):
        """消息中的 account 键值对应被脱敏"""
        msg = "account=myaccount 登录成功"
        result = sanitize_log_message(msg)
        assert "account=***" in result

    def test_empty_message(self):
        """空消息应返回空"""
        assert sanitize_log_message("") == ""

    def test_none_message(self):
        """None 消息应返回 None"""
        assert sanitize_log_message(None) is None

    def test_no_sensitive_info(self):
        """不含敏感信息的消息应不变"""
        msg = "系统启动成功"
        assert sanitize_log_message(msg) == msg

    def test_multiple_ips_in_message(self):
        """消息中的多个 IP 都应被脱敏"""
        msg = "从 192.168.1.1 连接到 10.0.0.1"
        result = sanitize_log_message(msg)
        assert "192.168.1.***" in result
        assert "10.0.0.***" in result

    def test_combined_ip_and_username(self):
        """同时包含 IP 和用户名的消息应都脱敏"""
        msg = "username=admin 从 192.168.1.100 登录"
        result = sanitize_log_message(msg)
        assert "username=***" in result
        assert "192.168.1.***" in result


class TestFormatConnectionLog:
    """连接日志格式化测试"""

    def test_with_sanitize(self):
        """开启脱敏时应隐藏 IP 最后一段"""
        result = format_connection_log("我的下载器", "192.168.1.100", 8080)
        assert result == "我的下载器 (192.168.1.***:8080)"

    def test_without_sanitize(self):
        """关闭脱敏时应显示完整 IP"""
        result = format_connection_log("我的下载器", "192.168.1.100", 8080, sanitize=False)
        assert result == "我的下载器 (192.168.1.100:8080)"

    def test_default_sanitize_is_true(self):
        """默认应开启脱敏"""
        result = format_connection_log("test", "10.0.0.1", 9090)
        assert "10.0.0.***" in result

    def test_different_port_types(self):
        """端口参数支持多种类型"""
        # 字符串端口
        result = format_connection_log("test", "10.0.0.1", "8080")
        assert ":8080)" in result
        # 整数端口
        result = format_connection_log("test", "10.0.0.1", 8080)
        assert ":8080)" in result


class TestShouldSanitize:
    """环境判断测试"""

    def test_default_returns_false(self):
        """默认（开发环境）应不脱敏"""
        assert should_sanitize() is False
