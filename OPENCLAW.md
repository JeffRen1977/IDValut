# OpenClaw：IDVault 代理注册与可选多代理

本仓库目录名是 **IDValut**（历史拼写）；OpenClaw 代理 id 为 **`idvault`**。

## 1. 注册代理（已完成可跳过）

```bash
openclaw agents add idvault \
  --workspace /home/renjeff/Documents/projects/IDValut \
  --non-interactive
```

验证：

```bash
openclaw agents list --bindings
```

状态目录：`~/.openclaw/agents/idvault/`（sessions、agent 配置与其他代理**相互隔离**）。

## 2. 加载人设到 Gateway

```bash
openclaw agents set-identity --agent idvault --from-identity
```

（读取本仓库根目录 `IDENTITY.md`。）

## 3. Agent ↔ Agent（**可选**，仅在你需要跨代理派单时）

OpenClaw 使用 **`tools.agentToAgent`**（不是名为 `internal_messaging` 的字段）。若要让**其他** OpenClaw 代理能把核验请求转给 **idvault**，在 `~/.openclaw/openclaw.json` 的 `tools` 中配置，例如：

```json
"agentToAgent": {
  "enabled": true,
  "allow": ["idvault", "some-other-agent-id"]
}
```

将 `some-other-agent-id` 换成你实际存在的代理 id；**不配置此项则 idvault 与其他代理在消息层无自动往来**，仅共享同一 Gateway 进程（若你本地只跑 idvault，可忽略本节）。

修改后重启 Gateway：

```bash
openclaw gateway restart
```

官方说明：[Multi-Agent Routing](https://docs.openclaw.ai/concepts/multi-agent)。

## 4. 路由（可选）

IDVault 可以**只作为后台代理**，不绑定任何即时通讯渠道。若需要独立入口（例如专用 Telegram/WhatsApp 账号），再使用：

```bash
openclaw agents bind --agent idvault --bind <channel:account>
```

## 5. 工作区隔离

**idvault** 的代码与敏感数据应只放在本仓库（`IDValut`）下，与业务线、内容生产等其他项目**物理分离**，避免肖像/生物特征索引与无关稿件或素材混在同一目录树。
