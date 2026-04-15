# known_faces/

存放**库内主体**的人脸相关索引数据（由你的离线/本地识别管线生成）。

## 建议布局

- `index.json` 或 `subjects.yaml`：subject_id → 元数据（显示名、别名、脱敏备注），**不含**原始向量明文（若必须存向量，使用加密容器或专用数据库，勿提交 Git）。
- `embeddings/`（可选）：按 subject 分文件的加密 blob；本目录默认 **.gitignore**。
- `README` 每条 subject 的 **数据来源与保留期限**（合规）。

## Git

- 默认 **不** 提交真实生物特征数据。仅提交 schema 示例或脱敏 fixture。
