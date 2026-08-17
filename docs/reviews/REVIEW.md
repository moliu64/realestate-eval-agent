# 房地产评估智能体 —— 代码审查意见与整改任务书

> **审查对象**：`D:\房地产估价agent`（codex 交付的 Phase 1 RAG 实现）
> **审查方式**：通读全部源码 / 知识库 / 测试 / 依赖锁文件，并用两条硬证据做实关键结论（① 向量库 sqlite 的 `schema_str`；② `langchain-core` / `langchain-chroma` 源码）。
> **结论**：整体质量高，可验收；存在 1 个需整改的实质问题（P1）+ 若干健壮性/可复现性优化（P2/P3）。
> **给实现方（codex）**：按「整改清单」第 7 节顺序逐条修复，每完成一条对照该条的「验收方式」自测。

---

## 1. 总评

目录结构、模块拆分、函数签名、测试、评估问题集、README「实现决策记录」均对齐 `PLAN.md`，且正确规避了「OpenAI 兼容端点无 embedding API」这个最大坑（本地 BGE + OpenAI 兼容 chat 分离做对了）。

保留的优点（不要破坏）：
- 模块化与单例缓存（`app/llm.py`、`app/embeddings.py` 的 `lru_cache`）。
- README 的「实现决策记录」——主动记录对 PLAN 的偏离及理由，工程意识强。
- 知识库 6 篇专业且结构化，`06_faq.md` 内置「面试演示如何讲清楚」。
- 安全意识到位：`llm.py` 校验占位 key，`.gitignore` 排除 `.env` 与 `data/vector_db/`。

---

## 2. 🔴 P1 —— 向量空间用了 `l2`，违背 PLAN 的 `cosine` 约定，阈值语义失真

### 证据
1. `data/vector_db/chroma.sqlite3` 中 `collections` 表的 `schema_str` 字段明确写有 `"space":"l2"`，且 `config_json_str` 为 `{}`（说明建库时未显式指定 space，落入 Chroma 默认值 `l2`）。
2. `app/rag/vectorstore.py` 的 `Chroma.from_documents(...)` 与 `Chroma(...)` 均未传 `collection_metadata`。
3. `langchain_chroma/vectorstores.py:928-933`：`distance == "l2"` → 选用 `_euclidean_relevance_score_fn`；`distance == "cosine"` 才会选 `_cosine_relevance_score_fn`。
4. `langchain_core/vectorstores/base.py:388`：l2 的分数 = `1.0 - distance / sqrt(2)`；`base.py:393`：cosine 的分数 = `1.0 - distance`。

### 影响
`retrieve()` 返回的「相似度分」不是 cosine 相似度，而是 `1 - l2距离/√2`。由于 embedding 已归一化（`app/embeddings.py` 中 `normalize_embeddings=True`），二者换算关系为：

```
score_l2 = 1 - √(1 - cos)
```

代入 `MIN_RELEVANCE_SCORE=0.35`（`app/config.py:31`）：

```
1 - √(1 - cos) ≥ 0.35   →   cos ≥ 0.5775
```

即 `.env` 里写的「保留相似度 ≥ 0.35」实际效果是「只保留 cosine ≥ 0.58」，比预期严格得多，会误杀中等相关片段。PLAN 第 3.4 节写死的是 `cosine`，实现静默偏离。

### 修复（可直接抄）
修改 `app/rag/vectorstore.py`，构建与加载两处都显式指定 cosine：

```python
# build_vectorstore 内：
return Chroma.from_documents(
    documents=docs,
    embedding=get_embeddings(),
    persist_directory=str(path),
    collection_name=COLLECTION_NAME,
    collection_metadata={"hnsw:space": "cosine"},   # ← 新增
)

# load_vectorstore 内：
return Chroma(
    persist_directory=str(path),
    embedding_function=get_embeddings(),
    collection_name=COLLECTION_NAME,
    collection_metadata={"hnsw:space": "cosine"},   # ← 新增
)
```

### 验收方式
- [ ] 改后运行 `python scripts/build_index.py --rebuild`（**必须 rebuild**，space 是建库时写入的，改代码不会作用于旧库）。
- [ ] 用 sqlite 复查：`collections.schema_str` 中 `"space"` 已变为 `"cosine"`。
- [ ] `python -m unittest tests.test_retriever` 通过。

---

## 3. 🟠 P2 —— 用「压 warning」掩盖根因

### 证据
`app/rag/retriever.py:11-16` 用 `warnings.catch_warnings` + `filterwarnings` 静默掉 `"Relevance scores must be between 0 and 1.*"`。

### 影响
这个 warning 正是「分数越界/语义不对」的信号。压掉它等于把问题藏起来，后续任何分数异常都会变成「看不见的雷」。根因在 P1，应在修掉 P1 后删除此 hack。

### 修复
修完 P1 后，把 `retrieve()` 简化为：

```python
def retrieve(query: str, k: int = 4) -> list[tuple[Document, float]]:
    config = load_config()
    vectorstore = load_vectorstore(config.vector_db_dir)
    return vectorstore.similarity_search_with_relevance_scores(query, k=k)
```

并删除 `import warnings`（`app/rag/retriever.py:2`）。

### 验收方式
- [ ] 删除压制后运行检索，无 `Relevance scores must be between 0 and 1` warning 输出（若仍出现，说明 embedding 归一化或 space 仍有问题，回到 P1 排查）。

---

## 4. 🟠 P2 —— 相对路径依赖 CWD，离开项目根运行即失败

### 证据
`app/config.py:28-29` 将 `DOCS_DIR`、`VECTOR_DB_DIR` 存为相对路径；`run_rag.py` 只做了 `sys.path.insert`，未做 `os.chdir`。从任意目录执行 `python D:\房地产估价agent\run_rag.py "..."` 会 `FileNotFoundError`。

### 影响
换目录演示、被其他脚本调用、CI 运行都会挂。求职 demo 换机器/换目录演示时是硬伤。

### 修复
在 `app/config.py` 中基于项目根解析路径：

```python
PROJECT_ROOT = Path(__file__).resolve().parents[1]  # app/ 的上一级即项目根

def _resolve(p: str) -> str:
    path = Path(p)
    return str(path if path.is_absolute() else PROJECT_ROOT / path)
```

`load_config()` 内改为：

```python
docs_dir = _resolve(os.getenv("DOCS_DIR", "data/docs"))
vector_db_dir = _resolve(os.getenv("VECTOR_DB_DIR", "data/vector_db"))
```

### 验收方式
- [ ] 在项目根以外的任意目录执行 `python D:\房地产估价agent\run_rag.py "收益法的资本化率怎么确定"`，能正常返回（不报 FileNotFoundError）。

---

## 5. 🟡 P3 —— 每次检索都重建 vectorstore 客户端

### 证据
`app/rag/retriever.py:10` 每次调用 `load_vectorstore()`；`tests/test_retriever.py` 遍历 10 条问题即重复加载 10 次（每次重连 sqlite、重新拿 collection）。

### 影响
低效，测试变慢，检索链路有大量无谓开销。

### 修复
给 `load_vectorstore` 加缓存（embedding 已是单例，vectorstore 同样可复用；demo 单线程场景安全）：

```python
from functools import lru_cache

@lru_cache(maxsize=1)
def load_vectorstore(persist_dir: str) -> Chroma:
    ...
```

### 验收方式
- [ ] 连续两次 `retrieve` 不会重复触发 Chroma 客户端重建（可打印日志或在 `load_vectorstore` 内加一次性 print 观察只打印一次）。

---

## 6. 🟡 P3 —— 依赖声明与锁定版本脱节 + 模型未缓存

### 6.1 依赖脱节
- 证据：`requirements.txt` 写 `langchain>=0.3`，但 `requirements.lock` 实际锁的是 `langchain==1.3.15`、`langchain-openai==1.5.1`、`langchain-chroma==1.1.0`（1.x 主版本）。
- 影响：换机器 `pip install -r requirements.txt` 会装到完全不同的主版本，可能跑挂。
- 修复（二选一）：
  - 收紧 `requirements.txt`（例如 `langchain>=1.3,<2`、`langchain-openai>=1.5,<2`、`langchain-chroma>=1.1,<2`）；或
  - README 明确「以 `pip install -r requirements.lock` 为准」。

### 6.2 embedding 模型未缓存
- 证据：实测重新跑检索时 `sentence-transformers` 尝试从 `huggingface.co` 下载 `BAAI/bge-small-zh-v1.5` 并超时（`WinError 10060`），说明建库时的模型缓存不在当前可复用位置。
- 影响：离线/换机无法复现，演示有风险。
- 修复：README「快速开始」补充网络受限时的镜像配置：

  ```powershell
  $env:HF_ENDPOINT="https://hf-mirror.com"
  ```

  或将模型固定到本地目录并在 README 说明存放位置。

---

## 7. 整改清单（按此顺序执行）

1. **P1**：`vectorstore.py` 显式 `collection_metadata={"hnsw:space": "cosine"}`（构建 + 加载两处）→ `--rebuild` 重建 → 复查 sqlite space 为 cosine。
2. **P2**：删除 `retriever.py` 的 warning 压制 → 复跑检索确认无 warning。
3. **P2**：`config.py` 用 `Path(__file__)` 锚定绝对路径。
4. **P3**：`load_vectorstore` 加 `@lru_cache`。
5. **P3**：`requirements.txt` 与 lock 对齐；README 补 HF 镜像说明。
6. 顺手项（不阻塞验收）：
   - `scripts/make_docs.py` 纳入流程或删除。
   - `build_index.py:34` 与 `test_retriever.py:14` 的私有 API `_collection.count()` 评估是否替换为公开方法。

### 整改完成标准
- [ ] P1–P3 全部修复，`python -m unittest tests.test_retriever` 通过。
- [ ] 从项目根外目录运行 `run_rag.py` 正常。
- [ ] 检索无 relevance score warning。
- [ ] 提交一条整改说明：逐条列出改了什么、验收方式的结果。
