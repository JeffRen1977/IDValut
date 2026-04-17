# IDVault — `scripts/`

Local, Firebase-free face-recognition and daily monitoring pipeline.

The core face-detection / embedding logic is adapted from an earlier
`faceIdentity-main/backend` prototype:

| faceIdentity source | IDVault destination | Notes |
|---|---|---|
| `backend/face_utils_deepface.py` | `scripts/face_utils.py` | Pure CV/DeepFace helpers; no DB. |
| `backend/video_utils.py` → `VideoProcessor` | `scripts/analyze_video.py` | Firebase/SQLAlchemy removed. Reads local index, writes local JSON. |
| *(new)* | `scripts/build_known_faces.py` | Builds `known_faces/index.json` from reference photos. |
| *(new)* | `scripts/run-daily-idvault.sh` | Orchestrator: ingest → yt-dlp → scan → alert. |

## One-time setup

```bash
cd /home/renjeff/Documents/projects/IDValut
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r scripts/requirements.txt
# system deps
sudo apt-get install -y jq ffmpeg
pip install --user yt-dlp      # or: pipx install yt-dlp
```

### Python / TensorFlow compatibility

| Python | TensorFlow | Notes |
|---|---|---|
| 3.10 / 3.11 | `tensorflow==2.15.0`, `tf-keras==2.15.0` | Older, battle-tested combo used by `faceIdentity-main`. |
| **3.12** | `tensorflow>=2.16,<2.20`, `tf-keras>=2.16,<2.20` | **Required** — no TF 2.15 wheels exist for Python 3.12. This is what `requirements.txt` ships. |

TF ≥ 2.16 defaults to Keras 3, but DeepFace still expects Keras 2. Both
`scripts/face_utils.py` and `scripts/run-daily-idvault.sh` set
`TF_USE_LEGACY_KERAS=1` automatically, which routes `tf.keras` through the
`tf-keras` sidecar package. If you import DeepFace from an unrelated script,
export that variable yourself before importing.

#### Troubleshooting pip resolution

- `No matching distribution found for tensorflow==2.15.0`
  → You're on Python 3.12. Pull the latest `requirements.txt` (which uses the
  2.16+ line), or recreate the venv with Python 3.11:
  `python3.11 -m venv .venv && source .venv/bin/activate`.
- `tf-keras` and `tensorflow` minor versions must match. If you pin one, pin
  the other to the same `2.X`.

## Enrolling known faces

Put reference photos under (not committed to Git):

```
known_faces/images/<subject_id>/<any>.jpg
```

Optional metadata file (`known_faces/subjects.json` or `.yaml`):

```json
{
  "TALENT_2026_001": { "label": "Artist A", "notes": "approved likeness, contract 42" }
}
```

Build / rebuild the index:

```bash
python3 scripts/build_known_faces.py
# -> writes known_faces/index.json
```

## Single-video dry run

```bash
python3 scripts/analyze_video.py \
  --video /path/to/clip.mp4 \
  --scan-out reports/2026-04-16/scan_clip.json \
  --alert-out reports/2026-04-16/alert_test.json \
  --alert-id IDV-20260416-001 \
  --case-id CASE-2026-04-16-001 \
  --platform youtube \
  --video-url "https://..." --video-title "..." --video-id "xxx" \
  --frame-interval 30 --threshold 0.6
```

## Daily pipeline

Today’s URLs — either of these is picked up automatically:

```
ingest/2026-04-16/sources.json       # {"urls":[{"url":"...","platform":"youtube"}, ...]}
ingest/daily_urls.txt                # one URL per line
```

Run:

```bash
scripts/run-daily-idvault.sh                  # uses today
scripts/run-daily-idvault.sh 2026-04-16       # backfill a specific date
scripts/run-daily-idvault.sh --discover       # run discovery first, then scan
```

Outputs:

- `reports/<DATE>/scan_<platform>_<vid>.json` — full scan detail
- `reports/<DATE>/alert_<alert_id>.json` — alert per video with ≥ 1 match
- `reports/<DATE>/summary.json` — batch summary index

## Discovery pipeline (auto-populate `sources.json`)

Instead of curating URLs by hand, IDVault can discover candidates from seeded
YouTube / TikTok sources:

| Script | Engine | Trigger |
|---|---|---|
| `scripts/discover_youtube.py` | YouTube Data API v3 (when `$YOUTUBE_API_KEY`) or yt-dlp `ytsearchN:"…"` fallback. | Keyword × subject-label templates from `ingest/seeds.yaml`. |
| `scripts/discover_rss.py` | YouTube channel Atom feeds (no auth). | `youtube.channels[]` in `seeds.yaml`. |
| `scripts/discover_tiktok.py` | `yt-dlp --flat-playlist` on TikTok user / hashtag pages. | `tiktok.users[]` / `tiktok.hashtags[]` in `seeds.yaml`. |
| `scripts/_merge_candidates.py` | Dedup vs `ingest/cache/seen.json`, coalesce `discovery_source`, emit `sources.json`. | Invoked by `run-discover.sh`. |
| `scripts/run-discover.sh` | Orchestrator. | `scripts/run-discover.sh [DATE]` or `run-daily-idvault.sh --discover`. |

Seeds live in `ingest/seeds.yaml` (committed). API keys / cookies live in
`~/.idvault-env`:

```bash
# ~/.idvault-env
export YOUTUBE_API_KEY=...
export YTDLP_COOKIES="$HOME/.config/yt-dlp/cookies.txt"   # optional TikTok cookies
```

Rate-limit / ToS posture is documented in
[`../docs/DISCOVERY_POLICY.md`](../docs/DISCOVERY_POLICY.md).

### Skip an engine

```bash
IDVAULT_SKIP_TIKTOK=1 scripts/run-discover.sh                 # YouTube + RSS only
IDVAULT_SKIP_YT=1 IDVAULT_SKIP_RSS=1 scripts/run-discover.sh  # TikTok only
```

## Tunables (env vars)

| Var | Default | Meaning |
|---|---|---|
| `FRAME_INTERVAL` | `30` | Process every Nth frame. |
| `MATCH_THRESHOLD` | `0.6` | Cosine similarity threshold for a hit. |
| `MAX_FRAMES` | `0` | Cap processed frames per video (0 = no cap). |
| `YTDLP_FORMAT` | `mp4/...` | yt-dlp `-f` selector. |
| `KEEP_MEDIA` | `0` | Keep downloaded media in `ingest/cache/<DATE>/`. |
| `IDVAULT_DISCOVER` | `0` | Run discovery before scan (`1` == `--discover`). |
| `LOG` | `/tmp/idvault-daily.log` | Log file. |

Put secrets in `~/.idvault-env` (auto-sourced by the runner). **Never** commit
credentials or raw media.

## Sending warnings (email)

`scripts/send-warnings.sh` emails each `reports/<DATE>/alert_*.json` to the
recipients listed in [`ingest/notifications.yaml`](../ingest/notifications.yaml)
via SMTP. Under the hood it calls `scripts/send_warnings.py`, which:

- filters alerts by `include_reasons` and `min_severity_tier`;
- renders a plain-text + HTML body with the matched-subject table and the LLM
  summary;
- attaches the raw alert JSON for auditing;
- writes an idempotency marker at `reports/<DATE>/.sent/<alert_id>.json` after
  a successful send (marker dir is git-ignored).

### Configure SMTP

Add to `~/.idvault-env` (the runner auto-sources this):

```bash
export SMTP_HOST=smtp.gmail.com
export SMTP_PORT=587
export SMTP_USER=you@example.com
export SMTP_PASSWORD=xxxxxxxxxxxxxxxx          # Gmail app password
export SMTP_FROM='IDVault <you@example.com>'   # optional
# export SMTP_USE_SSL=1                        # use port 465 + SMTPS instead
# export SMTP_STARTTLS=0                       # disable STARTTLS (default 1)
```

**Gmail**: enable 2-factor auth, then create an *App password* at
<https://myaccount.google.com/apppasswords> — that's what goes into
`SMTP_PASSWORD`. Your daily Gmail password will be rejected.

### Run

```bash
scripts/send-warnings.sh                           # today's alerts
scripts/send-warnings.sh 2026-04-16                # specific date
scripts/send-warnings.sh 2026-04-16 --dry-run      # render, don't send
scripts/send-warnings.sh --to someone@example.com reports/2026-04-16
scripts/send-warnings.sh 2026-04-16 --force        # resend (ignore .sent markers)
```

### Auto-send from the daily pipeline

```bash
scripts/run-daily-idvault.sh --discover --send-warnings
# or: IDVAULT_SEND_WARNINGS=1 scripts/run-daily-idvault.sh --discover
```
