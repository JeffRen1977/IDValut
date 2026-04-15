# Agents in this workspace (`idvault`)

- **idvault**（本工作区）：身份与**肖像权授权**数据的守门代理。工作目录：`known_faces/`（特征或加密索引）、`licenses/`（授权记录）、`Case_Log.md`（侵权/核验案例流水）。详见 `SOUL.md` 与 `skills/`。

本工作区**自成一体**：职责仅限身份与授权数据，不依赖任何其他产品或代理仓库。若你在 OpenClaw 里还运行其他代理，仅当你**主动配置** `tools.agentToAgent` 时，它们才可能向 **idvault** 发核验类任务；未配置则完全独立。参见 `OPENCLAW.md`。

## Skills

| Skill | 用途 |
|--------|------|
| `skills/idvault-face-index/` | `known_faces/` 目录约定、索引格式、禁止提交秘密 |
| `skills/idvault-authorization/` | 授权状态查询流程、`licenses/` 结构、`Case_Log.md` 写法 |

## 安全提示

- **不要将** 明文特征、密钥或大型模型权重提交到 Git；使用 `.gitignore` 与本地加密存储（见 `known_faces/README.md`）。
