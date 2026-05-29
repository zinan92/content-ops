# Tooling Inventory

This is the current evidence-based map of reusable tools for the Park-IO outbox.
The rule is: use existing starred/local tooling first, then write only the glue
needed for Wendy's dashboard workflow.

## Selected Production Routes

| Channel | Primary tool | Local path | Dashboard behavior |
| --- | --- | --- | --- |
| 小红书 | `social-auto-upload` via `content-toolkit/capabilities/publish` | `/Users/wendy/content-toolkit/capabilities/publish` | Create image-text draft with `--draft`; saves to 小红书草稿/暂存 flow, does not publish. |
| 公众号 | `wechat-workflow` bridge | `/Users/wendy/wechat-workflow` | Create WeChat MP draft; no mass-send. |
| 视频号 | `social-auto-upload` Tencent uploader wrapper | `/Users/wendy/work/content-ops/scripts/push_wechat_channels_draft.py` | Upload as 视频号 draft after cookie login. |
| Bilibili | `social-auto-upload` + `biliup` | `/Users/wendy/content-toolkit/capabilities/publish` | Upload as `--is-only-self 1`; not public. |
| YouTube | Park-IO YouTube Data API wrapper | `/Users/wendy/work/content-ops/scripts/youtube_channel.py` | Upload as `privacyStatus=private`; not public. `social-auto-upload` local/upstream tree has no YouTube uploader directory, so this route currently requires Google OAuth. |
| X | Web Intent | built into dashboard server | Open composer with prefilled text; no API post. |
| 知乎 | Browser handoff | built into dashboard server | Open editor and prepare text; no confirmed official draft API. |

## Starred Repos Checked

- Checked GitHub stars for `zinan92` on 2026-05-22 through `gh api
  users/zinan92/starred`. The relevant current hits confirm the local route
  choices below.
- `dreammis/social-auto-upload`: selected for 小红书, 视频号, Bilibili. It is the
  best available local base for multi-platform upload automation. GitHub
  description mentions YouTube, but the fetched `origin/main` tree currently has
  no YouTube uploader directory or CLI entry, so Park-IO still uses its local
  YouTube Data API wrapper for outbound YouTube.
- `autoclaw-cc/xiaohongshu-skills`: installed locally and kept as a fallback
  Xiaohongshu Bridge, but not the preferred route because extension host
  permissions have been unreliable.
- `white0dew/XiaohongshuSkills`, `lucasygu/redbook`, `zhjiang22/openclaw-xhs`,
  `Jamailar/RedBox`: useful Xiaohongshu fallback/reference tools.
- `geekjourneyx/md2wechat-skill`, `oaker-io/wewrite`,
  `limin112/wechat-publish-template`: useful WeChat writing/publishing
  references; current Park-IO route stays on `wechat-workflow` because it is
  already wired locally.
- `Panniantong/Agent-Reach`, `NanmiCoder/MediaCrawler`,
  `JoeanAmier/XHS-Downloader`, `putyy/res-downloader`: useful for discovery,
  crawling, or acquisition, not primary publish/draft routes.
- `jiji262/douyin-downloader`, `zinan92/douyin-downloader`: useful for Douyin
  acquisition/transcript workflows. Current mature Douyin sources are already
  stored under `/Users/wendy/park-io/outbox/sent/douyin/`.
- `jdepoix/youtube-transcript-api`: useful for YouTube transcript ingestion, not
  needed for outbound private upload.

## YouTube Decision

`/Users/wendy/content-toolkit/capabilities/publish/uploader/` currently contains
Douyin, Kuaishou, Xiaohongshu, Tencent/视频号, Bilibili, and Baijiahao uploaders,
but no YouTube uploader. Therefore the lowest-risk outbound YouTube route is the
local YouTube Data API wrapper, uploading videos as `private`. If OAuth is not
configured, the dashboard can still open YouTube Studio as a manual handoff, but
that is not considered a fully automated channel.

Dashboard fallback: Bilibili and YouTube now also expose a manual handoff action
for video sources. It opens the platform backend and copies title, description,
source URL, and the local video path to the clipboard. This is deliberately not
treated as a completed automated channel, but it prevents OAuth/cookie gaps from
becoming a dead end while Wendy reviews manually.

Runtime note: `youtube_channel.py` now re-execs itself through
`/Users/wendy/work/content-ops/.venv/bin/python`, so both manual `python3
scripts/youtube_channel.py ...` calls and dashboard calls use the environment
where the Google API packages are installed. Current remaining YouTube blocker is
the OAuth desktop client JSON, not Python dependencies.

## Current Authorization Artifacts

These files are intentionally outside `park-io/outbox` because they are
credentials/cookies, not content assets.

```text
/Users/wendy/content-toolkit/capabilities/publish/cookies/xiaohongshu_creator.json
/Users/wendy/content-toolkit/capabilities/publish/cookies/tencent_uploader/account.json
/Users/wendy/content-toolkit/capabilities/publish/cookies/bilibili_creator.json
/Users/wendy/.config/park/youtube-oauth.json
/Users/wendy/.config/park/youtube-token.json
/Users/wendy/.credentials/youtube.json
```

Dashboard completion means each platform can move a prepared local draft into a
platform-side draft/private/self-only state. It does not mean automatic public
posting.
