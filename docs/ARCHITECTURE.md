# Architecture

## Overview

项目是一个单体 Python Web 应用：FastAPI 提供静态页面和 JSON API，LangGraph 编排多方法估价流程，RAG 模块从本地文档和 Chroma 向量库检索依据，估价工具负责确定性计算，视觉模块负责户型图解析。会话和注册账号当前使用本地 JSON 文件保存。

## Components

| Component | Location | Responsibility |
| --- | --- | --- |
| HTTP server | `app/server.py` | 页面、认证、会话、估价、RAG 和管理 API |
| Configuration | `app/config.py` | `.env` 解析、路径和模型配置 |
| Workflow | `app/workflow/` | 需求理解、方法规划、检索、计算、校核和报告 |
| RAG | `app/rag/` | 文档加载、格式适配、切片、检索和 Chroma 向量库 |
| Valuation tools | `app/tools/` | 市场比较法、收益法和成本法计算 |
| Vision | `app/vision.py` | 户型图和图片文档解析 |
| Web UI | `app/web/static/` | 登录、注册、会话工作台和管理员页面 |
| Indexing scripts | `scripts/indexing/` | 文档整理和向量库重建 |

## Runtime Flow

### Valuation

1. 用户登录后创建或读取自己的会话。
2. 前端提交固定参数和补充说明到会话消息接口。
3. `server.py` 构造工作流初始状态并调用 `workflow_app`。
4. 工作流按方法检索知识、调用确定性工具并累加 `computations`。
5. 多方法完成后执行校核并生成 Markdown 报告和结构化 JSON。
6. 服务端将用户消息、报告、步骤和 JSON 持久化到该账号的会话文件。

### Authentication and Isolation

登录成功后服务端签发 HttpOnly Cookie，并在进程内维护短期认证会话。`.env` 中的管理员和普通账号用于登录，注册普通账号保存为 `data/auth_users.json`。会话文件使用 `user:<username>` 作为 owner，读取和修改前都会校验 owner。

### RAG Retrieval

普通用户和管理员都可以调用 RAG 检索。检索只读知识库，不允许普通用户修改文档或重建向量库；管理接口统一通过管理员角色校验。

## Storage

| Path | Type | Git policy |
| --- | --- | --- |
| `data/docs/` | Markdown 等知识源 | 提交 |
| `data/vector_db/` | Chroma 本地索引 | 忽略，按需重建 |
| `data/sessions/` | 会话 JSON | 忽略 |
| `data/auth_users.json` | 注册账号哈希 | 忽略 |

## Configuration

`.env.example` 是配置模板。主要配置包括文本模型、视觉模型、Embedding 模型、文档目录、向量库目录、认证账号、监听地址和 CORS 来源。真实密钥只能放在 `.env` 或部署平台的密钥管理中。

## Deployment

本地入口是 `python run_web.py`，监听 `APP_HOST:APP_PORT`。Windows 在线入口 `start_online.bat` 会启动后端和本机 Cloudflare Tunnel；Tunnel 配置位于用户目录的 `.cloudflared/config.yml`，不提交到仓库。

## Known Constraints

- 认证会话存储在进程内，重启服务会使登录 Cookie 失效。
- 会话、注册账号和向量库是本地文件，不适合多实例部署。
- 对外开放前需要增加限流、审计、备份和集中式账号存储。
