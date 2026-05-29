#!/usr/bin/env python3
"""Topological-order workflow executor for content-repurpose-workflow.yaml.

Reads the workflow YAML, builds a DAG from edges, and runs node `command:`
blocks in dependency order. Nodes without a command (entry / sink / human /
nodes not yet wired) are skipped with a "skipped" status.

Variable substitution: `${var}` in args is replaced from `defaults:` (in YAML)
merged with `--var k=v` (CLI overrides) plus `${source_id}` from `--source-id`.

Failure handling: each command can set `blocks_on_failure: true` (default).
A blocking failure stops the run; non-blocking failures are logged and
execution continues.

Selection flags:
  --source-id <id>      required for any command using ${source_id}
  --lane <id>           only run nodes in this lane
  --from <node_id>      start from this node (skip earlier in topo order)
  --only <node_id>      run only this node (single-step debug)
  --skip <node_id>      skip these nodes (repeatable)
  --dry-run             print planned execution, do not run subprocesses
  --var k=v             override / set substitution variables (repeatable)

Outputs a report to `.runs/workflow/<source_id>/<timestamp>.json` that mirrors
the old `run_xiaohongshu_pipeline.py` report shape so dashboard / downstream
tools continue to work.

This script replaces run_xiaohongshu_pipeline.py for new runs. The old script
is kept for backward compatibility.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import time
from collections import defaultdict, deque
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_WORKFLOW = REPO_ROOT / "content-repurpose-workflow.yaml"
RUNS_DIR = REPO_ROOT / ".runs" / "workflow"

VAR_PATTERN = re.compile(r"\$\{([a-zA-Z_][a-zA-Z0-9_]*)\}")
DEFAULT_TIMEOUT_S = 600


class WorkflowError(Exception):
    pass


def load_workflow(path: Path) -> dict[str, Any]:
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise WorkflowError(f"failed to load {path}: {exc}") from exc
    if not isinstance(data, dict) or "nodes" not in data or "edges" not in data:
        raise WorkflowError(f"{path} missing nodes/edges")
    return data


def topo_sort(nodes: list[dict], edges: list[dict]) -> list[str]:
    node_ids = [n["id"] for n in nodes]
    incoming: dict[str, set[str]] = defaultdict(set)
    outgoing: dict[str, set[str]] = defaultdict(set)
    for edge in edges:
        src, dst = edge["from"], edge["to"]
        outgoing[src].add(dst)
        incoming[dst].add(src)

    in_degree = {nid: len(incoming.get(nid, set())) for nid in node_ids}
    queue = deque(sorted(nid for nid, deg in in_degree.items() if deg == 0))
    order: list[str] = []
    while queue:
        nid = queue.popleft()
        order.append(nid)
        for nxt in sorted(outgoing.get(nid, set())):
            in_degree[nxt] -= 1
            if in_degree[nxt] == 0:
                queue.append(nxt)
    if len(order) != len(node_ids):
        unresolved = sorted(set(node_ids) - set(order))
        raise WorkflowError(f"cycle detected; unresolved nodes: {unresolved}")
    return order


def parse_vars(pairs: list[str]) -> dict[str, str]:
    out: dict[str, str] = {}
    for raw in pairs:
        if "=" not in raw:
            raise WorkflowError(f"--var expects k=v, got {raw!r}")
        key, _, value = raw.partition("=")
        out[key.strip()] = value
    return out


def substitute(value: str, variables: dict[str, str]) -> str:
    def replace(match: re.Match[str]) -> str:
        name = match.group(1)
        if name not in variables:
            raise WorkflowError(f"undefined variable ${{{name}}} in {value!r}")
        return str(variables[name])
    return VAR_PATTERN.sub(replace, value)


def build_command(node: dict, variables: dict[str, str]) -> list[str] | None:
    command = node.get("command")
    if not isinstance(command, dict):
        return None
    script = command.get("script")
    if not script:
        return None
    args = command.get("args") or []
    resolved = [substitute(str(arg), variables) for arg in args]
    script_path = (REPO_ROOT / script).resolve()
    return ["python3", str(script_path), *resolved]


def run_command(
    node_id: str,
    cmd: list[str],
    timeout_s: int,
) -> dict[str, Any]:
    started = time.monotonic()
    try:
        result = subprocess.run(
            cmd,
            text=True,
            capture_output=True,
            cwd=str(REPO_ROOT),
            timeout=timeout_s,
        )
    except subprocess.TimeoutExpired as exc:
        elapsed = time.monotonic() - started
        return {
            "node": node_id,
            "command": " ".join(cmd),
            "returncode": None,
            "ok": False,
            "elapsed_s": round(elapsed, 2),
            "output": f"TIMEOUT after {timeout_s}s\n{exc.stdout or ''}\n{exc.stderr or ''}"[-3000:],
        }
    elapsed = time.monotonic() - started
    combined = "\n".join(
        part for part in [result.stdout.strip(), result.stderr.strip()] if part
    )
    return {
        "node": node_id,
        "command": " ".join(cmd),
        "returncode": result.returncode,
        "ok": result.returncode == 0,
        "elapsed_s": round(elapsed, 2),
        "output": combined[-3000:],
    }


def select_nodes(
    order: list[str],
    node_by_id: dict[str, dict],
    lane: str | None,
    from_node: str | None,
    only_node: str | None,
    skip: set[str],
) -> list[str]:
    if only_node:
        if only_node not in node_by_id:
            raise WorkflowError(f"--only references unknown node {only_node!r}")
        return [only_node]
    selected = list(order)
    if from_node:
        if from_node not in selected:
            raise WorkflowError(f"--from references unknown node {from_node!r}")
        selected = selected[selected.index(from_node):]
    if lane:
        lanes = {n["id"]: n.get("lane") for n in node_by_id.values()}
        selected = [nid for nid in selected if lanes.get(nid) == lane]
        if not selected:
            raise WorkflowError(f"--lane {lane!r} matched no nodes")
    return [nid for nid in selected if nid not in skip]


def write_report(report: dict[str, Any], source_id: str) -> Path:
    folder = RUNS_DIR / (source_id or "no-source")
    folder.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%dT%H%M%S")
    path = folder / f"{stamp}.json"
    path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return path


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Execute a workflow YAML in topological order."
    )
    parser.add_argument("--workflow", default=str(DEFAULT_WORKFLOW))
    parser.add_argument("--source-id", help="Sets ${source_id} for commands.")
    parser.add_argument("--lane", help="Only run nodes in this lane.")
    parser.add_argument("--from", dest="from_node", help="Start from this node.")
    parser.add_argument("--only", help="Run only this node.")
    parser.add_argument("--skip", action="append", default=[],
                        help="Skip this node id (repeatable).")
    parser.add_argument("--var", action="append", default=[],
                        help="Set / override variable k=v (repeatable).")
    parser.add_argument("--dry-run", action="store_true",
                        help="Print planned commands, do not execute.")
    parser.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT_S,
                        help=f"Per-command timeout seconds (default: {DEFAULT_TIMEOUT_S}).")
    args = parser.parse_args()

    try:
        workflow = load_workflow(Path(args.workflow))
    except WorkflowError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    nodes = workflow.get("nodes") or []
    edges = workflow.get("edges") or []
    node_by_id = {n["id"]: n for n in nodes}

    variables: dict[str, str] = {}
    defaults = workflow.get("defaults") or {}
    if isinstance(defaults, dict):
        variables.update({k: str(v) for k, v in defaults.items()})
    if args.source_id:
        variables["source_id"] = args.source_id
    variables.update(parse_vars(args.var))

    try:
        order = topo_sort(nodes, edges)
        selected = select_nodes(
            order, node_by_id,
            lane=args.lane,
            from_node=args.from_node,
            only_node=args.only,
            skip=set(args.skip),
        )
    except WorkflowError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    print(f"workflow={Path(args.workflow).name} nodes={len(selected)}/{len(order)} "
          f"source_id={args.source_id or '-'}", flush=True)

    steps: list[dict[str, Any]] = []
    stopped_early = False
    for node_id in selected:
        node = node_by_id[node_id]
        try:
            cmd = build_command(node, variables)
        except WorkflowError as exc:
            print(f"  error building command for {node_id}: {exc}", file=sys.stderr)
            steps.append({"node": node_id, "status": "command_error", "error": str(exc)})
            stopped_early = True
            break

        if not cmd:
            kind = node.get("type") or node.get("role") or "unknown"
            print(f"  · {node_id:25s} skipped ({kind}, no command)", flush=True)
            steps.append({
                "node": node_id,
                "status": "skipped",
                "reason": f"no command (type={kind})",
            })
            continue

        if args.dry_run:
            print(f"  → {node_id:25s} DRY-RUN  {' '.join(cmd)}", flush=True)
            steps.append({"node": node_id, "status": "dry_run", "command": " ".join(cmd)})
            continue

        print(f"  → {node_id:25s} running …", flush=True)
        result = run_command(node_id, cmd, args.timeout)
        steps.append({"node": node_id, "status": "ran", **result})
        marker = "✓" if result["ok"] else "✗"
        print(f"  {marker} {node_id:25s} {result['elapsed_s']}s rc={result['returncode']}", flush=True)

        blocks = bool((node.get("command") or {}).get("blocks_on_failure", True))
        if not result["ok"] and blocks:
            print(f"  ! {node_id} failed and blocks_on_failure=true; stopping", file=sys.stderr)
            stopped_early = True
            break

    report = {
        "workflow": str(Path(args.workflow).resolve()),
        "workflow_version": workflow.get("version"),
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "source_id": args.source_id,
        "variables": variables,
        "selection": {
            "lane": args.lane,
            "from": args.from_node,
            "only": args.only,
            "skip": list(args.skip),
        },
        "ok": all(step.get("status") in {"skipped", "dry_run"}
                  or step.get("ok") for step in steps),
        "stopped_early": stopped_early,
        "steps": steps,
    }

    report_path = write_report(report, args.source_id or "no-source")
    print(f"report={report_path}", flush=True)
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
