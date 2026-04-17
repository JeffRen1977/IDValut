---
name: idvault_daily_monitor
description: Daily YouTube/TikTok URL intake, local face recognition vs known_faces, license cross-check, LLM video summary, and structured warning output. Use for the IDVault monitoring pipeline.
---

# IDVault — 每日视频监测流水线

## 目标

每个周期（建议**每日**）：

1. **收集** 待扫描的视频链接（YouTube / TikTok）。
2. **本地下载或抽帧**（由你仓库内的脚本实现；不在此 Skill 里绑定具体工具名）。
3. **本地人脸识别**：与 `known_faces/`（艺人 / 客户入库特征或加密索引）比对，得到候选 **subject_id** 与相似度（仅内部使用，对外报告可脱敏）。
4. **授权核对**：对每个命中主体查 `licenses/`；若**无有效授权**覆盖该视频用途/渠道/时间窗，则视为需预警的 **unlicensed_match**（或 `not_found` / `expired`）。
5. **LLM 视频理解**：在**已允许的**素材上使用模型生成简短、事实向的 **内容摘要**（主题、场景类型、是否明显商业推广等），**不得**编造未在元数据/转写/画面中体现的细节。
6. **产出告警**：写入 `reports/YYYY-MM-DD/` 下的结构化文件，并触发你们的「发出预警」机制（邮件、Webhook、企业微信等 —— 由实现脚本配置）。

## 目录约定

| 路径 | 用途 |
|------|------|
| `ingest/daily_urls.txt` 或 `ingest/YYYY-MM-DD/sources.json` | 当日待扫链接列表（可手工或爬虫脚本更新） |
| `known_faces/` | 艺人/客户人脸索引（见 `idvault-face-index`） |
| `licenses/` | 授权范围（见 `idvault-authorization`） |
| `reports/YYYY-MM-DD/` | 告警与汇总输出（**可**提交摘要 JSON/Markdown；**勿**提交原始视频） |
| `Case_Log.md` | 跨日案例索引；重要告警应有一条对应 `case_id` |

## 标准告警载荷（每条命中至少一份）

告警文件建议命名：`alert_<alert_id>.json` 或与 `case_id` 对齐。

必填字段逻辑：

- **video_title**：平台展示标题（或抓取时等价元数据）。
- **video_url**：canonical 链接。
- **platform**：`youtube` | `tiktok`（或扩展枚举）。
- **matched_subjects**：列表；每项含 `subject_id`、对外可用的 **celebrity_label**（展示名）、**license_status**（对此视频语境的结论）、可选 **similarity_tier**（如 `high` / `medium`，避免对外贴原始分数除非流程要求）。
- **llm_summary**：基于允许素材的短摘要，标注「摘要依据：标题/描述/转写/抽帧」之一或多者。
- **alert_reason**：固定短语之一，例如 `unlicensed_face_match`、`license_expired`、`license_scope_mismatch`。
- **case_id**：与 `Case_Log.md` 同步。
- **generated_at**：UTC ISO8601。

## 代理行为

- 协调**已有**脚本与数据：不虚构比对结果；若某步未实现，明确写「待接入：…」。
- 摘要与告警文本保持**可审计**；引用 `case_id` 与报告路径。
- 仍遵守 `SOUL.md`：**无法律结论**，不保证「构成侵权」，只报告事实与授权库状态。

## 与「发出预警」

- Skill 只定义**产出物**；实际发送由 `scripts/` 或外部自动化读取 `reports/` 完成（避免在 Skill 里写死密钥）。

## 参考实现

本仓库下已提供可直接运行的流水线脚本（详见 `scripts/README.md`）：

- `scripts/face_utils.py` — 核心人脸检测 / 嵌入 / 相似度（基于 DeepFace + Facenet，本地运行）。
- `scripts/build_known_faces.py` — 从 `known_faces/images/<subject_id>/*` 构建 `known_faces/index.json`。
- `scripts/analyze_video.py` — 单视频抽帧识别，输出 `scan_*.json` 与命中时的 `alert_*.json`（含授权状态）。
- `scripts/run-daily-idvault.sh` — 按日编排：`ingest/` → `yt-dlp` → `analyze_video.py` → `reports/<DATE>/`。

### 发现（可选前置）

- `scripts/discover_youtube.py` — YouTube Data API（或 yt-dlp `ytsearch` 回退）按主体 × 关键词模板搜索。
- `scripts/discover_rss.py` — 订阅 `seeds.yaml` 里登记的 YouTube 频道 Atom RSS。
- `scripts/discover_tiktok.py` — TikTok 用户/话题页面（yt-dlp），**仅扫描显式登记种子**。
- `scripts/_merge_candidates.py` — 合并/去重（以 `platform:video_id` 为键，命中 `ingest/cache/seen.json` 则跳过），写 `ingest/<DATE>/sources.json`。
- `scripts/run-discover.sh` — 以上的编排器；也可 `run-daily-idvault.sh --discover` 链式触发。

发现策略与 ToS/配额边界：`docs/DISCOVERY_POLICY.md`。种子文件：`ingest/seeds.yaml`（可提交）；凭证在 `~/.idvault-env`（**勿**提交）。

代理在协调任务时应优先复用这些脚本，而不是自行发明对等逻辑；若需要扩展（如新加平台、新增告警渠道），在 `scripts/` 下新增脚本并在 `AGENTS.md` 中登记。
