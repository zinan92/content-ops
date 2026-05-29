# Platform Channel Audit

Last checked: 2026-05-22.

This note records the current tool choice for Park-IO outbox channels. The goal
is to reuse existing starred/local repos first, then build only the glue needed
for Wendy's workflow.

## Selected Tools

| Platform | Current route | Evidence / source | Current boundary |
| --- | --- | --- | --- |
| 小红书 | `content-toolkit/capabilities/publish` safe draft uploader | starred/local `dreammis/social-auto-upload`; local path `/Users/wendy/content-toolkit/capabilities/publish`; fallback `/Users/wendy/.agents/skills/xiaohongshu-skills` | Primary route logs in with `sau_cli.py xiaohongshu login --account creator --headed`, then uploads image-text notes with `--draft` and clicks `暂存离开`; fallback Bridge remains available but is not the preferred route. |
| 公众号 | `wechat-workflow` bridge | local path `/Users/wendy/wechat-workflow` | Can create WeChat MP draft; no mass-send. |
| 视频号 | `social-auto-upload` Tencent uploader wrapper | starred/local `dreammis/social-auto-upload`; local wrapper `/Users/wendy/work/content-ops/scripts/push_wechat_channels_draft.py` | Can save draft with `TencentVideo(is_draft=True)` after cookie login. |
| Bilibili | `social-auto-upload` / `biliup` | starred/local `dreammis/social-auto-upload`; local path `/Users/wendy/content-toolkit/capabilities/publish` | Runtime exists, account cookie missing. Dashboard can upload as `--is-only-self 1`; no public publish. |
| YouTube | Park-IO `youtube_channel.py` + YouTube Data API | local script `/Users/wendy/work/content-ops/scripts/youtube_channel.py` | Can check OAuth and upload as `private` after Google OAuth client/token are configured; never public-publishes automatically. |
| X | Web Intent handoff | no draft API needed for v1 | Opens composer with text; does not call post API. |
| 知乎 | Web editor handoff | no confirmed public draft API in local tools | Opens editor and copies article body. |

## Starred Repos Considered

- `dreammis/social-auto-upload`: best fit for platform upload automation across
  Douyin, Xiaohongshu, 视频号, Bilibili, YouTube/TikTok-style platforms. Reused
  as the primary local publish capability for 小红书 safe draft login/upload,
  视频号 draft upload, and Bilibili self-only upload.
- `autoclaw-cc/xiaohongshu-skills`: useful Xiaohongshu browser Bridge. It is
  kept as a fallback because Chrome extension host permissions were unstable on
  this machine; the primary route is now the content-toolkit/social-auto-upload
  safe draft path.
- `geekjourneyx/md2wechat-skill` and `oaker-io/wewrite`: useful references for
  WeChat writing/publishing flows, but local `wechat-workflow` is already wired
  into Park-IO and closer to current outbox state.
- `lucasygu/redbook`, `white0dew/XiaohongshuSkills`, `zhjiang22/openclaw-xhs`:
  useful Xiaohongshu alternatives/references. Keep as fallback if the current
  content-toolkit safe draft path becomes unstable.
- `limin112/wechat-publish-template`: WeChat publishing template reference, not
  currently wired because `wechat-workflow` already provides the local bridge.
- `cooderl/wewe-rss`, `rachelos/we-mp-rss`, `wechat-article/wechat-article-exporter`:
  useful for reading/exporting WeChat content, not the primary draft creation
  route.
- `putyy/res-downloader`, `JoeanAmier/XHS-Downloader`: useful acquisition tools
  for platform source material. They are not needed for current outbox publish
  channels.
- `Panniantong/Agent-Reach`, `NanmiCoder/MediaCrawler`: useful for reading or
  crawling platform content, not the primary publish/draft channel.
- `jiji262/douyin-downloader`, `zinan92/douyin-downloader`: useful for Douyin
  source acquisition and transcript workflows. Park-IO already has local Douyin
  ingest/download scripts.

## Current Gaps

- 小红书 needs cookie at
  `/Users/wendy/content-toolkit/capabilities/publish/cookies/xiaohongshu_creator.json`.
  Preferred login command:
  `cd /Users/wendy/content-toolkit/capabilities/publish && /Users/wendy/content-toolkit/capabilities/publish/.venv/bin/python sau_cli.py xiaohongshu login --account creator --headed`.
  XHS Bridge still needs extension host permission if used as fallback, but it
  is no longer the preferred blocker.
- 视频号 needs cookie at
  `/Users/wendy/content-toolkit/capabilities/publish/cookies/tencent_uploader/account.json`.
- Bilibili needs cookie at
  `/Users/wendy/content-toolkit/capabilities/publish/cookies/bilibili_creator.json`.
- 视频号 wrapper must run with
  `/Users/wendy/content-toolkit/capabilities/publish/.venv/bin/python`, not the
  system Python. The publish venv now includes `playwright==1.52.0` because the
  Tencent uploader imports `playwright.async_api`.
- Playwright Chromium and patchright Chromium are installed in
  `/Users/wendy/Library/Caches/ms-playwright/`, so browser runtime is no longer
  the blocking issue for the local publish tooling.
- 视频号 check now supports `--check-only` and returns structured
  `cookie_missing`, `cookie_valid`, or `cookie_invalid`.
- Bilibili check now calls `sau_cli.py bilibili check --account creator` when
  a cookie file exists, so dashboard status reflects validity rather than only
  file presence.
- Bilibili `biliup upload` exposes `--is-only-self`; Park-IO uses this as the
  safe non-public upload state. It still submits an upload, but visibility is
  restricted to Wendy until she manually reviews and publishes in Bilibili.
- Local route validation now passes all 7 platform dry-runs via
  `/Users/wendy/work/content-ops/scripts/check_platform_channels.py`; remaining
  non-ready states are auth/cookie/OAuth only.
- YouTube now has a local private-upload channel. It needs a Google OAuth
  desktop client JSON at `/Users/wendy/.config/park/youtube-oauth.json` or
  `/Users/wendy/.credentials/youtube.json`, then `youtube_channel.py auth` saves
  `/Users/wendy/.config/park/youtube-token.json`.
- YouTube uploads are intentionally `privacyStatus=private`; Wendy must review
  in YouTube Studio before making anything public.
- `youtube_channel.py` auto-runs through
  `/Users/wendy/work/content-ops/.venv/bin/python`, and the required Google API
  packages are installed there. Current YouTube status should therefore be
  `oauth_client_missing` until a valid Google OAuth desktop client JSON is
  provided.
