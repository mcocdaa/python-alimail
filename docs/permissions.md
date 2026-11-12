# 权限（Scope）说明与推荐组合

阿里邮箱 OpenAPI 在应用维度做权限控制：调用某个接口时，应用必须持有该接口声明要求的 scope，
否则返回 `403 accessDenied`。本文把官方 OpenAPI spec（13.3.0）里的 **27 个 scope** 按资源整理成中文说明，
并给出按场景的推荐勾选组合。

> 本文是官方文档的摘要，方便对照后台勾选项使用；权威定义以[官方权限管理文档](https://mailhelp.aliyun.com/docs/guides/application/permission-management)为准。

## 命名规律

| 形式 | 含义 | 例子 |
|---|---|---|
| `X.Read.All` | 资源只读 | `Mail.Read.All` |
| `X.Write.All` | 资源写（部分资源有独立写 scope） | `User.Write.All` |
| `X.ReadWrite.All` | 资源读写；读取接口接受它，写接口通常也接受它 | `Department.ReadWrite.All` |

两条实践规则：

1. **读接口**一般列出「`X.Read.All` 或 `X.ReadWrite.All`」两者之一即可，所以只想读就勾 `Read`。
2. **写接口**通常列出「`X.Write.All` 或 `X.ReadWrite.All`」两者之一即可；但邮件的写操作没有独立的
   `Mail.Write.All`，统一用 `Mail.ReadWrite.All`；而**发信**是单独的 `Mail.Send.All`，必须额外勾。

## 27 个 Scope 全表

| Scope | 中文含义 | 主要覆盖 |
|---|---|---|
| `Mail.Read.All` | 读邮件 | 邮件列表、邮件详情、搜索、附件列表 |
| `Mail.ReadWrite.All` | 读写邮件 | 草稿、更新、移动、复制、批量删除、附件上传会话、文件夹管理 |
| `Mail.Send.All` | 发送邮件 | 发送草稿（`POST .../messages/{id}/send`） |
| `User.Read.All` | 读用户 | 用户列表与详情、共享账号成员、`sharedWithMe` |
| `User.Write.All` | 写用户 | 建/改/删用户、改密与重置密码、别名、安全手机、共享账号成员写 |
| `User.ReadWrite.All` | 用户读写 | 既可当读 scope，也可当写 scope 使用 |
| `User.Login.All` | 登录相关 | 生成用户免登录链接 |
| `Organization.Read.All` | 读组织 | 组织信息（`GET /v2/organization/$current`） |
| `Organization.ReadWrite.All` | 组织读写 | 读组织信息、更新组织信息 |
| `Domain.Read.All` | 读域名 | 域名列表、域名详情 |
| `Domain.ReadWrite.All` | 域名读写 | 创建/删除域名、验证域名所有权 |
| `Department.Read.All` | 读部门 | 部门信息、层级链、子部门、部门成员 |
| `Department.ReadWrite.All` | 部门读写 | 创建/更新/删除部门 |
| `Group.Read.All` | 读邮件组 | 邮件组列表与详情、成员列表 |
| `Group.ReadWrite.All` | 邮件组读写 | 创建/更新/删除邮件组、批量增删成员 |
| `SharedContact.Read.All` | 读公共联系人 | 公共联系人及分组查询 |
| `SharedContact.ReadWrite.All` | 公共联系人读写 | 公共联系人及分组的增删改 |
| `Calendar.Read.All` | 读日历 | 日历列表、日程详情、时间范围日程、忙闲状态、ICS 导出 |
| `Calendar.ReadWrite.All` | 日历读写 | 日历与日程增删改、共享、ICS 导入、响应会议邀请 |
| `Quarantine.Read.All` | 读隔离区 | 搜索隔离邮件、详情、附件列表 |
| `Quarantine.ReadWrite.All` | 隔离区读写 | 释放隔离邮件、批量删除隔离邮件 |
| `MessageRule.Read.All` | 读收信规则 | 查询域级收信黑白名单 |
| `MessageRule.Write.All` | 写收信规则 | 新建/批量删除域级黑白名单条目 |
| `MessageRule.ReadWrite.All` | 收信规则读写 | 既可当读 scope，也可当写 scope |
| `Report.Read.All` | 读审计日志 | 查询审计日志（`POST /v2/reports`） |
| `ConditionalAccessPolicy.Read.All` | 读条件访问 | 查询条件访问策略列表 |
| `ConditionalAccessPolicy.ReadWrite.All` | 条件访问读写 | 条件访问策略的增删改 |

少数接口在 spec 里没有标注 scope（例如「接受日历共享」、邮箱设置读写、日历共享查询），
它们仍然需要有效的 token 和对应的账号权限，实际以调用结果为准。

## 按场景推荐组合

### 1. 只读巡检 / 连通性验证（最小集合）

适合首次接入、健康检查、`alimail check`：

```text
Organization.Read.All  Domain.Read.All  User.Read.All
Department.Read.All    Group.Read.All   SharedContact.Read.All
Mail.Read.All          Calendar.Read.All  Quarantine.Read.All
MessageRule.Read.All   ConditionalAccessPolicy.Read.All  Report.Read.All
```

### 2. 收发邮件（单账号自动化）

```text
Mail.Read.All  Mail.ReadWrite.All  Mail.Send.All  User.Read.All
```

- 只读收件箱：`Mail.Read.All` 即可。
- 建草稿/标记已读/移动/删除：需要 `Mail.ReadWrite.All`。
- 真正发出去：必须再加 `Mail.Send.All`。
- 如果账号是 MCP token 模式，则不需要在后台勾 scope，token 自带该账号的权限。

### 3. 组织架构同步（只读）

```text
Organization.Read.All  Domain.Read.All  User.Read.All
Department.Read.All    Group.Read.All   SharedContact.Read.All
```

### 4. 组织架构同步（含写入）

在场景 3 的基础上按需增加：

```text
Organization.ReadWrite.All  Domain.ReadWrite.All
User.ReadWrite.All（或 User.Write.All）
Department.ReadWrite.All    Group.ReadWrite.All
SharedContact.ReadWrite.All
```

### 5. 安全审计 / 隔离区排查

```text
Report.Read.All  Quarantine.Read.All  MessageRule.Read.All
ConditionalAccessPolicy.Read.All  User.Read.All  Domain.Read.All
```

需要释放隔离邮件或调整黑白名单时再升级到 `Quarantine.ReadWrite.All`、`MessageRule.Write.All`。

### 6. 日历集成

```text
Calendar.Read.All  User.Read.All
```

需要创建日程、共享日历、响应邀请时增加 `Calendar.ReadWrite.All`。

### 7. 高风险写操作

以下 scope 会修改组织数据、影响邮件投递或账号安全，建议单独建一个应用、仅在受控环境启用：

```text
Mail.Send.All               # 对外发信，不可逆
User.Write.All              # 建/删用户、改密、重置密码
Domain.ReadWrite.All        # 增删域名
Organization.ReadWrite.All  # 改组织信息
MessageRule.Write.All       # 改域级黑白名单，影响收信
Quarantine.ReadWrite.All    # 释放/删除隔离邮件
ConditionalAccessPolicy.ReadWrite.All
```

建议：

- 读写分离：日常巡检用一个只读应用，写操作用另一个应用，用完可禁用。
- 写操作前二次确认目标（邮箱、ID、收件人），批量操作先小范围试。
- 开启并定期查看审计日志（需要 `Report.Read.All`，对应 `POST /v2/reports`，Python 里是 `client.reports.search(...)`）。

## 如何验证权限

```bash
alimail check --email user@example.com
```

输出 ✅/❌ 矩阵：`200` 表示对应 scope 已生效；`403 accessDenied` 表示还缺对应 scope。
在后台补勾 scope 后，**必须重新取一次 token**（旧 token 不会自动获得新权限）：先 `alimail token --force`，
再重跑 `alimail check`。

查某个接口到底需要哪些 scope，用 `alimail ops show <operation-name>`，输出里的 `scopes:` 字段即官方 spec 的声明。

Python 中可以直接捕获异常定位：

```python
from alimail import Client, PermissionDenied

client = Client.from_env()
try:
    client.organization.get()
except PermissionDenied as exc:
    print("缺少 scope 或无权访问：", exc.message)
```

## 参考

- 创建应用：<https://mailhelp.aliyun.com/docs/guides/application/create-application>
- 配置与维护权限：<https://mailhelp.aliyun.com/docs/guides/application/permission-management>
- 获取访问凭证：<https://mailhelp.aliyun.com/docs/guides/examples/get-access-token>
