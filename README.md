# python-alimail

[English](README_EN.md) | 简体中文

[![CI](https://github.com/mcocdaa/python-alimail/actions/workflows/ci.yml/badge.svg)](https://github.com/mcocdaa/python-alimail/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/alimail.svg)](https://pypi.org/project/alimail/)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/)

**非官方**的阿里邮箱（Alibaba Mail / 阿里企业邮箱）OpenAPI Python SDK 与 CLI。
零运行时依赖（纯标准库）、覆盖 112 个接口、内置权限自检。

> **非官方声明**
> 本项目是个人开源项目，与阿里云（Alibaba Cloud）及阿里邮箱（Alibaba Mail）**无任何关联**，未获其认证、背书或赞助。
> 所有接口能力与行为以[官方文档](https://mailhelp.aliyun.com/docs/)为准；本项目未使用任何官方 logo 或商标素材。
> 生产环境使用前，请先在测试租户中验证。

---

## 目录

- [特性](#特性)
- [安装](#安装)
- [快速开始](#快速开始)
- [Python API 速览](#python-api-速览)
- [CLI 命令](#cli-命令)
- [权限与 Scope](#权限与-scope)
- [常见坑](#常见坑)
- [与官方文档的关系](#与官方文档的关系)
- [开发与测试](#开发与测试)
- [English](README_EN.md)
- [License](#license)

## 特性

| 特性 | 说明 |
|---|---|
| 零运行时依赖 | 只用 Python 标准库，`pip install` 不引入任何第三方包 |
| 112 个接口全覆盖 | 组织、域名、用户、部门、邮件组、公共联系人、邮件、日历、隔离区、收信规则、审计日志、文件流 |
| 两种鉴权模式 | 企业应用 `app_id`/`app_secret`（OAuth2 `client_credentials`）与个人 MCP token |
| 内置权限自检 | `alimail check` 一次性探测一组只读接口，输出 ✅/❌ 矩阵，直接看出缺哪个 scope |
| Host 自动回退 | 国内 Host `alimail-cn.aliyuncs.com` 取 token 失败时自动改试新加坡 `alimail-sg.aliyuncs.com` |
| 类型化异常 | 401 / 403 / 404 / 429 / 5xx / 网络错误分别映射为独立异常类 |
| Python + CLI 双形态 | 同一套能力：脚本里调 `Client`，终端里用 `alimail` |
| 离线测试 | 单测全部 mock HTTP，不访问真实租户、不依赖任何凭据 |

## 安装

```bash
pip install alimail
```

要求 Python >= 3.10。从源码安装：

```bash
git clone https://github.com/mcocdaa/python-alimail.git
cd python-alimail
pip install -e ".[dev]"
```

## 快速开始

### 1. 准备凭据

企业应用模式（推荐，需要有管理员权限的企业邮箱）：

```bash
export ALIMAIL_APP_ID="你的应用ID"
export ALIMAIL_APP_SECRET="你的应用Secret"
```

个人 MCP token 模式（单邮箱，需 AI 尊享版）：

```bash
export ALIMAIL_MCP_TOKEN="你的MCP Token"
export ALIMAIL_EMAIL="user@example.com"
```

两种凭据从哪来、Host 怎么选，见 [docs/quickstart.md](docs/quickstart.md)。

### 2. Python：3 行拿到用户列表

```python
from alimail import Client

client = Client.from_env()
print(client.users.list(size=5))
```

### 3. CLI：2 行验证连通

```bash
alimail token
alimail users --size 5
```

### 4. 权限自检

```bash
alimail check --email user@example.com
```

会逐个调用只读接口并打印 ✅/❌ 矩阵（节选）：

```text
账号: user@example.com  通过 5/13

状态   接口             Scope                       说明
-------------------------------------------------------------------------------------
✅    组织信息          Organization.Read.All
✅    用户列表          User.Read.All
❌    域名列表          Domain.Read.All             accessDenied
...

还需在应用里补充的 scope: Domain.Read.All, Department.Read.All, ...
```

- `✅` 通过；`❌` 是 403、缺对应 scope；`⚠️` 是请求本身出错（token / 网络等）。
- 全部通过时退出码为 0，否则为 3，可放进 CI 做门禁。
- 补完 scope 记得用 `alimail token --force` 重新取 token 再跑一次。
  完整 scope 清单见 [docs/permissions.md](docs/permissions.md)。

## Python API 速览

构造客户端：

```python
from alimail import Client

client = Client(app_id="...", app_secret="...", base="https://alimail-cn.aliyuncs.com")
client = Client.from_env()  # 环境变量 / 凭据文件
client = Client.from_mcp_token("mcp-token", email="me@example.com")  # 个人 MCP token
```

常用资源方法（返回值均为 `dict` / `list`，非 2xx 抛异常）：

| 能力 | 代码 |
|---|---|
| 换取 / 验证 token | `client.token()` |
| 用户列表 | `client.users.list(size=10)` → `{users, total, hasMore, nextCursor}` |
| 用户详情 | `client.users.get("user@example.com")` |
| 邮件文件夹 | `client.mail.folders("user@example.com")` |
| 文件夹内邮件 | `client.mail.messages("user@example.com", folder_id="2", size=20)` |
| 收件箱 | `client.mail.inbox("user@example.com", size=20)` |
| 邮件详情 | `client.mail.message("user@example.com", message_id)` |
| 搜索邮件 | `client.mail.search("user@example.com", query="subject:hello", size=20)` |
| 创建草稿 | `client.mail.create_draft("user@example.com", to=["a@example.com"], subject="Hi", text="正文")` |
| 发送邮件 | `client.mail.send("user@example.com", to=["a@example.com"], subject="Hi", text="正文")` |
| 附件列表 | `client.mail.attachments("user@example.com", message_id)` |
| 批量删除邮件 | `client.mail.delete("user@example.com", ids=["id1", "id2"])` |
| 日历列表 | `client.calendars.list("user@example.com")` |
| 时间范围内日程 | `client.calendars.events("user@example.com", calendar_id, start=None, end=None)` |
| 组织信息 | `client.organization.get()` |
| 域名列表 | `client.domains.list()` |
| 子部门 | `client.departments.children("$root")`（`"$root"` 表示根部门） |
| 邮件组列表 | `client.groups.list()` |
| 公共联系人分组 | `client.contacts.folders()` |
| 分组内联系人 | `client.contacts.contacts(folder_id)` |
| 隔离区搜索 | `client.quarantine.search("user@example.com", size=20)` |
| 域级收信黑白名单 | `client.message_rules.allow_block_lists()` |
| 审计日志 | `client.reports.search(start="2026-01-01T00:00:00Z", end="2026-01-02T00:00:00Z")` |

底层通用方法：

| 方法 | 说明 |
|---|---|
| `client.request("GET", "/v2/users", params={"size": 10})` | 发请求，返回解析后的 JSON，非 2xx 抛异常 |
| `client.raw("GET", "/v2/domains")` | 返回带 `status` / `data` / `headers` 的原始响应对象，非 2xx 不抛异常 |
| `client.paginate("GET", "/v2/users", item_key="users", params={"size": 100})` | 迭代器，按 `nextCursor` 自动翻页 |
| `client.call("list_users", size=5)` | 按 operation 名调用，operation 清单见 `alimail ops list` |

### 异常

```python
from alimail import (
    APIError,
    AuthError,
    PermissionDenied,
    NotFound,
    RateLimitError,
    ServerError,
    TransportError,
)

try:
    client.users.list(size=10)
except PermissionDenied as exc:  # 403，应用缺少对应 scope
    print(exc.status, exc.detail_error_code, exc.message)
except APIError as exc:  # 其余接口错误的基类
    print(exc.status, exc.developer_message)
```

| 异常 | 触发条件 |
|---|---|
| `AuthError` | 401，token 缺失 / 过期 / 无效 |
| `PermissionDenied` | 403，scope 不足或无权访问该资源 |
| `NotFound` | 404，资源不存在或不在当前域 |
| `RateLimitError` | 429，超出限流（单域合计 40 次/秒） |
| `ServerError` | 5xx，服务端错误 |
| `TransportError` | 网络层错误（DNS、超时、TLS、连接失败） |

其中前 5 个继承 `APIError`，携带 `status`、`detail_error_code`、`message`、`developer_message` 属性；
`TransportError` 与「未配置凭据」时抛出的 `ConfigError` 同属 `AlimailError` 体系。

## CLI 命令

```bash
alimail token [--force]                              # 验证凭据并取 token；--force 忽略缓存
alimail org                                          # 组织信息
alimail users [--size 20] [--filter "(email=*)"]     # 用户列表
alimail folders --email user@example.com             # 邮件文件夹
alimail inbox --email user@example.com [--size 10]   # 收件箱
alimail read <message-id> --email user@example.com   # 读一封邮件
alimail search --email user@example.com [--size 20] "subject:hello"
alimail send --from user@example.com --to a@example.com \
  --subject "Hi" --text "正文" [--html "..."] [--yes]   # 发送（不加 --yes 只预览）
alimail check [--email user@example.com]             # 权限自检矩阵
alimail call <operation-name> [--path k=v ...] [--query k=v ...] [--json-body '{"k":"v"}']
alimail ops [list] [--grep 关键字] [--tag 分类]        # 列出 operation
alimail ops show <operation-name>                    # 查看 operation 详情（含所需 scopes）
alimail raw GET /v2/domains [--query k=v ...] [--json-body '{"k":"v"}']
```

全局参数：`--app-id`、`--app-secret`、`--base`、`--timeout`、`--json`（输出 JSON）、`--version`。
全局环境变量：`ALIMAIL_APP_ID`、`ALIMAIL_APP_SECRET`、`ALIMAIL_BASE`（MCP 模式用 `ALIMAIL_MCP_TOKEN`、`ALIMAIL_EMAIL`）。

示例：

```bash
alimail call list_users --query size=5
alimail ops show list_users
alimail raw GET /v2/domains
```

`alimail send` 不加 `--yes` 时只打印 DRY RUN 预览并返回非 0（退出码 2），加 `--yes` 才会真正发送；
内部按官方两步流程「创建草稿 → 发送草稿」执行。**发送不可逆**，脚本里请先预览再确认。

## 权限与 Scope

阿里邮箱 OpenAPI 共 **27 个 scope**，按资源分组，最常见的是：

| Scope | 含义 |
|---|---|
| `Mail.Read.All` / `Mail.ReadWrite.All` | 读邮件 / 读写邮件（草稿、移动、删除、附件） |
| `Mail.Send.All` | 发送邮件 |
| `User.Read.All` / `User.Write.All` / `User.ReadWrite.All` | 读用户 / 写用户 / 用户读写 |
| `Organization.Read.All` | 读组织信息 |
| `Domain.Read.All` / `Department.Read.All` / `Group.Read.All` | 读域名 / 部门 / 邮件组 |
| `Calendar.Read.All` | 读日历与日程 |
| `Quarantine.Read.All` | 读隔离区 |
| `Report.Read.All` | 读审计日志 |

**最小权限原则**：先只勾只读 scope 跑通 `alimail check`，需要写操作时再按接口补勾。
权限调整后旧 token 不会自动获得新权限，需要重新取一次 token（`alimail token --force`）。

- 27 个 scope 的逐条中文说明与「按场景推荐组合」见 [docs/permissions.md](docs/permissions.md)
- 单个接口需要哪些 scope：`alimail ops show <operation-name>` 的 `scopes:` 字段

## 常见坑

| 现象 | 一句话原因 | 详见 |
|---|---|---|
| 用户列表返回 `users: []` 但 `total` 有值 | 分页参数是 `size`，不是 `limit` | [docs/pitfalls.md](docs/pitfalls.md#1-用户列表返回空数组但-total-有值) |
| `folderId is invalid!` | `folderId` 必须是数字 ID（收件箱 = 2） | [docs/pitfalls.md](docs/pitfalls.md#2-folderid-必须是数字-id) |
| `account not valid` | `/v2/users/$current` 不支持，要传真实邮箱 | [docs/pitfalls.md](docs/pitfalls.md#3-v2userscurrent-不支持) |
| 补了权限仍 403 | 旧 token 不会自动带上新 scope | [docs/pitfalls.md](docs/pitfalls.md#4-权限变更后必须重新获取-token) |
| 偶发 429 | 单域所有应用合计 40 次/秒 | [docs/pitfalls.md](docs/pitfalls.md#5-单域限流-40-次秒) |
| 后台找不到「API 开放平台」 | 免费版不支持，需要标准版及以上 | [docs/pitfalls.md](docs/pitfalls.md#6-免费版不支持-api-开放平台) |
| 保存应用后再也看不到 Secret | 需再次点进编辑页才能看到/重置 | [docs/pitfalls.md](docs/pitfalls.md#7-secret-可能只显示一次) |
| 用阿里云 AccessKey 换 token 失败 | 邮箱 API 用邮箱应用凭据，不是 RAM AK/SK | [docs/pitfalls.md](docs/pitfalls.md#8-accesskey-不能替代-appidsecret) |

## 与官方文档的关系

- 官方文档总入口：<https://mailhelp.aliyun.com/docs/>
- API 开放平台入门：<https://mailhelp.aliyun.com/docs/api/alibaba-mail-api>
- 创建应用：<https://mailhelp.aliyun.com/docs/guides/application/create-application>
- 配置与维护权限：<https://mailhelp.aliyun.com/docs/guides/application/permission-management>
- 获取访问凭证：<https://mailhelp.aliyun.com/docs/guides/examples/get-access-token>
- 创建草稿并发送邮件：<https://mailhelp.aliyun.com/docs/guides/examples/send-draft>
- MCP 服务说明（AI 尊享版）：<https://help.aliyun.com/zh/document_detail/2925708.html>
- 各版本功能对比：<https://www.alibabacloud.com/help/zh/alibaba-mail/latest/product-architecture-optional>

本项目的接口定义来自官方 OpenAPI spec（版本 13.3.0，112 个 path，17 个分类，27 个 scope），
命令、参数、路径以官方文档为准。若官方接口变更导致不一致，请提 issue，不要按本项目文档硬调接口。

## 开发与测试

```bash
pip install -e ".[dev]"
python -m unittest discover -s tests -v   # 或 pytest
ruff check .
```

测试全部离线（mock HTTP），不需要任何真实凭据。贡献流程、提交规范、加新接口的步骤见
[CONTRIBUTING.md](CONTRIBUTING.md)；安全问题请按 [SECURITY.md](SECURITY.md) 私下报告。

## English

**python-alimail** is an **unofficial** Python SDK and CLI for the
[Alibaba Mail (Alibaba Enterprise Mail)](https://mailhelp.aliyun.com/docs/) OpenAPI.

> This project is not affiliated with, endorsed by, or sponsored by Alibaba Cloud or
> Alibaba Mail. The official documentation is the source of truth for API behavior.

- Zero runtime dependencies — standard library only
- Covers 112 API operations across 17 categories
- Two auth modes: enterprise application `app_id`/`app_secret` (OAuth2
  `client_credentials`) and a personal MCP token
- Built-in permission self-check (`alimail check`) that probes read-only endpoints and
  prints a ✅/❌ matrix per scope
- Automatic host fallback from `alimail-cn.aliyuncs.com` to `alimail-sg.aliyuncs.com`
- Typed errors: `APIError` subclasses (`AuthError`, `PermissionDenied`, `NotFound`,
  `RateLimitError`, `ServerError`), plus `TransportError` for network failures and
  `ConfigError` for missing credentials

```bash
pip install alimail
export ALIMAIL_APP_ID="your-app-id"
export ALIMAIL_APP_SECRET="your-app-secret"
alimail token
alimail inbox --email user@example.com --size 5
```

```python
from alimail import Client

client = Client.from_env()
print(client.users.list(size=5))
```

Requires Python 3.10+. Documentation: [quickstart](docs/quickstart.md) ·
[permissions](docs/permissions.md) · [pitfalls](docs/pitfalls.md).

## License

[MIT](LICENSE) © 2026 mcocdaa and contributors
