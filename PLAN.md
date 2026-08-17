# 房地产评估智能体（RealEstate Eval Agent）——项目规划书

> **文档性质**：实现方（codex）的执行规格书。请严格按本文档落地，不要擅自更改已写死的技术决策；遇到本文档未覆盖的实现细节时，遵循"最小可用、可演示、可讲清楚"的原则自行决策，并在代码注释中说明。
>
> **角色**：顾问（规划方）已确定方向与约束；实现方（codex）负责编码落地与自测。

---

## 1. 项目背景与目标

### 1.1 定位
**求职 / 面试作品集**。目标不是生产级系统，而是一个能跑通、能演示、能对着面试官讲清楚核心机制（RAG、Tool Calling、任务编排、LLM 集成）的端到端项目。

### 1.2 一句话目标
构建一个围绕**房产估值**业务的智能体系统，完整能力链为：

```
理解需求 → 检索知识(RAG) → 调用评估工具(Tool Calling) → 多步流程编排(LangGraph) → 生成估价报告
```

### 1.3 与目标岗位能力的映射（面试讲解主线）
| 岗位要求 | 项目落点 |
|---|---|
| ① Agent 架构设计 | LangGraph 状态图：多节点编排（理解/检索/计算/报告） |
| ② 代码实现 | FastAPI 后端 + 数据处理脚本 + 向量库构建脚本 |
| ③ 大模型集成 | Prompt 模板工程 + RAG + 带引用回答 |
| ④ 工具调用与任务编排 | 评估计算工具（市场比较法/收益法/成本法）+ Tool Calling 循环 |
| ⑤ 协作与文档 | README、架构文档、演示脚本、讲解材料 |

### 1.4 当前阶段范围（已确认）
**先做 Phase 1：RAG 检索问答**。做到"输入问题 → 检索知识库 → 带来源引用的回答"全链路跑通，即可作为第一个面试演示点。Phase 2–5 见第 8 节预告，本次不实现。

---

## 2. 技术选型（写死，勿改）

| 项 | 选择 | 说明 |
|---|---|---|
| 语言 | Python 3.13 | 已确认 |
| Agent 框架 | LangChain + LangGraph | 已确认 |
| 向量库 | ChromaDB（持久化本地） | 轻量、开箱即用、适合 demo |
| LLM | **OpenAI 兼容接口**（chat） | 已确认，可切 DeepSeek / Qwen / GLM / OpenAI |
| Embedding | **本地 sentence-transformers（BGE 中文模型）** | 见下方"坑点 1"：兼容端点不一定提供 embedding API |
| 后端框架 | FastAPI + uvicorn | Phase 4 才引入，Phase 1 不装 |
| 配置 | python-dotenv（.env） | 密钥与路径不进代码仓库 |

### 2.1 依赖清单（Phase 1 用，写入 `requirements.txt`）
```
langchain>=0.3
langchain-openai>=0.3
langchain-chroma>=0.2
chromadb>=0.5
sentence-transformers>=3.0
python-dotenv>=1.0
```
> 说明：`langgraph`、`langchain-community` 可在 Phase 3 再加，但允许提前安装不影响 Phase 1。安装后用 `pip freeze > requirements.lock` 锁定实际版本。

### 2.2 LLM 接入配置（OpenAI 兼容）
`.env` 中通过三个变量控制，`langchain-openai` 的 `ChatOpenAI` 直接读取：
```env
OPENAI_BASE_URL=<供应商兼容端点>
OPENAI_API_KEY=<你的 key>
LLM_MODEL=<模型名>
```
常见兼容端点参考（实现方按实际 key 选择其一填入）：
| 供应商 | OPENAI_BASE_URL | LLM_MODEL 示例 |
|---|---|---|
| DeepSeek | https://api.deepseek.com | deepseek-chat |
| 通义 Qwen | https://dashscope.aliyuncs.com/compatible-mode/v1 | qwen-plus |
| 智谱 GLM | https://open.bigmodel.cn/api/paas/v4 | glm-4 |
| OpenAI | （留空走默认） | gpt-4o-mini |

### 2.3 Embedding 选型
默认模型：`BAAI/bge-small-zh-v1.5`（中文、轻量、CPU 可跑、首次自动下载）。若追求更强效果可改 `BAAI/bge-m3`，但需确认机器内存足够。

---

## 3. 整体架构与目录结构

### 3.1 架构（Phase 1 范围内）
```
用户提问
   │
   ▼
[ retriever ]  ── 查询向量化 → ChromaDB 相似度检索 → top-k 片段 + 来源
   │
   ▼
[ prompt 模板 ]  ── 系统角色(资深房地产估价师) + 检索上下文 + 用户问题
   │
   ▼
[ LLM ]  ── 生成带 [来源: 文件名] 引用的回答
```

### 3.2 目录结构（按此创建，勿增删顶层模块）
```
realestate-eval-agent/
├── .env.example          # 配置模板（含注释说明，不含真实 key）
├── .gitignore            # 忽略 .env、data/vector_db/、__pycache__/ 等
├── README.md             # 项目说明 + 快速开始
├── PLAN.md               # 本规划书
├── requirements.txt      # 依赖清单
├── run_rag.py            # 演示入口：python run_rag.py "你的问题"
├── app/
│   ├── __init__.py
│   ├── config.py         # 配置加载（读 .env）
│   ├── llm.py            # ChatOpenAI 客户端封装
│   ├── embeddings.py     # 本地 BGE embedding 封装
│   └── rag/
│       ├── __init__.py
│       ├── loader.py     # 文档加载
│       ├── splitter.py   # 文档切分
│       ├── vectorstore.py# 向量库构建/加载
│       ├── retriever.py  # 检索
│       └── chain.py      # RAG 问答链（检索 + 生成）
├── scripts/
│   ├── build_index.py    # 一键构建向量库（加载→切分→写入 ChromaDB）
│   └── make_docs.py      # 生成/校验知识库示例文档（可选）
├── data/
│   ├── docs/             # 知识库 Markdown（4–8 篇）
│   └── vector_db/        # ChromaDB 持久化目录（脚本生成）
└── tests/
    ├── test_retriever.py # 检索单元测试
    └── eval_questions.jsonl  # 评估问题集（10 条，用于人工打分回归）
```

### 3.3 关键模块接口约定（实现方必须对齐的函数签名）
| 模块 | 函数 | 约定 |
|---|---|---|
| `app/config.py` | `load_config() -> Config` | 返回含 base_url/api_key/model/embedding_model 等字段 |
| `app/llm.py` | `get_chat_model() -> BaseChatModel` | 单例，用 `.env` 参数构建 `ChatOpenAI` |
| `app/embeddings.py` | `get_embeddings() -> Embeddings` | 单例，`HuggingFaceEmbeddings`，缓存避免重复加载 |
| `app/rag/loader.py` | `load_docs(docs_dir: str) -> list[Document]` | 加载目录下全部 .md |
| `app/rag/splitter.py` | `split_docs(docs: list[Document]) -> list[Document]` | 按 2.4 参数切分 |
| `app/rag/vectorstore.py` | `build_vectorstore(docs, persist_dir) -> Chroma` / `load_vectorstore(persist_dir) -> Chroma` | 持久化读写 |
| `app/rag/retriever.py` | `retrieve(query: str, k: int = 4) -> list[tuple[Document, float]]` | 返回 (文档, 相似度分) |
| `app/rag/chain.py` | `answer(question: str) -> str` | 最终带引用回答 |

### 3.4 关键参数（写死）
| 参数 | 值 | 备注 |
|---|---|---|
| chunk_size | 500（字符） | 中文按字符切分 |
| chunk_overlap | 50（字符） | 避免切断上下文 |
| 检索 top-k | 4 | 相似度检索 |
| 检索距离 | cosine | ChromaDB 默认 |
| 切分依据 | 按 Markdown 标题层级（HeaderTextSplitter）或段落边界 | 不得切断估价公式/表格 |

---

## 4. Phase 0：环境与脚手架

### 任务
1. 创建第 3.2 节的完整目录结构。
2. 编写 `requirements.txt`、`.env.example`、`.gitignore`。
3. 安装依赖（建议 venv 虚拟环境）。
4. 编写 `app/config.py`、`app/llm.py`，并验证 LLM 连通。

### 验收标准（全部通过才算完成）
- [ ] `pip install -r requirements.txt` 无报错。
- [ ] 运行连通性测试：`get_chat_model().invoke("用一句话解释什么是市场比较法")` 返回非空文本。
- [ ] `.env` 中真实 key 已配置且 `.gitignore` 已排除 `.env`。
- [ ] `python -c "from app.llm import get_chat_model; ..."` 可导入不报错。

---

## 5. Phase 1：RAG 检索问答（本次核心，逐步规格）

### 步骤 1 — 准备领域知识库
- 在 `data/docs/` 放入 **4–8 篇** Markdown，建议覆盖：
  1. 市场比较法（定义、适用场景、计算公式与步骤）
  2. 收益法（资本化率、净收益、折现）
  3. 成本法（重置成本、折旧）
  4. 估价技术规范与流程（估价目的、估价时点、报告要件）
  5. 常见税费与政策（契税、增值税、土地增值税等）
  6. FAQ（常见业务问答）
- 每篇几百字即可，**标题层级清晰（#/##）**，利于切分。
- 验收：`data/docs/` 下 .md 文件数在 4–8 之间，内容中文、结构规范。

### 步骤 2 — 文档加载与切分
- `loader.py` 读取全部 .md，`splitter.py` 按第 3.4 节参数切分。
- 验收：打印前 3 个 chunk，确认**没有把公式/表格/完整段落切断**。

### 步骤 3 — Embedding 与向量库
- `embeddings.py` 用 `HuggingFaceEmbeddings` 加载 BGE 中文模型（本地缓存）。
- `vectorstore.py` 用 `Chroma.from_documents(...)` 写入并持久化到 `data/vector_db/`。
- `scripts/build_index.py` 一键完成「加载→切分→写库」，支持增量重建。
- 验收：重复运行 `build_index.py` 后，`load_vectorstore()` 能读回且文档数量正确。

### 步骤 4 — 检索链路
- `retriever.py` 实现 `retrieve(query, k=4)`，返回 top-k 片段 + 来源 + 相似度分。
- 验收：拿 3 个已知问题，检索结果命中预期文档（人工核对）。

### 步骤 5 — 生成带引用的回答
- `chain.py` 组装 Prompt：
  - 系统角色 = 资深房地产估价师；
  - 指令 = 只能依据给定上下文回答、必须标注来源、答不出就明说、不要编造。
  - 用户消息 = `{检索到的上下文}\n\n问题：{question}`。
- 输出格式约定：回答末尾或句内标注 `[来源: <文件名>]`。
- 验收：对"收益法的资本化率怎么确定"这类问题，给出有依据且带来源的回答。

### 步骤 6 — 演示入口与评估
- `run_rag.py`：`python run_rag.py "你的问题"` 直接打印最终回答。
- `tests/eval_questions.jsonl`：准备 10 条测试问题，作为回归用例。
- 验收：一条命令跑通「提问→检索→带引用回答」，可作为首个面试演示点。

### Phase 1 总体验收
- [ ] 全链路一条命令跑通。
- [ ] 回答带来源引用，无依据时能诚实说"没有找到相关依据"。
- [ ] 检索命中率人工评估达到满意（≥ 7/10 命中预期文档）。
- [ ] `git`（若可用）或手动备份：代码 + 文档 + 演示脚本齐全。

---

## 6. 关键坑点清单（实现方必须遵守）

1. **Embedding 与 chat 分离**：OpenAI 兼容端点（尤其 DeepSeek）通常**不提供 embedding 接口**，故 embedding 必须走本地 `sentence-transformers`，不要尝试用兼容端点做 embedding。
2. **中文切分按字符**：`chunk_size=500` 指字符数，不是 token；注意别切断估价公式与表格。
3. **LangChain 版本兼容**：用 `langchain-openai`（新包），不要用旧教程里的 `langchain.chat_models.ChatOpenAI`；`langchain` / `langchain-openai` / `langchain-chroma` 版本要匹配，装完锁版本。
4. **embedding 模型首次下载**：`bge-small-zh-v1.5` 首次运行会从 HuggingFace 下载，若网络受限需配置镜像 `HF_ENDPOINT=https://hf-mirror.com`。
5. **密钥安全**：真实 key 只放 `.env`，`.gitignore` 必须排除 `.env` 与 `data/vector_db/`。
6. **单例缓存**：embedding 模型和 LLM 客户端用单例（模块级缓存），避免每次调用重复加载模型。
7. **诚实性**：Prompt 必须约束"答不出就明说"，防止幻觉——这是面试时会被追问的点。

---

## 7. 交付物清单（最终）

| 交付物 | 说明 |
|---|---|
| 可运行代码 | Phase 1 RAG 全链路 |
| `requirements.txt` + `requirements.lock` | 依赖与锁定版本 |
| `data/docs/` | 4–8 篇评估领域知识 |
| `scripts/build_index.py` | 一键建库脚本 |
| `run_rag.py` | 演示入口 |
| `tests/` | 检索测试 + 10 条评估问题集 |
| `README.md` | 快速开始 + 架构说明 |
| `PLAN.md` | 本规划书（随项目留存） |

---

## 8. 后续阶段预告（本次不实现，供全局视野）

| 阶段 | 内容 | 验收要点 |
|---|---|---|
| Phase 2 Tool Calling | 评估计算工具（市场比较法/收益法/成本法）+ 工具调用循环 | LLM 能正确选工具并回流计算结果 |
| Phase 3 任务编排 | LangGraph 状态图：理解需求→检索→计算→报告多节点 | "帮我评估一套房"自动拆多步执行 |
| Phase 4 前后端服务 | FastAPI 接口 + Gradio/简单 Web 演示界面 | 通过 HTTP 调用完整评估流程 |
| Phase 5 打磨与文档 | 架构文档、演示脚本、面试讲解材料 | 能 15 分钟讲清全部 5 条能力 |

---

## 9. 给实现方（codex）的执行约定

1. 按 Phase 0 → Phase 1 顺序推进，**每完成一步对照该步验收标准自测**。
2. 优先保证"跑通"，其次才是"跑好"；demo 的可演示性 > 过度工程。
3. 遇到本文档未覆盖的决策，选**最小可用方案**，并在代码注释或 README 里记录理由。
4. 完成后提交一份简短交付说明：已实现功能、如何运行、每个验收项的通过情况。
