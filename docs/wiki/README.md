# BtDeck Wiki 内容源

这里维护 BtDeck 面向使用者的 Wiki 内容源。当前基线为 BtDeck v1.0.6（2026-09-21 发布）。中文与英文页面使用相同的相对路径，便于后续同步到独立的 VitePress Wiki 站点。

## 目录

- [中文 Wiki](./zh/index.md)
- [English Wiki](./en/index.md)

## 维护约定

- 面向用户的事实以当前代码、发布配置和实际验证结果为准；路线图中的计划不能写成已支持功能。
- 每次新增或修改中文页面时，在同一变更中更新对应英文页面。
- 命令、环境变量、API 路径和配置键保持原样；产品术语按双语术语表统一。
- 不在 Wiki 中提交密码、密钥、私有地址或临时会话信息。
- 产品版本以 [`release/release-config.json`](../../release/release-config.json) 为唯一输入；内部里程碑编号不等同于产品版本。

## 当前首版范围

首版覆盖项目介绍、快速开始、Docker 与源码部署、核心功能、移动端与 Android 双模式、安全配置、故障排查、版本状态和术语表。API 参考、完整运维手册和逐页截图将在真实部署验证后继续补充。

## 内容来源

- [项目 README](../../README.md) / [English README](../../README_EN.md)
- [Docker Compose](../../docker-compose.yml) 与 [环境变量示例](../../.env.example)
- [Android 客户端说明](../../android/README.md)
- [发布说明](../release/v1.0.6.md)
- [代码路线图](../roadmap/README.md)
