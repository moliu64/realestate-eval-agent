# 前端重构计划书：估值表单化 + 户型图上传 + RAG/估值分离

> **文档性质**：实现方（codex）的执行规格书。在已验收的扩展基础上做前端交互重构与后端接口拆分。
> **角色**：顾问（规划方）确定方向与约束；实现方（codex）负责编码落地与自测。
> **已定决策**：① 估值入口 = 关键因素表单 + 可选补充说明框；② 前端同页两个 tab（估值 / 知识检索）；③ 户型支持上传房间布局图（走通义 VL）。
> **前置状态**：Phase 1–3 + 扩展（多格式/多模态/后台）均已验收。

---

## 1. 需求 → 改动映射

| 需求 | 改动 |
|---|---|
| 关键因素固定在页面让用户输入 | 后端 `/api/evaluate` 结构化接口 + 前端估值表单 |
| 户型支持房间布局图输入 | 后端 `/api/analyze-layout` + 前端户型图上传 |
| RAG 检索与估值分开 | 后端 `/api/rag` + 前端两个 tab |

---

## 2. 后端改造（`app/server.py`）

### 2.1 新增 `/api/evaluate`（结构化估值）
接收结构化字段，组装 workflow 输入，返回与 `/api/ask` 相同的三产物（`answer` + `steps` + `report_json`）。

```python
class EvaluateRequest(BaseModel):
    property_usage: str = ""
    area: float | None = None
    layout: str = ""
    building_age: float | None = None
    orientation: str = ""
    floor: str = ""
    decoration: str = ""
    location: str = ""
    valuation_purpose: str = ""
    valuation_date: str = ""
    comparable_price: float | None = None   # 市场比较法
    net_income: float | None = None          # 收益法
    cap_rate: float | None = None            # 收益法（小数）
    land_value: float | None = None          # 成本法
    replacement_cost: float | None = None    # 成本法
    depreciation: float | None = None        # 成本法
    note: str = ""                           # 补充说明（自然语言）
```

**组装逻辑**（关键：把结构化字段拼成 question 文本，复用现有 `plan` 的正则补参与 `retrieve` 关键词判断；同时把 `requirement` 预填，让 `understand` 跳过 LLM 提取）：

```python
@app.post("/api/evaluate")
def evaluate(request: EvaluateRequest) -> AskResponse:
    requirement = {
        "property_usage": request.property_usage,
        "area": request.area,
        "layout": request.layout,
        "building_age": request.building_age,
        "orientation": request.orientation,
        "floor": request.floor,
        "decoration": request.decoration,
        "location": request.location,
        "valuation_purpose": request.valuation_purpose,
        "valuation_date": request.valuation_date,
        "known_data": _collect_known_data(request),
        "missing_data": [],
    }
    question = _build_question(request)      # 见下
    init = dict(WORKFLOW_INIT, question=question, requirement=requirement)
    return _run_workflow(init)              # 复用 /api/ask 的 stream 收集逻辑，抽成公共函数
```

`_build_question` 把结构化字段拼成「自然语言式」文本，供 plan 正则提取与 retrieve 关键词命中，例如：

```python
def _build_question(req: EvaluateRequest) -> str:
    parts = [f"用途：{req.property_usage}", f"面积：{req.area}平方米", f"户型：{req.layout}",
             f"房龄：{req.building_age}年", f"朝向：{req.orientation}", f"楼层：{req.floor}",
             f"装修：{req.decoration}", f"区位：{req.location}", f"估价目的：{req.valuation_purpose}"]
    data = []
    if req.comparable_price: data.append(f"可比成交单价{req.comparable_price}元/平方米")
    if req.net_income: data.append(f"年度稳定净收益{req.net_income}元")
    if req.cap_rate is not None: data.append(f"资本化率{req.cap_rate}")
    if req.land_value is not None: data.append(f"土地价值{req.land_value}元")
    if req.replacement_cost is not None: data.append(f"重置成本{req.replacement_cost}元")
    if req.depreciation is not None: data.append(f"折旧{req.depreciation}元")
    if data: parts.append("已知数据：" + "；".join(data))
    if req.note: parts.append(f"补充说明：{req.note}")
    return "，".join(parts) + "。请给出参考估值。"
```

### 2.2 `understand` 节点跳过结构化输入（`app/workflow/nodes.py`）
结构化输入已预填 `requirement`，`understand` 检测后跳过 LLM 提取，避免覆盖：

```python
def understand_node(state: EvalState) -> dict:
    requirement = state.get("requirement") or {}
    if requirement.get("property_usage") or requirement.get("area") is not None or requirement.get("layout"):
        return {}   # 结构化输入已提供，跳过 LLM 提取
    # 原 LLM 提取逻辑不变
    ...
```

### 2.3 新增 `/api/analyze-layout`（户型图解析）
接收房间布局图，调通义 VL 返回户型文字描述，供前端填入户型字段：

```python
@app.post("/api/analyze-layout")
async def analyze_layout(file: UploadFile = File(...)) -> dict[str, str]:
    content = await file.read(20 * 1024 * 1024)
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in {".png", ".jpg", ".jpeg"}:
        raise HTTPException(400, "仅支持 png/jpg/jpeg 户型图。")
    prompt = "这是房屋户型/房间布局图。请提取并描述：几室几厅、朝向、面积标注、各房间分布；无法确认的内容请标注不确定。"
    description = describe_image(content, prompt)
    return {"layout": description}
```

### 2.4 新增 `/api/rag`（独立 RAG 检索）
复用 Phase 1 的 `rag.chain.answer`，与估值完全分离：

```python
class RagRequest(BaseModel):
    question: str = Field(min_length=1, max_length=500)

@app.post("/api/rag")
def rag(request: RagRequest) -> dict[str, str]:
    return {"answer": answer(request.question.strip())}
```

> 抽取公共函数 `_run_workflow(init)` 供 `/api/ask` 与 `/api/evaluate` 复用，避免 stream 收集逻辑重复。

---

## 3. 前端改造（`app/web/static/`）

### 3.1 同页两个 tab（`index.html`）
- 顶部导航两个 tab：「估值」与「知识检索」，点击切换显示对应面板。
- 估值 tab = 表单 + 报告（含参考因素、执行过程、JSON）。
- 检索 tab = 搜索框 + RAG 问答 + 来源 chips。

### 3.2 估值表单（关键因素固定字段）
分组展示，字段与 `EvaluateRequest` 一一对应：
- **估价对象**：用途（下拉：住宅/商铺/办公/工业厂房）、面积、户型、房龄、朝向、楼层、装修、区位
- **估价目的/时点**：估价目的、估价时点
- **已知数据**（可折叠，按需填）：可比成交单价、年净收益、资本化率、土地价值、重置成本、折旧
- **补充说明**：文本框（可选）

### 3.3 户型图上传
- 户型字段旁「上传户型图」按钮：选择图片 → `POST /api/analyze-layout` → 返回描述填入户型字段（可编辑）。
- 上传中显示 loading；解析失败给出提示（如未配 `VISION_API_KEY`）。

### 3.4 检索 tab
- 搜索框 + 提交 → `POST /api/rag` → 展示回答 + 来源 chips（复用 `renderSources`）。

---

## 4. 分步任务与验收

### 步骤 1 — 后端三接口 + understand 跳过
- 实现 `/api/evaluate`、`/api/analyze-layout`、`/api/rag`；抽取 `_run_workflow`；改造 `understand_node`。
- **验收**：`TestClient` 调 `/api/evaluate`（填面积/可比单价/净收益/资本化率）返回报告且含 2000000/12000000 对应值；`/api/rag` 返回 RAG 回答；`/api/analyze-layout` 上传户型图返回文字描述。

### 步骤 2 — 前端 tab 结构 + 估值表单
- 实现两个 tab、估值表单、已知数据折叠区。
- **验收**：网页能切换两个 tab；估值表单提交走 `/api/evaluate` 出报告。

### 步骤 3 — 户型图上传 + 检索 tab
- 户型图上传按钮接入 `/api/analyze-layout`；检索 tab 接入 `/api/rag`。
- **验收**：上传户型图后户型字段被填入描述；检索 tab 能问答并显示来源。

### 总验收
- [ ] 两个 tab 独立可用，估值表单能出完整报告（含参考因素/步骤/JSON）。
- [ ] 户型图上传解析可用。
- [ ] RAG 检索独立问答正常。
- [ ] `python -m unittest tests.test_workflow` 不回归；`run_web.py` 正常启动。

---

## 5. 关键坑点（必须遵守）

1. **结构化输入跳过 understand 的判断要可靠**：以「property_usage / area / layout 任一非空」为跳过条件，避免误跳过自然语言输入。
2. **`_build_question` 措辞对齐现有正则**：参数用「可比成交单价 X 元/平方米」「年度稳定净收益 X 元」「资本化率 0.05」等已被 `_supplement_params_from_question` 识别的措辞，单位统一为元、比例统一为小数。
3. **户型图 prompt 针对性**：提示词明确「房间布局图、几室几厅、朝向、面积标注」，与通用图片描述区分。
4. **视觉模型可选**：`/api/analyze-layout` 在未配 `VISION_API_KEY` 时返回明确错误（复用 `vision.py` 的 fail-closed），前端提示而非崩溃。
5. **不回归**：`/api/ask`（旧自由文本估值）保留兼容；`rag.chain.answer`、`workflow_app` 复用勿重写。
6. **前端 XSS**：户型图解析返回的描述用 `textContent`/`value` 填入，不 `innerHTML`。

---

## 6. 面试讲解主线（更新版）

1. **表单化**：结构化输入让关键因素可控、可校验，减少 LLM 自由提取的不确定性——体现「人机协同」的产品思维。
2. **户型图多模态**：房间布局图 → 通义 VL 提取户型 → 进入估值，展示「多模态 + 结构化」的落地。
3. **RAG 与估值分离**：知识检索与估价计算解耦，各司其职，体现系统边界清晰。

---

## 7. 给实现方（codex）的执行约定

1. 按步骤 1–3 顺序推进，每步对照验收自测。
2. 复用 `workflow_app`、`rag.chain.answer`、`describe_image`、`renderSources`、`renderMarkdown` 等，不重写。
3. `/api/ask` 保留兼容，前端估值 tab 走 `/api/evaluate`。
4. 完成后提交交付说明：实现功能、运行方式、各验收项通过情况、新增/修改文件。
