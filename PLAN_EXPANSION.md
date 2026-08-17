# 扩展计划书：估值因素增强 + 多格式/多模态知识库 + 后台管理入口 + UI 优化

> **文档性质**：实现方（codex）的执行规格书。在已验收的 Phase 1–3 + 补强基础上增量扩展。
> **角色**：顾问（规划方）已确定方向与约束；实现方（codex）负责编码落地与自测。
> **已定决策**：① 多模态走「换视觉模型」方案（Qwen-VL / GLM-4V 等 OpenAI 兼容视觉模型），DeepSeek 继续做文本；② 武汉房产数据由顾问整理成 `WUHAN_MARKET_DATA.md`，codex 负责入库。
> **前置状态**：Phase 1/2/3 + 过程可视化 + JSON 输出全部验收通过。

---

## 0. 需求 → 模块映射

| 需求 | 模块 |
|---|---|
| 户型/面积/房龄/价值走向纳入估值参考 | A 估值因素扩展 |
| 武汉近十年趋势 + 户型价值数据入库 | A（数据已备：`WUHAN_MARKET_DATA.md`） |
| RAG 支持图片/Word/PDF | B 多格式入库 + C 多模态 |
| DeepSeek 多模态 | C 视觉模型 |
| 后端管理入口（区别于前端） | D 后台管理入口 |
| 前端 UI 优化 | E |
| 后期挂网页 | F 部署预留 |

**实施顺序**：A → B → C → D → E/F。每模块独立可验收。

---

## 模块 A：估值因素扩展（户型 / 面积 / 房龄 / 价值走向）

### A.1 目标
把「户型、面积、房龄、市场走势」作为**定性参考因素**纳入估值流程（不硬编码进计算工具，而是通过「提取 + 检索趋势知识 + 报告呈现」落地）。

### A.2 改动
1. **`app/workflow/schemas.py`**：`RequirementSchema` 增加字段：
   - `layout: str`（户型，如「三房两厅」）、`building_age: float | None`（房龄年）、`orientation: str`（朝向）、`floor: str`（楼层）、`decoration: str`（装修）
2. **`app/workflow/nodes.py`**：
   - `understand_node` 的 prompt 补充「提取户型/房龄/朝向/楼层/装修」。
   - `_supplement_params_from_question` 加正则：房龄（`(\d+)\s*年` 房龄/楼龄）、面积已有。
   - `retrieve_node`：当 question 含「趋势/走势/房龄/户型」关键词时，检索 `07_wuhan_market_trend.md` 相关内容。
   - `report_node` 新增「参考因素说明」段：列出户型/房龄/朝向 + 检索到的趋势依据（来源标注）。
3. **知识库**：把 `WUHAN_MARKET_DATA.md` 内容写入 `data/docs/07_wuhan_market_trend.md`，`--rebuild` 重建向量库。
4. **`verify_node` 的 prompt**：提示结合房龄（折旧）、趋势（交易日期修正）对结果做定性复核。

### A.3 验收
- [ ] 问「一套 2015 年建的 89㎡ 两房，光谷，估值」，报告含「参考因素说明」段，列出房龄约 10 年、户型 89㎡，并引用 `07_wuhan_market_trend.md` 的趋势/户型依据。
- [ ] `test_workflow` 不回归。

---

## 模块 B：多格式入库（PDF / Word / 图片）

### B.1 目标
`loader` 支持 `.md` / `.pdf` / `.docx` / 图片（`.png/.jpg/.jpeg`），按扩展名分发。

### B.2 改动
1. **依赖**：`requirements.txt` 加 `pypdf>=4`、`python-docx>=1.1`。
2. **`app/rag/loader.py`** 扩展为按扩展名分发：
   - `.md` → 现有逻辑
   - `.pdf` → `pypdf.PdfReader` 逐页提取文本（`page.extract_text()`）
   - `.docx` → `python-docx` 遍历 `document.paragraphs` 拼接文本
   - 图片 → 调视觉模型转文字描述（见模块 C）
   - 未知扩展名 → 跳过并告警
3. **`scripts/build_index.py`** 扫描目录时支持上述扩展名；`make_docs.py` 校验逻辑放宽（不再强制 `.md`）。
4. 每个 `Document` 的 metadata 记录 `source`（文件名）+ `path` + `file_type`。

### B.3 验收
- [ ] 放入一个测试 `.pdf` 和一个 `.docx`，`build_index.py --rebuild` 能入库，`retrieve` 能命中其中内容。
- [ ] 图片文件经视觉模型转文字后可被检索（与模块 C 联调）。

### B.4 坑点
- 扫描型 PDF（图片无文本层）`extract_text()` 返回空，需走视觉模型兜底。
- Word 表格/图片内容纯段落提取会丢失，demo 阶段可接受，需在 README 说明。

---

## 模块 C：多模态（视觉模型解析图片）

### C.1 目标
用 OpenAI 兼容的**通义千问 VL（Qwen-VL，DashScope）**把图片转成文字描述，供入库与问答使用。DeepSeek 继续负责文本推理。

### C.2 改动
1. **`.env` / `.env.example`** 新增（已定通义千问 VL）：
   ```
   VISION_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
   VISION_API_KEY=sk-xxx（DashScope 平台申请的 key）
   VISION_MODEL=qwen-vl-plus
   ```
   > `qwen-vl-plus` 性价比高、适合文档/户型图/截图解析；追求更强效果可换 `qwen-vl-max`。两者均走 DashScope 的 OpenAI 兼容模式，与 DeepSeek 的文本接口是两套独立配置。
2. **新增 `app/vision.py`**：封装 `describe_image(image_bytes_or_base64, prompt) -> str`。
   - 用 `langchain_openai.ChatOpenAI`，`base_url`/`api_key`/`model` 走 VISION_ 配置。
   - 消息格式：`HumanMessage(content=[{"type": "text", "text": prompt}, {"type": "image_url", "image_url": {"url": "data:image/png;base64,<b64>"}}])`。
3. **`app/rag/loader.py`**：图片分支调用 `describe_image`，返回的文本作为 `Document.page_content`（metadata 记原图名 + `file_type: image`）。
4. **（可选）问答端**：若用户通过 admin 上传图片并提问，可扩展 `understand` 前先对图片生成描述注入上下文。

### C.3 验收
- [ ] 用一张测试图片（如户型图/房价走势截图），`describe_image` 返回中文文字描述。
- [ ] 图片入库后可被检索命中（联调模块 B）。

### C.4 坑点
- 视觉模型兼容端点格式差异：Qwen-VL 走 DashScope `compatible-mode/v1`，GLM-4V 走智谱 `api/paas/v4`；base64 前缀 `data:image/<fmt>;base64,` 必须正确。
- 图片大小：视觉模型有单图大小上限，入库前需压缩/缩放。
- 成本：视觉模型按 token 计费，图片解析会显著增加成本，仅对图片文件调用。

---

## 模块 D：后端管理入口（区别于问答前端）

### D.1 目标
提供**独立的后台入口**上传/管理知识库文件，与面向用户的问答前端区分。

### D.2 改动
1. **新增 `app/admin.py`**（或 `server.py` 挂载）：
   - `POST /admin/upload`：接收文件（multipart），按类型解析→切分→向量化→**增量入库**。
   - `GET /admin/documents`：列出已入库文档（source + 类型 + 时间）。
   - `DELETE /admin/documents/{source}`：删除该文档相关向量。
2. **鉴权**：`.env` 加 `ADMIN_TOKEN`，admin 接口校验 `X-Admin-Token`（或 Basic Auth）。**挂网页必须**，不能裸奔。
3. **前端**：独立 admin 页（`/admin` 路由 + `app/web/admin/`），提供上传表单 + 文档列表 + 删除按钮；与 `/` 问答页视觉与入口区分。
4. **增量入库**：上传后不破坏已有向量；实现方式可选「Chroma 按 source 增量 add / delete」，或「全量 rebuild 但先合并目录」。
5. **上传后自动重建可用**：上传新文档后无需手动跑 `build_index.py`。

### D.3 验收
- [ ] 通过 `/admin/upload` 上传一个 `.md`/`.pdf`，`GET /admin/documents` 能看到，`/api/ask` 能检索到新内容。
- [ ] `DELETE /admin/documents/{source}` 后该文档内容不再被检索。
- [ ] 未带 `ADMIN_TOKEN` 访问 admin 接口返回 401。

### D.4 坑点
- 文件上传大小限制（FastAPI 默认无硬限制，需设上限，如 20MB）。
- 文件解析失败要给明确错误（如「PDF 无文本层」），不能静默。
- 增量删除：Chroma 按 metadata 过滤删除需用 `collection.delete(where={"source": ...})`。
- 上传的临时文件要落盘到安全目录，避免路径穿越。

---

## 模块 E：前端 UI 优化

### E.1 目标
问答页更专业、信息层次更清晰、适配移动端；admin 页简洁可用。

### E.2 方向（codex 在既有风格上深化，勿推翻重来）
- 问答页：报告卡片信息层次（标题/分区/表格样式）、执行过程时间线的视觉衔接、加载与空态、示例问题分组。
- 增加「参考因素」区块的样式（模块 A 报告新段）。
- admin 页：独立布局，上传拖拽区 + 文档表格 + 删除确认。
- 响应式：窄屏下时间线/表格不溢出。

### E.3 验收
- [ ] 桌面与窄屏（≈375px）下问答页可正常使用、无明显错位。
- [ ] admin 页上传/删除流程可用。

---

## 模块 F：部署预留

### F.1 目标
为「挂网页」预留，不阻塞当前 demo。

### F.2 清单（本轮只需做前两项，其余列在 README）
1. 所有密钥/配置走 `.env`（已基本做到，核查 `VISION_*`、`ADMIN_TOKEN` 不硬编码）。
2. README 增补「部署说明」：`uvicorn app.server:app --host 0.0.0.0 --port 8000`、多 worker 建议、`requirements.lock` 安装方式。
3. 记录依赖体积（torch 较大）与最小机器配置要求。
4. 预留：HTTPS 反向代理（Nginx/Caddy）、静态资源缓存、向量库与上传文件目录的持久化路径说明。

### F.3 验收
- [ ] README 有完整的本地运行 + 部署指引；`.env.example` 含全部配置项。

---

## 分阶段验收总表

| 阶段 | 模块 | 核心验收 |
|---|---|---|
| 1 | A | 报告含「参考因素说明」段，检索命中 07 武汉趋势文档 |
| 2 | B + C | PDF/Word/图片可入库可检索；图片经视觉模型转文字 |
| 3 | D | admin 上传/列表/删除可用，带鉴权，增量入库 |
| 4 | E + F | UI 优化 + 部署指引 + 配置核查 |

**全局不回归**：每阶段完成后 `python -m unittest tests.test_workflow` 必须通过，`run_eval.py` / Web 问答功能正常。

---

## 关键坑点汇总（必须遵守）

1. **视觉模型兼容格式**：通义 Qwen-VL 走 DashScope 的 OpenAI 兼容模式（base_url 结尾必须是 `/compatible-mode/v1`），图片消息用 `{"type": "image_url", "image_url": {"url": "data:image/<fmt>;base64,<b64>"}}`；与 DeepSeek 的纯文本接口是两套独立配置，勿混用。
2. **图片压缩**：入库前缩放长边（如 ≤1280px）并转 JPEG/PNG，避免超出视觉模型大小限制。
3. **扫描 PDF 兜底**：`extract_text()` 为空时改走视觉模型（逐页转图再描述）。
4. **admin 鉴权**：`ADMIN_TOKEN` 必配，接口未鉴权禁止上生产。
5. **增量入库正确性**：上传新文档不重复、删除后不残留；用 `collection.delete(where={"source": ...})` 精确删除。
6. **路径安全**：上传文件名白名单/清洗，存储用服务端生成的唯一文件名，防路径穿越。
7. **成本与缓存**：视觉模型只对图片调用；embedding 与 LLM 已单例缓存，勿重复实例化。
8. **数据诚实性**：武汉趋势文档为参考性质，报告中引用时应保留「仅供参考、以官方为准」的说明。

---

## 给实现方（codex）的执行约定

1. 按 A → B → C → D → E/F 顺序推进，每模块对照验收自测。
2. 复用 `retrieve`/工具/`workflow_app`/`renderMarkdown` 等已有实现，不重写。
3. `WUHAN_MARKET_DATA.md` 内容复制到 `data/docs/07_wuhan_market_trend.md` 后 `--rebuild`。
4. 视觉模型配置先做成「可选」：未配 `VISION_*` 时图片入库给出明确提示而非崩溃。
5. 每完成一个模块提交交付说明（实现功能、运行方式、验收结果、新增/修改文件）。
