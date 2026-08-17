# Cloudflare Tunnel 部署

## 当前拓扑

```text
浏览器 -> Cloudflare HTTPS -> Cloudflare Tunnel -> 127.0.0.1:8000 -> FastAPI
```

公网地址为 `https://060115.top`。模型、`.env`、知识文档和向量库均保留在本机，Cloudflare 只负责 DNS、TLS 和隧道转发。

## 本机文件

- Tunnel 配置：`%USERPROFILE%\.cloudflared\config.yml`
- Tunnel 凭证：`%USERPROFILE%\.cloudflared\<tunnel-id>.json`
- 手动总入口：项目根目录 `start_online.bat`
- 单独运行 Tunnel：`scripts\deployment\run_tunnel.bat`
- 登录自动任务：Windows 任务计划程序中的 `RealEstateAgentOnline`

Tunnel 凭证和 `.env` 不得提交到 Git。

## 运维检查

```powershell
# 启动或恢复后端和 Tunnel
.\start_online.bat

# 查看自动任务最近结果，0 表示成功
Get-ScheduledTaskInfo -TaskName RealEstateAgentOnline

# 查看 Tunnel 连接
cloudflared tunnel info realestate-agent-060115

# 公网健康检查
curl.exe -I https://060115.top
```

## 运行约束

- 电脑必须保持开机、联网且不能休眠。
- 当前自动任务在用户登录时运行，不是无人登录的系统服务。
- 公网估值、知识检索和视觉接口会消耗模型额度，正式开放前应配置 Cloudflare 限流或 Turnstile。
- 修改 `.env` 或后端代码后，需要重启后端；双击 `start_online.bat` 可补启动缺失进程。
