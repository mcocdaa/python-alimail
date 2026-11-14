# 快速开始：从零到第一次调用

本指南带你完成：创建阿里邮箱 API 应用 → 选择 Host → 配置凭据 → 调通第一个接口。
后台不同版本的菜单名略有差异，文中同时给出常见叫法。

## 0. 前置条件

| 条件 | 说明 |
|---|---|
| 邮箱版本 | 企业邮箱**标准版 / AI 尊享版 / 国产化版**支持「API 开放平台」；**免费版不支持** |
| 账号权限 | 需要能进入邮箱域管理后台的管理员账号 |
| Python | >= 3.10（仅 Python 方式需要） |
| 网络 | 能访问 `alimail-cn.aliyuncs.com` 或 `alimail-sg.aliyuncs.com` 的 443 端口 |

如果你只有个人邮箱、没有企业租户，可走 MCP token 路线（需 AI 尊享版），见[方式 C](#方式-c个人-mcp-token)。

## 1. 创建应用（拿 App ID / Secret）

登录网页版邮箱 → 进入管理后台，按后台实际菜单名操作：

1. 找到「高级应用」或「集成」分组下的「**API 开放平台**」。
2. 点击「**添加应用**」。
3. 填写应用名称与用途，例如 `mail-agent-readonly`、说明写「只读巡检脚本」。
4. 勾选需要的接口权限（scope）。第一轮建议只勾只读，跑通再加写权限：

   | Scope | 用途 |
   |---|---|
   | `Organization.Read.All` | 读组织信息 |
   | `Domain.Read.All` | 读域名列表 |
   | `User.Read.All` | 读用户列表与用户详情 |
   | `Department.Read.All` | 读部门树 |
   | `Group.Read.All` | 读邮件组 |
   | `SharedContact.Read.All` | 读公共联系人 |
   | `Mail.Read.All` | 读邮件、文件夹、附件 |
   | `Calendar.Read.All` | 读日历与日程 |
   | `Quarantine.Read.All` | 读隔离区 |
   | `MessageRule.Read.All` | 读域级收信黑白名单 |
   | `Report.Read.All` | 读审计日志 |

5. **保存**。
6. 回到应用列表，**再次点进刚创建的应用（编辑）**，才能看到 **App ID** 和 **Secret**。
   Secret 可能只显示一次，立刻复制到密码管理器或终端环境变量。
7. 如果看不到 Secret，点「重置密钥 / 生成密钥」重新生成（旧 Secret 立即失效）。

> 权限随时可改：编辑应用 → 增删 scope → 保存。改完要重新取 token 才生效，见第 5 节。
> 需要写操作时再补勾 `Mail.ReadWrite.All`、`Mail.Send.All`、`User.ReadWrite.All` 等，
> 各 scope 含义与推荐组合见 [permissions.md](permissions.md)。

## 2. 选择 Host

| 租户地域 | Host |
|---|---|
| 中国大陆（默认） | `https://alimail-cn.aliyuncs.com` |
| 海外 / 新加坡 | `https://alimail-sg.aliyuncs.com` |

- 选哪个由**租户开通地域**决定，不是由你人在哪里决定。
- 默认使用国内 Host；未显式指定 Host 时，SDK 在取 token 失败后会自动静默回退尝试新加坡 Host（实际生效的 Host 可通过 `client.base` 或 `alimail token` 查看）。
- 也可以显式指定：环境变量 `ALIMAIL_BASE`、CLI 参数 `--base`，或 `Client(base="...")`。
- `base` 只写到主机名，不要带 `/v2` 之类的路径。

## 3. 配置凭据

凭据按以下顺序解析，先命中先用：

| 顺序 | 来源 |
|---|---|
| 1 | 构造参数 / CLI flag：`--app-id`、`--app-secret`、`--base` |
| 2 | 环境变量：`ALIMAIL_APP_ID`、`ALIMAIL_APP_SECRET`、`ALIMAIL_BASE`（MCP：`ALIMAIL_MCP_TOKEN`、`ALIMAIL_EMAIL`） |
| 3 | 当前目录 `./alimail_creds.json` |
| 4 | 用户目录 `~/.alimail/creds.json` |
| 5 | MCP 账号文件：Windows `%APPDATA%\Alimail\accounts.json`，其他系统 `~/.alimail/accounts.json` |

### 方式 A：环境变量（推荐）

bash / zsh：

```bash
export ALIMAIL_APP_ID="你的应用ID"
export ALIMAIL_APP_SECRET="你的应用Secret"
export ALIMAIL_BASE="https://alimail-cn.aliyuncs.com"   # 可选，默认就是这个
```

PowerShell：

```powershell
$env:ALIMAIL_APP_ID = "你的应用ID"
$env:ALIMAIL_APP_SECRET = "你的应用Secret"
$env:ALIMAIL_BASE = "https://alimail-cn.aliyuncs.com"   # 可选
```

适合 CI / 容器 / 临时终端：把值放进平台的 secret 管理，不要在代码或脚本里硬编码。

### 方式 B：凭据文件

创建 `./alimail_creds.json`（当前目录，适合本仓库内本地调试）或 `~/.alimail/creds.json`
（用户级，适合全局使用）：

```json
{
  "app_id": "你的应用ID",
  "app_secret": "你的应用Secret",
  "base": "https://alimail-cn.aliyuncs.com"
}
```

- `base` 可省略，默认国内 Host。
- 收紧权限（Linux/macOS：`chmod 600`）。
- 仓库的 `.gitignore` 已忽略 `alimail_creds.json`，仍请在提交前 `git status` 复核。
- 优点：Secret 不进入 shell history，也不容易误粘到聊天记录。

### 方式 C：个人 MCP token

前提：邮箱版本为 **AI 尊享版**，且你操作的是**自己的邮箱账号**（不是域管理凭据）。
在 Webmail → 设置 → AI 智能 → MCP 服务 → 生成 Token（填用途、设过期时间）。

用环境变量：

```bash
export ALIMAIL_MCP_TOKEN="你的MCP Token"
export ALIMAIL_EMAIL="user@example.com"
```

或写账号文件（Windows `%APPDATA%\Alimail\accounts.json`，其他系统 `~/.alimail\accounts.json`）：

```json
{
  "accounts": [
    {
      "email": "user@example.com",
      "token": "你的MCP Token",
      "baseUrl": "https://alimail-cn.aliyuncs.com"
    }
  ]
}
```

Python 中也可以直接构造：

```python
from alimail import Client

client = Client.from_mcp_token("你的MCP Token", email="user@example.com")
```

MCP token 只能访问该账号自己的邮件与日历；组织、域名、用户管理等域级接口仍需企业应用凭据。

## 4. 第一次调用

### CLI

```bash
# 1) 验证凭据、换取 token
alimail token

# 2) 只读权限自检，输出 ✅/❌ 矩阵
alimail check --email user@example.com

# 3) 读收件箱最近 5 封
alimail inbox --email user@example.com --size 5
```

`alimail token` 只要没有报错，说明 App ID / Secret（或 MCP token）与 Host 都是对的。

### Python

```python
from alimail import Client

client = Client.from_env()

print(client.token()[:8] + "...")  # 能换到 token 说明凭据正确
print(client.users.list(size=5))  # 需要 User.Read.All
print(client.mail.inbox("user@example.com", size=5))  # 需要 Mail.Read.All
```

第一条 `client.token()` 只验证鉴权；后两条分别验证用户域和邮件域的 scope。
哪个报 `PermissionDenied`（403），就回后台补哪个 scope，然后重新取 token。

## 5. Token 与权限

| 项目 | 说明 |
|---|---|
| 企业应用 token | OAuth2 `client_credentials` 换取，有效期约 2 天（以响应里的 `expires_in` 为准） |
| token 缓存 | SDK 会缓存 token 并在临近过期（提前 120 秒）时换新；业务请求遇到 401 会自动刷新并重试一次 |
| 缓存位置 | Windows `%LOCALAPPDATA%\alimail\token-cache.json`；其他系统 `~/.cache/alimail/token-cache.json`（设置了 `XDG_CACHE_HOME` 时在 `$XDG_CACHE_HOME/alimail/`） |
| 权限变更 | 已签发的 token 不会自动带上新 scope，需要重新取一次 token |
| MCP token | 由用户自己在 Webmail 生成，可设过期时间；只代表单个邮箱账号 |
| 不要这样做 | 每次业务调用都手动换 token（慢且浪费）、把 token 打印到日志、把 token 提交进仓库 |

重新取 token：CLI 用 `alimail token --force`（忽略缓存强制换新）；Python 用 `client.token(force=True)`，
或删除上面的缓存文件后重新创建 `Client`。仍返回 403 时，用 `alimail check` 确认后台是否真的加上了对应 scope。

## 6. 常见问题

| 报错 / 现象 | 可能原因 | 处理 |
|---|---|---|
| `400 invalid_request` | 凭据错误，或 App ID / Secret 填反 | 核对后台的 App ID 与 Secret；token 请求是 form 编码，SDK 已处理 |
| `401 unauthorized` | token 缺失、过期或无效 | 重新 `alimail token`；确认环境变量没被别的配置覆盖 |
| `403 accessDenied` | 应用没有勾选对应 scope | 后台补勾 → `alimail token --force` → `alimail check` |
| 权限自检出现 ⚠️ | 请求本身失败（换 token 失败 / 网络不通），不是缺 scope | 先 `alimail token` 确认鉴权与 Host 正常 |
| 所有接口都 403 | 应用被禁用 / 域与 Host 不匹配 | 检查应用状态、租户地域与 `ALIMAIL_BASE` |
| `404` | 邮箱、messageId、日历 ID 不存在或不在当前域 | 先用 `alimail users` 确认账号 |
| `429` | 单域所有应用合计超过 40 次/秒 | 降低并发、加退避重试 |
| 用户列表为空但 `total` 有值 | 分页参数写成了 `limit` | 用 `size`（SDK 与 CLI 已正确处理） |
| `folderId is invalid!` | 传了文件夹中文名 | 用数字 ID（收件箱 = 2），或直接用 `client.mail.inbox()` |
| `account not valid` | 用了 `/v2/users/$current` | `/v2/users/$current` 不支持，传真实邮箱 |
| 后台没有「API 开放平台」 | 免费版邮箱 | 升级到标准版及以上 |
| 设置里没有「MCP 服务」 | 版本不是 AI 尊享版 | 升级版本，或改用企业应用模式 |
| 连接超时 / 连不上 | Host 与租户地域不符 | 指定正确的 `ALIMAIL_BASE`（国内 / 新加坡） |

更多细节见 [pitfalls.md](pitfalls.md)。

## 下一步

- 可直接运行的示例：[list_users.py](../examples/list_users.py)、[read_inbox.py](../examples/read_inbox.py)、[send_mail.py](../examples/send_mail.py)
- 全部 scope 与按场景的推荐组合：[permissions.md](permissions.md)
- 真实踩坑合集：[pitfalls.md](pitfalls.md)
- 官方文档：<https://mailhelp.aliyun.com/docs/>
