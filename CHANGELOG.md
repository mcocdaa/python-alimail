# Changelog

本文件格式参考 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)，
版本号遵循 [语义化版本](https://semver.org/lang/zh-CN/)。

## [Unreleased]

## [0.1.0] - 2026-11-12

首个公开版本。非官方项目，与阿里云 / 阿里邮箱无关联。

### Added

- `Client` 同步客户端：支持企业应用 `app_id` / `app_secret`（OAuth2 `client_credentials`）
  与个人 MCP token 两种鉴权模式。
- 凭据解析顺序：构造参数 → 环境变量 → `./alimail_creds.json` → `~/.alimail/creds.json` →
  MCP 账号文件（Windows `%APPDATA%\Alimail\accounts.json`，其他系统 `~/.alimail/accounts.json`）。
- token 缓存与自动续期；业务请求返回 401 时刷新 token 并重试一次。
- Host 自动回退：默认 `alimail-cn.aliyuncs.com`，获取 token 失败时自动尝试
  `alimail-sg.aliyuncs.com`。
- 类型化异常：`APIError` 及其子类 `AuthError`、`PermissionDenied`、`NotFound`、
  `RateLimitError`、`ServerError`（统一携带 `status`、`detail_error_code`、
  `message`、`developer_message`）；网络层失败抛 `TransportError`，凭据缺失抛 `ConfigError`。
- 分页支持：`Client.paginate` 迭代器，以及响应中的 `hasMore` / `nextCursor`。
- 底层方法：`Client.token`、`Client.request`、`Client.raw`、`Client.call`（按 operation 名调用）。
- 资源封装：邮件（文件夹、草稿、搜索、详情、附件、批量删除）、用户、日历、组织、域名、
  部门、邮件组、公共联系人、隔离区、收信黑白名单、审计日志、文件流（分片上传）。
- CLI（`alimail`）：`token`、`org`、`users`、`folders`、`inbox`、`read`、`search`、`send`、
  `check`、`call`、`ops`、`raw`，以及 `--app-id`、`--app-secret`、`--base`、`--timeout` 全局参数。
- 权限自检：`alimail check` 依次调用只读接口，输出 ✅/❌ scope 矩阵，便于在管理员调整权限后复核。
- operations 注册表：`alimail ops list`、`alimail ops show <operation-name>`，配合 `alimail call`
  按 operation 名调用接口。
- 示例：`examples/list_users.py`、`examples/read_inbox.py`、`examples/send_mail.py`
  （发信示例默认 dry-run，需显式设置环境变量才会真正发送）。
- 文档：README、快速开始、权限说明、真实踩坑合集、贡献指南、安全策略。
- 测试与 CI：离线单元测试（mock HTTP）和 GitHub Actions 工作流（ruff + 测试）。

[Unreleased]: https://github.com/mcocdaa/python-alimail/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/mcocdaa/python-alimail/releases/tag/v0.1.0
