# 项目文档

本目录保存项目架构、接口、本地运行说明与界面截图，以及迭代过程中的历史计划与评审记录。运行所需的 RAG 知识文档位于 `data/docs/`，不要与本目录混用。

## 当前文档

| 文档 | 内容 |
| --- | --- |
| [`ARCHITECTURE.md`](ARCHITECTURE.md) | 当前分层、组件、请求流、估价工作流、认证与隔离、RAG、存储、配置、本地启动与已知约束 |
| [`API_ENDPOINTS.md`](API_ENDPOINTS.md) | FastAPI 路由、Cookie 认证、权限、字段、状态码与上传限制 |
| [`screenshots/`](screenshots/) | 本地启动面板、登录页、工作台、报告、知识库管理与移动端截图（README 引用） |
| [`reference/WUHAN_MARKET_DATA.md`](reference/WUHAN_MARKET_DATA.md) | 武汉市场数据原始整理稿（预设口径的参考资料） |

项目级文档位于仓库根目录：

- [README.md](../README.md)：项目定位、快速开始、配置、本地启动面板、使用方式与边界
- [CONTRIBUTING.md](../CONTRIBUTING.md)：开发流程、分层约定与 PR 检查清单
- [SECURITY.md](../SECURITY.md)：认证机制、数据保护与本地运行安全边界

本地启动方式以根目录 README 的「快速开始 / 本地启动与一键面板」为准：双击 `start_panel.bat`，或运行 `python run.py panel` / `python run.py web`。

## 历史记录

以下文件是项目迭代过程中的决策与评审记录，**不是当前运行文档**。其中提到的旧入口、旧配置名和旧目录结构可能已过时，当前实现以根目录 `README.md` 与源码为准。

### 计划

- [`plans/PLAN.md`](plans/PLAN.md)：Phase 0–1 基础规划
- [`plans/PLAN_PHASE2.md`](plans/PLAN_PHASE2.md)：Tool Calling Agent
- [`plans/PLAN_PHASE3.md`](plans/PLAN_PHASE3.md)：多方法估价工作流
- [`plans/PLAN_ENHANCEMENT.md`](plans/PLAN_ENHANCEMENT.md)：流式步骤与结构化输出
- [`plans/PLAN_EXPANSION.md`](plans/PLAN_EXPANSION.md)：数据、管理与视觉能力扩展
- [`plans/PLAN_UI_REFACTOR.md`](plans/PLAN_UI_REFACTOR.md)：Web UI 重构

### 评审

- [`reviews/REVIEW.md`](reviews/REVIEW.md)：Phase 1 评审
- [`reviews/REVIEW_PHASE2.md`](reviews/REVIEW_PHASE2.md)：Phase 2 评审
- [`reviews/REVIEW_PHASE3.md`](reviews/REVIEW_PHASE3.md)：Phase 3 评审
- [`reviews/REVIEW_EXPANSION.md`](reviews/REVIEW_EXPANSION.md)：扩展阶段评审

## 维护约定

- 新增或修改接口时，同步更新 `API_ENDPOINTS.md` 与 `README.md` 的 API 摘要。
- 调整分层、存储、认证或本地启动流程时，同步更新 `ARCHITECTURE.md`。
- 更新界面后重新生成 `screenshots/` 中的截图（含 `launcher.png`），保持 README 引用有效。
- 本项目定位为纯本地运行；不要引入公网部署、域名、隧道或反向代理相关配置与文档。
- 历史计划与评审保持原样，不复改写成当前文档；如需说明过时内容，在本页注明。
