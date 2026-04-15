# reports/

每日（或每批次）监测的**结构化输出**目录。按日期分子文件夹，便于审计与自动化消费。

## 布局

```text
reports/
2026-04-15/
    summary.json          # 可选：当日批次元数据 + 告警 id 列表
    alert_IDV-2026-04-15-001.json
    alert_IDV-2026-04-15-002.md   # 若人类更易读，可与 JSON 二选一或并存
```

## 告警 JSON 示例

```json
{
  "alert_id": "IDV-2026-04-15-001",
  "case_id": "CASE-2026-04-15-001",
  "platform": "youtube",
  "video": {
    "title": "Example title from platform",
    "url": "https://www.youtube.com/watch?v=xxxxxxxxxxx"
  },
  "scanned_at": "2026-04-15T08:30:00Z",
  "matched_subjects": [
    {
      "subject_id": "TALENT_2026_001",
      "celebrity_label": "公开称谓（与内部 subject 映射）",
      "license_status": "not_found",
      "similarity_tier": "high"
    }
  ],
  "llm_summary": "基于标题/描述/转写或抽帧的短摘要；不编造画面外情节。",
  "llm_summary_sources": ["title", "description"],
  "alert_reason": "unlicensed_face_match",
  "disclaimer": "事实与授权库状态报告，非法律意见。"
}
```

原始视频、大块中间特征请放在 **Git 忽略路径**（见仓库根 `.gitignore`），只把上述摘要纳入版本控制（若政策允许）。
