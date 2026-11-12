# 贡献指南

感谢你愿意改进 python-alimail。这是一个**非官方**开源项目，欢迎 issue 和 PR，尤其欢迎：

- 与官方 OpenAPI spec 同步的新接口封装
- 真实使用中踩到的坑、文档更正
- CLI 使用体验改进
- 离线测试覆盖

## 开发环境

要求 Python >= 3.10。

```bash
git clone https://github.com/mcocdaa/python-alimail.git
cd python-alimail
python -m venv .venv
```

激活虚拟环境：

```bash
# Windows PowerShell
.venv\Scripts\Activate.ps1

# Windows cmd
.venv\Scripts\activate.bat

# Linux / macOS
source .venv/bin/activate
```

安装开发依赖（`dev` 额外依赖见 `pyproject.toml`：pytest、ruff、build）：

```bash
python -m pip install -U pip
pip install -e ".[dev]"
```

## 目录结构

| 路径 | 说明 |
|---|---|
| `src/alimail/` | SDK 包：客户端与鉴权、异常、资源封装、CLI、operations 注册表 |
| `tests/` | 离线单元测试（mock HTTP，不需要真实凭据） |
| `examples/` | 可直接运行的示例脚本 |
| `docs/` | 快速开始、权限说明、踩坑合集 |
| `README.md` | 项目入口文档 |

## 运行测试

两种方式等价，任选其一：

```bash
python -m unittest discover -s tests -v
pytest
```

测试约定：

- **全部离线**：单元测试不允许访问真实租户，不允许读取或写入真实凭据。
- 新增接口时覆盖：成功响应解析、错误映射（401/403/404/429/5xx）、分页行为。
- 修 bug 时先补一个能复现问题的测试，再改实现。
- 测试输出里不要出现真实域名、邮箱、token。

## 代码风格

```bash
ruff check .
```

- 行宽 100，规则配置见 `pyproject.toml`。
- 公开方法加类型注解和简短 docstring。
- **零运行时依赖是硬约束**：不要往 `src/alimail/` 引入第三方 import；确有需要先开 issue 讨论。
- 不要把凭据、token、邮件正文、收件人列表打印到日志或异常信息里。
- 遵循现有代码风格即可，不需要为了风格大规模重排。

## 提交信息

使用 [Conventional Commits](https://www.conventionalcommits.org/zh-hans/)：

```text
<type>(<scope>): <summary>
```

| type | 用途 |
|---|---|
| `feat` | 新功能 / 新接口 |
| `fix` | 修 bug |
| `docs` | 只改文档 |
| `test` | 测试相关 |
| `refactor` | 重构（不改行为） |
| `perf` | 性能优化 |
| `chore` | 构建、依赖、杂项 |
| `ci` | CI 配置 |

示例：

```text
feat(mail): add attachment upload session helper
fix(client): refresh token once on 401
docs(pitfalls): document size vs limit pagination
test(users): cover pagination cursor
```

一条提交只做一件事；破坏性变更在 footer 写 `BREAKING CHANGE:`。

## 添加新接口

1. **查官方文档**：在 <https://mailhelp.aliyun.com/docs/> 找到对应 API 页，记录
   method、path、所需 scope、请求参数、响应字段、分页字段。
2. **加资源方法**：在 `src/alimail/` 对应资源类中新增方法，复用现有的 `request` / `paginate`，
   不要重复实现 HTTP、鉴权、重试逻辑。
3. **登记 operation**（可选但推荐）：如果希望支持 `client.call("...")` 和
   `alimail call ...`，把 operation 名登记进 operations 注册表。
4. **补测试**：在 `tests/` 加离线测试，覆盖成功与错误路径。
5. **更新文档**：用户可见的行为变化要同步 `README.md`、`docs/` 和 `CHANGELOG.md` 的 `[Unreleased]`。
6. **本地检查**：

   ```bash
   ruff check .
   python -m unittest discover -s tests -v
   ```

7. **提 PR**：描述里写清接口文档链接、所需 scope、测试方式、是否验证过真实环境（没验证也没关系，说明即可）。

## PR 检查清单

- [ ] 测试通过（`unittest` 或 `pytest`）
- [ ] `ruff check .` 通过
- [ ] 没有提交任何真实凭据、token、租户域名、个人邮箱
- [ ] 需要时更新了 `CHANGELOG.md` / `docs/`
- [ ] 新增代码有必要的注释或 docstring
- [ ] 关联了相关 issue（如有）

## 行为准则

讨论对事不对人，保持建设性。请勿在 issue/PR 中粘贴真实凭据、完整邮件内容或他人隐私数据；
发现安全问题请按 [SECURITY.md](SECURITY.md) 私下报告。
