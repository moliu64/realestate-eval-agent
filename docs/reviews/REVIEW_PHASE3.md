# Phase 3 代码审查意见与整改任务书

> **审查对象**：`D:\房地产估价agent` 的 Phase 3（多节点任务编排 + 多方法校核 + 结构化报告）。
> **结论**：Phase 3 已验收通过（单测 7/7、端到端 3/3、报告八段结构完整）。以下为收尾整改项，核心是把 Web 端从 Phase 2 升级到 Phase 3。
> **给实现方（codex）**：按第 5 节顺序整改，每完成一条对照「验收方式」自测。

---

## 1. 🟠 P1 —— Web 端仍接 Phase 2，未呈现 Phase 3 完整工作流

### 证据
- `app/server.py:9`：`from app.agent.graph import agent_app`（Phase 2 图）
- `app/server.py:36-43`：`agent_app.invoke(...)` 返回 Phase 2 的自然语言回答
- `app/web/static/app.js:54`：`answerEl.textContent = payload.answer`（纯文本塞入，不渲染 Markdown）
- `app/web/static/index.html:47`：`<div class="mode-pill">RAG</div>`；`:44` 标题「房地产估价问答」；`:62-64` 示例问题仍是 Phase 1 RAG 风格

### 影响
这是本次最重要的一条：**面试演示时 Web 界面只能做「单一工具问答」，看不到 Phase 3 的「估价工作流 + 多方法校核 + 结构化报告」**——而后者才是岗位核心能力的最终呈现。Phase 3 现在只能靠命令行 `run_eval.py` 演示，Web 端没有跟上。

### 修复（分三步）

#### 1a. `server.py` 切换到 `workflow_app`
```python
# 替换 import
from app.workflow.graph import workflow_app

WORKFLOW_INIT = {
    "question": "",
    "requirement": {},
    "methods": [],
    "params": {},
    "current_method": "",
    "context": "",
    "computations": [],
    "verification": "",
    "report": "",
    "messages": [],
    "loop_count": 0,
}

@app.post("/api/ask")
def ask(request: AskRequest) -> AskResponse:
    started = time.perf_counter()
    print(f"[api] ask started: {request.question[:40]}", flush=True)
    try:
        init = dict(WORKFLOW_INIT, question=request.question.strip())
        result = workflow_app.invoke(init)
        report = result["report"].replace("\u2212", "-")
        print(f"[api] ask finished in {time.perf_counter() - started:.2f}s", flush=True)
        return AskResponse(answer=report)
    except Exception as exc:
        print(f"[api] ask failed in {time.perf_counter() - started:.2f}s: {exc}", flush=True)
        raise HTTPException(status_code=500, detail="问答服务暂时不可用，请稍后重试。") from exc
```
> 说明：`workflow_app.invoke` 是同步调用，FastAPI 的同步 endpoint 会自动放入线程池，不会阻塞事件循环；单次完整工作流约 10–30s，前端超时已设 75s，无需调整。

#### 1b. 前端渲染 Markdown 报告（零依赖）
`app.js` 目前 `textContent` 会把 Markdown 源码原样显示。建议加一个极简 Markdown→HTML 转换（报告用到的主要元素：标题、列表、粗体、表格、引用块），再赋给 `answerEl.innerHTML`。

最小实现思路（供参考，codex 自行决定细节）：
```js
function renderMarkdown(md) {
  // 转义 HTML → 处理 ## 标题 → **粗体** → 表格行 → - 列表 → 换行
  // 用 innerHTML 输出，注意先 escape 用户内容防 XSS
}
// 替换 app.js:54
answerEl.innerHTML = renderMarkdown(payload.answer);
```
> 若想更省事，也可保持 `textContent` + `white-space: pre-wrap`（现状），报告仍可读，只是 `#`/`##`/`-` 标记可见——但面试演示观感会打折，建议做最小渲染。

#### 1c. 前端文案更新到 Phase 3
- `index.html:47` `mode-pill` 文案 `RAG` → `工作流`（或「多方法校核」）
- `index.html:44` 标题「房地产估价问答」→「房地产估价工作流」
- `index.html:62-64` 示例问题换成估价场景，例如：
  - 「帮我评估一套100平方米二手住宅，有近期可比成交单价20000元/平方米，年租金净收益8万元，资本化率4%，请做多方法校核」
- `index.html:57` placeholder 同步换成估价需求示例

### 验收方式
- [ ] `python run_web.py`，网页提问「帮我评估一套100平方米二手住宅…多方法校核」，返回完整估价报告（含多方法计算、交叉校核、来源），而非单一问答。
- [ ] 报告在网页上以可读格式显示（标题/列表/表格渲染），非 Markdown 源码。

---

## 2. 🟡 P2 —— `test_plan_supplements_*` 依赖 LLM，却放在无门控单测类

### 证据
`tests/test_workflow.py:63-84` 的 `test_plan_supplements_income_params` / `test_plan_supplements_multi_method_params` 调用 `plan_node`，而 `plan_node` 内部先执行 `_structured_invoke`（真实 LLM）。

### 影响
`python -m unittest tests.test_workflow` 默认就会真实调用 LLM，违背「单元测试不依赖 LLM」的分层约定（Phase 2 已做到 `test_tools` 纯单测 + `test_agent` 门控）。

### 修复
把真正被测的纯逻辑 `_supplement_params_from_question`（`nodes.py:257`）抽出来直接单测，或给 `plan_node` 注入 mock。推荐前者：

```python
from app.workflow.nodes import _supplement_params_from_question

def test_supplement_income_params(self):
    params = _supplement_params_from_question(
        "某商铺年度稳定净收益60万元，资本化率5%，请评估价值。",
        {"area": None, "known_data": {}},
        ["income"],
        {"income": {}},
    )
    self.assertEqual(params["income"]["net_income"], 600000)
    self.assertEqual(params["income"]["cap_rate"], 0.05)
```

### 验收方式
- [ ] `python -m unittest tests.test_workflow` 在**无 LLM 网络**（或断网）下仍能通过单测部分。

---

## 3. 🟡 P3 —— `run_eval.py` 的 stdout reconfigure 未设 encoding

### 证据
`run_eval.py:13`：`sys.stdout.reconfigure(errors="replace")`（未设 `encoding="utf-8"`），而 `run_agent.py:13` 是 `reconfigure(encoding="utf-8", errors="replace")`。

### 影响
两个入口不一致；在 GBK 控制台下 `run_eval.py` 输出的中文/Unicode 符号仍可能乱码或被替换。

### 修复
```python
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
```

### 验收方式
- [ ] `python run_eval.py "某工业厂房土地价值100万元...成本法"` 输出中文报告不乱码。

---

## 4. 🟡 P3 —— 报告「来源引用」段收集了 context 中全部命中来源

### 证据
`nodes.py:348 _collect_sources`：既收集 `computations` 的 source，也收集 `context` 里所有 `[来源: ...]`。单方法场景（只用收益法）最终来源段却列出了 3 个文档（`02_income_approach.md` + `03_cost_approach.md` + `01_market_comparison.md`）。

### 影响
「来源引用」语义应是「结论依据的来源」，列出未采用方法的来源显得不精确，面试时可能被追问。

### 修复
`report_node` 的来源段优先只取 `computations` 里实际参与计算的 `source`（去重），`context` 来源作为兜底或移除。

### 验收方式
- [ ] 单方法场景报告「来源引用」段只含该方法的来源（如 `02_income_approach.md`）。

---

## 5. 整改清单（按顺序）

1. **P1a**：`server.py` 切换 `workflow_app`（第 1a 节代码）。
2. **P1b**：`app.js` 增加 Markdown 最小渲染。
3. **P1c**：`index.html` 文案更新（mode-pill/标题/示例/placeholder）。
4. **P2**：`test_plan_supplements_*` 改为直接单测 `_supplement_params_from_question`。
5. **P3**：`run_eval.py` reconfigure 补 `encoding="utf-8"`。
6. **P3**：`report_node` 来源段只取 computations 的 source。

### 整改完成标准
- [ ] `python -m unittest tests.test_workflow` 通过（单测部分不依赖 LLM）。
- [ ] `python run_web.py` 网页能出完整 Phase 3 估价报告且格式可读。
- [ ] `run_eval.py` 中文输出正常。
- [ ] 提交整改说明：逐条列改动 + 验收结果。

---

## 6. 保留的优点（不要破坏）

1. **工作流编排**：七节点状态图 + `next_method` 队列循环 + `computations` 累加 reducer + `loop_count` 防死循环，结构清晰。
2. **鲁棒性兜底**：`_structured_invoke` 的 JSON 降级、`_heuristic_plan` 与正则参数提取、缺数据分支，层层兜底。
3. **校核专业度**：多方法结果对照、参数敏感性分析、合理区间，超出规划书预期。
4. **报告模板**：代码拼八段骨架，结构稳定，LLM 只填自然语言部分。
5. **前端已有基础**：`renderSources` 的正则 `\[来源:\s*([^\];\]]+)\]` 与 Phase 3 报告格式兼容，无需改。
