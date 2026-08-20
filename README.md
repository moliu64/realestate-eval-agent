# 房地产估价智能体

面向武汉房地产估价场景的 RAG + LangGraph 应用。系统将本地知识库、确定性估价工具、通义千问视觉模型和 OpenAI 兼容文本模型组合为可追踪的多方法估价工作流。

部署地址（按需启用）：[https://060115.top](https://060115.top)

> 在线环境通过 Cloudflare Tunnel 连接当前电脑。电脑关机、休眠或断网时，网站会离线。

## 主要功能

- 市场比较法、收益法、成本法计算与多方法交叉校核
- 武汉各区域 2019-2024 年估值参数预设
- Markdown 估价报告、执行时间线和结构化 JSON 输出
- PDF、DOCX、Markdown、TXT、CSV 和图片知识文档入库
- 相邻文档片段保留 10% 上下文重叠
- 通义千问 VL 户型图解析和图片知识入库
- 中文知识库管理页，支持预览、覆盖、删除和自动重建向量库
- 桌面端与手机端响应式 Web UI

## 技术栈

- Python、FastAPI、Uvicorn
- LangChain、LangGraph、Chroma
- sentence-transformers / BGE 中文 Embedding
- OpenAI-compatible Chat API
- DashScope compatible-mode / `qwen-vl-plus`
- 原生 HTML、CSS、JavaScript
- Cloudflare DNS、TLS、Tunnel

## 快速开始

建议使用 Python 3.11 或更高版本。

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.lock
Copy-Item .env.example .env
```

编辑 `.env`，至少配置：

```env
OPENAI_BASE_URL=https://你的文本模型兼容接口/v1
OPENAI_API_KEY=你的文本模型密钥
LLM_MODEL=你的文本模型名称

VISION_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
VISION_API_KEY=你的DashScope密钥
VISION_MODEL=qwen-vl-plus

ADMIN_TOKEN=兼容旧配置的管理密钥（管理页以登录角色为准）
AUTH_USERS_JSON={"admin":{"password":"更换为管理员密码","role":"admin"},"analyst":{"password":"更换为普通用户密码","role":"user"}}
```

`.env` 已被 Git 忽略，不应提交模型密钥、管理密钥或其它凭证。

## 构建知识库

首次运行或知识文档发生变化后执行：

```powershell
python scripts/indexing/make_docs.py
python scripts/indexing/build_index.py --rebuild
```

Embedding 模型已经缓存时，可以强制离线加载：

```powershell
$env:HF_HUB_OFFLINE='1'
$env:TRANSFORMERS_OFFLINE='1'
```

首次下载模型遇到 HuggingFace 网络问题时：

```powershell
$env:HF_HUB_OFFLINE='0'
$env:TRANSFORMERS_OFFLINE='0'
$env:HF_ENDPOINT='https://hf-mirror.com'
python scripts/indexing/build_index.py --rebuild
```

## 运行方式

### 一体化 Web

```powershell
python run_web.py
```

打开 `http://127.0.0.1:8000`。这是本地使用和 Cloudflare Tunnel 采用的入口。

首页支持三栏估价工作台：左侧管理可持久化会话，中间进行多轮估价对话，右侧上传并查看户型图解析。会话数据保存在本地 `data/sessions/`，该目录已加入忽略规则，不会进入版本库。

会话按登录账号隔离：后端通过 HttpOnly Cookie 维护登录态，并将会话归属绑定到账号。列表、读取、修改、删除、估价和知识库问答接口均校验会话归属，不同账号无法互相读取会话；生产环境应继续使用 HTTPS，并将会话目录配置为仅服务进程可读写。

### 前后端独立运行

Windows 下先双击 `start_backend.bat`，再双击 `start_frontend.bat`：

- 后端：`http://127.0.0.1:8000`
- 前端：`http://127.0.0.1:5173`

等价的终端命令：

```powershell
python run_backend.py
python run_frontend.py
```

独立部署时通过 `BACKEND_URL` 指定 API 地址，通过 `CORS_ORIGINS` 配置允许的前端来源。

### 在线服务

双击根目录 `start_online.bat`，脚本会检测并补启动后端与 Cloudflare Tunnel：

```powershell
.\start_online.bat
```

当前线上服务默认关闭。需要上线时手动执行 `start_online.bat`；如需开机自动运行，再按 [Cloudflare 部署文档](docs/deployment/CLOUDFLARE.md) 配置 Windows 任务计划。详细拓扑、凭证位置和故障检查也见该文档。

## 知识库管理

首次进入估价工作台需要登录。账号由 `.env` 中的 `AUTH_USERS_JSON` 配置；只有 `role=admin` 的账号会显示并可访问 RAG 知识库管理入口。普通用户可以使用 RAG 检索和估价工作流中的知识依据，但不能访问文档上传、删除、切片预览、向量库重建等管理接口。生产环境请使用强密码并启用 HTTPS。

登录页支持注册普通用户账号。用户名长度为 3-80 个字符且不可重复，密码长度至少 8 位，注册时必须两次输入一致。注册账号保存在 `data/auth_users.json`，管理员账号仍只从 `.env` 配置，不允许通过注册页创建。

管理页支持：

- 按估价方法、市场数据、政策法规、估价规范、业务知识、用户资料分类
- 上传 `.md`、`.txt`、`.csv`、`.pdf`、`.docx`、`.png`、`.jpg`、`.jpeg`
- 入库前查看切片及 10% 重叠结果
- 同名覆盖、删除文档并自动重建向量库
- 单文件最大 20 MB

运行所需知识文档统一放在 `data/docs/`。文件名使用 `大类_中文标题.扩展名`，不要把规划或评审文档放入该目录。

## CLI 示例

```powershell
# RAG 问答
python run_rag.py "收益法的资本化率如何确定？"

# 工具调用 Agent
python run_agent.py "某商铺年净收益60万元，资本化率5%，请估值。"

# 多方法估价工作流
python run_eval.py "评估一套100平方米二手住宅，并进行多方法校核。"
```

## 测试

核心回归测试：

```powershell
python -m unittest tests.test_presets tests.test_splitter tests.test_workflow tests.test_tools tests.test_retriever tests.test_agent
```

需要真实模型的测试默认跳过。显式启用：

```powershell
$env:RUN_LLM_TESTS='1'
python -m unittest tests.test_agent tests.test_workflow
```

## 架构

```text
Web / CLI
   |
FastAPI -> LangGraph workflow
              |-> RAG retrieval -> Chroma -> BGE Embedding
              |-> valuation tools -> 市场比较法 / 收益法 / 成本法
              |-> chat model -> 校核、报告与引用
              `-> Qwen-VL -> 户型图和图片文档解析
```

工作流主路径：

```text
understand -> plan -> next_method -> retrieve -> compute
                 ^                         |
                 `------ multi-loop -------'
                              |
                           verify -> report
```

`computations` 使用累加 reducer，确保多方法计算结果不会互相覆盖。报告同时输出 Markdown 和确定性 JSON，便于人工阅读及系统集成。

## 目录结构

```text
.
├── .github/workflows/        # GitHub Actions
├── app/
│   ├── agent/                # Tool Calling Agent
│   ├── rag/                  # 文档加载、切分、检索和向量库
│   ├── tools/                # 确定性估价工具
│   ├── web/static/           # 前端页面与资源
│   └── workflow/             # 多方法 LangGraph 工作流
├── data/
│   ├── docs/                 # 生产 RAG 知识文档
│   ├── sessions/              # 运行时会话，不提交 Git
│   └── vector_db/             # 本地生成，不提交 Git
├── docs/
│   ├── deployment/           # 部署与运维文档
│   ├── plans/                # 历史实施计划
│   ├── reference/            # 数据参考资料
│   └── reviews/              # 历史评审记录
├── scripts/
│   ├── deployment/           # 在线启动内部脚本
│   └── indexing/             # 文档校验和向量库构建
├── tests/                    # 单元、检索和工作流测试
├── run_*.py                  # CLI 与服务公开入口
├── start_*.bat               # Windows 一键入口
├── requirements.txt          # 宽松依赖范围
└── requirements.lock         # 可复现锁定版本
```

历史计划与评审索引见 [docs/README.md](docs/README.md)。

## GitHub 同步说明

仓库只提交源代码、测试、知识文档和部署文档。以下内容由本地运行生成或包含敏感信息，已通过 `.gitignore` 排除：`.env`、`.venv/`、`data/sessions/`、`data/vector_db/`、`data/auth_users.json`、Python 缓存和临时目录。克隆仓库后按“快速开始”配置环境，再按“构建知识库”生成本地向量库。

## 数据说明

武汉预设以武汉市人民政府基准地价和国家统计局住宅价格指数为官方基准。区级代表地价映射、可比单价、净收益、资本化率、重置成本和折旧仍包含公式推导或可编辑估值假设，不能替代具体宗地定位、现场查勘和真实成交案例调查。

公网估值、RAG 和视觉接口会消耗模型 API 额度。正式对外推广前应在 Cloudflare 配置限流或 Turnstile。
