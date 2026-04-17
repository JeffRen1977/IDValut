# ingest/

待扫描视频链接的入口。由**发现脚本**、定时任务或人工更新。

## 入口格式（扫描器按顺序尝试）

1. **结构化（推荐）**：`ingest/<YYYY-MM-DD>/sources.json`

```json
{
  "date": "2026-04-16",
  "generated_at": "2026-04-16T08:30:00Z",
  "urls": [
    {
      "url": "https://www.youtube.com/watch?v=...",
      "platform": "youtube",
      "platform_video_id": "...",
      "title": "Example title",
      "channel": "Some Channel",
      "published_at": "2026-04-16T00:00:00Z",
      "subject_hint": "Angelina Jolie",
      "discovery_source": "youtube_api:keyword:Angelina Jolie"
    }
  ]
}
```

2. **简单**：`ingest/daily_urls.txt`，每行一个 URL（`#` 开头为注释）。

## 发现流水线

`ingest/<DATE>/sources.json` 可以由 `scripts/run-discover.sh` **自动生成**：

```bash
scripts/run-discover.sh 2026-04-16
# 或在日常扫描时一并触发：
scripts/run-daily-idvault.sh --discover
```

行为：

1. 读取 `ingest/seeds.yaml`（关键词模板、watchlist 频道、TikTok 账号/话题）。
2. 分别调用：
   - `scripts/discover_youtube.py` — YouTube Data API（有 `YOUTUBE_API_KEY`）或 yt-dlp `ytsearch` 回退。
   - `scripts/discover_rss.py` — 订阅的 YouTube 频道 RSS。
   - `scripts/discover_tiktok.py` — TikTok 用户 / 话题页面（yt-dlp）。
3. 产物写到 `ingest/<DATE>/_discover_youtube.json` / `_discover_rss.json` / `_discover_tiktok.json`（**中间产物，`.gitignore` 已屏蔽**）。
4. `scripts/_merge_candidates.py` 合并、按 `platform:video_id` 去重，合并每个视频的 `discovery_source`，写入 `sources.json`（**可提交**，作为审计证据）。
5. 去重缓存：`ingest/cache/seen.json`（**不提交**），下次运行时自动跳过已处理视频。

## 种子文件 `seeds.yaml`

示例见仓库内该文件。要点：

- `keyword_modifiers` 中的 `{label}` 会替换为 `known_faces/index.json` 中每个主体的 `celebrity_label`。
- `extra_keywords` 为与具体主体无关的泛化查询。
- YouTube `channels`（ID）走 RSS；TikTok 只扫描**显式登记**的 `users` 和 `hashtags`。
- 凭证（API Key、cookies 路径）放 `~/.idvault-env`，不提交仓库。

详见 `docs/DISCOVERY_POLICY.md`。

## 安全

- 下载的缓存视频、临时文件写入 `ingest/cache/`，**不提交**到 Git。
- 合并后的 `sources.json` 保留审计链路：每条 URL 都带 `discovery_source`，可追溯到发现引擎与种子。
