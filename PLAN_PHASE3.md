# Phase 3 规划书：多节点任务编排 + 多方法交叉校核 + 结构化估价报告

> **文档性质**：实现方（codex）的执行规格书。在已验收的 Phase 1（RAG）、Phase 2（Tool Calling）基础上增量开发，复用其模块，勿改动对外行为。
> **角色**：顾问（规划方）确定方向与约束；实现方（codex）负责编码落地与自测。
> **前置状态**：Phase 1 / Phase 2 均已验收通过（cosine 向量库、3 个估价工具、LangGraph 工具循环、`server.py` 已接 `agent_app`）。

---

## 1. 背景与目标

### 1.1 定位
Phase 2 是「单一工具循环」（一次检索 → 一次工具调用 → 回答）。Phase 3 升级为「**多节点任务编排**」：用户给一个**模糊的估价需求**，智能体自动把它**分解成多个阶段**执行，最终产出**结构化估价报告**。

> 用户输入「帮我评估一套 100㎡ 的二手住宅，有近期可比成交，也想知道收益角度值多少」→ 系统自动：理解需求 → 规划方法（市场比较法 + 收益法）→ 逐方法检索规范 → 逐方法工具计算 → 交叉校核 → 生成报告。

### 1.2 与岗位能力映射（本阶段是核心落点）
| 岗位要求 | 本阶段落点 |
|---|---|
| ④ 任务分解与执行编排机制 | 显式多节点状态图 + 方法队列循环 + 条件边 |
| ④ 提升自动化处理能力 | 一个请求自动跑完整估价流程，无需人工分步 |
| ① Agent 架构设计 | 六节点工作流 + 状态定义 + 循环编排 |
| ⑤ 撰写技术文档 | Markdown 结构化估价报告 |

### 1.3 为什么这是亮点（面试必讲）
Phase 2 的 agent 循环靠 LLM「自己看着办」，流程不可控；Phase 3 用 **LangGraph 显式状态图**把估价作业流程固化成节点，LLM 只在关键节点做判断（理解/规划/校核/成文），计算仍走确定性工具——**可控性与智能化兼顾**，这正是企业级 Agent 的编排范式。

---

## 2. 技术决策（写死，勿改）

| 项 | 决策 |
|---|---|
| 编排框架 | LangGraph `StateGraph`（显式多节点，非纯 ReAct） |
| 校核 | **多方法交叉校核**（一个任务可用多种方法，最后对比综合） |
| 报告 | **Markdown 结构化估价报告** |
| 结构化输出 | `with_structured_output(PydanticModel)`（understand / plan 节点） |
| 计算 | 复用 Phase 2 的 3 个估价工具（勿重写） |
| 方法循环 | 状态字段 `methods` 队列 + 条件边（`next_method` 调度） |

---

## 3. 架构：状态图

```text
START
  │
  ▼
understand ──▶ plan ──▶ next_method ──(队列空?)──▶ verify ──▶ report ──▶ END
                         │  ▲                           
                         │  │ (还有方法)
                         ▼  │
                     retrieve ──▶ compute ──┘
```

**七节点职责**：
| 节点 | 职责 | 输出 |
|---|---|---|
| `understand` | 结构化提取估价需求（对象/目的/时点/已知/缺失） | `requirement: dict` |
| `plan` | 规划估价方法列表 + 各方法已知参数 | `methods: list`、`params: dict` |
| `next_method` | 从队列弹出下一个方法，设置当前方法/参数；队列空则转 verify | `current_method`、`remaining` |
| `retrieve` | 检索当前方法的知识规范（复用 Phase 1 `retrieve`） | `context` |
| `compute` | 调用当前方法对应的工具计算 | `computations`（累积） |
| `verify` | 多方法结果交叉校核 | `verification: str` |
| `report` | 生成 Markdown 结构化报告 | `report: str` |

**条件边**：`next_method` 之后判断队列是否空 → 空则 `verify`，非空则 `retrieve`。`compute → next_method` 构成方法循环。

---

## 4. 状态定义（`app/workflow/state.py`）

```python
class EvalState(TypedDict):
    question: str
    requirement: dict                 # 需求理解结果
    methods: list[str]                # 待处理方法队列（如 ["market_comparison", "income"]）
    params: dict                      # 各方法已知参数 {method: {参数}}
    current_method: str               # 当前处理的方法
    context: str                      # 当前方法检索上下文
    computations: Annotated[list, operator.add]   # 各方法计算结果（累积）
    verification: str                 # 校核结论
    report: str                       # 最终报告
    messages: Annotated[list, add_messages]
```

> ⚠️ 关键：`computations` 必须用 `Annotated[list, operator.add]`（累加 reducer），否则节点返回会覆盖而非累积。

---

## 5. 方法 ↔ 工具映射（写死）

| 方法标识 | 工具 |
|---|---|
| `market_comparison` | `calc_market_comparison` |
| `income` | `calc_income_approach` |
| `cost` | `calc_cost_approach` |

方法标识由 `plan` 节点产出，`compute` 节点据此绑定**唯一对应工具**（每轮只 bind 一个，避免 LLM 选错）。

---

## 6. 节点规格

### 6.1 `understand`（需求理解）
- 输入 `question`，用 `llm.with_structured_output(RequirementSchema)` 产出：
  - `property_usage`（用途）、`area`、`location`、`rights_type`
  - `valuation_purpose`（估价目的）、`valuation_date`（估价时点）
  - `known_data: dict`（已知数据）、`missing_data: list[str]`（缺失数据）
- 若提取失败或关键信息缺失，在 `missing_data` 里标注，报告阶段要体现。

### 6.2 `plan`（方法规划）
- 输入 `requirement`，用 `with_structured_output(MethodPlanSchema)` 产出：
  - `methods: list[str]`（候选方法，取值见第 5 节标识）
  - `params: dict`（每个方法的已知入参；缺失的用占位或留空并在报告说明）
- 判断依据：有可比成交 → 市场比较法；有收益数据 → 收益法；成本资料充分/特殊用途 → 成本法；可多选。

### 6.3 `next_method`（循环调度）
- 若 `methods` 非空：`pop(0)` 设为 `current_method`，返回 `retrieve` 分支。
- 若空：返回 `verify` 分支。
- 设最大循环次数兜底（如 4 次），防止异常导致空转。

### 6.4 `retrieve`（检索）
- 按 `current_method` 检索对应知识（复用 `app.rag.retriever.retrieve`），格式化为 `context`。

### 6.5 `compute`（工具计算）
- `get_chat_model().bind_tools([对应工具])`，把 `current_method` 的 `params` + `context` 注入，让 LLM 调用工具。
- 工具结果（含计算过程）append 到 `computations`，结构：`{"method": ..., "tool": ..., "result": ..., "source": ...}`。

### 6.6 `verify`（交叉校核）
- 输入 `computations`（多方法结果），LLM 输出：
  - 各方法结果是否互相印证；
  - 若差异明显，说明可能原因（方法口径、假设、数据差异）；
  - 给出最终估价结论或合理区间。

### 6.7 `report`（报告生成）
- **代码拼骨架 + LLM 填充**（保证结构稳定）：Markdown 模板含固定段落（估价对象、目的/时点、采用方法、各方法计算过程、校核结论、最终结论、来源引用），LLM 负责填写「最终结论」「校核说明」等自然语言部分。

---

## 7. 目录结构（新增，不删旧）

```
app/workflow/
├── __init__.py
├── state.py        # EvalState
├── schemas.py      # RequirementSchema / MethodPlanSchema（Pydantic）
├── nodes.py        # 七节点实现
└── graph.py        # 组装 StateGraph + 条件边 + compile
run_eval.py         # 演示入口：python run_eval.py "估价需求"
tests/
├── test_workflow.py  # 节点/映射/循环单测
└── eval_cases.jsonl  # 端到端用例（含多方法场景）
```

---

## 8. 分步任务与验收

### 步骤 1 — 状态与 schema（`state.py`、`schemas.py`）
- 定义 `EvalState`（`computations` 用累加 reducer）、`RequirementSchema`、`MethodPlanSchema`。
- **验收**：导入不报错；Pydantic schema 字段齐全。

### 步骤 2 — `understand` + `plan` 节点
- 用 `with_structured_output` 实现，打印验证结构化输出正确。
- **验收**：对「帮我评估一套 100㎡ 二手住宅」能提取出用途/面积/缺失数据；对含收益数据的输入能 plan 出 `income`。

### 步骤 3 — `next_method` + 方法循环（`graph.py`）
- 组装状态图：`understand→plan→next_method`，`next_method` 条件边接 `retrieve`/`verify`，`retrieve→compute→next_method`。
- **验收**：`methods=["market_comparison","income"]` 时，循环恰好执行 2 次后进入 `verify`，无空转。

### 步骤 4 — `retrieve` + `compute` 节点
- `compute` 按 `current_method` bind 唯一工具并计算，结果累积到 `computations`。
- **验收**：单方法场景计算正确（复用 Phase 2 工具结果）。

### 步骤 5 — `verify` + `report` 节点
- 校核多方法结果；报告用「模板 + LLM 填充」生成 Markdown。
- **验收**：报告含固定段落、各方法计算过程、来源引用。

### 步骤 6 — 演示入口 + 端到端用例
- `run_eval.py` 读命令行问题，跑图，打印 `report`。
- `tests/eval_cases.jsonl` 放 2–3 条用例（含 1 条多方法、1 条单方法、1 条缺数据）。
- **验收**：`run_eval.py "..."` 输出完整报告；`tests/test_workflow.py` 单测通过。

### Phase 3 总体验收
- [ ] 一个模糊需求自动跑完 understand→plan→(多方法循环)→verify→report。
- [ ] 报告含「对象/目的/时点/方法/计算过程/校核结论/来源」。
- [ ] 多方法场景能交叉校核；缺数据场景能诚实标注缺失。
- [ ] README 增补 Phase 3 架构图、运行命令、面试讲解要点。

---

## 9. 关键坑点（必须遵守）

1. **`computations` 必须用累加 reducer**：`Annotated[list, operator.add]`，否则多方法结果互相覆盖，verify 拿不到全部。
2. **`with_structured_output` 兼容性**：DeepSeek 等支持 function calling 的端点通常可用；若某端点不支持，退回「LLM 输出 JSON + 手动 `pydantic` 解析」，不要硬依赖。
3. **方法循环防死循环**：`next_method` 必须递减队列，并设最大循环次数兜底。
4. **缺数据分支**：某方法缺关键参数（如收益法无净收益）时，`compute` 不应强行算错，应标记「该方法因缺数据未采用」，verify/report 要体现。
5. **报告稳定性**：报告骨架用代码模板固定，LLM 只填自然语言段落，避免 LLM 每次生成格式漂移。
6. **复用勿重写**：`retrieve`、3 个工具、`get_chat_model`、`get_embeddings` 均复用，不复制代码。
7. **多方法参数口径**：`plan` 产出的 `params` 单位要统一（元、小数），与 Phase 2 工具 schema 一致。

---

## 10. 面试讲解主线（20 分钟版）

1. **从 Phase 2 到 Phase 3**：单循环 → 显式多节点编排，为什么企业级要可控。
2. **任务分解**：understand/plan 用结构化输出把模糊需求拆成「方法列表 + 参数」。
3. **编排循环**：`next_method` 队列 + 条件边，逐个方法「检索→计算」，累加 reducer 收集结果。
4. **交叉校核**：verify 对比多方法，体现估价行业「多方法印证」的专业性。
5. **报告生成**：模板 + LLM 填充，稳定产出结构化文档。
6. **工程细节**：reducer、防死循环、缺数据分支、结构化输出兼容性。

---

## 11. 给实现方（codex）的执行约定

1. 按步骤 1–6 顺序推进，每步对照验收自测。
2. 先跑通**单方法**全流程，再加**多方法循环 + 校核**。
3. 复用 Phase 1/2 模块，不重写；新增代码集中在 `app/workflow/`。
4. 完成后提交交付说明：实现功能、运行方式、各验收项通过情况、新增文件清单。
