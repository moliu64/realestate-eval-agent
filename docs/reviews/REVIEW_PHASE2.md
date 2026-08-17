# Phase 2 代码审查意见与整改任务书

> **审查对象**：`D:\房地产估价agent` 的 Phase 2（Tool Calling + LangGraph）实现。
> **结论**：Phase 2 已验收通过（工具单测 4/4、端到端 3/3、规划书约束全部命中）。以下为**优化整改项**，非阻塞，但建议在进入 Phase 3 前完成，尤其 P1。
> **给实现方（codex）**：按第 5 节顺序逐条整改，每完成一条对照「验收方式」自测。

---

## 1. 🟠 P1 —— `server.py` 接的是 Phase 1 的 `answer`，Web 端没有工具调用能力

### 证据
- `app/server.py:10`：`from app.rag.chain import answer`
- `app/server.py:36`：`result = answer(request.question.strip())`

### 影响
`run_web.py` 启动的 Web 界面，`/api/ask` 走的是纯 RAG 问答链，**不会调用估价工具**。面试时若通过网页演示「估值计算」，会退化成「只检索、不计算」，等于 Phase 2 的核心能力在 Web 端完全没有暴露。这是本次最需要修的一处。

### 修复
`app/server.py` 改为调用 Phase 2 的 `agent_app`：

```python
# 替换 import
from app.agent.graph import agent_app

@app.post("/api/ask")
def ask(request: AskRequest) -> AskResponse:
    started = time.perf_counter()
    print(f"[api] ask started: {request.question[:40]}", flush=True)
    try:
        result = agent_app.invoke({
            "question": request.question.strip(),
            "context": "",
            "messages": [],
            "answer": "",
        })
        answer_text = result["answer"].replace("\u2212", "-")
        print(f"[api] ask finished in {time.perf_counter() - started:.2f}s", flush=True)
        return AskResponse(answer=answer_text)
    except Exception as exc:
        print(f"[api] ask failed in {time.perf_counter() - started:.2f}s: {exc}", flush=True)
        raise HTTPException(status_code=502, detail=str(exc)) from exc
```

> 顺带建议：异常统一用 `status_code=500`（502 是网关错误语义），`detail` 可改为固定文案避免向客户端泄露内部堆栈。此项可选。

### 验收方式
- [ ] 启动 `python run_web.py`，网页提问「某商铺年度稳定净收益60万元，资本化率5%，估值多少」，回答应含 `12000000` 与 `[来源: 02_income_approach.md]`（而非纯知识问答）。

---

## 2. 🟠 P2 —— HF 配置在三处入口不一致，直接跑 `run_agent.py` 可能卡在模型加载

### 证据
- `run_web.py:3`：`os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")`
- `run_agent.py` 与 `run_rag.py`：无任何 HF 相关环境变量设置。

### 影响
模型已缓存到本机，但 `sentence-transformers` 加载时仍会联网探测可选文件（如 `adapter_config.json`）；若本机连不上 HuggingFace，直接 `python run_agent.py "..."` 会超时重试卡住（验收时已复现）。`run_web.py` 靠镜像规避，另两个入口没有，行为不一致。

### 修复
统一在 `app/embeddings.py` 顶部（`import sentence_transformers` 之前）强制离线加载，并删除 `run_web.py` 里的镜像行：

```python
# app/embeddings.py 最顶部
import os

os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
```

> 注意：离线模式依赖模型已缓存；换机/首次下载时需临时设 `$env:HF_HUB_OFFLINE="0"` + `$env:HF_ENDPOINT="https://hf-mirror.com"` 重新下载一次。README 已说明镜像方式，保留即可。

### 验收方式
- [ ] 在未设任何 HF 环境变量的干净 shell 里，直接 `python run_agent.py "..."` 能秒级完成模型加载（不再出现 `Retrying ... huggingface.co` 超时）。

---

## 3. 🟡 P2 —— `test_agent.py` 硬编码只测 1 条，未消费 `agent_questions.jsonl`

### 证据
- `tests/agent_questions.jsonl`：定义了 3 条用例（收益法/市场比较法/成本法）。
- `tests/test_agent.py:9-19`：只硬编码测了收益法一条。

### 影响
回归用例数据和测试代码脱节，市场比较法、成本法两个场景没有自动化覆盖。

### 修复
让 `test_agent.py` 遍历 jsonl：

```python
import json
from pathlib import Path
import os
import unittest

from app.agent.graph import agent_app


@unittest.skipUnless(os.getenv("RUN_LLM_TESTS") == "1", "requires real LLM with tool calling")
class AgentEndToEndTest(unittest.TestCase):
    def test_all_valuation_scenarios(self):
        cases = [
            json.loads(line)
            for line in Path("tests/agent_questions.jsonl").read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        for case in cases:
            result = agent_app.invoke({
                "question": case["question"],
                "context": "",
                "messages": [],
                "answer": "",
            })
            norm = result["answer"].replace(",", "").replace("\u2212", "-")
            with self.subTest(question=case["question"]):
                self.assertIn(case["expected_value"], norm)
                self.assertIn(case["expected_source"], norm)
```

### 验收方式
- [ ] `$env:RUN_LLM_TESTS="1"; python -m unittest tests.test_agent` 三条用例全部通过。

---

## 4. 🟡 P2 —— README 未说明 Phase 2 测试命令与 `RUN_LLM_TESTS`

### 证据
`README.md:62-66` 只写了 `python -m unittest tests.test_retriever`，未提 `test_tools` 与 `test_agent`。

### 修复
在 README「检索自测」处补充：

```markdown
工具单测：

python -m unittest tests.test_tools

Agent 端到端（需真实 LLM，默认跳过）：

$env:RUN_LLM_TESTS="1"
python -m unittest tests.test_agent
```

### 验收方式
- [ ] 按 README 命令能分别跑通三个测试模块。

---

## 5. 🟡 P3 —— `run_agent.py` 用字符串替换规避 Unicode 减号，偏 hacky

### 证据
`run_agent.py:16`：`answer = result["answer"].replace("−", "-")`

### 影响
能跑，但只处理了 `−`(U+2212) 一种字符，其他 Unicode 符号（如全角括号、±）在 GBK 控制台仍可能崩。根本解法是统一 stdout 编码。

### 修复
在 `run_agent.py` 的 `main()` 开头加：

```python
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
```

之后 `.replace("−", "-")` 可保留（无害）或删除。若采用本方案，建议 `run_rag.py`、`server.py` 的日志输出也统一处理。

### 验收方式
- [ ] `python run_agent.py "某工业厂房土地价值100万元...用成本法估值多少"` 正常输出，不抛 `UnicodeEncodeError`。

---

## 6. ⚪ P3 —— 物理残留日志文件

### 证据
项目根存在 `server.err.log`、`server.out.log`（`.gitignore` 已用 `*.log` 覆盖，git 层面无问题）。

### 修复
顺手删除这两个文件即可（或保持，不影响）。

---

## 7. 整改清单（按顺序）

1. **P1**：`server.py` 改为调用 `agent_app`（第 1 节代码）。
2. **P2**：`embeddings.py` 顶部统一 `HF_HUB_OFFLINE=1`，删除 `run_web.py` 镜像行。
3. **P2**：`test_agent.py` 遍历 `agent_questions.jsonl`。
4. **P2**：README 补充工具/agent 测试命令。
5. **P3**：`run_agent.py` 加 `sys.stdout.reconfigure(encoding="utf-8")`。
6. **P3**：删除 `server.err.log` / `server.out.log`。

### 整改完成标准
- [ ] `python -m unittest tests.test_tools` 通过。
- [ ] `$env:RUN_LLM_TESTS="1"; python -m unittest tests.test_agent` 通过（3 条）。
- [ ] `python run_web.py` 网页问答能出工具计算结果。
- [ ] 干净 shell 直接 `python run_agent.py` 不再卡 HF 加载。
- [ ] 提交整改说明：逐条列改动 + 验收结果。

---

## 8. 保留的优点（不要破坏）

1. **工具设计**：3 个估价工具公式与知识库对齐、Pydantic schema 带中文 description、`cap_rate<=0` 返回错误文案而非抛异常。
2. **agent 编排**：`Annotated[list, add_messages]`、`bind_tools` + `ToolNode`、条件边、`MAX_TOOL_CALLS=5` 防死循环、system prompt 含单位换算（万→元、%→小数）。
3. **README 已较完整**：Phase 2 架构、面试讲解要点、HF 镜像/离线说明、实现决策记录（含 cosine 空间、`MIN_RELEVANCE_SCORE=0.5` 的理由）都齐了。
4. **测试分层合理**：工具用纯单元测试（不依赖 LLM，默认跑）、agent 端到端用 `RUN_LLM_TESTS` 门控（默认跳过），成本控制得当。
