# Phase 4 补强规划书：Web 过程可视化 + 报告 JSON 结构化输出

> **文档性质**：实现方（codex）的执行规格书。在已验收的 Phase 1–3 基础上增量补强，复用现有模块，勿改动已有对外行为。
> **角色**：顾问（规划方）确定方向与约束；实现方（codex）负责编码落地与自测。
> **前置状态**：Phase 1/2/3 全部验收通过，`server.py` 已接 `workflow_app`，Web 端已渲染 Markdown 报告。

---

## 1. 背景与目标

Phase 3 已能产出结构化估价报告，但面试演示时存在两个短板：

1. **看不到过程**：网页只显示最终报告，面试官看不到「理解需求 → 规划方法 → 逐方法计算 → 交叉校核」的**任务编排过程**——而这正是岗位核心能力。
2. **只有 Markdown**：报告是 Markdown 文本，缺少**机器可读的结构化数据**，不便于下游集成，也少了一个「结构化输出」的展示点。

本补强解决这两个问题：**Web 端展示工作流执行步骤** + **报告附带 JSON 结构化输出**。

---

## 2. 补强 1：Web 端过程可视化

### 2.1 方案总览
后端用 LangGraph 的 **`stream(stream_mode="updates")`** 捕获每个节点的执行结果，组装成**步骤列表** `steps`；前端新增一个「执行过程」时间线面板，把步骤渲染出来（与最终报告并存）。

```
用户提问
   │  workflow_app.stream(...) 逐个节点捕获
   ▼
steps = [
  understand,  plan,  retrieve(市场比较法), compute(市场比较法),
  retrieve(收益法), compute(收益法),  verify,  report
]
   │  一次性随响应返回
   ▼
前端：报告卡片 + 执行过程时间线 + JSON 折叠面板
```

### 2.2 后端：`server.py` 捕获步骤
`/api/ask` 改用 `stream` 迭代，收集 `steps` 与最终 `report`/`report_json`：

```python
from langgraph.types import StreamMode  # 若 1.x 提供，否则直接用字符串

@app.post("/api/ask")
def ask(request: AskRequest) -> AskResponse:
    init = dict(WORKFLOW_INIT, question=request.question.strip())
    steps: list[dict] = []
    report = ""
    report_json = ""
    current_method = ""

    for chunk in workflow_app.stream(init, stream_mode="updates"):
        for node, update in chunk.items():
            step = _build_step(node, update, current_method)
            if node == "next_method":
                current_method = update.get("current_method", "")
                continue  # 调度节点不产出步骤，仅更新当前方法
            if step:
                steps.append(step)
            if "report" in update:
                report = update["report"]
            if "report_json" in update:
                report_json = update["report_json"]

    return AskResponse(answer=report.replace("\u2212", "-"), steps=steps, report_json=report_json)
```

`_build_step(node, update, current_method)` 把节点更新转成前端友好的步骤（type + label + detail）：

| 节点 | step.type | label | detail |
|---|---|---|---|
| understand | `understand` | 需求理解 | `requirement`（用途/面积/已知/缺失） |
| plan | `plan` | 方法规划 | `{"methods": [...]}`（转成中文名） |
| retrieve | `retrieve` | 检索知识 | `{"method": current_method, "sources": 从 context 提取的 [来源]}` |
| compute | `compute` | 工具计算 | `{"method": ..., "result": ..., "value": ...}` |
| verify | `verify` | 交叉校核 | `{"verification": ...}`（截断到合理长度） |
| report | `report` | 生成报告 | 不产出步骤（报告单独展示） |
| next_method | — | （调度） | 跳过 |

> 关键：`current_method` 由 `next_method` 节点的 update 维护，供后续 `retrieve`/`compute` 步骤标注所属方法。

### 2.3 前端：执行过程时间线
- `index.html` 在报告卡片上方新增一个「执行过程」区域（`<div id="steps">`），默认折叠或展开。
- `app.js` 渲染 `payload.steps` 为时间线：每步一个条目，展示 label + detail（方法名、来源、结果数值等），可加序号/图标。
- 用 `renderSources` 同款思路，来源用 chip 展示。

### 2.4 验收
- [ ] `python run_web.py`，网页提问多方法场景，能看到「需求理解 → 方法规划 → 检索/计算市场比较法 → 检索/计算收益法 → 交叉校核」的步骤时间线。
- [ ] 每个计算步骤能显示所属方法名与结果数值。
- [ ] 报告卡片仍正常渲染（不受影响）。

---

## 3. 补强 2：报告 JSON 结构化输出

### 3.1 方案
`report` 节点在生成 Markdown 报告的同时，把**结构化过程数据 + 结论文本**组装成 JSON，存入 state 的 `report_json` 字段。JSON 由确定性数据（process data）保证稳定，不依赖 LLM 二次结构化。

### 3.2 Schema（`app/workflow/schemas.py` 新增）
```python
class ComputationItem(BaseModel):
    method: str
    tool: str
    result: str
    source: str
    value: float | None
    missing: list[str]

class ReportSchema(BaseModel):
    question: str
    property_info: dict
    valuation_purpose: str
    valuation_date: str
    methods: list[str]
    computations: list[ComputationItem]
    verification: str
    missing_data: list[str]
    sources: list[str]
    report_markdown: str
```

### 3.3 节点改造（`app/workflow/nodes.py`）
- `report_node` 在 `return {"report": draft}` 基础上，额外组装 `ReportSchema` 并 `model_dump_json(ensure_ascii=False)`，返回 `{"report": draft, "report_json": json_str}`。
- `EvalState` 增加 `report_json: str` 字段。

### 3.4 接口（`app/server.py`）
- `AskResponse` 增加 `steps: list[dict]` 与 `report_json: str` 字段。
- 前端加一个「结构化数据」折叠面板，展示 `report_json`（`JSON.parse` 后 `JSON.stringify(..., null, 2)` 格式化），并提供「复制」按钮（可选）。

### 3.5 验收
- [ ] `/api/ask` 响应含 `answer`（Markdown）、`steps`（步骤列表）、`report_json`（合法 JSON 字符串）。
- [ ] `report_json` 可 `json.loads`，且含 `methods`、`computations`、`sources`、`verification`、`report_markdown` 字段。
- [ ] 网页能展开查看 JSON 结构。

---

## 4. 分步任务与验收（按顺序）

### 步骤 1 — 后端 stream 捕获（补强 1 后端）
- `server.py` 改 `stream(stream_mode="updates")`，实现 `_build_step` 与 `current_method` 跟踪。
- **验收**：本地脚本调 `/api/ask`，返回的 `steps` 包含 understand/plan/compute×N/verify 步骤，且 compute 步骤带正确 `method`。

### 步骤 2 — 前端时间线（补强 1 前端）
- `index.html` + `app.js` 渲染 `steps` 时间线。
- **验收**：网页提问多方法场景，时间线完整、可读。

### 步骤 3 — JSON 结构化输出（补强 2）
- `schemas.py` 加 `ComputationItem`/`ReportSchema`；`state.py` 加 `report_json`；`report_node` 组装 JSON；`server.py` `AskResponse` 加字段。
- **验收**：`report_json` 合法且字段齐全。

### 步骤 4 — 前端 JSON 面板 + 联调
- 前端加 JSON 折叠面板。
- **验收**：网页能同时看到报告、时间线、JSON 三块，互不影响。

### 补强总验收
- [ ] `python -m unittest tests.test_workflow` 仍通过（不回归）。
- [ ] `run_web.py` 网页完整展示「报告 + 执行过程 + JSON」。
- [ ] README 增补「执行过程可视化」与「JSON 输出」说明及面试讲解要点。

---

## 5. 关键坑点（必须遵守）

1. **`stream` 的 yield 结构**：`stream_mode="updates"` 下每次 yield 是 `{node_name: update_dict}`；`next_method` 这类条件边前节点也会 yield，需跳过。
2. **`current_method` 跟踪**：`retrieve`/`compute` 的 update 不含 `current_method`（它是 state 字段，非节点返回值），必须从 `next_method` 的 update 里维护变量。
3. **节点返回值与 state 更新的区别**：stream 拿到的是节点**返回值**，不是完整 state。若某字段（如 `current_method`）在节点返回值里没有，就去 `next_method` 的返回值里取。
4. **`report_json` 序列化**：`value` 可能为 `None`（缺数据场景），`model_dump_json` 默认会保留 `null`；`ensure_ascii=False` 保证中文可读。`source` 可能为空串，前端需容错。
5. **不回归**：`report_node` 现在只返回 `report`，改后要同时返回 `report_json`，确认 `run_eval.py`（读 `result["report"]`）与既有测试不受影响。
6. **前端 XSS**：JSON 展示用 `textContent`（不要 `innerHTML`），Markdown 渲染继续走已有 `escapeHtml`。

---

## 6. 面试讲解主线（新增 5 分钟）

1. **过程可视化**：为什么要把 agent 的「黑盒」拆开——LangGraph 的 `stream` 让每一步可观测、可解释，体现工程可控性。
2. **双输出**：Markdown 给人看、JSON 给系统用，一份流程两种产物，体现「结构化输出」能力。
3. **演示**：网页问一个多方法场景，指着时间线讲「这就是任务分解 + 编排循环」，再展开 JSON 讲「这就是可集成的数据接口」。

---

## 7. 给实现方（codex）的执行约定

1. 按步骤 1–4 顺序推进，每步对照验收自测。
2. 复用 `workflow_app`、`renderSources`、`escapeHtml` 等已有实现，不重写。
3. 优先保证「不回归」——改完后 `test_workflow`、`run_eval.py`、既有 Web 功能都必须正常。
4. 完成后提交交付说明：实现功能、运行方式、各验收项通过情况、新增/修改文件清单。
