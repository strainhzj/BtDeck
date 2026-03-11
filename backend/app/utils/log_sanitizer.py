# -*- coding: utf-8 -*-
"""
日志脱敏工具

用于在日志中屏蔽敏感信息（IP、用户名、密码等）
"""
import re
from typing import Any

# IP地址正则表达式
IP_PATTERN = re.compile(
    r'\b(?:\d{1,3}\.){3}\d{1,3}\b'
)

# 用户名常见模式（邮箱、简单用户名）
USERNAME_PATTERN = re.compile(
    r'(username|user|account)[=:\s]+([^\s,\'"}]+)',
    re.IGNORECASE
)


def sanitize_ip(ip: str) -> str:
    """脱敏IP地址
    
    Args:
        ip: IP地址字符串
        
    Returns:
        str: 脱敏后的IP（如：192.168.1.***）
    """
    if not ip:
        return "***"
    
    match = IP_PATTERN.match(ip.strip())
    if match:
        parts = ip.split('.')
        if len(parts) == 4:
            # 保留前3段，隐藏最后一段
            return f"{parts[0]}.{parts[1]}.{parts[2]}.***"
    
    return "***"


def sanitize_username(username: str) -> str:
    """脱敏用户名
    
    Args:
        username: 用户名
        
    Returns:
        str: 脱敏后的用户名（只显示首尾字符）
    """
    if not username or len(username) <= 2:
        return "***"
    
    return f"{username[0]}***{username[-1]}"


def sanitize_log_message(message: str) -> str:
    """脱敏日志消息
    
    Args:
        message: 原始日志消息
        
    Returns:
        str: 脱敏后的日志消息
    """
    if not message:
        return message
    
    # 脱敏IP地址
    sanitized = IP_PATTERN.sub(
        lambda m: sanitize_ip(m.group()),
        message
    )
    
    # 脱敏用户名
    sanitized = USERNAME_PATTERN.sub(
        lambda m: f"{m.group(1)}=***",
        sanitized
    )
    
    return sanitized


def format_connection_log(
    nickname: str,
    host: str,
    port: Any,
    sanitize: bool = True
) -> str:
    """格式化连接日志（可选脱敏）
    
    Args:
        nickname: 下载器昵称
        host: 主机地址
        port: 端口
        sanitize: 是否脱敏（默认True，生产环境建议开启）
        
    Returns:
        str: 格式化的日志字符串
    """
    if sanitize:
        host_display = sanitize_ip(host)
    else:
        host_display = host
    
    return f"{nickname} ({host_display}:{port})"


# 生产环境配置（可通过环境变量控制）
PRODUCTION_MODE = False  # 默认关闭脱敏，开发环境可看到完整信息


def should_sanitize() -> bool:
    """判断当前环境是否需要脱敏
    
    Returns:
        bool: 生产环境返回True
    """
    return PRODUCTION_MODE


__all__ = [
    'sanitize_ip',
    'sanitize_username',
    'sanitize_log_message',
    'format_connection_log',
    'should_sanitize',
    'PRODUCTION_MODE',
]
