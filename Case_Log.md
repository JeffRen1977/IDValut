# Case_Log — 侵权线索与核验记录

仅记录**可审计摘要**。不要在此文件粘贴特征向量、密钥或完整人脸图路径（可用内部 `case_id` + `subject_id` 引用）。

| date (UTC) | case_id | source_hint | subject_id | finding | license_ref | next_step |
|------------|---------|-------------|------------|---------|-------------|-----------|
| _example_ | CASE-YYYYMMDD-001 | e.g. video URL or internal batch id | e.g. ARTIST_ABC | authorized / no_match / ambiguous | e.g. LIC-2026-001 | human review |

---

## 追加规范

1. 一行一案或一案一节；`case_id` 全局唯一。
2. `finding` 使用受控词：`authorized`、`expired`、`not_found`、`ambiguous`、`pending_review`。
3. 若 **main** 撰稿引用本表，只引用 **case_id + finding + date**，细节留在本仓库。
