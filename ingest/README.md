# ingest/

存放**待扫描**视频链接的入口；由定时任务、人工或你自己的采集脚本更新。

## 建议格式

- **简单**：`daily_urls.txt`，每行一个 URL（`#` 开头为注释）。
- **结构化**：`YYYY-MM-DD/sources.json`，例如：

```json
{
  "date": "2026-04-15",
  "urls": [
    { "platform": "youtube", "url": "https://..." },
    { "platform": "tiktok", "url": "https://..." }
  ]
}
```

下载的缓存视频、临时文件应写入被 `.gitignore` 覆盖的目录（如 `ingest/cache/`），**不要**提交到 Git。
