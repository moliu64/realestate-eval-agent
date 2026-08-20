# 房地产估价智能体

面向武汉房地产估价场景的 RAG + LangGraph 应用。系统将本地知识库、确定性估价工具、通义千问视觉模型和 OpenAI 兼容文本模型组合为可追踪的多方法估价工作流。

在线地址：[https://060115.top](https://060115.top)

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

ADMIN_TOKEN=自定义高强度管理密钥
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

Windows 登录任务 `RealEstateAgentOnline` 会自动执行同一脚本。详细拓扑、凭证位置和故障检查见 [Cloudflare 部署文档](docs/deployment/CLOUDFLARE.md)。

## 知识库管理

点击估值首页右下角“管理入口”，输入 `.env` 中的 `ADMIN_TOKEN` 后进入管理页。

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
│   └── vector_db/            # 本地生成，不提交 Git
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

## 数据说明

武汉预设以武汉市人民政府基准地价和国家统计局住宅价格指数为官方基准。区级代表地价映射、可比单价、净收益、资本化率、重置成本和折旧仍包含公式推导或可编辑估值假设，不能替代具体宗地定位、现场查勘和真实成交案例调查。

公网估值、RAG 和视觉接口会消耗模型 API 额度。正式对外推广前应在 Cloudflare 配置限流或 Turnstile。
