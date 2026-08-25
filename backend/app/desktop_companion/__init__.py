# -*- coding: utf-8 -*-
"""桌面伴侣模式支持包（dual-mode-client task .6 桌面双模式对齐）。

与安卓端 com.btdeck.companion 包语义对齐：
- hosts/lan_policy：URL 解析与明文准入（字面量私有 LAN 判定，fail-closed）；
- profiles：服务器 profile 模型与 JSON 持久化（字段与安卓 ServerProfile 一致，
  桌面端不做自签证书指纹信任——内嵌 WebView 的证书 UX 由渲染引擎承载，
  健康检查仍单独归类 TLS_ERROR）；
- health：/health/live → /health/ready 链式探测与五态分类；
- launcher：模式选择向导 + 服务器管理页 + 远程窗口控制器（pywebview）。
"""
