# IDVault — Discovery Policy

This document records **how** IDVault discovers candidate videos for daily
face-recognition monitoring and **why** each method was chosen. It exists so
audits can answer "where did this URL come from?" without re-reading code.

## Principles

1. **Layered, targeted sampling — not bulk crawl.**
   No blind scraping of entire platforms. Every URL has a recorded
   `discovery_source` tagging the engine + seed that produced it.
2. **Official APIs first.** Scrape-backed tools only as documented fallbacks
   when the official channel does not exist (TikTok) or is rate-limited.
3. **Minimum necessary.** Discovery only stores `(platform, video_id, title,
   channel, published_at, discovery_source)`. No profile scraping, no raw
   biometric metadata collection beyond the target scan.
4. **Respect rate limits and `robots.txt`.** Back off on 429 / quota errors.
5. **No credentials in the repo.** All keys live in `~/.idvault-env`.

## Engines

| Engine | Script | Source of truth | Notes |
|---|---|---|---|
| YouTube Data API v3 (`search.list`) | `discover_youtube.py` | Official Google API, `$YOUTUBE_API_KEY`. | 10,000 quota units/day free. `search.list` = 100 units/call. Budget ~100 calls/day. |
| YouTube RSS (channel feeds) | `discover_rss.py` | `https://www.youtube.com/feeds/videos.xml?channel_id=...` | Unauthenticated, stable, channel-scoped only. Ideal for watchlists. |
| YouTube yt-dlp `ytsearch` (fallback) | `discover_youtube.py --engine ytdlp` | `yt-dlp --flat-playlist ytsearchN:"…"` | Scrape-backed. Only used when no API key is set. |
| TikTok yt-dlp (seeded) | `discover_tiktok.py` | yt-dlp over user/hashtag pages listed in `seeds.yaml`. | No official public search API. **Seeded only**: no random tag crawl. |

Each engine emits candidate records with a `discovery_source` of the form
`<engine>:<kind>:<seed>`, e.g. `youtube_api:keyword:Angelina Jolie`,
`youtube_rss:channel:UCxxxx`, `tiktok_ytdlp:hashtag:aiface`.

## Deduplication & audit trail

- `ingest/cache/seen.json` stores `(platform:video_id)` → first-seen metadata.
  Video IDs are never re-scanned.
- Per-engine intermediate outputs (`ingest/<DATE>/_discover_*.json`) are
  retained for the day for debugging and are **git-ignored**.
- The merged, dedupped `ingest/<DATE>/sources.json` **is** committed to
  preserve the audit trail of what the scanner actually processed.

## Platform-specific notes

### YouTube

- Prefer the Data API. Quota budgeting is enforced by the script
  (`max_results_per_query`, `published_within_days` in `seeds.yaml`).
- Channel RSS gives ~last 15 videos per channel, free, no quota impact — use
  it for every repeat-offender channel.

### TikTok

- TikTok does **not** offer a free public search API. The "Research API" is
  approval-gated and only for academic institutions.
- We therefore limit TikTok discovery to **seeded sources**: specific users
  and hashtags maintained in `ingest/seeds.yaml` by a human operator.
- If TikTok requires login-gated cookies in your region, export them from a
  throwaway browser profile into `~/.config/yt-dlp/cookies.txt` and set
  `YTDLP_COOKIES=~/.config/yt-dlp/cookies.txt` in `~/.idvault-env`; the
  script will forward it via `--cookies`.

## Out of scope (intentionally)

- No direct scraping of user profiles or comment sections.
- No facial-embedding harvesting beyond the declared subjects in
  `known_faces/`.
- No off-platform crawling for personal data about the matched subjects.
