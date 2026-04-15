# OpenClaw：IDVault 代理注册与多代理协作

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

状态目录：`~/.openclaw/agents/idvault/`（sessions、agent 配置与 **main 隔离**）。

## 2. 加载人设到 Gateway

```bash
openclaw agents set-identity --agent idvault --from-identity
```

（读取本仓库根目录 `IDENTITY.md`。）

## 3. Agent ↔ Agent（对应文档中的「内部协作」）

OpenClaw 使用 **`tools.agentToAgent`**（不是名为 `internal_messaging` 的字段）。在 `~/.openclaw/openclaw.json` 的 `tools` 中增加：

```json
"agentToAgent": {
  "enabled": true,
  "allow": ["main", "idvault"]
}
```

这样 **main** 可在工具流程中向 **idvault** 派发核验类任务（具体工具名以当前 OpenClaw 版本为准）。

修改后重启 Gateway：

```bash
openclaw gateway restart
```

官方说明：[Multi-Agent Routing](https://docs.openclaw.ai/concepts/multi-agent)（文中含 `tools.agentToAgent` 示例）。

## 4. 路由（可选）

IDVault 通常**不**绑定 WhatsApp/Telegram，仅作为后台代理；**main** 继续处理渠道消息。若需单独入口，再使用：

```bash
openclaw agents bind --agent idvault --bind <channel:account>
```

## 5. WeChat 工作区

**main** 仍使用 `~/Documents/projects/wechat`；与 **idvault** 工作区物理分离，避免肖像数据与公众号稿件混在同一棵树。
