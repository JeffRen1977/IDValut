# Agents in this workspace (`idvault`)

- **idvault**（本工作区）：**每日**监测 YouTube/TikTok 等视频链接，**本地**人脸比对艺人/客户库（`known_faces/`），核对授权（`licenses/`），对未授权或存疑命中生成 **告警包**（视频标题、链接、对应名人标签、LLM 视频摘要），并触发**预警下发**。流水与案例见 `Case_Log.md`、`reports/`。人设见 `SOUL.md`。

本工作区**自成一体**：不依赖其他产品仓库。OpenClaw 多代理协作见 `OPENCLAW.md`（可选）。

## 数据流（期望形态）

1. **ingest/** — 当日待扫 URL 列表（人工或脚本写入）。
2. **本地 FR** — 你的识别算法（本仓库后续可放 `scripts/`，GPU/模型仅在本地运行）。
3. **licenses/** — 判断该使用场景是否允许；无覆盖则进入告警。
4. **LLM** — 对允许素材生成短摘要，写入告警 JSON。
5. **reports/YYYY-MM-DD/** — 结构化告警；**预警发送**由 webhook/邮件等脚本消费（勿把密钥写入 Git）。

## Skills

| Skill | 用途 |
|--------|------|
| `skills/idvault-daily-monitor/` | 每日流水线、告警字段、目录约定 |
| `skills/idvault-face-index/` | `known_faces/` 目录与索引约定 |
| `skills/idvault-authorization/` | 授权查询、`Case_Log`、与告警联动 |

## 安全提示

- **不要将** 明文特征、密钥、原始视频缓存提交到 Git；见根目录 `.gitignore` 与 `known_faces/README.md`。
