# Park-IO Outbox Platform Auth Runbook

Last checked: 2026-05-22.

This runbook is for finishing the four remaining platform authorization steps
after the local code routes have passed `验收通道路由`.

Current route validation:

```bash
python3 /Users/wendy/work/content-ops/scripts/check_platform_channels.py
```

Expected before login:

```text
code_or_runtime_gap_count = 0
dry_run_ok_count = 7
needs_auth_count = 4
```

The validation output also includes `next auth`, which points to the next
platform to authorize in the safe order. Example:

```text
next auth: 小红书 (bridge_not_ready)
- dashboard: 小红书 -> 准备通道
- command: cd /Users/wendy/.agents/skills/xiaohongshu-skills/scripts && python3 cli.py login
```

## Dashboard Entry

Use the local workbench server, not `file://`:

```bash
python3 /Users/wendy/work/content-ops/scripts/workbench_server.py --port 8788
open http://127.0.0.1:8788/dashboard.html
```

Recommended button order:

1. `验收通道路由`
2. If the platform card shows `导入 Chrome 登录态`, try it once
3. If import fails, use `准备下一个授权`
4. Finish that one login/OAuth prompt
5. `等待授权完成`
6. `检查全部通道`
7. Repeat steps 2-6 until all four auth channels are ready
8. Open a source item, then `预检这条内容`
9. Push/upload from the platform row

Use `检查授权文件` when you only want to verify whether cookie/OAuth files
landed on disk. Use `等待授权完成` while the login/OAuth window is open; it waits
up to two minutes for a new cookie/token file, then refreshes channel status.

`导入 Chrome 登录态` is a shortcut, not the source of truth. It reads existing
Chrome cookies, converts them into a local Playwright `storage_state`, then
immediately runs the normal platform login check. If the check fails, the
temporary account file is removed so the dashboard does not treat a stale cookie
as a working channel.

Use `准备缺失通道` only when you deliberately want to launch every missing
login/OAuth flow at once. The safer default is `准备下一个授权`, which handles one
platform at a time in this order:

```text
小红书 -> 视频号 -> Bilibili -> YouTube
```

If the current first blocker is a manual browser fix, such as
`extension_host_permission_missing`, use `跳过人工卡点继续` to start the next
actionable auth flow while keeping the manual blocker visible in validation.

The dashboard also shows login-session cards. If a QR code is marked
`可能过期` or its session says `未运行`, click `重新生成` before scanning. Do not
scan stale QR images left from a previous login attempt.

## 小红书

Current blocker:

```text
xhs_sau_cookie_missing_bridge_permission_missing
```

Preferred prepare command:

```bash
cd /Users/wendy/content-toolkit/capabilities/publish
/Users/wendy/content-toolkit/capabilities/publish/.venv/bin/python sau_cli.py xiaohongshu login --account creator --headed
```

This creates:

```text
/Users/wendy/content-toolkit/capabilities/publish/cookies/xiaohongshu_creator.json
```

The dashboard uses this cookie with content-toolkit's safe Xiaohongshu draft
mode. That mode fills the note, clicks `暂存离开`, and does not click `发布`.

Fallback prepare command:

```bash
cd /Users/wendy/.agents/skills/xiaohongshu-skills/scripts
python3 cli.py login
```

If `check-login` says Chrome cannot access the page contents, reload the XHS
Bridge extension in Chrome:

```text
chrome://extensions/?id=djmopoijialkhicdddlneckfmfoagcki
```

The extension manifest in both local skill copies includes
`https://*.xiaohongshu.com/*`; Chrome still needs the unpacked extension to be
reloaded before it picks up that permission.

If the dashboard reports:

```text
extension_host_permission_missing
```

the bridge server and extension are connected, but Chrome has not granted the
extension access to the current xiaohongshu.com tab. Reload the extension page
above and set site access to allow xiaohongshu.com.

In this state, `准备下一个授权` opens the Chrome extension detail page instead
of rerunning the login command.

Dashboard button:

```text
小红书 -> 导入 Chrome 登录态
小红书 -> 准备通道
```

The Chrome import has already been tested on this machine: Chrome has
xiaohongshu.com cookies, but they did not pass the creator backend check. The
expected path is still the `准备通道` QR login unless you log into the creator
backend in Chrome again and re-test import.

Ready condition:

```text
小红书 -> 检查登录 -> sau_cookie_valid
```

After ready, the dashboard can fill the creator form and save the note as a
platform draft. It does not publish.

## 视频号

Current blocker:

```text
cookie_missing
```

Expected cookie:

```text
/Users/wendy/content-toolkit/capabilities/publish/cookies/tencent_uploader/account.json
```

Prepare command:

```bash
cd /Users/wendy/work/content-ops/scripts
/Users/wendy/content-toolkit/capabilities/publish/.venv/bin/python \
  /Users/wendy/work/content-ops/scripts/push_wechat_channels_draft.py \
  --title login-only \
  --login-only
```

Dashboard button:

```text
视频号 -> 导入 Chrome 登录态
视频号 -> 准备通道
```

The Chrome import can only work if Chrome has `channels.weixin.qq.com` cookies.
The last local check found zero such cookies, so the expected path is still
`准备通道` QR login.

The dashboard now starts the 视频号 login in a persistent local session instead
of using the upstream `page.pause()` debugger flow. A visible browser page opens
at `channels.weixin.qq.com`; scan/confirm login there. The wrapper polls the page
and saves the cookie only after login appears valid. Failed login attempts remove
the temporary invalid `account.json`.

Ready condition:

```text
视频号 -> 检查登录 -> cookie_valid
```

After ready, the dashboard can upload video and save it as a 视频号 draft via
`TencentVideo(is_draft=True)`. It does not publish.

## Bilibili

Current blocker:

```text
missing_account
```

Expected cookie:

```text
/Users/wendy/content-toolkit/capabilities/publish/cookies/bilibili_creator.json
```

Prepare command:

```bash
cd /Users/wendy/content-toolkit/capabilities/publish
/Users/wendy/content-toolkit/capabilities/publish/.venv/bin/python \
  sau_cli.py bilibili login --account creator
```

Dashboard button:

```text
Bilibili -> 准备通道
```

The dashboard starts the Bilibili login in a persistent tmux session and copies
`qrcode.png` into:

```text
/Users/wendy/park-io/outbox/.system/auth-qrcodes/bilibili.png
```

Open the QR card in the dashboard and scan it with the Bilibili app.

Ready condition:

```text
Bilibili -> 检查登录 -> ready
```

After ready, the dashboard can upload a video with:

```text
biliup upload ... --is-only-self 1
```

This creates a Bilibili upload visible only to Wendy. It does not publicly
publish the video.

## YouTube

Current blocker:

```text
oauth_client_missing
```

OAuth client candidates:

```text
/Users/wendy/.config/park/youtube-oauth.json
/Users/wendy/.credentials/youtube.json
```

Token destination:

```text
/Users/wendy/.config/park/youtube-token.json
```

Step 1: Create or download a Google OAuth Desktop client JSON, then place it at
one of the candidate paths above.

Existing Google Cloud ADC files on this machine were checked. They do not have
the required `https://www.googleapis.com/auth/youtube.upload` grant, so they
cannot be safely reused for YouTube private upload.

`youtube_channel.py` automatically re-runs through the local content-ops venv,
where the Google API packages are installed. Dependency errors should no longer
be the blocker; the expected status is `oauth_client_missing` until a valid
Google OAuth Desktop client JSON exists.

Dashboard shortcut:

```text
YouTube -> 安装 OAuth client
```

This scans:

```text
/Users/wendy/Downloads
/Users/wendy/Desktop
/Users/wendy/Documents
```

for `client_secret*.json`, `*oauth*.json`, or `credentials*.json`, validates the
Google OAuth client shape, and installs the first valid file to:

```text
/Users/wendy/.config/park/youtube-oauth.json
```

Step 2: Run OAuth:

```bash
cd /Users/wendy/work/content-ops
/Users/wendy/work/content-ops/.venv/bin/python \
  /Users/wendy/work/content-ops/scripts/youtube_channel.py auth
```

Dashboard button after the client JSON exists:

```text
YouTube -> 准备 OAuth
```

Ready condition:

```text
YouTube -> 检查 OAuth -> token_valid
```

After ready, the dashboard can upload the selected video as `privacyStatus:
private`. It does not publicly publish the video.

## Final Verification

After finishing all login/OAuth steps:

```bash
python3 /Users/wendy/work/content-ops/scripts/check_platform_channels.py
```

Target final state:

```text
ready_count = 7
needs_auth_count = 0
code_or_runtime_gap_count = 0
dry_run_ok_count = 7
```
