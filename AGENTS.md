# Agents in this workspace (`idvault`)

- **idvault**（本工作区）：**每日**监测 YouTube/TikTok 等视频链接，**本地**人脸比对艺人/客户库（`known_faces/`），核对授权（`licenses/`），对未授权或存疑命中生成 **告警包**（视频标题、链接、对应名人标签、LLM 视频摘要），并触发**预警下发**。流水与案例见 `Case_Log.md`、`reports/`。人设见 `SOUL.md`。

本工作区**自成一体**：不依赖其他产品仓库。OpenClaw 多代理协作见 `OPENCLAW.md`（可选）。

## 数据流（期望形态）

1. **ingest/** — 当日待扫 URL 列表（人工或脚本写入）。
2. **本地 FR** — 本仓库 `scripts/` 下的 DeepFace 流水线（`face_utils.py` + `analyze_video.py`），GPU/模型仅在本地运行。
3. **licenses/** — 判断该使用场景是否允许；无覆盖则进入告警。
4. **LLM** — 对允许素材生成短摘要，写入告警 JSON。
5. **reports/YYYY-MM-DD/** — 结构化告警；**预警发送**由 webhook/邮件等脚本消费（勿把密钥写入 Git）。

## 本仓库脚本（`scripts/`）

| 脚本 | 作用 |
|------|------|
| `scripts/face_utils.py` | DeepFace 检测/对齐 + Facenet 嵌入 + 余弦相似度（核心 FR 原语）。|
| `scripts/build_known_faces.py` | 由 `known_faces/images/<subject_id>/` 下参考照片生成 `known_faces/index.json`。|
| `scripts/analyze_video.py` | 对单个本地视频做抽帧人脸比对，产出 `scan_*.json` + 命中时的 `alert_*.json`。|
| `scripts/discover_youtube.py` | YouTube 关键词发现（Data API 首选，`yt-dlp ytsearch` 回退）。|
| `scripts/discover_rss.py` | YouTube 频道 RSS 订阅（watchlist）。|
| `scripts/discover_tiktok.py` | TikTok 用户/话题页面发现（yt-dlp；需在 `seeds.yaml` 显式登记）。|
| `scripts/_merge_candidates.py` | 按 `platform:video_id` 去重，合并 `discovery_source`，写 `ingest/<DATE>/sources.json`。|
| `scripts/run-discover.sh` | 发现编排器；也可通过 `run-daily-idvault.sh --discover` 链式调用。|
| `scripts/run-daily-idvault.sh` | **每日编排**：读取 `ingest/`，`yt-dlp` 下载，调用 analyze_video.py，写 `reports/<DATE>/`。支持 `--discover` 与 `--send-warnings`。|
| `scripts/send_warnings.py` / `scripts/send-warnings.sh` | 邮件派发器：把 `reports/<DATE>/alert_*.json` 发给 `ingest/notifications.yaml` 里的收件人；幂等（`.sent/` 标记）。|
| `scripts/requirements.txt` | Python 依赖（DeepFace、OpenCV、TensorFlow、PyYAML 等）。|
| `scripts/README.md` | 详细用法与环境变量说明。|
| `ingest/seeds.yaml` | 发现种子（关键词模板、watchlist 频道、TikTok 账号/话题）。|
| `ingest/notifications.yaml` | 通知收件人与过滤（`min_severity_tier`、`include_reasons`）。|
| `docs/DISCOVERY_POLICY.md` | 发现策略、引擎边界与 ToS/配额说明。|

## Skills

| Skill | 用途 |
|--------|------|
| `skills/idvault-daily-monitor/` | 每日流水线、告警字段、目录约定 |
| `skills/idvault-face-index/` | `known_faces/` 目录与索引约定 |
| `skills/idvault-authorization/` | 授权查询、`Case_Log`、与告警联动 |

## 安全提示

- **不要将** 明文特征、密钥、原始视频缓存提交到 Git；见根目录 `.gitignore` 与 `known_faces/README.md`。
