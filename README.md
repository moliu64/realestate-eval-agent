# 房地产估价智能体

面向武汉房地产估价场景的 RAG + LangGraph 应用。系统将本地估价知识库、确定性估价工具、视觉模型和 OpenAI 兼容文本模型组合为可追踪的多方法估价工作流。

> 公网部署地址 `https://060115.top` 当前按需启用；本项目默认以本地运行作为开发和验证方式。

## 功能概览

- 市场比较法、收益法、成本法计算与多方法交叉校核
- 武汉区域和年度估价参数预设
- 多轮估价会话、账号登录、注册和账号级会话隔离
- Markdown 估价报告、执行步骤时间线和结构化 JSON 输出
- PDF、DOCX、Markdown、TXT、CSV 和图片文档入库
- 文档切片保留 10% 上下文重叠，减少边界信息丢失
- 户型图上传与视觉模型解析
- 普通用户可使用 RAG 检索；仅管理员可进入知识库管理页面
- 桌面端和移动端响应式 Web UI

## 技术栈

| 层次 | 技术 |
| --- | --- |
| 运行时 | Python 3.11+ |
| Web 后端 | FastAPI、Uvicorn |
| 工作流 | LangGraph |
| LLM 集成 | LangChain、OpenAI-compatible API |
| 向量检索 | Chroma、sentence-transformers、BGE Embedding |
| 视觉模型 | OpenAI-compatible Vision API，可配置 Qwen-VL 或其他兼容模型 |
| 前端 | 原生 HTML、CSS、JavaScript |
| 在线转发 | Cloudflare Tunnel，可选 |

## 快速开始

### 1. 安装依赖

建议使用 Python 3.11 或更高版本。

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.lock
Copy-Item .env.example .env
```

### 2. 配置环境变量

编辑 `.env`，至少配置文本模型和视觉模型：

```dotenv
OPENAI_BASE_URL=https://your-text-provider.example/v1
OPENAI_API_KEY=your-text-api-key
LLM_MODEL=your-text-model

VISION_BASE_URL=https://your-vision-provider.example/v1
VISION_API_KEY=your-vision-api-key
VISION_MODEL=your-vision-model

AUTH_USERS_JSON={"admin":{"password":"change-me","role":"admin"}}
```

`.env`、注册账号数据、会话数据和向量库均不应提交到 GitHub。

### 3. 构建向量库

知识源文档位于 `data/docs/`。首次运行或文档发生变化后执行：

```powershell
python scripts/indexing/make_docs.py
python scripts/indexing/build_index.py --rebuild
```

Embedding 模型已缓存时，可使用离线模式：

```powershell
$env:HF_HUB_OFFLINE='1'
$env:TRANSFORMERS_OFFLINE='1'
python scripts/indexing/build_index.py --rebuild
```

首次下载模型遇到网络问题时，可临时关闭离线模式并配置镜像：

```powershell
$env:HF_HUB_OFFLINE='0'
$env:TRANSFORMERS_OFFLINE='0'
$env:HF_ENDPOINT='https://hf-mirror.com'
```

### 4. 启动 Web 应用

```powershell
python run_web.py
```

打开 <http://127.0.0.1:8000>。

Windows 也可以使用根目录的一键入口：

- `start_backend.bat`：启动后端
- `start_frontend.bat`：启动独立前端开发服务
- `start_online.bat`：启动后端和 Cloudflare Tunnel，默认不自动执行

前后端独立运行时，前端通过 `BACKEND_URL` 指向后端，后端通过 `CORS_ORIGINS` 控制允许的来源。

## 账号与权限

账号由 `.env` 中的 `AUTH_USERS_JSON` 提供，注册的普通用户保存在本地 `data/auth_users.json`。管理员账号不能通过注册页面创建。

- 普通用户：登录、估价、多轮会话、RAG 检索、户型图解析
- 管理员：普通用户全部权限，以及知识库文档上传、预览、删除和向量库重建

会话归属绑定到登录账号，不同账号无法读取彼此的会话。生产环境必须使用 HTTPS，并妥善保护 `.env` 和运行时数据目录。

## 测试

运行完整确定性测试：

```powershell
pytest -q
```

需要真实模型的测试默认跳过。显式启用：

```powershell
$env:RUN_LLM_TESTS='1'
python -m unittest tests.test_agent tests.test_workflow
```

## 项目结构

```text
.
├── app/                    # 应用源码
│   ├── agent/              # Tool Calling Agent
│   ├── rag/                # 文档加载、切片、检索和向量库
│   ├── tools/              # 确定性估价工具
│   ├── web/static/         # Web 页面和静态资源
│   └── workflow/           # LangGraph 多方法估价工作流
├── data/docs/              # RAG 知识源文档，可版本化
├── docs/                   # 架构、API、部署及历史决策文档
├── scripts/indexing/       # 文档整理和向量库构建脚本
├── scripts/deployment/     # Cloudflare Tunnel 启动脚本
├── tests/                  # 单元测试、工作流测试和测试夹具
├── run_*.py                # Python 命令行和服务入口
├── start_*.bat             # Windows 一键启动入口
├── requirements.txt        # 宽松依赖范围
├── requirements.lock       # 可复现依赖版本
└── .env.example            # 环境变量模板，不含真实凭证
```

运行时生成的 `data/sessions/`、`data/vector_db/`、`data/auth_users.json`、缓存和临时文件已由 `.gitignore` 排除。

## 文档索引

- [架构说明](docs/ARCHITECTURE.md)
- [API 接口](docs/API_ENDPOINTS.md)
- [贡献指南](CONTRIBUTING.md)
- [安全策略](SECURITY.md)
- [部署文档](docs/deployment/CLOUDFLARE.md)
- [历史计划与评审](docs/README.md)

## 数据和使用边界

武汉预设数据用于演示和估价流程验证，不能替代具体宗地定位、现场查勘、真实成交案例调查或正式估价报告。公网估价、RAG 和视觉接口会消耗模型 API 额度；正式对外服务前应配置 HTTPS、限流、日志审计和更完善的持久化账号系统。

## License

本项目采用 MIT License，详见 [LICENSE](LICENSE)。
