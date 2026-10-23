# 架构说明

## 概览

项目是一个**纯本地运行**的单体 Python 应用：FastAPI 负责页面与 JSON API，`app/api` 只处理 HTTP 合同，`app/services` 承载认证、会话、工作流编排和知识库操作，LangGraph 编排多方法估价流程，RAG 模块从本地文档与 Chroma 向量库检索依据，`app/tools` 负责确定性估价计算。前端由同一 FastAPI 进程同源提供，不单独部署；`launcher.py` 提供 Tkinter 本地启动面板。Web 服务与数据都在本机，模型调用只发往 `.env` 配置的 API 端点。

设计原则：

- **Web 框架与业务解耦**：服务层抛领域异常（`app/services/errors.py`），由应用工厂统一映射为 HTTP 状态码。
- **不确定与确定分离**：LLM 负责需求理解、方法规划与文字组织；金额计算全部走可单测的纯函数工具。
- **依据可追溯**：检索上下文和报告都携带 `[来源: 文件名]`，结构化 JSON 保存来源与计算项。
- **单机可运行**：认证会话在进程内存，会话与账号用本地 JSON；这是有意的取舍，降低本地演示与开发成本。
- **本地优先**：只监听 `127.0.0.1`，不包含域名、隧道、反向代理或公网部署逻辑。

## 组件

| 组件 | 位置 | 职责 |
| --- | --- | --- |
| 本地启动面板 | `launcher.py`、`start_panel.bat` | Tkinter 面板：启动/停止本地服务、打开工作台、重建索引、环境自检、实时日志与状态卡片 |
| 本地状态读取 | `app/local_runtime.py` | 仅标准库：健康检查、文档数、Chroma SQLite 向量数、`collect_status()` |
| 应用工厂 | `app/main.py` | `create_app()`、路由注册、`ServiceError` 异常映射、本地安全响应头 / 静态缓存中间件、`/` 页面 |
| HTTP 路由 | `app/api/` | `auth.py`、`sessions.py`、`valuation.py`、`admin.py`、`system.py`、`deps.py`、`models.py` |
| 认证服务 | `app/services/auth_store.py` | PBKDF2 密码哈希、`.env` 固定账号、注册用户 JSON、内存登录态 |
| 会话服务 | `app/services/session_store.py` | 每会话一个 JSON 文件、临时文件 + 原子替换、按会话锁、owner 校验 |
| 工作流服务 | `app/services/workflow_service.py` | 构造 LangGraph 初始状态、运行工作流、把节点更新整理为步骤时间线 |
| 知识库服务 | `app/services/knowledge_service.py` | 上传校验、切片预览、Chroma 重建、失败回滚、全局索引锁 |
| 领域异常 | `app/services/errors.py` | `InvalidInputError`(400)、`UnauthorizedError`(401)、`ForbiddenError`(403)、`NotFoundError`(404)、`ConflictError`(409)、`PayloadTooLargeError`(413)、`UnavailableError`(503) |
| 估价工作流 | `app/workflow/` | `graph.py` 状态图、`nodes.py` 六个阶段、`state.py`、`schemas.py` |
| RAG | `app/rag/` | 文档加载、500 字切片 + 10% 重叠、Chroma 余弦向量库、检索、带引用问答链 |
| 估价工具 | `app/tools/valuation.py` | 市场比较法、收益法、成本法计算；同时暴露为 LangChain Tool |
| Tool Calling Agent | `app/agent/` | `retrieve → agent ⇄ tools → finalize`，最多 5 次工具调用 |
| 视觉 | `app/vision.py` | 户型图与图片文档解析，图片会压缩到 1600px 内再发送 |
| 预设 | `app/presets.py` | 武汉 15 个区/功能区、2019–2024 年、四类物业的初测参数 |
| Web UI | `app/web/static/` | 登录/注册、工作台、报告、来源 chips、JSON 折叠、管理页 |
| 命令行 | `run.py` | `web` / `panel` / `status` / `index` / `eval` / `rag` / `agent` / `check` 统一入口 |
| 兼容入口 | `app/server.py` | `from app.main import app`，保留 `uvicorn app.server:app` |

## 请求流

```text
浏览器（http://127.0.0.1:8000）
  → FastAPI 中间件（本地安全响应头、静态缓存）
  → 路由（app/api/*）
  → 依赖（app/api/deps.py：Cookie 认证、角色、owner）
  → 服务层（app/services/*）
  → RAG / 工作流 / 工具 / JSON 存储
  → Pydantic 响应模型（app/api/models.py）
```

- 静态资源挂载在 `/static`，HTML 页面 `Cache-Control: no-cache`，静态资源长缓存，API 与 `/admin/` 响应 `no-store`；`/` 返回工作台 HTML，`/admin` 仅管理员返回管理页 HTML，未登录或普通用户会被 `302` 重定向到 `/`。
- 所有可预期的业务错误由 `ServiceError` 处理器统一返回 `{"detail": "..."}`；请求体校验失败仍是 FastAPI 默认的 422。
- 安全响应头包含 CSP（`script-src 'self'`、`connect-src 'self'`）、`X-Content-Type-Options: nosniff`、`X-Frame-Options: DENY`、`Referrer-Policy: same-origin`、`Permissions-Policy`；不包含域名、隧道或 HTTPS 跳转逻辑。

## 估价工作流

LangGraph 状态图（`app/workflow/graph.py`）节点：

```text
START → understand → plan → next_method
                              ├─(还有方法)→ retrieve → compute → next_method
                              └─(队列空)→ verify → report → END
```

1. **understand**：若请求已带结构化参数则跳过 LLM；否则用 `RequirementSchema` 结构化需求，金额统一为元、比例为小数，无法确定的信息进入 `missing_data`。
2. **plan**：LLM 按「有可比成交数据 / 有净收益与资本化率 / 有土地价值、重置成本、折旧」规划方法队列；LLM 失败或返回空时使用关键词启发式规划。
3. **next_method**：从队列取出当前方法，最多执行 4 轮。
4. **retrieve**：按方法检索知识库（`RETRIEVAL_TOP_K` 默认 4），同时按关键词单独检索武汉市场趋势来源，方法与趋势来源分离。
5. **compute**：调用确定性工具；缺少必需参数时返回缺失项而不编造数值。
6. **verify**：汇总各方法计算结果，由 LLM 做交叉校核，说明是否互相印证、差异原因与合理区间。
7. **report**：生成 Markdown 报告（估价对象、参考因素、目的与时点、采用方法、计算过程、校核结论、缺失资料、来源引用），同时输出 `ReportSchema` JSON。

工作流结果由 `workflow_service.run_workflow()` 用 `stream(stream_mode="updates")` 收集，转成前端可展示的步骤时间线（`understand` / `plan` / `retrieve` / `compute` / `verify`）。

## 认证与隔离

```text
POST /api/auth/login
  → auth_store.authenticate()（.env 账号优先，其次 data/auth_users.json）
  → 成功：secrets.token_urlsafe(32) 生成不透明 token，写入进程内存
  → Set-Cookie: realestate_auth=<token>; HttpOnly; SameSite=Lax; Max-Age=7d
```

- **角色**：`admin` / `user`。管理员账号只能来自 `.env` 的 `AUTH_USERS_JSON`；注册页只能创建 `user`，注册用户保存在 `AUTH_USERS_FILE`。
- **密码**：注册用户使用 PBKDF2-SHA256、260,000 轮、16 字节随机盐；`.env` 注入账号允许明文比较，因此必须使用强密码并保护 `.env`。
- **登录态**：内存字典 + 线程锁，过期时间 7 天；服务重启后 Cookie 全部失效。
- **隔离**：会话文件以 `owner_id = user:<username>` 标记；列表按 owner 过滤，读取/修改/删除前校验 owner，越权返回 404。
- **权限依赖**：`require_user` 返回 401，`require_admin` 返回 403，`current_owner` 生成 owner 字符串；`GET /admin` 页面路由不抛异常，非管理员直接 302 跳转 `/`。

当前公开（无需登录）的接口：`/api/auth/*`、`/api/health`、`/api/evaluate`、`/api/ask`、`/api/presets/*`、`/api/analyze-layout`；`/api/rag` 需要登录。具体清单见 [API_ENDPOINTS.md](API_ENDPOINTS.md)。

## RAG 检索

```text
data/docs/*（md/txt/csv/pdf/docx/png/jpg/jpeg）
  → loader 解析为 Document（保留 source / file_type / category）
  → splitter 按 500 字切片、10% 上下文重叠、优先在段落/句号处断开
  → bge-small-zh-v1.5 本地 Embedding（默认离线加载）
  → Chroma 持久化（余弦距离，集合 realestate_eval_docs）
  → retriever 相似度检索 top_k
  → chain：过滤低于 MIN_RELEVANCE_SCORE 的切片；无相关依据时明确返回「没有找到相关依据」
```

- 回答系统提示强制标注 `[来源: 文件名]`，禁止编造上下文之外的内容。
- 未配置 `OPENAI_API_KEY` 时，RAG 降级为「检索结果摘要」而非直接报错。
- PDF / DOCX / 图片入库分别依赖 `pypdf`、`python-docx`、`Pillow` + 视觉模型；缺少依赖或视觉密钥时会给出明确错误。
- 管理员上传/删除文档后会同步重建向量库；重建持有全局索引锁，失败时恢复原文件并尽力重建，避免知识库与文件不一致。

## 存储

| 路径 | 类型 | 说明 | Git |
| --- | --- | --- | --- |
| `data/docs/` | 源文件 | RAG 知识源，含示例估价方法、武汉市场数据、规范、税费、业务知识 | 提交 |
| `data/vector_db/` | Chroma | 本地向量索引，可重建 | 忽略 |
| `data/sessions/` | JSON | 每会话一个文件；临时文件 + `replace()` 原子写；进程内按会话锁 | 忽略 |
| `data/auth_users.json` | JSON | 注册普通用户（PBKDF2 哈希） | 忽略 |
| `data/launcher-error.log` | 日志 | 面板启动异常时写入的本地排错日志 | 忽略 |
| `app/web/static/` | 静态资源 | 同源前端页面与脚本 | 提交 |
| `.env` | 环境变量 | 模型密钥、管理员账号、路径与运行参数 | 忽略 |

会话 JSON 结构包含 `id`、`owner_id`、`title`、时间戳、`fixed_fields`、`layout_description`、`layout_filename` 和 `messages`（用户消息、报告、RAG 回答、步骤与报告 JSON）。

## 配置

`app/config.py` 在进程启动时读取 `.env` / 环境变量并缓存为不可变 `Config`。分为六类：

1. **文本模型**：`OPENAI_BASE_URL`、`OPENAI_API_KEY`、`LLM_MODEL`、`LLM_TIMEOUT_SECONDS`
2. **Embedding 与检索**：`EMBEDDING_MODEL`、`RETRIEVAL_TOP_K`、`MIN_RELEVANCE_SCORE`
3. **存储路径**：`DOCS_DIR`、`VECTOR_DB_DIR`、`SESSIONS_DIR`、`AUTH_USERS_FILE`（相对路径以项目根为基准）
4. **视觉模型**：`VISION_BASE_URL`、`VISION_API_KEY`、`VISION_MODEL`
5. **认证**：`AUTH_USERS_JSON`（固定账号）
6. **运行**：`APP_HOST`、`APP_PORT`、`LOG_LEVEL`、`MAX_UPLOAD_MB`

数值配置会在启动时校验（端口范围、`RETRIEVAL_TOP_K > 0`、`0 ≤ MIN_RELEVANCE_SCORE ≤ 1` 等），非法值直接启动失败。`APP_HOST` 默认 `127.0.0.1`，用于保证本地运行。

## 本地启动

```text
start_panel.bat（.venv\Scripts\pythonw.exe launcher.py）
  → launcher.py：Tkinter 面板
      ├─ 启动/停止：subprocess 运行 python run.py web
      ├─ 状态刷新：app/local_runtime.collect_status() → GET /api/health + Chroma SQLite
      ├─ 重建索引：python run.py index（流式日志）
      └─ 环境自检：python run.py check（流式日志）

python run.py web      → uvicorn app.main:app，监听 127.0.0.1:8000
python run.py status   → 输出 collect_status() 的 JSON
```

- Uvicorn 以单进程启动（`run.py` 中 `uvicorn.run`），监听 `APP_HOST:APP_PORT`，默认 `127.0.0.1:8000`；没有域名、隧道或反向代理相关行为。
- 面板只管理由它自己通过 `subprocess` 启动的服务进程；服务已在运行时只提示，不接管。关闭面板会确认并停止其启动的服务，避免后台残留。
- `python run.py panel` 与 `python launcher.py` 等价；`start_panel.bat` 使用 `.venv\Scripts\pythonw.exe`，不弹控制台。
- 修改 `.env` 或代码后需要重启服务；配置在启动时一次性加载。

## 已知约束

1. **本地单机**：服务默认只监听 `127.0.0.1`，所有数据保存在本机；不应把端口暴露到公网。如确需外部访问，需自行增加 TLS、反向代理与限流并承担风险。
2. **单实例**：登录态在进程内存，会话锁也是进程内的；多 worker / 多实例会导致登录态漂移与会话写竞争。
3. **JSON 存储**：会话与注册账号是本地文件，缺少事务、索引和并发控制，不适合高并发生产。
4. **无内置限流与审计**：项目面向本地单用户使用，如需对外提供服务需自行补齐网关层能力。
5. **部分接口公开**：无会话估价、预设、户型图解析无需登录，会消耗模型额度。
6. **同步索引重建**：上传/删除文档会阻塞式重建向量库；文档量大时应改为后台任务。
7. **演示数据**：武汉预设是「官方数据 + 模型假设」的初测口径，不能替代正式估价。
8. **模型依赖**：LLM 不可用时估价工作流会失败；Embedding 模型未缓存时需先联网下载。
9. **面板依赖桌面环境**：`launcher.py` 使用标准库 Tkinter，需要带 Tk 的 Python 与桌面会话；无桌面环境时可直接使用 `run.py web` / `run.py status`。
