# Handoff: Xiaohongshu Two-Layer Quality Gate + YAML-Driven Workflow

> Session handoff for Codex. Everything below was built in one session. Nothing
> is committed to git (no repo). All paths are absolute or relative to
> `/Users/wendy/work/content-ops/`.

## What this session set out to do

Wendy felt the Xiaohongshu (小红书) polishing step was weak. The old quality
gate (`quality_xiaohongshu_drafts.py`) claimed to be "dbskill-inspired" but was
actually keyword-bag matching — it caught literal markers but could not judge
content quality. Goal: integrate the installed **dbskill** (`~/.claude/skills/dbs-content`)
as a real LLM reviewer, scoring drafts against Wendy's 9-dimension checklist.

## Key design decisions (already made — do not relitigate)

1. **Two-layer gate, not replacement.** Layer 1 stays deterministic (cheap,
   no false negatives). Layer 2 adds LLM semantic scoring. A draft must pass
   Layer 1 before Layer 2 runs.
2. **Diagnose, do NOT auto-rewrite.** dbs-content's principle: "你不帮人写内容，
   你帮人诊断内容该怎么做。" Layer 2 outputs a `first_action` string for the
   human; it does not edit copy. **Auto-modification is intentionally NOT built.**
   Wendy edits drafts herself based on the diagnosis.
3. **9 dimensions are the rubric; dbs-content supplies the persona.** The review
   prompt = dbs-content's editorial voice (不讨好 / 给行动不给建议 / 像编辑一样精准)
   + Wendy's 9-dim rubric. We did NOT adopt dbs-content's own 5-dim rubric.
4. **Suspense is a structural problem.** The default card template
   (cover→misunderstanding→reframe→reasoning→method) is conclusion-first, so
   `suspense` always scores low and reword cannot fix it. Layer 2 flags this
   with `structural: true`. A `suspense_first` template variant was added as
   scaffolding (method pushed to card 7).
5. **No n8n / Coze.** For a local-file + local-Python + one-LLM-subprocess
   pipeline, an external orchestration engine is overkill. Instead the workflow
   YAML was made executable (it both renders the diagram AND drives execution).

## The 9-dimension rubric (Wendy's checklist)

`real_pain, topic_standalone, credibility_anchor, counterintuitive, conflict,
core_claim, suspense, tension, cognitive_gap` — each 0-10. Full rubric text and
scoring bands are inlined in `scripts/dbs_xhs_review.py` (`RUBRIC` constant).

## Files created / modified this session

| File | Change |
|---|---|
| `scripts/quality_xiaohongshu_drafts.py` | **Rewritten** 772→310 lines. Now Layer 1 hard-fail only (marker leaks, card length 70-260, repeated sentences, transcript overlap, required structure, template-aware card roles). Removed all topic/keyword inference and title generation. |
| `scripts/dbs_xhs_review.py` | **New.** Layer 2. Calls `claude -p --output-format json` subprocess, dbs persona + 9-dim rubric, feeds organized transcript (4000 chars) for credibility-anchor judgment. Writes `xhs_quality.dbs_review`. Default model `sonnet` (~$0.18/draft, ~60s). Flags: `--source-content-id`, `--model`, `--include-failed`, `--force`, `--limit`. |
| `scripts/polish_xiaohongshu_drafts.py` | Added `CARD_PLAN_TEMPLATES` registry with `conclusion_first` (default) and `suspense_first` variants. `card_plan()` now template-aware. |
| `scripts/run_xiaohongshu_pipeline.py` | Added `dbs_review` step between quality and render. Flags `--skip-dbs-review`, `--dbs-review-model`. **Kept for backward compat** (`run_outbox_action_queue.py` still calls it). |
| `scripts/build_dashboard.py` | Added `_dbs_review_summary()` helper + DBS score chip / structural-lock chip / weakest-dims / first_action line to each Xiaohongshu draft card. |
| `scripts/run_workflow.py` | **New.** YAML-driven executor. Topo-sorts the workflow DAG, runs node `command:` blocks in order. Flags `--source-id --lane --from --only --skip --var k=v --dry-run --timeout`. Writes report to `.runs/workflow/<source_id>/<timestamp>.json`. |
| `content-repurpose-workflow.yaml` | **New.** Single source of truth: renders the diagram AND drives `run_workflow.py`. Has `defaults:` (engine/dbs_model/generate_timeout) and `command:` on 5 Xiaohongshu nodes. |
| `content-repurpose-workflow-v2.html/.png/.json` | **New.** Rendered diagram (3 platforms: WeChat/XHS/X; migration path intentionally excluded). |
| `/Users/wendy/park-io/inbox/render-workflow-diagram.py` | Patched to support `canvas: {w,h}` from YAML and auto-size the Chrome screenshot window. (This is a shared ParkIO tool — edit was additive/backward-compatible.) |
| `README.md` | Added "Two-Layer Quality Gate" + "Card-Plan Templates" sections. |

## Contract preserved for downstream tools

`build_dashboard.py`, `audit_xiaohongshu_workflow.py`, `verify_xiaohongshu_workflow.py`,
`triage_xiaohongshu_blocked_sources.py` all read `xhs_quality.passes_quality_gate`
(bool) and `xhs_quality.quality_warnings` (list[str]). These are preserved.
`recommended_title` kept as nullable (Layer 2 may populate later). Layer 2 data
lives at `xhs_quality.dbs_review`.

## How to run

```bash
# Layer 1 only (deterministic, free)
python3 scripts/quality_xiaohongshu_drafts.py --source-content-id <aweme-id> --force

# Layer 2 only (LLM, ~$0.18/draft on sonnet; Layer 1 must pass, or use --include-failed)
python3 scripts/dbs_xhs_review.py --source-content-id <aweme-id> --model sonnet

# Full pipeline via OLD runner (still works)
python3 scripts/run_xiaohongshu_pipeline.py --source-content-id <aweme-id>

# Full pipeline via NEW YAML-driven runner (preferred)
python3 scripts/run_workflow.py --source-id <aweme-id>
python3 scripts/run_workflow.py --source-id <aweme-id> --dry-run   # preview
python3 scripts/run_workflow.py --source-id <aweme-id> --only xhs_layer2   # single step
python3 scripts/run_workflow.py --source-id <aweme-id> --var dbs_model=opus

# Re-render the diagram after editing the YAML
python3 /Users/wendy/park-io/inbox/render-workflow-diagram.py \
  --input  /Users/wendy/work/content-ops/content-repurpose-workflow.yaml \
  --html   /Users/wendy/work/content-ops/content-repurpose-workflow-v2.html \
  --json   /Users/wendy/work/content-ops/content-repurpose-workflow-v2.json \
  --png    /Users/wendy/work/content-ops/content-repurpose-workflow-v2.png
```

## Verified working

- Spike confirmed `claude -p --output-format json` returns stable parseable JSON.
- Layer 1 tested on `2026-05-20--100件事99件不赚钱--xiaohongshu-414054-01.json`:
  correctly fails (all 10 cards < 70 chars).
- Layer 2 tested on same draft (sonnet, $0.18, 58s): scored 40/90, verdict=kill,
  structural_blockers=[suspense], with a concrete first_action.
- `run_workflow.py` dry-run produces identical command sequence to the old
  pipeline (generate→quality→dbs_review→render→build_dashboard). `--only xhs_layer1`
  real run: rc=0, 0.06s, report persisted.

## Current state / what is NOT done (candidate next steps for Codex)

1. **No auto-modification.** This is by design (decision #2). If Wendy later
   wants it, the safest first step is mechanical-only: `structural_blockers=[suspense]`
   → set `template_kind: suspense_first` and re-run polish+Layer1+Layer2. Do NOT
   wire in `polish_xiaohongshu_drafts.py`'s 1700-line auto-rewriter blindly — it
   rewrites from hardcoded templates, not from Layer 2 diagnosis.
2. **`suspense_first` template is scaffolding only.** The card-role sequence and
   Layer 1 required-roles exist, but there is NO generate-prompt that produces a
   suspense-first draft yet. To use it today you must hand-set
   `template_kind: "suspense_first"` in a draft JSON.
3. **Action queue has no `needs_dbs_polish` lane.** Layer 2 verdict
   (keep/rewrite/kill) shows on the dashboard but does not feed the action queue.
   Decide after observing real data whether to add a lane.
4. **No batch baseline yet.** Recommend running Layer 2 across ~10-20 existing
   drafts (`dbs_xhs_review.py --include-failed --limit 20`) to see the score
   distribution and which dimensions fail most often, BEFORE automating any fix.
5. **Model cost not optimized.** Sonnet $0.18/draft works well. Haiku 4.5 not
   yet compared — worth testing if batching 50+ drafts.
6. **WeChat / X paths have no `command:` fields** in the YAML. Only the 5
   Xiaohongshu nodes are wired for execution. Add `command:` blocks to extend
   `run_workflow.py` coverage to those platforms.

## Important gotchas

- Old quality reports are NOT consumed by anything but their producer — safe to
  change report shape.
- `dbs_xhs_review.py` filters a noisy unrelated `SessionEnd` hook error on stderr
  (missing `clawd-hook.js`) — it does not affect results.
- The diagram intentionally omits 视频号/B站/YouTube (they are "upload-and-archive"
  migration, not repurposing). Mentioned only in YAML `notes`.
- No test suite was added. Verification was manual via real runs.
