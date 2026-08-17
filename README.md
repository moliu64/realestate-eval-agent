# 房地产评估智能体

Phase 1 实现了一个可演示的 RAG 检索问答链路：读取房地产估价领域 Markdown 知识库，构建本地 Chroma 向量库，检索相关片段，并通过 OpenAI 兼容 chat 模型生成带来源引用的回答。

## 快速开始

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
```

若要完全复现当前环境，可改用锁定版本安装：

```powershell
pip install -r requirements.lock
```

编辑 `.env`，填入 `OPENAI_API_KEY`、`OPENAI_BASE_URL` 和 `LLM_MODEL`。Embedding 使用本地 `sentence-transformers` 模型，不依赖 chat 供应商的 embedding API。
`LLM_TIMEOUT_SECONDS` 控制模型调用超时时间，默认 60 秒。

图片入库使用通义千问 VL：按 `.env.example` 配置 `VISION_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1`、`VISION_API_KEY` 和 `VISION_MODEL=qwen-vl-plus`。视觉模型只处理图片，文本问答仍使用 `OPENAI_*` 配置；未配置视觉 key 时，图片入库会给出明确提示。

如果 HuggingFace 访问超时，先配置镜像再构建向量库：

```powershell
$env:HF_ENDPOINT="https://hf-mirror.com"
```

模型已缓存到本机后，项目默认使用离线加载；也可以在 shell 中显式设置：

```powershell
$env:HF_HUB_OFFLINE="1"
$env:TRANSFORMERS_OFFLINE="1"
```

首次换机或需要重新下载模型时，临时关闭离线并使用镜像下载一次：

```powershell
$env:HF_HUB_OFFLINE="0"
$env:TRANSFORMERS_OFFLINE="0"
$env:HF_ENDPOINT="https://hf-mirror.com"
```

构建向量库：

```powershell
python scripts/make_docs.py
python scripts/build_index.py --rebuild
```

运行问答：

```powershell
python run_rag.py "收益法的资本化率怎么确定"
```

运行 Web UI：

```powershell
python run_web.py
```

打开 `http://127.0.0.1:8000`。
Web UI 会展示 Markdown 估价报告、工作流执行过程时间线，并在“结构化数据”面板提供同一结果的 JSON 输出，方便面试演示和下游系统集成。

### 前后端独立启动

Windows 下可直接双击根目录的 `start_backend.bat` 和 `start_frontend.bat`。先启动后端，再启动前端；前端会自动打开浏览器。

也可以分别从终端启动：

```powershell
# 终端 1：FastAPI，默认 http://127.0.0.1:8000
python run_backend.py

# 终端 2：静态前端，默认 http://127.0.0.1:5173
python run_frontend.py
```

独立前端通过 `BACKEND_URL` 调用后端；后端通过 `CORS_ORIGINS` 限制允许访问的前端来源。线上分域部署时应在 `.env` 中把这两个值改为实际 HTTPS 地址，并设置 `FRONTEND_OPEN_BROWSER=0`。原 `python run_web.py` 一体化入口继续保留。

首页以估值工作台为主：估值表单调用 `/api/evaluate`，结构化填写估价因素和计算参数；左侧支持上传户型图并调用 `/api/analyze-layout`。知识检索通过右上角搜索按钮打开独立面板并调用 `/api/rag`，不会中断估值输入。原 `/api/ask` 自由文本估值接口继续保留兼容。

选择武汉区域和 2019—2024 数据年份后，可在“计算参数”中载入区域年份预设。预设以武汉市人民政府 2023 基准地价和国家统计局武汉二手住宅销售价格指数为官方基准；区级代表地价映射、可比单价、净收益、资本化率、重置成本与折旧包含公式推导或可编辑估值假设，不能替代具体宗地地价图定位和真实可比成交调查。

先在 `.env` 配置随机的 `ADMIN_TOKEN`。点击估值首页右下角“管理入口”，输入正确密钥后会转到后端知识库管理页；密钥错误会在入口弹层中提示。管理页按“估价方法、市场数据、政策法规、估价规范、业务知识、用户资料”生成中文文件名，支持 `.md`、`.txt`、`.csv`、`.pdf`、`.docx`、`.png`、`.jpg`、`.jpeg` 的上传、切分预览、覆盖更新、列出和删除；每次变更都会自动重建向量库，单文件上限 20MB。

部署时使用：

```powershell
uvicorn app.server:app --host 0.0.0.0 --port 8000
```

生产环境建议在 Nginx/Caddy 后使用 HTTPS，并将 `data/vector_db` 和 `data/docs` 持久化；Torch、Transformers 和本地 embedding 模型占用空间较大，建议至少 4 核 CPU、8GB RAM。多 worker 会各自加载模型，资源有限时保持单 worker。

运行 Phase 2 工具调用 Agent：

```powershell
python run_agent.py "某商铺年度稳定净收益60万元，资本化率5%，适合用什么方法估值，估值多少？"
```

运行 Phase 3 多节点估价工作流：

```powershell
python run_eval.py "帮我评估一套100平方米二手住宅，有近期可比成交单价20000元/平方米；同时年租金净收益8万元，资本化率4%，请做多方法校核。"
```

检索自测：

```powershell
python -m unittest tests.test_retriever
```

工具单测：

```powershell
python -m unittest tests.test_tools
```

Agent 端到端测试需要真实 LLM，默认跳过：

```powershell
$env:RUN_LLM_TESTS="1"
python -m unittest tests.test_agent
```

Phase 3 工作流端到端测试同样需要真实 LLM：

```powershell
$env:RUN_LLM_TESTS="1"
python -m unittest tests.test_workflow
```

## 架构

```text
用户问题 -> Chroma 相似度检索 -> Prompt 注入上下文 -> ChatOpenAI 生成带来源回答
```

Phase 2 增加 Tool Calling 编排：

```text
用户问题 -> retrieve -> agent(bind_tools) -> ToolNode -> agent -> finalize
```

Phase 3 增加显式多节点估价工作流：

```text
START -> understand -> plan -> next_method
                         |         |
                         |         v
                         |      retrieve -> compute
                         |         ^          |
                         v         |          v
                      verify <- next_method <-+
                         |
                         v
                      report -> END
```

核心模块：

- `app/config.py`：读取 `.env` 并提供配置对象。
- `app/embeddings.py`：封装本地 BGE 中文 embedding，模块级单例缓存。
- `app/rag/loader.py`：按扩展名加载 Markdown、PDF、Word，并将图片交给 Qwen-VL 描述后入库。
- `app/vision.py`：通义千问 VL 的 DashScope OpenAI-compatible 适配层，负责图片压缩和 base64 消息封装。
- `app/rag/splitter.py`：优先在段落和句子边界切分，目标 500 字；所有相邻片段按前一片长度保留 10% 重叠，并记录起止位置和重叠元数据。
- `app/rag/vectorstore.py`：构建和加载持久化 Chroma 向量库。
- `app/rag/retriever.py`：返回 top-k 文档片段与相似度分。
- `app/rag/chain.py`：组织 RAG Prompt 并调用 LLM。
- `app/tools/valuation.py`：市场比较法、收益法、成本法三个确定性计算工具。
- `app/agent/graph.py`：LangGraph 工具调用循环，复用 Phase 1 检索和 LLM。
- `app/workflow/graph.py`：Phase 3 多节点工作流，自动完成需求理解、方法规划、逐方法检索计算、交叉校核和报告生成。
- `app/server.py`：问答 API、工作流过程输出，以及带 `X-Admin-Token` 鉴权的知识库管理 API。
- `app/presets.py`：武汉区域、年份和用途预设，区分官方基准、公式推导与估值假设。

## 项目结构

```text
.
├── .github/workflows/   # GitHub Actions 持续集成
├── app/                 # API、Agent、RAG、估价工作流与 Web 静态资源
├── data/docs/           # 可入库的估价知识文档
├── docs/                # 规划、评审和数据参考资料
├── scripts/             # 文档校验与向量库构建脚本
├── tests/fixtures/      # 自动化测试数据
├── tests/               # 单元、检索和工作流测试
├── run_*.py             # 本地 CLI 与 Web 启动入口
├── requirements.txt     # 兼容版本范围
└── requirements.lock    # 可复现的锁定依赖
```

`output/`、`data/vector_db/`、本地虚拟环境、测试截图和运行日志均为可再生成内容，不纳入版本控制。历史实施资料索引见 [`docs/README.md`](docs/README.md)。

## Phase 2 面试讲解要点

- LLM 负责判断估价方法、抽取参数和组织语言，Python 工具负责精确计算。
- RAG 提供方法口径和来源引用，Tool Calling 提供可复核的数值过程。
- LangGraph 通过 `agent -> tools -> agent` 循环让工具结果回流，再生成最终回答。
- 工具 schema 明确金额单位为元、百分比转小数，降低模型填参错误。

## Phase 3 面试讲解要点

- Phase 3 把单次工具调用升级为显式估价流程：需求理解、方法规划、方法队列循环、交叉校核、报告生成。
- `computations` 使用 `Annotated[list, operator.add]` 累加 reducer，确保多方法计算结果不会互相覆盖。
- 每轮 `compute` 只绑定当前方法对应的唯一工具，降低 LLM 选错工具的风险。
- 缺关键参数时不强行计算，会把缺失项写入计算结果和报告限制条件。
- 报告骨架由代码固定，LLM 负责校核说明等自然语言部分，兼顾稳定结构和表达质量。

## Phase 4 面试讲解要点

- 后端使用 `workflow_app.stream(..., stream_mode="updates")` 捕获 LangGraph 节点更新，把需求理解、方法规划、检索、计算和校核转换成可观察步骤。
- Web 端在报告上方展示执行过程时间线，计算步骤会标出方法、工具结果和数值，便于说明 agent 的任务编排过程。
- 报告节点同时输出 Markdown 和确定性 JSON：Markdown 给人阅读，JSON 给系统集成，且 JSON 不依赖 LLM 二次结构化。

## 实现决策记录

- 文档切分优先寻找段落、换行和中文标点边界；每个后续片段从前一片末尾向前回退约 10%，确保 PDF 页边界、Word 段落和普通文本在检索时保留相邻上下文。
- PLAN 指定 `HuggingFaceEmbeddings`。为减少 LangChain 周边包版本兼容风险，当前用 `sentence-transformers` 直接实现 LangChain `Embeddings` 接口，仍然满足“本地 BGE embedding、单例缓存、chat 与 embedding 分离”的约束。
- `scripts/build_index.py --rebuild` 默认删除旧向量库后重建，保证重复运行时文档数量可核对；不传 `--rebuild` 时保留目录并写入当前文档集合。
- Chroma collection 显式使用 cosine 向量空间，和 PLAN 第 3.4 节的检索距离约定一致。
- `MIN_RELEVANCE_SCORE` 默认设为 `0.5`。这是 cosine 空间下的最小可用阈值，用于过滤跨领域弱相关片段；需要更宽松召回时可在 `.env` 中调低。
