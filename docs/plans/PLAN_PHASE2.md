# Phase 2 规划书：Tool Calling（工具调用）+ RAG 混合

> **文档性质**：实现方（codex）的执行规格书。在已整改完成的 Phase 1 代码基础上增量开发，勿改动 Phase 1 已有模块的对外行为。
> **角色**：顾问（规划方）确定方向与约束；实现方（codex）负责编码落地与自测。
> **前置状态**：Phase 1 已验收通过（向量库 space=cosine、路径绝对化、vectorstore 缓存、单元测试 2/2、端到端跑通）。

---

## 1. 背景与目标

### 1.1 定位
Phase 1 解决「知识问答」（RAG）；Phase 2 解决「精确计算」（Tool Calling），并把两者编排起来。目标能力：

> 用户给出一个估价场景 → 智能体先检索知识（判断适用哪种估价方法、参数口径）→ 调用对应估价计算工具算出数值 → 综合生成带「计算过程 + 来源引用」的回答。

### 1.2 与岗位能力映射
| 岗位要求 | 本阶段落点 |
|---|---|
| ④ 工具调用与任务编排 | Tool Calling 循环（LangGraph ToolNode）+ 条件边编排 |
| ② 代码实现 | 工具函数 + Agent 图 + 入口脚本 |
| ③ 大模型集成 | `bind_tools`、工具 schema、Prompt 注入检索上下文 |

### 1.3 为什么需要工具（面试必讲）
LLM 不擅长精确数值计算与公式推导，容易算错。把估价公式封装成**确定性的 Python 工具**，让 LLM 负责「判断 + 决策 + 组织语言」，工具负责「算数」，是 Agent 的核心分工。

---

## 2. 技术决策（写死，勿改）

| 项 | 决策 |
|---|---|
| 工具调用循环 | **LangGraph `ToolNode`**（`langgraph.prebuilt`） |
| 图框架 | LangGraph `StateGraph`（已装 `langgraph==1.2.11`） |
| 与 RAG 结合 | **检索 + 工具混合**：先 `retrieve` 注入上下文，再 `bind_tools` 决策 |
| 工具数量 | 3 个估价计算工具（市场比较法 / 收益法 / 成本法） |
| 工具返回 | 返回 `str`（含计算过程），便于 LLM 直接引用 |
| 入参 schema | Pydantic v2 `BaseModel` + `Field(description=...)` |

---

## 3. 架构：LangGraph 状态图

```text
            ┌─────────────────────────────────────────────┐
用户问题 ──▶│ retrieve ──▶ agent ──(有 tool_calls?)──▶ tools │
            │               ▲                    │         │
            │               └────────────────────┘         │
            │                 (工具结果回流 agent 再决策)      │
            │                        │ (无 tool_calls)       │
            │                        ▼                      │
            │                    finalize ──▶ 最终回答       │
            └─────────────────────────────────────────────┘
```

**节点职责**：
| 节点 | 职责 |
|---|---|
| `retrieve` | 调用 Phase 1 `retrieve()`，把 top-k 片段格式化为 `context` |
| `agent` | `get_chat_model().bind_tools(TOOLS)`，system prompt 注入 `context`，返回 AI 消息（可能带 `tool_calls`） |
| `tools` | LangGraph `ToolNode(TOOLS)` 执行工具，结果以 `ToolMessage` 写回 `messages` |
| `finalize` | 取出最后一条 AI 消息内容作为最终回答 |

**条件边**：`agent` 之后判断最后一条消息是否含 `tool_calls` → 有则去 `tools`，无则去 `finalize`。`tools` 之后回到 `agent` 形成循环。

---

## 4. 目录结构（新增，不删旧）

```
app/
├── tools/
│   ├── __init__.py          # 导出 TOOLS 列表
│   └── valuation.py         # 3 个估价计算工具
├── agent/
│   ├── __init__.py
│   ├── state.py             # AgentState TypedDict
│   ├── nodes.py             # retrieve/agent/finalize 节点 + should_continue
│   └── graph.py             # 构建并 compile StateGraph，导出可调用 app
run_agent.py                 # 演示入口：python run_agent.py "估价场景"
tests/
├── test_tools.py            # 3 个工具的计算单元测试
└── test_agent.py            # 端到端 agent 测试（可选，需真实 LLM）
```

---

## 5. 工具规格（公式与 schema 写死）

### 5.1 市场比较法 `calc_market_comparison`
**公式**（与 `data/docs/01_market_comparison.md` 一致）：
```
估价对象单价 = 可比实例成交单价 × 交易情况修正 × 交易日期修正 × 区位修正 × 实物修正 × 权益修正
估价对象总价 = 估价对象单价 × 建筑面积
```
**入参**（Pydantic，`Field(description=...)` 必填，LLM 靠它理解）：
| 字段 | 类型 | 说明 |
|---|---|---|
| `comparable_price` | float | 可比实例成交单价（元/㎡） |
| `transaction_adj` | float=1.0 | 交易情况修正系数 |
| `date_adj` | float=1.0 | 交易日期修正系数 |
| `location_adj` | float=1.0 | 区位状况修正系数 |
| `physical_adj` | float=1.0 | 实物状况修正系数 |
| `rights_adj` | float=1.0 | 权益状况修正系数 |
| `area` | float | 建筑面积（㎡） |

**返回**：`str`，含单价、总价、完整计算过程（数字保留 2 位小数）。

### 5.2 收益法 `calc_income_approach`
**公式**（与 `02_income_approach.md` 一致）：
```
房地产价值 = 年度稳定净收益 ÷ 资本化率
```
**入参**：
| 字段 | 类型 | 说明 |
|---|---|---|
| `net_income` | float | 年度稳定净收益（元） |
| `cap_rate` | float | 资本化率（小数，如 0.05 = 5%） |

**校验**：`cap_rate <= 0` 时返回明确错误文案（不抛异常，让 LLM 能读）。**返回**：收益价值 + 计算过程。

### 5.3 成本法 `calc_cost_approach`
**公式**（与 `03_cost_approach.md` 一致）：
```
房地产价值 = 土地价值 + 建筑物重置成本 - 建筑物折旧
```
**入参**：
| 字段 | 类型 | 说明 |
|---|---|---|
| `land_value` | float | 土地价值（元） |
| `replacement_cost` | float | 建筑物重置成本（元） |
| `depreciation` | float | 建筑物折旧（元） |

**返回**：房地产价值 + 计算过程。

> 工具 docstring 用中文一句话说明「何时用、算什么」，这是 LLM 选择工具的判断依据。

---

## 6. 分步任务与验收

### 步骤 1 — 实现 3 个工具（`app/tools/valuation.py`）
- 用 `@tool` 装饰器 + Pydantic `args_schema`。
- `__init__.py` 导出 `TOOLS = [calc_market_comparison, calc_income_approach, calc_cost_approach]`。
- **验收**：`tests/test_tools.py` 断言——`calc_income_approach(600000, 0.05)` 返回含 `12000000`；`calc_market_comparison(20000, area=100)`（其余系数 1.0）返回单价 20000、总价 2000000；`calc_cost_approach(1000000, 2000000, 300000)` 返回 2700000。

### 步骤 2 — 定义 AgentState + 节点（`app/agent/state.py`、`nodes.py`）
- `AgentState(TypedDict)`：`question: str`、`context: str`、`messages: Annotated[list, add_messages]`、`answer: str`。
- `retrieve` 节点：`retrieve(question)` → 格式化 `context`（截断到合理长度，例如每片段 ≤ 300 字、最多 4 段）。
- `agent` 节点：`bind_tools(TOOLS)`，system prompt 含「资深估价师 + 依据 context 选方法 + 需要计算时必须调用工具 + 工具结果要写进回答」。
- `finalize` 节点：取最后一条 AI 消息作为 `answer`。
- **验收**：导入不报错；`agent` 节点对「某商铺年净收益 60 万、资本化率 5%」能产出含 `tool_calls` 的消息（可用脚本打印确认）。

### 步骤 3 — 组装图（`app/agent/graph.py`）
- `StateGraph(AgentState)`：加 4 节点、`START→retrieve`、`retrieve→agent`、`add_conditional_edges(agent, should_continue, {...})`、`tools→agent`、`finalize→END`，最后 `.compile()`。
- **验收**：`graph.invoke({"question": "..."})` 跑通，最终 `answer` 非空且含工具计算结果。

### 步骤 4 — 演示入口 `run_agent.py`
- 读取命令行参数为 `question`，`invoke` 图并打印 `answer`。
- **验收**：`python run_agent.py "某商铺年度净收益60万元，资本化率5%，估值多少"` 返回约 1200 万的回答，且回答里带计算过程与来源引用。

### 步骤 5 — 检索 + 工具协同验证
- 构造「需要知识定方法 + 需要工具算数」的复合问题，验证 retrieve 提供的 context 帮助 agent 选对工具、算对数。
- **验收**：至少 2 个复合场景人工核对通过；把 3 条典型问题写入 `tests/` 作为回归用例。

### Phase 2 总体验收
- [ ] `python -m unittest tests.test_tools` 通过。
- [ ] `run_agent.py` 对收益法/市场比较法/成本法三类问题各跑通一次，数值正确。
- [ ] 回答同时包含「工具计算过程」与「来源引用」。
- [ ] README 增补 Phase 2 的架构图、运行命令与面试讲解要点。

---

## 7. 关键坑点（必须遵守）

1. **LangGraph 1.x 导入路径**：`from langgraph.graph import StateGraph, START, END`、`from langgraph.prebuilt import ToolNode`、`from langgraph.graph.message import add_messages`。不要用旧版 `langgraph.graph.graph` 等路径。
2. **消息合并用 `Annotated[list, add_messages]`**：否则每次节点返回会覆盖而非追加，tool_calls/tool_result 会丢失。
3. **工具结果回流**：`tools → agent` 这条边必须存在，否则工具算完没有后续 AI 消息，`finalize` 拿不到答案。
4. **防死循环**：`compile(checkpointer=None)` 默认有递归上限，但建议在 `agent` 节点或 `should_continue` 里设最大工具调用次数（如 5 次），超限强制去 `finalize`，避免「LLM 反复调工具」卡死。
5. **工具入参校验在工具内做**（如 `cap_rate<=0`），返回错误文案而非抛异常，LLM 才能读懂并纠正。
6. **数值类型**：LLM 可能把「60万」理解成 60 或 600000，工具 docstring 与字段 description 要写清单位（元）；必要时在 `agent` system prompt 里提示「金额单位统一为元」。
7. **`context` 注入长度**：检索片段拼接后要截断，避免挤爆上下文窗口。
8. **`@tool` 与 Pydantic v2**：`args_schema` 用 `BaseModel`，字段加 `description`，这是 LLM 正确填参的关键。

---

## 8. 面试讲解主线（15 分钟版）

1. **痛点**：LLM 算不准数 → 引出 Tool Calling。
2. **工具 = 函数 + schema + docstring**：展示 3 个估价工具，公式与知识库对齐。
3. **循环机制**：agent 决策 → `ToolNode` 执行 → `ToolMessage` 回流 → 再决策 → 无 tool_calls 则 finalize。
4. **RAG 与工具分工**：检索定方法/口径，工具算数值，LLM 编排两者。
5. **工程细节**：`Annotated[list, add_messages]`、条件边、防死循环、单位约定——体现工程把控。

---

## 9. 给实现方（codex）的执行约定

1. 按步骤 1–5 顺序推进，每完成一步对照该步验收自测。
2. 复用 Phase 1 的 `retrieve` / `get_chat_model`，**不要重写**它们。
3. 优先跑通「收益法」单一工具闭环，再扩展另外两个工具与复合场景。
4. 完成后提交交付说明：实现功能、运行方式、各验收项通过情况、新增文件清单。
