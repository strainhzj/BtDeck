# -*- coding: utf-8 -*-
"""登录失败限流（进程内实现，安全修复 W9）。

约束与设计：
- WORKERS=1 是项目文档化约束（docker-compose 注释明确禁止多 Worker），
  进程内计数即全局有效；若未来放开多 Worker，必须换共享存储实现。
- 键：username + request.client.host（直连对端）。绝不信任 X-Forwarded-For：
  uvicorn 未配置 proxy-headers 信任（nginx 容器非 127.0.0.1），放开即引入
  伪造 IP 绕过。反代部署下所有请求的 client.host 相同（网关 IP），键实际
  退化为 username 维度。
- 阶梯锁定：5 次失败锁 15 分钟，累计 10 次锁 1 小时（封顶 1 小时——
  缓解攻击者蓄意锁死管理员账号的 DoS 面，管理员最长 1 小时可恢复）。
- 锁定响应不带剩余时间（防止攻击者精确续锁）。
- 密码错误与 TOTP 验证码错误共用同一计数（2FA 6 位数字空间小，
  单独不限流等于可爆破）。
"""

import threading
import time

# 阶梯阈值与锁定时长（秒）
_THRESHOLD_15M = 5
_THRESHOLD_1H = 10
_WINDOW_15M = 15 * 60
_LOCK_15M = 15 * 60
_LOCK_1H = 60 * 60


class LoginThrottle:
    """线程安全的登录失败计数与阶梯锁定。"""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._failures: dict = {}  # key -> 近 1 小时失败时间戳列表
        self._locked_until: dict = {}  # key -> 锁定截止时间戳

    @staticmethod
    def _key(username: str, ip: str) -> str:
        return f"{(username or '').lower()}|{ip or ''}"

    def check_locked(self, username: str, ip: str) -> bool:
        """当前键是否处于锁定期。"""
        now = time.monotonic()
        with self._lock:
            until = self._locked_until.get(self._key(username, ip))
            return bool(until and until > now)

    def record_failure(self, username: str, ip: str) -> None:
        """记录一次失败，按阶梯阈值升级锁定期。"""
        now = time.monotonic()
        key = self._key(username, ip)
        with self._lock:
            fails = [t for t in self._failures.get(key, []) if now - t < _LOCK_1H]
            fails.append(now)
            self._failures[key] = fails
            if len(fails) >= _THRESHOLD_1H:
                self._locked_until[key] = now + _LOCK_1H
            elif len(fails) >= _THRESHOLD_15M:
                self._locked_until[key] = now + _LOCK_15M

    def record_success(self, username: str, ip: str) -> None:
        """登录成功清零该键的失败记录。"""
        key = self._key(username, ip)
        with self._lock:
            self._failures.pop(key, None)
            self._locked_until.pop(key, None)


# 模块级单例（login 端点是同步 def 跑线程池，必须加锁）
login_throttle = LoginThrottle()
