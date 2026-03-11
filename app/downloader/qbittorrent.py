from qbittorrentapi import Client

def initialQb():
    """
    初始化qBittorrent客户端连接（示例代码）

    ⚠️ 安全警告：请勿在代码中硬编码密码！
    应该从以下方式读取配置：
    1. 环境变量
    2. 配置文件（如 config.ini, .env）
    3. 密钥管理服务

    示例：
    ```python
    import os
    from app.core.config import settings

    client = Client(
        host=settings.QBITTORRENT_HOST,
        username=settings.QBITTORRENT_USER,
        password=settings.QBITTORRENT_PASSWORD
    )
    ```
    """
    i = 0
    # TODO: 从配置文件或环境变量读取连接信息
    # client = Client(
    #     host=os.getenv("QBITTORRENT_HOST", "localhost"),
    #     username=os.getenv("QBITTORRENT_USER", "admin"),
    #     password=os.getenv("QBITTORRENT_PASSWORD")
    # )

    # while i<1:
    #     client = Client(host="ncqb3.btpmanager.top", username="huangzj", password="YOUR_PASSWORD_HERE")
    #     client2 = Client(host="ncqb3.btpmanager.top", username="huangzj", password="YOUR_PASSWORD_HERE")
    #     d1 = {"ncqb3": client}
    #     d2 = {"ncqb4": client2}
    #     i = i + 1
    #     d3 = d1.update(d2)

    return {}  # 返回空字典，避免导入时执行连接

# ⚠️ 不要在模块级别执行初始化
# qblist = initialQb()
