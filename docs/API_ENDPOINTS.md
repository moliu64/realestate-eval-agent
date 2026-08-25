# API Endpoints

## Base URL

本地：`http://127.0.0.1:8000`。前端同源访问时使用相对路径。

## Authentication

认证使用 HttpOnly Cookie `realestate_auth`。登录、注册和登出接口位于 `/api/auth`。会话接口、独立 RAG 接口和会话内业务操作要求登录；预设读取、兼容旧版问答、无会话估价和户型图解析接口当前保持公开；知识库管理和 `/admin` 页面要求管理员角色。

错误响应统一为：

```json
{"detail": "错误说明"}
```

## Authentication Endpoints

| Method | Path | Auth | Description |
| --- | --- | --- | --- |
| `POST` | `/api/auth/login` | Public | 登录并设置认证 Cookie |
| `POST` | `/api/auth/register` | Public | 注册普通用户，用户名不可重复 |
| `POST` | `/api/auth/logout` | Optional | 清除当前登录态 |
| `GET` | `/api/auth/me` | Optional | 获取当前认证状态 |

注册请求：`{ "username": string, "password": string, "confirm_password": string }`。

## Sessions and Valuation

| Method | Path | Auth | Description |
| --- | --- | --- | --- |
| `GET` | `/api/sessions` | User | 获取当前账号会话列表 |
| `POST` | `/api/sessions` | User | 创建会话 |
| `GET` | `/api/sessions/{session_id}` | Owner | 获取会话详情 |
| `PATCH` | `/api/sessions/{session_id}` | Owner | 更新固定参数和户型图信息 |
| `DELETE` | `/api/sessions/{session_id}` | Owner | 删除会话 |
| `POST` | `/api/sessions/{session_id}/messages` | Owner | 提交估价消息并生成报告 |
| `POST` | `/api/sessions/{session_id}/rag` | Owner | 在当前会话中进行 RAG 问答 |
| `POST` | `/api/evaluate` | Public | 无会话的估价调用 |
| `POST` | `/api/ask` | Public | 兼容旧版问答入口 |

## RAG and Presets

| Method | Path | Auth | Description |
| --- | --- | --- | --- |
| `POST` | `/api/rag` | User | 独立 RAG 问答 |
| `GET` | `/api/presets/options` | Public | 获取预设选项 |
| `GET` | `/api/presets/wuhan` | Public | 获取武汉区域年度预设 |
| `POST` | `/api/analyze-layout` | Public | 上传户型图并调用视觉模型解析 |

## Knowledge Base Administration

以下接口均要求登录且 `role=admin`。普通用户可以使用 RAG 检索，但不能访问这些管理接口。

| Method | Path | Description |
| --- | --- | --- |
| `GET` | `/admin` | 管理页面 |
| `GET` | `/admin/access` | 检查管理员权限 |
| `POST` | `/admin/preview` | 预览上传文件的切片 |
| `POST` | `/admin/upload` | 上传或覆盖知识文档并重建向量库 |
| `GET` | `/admin/documents` | 列出知识文档 |
| `GET` | `/admin/documents/{source}` | 预览已入库文档切片 |
| `DELETE` | `/admin/documents/{source}` | 删除文档并重建向量库 |

支持 `.md`、`.txt`、`.csv`、`.pdf`、`.docx`、`.png`、`.jpg`、`.jpeg`，单文件最大 20 MB。

## Status Codes

- `400`: 请求参数或文件格式错误
- `401`: 未登录或认证已失效
- `403`: 已登录但没有管理员权限，或无权访问其他账号的资源
- `404`: 资源不存在或不属于当前账号
- `409`: 用户名已存在
- `413`: 上传文件超过大小限制
- `500`: 服务端或模型调用异常
