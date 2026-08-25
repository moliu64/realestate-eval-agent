# 贡献指南

感谢参与项目改进。提交变更前请确保改动能够在本地复现，并避免提交密钥、会话数据、向量库和缓存目录。

## 开发流程

1. Fork 仓库并创建功能分支。
2. 按 README 完成本地环境和 `.env` 配置。
3. 修改代码、测试和相关文档。
4. 运行 `pytest -q` 及必要的语法检查。
5. 提交 Pull Request，说明动机、改动范围、测试结果和已知限制。

## 代码约定

- 后端使用现有 FastAPI、Pydantic 和 LangGraph 结构，不重复实现 RAG 或估价工具。
- 确定性估价逻辑放在 `app/tools/`，工作流编排放在 `app/workflow/`。
- 文档处理和向量库逻辑放在 `app/rag/`。
- 用户可见行为需要同步更新 README 或 `docs/` 文档。
- 新增接口需要更新 `docs/API_ENDPOINTS.md`，并补充权限和错误行为说明。

## 测试要求

```powershell
pytest -q
python -m py_compile app/server.py app/config.py
node --check app/web/static/app.js
node --check app/web/static/admin.js
git diff --check
```

涉及认证、会话隔离、RAG 权限或上传管理的改动，需要覆盖未登录、普通用户和管理员三类场景。
