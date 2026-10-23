# API 接口

## Base URL

本地默认地址：`http://127.0.0.1:8000`。前端由同一 FastAPI 进程同源提供，页面内使用相对路径调用 `/api/*`，不涉及跨域和独立前端服务。

本项目为**纯本地运行**：服务只监听 `127.0.0.1`，不包含域名、隧道或公网部署逻辑。本地启动面板与 `python run.py status` 通过 `GET /api/health` 判断服务状态。如需从其他设备访问，需自行增加 TLS、反向代理与限流并承担风险。

- 请求与响应均为 JSON，上传接口为 `multipart/form-data`。
- 错误响应统一为：

```json
{"detail": "错误说明"}
```

- FastAPI 请求体校验失败返回 `422`，响应体为 FastAPI 默认校验错误结构。
- `GET /api/openapi.json` 返回自动生成的 OpenAPI schema；Swagger UI 与 ReDoc 已关闭（`docs_url=None`、`redoc_url=None`）。

## 认证

认证使用 HttpOnly Cookie `realestate_auth`；管理接口通过登录 Cookie 与 `role=admin` 判定权限，不使用独立管理令牌、自定义鉴权请求头或 CORS 白名单。

| 属性 | 值 |
| --- | --- |
| Cookie 名称 | `realestate_auth` |
| HttpOnly | 是 |
| SameSite | `Lax` |
| Secure | 默认本地 HTTP 不启用；HTTPS 请求下自动启用 |
| Max-Age | 7 天（`SESSION_TTL_SECONDS`） |

- 登录成功后由 `secrets.token_urlsafe(32)` 生成不透明 token，保存在**服务进程内存**；服务重启后所有登录态失效。
- 角色为 `admin` 或 `user`。管理员账号只能来自 `.env` 的 `AUTH_USERS_JSON`；注册接口只能创建普通用户，并保存到 `AUTH_USERS_FILE`（默认 `data/auth_users.json`）。
- 注册用户密码使用 PBKDF2-SHA256（260,000 轮、随机盐）存储；`.env` 注入账号允许明文比较。
- 会话接口除登录外，还要求当前账号为会话所有者；越权访问统一返回 `404`。

权限标记：

- **公开**：无需登录。
- **可选**：未登录也可访问，已登录时返回登录信息。
- **登录**：任意已登录账号。
- **所有者**：登录账号必须是该会话的 `owner_id`。
- **管理员**：登录且 `role=admin`。

## 认证接口

前缀：`/api/auth`

| 方法 | 路径 | 权限 | 说明 |
| --- | --- | --- | --- |
| `POST` | `/api/auth/login` | 公开 | 校验账号密码，设置认证 Cookie |
| `POST` | `/api/auth/register` | 公开 | 注册普通用户 |
| `POST` | `/api/auth/logout` | 可选 | 撤销当前 token 并清除 Cookie |
| `GET` | `/api/auth/me` | 可选 | 查询当前登录状态 |

**登录**请求体：`{"username": string, "password": string}`（用户名 1–80 字符，密码 1–200 字符）。成功返回：

```json
{"authenticated": true, "username": "admin", "role": "admin", "expires_at": 1760000000.0}
```

失败返回 `401`。

**注册**请求体：`{"username": string, "password": string, "confirm_password": string}`。用户名 3–80 字符，只允许中文、字母、数字、下划线和短横线；密码至少 8 位。两次密码不一致返回 `400`，用户名已存在返回 `409`。成功返回 `{"registered": true, "username": "...", "role": "user"}`。

**登出**返回 `{"logged_out": true}`；无有效 Cookie 时同样返回成功。

**当前登录态**未登录返回 `{"authenticated": false}`；已登录返回用户名、角色与过期时间戳。

## 会话接口

前缀：`/api/sessions`

| 方法 | 路径 | 权限 | 说明 |
| --- | --- | --- | --- |
| `GET` | `/api/sessions` | 登录 | 当前账号的会话摘要列表 |
| `POST` | `/api/sessions` | 登录 | 创建会话（无请求体） |
| `GET` | `/api/sessions/{session_id}` | 所有者 | 读取完整会话 |
| `PATCH` | `/api/sessions/{session_id}` | 所有者 | 更新标题、固定参数、户型信息 |
| `DELETE` | `/api/sessions/{session_id}` | 所有者 | 删除会话 |
| `POST` | `/api/sessions/{session_id}/messages` | 所有者 | 提交估价参数与补充说明，运行工作流并写入报告 |
| `POST` | `/api/sessions/{session_id}/rag` | 所有者 | 在当前会话内做知识库问答 |

- `session_id` 必须是 32 位十六进制字符串，否则返回 `400`。
- 列表项包含 `id`、`title`、`updated_at`、`message_count`、`last_user_message`。
- `PATCH` 请求体字段均可选：`title`、`fixed_fields`、`layout_description`、`layout_filename`。
- `/messages` 请求体继承估价结构化参数（见下节），另支持 `message`（补充说明，最长 5000 字符）；省略时使用默认提示。响应为 `{"session": {...}, "message": {...}}`，助手消息包含 `content`（Markdown 报告）、`steps`（步骤时间线）、`report_json`。
- `/rag` 请求体：`{"question": string}`（1–500 字符）。向量库不可用时返回 `503`。

## 估价与知识接口

| 方法 | 路径 | 权限 | 说明 |
| --- | --- | --- | --- |
| `POST` | `/api/evaluate` | 公开 | 无会话估价，提交结构化参数 |
| `POST` | `/api/ask` | 公开 | 无会话自然语言问答，运行完整估价工作流 |
| `POST` | `/api/rag` | 登录 | 独立 RAG 问答 |
| `GET` | `/api/presets/options` | 公开 | 预设的区县、年份、用途与数据来源 |
| `GET` | `/api/presets/wuhan` | 公开 | 武汉区域年份预设参数 |
| `POST` | `/api/analyze-layout` | 公开 | 上传户型图并调用视觉模型解析 |

**估价结构化参数**（`/api/evaluate`、`/api/sessions/{id}/messages` 共用）：

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `property_usage` | string | 用途：住宅、商铺、办公、工业厂房 |
| `area` | number | 建筑面积（平方米） |
| `layout` | string | 户型，如三室两厅 |
| `building_age` | number | 房龄（年） |
| `orientation` | string | 朝向 |
| `floor` | string | 楼层 |
| `decoration` | string | 装修状况 |
| `location` | string | 区位 |
| `valuation_purpose` | string | 估价目的 |
| `valuation_date` | string | 估价时点 |
| `comparable_price` | number | 可比成交单价（元/平方米） |
| `net_income` | number | 年度稳定净收益（元） |
| `cap_rate` | number | 资本化率（小数，如 5% 填 0.05） |
| `land_value` | number | 土地价值（元） |
| `replacement_cost` | number | 建筑物重置成本（元） |
| `depreciation` | number | 建筑物折旧（元） |
| `preset_year` | number | 预设数据年份（2019–2024） |
| `preset_sources` | string[] | 预设数据来源文件名 |
| `preset_basis` | string | 预设口径说明 |
| `note` | string | 补充说明 |

`/api/evaluate` 与 `/api/ask` 的响应：

```json
{"answer": "Markdown 报告", "steps": [{"type": "understand", "label": "需求理解", "detail": {}}], "report_json": "{...}"}
```

`/api/rag` 响应：`{"answer": "回答文本"}`；未配置文本模型时降级返回检索摘要，检索不到依据时返回「没有找到相关依据」。

**预设选项**返回 `districts`、`years`、`property_usages`、`sources`。**武汉预设**查询参数：`district`（必填）、`year`（必填，2019–2024）、`property_usage`（默认 `住宅`）、`area`、`building_age`；返回代表级别、年份系数、官方楼面地价，以及带「公式推导 / 估值假设」标注的 `comparable_price`、`net_income`、`cap_rate`、`land_value`、`replacement_cost`、`depreciation` 字段与风险提示。非法区县 / 年份 / 用途返回 `400`。

**户型图解析**为 `multipart/form-data`，字段名 `file`，仅支持 `.png`、`.jpg`、`.jpeg`；大小受 `MAX_UPLOAD_MB` 限制（默认 20MB，超出返回 `413`）。未配置视觉模型时返回 `503`。响应：`{"layout": "解析文本"}`。

## 管理接口

以下接口均使用 `role=admin` 判定权限。`GET /admin` 是页面路由：未登录或普通用户访问时返回 `302` 重定向到 `/`，只有管理员才会拿到管理页 HTML；其余 `/admin/*` JSON 接口未登录返回 `401`，普通用户返回 `403`。普通用户仍可使用 RAG 检索。

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| `GET` | `/admin` | 知识库管理页面（HTML）；非管理员 `302 → /` |
| `GET` | `/admin/access` | 校验管理员权限 |
| `POST` | `/admin/preview` | 预览上传文件的切片结果 |
| `POST` | `/admin/upload` | 上传或覆盖文档并同步重建向量库 |
| `GET` | `/admin/documents` | 列出已入库文档 |
| `GET` | `/admin/documents/{source}` | 预览已入库文档切片 |
| `DELETE` | `/admin/documents/{source}` | 删除文档并重建向量库 |

- 上传字段：`file`（必填）、`category`（默认 `用户资料`）、`title`（默认取文件名）。支持 `.md`、`.txt`、`.csv`、`.pdf`、`.docx`、`.png`、`.jpg`、`.jpeg`；大小上限由 `MAX_UPLOAD_MB` 控制（默认 20MB）。
- 分类取值：`估价方法`、`市场数据`、`政策法规`、`估价规范`、`业务知识`、`用户资料`；非法分类返回 `400`。
- 上传成功返回 `source`、`file_type`、`vector_count`、`replaced`；解析或入库失败会回滚文件并返回 `400`。
- 文档列表项包含 `source`、`file_type`、`category`、`updated_at`、`size`。
- 删除成功返回 `source`、`deleted`、`vector_count`；文件不存在返回 `404`，重建失败会恢复原文件并返回 `400`。

## 系统与页面

| 方法 | 路径 | 权限 | 说明 |
| --- | --- | --- | --- |
| `GET` | `/api/health` | 公开 | 健康检查，返回 `status`、`service`、`version` |
| `GET` | `/api/openapi.json` | 公开 | OpenAPI schema |
| `GET` | `/` | 公开 | Web 工作台页面 |
| `GET` | `/static/*` | 公开 | 前端静态资源 |

健康检查响应示例：

```json
{"status": "ok", "service": "realestate-eval-agent", "version": "2.0.0"}
```

## 状态码

| 状态码 | 含义 |
| --- | --- |
| `200` | 成功 |
| `302` | 非管理员访问 `GET /admin` 时重定向到 `/` |
| `400` | 参数、文件格式、分类或文件名非法 |
| `401` | 未登录或登录态已失效 |
| `403` | 已登录但不是管理员 |
| `404` | 资源不存在、不属于当前账号或文档不存在 |
| `409` | 用户名已存在 |
| `413` | 上传文件超过 `MAX_UPLOAD_MB` 限制 |
| `422` | 请求体未通过 Pydantic 校验 |
| `500` | 未预期服务端错误 |
| `503` | 模型 / 向量库 / 外部依赖不可用 |

## 约定与限制

- 本项目面向本机单用户使用：前端与 API 同源，没有 CORS 中间件；不要直接把端口暴露到公网。
- 登录态只在进程内存中，重启服务后需要重新登录。
- 会话与注册账号是本地 JSON 文件，不支持多实例共享。
- `/api/evaluate`、`/api/ask`、预设和户型图解析当前公开，会消耗模型额度；仅建议在本机使用。
