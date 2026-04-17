# TOOLS.md - Local Notes

Skills define _how_ tools work. This file is for _your_ specifics — the stuff that's unique to your setup.

## What Goes Here

Things like:

- Camera names and locations
- SSH hosts and aliases
- Preferred voices for TTS
- Speaker/room names
- Device nicknames
- Anything environment-specific

## Examples

```markdown
### Cameras

- living-room → Main area, 180° wide angle
- front-door → Entrance, motion-triggered

### SSH

- home-server → 192.168.1.100, user: admin

### TTS

- Preferred voice: "Nova" (warm, slightly British)
- Default speaker: Kitchen HomePod
```

## Why Separate?

Skills are shared. Your setup is yours. Keeping them apart means you can update skills without losing your notes, and share skills without leaking your infrastructure.

---

Add whatever helps you do your job. This is your cheat sheet.

## IDVault-local — Face Recognition & Daily Pipeline

本仓库自带的本地 FR 流水线（详见 `scripts/README.md`）：

- **核心模块**（由 `faceIdentity-main/backend` 提取、去掉 Firebase 依赖后本地化）：
  - `scripts/face_utils.py` — DeepFace 检测 / Facenet 嵌入 / 余弦相似度。
  - `scripts/analyze_video.py` — 单视频抽帧识别；输出 `scan_*.json` + 命中时的 `alert_*.json`。
- **辅助模块**：
  - `scripts/build_known_faces.py` — 由 `known_faces/images/<subject_id>/*` 构建 `known_faces/index.json`。
  - `scripts/run-daily-idvault.sh` — 每日流水线：`ingest/` → `yt-dlp` → 比对 → `reports/<DATE>/`。

### 常用调用

```bash
pip install -r scripts/requirements.txt          # DeepFace + TF
python3 scripts/build_known_faces.py             # 建 / 重建索引
scripts/run-daily-idvault.sh                     # 跑今天
scripts/run-daily-idvault.sh 2026-04-16          # 补跑某天
```

可调环境变量：`FRAME_INTERVAL`、`MATCH_THRESHOLD`、`MAX_FRAMES`、`YTDLP_FORMAT`、`KEEP_MEDIA`、`LOG`。
私密凭证放到 `~/.idvault-env`（会被运行器自动 source），**勿**提交仓库。
