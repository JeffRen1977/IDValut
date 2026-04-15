---
name: idvault_face_index
description: IDVault workspace layout for known_faces — subject IDs, index files, no raw biometrics in Git. Use when adding or documenting face index data.
---

# IDVault — 人脸特征 / 索引管理

## 何时使用

- 新建或整理 `known_faces/` 目录结构
- 约定 subject_id 命名、索引格式
- 判断哪些文件**绝不能**提交版本库

## 规则

1. **subject_id**：稳定、匿名化优先（如 `TALENT_2026_001`），避免直接用身份证号或手机号。
2. **索引**：优先「subject元数据 + 外部加密存储指针」；仓库内可保留 JSON Schema 与空表示例。
3. **禁止**：向 `main` 工作区或公众号草稿中复制 `known_faces` 下的二进制嵌入文件。
4. 离线 GPU/模型推理应封装为 **idvault 工作区内** 的脚本或工具（由你在本仓库实现），仅 **idvault** 会话默认 cwd 在此工作区。

## 路径

- 索引说明：`known_faces/README.md`
- 案例流水：`Case_Log.md`
