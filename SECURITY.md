# 安全策略

## 支持范围

本项目处于 0.x 阶段，安全修复只针对最新发布版本，不承诺向旧版本 backport。

## 报告漏洞

请**不要**开公开 issue 披露漏洞细节，按以下方式私下报告：

- GitHub Security Advisory：<https://github.com/mcocdaa/python-alimail/security/advisories/new>
- 报告中请包含：受影响版本、复现步骤、最小示例、影响评估。
- 示例里请用占位符代替真实凭据、域名、邮箱；不要附带真实 token 或邮件内容。
- 维护者会尽力在 3 个工作日内确认，修复后发布安全公告并致谢（可选择匿名）。

## 凭据安全

本项目不负责存储凭据，安全责任在部署方：

| 做法 | 说明 |
|---|---|
| ✅ 环境变量 / secret 管理 | 凭据只通过环境变量、平台 secret manager 或受控配置文件提供 |
| ✅ 最小权限 | 按 [docs/permissions.md](docs/permissions.md) 只勾需要的 scope；读写分离 |
| ✅ 权限收紧 | 凭据文件限制为当前用户可读（Linux/macOS：`chmod 600`） |
| ✅ 保护 token 缓存 | SDK 的 token 缓存（Windows `%LOCALAPPDATA%\alimail\token-cache.json`，其他系统 `~/.cache/alimail/token-cache.json`）含 access token，不要提交或外传 |
| ✅ 及时轮换 | Secret / MCP token 定期更换，离职或交接后立即重置 |
| ❌ 提交到仓库 | `.gitignore` 已忽略 `alimail_creds.json`、`.env`，提交前仍请 `git status` 复核 |
| ❌ 写进代码或文档 | 不要在源码、示例、issue、聊天记录里粘贴真实凭据 |
| ❌ 长期用 `--app-secret` | 命令行参数会进 shell history 和进程列表，优先用环境变量或凭据文件 |
| ❌ 打印到日志 | 不要记录 `Authorization` 头、token、Secret、邮件正文、收件人列表 |

## 凭据泄露处置

Secret 或 MCP token 泄露约等于邮箱被接管。按顺序处理：

1. **立即重置**：在邮箱管理后台重置应用 Secret；MCP token 泄露则在 Webmail 里撤销并重新生成。
2. **更新部署**：替换所有本机、服务器、CI/CD 中的旧值，确认旧值已全部下线。
3. **审计**：拉取审计日志（需要 `Report.Read.All`，对应 `POST /v2/reports`），检查登录、发信、
   规则变更记录，确认泄露期间没有异常操作。
4. **验证**：用新凭据跑 `alimail token` 和 `alimail check`，确认鉴权与权限正常。
5. **上报**：如涉及真实用户数据或业务损失，按组织内部安全流程上报。
6. **清理副本**：删除聊天记录、日志、临时文件中的泄露副本；不要继续复用同一 Secret。

## 已知安全边界

- 这是**非官方**项目，上游服务（阿里邮箱）的安全由服务提供方负责。
- 接口权限由邮箱管理后台的 scope 控制，本项目无法绕过；`403` 是预期行为，不是漏洞。
- 示例脚本仅用于演示，请勿直接拿去跑生产批量操作；发送、删除、释放隔离区等操作不可逆。
- 项目零运行时依赖（纯标准库），dev 依赖仅用于开发（见 `pyproject.toml`）。
- 调用真实租户前，先在测试租户验证；批量写操作前二次确认目标。
