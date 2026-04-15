# Agents in this workspace (`idvault`)

- **idvault**（本工作区）：身份与**肖像权授权**数据的守门代理。工作目录：`known_faces/`（特征或加密索引）、`licenses/`（授权记录）、`Case_Log.md`（侵权/核验案例流水）。详见 `SOUL.md` 与 `skills/`。

## 与 `main`（WeChat）协作

- **main** 负责内容生产与渠道；**idvault** 不负责发文。
- 当 **main** 需要核实「某素材中是否出现库内艺人/是否已授权」时，应通过 OpenClaw **agent-to-agent** 向 **idvault** 发任务（需在 `openclaw.json` 中启用 `tools.agentToAgent` 并 allowlist `main` 与 `idvault`）。参见 `OPENCLAW.md`。
- idvault 的回复应可被 main **引用为事实依据**（subject_id、授权条目、Case_Log 条目），但**不**在消息中粘贴敏感向量或原始特征文件内容。

## Skills

| Skill | 用途 |
|--------|------|
| `skills/idvault-face-index/` | `known_faces/` 目录约定、索引格式、禁止提交秘密 |
| `skills/idvault-authorization/` | 授权状态查询流程、`licenses/` 结构、`Case_Log.md` 写法 |

## 安全提示

- **不要将** 明文特征、密钥或大型模型权重提交到 Git；使用 `.gitignore` 与本地加密存储（见 `known_faces/README.md`）。
