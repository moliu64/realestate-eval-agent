# 贡献指南

感谢参与项目改进。提交变更前请确保改动能在本地复现，并避免提交密钥、会话数据、注册账号文件、向量库和缓存目录。

## 环境准备

要求 Python 3.11+，仓库默认使用 `unittest` 与 FastAPI 同源前端。

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt      # 完整运行依赖
pip install -r requirements-dev.txt  # 测试 / CI 轻量依赖
Copy-Item .env.example .env
```

运行完整功能（向量检索、估价工作流）还需要在 `.env` 中配置 `OPENAI_BASE_URL`、`OPENAI_API_KEY`、`LLM_MODEL`，并按需配置 `VISION_*` 与 `AUTH_USERS_JSON`。没有模型密钥时，仍可运行确定性的单元测试与 HTTP 合同测试。

## 开发流程

1. Fork 仓库并从 `main` 创建功能分支。
2. 按 [README](README.md) 完成本地环境、`.env` 和向量库（`python run.py index`）准备。
3. 修改代码、测试与相关文档。
4. 运行下方「本地检查」全部通过。
5. 提交 Pull Request，说明动机、改动范围、测试结果与已知限制。

## 本地检查

统一入口是 `run.py`（`web` 为默认子命令）：

```powershell
# 测试（标准库 unittest，当前 37 个用例）
python -m unittest discover -s tests -v

# 字节编译（CI 同样覆盖 launcher.py）
python -m compileall -q app run.py launcher.py tests scripts

# 前端语法
node --check app/web/static/app.js
node --check app/web/static/admin.js
node --check app/web/static/ui.js

# 环境 / 知识库自检；--llm 会发起真实模型请求
python run.py check
python run.py check --llm

# 手工冒烟
python run.py web
python run.py panel       # 打开本地启动面板
python run.py status      # 输出本地运行状态 JSON
python run.py eval "帮我评估一套100平方米二手住宅，有近期可比成交单价20000元/平方米"
python run.py rag "收益法的资本化率怎么确定"

# 空白字符检查
git diff --check
```

- 检索相关测试在未构建向量库、向量库为空或 Embedding 模型不可用时自动 `skip`。
- 需要真实 LLM 的端到端测试默认跳过，显式启用：

```powershell
$env:RUN_LLM_TESTS='1'
python -m unittest tests.test_workflow tests.test_agent -v
```

## 架构约定

| 目录 | 职责 | 约定 |
| --- | --- | --- |
| `app/api/` | HTTP 层 | 只做参数校验、认证依赖和响应模型；新增路由同步更新 `docs/API_ENDPOINTS.md` |
| `app/services/` | 领域服务 | 不导入 FastAPI，不抛 `HTTPException`，使用 `app/services/errors.py` 的领域异常 |
| `app/workflow/` | LangGraph 编排 | 节点只返回状态增量；确定性计算下沉到 `app/tools/` |
| `app/tools/` | 确定性计算 | 纯函数、可独立单测；金额单位为元、比例为小数 |
| `app/rag/` | 文档与检索 | 文档处理、切片、向量库、检索链各自独立；不要绕过 `knowledge_service` 直接改知识库 |
| `app/main.py` | 应用装配 | 只做路由注册、异常映射与跨切面中间件 |
| `app/web/static/` | 前端 | 原生 HTML/CSS/JS，同源调用 `/api/*`；不要引入独立前端服务或跨域配置 |
| `launcher.py` | 本地启动面板 | Tkinter 标准库实现；只管理自己启动的服务进程，状态读取复用 `app/local_runtime.py` |
| `app/local_runtime.py` | 本地状态 | 仅标准库，不导入 Tkinter 或模型；供面板、`run.py status` 与测试复用 |

其他约定：

- 会话归属统一使用 `owner_id = user:<username>`，读写前必须校验，越权一律按不存在处理。
- 新增环境变量必须同步 `.env.example`、`app/config.py`、README 配置表和 `docs/ARCHITECTURE.md`。
- 认证、登录态与密码逻辑集中在 `app/services/auth_store.py`，不要在路由里重复实现。
- 保持 `app/server.py` 仅为兼容入口（`from app.main import app`）。
- 本项目定位为**纯本地运行**：不要引入域名、隧道、公网部署或反向代理相关配置；如需对外访问，应作为独立扩展并明确风险。
- 修改启动方式或新增 CLI 子命令时，同步更新 `run.py` 的帮助文本、README 与 `docs/ARCHITECTURE.md`。
- 历史文档 `docs/plans/`、`docs/reviews/` 是决策记录，不随实现回写；当前行为以 README 和源码为准。

## 测试要求

- 新增计算逻辑：在 `tests/test_tools.py` 或 `tests/test_workflow.py` 覆盖正常值与边界值。
- 新增接口：在 `tests/test_api.py` 使用 Starlette `TestClient` 覆盖成功、未登录、越权与非法参数路径，测试数据写入临时目录，不依赖真实模型。
- 修改本地状态读取或启动面板逻辑：在 `tests/test_local_runtime.py` 覆盖文档计数、向量计数、服务探测与 URL；面板交互本身需按「本地检查」手工冒烟。
- 涉及认证、会话隔离、RAG 权限或上传管理的改动，至少覆盖「未登录 / 普通用户 / 管理员」三类场景。
- 不要为了让测试通过而放宽 `skip` 条件；检索与 LLM 用例的跳过是 CI 友好设计。
- CI 会执行 `compileall`（含 `launcher.py`）、`node --check` 和 `python -m unittest discover -s tests -v`，PR 前请在本地跑通。

## 文档与素材

- 用户可见行为变化需同步更新 `README.md` 或 `docs/`。
- 截图放在 `docs/screenshots/`，README 只引用实际存在的文件，更新界面后重新生成。
- 文档和示例中不得出现真实 API Key、密码、本机绝对路径、内网地址或个人信息。
- 不要提交 `.env`、`data/auth_users.json`、`data/sessions/`、`data/vector_db/`、`__pycache__/` 和日志。

## PR 检查清单

- [ ] 变更范围聚焦，未混入无关重构或格式化噪声。
- [ ] `python -m unittest discover -s tests -v` 通过，新增行为有测试覆盖。
- [ ] `python -m compileall -q app run.py launcher.py tests scripts` 通过。
- [ ] 前端改动通过 `node --check app/web/static/app.js`、`node --check app/web/static/admin.js` 与 `node --check app/web/static/ui.js`。
- [ ] `python run.py check` 通过；涉及界面时本地启动 `python run.py web` 验证关键流程。
- [ ] 涉及启动面板时，`python run.py panel` 与 `python run.py status` 手工冒烟通过。
- [ ] 新增/修改接口、配置、入口已同步到 README、`docs/API_ENDPOINTS.md`、`docs/ARCHITECTURE.md`。
- [ ] 未提交任何密钥、会话数据、账号文件、向量库或本机路径。
- [ ] PR 描述包含动机、改动摘要、测试结果和已知限制。

## 提交信息

建议使用简洁的祈使句描述改动，例如：

```text
feat: 增加会话内 RAG 来源引用
fix: 修复上传文档重建索引失败时的回滚
docs: 更新快速开始与配置说明
test: 补充未登录会话接口的合同测试
```
