---
name: idvault_authorization
description: Check portrait/license authorization for a subject vs. a use case; append findings to Case_Log. Use when a human or upstream system asks if talent X is cleared for asset Y.
---

# IDVault — 授权校验与案例记录

## 何时使用

- 询问：「明星/主体 A 在视频/封面/文章场景 B 中是否已授权？」
- 收到上游转发的素材线索，需要给出 **authorized / not_found / expired / ambiguous**
- 需要将结论写入 `Case_Log.md` 供后续法务或合规流程引用

## 流程

1. **解析请求**：提取 `subject_id`（或候选别名）、素材类型（短视频/图文/广告等）、时间范围。
2. **查 `licenses/`**：匹配 `subject_id` 与 `scope` /有效期 /地域；无记录则 `not_found`。
3. **可选**：若存在离线比对结果摘要（来自你的人脸管线），仅核对「是否同一 subject」，不在对话中输出原始特征。
4. **写 Case_Log**：新行追加 `Case_Log.md` 表格（或等价结构），`case_id` 唯一，`finding` 使用受控词。
5. **回复请求方**：给出 `case_id`、`finding`、**一条** `license_ref`（若有），并列出缺口（缺哪类授权）。

## 输出模板（供外部引用）

```text
case_id: CASE-YYYYMMDD-xxx
subject_id: ...
finding: authorized | not_found | expired | ambiguous
license_ref: LIC-... | (none)
notes: （简短、无法律结论）
```

## 注意

- 不提供「一定侵权/一定胜诉」等法律结论。
- 敏感证据路径使用内部命名，避免对外泄露。
