# Park-IO Outbox Workbench User Journey

This document is the regression path for the local outbox workbench. It describes what a user should see and what the system must verify for one source video.

## Current Scope

The current production path is one source video at a time:

1. Video migration to 视频号, Bilibili, YouTube.
2. Content package approval.
3. WeChat MP article preview and push to draft box.
4. Topic split.
5. Xiaohongshu draft generation and review.
6. X draft generation.

The video migration step is the only step that can publicly publish content in v1.

## Journey 1: Open One Source Video

1. Open `http://127.0.0.1:8788/dashboard.html`.
2. Click one source video.
3. The page opens `workbench.html?source=<source_content_id>`.
4. The page must show `本地动作服务已连接`.
5. The workbench should show one source video only, not the full source list.

Acceptance:

- If opened with `file://`, mutating buttons must not pretend to run.
- If opened through `127.0.0.1:8788`, action buttons may call local APIs.

## Journey 2: One-Click Video Migration

User action:

1. In `第一步：视频搬运`, click `一键公开发布到 3 个平台`.
2. Confirm the public publish dialog.

Expected behavior:

1. The button immediately shows activity in the section.
2. The backend returns structured status for exactly three platforms: 视频号, Bilibili, YouTube.
3. If any platform is not logged in, no upload starts for any platform.
4. The section shows the exact platform state:
   - `需要登录`
   - `已连接`
   - `发布中`
   - `已公开发布`
   - `失败`
5. If the request fails, the section must show `请求没有成功返回`, not stay stuck at `发布中`.

Acceptance:

- No silent success.
- No silent failure.
- No partial public publish while another platform still needs login.
- Every run writes to `outbox/.system/actions/action-log.jsonl`.

Current verified state for `7615510060650777892`:

- 视频号: `needs_login`, because `tencent_uploader/account.json` is missing or invalid.
- Bilibili: `connected`.
- YouTube: `connected`.
- Result: no upload starts; page shows the blocker.

## Journey 3: Content Package Approval

User action:

1. Read the content package.
2. Click `✓ 通过`.

Expected behavior:

1. The section changes from yellow/warning to green/done only after user approval.
2. The approval timestamp is written into the content package metadata.
3. The action is written to `action-log.jsonl`.

Acceptance:

- Generated does not mean approved.
- Old placeholder content must not appear as green/done.

## Journey 4: WeChat MP Article

User action:

1. Review the embedded HTML preview inside the dashboard.
2. Click `推送到公众号草稿箱`.

Expected behavior:

1. The article pushed to WeChat draft box should match the dashboard preview structure.
2. Cover and inline visuals should be included when available.
3. The page should show success or the exact API/browser error.

Acceptance:

- No Markdown-only button in the main path.
- No `Error response 404` iframe in the preview.
- The section becomes green only after a valid local article exists or after draft push succeeds, depending on the step status shown.

## Journey 5: Xiaohongshu Drafts

User action:

1. Review the generated note previews.
2. Open image carousel for each note.
3. Check DBS score and first action.
4. Push only after review.

Expected behavior:

1. Topic and Xiaohongshu note mapping must be clear.
2. Structure/debug labels must be hidden by default.
3. Images must use the current dense card style, not the old sparse template.

Acceptance:

- No repeated internal metadata as public-facing copy.
- No placeholder note marked as ready.
- The system can show a generated draft without claiming it has been pushed.

## Debug Checklist

For every regression run:

1. Rebuild the dashboard:
   `python3 /Users/wendy/work/content-ops/scripts/build_dashboard.py`
2. Start local server:
   `python3 /Users/wendy/work/content-ops/scripts/workbench_server.py --port 8788`
3. Verify health:
   `curl http://127.0.0.1:8788/api/health`
4. Test the button path in browser.
5. Check browser console for `ERR_EMPTY_RESPONSE` or JSON parse errors.
6. Check `outbox/.system/actions/action-log.jsonl` for a structured result.

