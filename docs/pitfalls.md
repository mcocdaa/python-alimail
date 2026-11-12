# 真实踩坑合集

以下每一条都来自实际调用（2026-11 实测，OpenAPI spec 13.3.0），按「现象 → 原因 → 正确做法」整理。

---

## 1. 用户列表返回空数组，但 total 有值

**现象**

```text
GET /v2/users?limit=10
{"users": [], "total": 3}
```

数组是空的，`total` 却显示有 3 个用户，很容易误判成「没有权限」或「租户下没有账号」。

**原因**

用户列表的分页参数是 **`size`**，不是 `limit`。传 `limit` 不会被识别，服务端按默认分页窗口返回，
于是出现「空页 + total 是总计数」的迷惑结果。

**正确做法**

```python
users = client.users.list(size=10)  # 正确：size
print(users["total"], users["hasMore"], users["nextCursor"])

# 数据量大时自动翻页
for user in client.paginate("GET", "/v2/users", item_key="users", params={"size": 100}):
    print(user["email"])

# 等价写法：users.iter_all() 内部就是上面的 paginate
for user in client.users.iter_all(size=100):
    print(user["email"])
```

```bash
alimail users --size 10
```

排查口诀：**列表为空但 `total` > 0，先怀疑分页参数名写错。**

---

## 2. folderId 必须是数字 ID

**现象**

```text
GET /v2/users/user@example.com/mailFolders/收件箱/messages
400 {"message": "folderId is invalid!"}
```

传文件夹显示名（中文「收件箱」或英文 `Inbox`）都会失败。

**原因**

`folderId` 是数字 ID，不是 `displayName`。显示名还会随租户语言变化，不能用于接口路径。

**正确做法**

先解析出数字 ID 再查邮件。常用 ID 为：`sentitems=1`、`inbox=2`、`spam=3`、`draft=5`、`deleted=6`，
但不要依赖固定编号，让 SDK 解析最稳：

```python
# 方式 1：按文件夹名解析数字 ID（兼容中英文显示名）
inbox_id = client.mail.find_folder_id("user@example.com", "inbox")
messages = client.mail.messages("user@example.com", folder_id=inbox_id, size=20)

# 方式 2：更省事，inbox() 内部直接使用收件箱 ID
messages = client.mail.inbox("user@example.com", size=20)
```

---

## 3. `/v2/users/$current` 不支持

**现象**

```text
GET /v2/users/$current
{"detailErrorCode": "account not valid", ...}
```

**原因**

`$current` 这个占位符只在**组织**维度有效（`/v2/organization/$current`）。
用户相关接口必须给出真实用户 ID 或邮箱地址，服务端不会从 token 推断「当前用户」。

**正确做法**

先列用户拿到邮箱，再调用户维度接口：

```python
users = client.users.list(size=10)["users"]
email = users[0]["email"]

print(client.users.get(email))
print(client.mail.inbox(email, size=5))
```

CLI 里统一用 `--email` 显式指定：

```bash
alimail inbox --email user@example.com --size 5
```

组织信息不受影响：`client.organization.get()` / `alimail org` 内部就是 `/v2/organization/$current`。

---

## 4. 权限变更后必须重新获取 token

**现象**

管理员在后台给应用补勾了 `Mail.Send.All`，但客户端仍然返回 `403 accessDenied`，过一段时间也不恢复。

**原因**

scope 在**签发 token 时**确定，已经签发的 access token 不会自动获得新权限。
另外 SDK 会缓存 token（默认提前 120 秒过期），进程不重启就可能一直用旧的。

**正确做法**

改完权限后强制换一次 token，再复核：

```bash
alimail token --force                   # 忽略缓存，主动换取新 token
alimail check --email user@example.com  # 确认 scope 是否生效
```

Python 中显式强制刷新：

```python
client = Client.from_env()
print(client.token(force=True))  # 忽略缓存，重新换取
```

如果怀疑本地缓存有问题，也可以直接删掉缓存文件再重试：
Windows `%LOCALAPPDATA%\alimail\token-cache.json`，其他系统 `~/.cache/alimail/token-cache.json`。

仍返回 403 时按顺序检查：后台 scope 是否保存成功 → Host 是否与租户地域一致 → 应用是否被禁用。

---

## 5. 单域限流 40 次/秒

**现象**

批量拉取用户/邮件时偶发 `429`，对应 `RateLimitError`，重试后又时好时坏。

**原因**

官方限制：**单个域内所有应用合计 ≤ 40 次/秒**，超出返回 429。多进程、多实例共享同一个域时，
每个客户端单看都没超，加起来就超了。

**正确做法**

- SDK 默认已对 `429`（以及幂等请求的 `5xx`）做指数退避重试；持续收到 429 说明整体频率仍然超标。
- 串行或低并发请求，列表用较大的 `size` 分页，减少总请求数。
- 业务层再加一层退避，不要原地忙等：

```python
import time
from alimail import Client, RateLimitError

client = Client.from_env()
for attempt in range(5):
    try:
        users = client.users.list(size=100)
        break
    except RateLimitError:
        time.sleep(2**attempt)  # 1s, 2s, 4s, 8s...
else:
    raise SystemExit("持续被限流：请降低并发或拆分应用")
```

- 大批量通知/营销类发送不要走邮箱 API，官方建议改用**邮件推送（DirectMail）**。

---

## 6. 免费版不支持 API 开放平台

**现象**

登录邮箱管理后台，找不到「高级应用 / API 开放平台 / 添加应用」入口；或者根本没有管理后台。

**原因**

API 开放平台只对企业邮箱**标准版 / AI 尊享版 / 国产化版**开放，**免费版不支持**。
MCP 服务（个人 token）则只对 **AI 尊享版**开放，标准版里没有这个菜单，改权限也变不出来。

**正确做法**

| 你的情况 | 该走哪条路 |
|---|---|
| 企业邮箱标准版及以上 + 管理员权限 | 企业应用（app_id/secret），标准版即可 |
| AI 尊享版，只想操作自己的邮箱 | Webmail 生成 MCP token |
| 免费版 / 个人邮箱 | 两条路都不通，需先升级企业邮箱；纯批量发信考虑 DirectMail |

---

## 7. Secret 可能只显示一次

**现象**

在后台保存应用后，应用列表里只看得到 App ID，看不到 Secret；或者当时没记，之后再也找不到。

**原因**

后台的设计是：**保存后需要再次点进该应用的编辑页**才能看到 App ID 与 Secret，且 Secret 可能只展示一次。

**正确做法**

1. 保存应用后立刻**再次点进应用（编辑）**，复制 App ID 和 Secret。
2. 马上存进密码管理器或部署平台的环境变量，并立刻验证一次：`alimail token`。
3. 真的丢了就点「重置密钥 / 生成密钥」生成新 Secret——**旧 Secret 立即失效**，
   别忘了同步更新所有部署和 CI 里的值。

---

## 8. AccessKey 不能替代 appId/secret

**现象**

用阿里云 RAM 的 AccessKey ID / AccessKey Secret 去换 token，返回 `400 invalid_request` 或 `invalid_client`。

**原因**

这是两套完全不同的鉴权体系：

| 体系 | 凭据 | 用途 |
|---|---|---|
| 阿里邮箱 API 开放平台 | 邮箱后台创建的应用 `app_id` + `app_secret` | 本项目的所有邮箱接口 |
| 阿里云 OpenAPI（RAM） | AccessKey ID / AccessKey Secret | ECS、OSS、DirectMail 等云产品 |

`aliyun` CLI、阿里云 SDK 里配置的 AK/SK 与邮箱 API 无关。

**正确做法**

凭据只从邮箱管理后台「API 开放平台 → 应用」获取；没有管理员权限就找管理员开应用。
需要批量发信时，DirectMail 才是用 AK/SK 的那套产品，不要混用。

---

## 9. Host 与租户地域不匹配

**现象**

取 token 超时或鉴权失败，但凭据确认没填错；或国内租户误连了新加坡 Host。

**原因**

Host 由**租户开通地域**决定：国内 `alimail-cn.aliyuncs.com`，海外/新加坡 `alimail-sg.aliyuncs.com`，
两者不互通。凭据正确但 Host 错了，同样连不上。

**正确做法**

显式配置 Host，不要靠猜：

```bash
export ALIMAIL_BASE="https://alimail-sg.aliyuncs.com"   # 海外/新加坡租户
```

SDK 默认使用国内 Host，取 token 失败时会自动改试新加坡 Host 并在错误信息中体现；
生产环境建议直接写死正确 Host，省掉这次多余的重试延迟。

---

## 10. 发信是两步，不是一次请求

**现象**

直接把收件人、主题、正文 POST 给发送接口，报参数错误或找不到资源。

**原因**

官方发信流程是两步：先**创建草稿**拿到邮件 `id`，再**发送草稿**。
`POST /v2/users/{email}/messages/{id}/send` 里的 `{id}` 是已存在的草稿 ID，不是新邮件内容。

**正确做法**

用封装好的方法或 CLI（内部已处理两步）：

```python
client.mail.send("user@example.com", to=["a@example.com"], subject="Hi", text="正文")
```

```bash
alimail send --from user@example.com --to a@example.com --subject "Hi" --text "正文" --yes
```

`alimail send` 不加 `--yes` 时只做 dry-run 预览、不会真正发送；`--yes` 才会发出。
自己实现时按顺序调用 `create_draft(...)` → 从响应取 `id` → 调发送接口。
注意：**发送不可逆**，脚本里应先 dry-run、打印收件人与正文，确认后再真正发送。

---

## 相关

- 权限与 scope 对照：[permissions.md](permissions.md)
- 从零接入：[quickstart.md](quickstart.md)
- 官方文档：<https://mailhelp.aliyun.com/docs/>
