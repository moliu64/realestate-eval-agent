# 扩展代码审查意见与整改任务书

> **审查对象**：`D:\房地产估价agent` 的扩展交付（估值因素 / 多格式 / 多模态 / 后台入口 / UI / 部署）。
> **结论**：模块 B/C/D/E/F 验收通过，模块 A 部分通过。以下 2 项为收尾整改，改完即整体闭环。
> **给实现方（codex）**：按第 3 节顺序整改，每完成一条对照「验收方式」自测。

---

## 1. 🔴 P1 —— 新依赖未安装到虚拟环境（交付不完整）

### 证据
`requirements.txt` / `requirements.lock` 已声明 4 个新依赖：
```
Pillow==12.2.0  pypdf==6.16.1  python-docx==1.2.0  python-multipart==0.0.32
```
但 `.venv` 中并未安装（`pip list` 无这些包），导致 `from app.server import app` 在定义 `/admin/upload` 时抛：

```
RuntimeError: Form data requires "python-multipart" to be installed.
```

### 影响
`run_web.py` 无法启动，admin 上传、PDF/Word/图片入库全部失效——核心新增功能处于不可用状态。

### 修复
安装依赖并确认环境可运行：
```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.lock
```

### 验收方式
- [ ] `python -c "from app.server import app"` 不报错。
- [ ] `python run_web.py` 能正常启动。
- [ ] 交付说明中注明「已执行依赖安装，环境可运行」。

> 注：验收方已临时补装这 4 个依赖以完成后续验证；实现方仍需在正式交付时保证 `.venv` 完整。

---

## 2. 🟠 P2 —— 模块 A「市场趋势依据」未生效（武汉趋势来源丢失）

### 证据
- `app/workflow/nodes.py:120-126` `retrieve_node`：把「方法查询」与「武汉趋势查询」混在**一个 query** 里检索。
- `app/workflow/nodes.py:133` `compute_node`：`source = _source_from_context(...)` 只取 context 的**第一个**来源。
- `app/workflow/nodes.py:203` `report_node`：从 `computations` 的 source 里硬找 `wuhan_market_trend`。
- 实测：报告「市场趋势依据」显示「未检索到趋势资料」，但向量库检索「武汉房价走势」能命中 `07_wuhan_market_trend.md`。

### 影响
估值因素扩展里，户型/房龄/朝向提取已生效，但「市场趋势」这一参考因素没有体现在报告中，模块 A 的关键价值打了折扣。

### 根因
方法文档（01/02/03）与趋势文档（07）混在一个 query 里，方法文档相似度更高排前，`_source_from_context` 只取首个来源，07 来源丢失；而 `report_node` 只从 `computations.source`（方法来源）里找 `wuhan_market_trend`，自然找不到。

### 修复（拆两次检索 + 单独字段）
**① `app/workflow/state.py`** 增加字段：
```python
trend_sources: list[str]
```

**② `app/workflow/nodes.py` 的 `retrieve_node`** 改为方法检索 + 趋势检索分离：
```python
def retrieve_node(state: EvalState) -> dict:
    method = state["current_method"]
    query = f"{METHOD_QUERY.get(method, method)}\n用户需求：{state['question']}"
    results = retrieve(query, k=4)
    context = _format_context(results)

    trend_sources: list[str] = []
    if any(kw in state["question"] for kw in ("趋势", "走势", "房龄", "户型", "房价")):
        trend_results = retrieve("武汉房地产市场趋势 户型 房龄 价格走势", k=4)
        for doc, _ in trend_results:
            source = doc.metadata.get("source", "")
            if "wuhan_market_trend" in source and source not in trend_sources:
                trend_sources.append(source)
    return {"context": context, "trend_sources": trend_sources}
```

**③ `app/workflow/nodes.py` 的 `report_node`** 改从 `trend_sources` 取（替换第 203 行）：
```python
trend_sources = state.get("trend_sources") or []
# 参考因素段内：
f"- 市场趋势依据：{'; '.join(f'[来源: {source}]' for source in trend_sources) or '未检索到趋势资料'}\n\n"
```

**④ 初始 state 补字段**：`app/server.py` 的 `WORKFLOW_INIT` 与 `run_eval.py` 的初始 dict 都加 `"trend_sources": []`。

### 验收方式
- [ ] 问「2015 年建成、89㎡ 两房、光谷，结合武汉房价走势和房龄影响给参考估值」，报告「参考因素说明」的「市场趋势依据」显示 `[来源: 07_wuhan_market_trend.md]`。
- [ ] `python -m unittest tests.test_workflow` 不回归。

---

## 3. 整改清单（按顺序）

1. **P1**：`pip install -r requirements.lock`，确认 `from app.server import app` 与 `run_web.py` 正常。
2. **P2**：按第 2 节四处改动（state.py / nodes.py retrieve_node / nodes.py report_node / server.py+run_eval.py 初始 state），实现「方法检索 + 趋势检索分离」。

### 整改完成标准
- [ ] 报告「市场趋势依据」能正确引用 `07_wuhan_market_trend.md`。
- [ ] 环境依赖完整、`run_web.py` 可启动。
- [ ] `test_workflow` 回归通过。
- [ ] 提交整改说明：逐条列改动 + 验收结果。

---

## 4. 保留的优点（不要破坏）

1. **多格式 loader**：按扩展名分发 `.md/.pdf/.docx/图片`，metadata 带 `file_type`，空文档与不支持格式有告警兜底。
2. **视觉模型封装**：`app/vision.py` 走 DashScope 兼容端点、图片 base64 格式正确、Pillow 压缩 `thumbnail(1600)`、未配 key 时 fail-closed；已实测通义 VL 能正确描述图片。
3. **后台入口安全**：`hmac.compare_digest` 防时序攻击、`target.parent` 防路径穿越、20MB 限制、上传失败回滚、增量重建。
4. **依赖声明收紧**：`requirements.txt` 已把 langchain 等收紧到已验证主版本（`>=1.x,<2`），解决了历史版本漂移问题。
