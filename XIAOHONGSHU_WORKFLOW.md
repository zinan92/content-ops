# Xiaohongshu Search-Card Workflow

This is the reusable production workflow for turning one mature Douyin source
asset into one or more Xiaohongshu image-text notes.

## Product Definition

A Xiaohongshu note is not a transcript screenshot and not a generic PPT deck.
For this outbox system, the default format is:

```text
search-driven knowledge card = Xiaohongshu SEO note + light PPT-style card structure
```

Use PPT thinking for structure only: hierarchy, card sequence, contrast,
numbering, and visual clarity. Do not make it feel like a corporate slide deck.
The note should still look like a native Xiaohongshu image-text post that can be
searched, saved, and reviewed quickly.

## What Good Looks Like

The default winning format for Wendy's material is:

```text
image-text note + light PPT structure + Xiaohongshu search keywords
```

That means:

- use image-text as the platform format, because Wendy's source videos are
  arguments, frameworks, and judgments that need to become searchable,
  saveable cards.
- use PPT thinking only for structure: one card, one cognitive move; clear
  hierarchy; cover -> misunderstanding -> reframe -> reasoning -> example ->
  method -> boundary -> saveable rule.
- keep card density high: a full note should usually have 8-10 images, and each
  image card should carry roughly 90-220 Chinese characters.
- add light visual explanation only when it clarifies the logic, such as a small
  flow strip or comparison row. Do not turn the output into a corporate deck.
- keep the surface native to Xiaohongshu: direct titles, keyword-bearing cover
  text, short paragraphs, high information density, and a reason to save.
- never render a raw transcript into images. The organized transcript preserves
  the original thinking; the Xiaohongshu note extracts one independent claim.

In product terms, the Xiaohongshu note is a **search-card content product**:

```text
one search intent -> one claim -> one card chain -> one rendered package
```

The picture cards can borrow PPT discipline, but only for hierarchy and flow.
They should not feel like a corporate slide deck. The surface should still be
native Xiaohongshu: keyword-bearing cover, high-density readable text, strong
first judgment, and enough reasoning to make the note worth saving.

The difference between the three text layers is strict:

| Layer | Purpose | Keep how much source? | Output style |
|---|---|---:|---|
| organized transcript | Preserve Wendy's original thinking | 90%+ | cleaned long transcript |
| note body | Publish caption and context | selective | short paragraphs, discussion-ready |
| image_cards | Final card script | compressed | edited judgments, not transcript chunks |

Anti-patterns:

- transcript screenshot: too oral, too long, no card-level judgment.
- generic PPT deck: visually neat, but not searchable or native to Xiaohongshu.
- title-only draft: looks like a note but was not grounded in source content.
- one source equals fixed three notes: wrong; topic count depends on independent
  claims and source support.

Naming and topic rules:

- a filename is only a weak hint. The draft title must be cleaned before use.
- strip platform suffixes such as `--xiaohongshu-<id>-<n>` and truncated forms
  such as `--xiaohon`, `--xiaohong`, or `--xiaohongsh`.
- choose one `template_kind` for the draft, then use the same kind for title,
  `note_brief`, body, card plan, image cards, and quality checks.
- preserve a filename-derived topic only when it matches the selected keyword
  family; otherwise use the reusable template title for that family.
- align `title`, `note_brief.search_keywords`, cover, tags, and the first body
  paragraph. A good title with unrelated keywords is still a broken draft.

The reusable production chain is:

```text
organized transcript
  -> topic plan
  -> note brief
  -> card plan
  -> card script
  -> rendered image package
  -> platform draft
  -> sent record
```

The long organized transcript preserves Wendy's thinking. The Xiaohongshu note
extracts one searchable, saveable, shareable claim from that transcript.

## Step 1: Topic Plan

One Douyin video can become zero, one, or many Xiaohongshu notes. A topic is
eligible only when it has all of these:

- an independent claim
- a cognitive conflict or curiosity hook
- enough support for 7-10 cards or 700-1200 Chinese characters
- at least one concrete scene, example, analogy, or operating rule
- a clear reader payoff

Do not mechanically convert every chapter into a note.

Use this decision rule:

```text
If a segment cannot support a 7-card chain with one claim, one conflict,
one example, one method, and one saveable conclusion, it is not a Xiaohongshu
note yet. Merge it, reingest it, or drop it.
```

## Step 2: Note Brief

Every Xiaohongshu draft must contain `note_brief` before it is considered
production-ready.

Required fields:

- `search_keywords`: the keyword cluster to hit in title, cover, body, and tags
- `search_intent`: what the reader is searching for or trying to save
- `target_reader`: who this note is for
- `core_claim`: the one claim this note makes
- `cognitive_conflict`: what ordinary readers misunderstand
- `source_evidence`: examples or reasoning retained from the source video
- `reader_payoff`: what the reader can do or understand after reading
- `format_rationale`: why this topic should become search-card image text
- `card_chain`: the intended card sequence, such as cover -> misunderstanding -> reasoning -> example -> method -> saveable rule

Every draft should also contain:

- `xhs_format.format = search_knowledge_cards`
- `xhs_format.visual_mode = light_ppt_text_cards`
- `card_plan`: one row per image card with `role`, `purpose`, and `text`

## Step 3: Card Script

`image_cards` is the source of truth for rendered images. It is not a split
body paragraph list. It should be written after `card_plan`, not copied from
the transcript.

Recommended card chain:

1. Cover: keyword + strongest claim
2. Misunderstanding: what most people get wrong
3. Reframe: the better way to see the problem
4. Reasoning: why this claim holds
5. Example: concrete case from the source video
6. Operating rule: how to apply it
7. Risk / boundary: when the idea fails or is misused
8. Saveable conclusion: a short decision rule

Each card should carry one cognitive move. Prefer 40-120 Chinese characters per
card. Avoid raw oral markers such as "然后呢", "就是说", "对吧", "嗯", and
duplicated ASR fragments. If the source is a dense spoken transcript, preserve
the logic but rewrite the surface language.

Card quality rules:

- Every card needs both a judgment and a reason/context. A card that only says
  "核心观点" or one thin sentence is too empty.
- Cards longer than 150 Chinese characters usually mean transcript leakage.
- At least one of the core search keywords should appear in the title, cover,
  first body paragraph, and tags.
- If two or more cards substantially overlap with raw `source_excerpt`, rewrite
  them. The cards are edited product copy, not subtitles.
- Keep Wendy's meaning and examples, but remove oral scaffolding and repeated
  spoken fragments.

The card script can be generated with:

```bash
python3 /Users/wendy/work/content-ops/scripts/generate_xiaohongshu_from_content_package.py \
  --source-content-id <douyin-aweme-id> \
  --engine auto \
  --overwrite
```

Engine rules:

- `auto`: Claude Sonnet through the CLI proxy first; if Claude fails, use Codex
  CLI. There is no local rules-engine fallback for production copy.
- `claude`: Claude Sonnet only. It must return strict `note_brief + body +
  image_cards` JSON.
- `codex`: Codex CLI only.

Local code is allowed to render images and run quality checks. It must not write
publishable Xiaohongshu titles, body copy, argument packs, or image-card copy.

Legacy local template families are not production engines anymore. If they
remain in old scripts, treat them as historical test fixtures only, not as a
source for publishable copy.

## Step 4: Caption Body

The `body` is platform caption text. It should not be copied into images by
default. It should:

- open with the same keyword cluster as the title and cover
- explain the context in short paragraphs
- preserve Wendy's core reasoning and examples
- end with precise tags

## Step 5: Quality Gate

Before rendering, run:

```bash
python3 /Users/wendy/work/content-ops/scripts/quality_xiaohongshu_drafts.py \
  --source-content-id <douyin-aweme-id> \
  --force
```

The gate must flag:

- missing `note_brief`
- weak title tension
- no cognitive conflict
- no reasoning chain or concrete anchor
- card scripts that still look like transcript chunks
- fewer than 7 cards or thin cards
- missing keyword coverage across title / cover / body / tags
- overlong cards that read like pasted transcript

The current reusable gate is `search-card-v2`. It intentionally fails drafts
that look informative but are still just oral transcript split into images.

## Batch Upgrade

To upgrade all eligible Xiaohongshu drafts to the current reusable card
standard, run a dry-run first:

```bash
python3 /Users/wendy/work/content-ops/scripts/upgrade_xiaohongshu_search_cards.py
```

Apply the upgrade only after checking the eligible/skipped counts:

```bash
python3 /Users/wendy/work/content-ops/scripts/upgrade_xiaohongshu_search_cards.py \
  --apply

python3 /Users/wendy/work/content-ops/scripts/upgrade_xiaohongshu_search_cards.py \
  --apply \
  --render-only
```

The upgrade script deliberately skips drafts in the action queue and drafts
whose `source_excerpt` is under the threshold. Those must be reingested, merged,
or dropped; they should not be repaired by inventing content from titles.

Use `--only-non-v2` only when rules are unchanged and the goal is to catch up
old non-v2 drafts. If title parsing, topic classification, template text,
quality checks, or rendering assumptions changed, do not use `--only-non-v2`;
rewrite all eligible drafts so the dashboard shows one coherent standard.

For the full outbox workflow, use:

```bash
python3 /Users/wendy/work/content-ops/scripts/run_outbox_workflow.py \
  --upgrade-xhs-v2 \
  --render-upgraded-xhs \
  --verify
```

## Step 6: Rendering

Render with:

```bash
python3 /Users/wendy/work/content-ops/scripts/render_xiaohongshu_cards.py \
  --source-content-id <douyin-aweme-id> \
  --style dense \
  --overwrite
```

Dense rendering uses `image_cards` only. `body` is the caption source, not an
image source. If the card script is thin, fix `image_cards` and rerun quality;
do not let the renderer silently fill images with caption or transcript text.

## Verification

After changing the workflow, run:

```bash
python3 /Users/wendy/work/content-ops/scripts/verify_xiaohongshu_workflow.py --render
```

This verifies representative production packages end to end:

- generate AI-authored drafts with `--engine auto`
- quality gate
- rendered image package
- renderer regression: `body` must not be used as an image fallback

The verifier runs on copied drafts under `.runs/tmp/`, not production drafts in
`outbox/drafts`.

The report is written to:

```text
/Users/wendy/work/content-ops/.runs/reports/xiaohongshu-workflow-verification.json
```

For all current Xiaohongshu drafts, run:

```bash
python3 /Users/wendy/work/content-ops/scripts/audit_xiaohongshu_workflow.py --fail-on-issues
```

Audit statuses:

- `passed`: draft has source support, note brief, card plan, image cards, and quality gate.
- `blocked_source`: source excerpt is missing or too short; return to transcript/topic extraction before publishing.
- `needs_work`: source exists but the script/template/quality layer still needs repair.

When `blocked_source` comes from a stale or missing excerpt, repair from the
current Douyin transcript units before rewriting:

```bash
python3 /Users/wendy/work/content-ops/scripts/repair_xiaohongshu_source_excerpts.py --min-chars 400
```

If repair still leaves less than 400 Chinese characters, keep the draft blocked.
The workflow should never promote a title-only draft into a publishable note.

Use triage to turn remaining blocked drafts into an action queue:

```bash
python3 /Users/wendy/work/content-ops/scripts/triage_xiaohongshu_blocked_sources.py --min-chars 400
```

Reports:

```text
/Users/wendy/work/content-ops/.runs/reports/xiaohongshu-blocked-source-triage.json
/Users/wendy/work/content-ops/.runs/reports/xiaohongshu-blocked-source-triage.md
```

For daily production on one Douyin source, run:

```bash
python3 /Users/wendy/work/content-ops/scripts/run_xiaohongshu_pipeline.py \
  --source-content-id <douyin-aweme-id> \
  --engine auto
```

This is the stable single-entry command for the Xiaohongshu AI pipeline.
