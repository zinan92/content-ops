# content-ops

Local content distribution layer for Wendy's social media production.

This folder is project-specific. It is not a generic content toolkit and should
stay small: Park-IO state rules, Wendy's outbox dashboard, and scripts that glue
existing tools into this workflow. Reusable or third-party capabilities live
outside this folder, mainly under `/Users/wendy/content-toolkit`,
`/Users/wendy/videocut`, and installed skills.

Operational SOP: [SOP.md](SOP.md)

Reusable tool choices and starred-repo evidence: [TOOLING_INVENTORY.md](TOOLING_INVENTORY.md)

Xiaohongshu production standard: [XIAOHONGSHU_WORKFLOW.md](XIAOHONGSHU_WORKFLOW.md)

This is separate from `input-to-park`:

- `input-to-park` watches outside sources and produces intelligence/newsletter briefs.
- `content-ops` watches Wendy's own content assets and turns them into platform drafts, approvals, and publication state.
- In Park-IO, Wendy's own published/draft content lives under `outbox/`, not `inbox/`.

## Current Data Flow

```text
/Users/wendy/content-toolkit/capabilities/download/output/manifest.jsonl
    -> scripts/build_dashboard.py
    -> /Users/wendy/park-io/outbox/.system/data/assets.json
    -> /Users/wendy/work/content-ops/.runs/reports/platform-progress.md
    -> /Users/wendy/park-io/outbox/dashboard.html
```

Current Douyin text flow:

```text
outbox/sent/douyin/<title-id>/media/video.mp4
    -> scripts/transcribe_douyin_mlx.py
    -> transcript/raw.json + transcript/raw.md
    -> scripts/organize_douyin_transcripts.py
    -> transcript/organized.json + transcript/organized.md
    -> drafts/xiaohongshu, drafts/wechat_mp, drafts/x, ...
```

Current WeChat MP draft flow:

```text
drafts/wechat_mp/<draft-id>.json + <draft-id>.md + image assets
    -> scripts/generate_wechat_mp_article.py
    -> drafts/wechat_mp/<draft-id>.html         # dashboard preview only
    -> drafts/wechat_mp/<draft-id>.wechat.html # WeChat-compatible inline HTML
    -> /api/actions/push-draft
    -> save as draft in the official account draft box
```

Official WeChat MP API publishing is still the preferred long-term path, but it
requires the current outbound IP to be accepted by the公众号 API IP whitelist.
The production artifact is `<draft-id>.wechat.html`, not the dashboard preview
HTML. It must use inline styles and real images so WeChat does not strip the
layout.

When the API path fails with `40164`, DOCX import is only a manual fallback:

```text
drafts/wechat_mp/<draft-id>.json
    -> scripts/build_wechat_mp_docx.py
    -> drafts/wechat_mp/<draft-id>.docx
    -> WeChat MP backend 文档导入
    -> set cover from the first body image
    -> save as draft
```

After any DOCX fallback, verify title, first body image, cover, and draft-list
completeness warning before treating the push as complete.

## Data Model

`ContentAsset`

Original source material. Today this is `Park的AI世界` content that has already been downloaded/indexed locally.

Core fields:

- `asset_id`
- `source_platform`
- `source_content_id`
- `content_dir`
- `content_type`
- `published_at`
- `title`
- `description`
- `tags`
- `media_files`
- `cover_files`
- `transcript_json`
- `transcript_md`
- `organized_transcript_json`
- `organized_transcript_md`

Canonical Douyin item layout:

```text
outbox/sent/douyin/YYYY-MM-DD--<douyin-title>--<aweme-id>/
  media/
    video.mp4
    cover.jpg
  source.json
  transcript/
    raw.json
    raw.md
    organized.json
    organized.md
  _raw/
    ...
```

`source.json`, `media/`, and `transcript/` are the production surface. `_raw/`
is only for traceability and cache material from download, extraction, and
transcription tools; downstream scripts should not depend on `_raw/` unless
they are doing recovery or debugging.

Canonical outbox root layout:

```text
/Users/wendy/park-io/outbox/
  dashboard.html
  README.md
  drafts/
  sent/
  .system/    # hidden machine-readable indexes used by the dashboard
```

Only `dashboard.html`, `drafts/`, and `sent/` are intended as the human-facing
production surface.

Transient reports, debug logs, and temporary downloader cache belong under
`/Users/wendy/work/content-ops/.runs/`, not under Park-IO outbox.

`DerivedPiece`

A reusable content unit generated from an asset. One long source video can create many derived pieces.

Examples:

- Xiaohongshu note 1
- Xiaohongshu note 2
- WeChat article
- X thread
- YouTube Shorts package

`Publication`

Platform-specific state for one derived piece.

Examples:

- `xiaohongshu: draft_ready`
- `wechat: approved`
- `x: published`
- `bilibili: failed`

## MVP Boundary

Phase 1 is visibility:

- show each platform as a progress bar
- show source assets already published on Douyin
- show which platforms have no synced output yet
- produce a backlog of source assets to process into drafts

Phase 2 is draft generation:

- first generate a deterministic topic plan for every Douyin source asset
- generate Xiaohongshu notes through `note_brief -> image_cards`, plus WeChat
  drafts and X posts from selected topics
- store drafts under `/Users/wendy/park-io/outbox/drafts/`
- render Xiaohongshu image-text cards locally from `image_cards`, not from raw
  transcript or long caption body
- require human approval before publish

Phase 3 is publishing:

- use direct publish only where stable
- use assisted publish packages for fragile platforms
- record every result back into publication state

Xiaohongshu image-text cards are rendered locally with
`scripts/render_xiaohongshu_cards.py`. The renderer uses HTML/CSS and Chrome
Headless screenshots, so it does not require a new image-generation API key.

## Daily Local Workflow

At the start of a work session, run the doctor:

```bash
python3 /Users/wendy/work/content-ops/scripts/outbox_doctor.py
```

It does not generate drafts or mutate workflow state. It checks dashboard
availability, workbench server/API, workflow reports, verification status,
action queue counts, and whether any local production job is still running.
Reports are written to:

```text
/Users/wendy/work/content-ops/.runs/reports/outbox-doctor.json
/Users/wendy/work/content-ops/.runs/reports/outbox-doctor.md
```

Before opening the outbox dashboard for production review, run the reusable
local workflow:

```bash
python3 /Users/wendy/work/content-ops/scripts/run_outbox_workflow.py
```

This command does not publish or push drafts to any platform. It only:

1. rebuilds the local dashboard data;
2. audits Xiaohongshu drafts against the search-card workflow;
3. triages blocked Xiaohongshu drafts into source-action buckets;
4. builds an actionable queue for repair / reingest / merge decisions;
5. rebuilds `outbox/dashboard.html` so the workbench shows the latest state.

Reports are written to:

```text
/Users/wendy/work/content-ops/.runs/reports/outbox-workflow-report.json
/Users/wendy/work/content-ops/.runs/reports/outbox-workflow-report.md
/Users/wendy/work/content-ops/.runs/reports/outbox-action-queue.json
/Users/wendy/work/content-ops/.runs/reports/outbox-action-queue.md
```

Use the default non-strict mode for daily production. In this mode,
`blocked_source` is treated as an action queue, not a script failure. Use
`--strict` only when you want CI-style failure if any Xiaohongshu draft is still
blocked.

Action queue lanes:

- `auto_repair_candidate`: source exists and the excerpt is close to the
  threshold; run the generated repair command, then rerun polish, quality, and
  render only for the repaired Xiaohongshu draft.
- `manual_reingest_or_drop`: local source is missing or too thin; re-download /
  transcribe the Douyin source first, or keep the draft blocked.
- `manual_merge_or_drop`: the topic unit is too small; merge it into a stronger
  Xiaohongshu note or drop it from the production queue.

To preview executable repairs without changing files:

```bash
python3 /Users/wendy/work/content-ops/scripts/run_outbox_action_queue.py
```

To apply only the auto-repair lane:

```bash
python3 /Users/wendy/work/content-ops/scripts/run_outbox_action_queue.py --apply
python3 /Users/wendy/work/content-ops/scripts/run_outbox_workflow.py
```

The executor only allows known local scripts and defaults to dry-run. Manual
reingest/drop and merge/drop lanes remain human decisions.

To record a manual decision from CLI:

```bash
python3 /Users/wendy/work/content-ops/scripts/record_outbox_action_decision.py \
  '/absolute/path/to/xiaohongshu-draft.json' \
  --decision merge \
  --reason 'topic unit is too thin; merge into stronger note' \
  --merge-target 'target note title'
python3 /Users/wendy/work/content-ops/scripts/run_outbox_workflow.py
```

Supported decisions are `reingest`, `skip`, `merge`, `drop`, and
`keep_blocked`. They are stored in:

```text
/Users/wendy/park-io/outbox/.system/data/action-decisions.json
```

Automatic repair attempts are stored separately in:

```text
/Users/wendy/park-io/outbox/.system/data/action-attempts.json
```

This keeps failed automatic repairs durable. A later dry-run cannot erase the
fact that a draft already failed automatic repair and should move to manual
merge/drop review.

The dashboard exposes the same manual decisions as buttons on each queue item:
`标记重抓`, `标记跳过`, `标记合并`, and `标记丢弃`. These buttons only record
local workflow state and refresh the queue; they do not delete files and do not
publish anything.

If a decision is wrong, use `撤回决策` in the dashboard's `已决策项目`
section, or run:

```bash
python3 /Users/wendy/work/content-ops/scripts/record_outbox_action_decision.py \
  '/absolute/path/to/xiaohongshu-draft.json' \
  --clear
python3 /Users/wendy/work/content-ops/scripts/run_outbox_workflow.py
```

The dashboard also surfaces the same queue near the top of the workbench:

- use the top stat `修复队列` to see how many blocked-source actions remain;
- use `下一步行动队列` to see the first actions without opening JSON reports;
- use `预演自动修复` before changing anything. This calls the same dry-run
  executor as `run_outbox_action_queue.py` and only checks what would run.
- use `执行自动修复` only after the dry-run looks right. This runs only the
  `auto_repair_candidate` lane at draft scope, then refreshes the outbox
  workflow/dashboard.
- open `outbox-action-queue.md` when you need the exact repair/apply command.

The dashboard buttons do not publish, upload, or push drafts to platform
backends. They only repair local Xiaohongshu draft/source metadata for items
that the workflow already marked as safe automatic candidates.

For deeper template regression checks:

```bash
python3 /Users/wendy/work/content-ops/scripts/run_outbox_workflow.py --verify --render-verify
```

`--verify` now runs two layers:

- `verify_outbox_workflow.py`: checks the production workflow contracts,
  including action queue dry-run, manual decision record/clear roundtrip,
  dashboard action buttons, and report structure.
- `verify_xiaohongshu_workflow.py`: checks representative Xiaohongshu template,
  quality, and optional render behavior.

To run only the production workflow contract verifier:

```bash
python3 /Users/wendy/work/content-ops/scripts/verify_outbox_workflow.py --refresh
```

`verify_outbox_workflow.py --embedded` is reserved for
`run_outbox_workflow.py --verify`; use `--refresh` when running it directly.

## Topic Plan Rules

Every mature Douyin source must have a topic plan before downstream review.
`scripts/build_dashboard.py` writes the current deterministic plan to:

```text
/Users/wendy/park-io/outbox/.system/data/topic-plans.json
```

Do not equate a transcript chapter with a publishable note. A topic is eligible
for Xiaohongshu / WeChat MP / X only when it has:

- an independent claim
- enough substance for 700-1200 Chinese characters or 7-10 image-text cards
- a cognitive contrast, conflict, or curiosity hook
- a concrete scene, example, analogy, or operating rule
- a clear reader payoff

Use `priority=main` for the strongest publishable themes, `priority=secondary`
for optional or tooling/process themes, and `priority=discard` for fragments
that should not become standalone drafts.

The dashboard should make this plan visible before platform drafts. Xiaohongshu,
WeChat MP, and X are preview-first platforms. 视频号, Bilibili, and YouTube are
compact migration-status platforms. Zhihu is intentionally outside the v1 main
dashboard.

## Xiaohongshu Card Rules

Xiaohongshu drafts must follow the reusable search-card workflow documented in
[XIAOHONGSHU_WORKFLOW.md](XIAOHONGSHU_WORKFLOW.md).

Required production structure:

```text
organized transcript -> topic plan -> note_brief -> card_plan -> image_cards -> rendered package
```

`note_brief` defines the search keywords, target reader, core claim, cognitive
conflict, source evidence, and reader payoff. `image_cards` is the card script
used by the renderer. The long `body` is the platform caption, not an image
fallback.

Do not render images by splitting the caption body or organized transcript into
pages. That produces transcript screenshots, not Xiaohongshu notes.

The visual target is not a generic PPT deck. It is a Xiaohongshu-native
knowledge card pack: keyword-bearing cover, one cognitive move per card, clear
reasoning chain, source example, operating rule, boundary, and saveable
conclusion.

The reusable Xiaohongshu standard is now `search-card-v2`:

- keep the organized transcript as the long source layer, not the publish layer.
- split one Douyin source into notes only when each note has an independent
  search intent and enough evidence.
- write `image_cards` as edited card scripts: each card needs a judgment plus
  explanation, not raw oral transcript.
- target roughly 90-220 Chinese characters per image card. Below that the note
  reads like slogans; above that it starts to become transcript screenshots.
- use PPT discipline only for card sequence and hierarchy; do not make generic
  presentation slides.
- use light visual explainers such as small logic strips where useful, but keep
  the card primarily text-led and Xiaohongshu-native.
- ensure title, cover, first body paragraph, tags, and card text all reinforce
  the same keyword cluster.
- fail the quality gate if cards are too thin, too long, or too close to the
  raw source excerpt.

Batch upgrade command:

```bash
python3 /Users/wendy/work/content-ops/scripts/upgrade_xiaohongshu_search_cards.py --apply
python3 /Users/wendy/work/content-ops/scripts/upgrade_xiaohongshu_search_cards.py --apply --render-only
```

Use `--only-non-v2` only when the workflow rules have not changed and you only
want to catch up old drafts. If the v2 rules changed, rerun without
`--only-non-v2` so existing v2 drafts are rewritten with the current rules.

The script skips blocked or under-sourced drafts. If a draft is in the action
queue, fix the source first instead of generating from the title.

Current production invariant:

- choose one `template_kind` per draft and use it through title, brief, body,
  cards, and quality.
- strip platform suffixes such as `--xiaohongshu-<id>-<n>` before deriving a
  human title from a filename.
- align `title`, `note_brief.search_keywords`, cover text, body opening, tags,
  and card claims around the same keyword cluster.
- never promote a title-only or under-sourced draft into a rendered package.
- dashboard previews should show the full rendered package when practical
  (normally 8-10 images), not just the first few thumbnails.

Blocked drafts must be triaged instead of rewritten from titles:

```bash
python3 /Users/wendy/work/content-ops/scripts/audit_xiaohongshu_workflow.py --fail-on-issues
python3 /Users/wendy/work/content-ops/scripts/triage_xiaohongshu_blocked_sources.py --min-chars 400
```

## Two-Layer Quality Gate

Xiaohongshu drafts pass through two gates before render:

**Layer 1 — `quality_xiaohongshu_drafts.py`** (deterministic hard fails)

- instruction / oral / internal-ops marker leaks
- card count, length bounds (70-260 chars), repeated sentences, transcript overlap
- required structure: `note_brief`, `card_plan`, `xhs_format`
- card-plan roles per `template_kind` (see `REQUIRED_CARD_ROLES_BY_TEMPLATE`)

A draft must pass Layer 1 before Layer 2 runs.

**Layer 2 — `dbs_xhs_review.py`** (LLM 9-dim semantic review)

Runs `claude -p` subprocess with dontbesilent `dbs-content` persona and Wendy's
9-dimension rubric:

    real_pain, topic_standalone, credibility_anchor, counterintuitive,
    conflict, core_claim, suspense, tension, cognitive_gap

Each scored 0-10 with one-line reason. `suspense.structural=true` marks scores
that are locked in by template ordering (cannot be fixed by rewording — must
change `template_kind`). Output includes `verdict ∈ {keep, rewrite, kill}` and
one concrete `first_action`. Costs ≈ $0.18/draft on Sonnet, ≈ $0.33 on Opus.

```bash
python3 /Users/wendy/work/content-ops/scripts/dbs_xhs_review.py --source-content-id <aweme-id> --model sonnet
```

Both gates are wired into `run_xiaohongshu_pipeline.py`:
`generate → quality (Layer 1) → dbs_review (Layer 2) → render → dashboard`.
Use `--skip-dbs-review` for fast iteration without LLM cost.

## Card-Plan Templates

`polish_xiaohongshu_drafts.py:CARD_PLAN_TEMPLATES` defines the role sequence
for each kind. Two ship today:

- `conclusion_first` (default): cover → misunderstanding → reframe → reasoning
  → example → method → boundary → saveable_rule → application → close.
  Strong for SEO and saveable knowledge, but always scores low on `suspense`
  because the method appears at position 6.
- `suspense_first`: cover (no spoiler) → conflict → example (first-person,
  credibility anchor) → consequence → reasoning → reframe → method → boundary
  → saveable_rule → close. Method pushed to position 7 to keep readers reading.

To use `suspense_first`, set `template_kind: "suspense_first"` in the draft
JSON before running quality + dbs_review. Layer 1 will validate the matching
required role set automatically.

## Daily Douyin Save

After Wendy publishes a mature Douyin video, save it into Park-IO outbox before
repurposing:

```bash
python3 /Users/wendy/work/content-ops/scripts/save_douyin_sent.py '<douyin-video-url>' --slug short-topic
python3 /Users/wendy/work/content-ops/scripts/build_dashboard.py
```

Repurposing jobs should read mature Douyin sources from
`/Users/wendy/park-io/outbox/sent/douyin/` only.
