# Content Ops SOP

This SOP fixes Wendy's social content production workflow around Park-IO.

## Core Rule

Park-IO is organized by information lifecycle:

- `/Users/wendy/park-io/inbox/` is input to Wendy's thinking system.
- `/Users/wendy/park-io/outbox/` is Wendy's own output system.
- Mature published Douyin videos belong under `outbox/sent/douyin/`.
- Repurposed but unsent platform content belongs under `outbox/drafts/<platform>/`.
- Published platform content belongs under `outbox/sent/<platform>/`.

Repurposing reads mature Douyin records from `outbox/sent/douyin/` only.
Do not repurpose unpublished ideas, scratch files, or inbox materials unless
Wendy explicitly turns them into an outbox draft.

## Available Tools

| Layer | Tool | Path | Use |
|---|---|---|---|
| Orchestrator | content-ops | `/Users/wendy/work/content-ops` | Park-IO-specific state, dashboard, SOP, draft queue |
| Toolkit router | content-toolkit | `/Users/wendy/content-toolkit` | Unified content CLI and capability registry |
| Douyin ingest | content-downloader | `/Users/wendy/content-toolkit/capabilities/download` | Resolve Douyin URL/profile and save metadata/media |
| Rewrite | content-rewriter | `/Users/wendy/content-toolkit/capabilities/rewrite` | Convert text/Douyin content to Xiaohongshu and WeChat drafts |
| Video processing | videocut / MLX Whisper | `/Users/wendy/content-toolkit/capabilities/videocut` and `/Users/wendy/videocut` | Transcribe, cut, subtitle, hook, cover, clips |
| Xiaohongshu ops | xiaohongshu-skills | `/Users/wendy/.agents/skills/xiaohongshu-skills` | XHS search, content ops, publish flow; publishing requires confirmation |
| Xiaohongshu title expert | dbs-xhs-title | `/Users/wendy/.agents/skills/dbs-xhs-title` | Title formulas, tension check, XHS title candidates |
| Xiaohongshu hook expert | dbs-hook | `/Users/wendy/.agents/skills/dbs-hook` | First-screen hook and opening diagnosis |
| Content diagnosis | dbs-content | `/Users/wendy/.agents/skills/dbs-content` | Check whether the note is clear, publishable content rather than instructions |
| WeChat workflow | wechat-workflow | `/Users/wendy/wechat-workflow` | WeChat article workflow prototype: writing, formatting, preview, publish adapter |
| Multi-platform publish | social-auto-upload via content-toolkit publish | `/Users/wendy/content-toolkit/capabilities/publish` | Douyin/XHS/Bilibili/Kuaishou/video upload; external/unverified, use carefully |
| Outbox workbench server | workbench_server | `/Users/wendy/work/content-ops/scripts/workbench_server.py` | Local mouse-driven dashboard actions; draft/fill only, no final publish |

## Current Fixed Scripts

Run from anywhere.

```bash
# Refresh mature Douyin profile metadata.
/Users/wendy/content-toolkit/capabilities/download/.venv/bin/python \
  /Users/wendy/work/content-ops/scripts/ingest_douyin_profile.py

# Save one newly published mature Douyin video into outbox.
python3 /Users/wendy/work/content-ops/scripts/save_douyin_sent.py '<douyin-video-url>' --slug short-topic

# Build or refresh clean title-based Douyin sent folders.
python3 /Users/wendy/work/content-ops/scripts/sync_douyin_video_library.py

# Transcribe downloaded Douyin videos with MLX Whisper, without compressing information.
python3 /Users/wendy/work/content-ops/scripts/transcribe_douyin_mlx.py

# Organize raw transcripts into readable long-form source text.
# This preserves source logic and should retain at least 90% of content.
python3 /Users/wendy/work/content-ops/scripts/organize_douyin_transcripts.py

# Generate cross-platform draft queue from mature Douyin assets.
python3 /Users/wendy/work/content-ops/scripts/generate_repurpose_drafts.py

# Upgrade Xiaohongshu direction drafts into reviewable copy.
python3 /Users/wendy/work/content-ops/scripts/upgrade_xiaohongshu_drafts.py

# Run dbskill-inspired Xiaohongshu quality checks before rendering/upload.
python3 /Users/wendy/work/content-ops/scripts/quality_xiaohongshu_drafts.py --source-content-id <douyin-aweme-id>

# Rebuild dashboard and progress files.
python3 /Users/wendy/work/content-ops/scripts/build_dashboard.py

# Start the mouse-driven local workbench with platform draft actions.
python3 /Users/wendy/work/content-ops/scripts/workbench_server.py --port 8788
```

Primary outputs:

```text
/Users/wendy/park-io/outbox/dashboard.html
/Users/wendy/park-io/outbox/.system/data/assets.json
/Users/wendy/park-io/outbox/.system/data/platform-summary.json
/Users/wendy/park-io/outbox/drafts/<platform>/
/Users/wendy/park-io/outbox/sent/<platform>/
```

Transient reports and debug logs go under
`/Users/wendy/work/content-ops/.runs/`, not inside Park-IO outbox.

To use the dashboard as an action surface, open:

```text
http://127.0.0.1:8788/dashboard.html
```

Opening `dashboard.html` through `file://` is view-only. It cannot push content
into platform draft boxes because browsers block local file pages from calling
the action API.

## Daily Workflow

0. Check the current production health:

```bash
python3 /Users/wendy/work/content-ops/scripts/outbox_doctor.py
```

Use the returned `next_action` as the operator priority. The doctor is read-only:
it does not generate drafts, push platform drafts, or change queue decisions.

1. Wendy publishes a mature Douyin video.
2. Save the Douyin URL:

```bash
python3 /Users/wendy/work/content-ops/scripts/save_douyin_sent.py '<douyin-video-url>' --slug short-topic
```

3. Rebuild the draft queue:

```bash
python3 /Users/wendy/work/content-ops/scripts/generate_repurpose_drafts.py
python3 /Users/wendy/work/content-ops/scripts/upgrade_xiaohongshu_drafts.py
python3 /Users/wendy/work/content-ops/scripts/quality_xiaohongshu_drafts.py --source-content-id <douyin-aweme-id>
python3 /Users/wendy/work/content-ops/scripts/build_dashboard.py
```

To audit whether Xiaohongshu drafts really follow the reusable workflow:

```bash
python3 /Users/wendy/work/content-ops/scripts/audit_xiaohongshu_workflow.py --fail-on-issues
```

The audit distinguishes:

- `passed`: ready for review/render/push.
- `blocked_source`: not enough source transcript or excerpt; do not publish until source extraction is fixed.
- `needs_work`: source exists but the template or quality layer still needs repair.

If a draft is `blocked_source`, first try to re-derive the source excerpt from
the current Douyin transcript units:

```bash
python3 /Users/wendy/work/content-ops/scripts/repair_xiaohongshu_source_excerpts.py --min-chars 400
```

Then rerun polish, quality, render, and audit. If the source is still shorter
than 400 Chinese characters, keep it blocked; do not write a publishable note
from title alone.

To decide what to do with the remaining blocked drafts, generate the triage
report:

```bash
python3 /Users/wendy/work/content-ops/scripts/triage_xiaohongshu_blocked_sources.py --min-chars 400
```

The triage buckets are:

- `skip_or_reingest`: no local video/transcript; skip the draft or re-download/transcribe first.
- `near_threshold_review`: source is close to 400 chars; consider merging adjacent transcript units.
- `merge_or_drop_unit`: source video has transcript, but this topic unit is too thin; merge it into a stronger topic or keep it blocked.
- `stale_quality_recheck`: source is long enough, but quality metadata is stale; rerun quality/polish/render.

4. Review drafts in:

```text
/Users/wendy/park-io/outbox/dashboard.html
/Users/wendy/park-io/outbox/drafts/<platform>/
```

For mouse-driven work, use the local server entry instead:

```bash
python3 /Users/wendy/work/content-ops/scripts/workbench_server.py --port 8788
```

Then open `http://127.0.0.1:8788/dashboard.html` and use the platform buttons.
Supported actions must save to draft/fill forms only. Final publish stays manual
inside the platform backend.

5. After a platform draft is sent, record it under:

```text
/Users/wendy/park-io/outbox/sent/<platform>/
```

## Backfill Workflow

Goal: bring all platforms up to date with mature Douyin content.

1. Refresh Douyin profile:

```bash
/Users/wendy/content-toolkit/capabilities/download/.venv/bin/python \
  /Users/wendy/work/content-ops/scripts/ingest_douyin_profile.py
```

2. Rebuild dashboard:

```bash
python3 /Users/wendy/work/content-ops/scripts/sync_douyin_video_library.py
python3 /Users/wendy/work/content-ops/scripts/transcribe_douyin_mlx.py
python3 /Users/wendy/work/content-ops/scripts/organize_douyin_transcripts.py
```

Douyin sent folders must use this human-readable directory pattern:

```text
outbox/sent/douyin/YYYY-MM-DD--<douyin-title>--<aweme-id>/
```

Each downloaded video asset should contain:

```text
media/video.mp4
source.json
transcript/raw.json
transcript/raw.md
transcript/organized.json
transcript/organized.md
_raw/
```

`source.json` is the canonical metadata record. `_raw/` is only for original
tool output, cache files, and recovery/debugging.

`transcript/raw.md` is a direct timestamped transcription. Do not summarize,
compress, or rewrite it at this stage. Gallery/image posts remain sent Douyin
assets but do not need video transcripts.

`transcript/organized.md` is the cleaned source text used for downstream
repurposing. It may remove obvious filler words, repeated fragments, and broken
ASR phrasing, but it must not turn a long video into a short summary. Target
retention is 90%+ of the source content and the original logic order must stay
intact.

3. Run the local outbox workflow:

```bash
python3 /Users/wendy/work/content-ops/scripts/run_outbox_workflow.py
```

This is the daily production entrypoint. It rebuilds the dashboard, audits
Xiaohongshu drafts, triages blocked source gaps, and writes an operator report
without publishing anything.

Reports:

```text
/Users/wendy/work/content-ops/.runs/reports/outbox-workflow-report.json
/Users/wendy/work/content-ops/.runs/reports/outbox-workflow-report.md
/Users/wendy/work/content-ops/.runs/reports/outbox-action-queue.md
```

Interpretation:

- `passed`: ready for Wendy's manual review.
- `blocked_source`: do not publish; return to source transcript/topic plan.
- `needs_work`: workflow bug or draft-quality bug; fix script/template before review.
- `auto_repair_candidate`: run the generated repair command in the action queue,
  then rerun polish, quality, and render only for the repaired draft.
- `manual_reingest_or_drop`: source material is missing; re-download/transcribe
  or keep blocked.
- `manual_merge_or_drop`: topic unit is too thin; merge into a stronger note or
  drop it.

To preview safe automatic repairs:

```bash
python3 /Users/wendy/work/content-ops/scripts/run_outbox_action_queue.py
```

To execute only the `auto_repair_candidate` lane:

```bash
python3 /Users/wendy/work/content-ops/scripts/run_outbox_action_queue.py --apply
python3 /Users/wendy/work/content-ops/scripts/run_outbox_workflow.py
```

Do not use the executor for `manual_reingest_or_drop` or
`manual_merge_or_drop`; those require a human decision about whether the source
should be re-downloaded, merged, or removed from the production queue.

Record those human decisions with the dashboard queue buttons or with:

```bash
python3 /Users/wendy/work/content-ops/scripts/record_outbox_action_decision.py \
  '/absolute/path/to/xiaohongshu-draft.json' \
  --decision reingest \
  --reason 'local source is title-only; needs fresh download/transcript'
python3 /Users/wendy/work/content-ops/scripts/run_outbox_workflow.py
```

Allowed decisions:

- `reingest`: keep the draft blocked and return to source download/transcript.
- `skip`: this draft should not be produced now.
- `merge`: merge this thin unit into another stronger note.
- `drop`: remove this draft from the production queue without deleting files.
- `keep_blocked`: leave the item visible as blocked.

Decisions are stored in
`/Users/wendy/park-io/outbox/.system/data/action-decisions.json` and mirrored
into the draft JSON as `manual_decision`.

Automatic repair attempts are stored in
`/Users/wendy/park-io/outbox/.system/data/action-attempts.json`. If an automatic
repair runs but still leaves the source excerpt below threshold, that failed
attempt remains durable and the item moves to manual merge/drop review. Dry-run
executions must not erase this state.

To undo a mistaken decision:

```bash
python3 /Users/wendy/work/content-ops/scripts/record_outbox_action_decision.py \
  '/absolute/path/to/xiaohongshu-draft.json' \
  --clear
python3 /Users/wendy/work/content-ops/scripts/run_outbox_workflow.py
```

Dashboard reading rule:

- `修复队列` is the count of blocked-source actions.
- `下一步行动队列` shows the first repair / reingest / merge items directly in
  the workbench.
- `预演自动修复` runs the safe executor in dry-run mode. Use it first whenever
  the queue changes.
- `执行自动修复` applies only the `auto_repair_candidate` lane, then refreshes
  the workflow/dashboard. Follow-up work is scoped to the repaired draft, not
  every note under the same Douyin source. It does not touch manual
  reingest/drop or merge/drop items.
- `标记重抓` / `标记跳过` / `标记合并` / `标记丢弃` are manual decision buttons.
  They update local workflow state and remove decided items from the pending
  action queue after refresh.
- `撤回决策` removes a recorded decision and lets the item return to the queue
  on the next workflow refresh.
- Use the linked `outbox-action-queue.md` for exact commands and full context.

These dashboard queue buttons only change local outbox draft/source metadata.
They do not upload to Xiaohongshu, do not save platform drafts, and do not
publish anything.

4. Generate missing drafts for one source when needed:

```bash
python3 /Users/wendy/work/content-ops/scripts/run_xiaohongshu_pipeline.py \
  --source-content-id <douyin-aweme-id> \
  --engine auto
```

For Xiaohongshu, the fixed production shape is:

```text
organized transcript -> topic plan -> note_brief -> card_plan -> image_cards -> rendered package
```

`note_brief` is the planning object. `image_cards` is the rendered card script.
`body` is the platform caption. Do not treat a long transcript or caption body
as the image source. If `image_cards` is missing or too thin, stop at quality
repair; do not render caption/transcript paragraphs as images.

Default Xiaohongshu format:

```text
search_knowledge_cards / light_ppt_text_cards
```

This means: use PPT-like structure, but keep native Xiaohongshu search logic.
The card pack should have a keyword-driven cover, a clear misunderstanding, a
reframe, reasoning, source example, operating rule, boundary, and saveable
conclusion. Do not render raw transcript paragraphs as images.

Operational rule for `search-card-v2`:

```text
organized transcript preserves the long thinking.
Xiaohongshu body explains the selected claim.
image_cards are edited knowledge cards.
```

Never use the 90% preservation rule at the image-card layer. That rule belongs
to organized transcripts. Xiaohongshu cards should compress and reorganize the
source into a search-driven note: one keyword cluster, one claim, one conflict,
one reasoning chain, one example, one operating rule, and one saveable close.

Card density standard:

- target 8-10 images for a full note; 7 is the minimum for a complete package.
- target roughly 90-220 Chinese characters per image card.
- average card length below 90 Chinese characters should fail quality, because
  it usually means the package is too sparse.
- cards may include light visual explainers, such as a three-part logic strip,
  but the note remains text-led rather than a generic PPT deck.
- dashboard previews should show the full rendered package when practical, so
  Wendy can review the actual sequence without opening a separate folder.

When reviewing cards, reject these patterns:

- card text is mostly copied from `source_excerpt`.
- cards contain oral fillers such as `然后呢`, `就是说`, `对吧`, `嗯`.
- cards are only slogans with no explanation.
- one card is longer than a readable Xiaohongshu page.
- title, cover, body, and tags point to different topics.

Batch upgrade current Xiaohongshu drafts to the reusable v2 standard:

```bash
python3 /Users/wendy/work/content-ops/scripts/upgrade_xiaohongshu_search_cards.py
python3 /Users/wendy/work/content-ops/scripts/upgrade_xiaohongshu_search_cards.py --apply
python3 /Users/wendy/work/content-ops/scripts/upgrade_xiaohongshu_search_cards.py --apply --render-only
```

This script only touches eligible drafts with enough source material. It skips
blocked action-queue items and short source excerpts, because those need
reingest, merge, or drop decisions.

Use `--only-non-v2` only for a catch-up run when the current v2 rules are
unchanged. When title parsing, topic classification, quality gates, or card
logic changes, rerun without `--only-non-v2` so existing v2 drafts are rewritten
under the current standard.

The full workflow entrypoint can also run the upgrade:

```bash
python3 /Users/wendy/work/content-ops/scripts/run_outbox_workflow.py --upgrade-xhs-v2 --render-upgraded-xhs --verify
```

Each Xiaohongshu JSON draft should include:

```text
note_brief.search_keywords
note_brief.format_rationale
note_brief.card_chain
xhs_format.format = search_knowledge_cards
xhs_format.visual_mode = light_ppt_text_cards
card_plan[]
image_cards[]
```

Production Xiaohongshu copy must be AI-authored:

- `--engine auto`: try Claude Sonnet through the CLI proxy first, then fall back
  to Codex CLI if Claude fails.
- `--engine claude`: require Claude Sonnet structured output; fail if Claude
  does not return a valid JSON note.
- `--engine codex`: use Codex CLI directly.

Do not use a deterministic local rules engine for publishable Xiaohongshu copy.
Local code may run structural checks, quality gates, and image rendering, but
the title, body, argument pack, and image card copy must come from an AI model.

The AI output must keep these fields aligned:

```text
template_kind -> title -> note_brief.search_keywords -> body opening -> tags -> image_cards
```

Do not preserve a filename-derived topic unless it matches the selected keyword
family. For example, a filename containing `99` is not enough to classify a
draft as a trading note; it must also contain a trading signal such as `明牌`,
`交易`, `石油`, or `预期差`. Platform suffixes such as
`--xiaohongshu-596096-02` must never leak into titles, card text, or captions.

Current local Xiaohongshu template families:

| Template | Use case |
|---|---|
| `trading_expectation` | trading, oil, war, risk assets, expectation gap |
| `decision_framework` | first principles, samples, causality, result vs decision quality |
| `focus_ant_theory` | ant theory, scattered smart people, focus and compounding |
| `ai_visual_workflow` | Remotion, AI video, visualizing abstract concepts |
| `ai_adoption_mindset` | AI capability boundaries, blind-men-and-elephant thinking, passive vs active exploration |
| `agent_architecture` | multi-agent architecture, single capability reuse, context cost, workflow design |
| `agent_cost_analysis` | AI agent comparison, token cost, rework rate, stability |
| `ai_workflow` | AI tools, agents, automation, workflow/SOP leverage |
| `life_choice` | focus, compounding, career choice, effort vs direction |
| `content_business` | Xiaohongshu, self-media, one-person company, content repurposing |
| `general_framework` | fallback for topics without a specific family |

After editing templates, verify the reusable workflow:

```bash
python3 /Users/wendy/work/content-ops/scripts/verify_xiaohongshu_workflow.py --render
```

This runs representative drafts through local polish, quality gate, and image
rendering on copied draft files under `.runs/tmp/`, so verification does not
mutate production drafts in `outbox/drafts`. It also checks that dense rendering
does not use `body` as an image fallback. The report is:

```text
/Users/wendy/work/content-ops/.runs/reports/xiaohongshu-workflow-verification.json
```

After editing dashboard, action queue, manual decision, or workflow orchestration
scripts, run the broader outbox verifier:

```bash
python3 /Users/wendy/work/content-ops/scripts/verify_outbox_workflow.py --refresh
```

This verifies core script compilation, action queue dry-run, manual decision
record/clear roundtrip on copied drafts, dashboard controls, and workflow report
contracts. It does not publish or push drafts. Report:

```text
/Users/wendy/work/content-ops/.runs/reports/outbox-workflow-verification.json
```

The `--embedded` verifier mode is only for `run_outbox_workflow.py --verify`;
operators should use `--refresh` when running the verifier directly.

For one source video, use the single pipeline entrypoint:

```bash
python3 /Users/wendy/work/content-ops/scripts/run_xiaohongshu_pipeline.py \
  --source-content-id <douyin-aweme-id> \
  --engine auto
```

This runs:

```text
generate AI-authored drafts -> quality -> render -> rebuild dashboard
```

It writes a machine-readable run report to:

```text
/Users/wendy/work/content-ops/.runs/reports/xiaohongshu-pipeline-report.json
```

The dashboard rebuild writes the current topic decision layer to:

```text
/Users/wendy/park-io/outbox/.system/data/topic-plans.json
```

Treat this as the fixed planning layer between transcript and drafts. It decides
how many themes a Douyin video can become. A theme should become a draft only if
it has an independent claim, enough support, a reader payoff, a cognitive hook,
and at least one concrete scene/example/operating rule. Do not mechanically turn
every transcript chapter into a Xiaohongshu note.

5. Run the Xiaohongshu quality layer before rendering:

```bash
python3 /Users/wendy/work/content-ops/scripts/quality_xiaohongshu_drafts.py \
  --source-content-id <douyin-aweme-id> \
  --force
```

This writes `xhs_quality` into each draft JSON and a `## 小红书质量层` section
into the Markdown. It is based on the local `dbs-xhs-title`, `dbs-hook`, and
`dbs-content` skills. It should catch drafts that still look like instruction
sets, titles that are too weak, missing source excerpts, missing `note_brief`,
card scripts that still look like transcript chunks, and card packages that are
too thin.

6. Render Xiaohongshu image-text packages after a draft is `draft_ready` and has
passed or been manually accepted through the quality layer:

```bash
python3 /Users/wendy/work/content-ops/scripts/render_xiaohongshu_cards.py \
  --source-content-id <douyin-aweme-id> \
  --overwrite
```

This creates one package per Xiaohongshu note:

```text
outbox/drafts/xiaohongshu/<draft-id>/
  title.txt
  content.txt
  manifest.json
  images/
    01.png
    02.png
    ...
```

The renderer is local: HTML/CSS + Chrome Headless screenshots. It does not need
an image-generation API key. Dense rendering reads `image_cards` first; `body`
is only the caption source, not an image fallback.

7. Push a Xiaohongshu package only after Wendy chooses it:

Recommended mouse path:

```text
dashboard -> choose source video -> 小红书 -> 推送草稿箱
```

This calls `xiaohongshu-skills` to fill the creator form and save the note as a
platform draft.

Manual fallback:

```bash
cd /Users/wendy/.agents/skills/xiaohongshu-skills/scripts
python3 cli.py fill-publish \
  --title-file /Users/wendy/park-io/outbox/drafts/xiaohongshu/<draft-id>/title.txt \
  --content-file /Users/wendy/park-io/outbox/drafts/xiaohongshu/<draft-id>/content.txt \
  --images /Users/wendy/park-io/outbox/drafts/xiaohongshu/<draft-id>/images/*.png
```

This only fills the form. Publishing still requires Wendy's browser confirmation
followed by `python3 cli.py click-publish`, or `python3 cli.py save-draft` if
Wendy decides not to publish immediately.

8. Push a WeChat MP draft only after Wendy chooses it:

Recommended mouse path:

```text
dashboard -> choose source video -> 公众号 -> 推送草稿箱
```

This calls the local `wechat-workflow` bridge and creates a draft in the WeChat
MP draft box. It does not publish or mass-send.

The production path is:

```text
content-package.json
  -> scripts/generate_wechat_mp_article.py
  -> drafts/wechat_mp/<draft-id>.md
  -> drafts/wechat_mp/<draft-id>.html          # dashboard preview only
  -> drafts/wechat_mp/<draft-id>.wechat.html  # WeChat-compatible inline HTML
  -> rendered images: cover.png, article-spine.png, decision-checklist.png, framework-layers.png
  -> /api/actions/push-draft
  -> wechat-workflow bridge / md2wechat-compatible draft payload
```

### Topic Framework

第四步的主题不是摘要，也不是小红书文案。主题必须先被整理成一个
`可被卖出去的观点`，然后第五步才做小红书、X、clips 的平台化改写。

每条抖音视频可以进入 1-N 个原子选题，不强制最多 5 个。短视频如果只有
一个完整观点，就只保留 1 个主题；长视频如果确实有 14 个互相独立、证据
充足、可以单独成篇的观点，就保留 14 个原子选题。

重要边界：

- `topics` / `fine_topics` 是原子选题，是第四步和第五步的默认输入。
- `topic_groups` 只是可选的生产批次或聚类建议，不能替代原子选题。
- 合并只能发生在“同一个观点的上下游论据”之间；不能把 workflow 的不同
  阶段、不同层级、不同结论揉成一个主题。
- 如果要控制生产量，在 dashboard 里选择本批发布 3-5 篇；不要在主题层硬
  合并。

每个生产主题必须包含以下结构：

```text
主题 = 一个可被卖出去的观点

1. 用户视角
   先说大众常见误区或读者真实困惑，让读者有“这说的是我”的体感。

2. 反对结论
   直接告诉读者：你们错在哪里，正确结论是什么。

3. 论证与支持
   用一两句话解释为什么大众误区是错的、为什么你的结论成立。

4. 3-5 个 supporting evidence
   可以是递进，也可以是并列，但必须清楚。
   每一点都要有：读者体感 + 判断 + 解释 + 例子/场景。

5. Boundary / 边界
   这个观点不适用于什么情况？容易被怎么误用？

6. Takeaway / 总结
   读者看完之后，下一次应该怎么判断或行动？
```

Structured form:

```json
{
  "title": "生产主题标题",
  "reader_mirror": "用户视角：如果你也……，这个观点就在说你",
  "claim": "反对结论：大众错在哪里，正确结论是什么",
  "cognitive_contrast": "大众误区，不要写成外露的元数据",
  "why_it_matters": "论证与支持：为什么这个观点成立",
  "points": [
    {
      "title": "要点 1",
      "reader_mirror": "如果你在这个点上有什么具体感受或行为",
      "judgment": "判断",
      "explanation": "解释",
      "evidence": "例子或场景"
    }
  ],
  "boundary": "边界",
  "takeaway": "总结和下一步判断动作"
}
```

Do not let Xiaohongshu-specific concerns decide the topic split. Xiaohongshu
customization begins after fourth-step topics are approved. The topic count is
decided by content density and evidence, not by platform quota.

### Xiaohongshu Natural Draft Prompt

第五步的小红书图文不是第四步字段的可视化。第四步字段是内部编辑脚手架，
第五步必须把它改写成像人在和读者说话的自然图文。

默认生成引擎：`--engine auto`。它先调用 Claude CLI proxy
(`claude -p --model sonnet`)，Claude 不可用时才调用 Codex CLI。不得使用
本地规则引擎兜底生成小红书文案。Python 脚本只负责落盘、渲染、质检和
dashboard 展示；小红书正文、图文卡片和立论包必须由 AI 模型生成。

System prompt:

```text
你是 Park 的小红书图文编辑。

输入是一条已经 approved 的生产主题，包含：
claim / cognitive_contrast / reader_mirror / why_it_matters / points /
boundary / takeaway。

你的任务不是展示这些字段，而是先生成一份小红书立论包，再把立论包改写成
一篇自然、连贯、有体感的图文笔记。立论包是内部中间产物，不得出现在最终
图文里。

内部立论包必须回答：
- 这篇真正要卖出去的一个观点是什么？
- 读者原本怎么想，为什么这个想法会误导他？
- 读者在哪个具体场景里会有体感？
- 用哪个类比把抽象判断讲得可感？
- 哪些原视频例子能支撑这篇，而不是空讲道理？
- 最后读者下次应该用什么问题检查自己？

硬性要求：
1. 不得出现内部字段名：
   主张、认知反差、Reader Mirror、为什么成立、判断、解释、例子、
   Boundary、Takeaway、要点、point。
2. 每一页都像自然段，不像表格或 QA。
3. 必须让读者有“这说的是我”的体感。优先使用第二人称：你、你是不是、
   如果你也、你有没有发现。
4. 必须至少使用一个贯穿类比或局部类比。类比要服务理解，不要装饰。
   好的类比像：在海上划船、水流和风力、地图和路标、仓位像会改写视野的眼镜。
5. 结构不能机械写死，但整篇必须连贯递进：
   先让读者进入问题，再给核心判断，再解释为什么，再展开 2-3 层，
   最后收束到一个可执行判断。
6. 每张图只推进一个小判断。不要把多个字段堆在同一页。
7. 语言要像跟读者直接说话，不要像报告、摘要、框架说明。
8. 可以使用排比增强体感，但不能空泛。排比必须围绕具体行为、具体困惑、
   具体场景。
9. 保留原视频的观点和边界，不要为了小红书效果改写成鸡汤。
10. 结尾必须给读者一个下一次可以使用的判断动作。

输出应是 6-10 张图文卡片：
- 第一张可以是问题钩子或大判断，不固定。
- 中间页自然推进，不显示内部标签。
- 最后一张收束到边界或行动。
```

Bad output:

```text
判断：先定义赌注。
解释：如果变量说不清，后面看到的机会、风险和解释都会漂移。
例子：市场因为战争不确定性突然下跌。
```

Good output:

```text
很多人一下场，就开始问自己会不会赢。

但更重要的问题其实是：
我到底把什么东西押出去了？

如果这个变量说不清，后面看到的机会、风险和解释，都会跟着漂。
```

Analogy guidance:

```text
不要为了类比而类比。
类比必须让抽象判断变得可感。

例如：
只看方向就下场，就像在海上看到风往东吹，就立刻开始划船。
但你还没看水流，也没看自己船上有多少粮。
风变了，你会以为是自己不够努力。
其实是你从一开始就没定义航线和返航条件。
```

Important rule: do not treat the dashboard preview HTML as the source of truth for
WeChat. The dashboard preview may use `<style>` blocks, CSS variables, and local
layout wrappers. The WeChat production artifact must be `.wechat.html`: inline
styles only, real images only, no CSS-only diagrams, no external stylesheet, and
no metadata visible to readers.

The current local `md2wechat` binary is allowed as a future renderer/publisher
when a valid `md2wechat` API key is configured. Without a valid key, its API mode
fails before conversion. Do not silently substitute DOCX as the primary path just
because `md2wechat` is unavailable.

If the bridge returns WeChat `40164 invalid ip`, do not keep retrying the same
API route. DOCX import is only a fallback for manual rescue, not the normal
production route. Build an importable DOCX and use the authenticated MP backend:

```bash
/Users/wendy/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 \
  /Users/wendy/work/content-ops/scripts/build_wechat_mp_docx.py \
  /Users/wendy/park-io/outbox/drafts/wechat_mp/<draft-id>.json
```

Then in `mp.weixin.qq.com`: `新的创作 -> 文章 -> 文档导入`, upload the generated
DOCX, set the cover from the first body image, fill the摘要 if needed, and save as
draft. After any DOCX fallback, QA must confirm:

- the title is the production title, not the DOCX filename;
- the first body image is the article-spine image, not a CSS diagram degraded to text;
- the cover is not the Douyin video screenshot unless explicitly chosen;
- the draft list shows no incomplete-content warning.

9. Push a WeChat Channels draft only after Wendy chooses it:

Recommended mouse path:

```text
dashboard -> choose source video -> 视频号 -> 推送草稿箱
```

This calls the local `push_wechat_channels_draft.py` wrapper, which reuses
social-auto-upload but forces `is_draft=True`. It needs a valid 视频号 cookie at:

```text
/Users/wendy/content-toolkit/capabilities/publish/cookies/tencent_uploader/account.json
```

10. Upgrade drafts platform by platform. Recommended order:

```text
xiaohongshu -> wechat_mp -> wechat_channels -> bilibili -> youtube -> x -> zhihu
```

11. For video migration platforms, use the safest non-public platform state:

```text
dashboard -> choose source video -> 视频号 -> 推送草稿箱
dashboard -> choose source video -> Bilibili -> 上传仅自己可见
dashboard -> choose source video -> YouTube -> 上传 private 视频
```

视频号保存平台草稿；Bilibili 通过 `biliup --is-only-self 1` 上传为仅自己可见；
YouTube 通过 OAuth API 上传为 private。None of these actions publicly publish
content. Wendy still does final review and public release inside the platform.

12. For platforms without confirmed draft/upload APIs, use handoff actions:

```text
dashboard -> choose source video -> X / 知乎 -> 打开后台填稿
```

This opens the platform backend or composer and writes the prepared title/body
into the system clipboard. It does not call final publish commands.

13. Use `检查登录` in the dashboard before real platform actions. It checks the
current local readiness state:

```text
小红书: xiaohongshu-skills login state
公众号: wechat-workflow bridge + WECHAT_APPID / WECHAT_SECRET
视频号: tencent_uploader cookie file
Bilibili: bilibili cookie + biliup runtime
YouTube: local OAuth credential candidate
X: web intent availability
知乎: web-editor handoff availability
```

14. Use `准备通道` when readiness is missing. The current supported preparation
actions are:

```text
Bilibili: install or refresh the local biliup runtime, then prompt for terminal login.
公众号: start the local wechat-workflow bridge.
小红书: start the xiaohongshu-skills login flow.
YouTube / X / 知乎: open the platform backend/editor.
视频号: reports the cookie-login command; cookie still needs an interactive login.
```

For a one-shot setup pass, use `准备缺失通道` in the dashboard. It first checks
all channels, then starts only missing preparable channels:

```text
小红书: open xiaohongshu-skills login flow
公众号: start wechat-workflow bridge
视频号: open Tencent uploader login-only flow
Bilibili: prepare biliup runtime and open Bilibili terminal login
YouTube: open Studio; OAuth still requires explicit credential setup
```

This action can open multiple Terminal windows or platform pages. It never
publishes content and does not bypass platform login, QR scan, cookie, or OAuth
requirements.

For calmer step-by-step setup, prefer `准备下一个授权`. It opens only one missing
auth flow at a time, in this order:

```text
小红书 -> 视频号 -> Bilibili -> YouTube
```

After finishing that login/OAuth prompt, run `检查全部通道`, then click
`准备下一个授权` again if another auth channel is still missing.

Use `验收通道路由` when you need to prove the code path is wired before asking
Wendy to log in. It runs:

```text
python3 /Users/wendy/work/content-ops/scripts/check_platform_channels.py
```

The script checks channel readiness, chooses representative local drafts for
each platform, and dry-runs all seven routes:

```text
小红书: rendered package -> fill/save draft command dry-run
公众号: wechat-workflow draft payload dry-run
视频号: TencentVideo(is_draft=True) command dry-run
Bilibili: biliup --is-only-self 1 command dry-run
YouTube: private upload payload dry-run
X / 知乎: handoff clipboard/editor dry-run
```

Expected result before Wendy logs in: `code_or_runtime_gap_count = 0`, all
seven dry-runs pass, and any remaining failures are only `needs_auth`.

When `needs_auth_count > 0`, use the explicit login runbook:

```text
/Users/wendy/work/content-ops/AUTH_RUNBOOK.md
```

The dashboard also shows `最近动作`, backed by:

```text
/Users/wendy/park-io/outbox/.system/actions/action-log.jsonl
```

Use this panel to confirm what the workbench last checked, prepared, handed off,
or pushed. It is an operational history, not a publication proof; a platform is
considered sent only after Wendy confirms in the platform backend and marks the
local draft as sent.

Before pushing a specific source item, use `预检这条内容` in the detail panel.
It runs a read-only check across all platform channels:

```text
local draft exists
source video exists for video-migration platforms
Xiaohongshu rendered package exists
WeChat MP markdown exists
channel login/cookie/bridge readiness
```

Preflight does not open platform pages, write the clipboard, or create drafts.
It is the recommended check immediately before `推送平台草稿箱` or `打开后台填稿`.

If preflight reports that Xiaohongshu is missing a rendered package, use
`生成小红书图文包`. It runs only local commands:

```text
python3 /Users/wendy/work/content-ops/scripts/quality_xiaohongshu_drafts.py --source-content-id <id> --force
python3 /Users/wendy/work/content-ops/scripts/render_xiaohongshu_cards.py --source-content-id <id> --style dense
```

After this succeeds, run `预检这条内容` again. The item should move from
`缺 xhs_rendered_package` to a pushable local package state, assuming the
Xiaohongshu channel itself is logged in.

If preflight reports that video-migration platforms are missing `source_video`,
use `修复这条原视频`. The dashboard calls the same repair tool but scopes it to
the selected source id:

```text
python3 /Users/wendy/work/content-ops/scripts/repair_missing_douyin_videos.py --source-content-id <id> --apply
```

Do not use this for Douyin gallery/image posts. Gallery sources should stay out
of 视频号/Bilibili/YouTube migration queues and be repurposed as text/image
platform content instead.

If preflight reports that a platform is missing `local_draft`, use
`生成本地草稿`. The dashboard scopes generation to the selected source and
platform:

```text
python3 /Users/wendy/work/content-ops/scripts/generate_repurpose_drafts.py --source-content-id <id> --platform <platform>
```

This writes only local `outbox/drafts/<platform>/*.json|*.md` files. It does not
open a platform backend and does not publish.

When a selected source has several local gaps, prefer `补齐本地缺口`. It batches
the local-only fixes:

```text
generate missing local drafts
render missing Xiaohongshu image-text package
```

It deliberately does not repair videos, open platform pages, write the
clipboard, or publish. Video repair stays a separate explicit action because it
can require network download through Douyin cookies.

When the whole outbox has drifted, use `补齐全部本地缺口` from the dashboard top
bar. It runs the same local-only repair across every indexed Douyin source:

```text
POST /api/actions/repair-all-local-gaps
```

Expected result when the local layer is clean:

```text
source_count=14
ok_count=14
failure_count=0
```

After that, remaining preflight failures should be platform authorization
failures only, not missing local drafts or missing rendered packages.

## Platform Draft Targets

Current target ratios are configured in:

```text
/Users/wendy/work/content-ops/platforms.json
```

Default targets per one Douyin asset:

| Platform | Ratio | Meaning |
|---|---:|---|
| Xiaohongshu | 3.0 | One Douyin can become multiple notes |
| WeChat MP | 0.3 | Only stronger ideas become long articles |
| WeChat Channels | 1.0 | Usually mirrors/edits the video |
| X | 1.0 | One post or short thread |
| YouTube | 0.5 | Selected videos only |
| Bilibili | 0.5 | Selected videos only |
| Zhihu | 0.2 | Only argument-heavy topics |

## Human Confirmation Gates

Never publish automatically unless Wendy explicitly asks for that specific item.

Required confirmation points:

- Xiaohongshu publish or comment
- WeChat draft push or publish
- Any multi-platform `content publish` / `sau` upload
- Any bulk publishing run

Allowed without extra confirmation:

- Refresh metadata
- Generate or overwrite local drafts
- Rebuild dashboard
- Produce preview files

## Tool Selection Rules

Use `content-ops` scripts for Park-IO state and dashboard.

Use `content-rewriter` when upgrading text into Xiaohongshu or WeChat prose:

```bash
/Users/wendy/content-toolkit/capabilities/rewrite/.venv/bin/content-rewriter rewrite \
  --from douyin \
  --to xiaohongshu,wechat \
  --output-dir /Users/wendy/park-io/outbox/drafts/_rewriter \
  <content-dir-or-text-file>
```

Use `xiaohongshu-skills` only through its own CLI rules for native XHS research
or publishing. Publishing requires Wendy confirmation.

Use `/Users/wendy/work/content-ops/scripts/quality_xiaohongshu_drafts.py` as the
fixed Xiaohongshu quality gate after polish and before image rendering. It does
not publish, does not call a model, and does not replace Wendy's final editorial
choice. It records title candidates, formula trace, opening hook, diagnosis, and
warnings directly into the draft.

Use `wechat-workflow` for WeChat article workflow and preview experiments. Treat
it as a WeChat specialist layer, not Park-IO's source of truth.

Use `content publish` / `social-auto-upload` only after drafts are reviewed and
Wendy confirms the publish action.

Use `/Users/wendy/work/content-ops/scripts/transcribe_douyin_mlx.py` for the
Douyin outbox backfill. It uses `/Users/wendy/videocut/.venv-mlx-whisper` and
segment-level timestamps. Do not use `content-extractor --force` for bulk
Douyin video backfill unless word-level subtitle data is explicitly needed.

Use `/Users/wendy/work/content-ops/scripts/organize_douyin_transcripts.py`
before generating Xiaohongshu, WeChat, X, video clip, or platform mirror
packages. The organized transcript is the shared source layer for Xiaohongshu
image-text notes, Xiaohongshu clips, WeChat MP drafts, X threads, and direct
video mirroring to WeChat Channels, Bilibili, and YouTube.

## Current Maturity

Working now:

- Douyin profile ingest
- Daily Douyin sent-save command
- Outbox folder convention
- Cross-platform draft queue generation
- Dashboard and progress tracking
- Xiaohongshu dbskill-inspired quality gate

Needs next hardening:

- Upgrade selected WeChat MP drafts using content-rewriter/wechat-workflow
- Add explicit sent-record command per non-Douyin platform
- Add dashboard actions for review/publish workflow
- Add platform login health checks before any publish automation
