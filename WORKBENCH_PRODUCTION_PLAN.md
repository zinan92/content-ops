# Workbench Production Plan (v2)

> Replaces the flat principle-dump. Same diagnosis, sequenced into shippable
> phases. Goal is NOT a multi-user cloud "product" — it is a **single-operator
> console that never lies about what it did**. Scope: local, one user (Wendy).

## North Star (the falsifiable done-metric)

A first-time operator opens `workbench.html?source=<id>` and, **without asking
anyone**, can:

1. See which video this is and what the next action is.
2. Click exactly one obvious main button per step.
3. Within **2 seconds** of any click, see a visible state change. **2s is the
   feedback bar, not the completion bar:** login / video upload / content
   generation legitimately take longer. The rule is — within 2s the card must
   show「已开始 + 正在做什么 + 哪个平台」; the action itself may take minutes;
   long tasks MUST surface progress via polling and survive refresh via the
   state file.
4. Never reach a screen where a button was clicked and nothing visibly changed.

If any click can still produce "nothing happened" (even for a 2-minute upload),
we are not done. Everything below serves this metric.

## Current reality (verified, not assumed)

- `scripts/workbench_server.py` — 3587 lines, **~30 POST endpoints**, many are
  generic plumbing buttons (`prepare-channel`, `check-auth-artifacts`,
  `wait-auth-artifacts`, `import-chrome-auth`, `refresh-auth-prompts`, …).
- `scripts/build_dashboard.py` — 4934 lines, generates dashboard + workbench as
  Python f-string HTML with inline JS.
- **Live contradiction**: the main button reads「一键公开发布到 3 个平台」
  (build_dashboard.py ~L4548) but the platform cards read「目标：上传为仅自己
  可见，不公开发布」(~L3100/3110). The button promises a different action than
  the cards. This is a shipped bug, not a hypothetical.
- A response-state vocabulary already half-exists in the front-end
  (`needs_login / waiting_auth / publishing / blocked / published`). We are
  formalizing and enforcing it, not inventing from zero.

## Architectural decisions (locked)

1. **No front-end framework.** Keep `build_dashboard.py` generating the
   read-only dashboard + workbench shell. Interactive state is driven by the
   workbench polling **one state file** with hand-authored vanilla JS. Adding
   React/SPA to a 4.9k-line generator is the same "cannon for a mosquito"
   mistake we rejected for n8n.
2. **Reuse `run_workflow.py`'s report *structure*, add a workbench adapter.**
   Correction (verified against a real file): the shipped report at
   `.runs/workflow/<source_id>/<ts>.json` is **not** a UI state machine. Its
   top level is `ok / stopped_early / steps / source_id / variables /
   workflow_version / generated_at / selection`; each step is `node / status /
   command / returncode / ok / elapsed_s / output`. The UI fields
   `stage / status / message / next_action` **do not exist there.** So we do NOT
   "directly reuse" it. We reuse the report + `steps[]` *thinking*, and add a
   thin **workbench action-state adapter** that normalizes a workflow/action
   result into the UI contract (`stage / status / message / next_action`). One
   conceptual model, one adapter — not two parallel state machines, and not a
   pretend-existing UI schema.
3. **Additive migration, never big-bang.** New contract is a wrapper layer over
   existing endpoints. Old endpoints keep working until each is migrated. No
   half-migrated cliff.

---

## The unified action-state contract (the spine)

Every action endpoint returns this exact shape. No exceptions. No empty
responses. A failure is a 200 with `ok:false` + reason, never a dropped socket.

```jsonc
{
  "ok": true,                         // false = action failed, see message
  "source_content_id": "7630388755329575656",
  "action": "video-migration/run",   // which action
  "stage": "publishing",             // see state enum below
  "status": "ok",                    // ok | needs_login | blocked | failed | done
  "message": "正在上传到 Bilibili（2/3）…",   // human-readable, shown verbatim
  "next_action": {                    // null only when terminal-success
    "label": "登录视频号",
    "endpoint": "/api/actions/video-migration/prepare-login",
    "payload": {"platform": "wechat_channels"}
  },
  "platforms": [                      // per-platform breakdown for this action
    {"platform": "wechat_channels", "stage": "needs_login", "message": "未登录"},
    {"platform": "bilibili", "stage": "publishing", "message": "上传中"},
    {"platform": "youtube",  "stage": "queued", "message": "等待前序平台"}
  ],
  "evidence": [                       // proof, accumulates across runs
    {"platform": "bilibili", "kind": "url", "value": "https://...", "at": "..."}
  ]
}
```

**State enum (the 7 states + transitions).** A state machine without transitions
is just adjectives — here are the edges:

```
未开始(idle) ──click──▶ 检查中(checking)
检查中 ──所有平台ready──▶ 可执行(ready) ──click──▶ 执行中(running)
检查中 ──有平台未登录──▶ 需要登录(needs_login) ──prepare-login──▶ 检查中
执行中 ──成功──▶ 待审核(review) ──user ✓──▶ 已完成(done)
执行中 ──任一失败──▶ 失败(failed) ──含 next_action──▶ (用户决定重试/跳过)
任意 ──refresh page──▶ 从 state 文件恢复到最后已知 stage（不回到 idle）
```

Persisted at `outbox/.system/actions/state/<source_id>.json` (single file per
source, last-known stage), append-only audit at the existing
`outbox/.system/actions/action-log.jsonl`. Refresh reads the state file — never
resets to idle.

---

## Phase 0 — "Stop lying to me" (≈1 day, do first, ships alone)

Smallest change that would have prevented the triggering bug. **No IA redesign,
no button hiding, no 5-step rework.**

1. **Response wrapper over all ~30 endpoints — anti-empty / anti-no-feedback
   ONLY.** A decorator/middleware in `workbench_server.py`: any handler that
   raises, times out, or returns empty is caught and converted to
   `{ok:false, status:"failed", message:<reason>, next_action:<retry|null>}`.
   **Scope discipline:** P0 only guarantees "never empty, never silent" across
   all endpoints. It does **not** semantically migrate all 30 to rich
   `stage/next_action` business logic — that is per-endpoint work deferred to
   P1/P2. P0 = no socket drops, no failure-shown-as-success. Nothing more.
2. **Absolute paths for local tools.** tmux / ffmpeg / ffprobe / python / node
   resolved by absolute path (the literal root cause of the empty response was a
   background server without `tmux` on PATH). Add a `/api/health` check that
   surfaces any missing tool up-front.
3. **Front-end: every fetch shows a result.** Wrap the existing button handlers
   so every click renders the returned `message` + `next_action` in-card within
   2s, including failures. No silent catch.

**Phase 0 acceptance:** trigger the original failure (video migration with
wechat not logged in) → the card now shows「视频号需要登录」+ a「登录视频号」
button, never a blank/no-op. Done when no click can produce "nothing happened."

---

## Phase 1 — Resolve semantics + one button per step (≈2–4 days)

1. **Kill the button contradiction. Pick ONE end-state and change everything in
   lockstep:**
   - **Decision: default = 保存为草稿/私密/待审核, NOT 公开发布.** Safer blast
     radius; partial-success can't silently half-publish you live.
   - Rename button「一键搬运到 3 个平台（草稿/私密）」. Update the cards, the
     confirm() dialog, and `第一步` copy to all say the same thing. No surface
     may say "公开发布" until a separate explicit publish action exists (P2+).
2. **One main button per step; demote the rest.** The 5 steps stay
   (搬运 → 内容包 → 公众号 → 主题 → 小红书/X). Each shows exactly one primary
   button keyed off `next_action`. Move `prepare-channel`,
   `check-auth-artifacts`, `wait-auth-artifacts`, `import-chrome-auth`,
   `refresh-auth-prompts`, `prepare-next-auth`, `skip-human-gate` into a
   collapsed `高级 / Debug` panel. Not deleted — hidden.
3. **Login is a sub-stage, auto-chained but ALWAYS with a visible manual
   fallback.** This is the exact spot that broke trust last time ("你说会弹，但
   我没看到"). Fixed UX sequence, no exceptions:
   1. Main button clicked → a platform is `needs_login`.
   2. Card immediately shows「<平台>需要登录」(within the 2s feedback bar).
   3. System auto-attempts to open the login flow.
   4. Card **simultaneously** shows「如果没有自动弹出，请点这里登录<平台>」with
      a manual button — shown every time, not only on failure.
   So even if the auto-open silently fails (Terminal didn't surface, popup
   blocked), the user always has a working manual path and never stares at a
   dead screen. Terminal-based login is acceptable as the mechanism but is
   tracked as debt; the copy must warn "会打开一个终端窗口帮你登录" so it isn't
   a surprise.

**Phase 1 acceptance:** the North Star metric passes for the video-migration
step end-to-end on a real source; no surface contradicts another on
publish-vs-draft.

---

## Phase 2 — Trust & recovery (≈3–5 days, after P0+P1 prove out)

1. **Evidence capture.** On any successful platform action, persist returned
   ID / URL / screenshot into the `evidence[]` of the source state file; render
   it on the card. Without this the dashboard is not trustworthy.
2. **Refresh-safe.** Reloading mid-`running` restores from the state file to the
   last known stage, not idle.
3. **Status truth-tiers for drafts.** Distinguish 旧草稿 / 当前SOP草稿 / 已审核 /
   已推送 / 已发布 so stale placeholders can never read as "done" (this bit XHS
   and 公众号 before).
4. **"已连接 ≠ 可发布".** Pre-flight per platform: video file present, title,
   description, cover, platform limits — surfaced before the run button enables.
5. **Health check on load.** Missing tool / unreachable bridge shown at top of
   workbench, not discovered mid-action.

**Phase 2 acceptance:** every completed action has durable evidence; a mid-run
refresh never loses state; no stale draft reads as done.

---

## Explicitly deferred (not now)

- 公开发布 as a distinct action (only after draft/private flow is solid).
- Multi-user / auth / cloud deploy — out of scope, this is a personal tool.
- X auto-publish — P1 stays "generate draft text only" (matches current workflow
  `x_review` node being human).
- Migrating the dashboard generator to a framework — rejected (see decisions).

## What this plan deliberately does NOT do that Codex's did

- Does not treat all 10 principles as co-equal P0 work. P0 is exactly one thing:
  the response contract + the one broken button.
- Does not re-architect the whole action surface at once. Wrapper-then-migrate.
- Does not leave "公开 vs 草稿" as an open principle — it picks 草稿 and commits.
- Does not invent a new state model — reuses `run_workflow.py`'s.

## Sequencing summary

| Phase | Theme | Effort | Gate |
|---|---|---|---|
| P0 | Stop lying (response contract + abs paths) | ~1 day | no click → no-op |
| P1 | Semantics + one button per step | 2–4 days | North Star passes for migration |
| P2 | Evidence + refresh + truth-tiers | 3–5 days | every action leaves proof |

Build P0 first. It alone would have prevented the bug that started this.
