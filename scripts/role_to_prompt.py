"""role_to_prompt — render a RoleContext as a system prompt.

This is the bridge piece between the discovery system (which produces
structured RoleContext objects) and the harness (which runs an agent
with a system prompt). Renders the context into a markdown block the
agent can use as priors.

Usage:

    # Print to stdout — paste into harness sidebar manually
    uv run python -m scripts.role_to_prompt \\
        --role-id solutions-consultant

    # Push directly to a running harness's /api/config
    uv run python -m scripts.role_to_prompt \\
        --role-id solutions-consultant --push

    # Push to a specific harness URL (default: localhost:8006)
    uv run python -m scripts.role_to_prompt \\
        --role-id solutions-consultant --push --harness-url http://localhost:8006
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import urllib.request
import urllib.error

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SKILLS_DIR = PROJECT_ROOT / "skills"


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------

def render_system_prompt(ctx: dict[str, Any]) -> str:
    """Turn a RoleContext dict into a markdown system prompt."""
    role_name = ctx.get("role_name", "<unknown role>")
    summary = (ctx.get("role_summary") or "").strip()

    lines: list[str] = []
    lines.append(f"You are role-playing as a {role_name} at Atlan. Use the context below as your priors.")
    lines.append("")
    lines.append(f"## Your role")
    lines.append(summary or "_(no summary)_")
    lines.append("")

    outcomes = ctx.get("primary_outcomes") or []
    if outcomes:
        lines.append("## What you're measured on")
        for o in outcomes:
            lines.append(f"- {o}")
        lines.append("")

    workflows = ctx.get("typical_workflows") or []
    if workflows:
        lines.append("## Workflows you run")
        for w in workflows:
            name = w.get("name", "")
            purpose = w.get("purpose", "")
            trigger = w.get("trigger", "")
            steps = w.get("steps") or []
            lines.append(f"### {name}")
            if purpose:
                lines.append(f"_{purpose}_")
            if trigger:
                lines.append(f"**Trigger:** {trigger}")
            if steps:
                lines.append("**Steps:**")
                for i, s in enumerate(steps, 1):
                    lines.append(f"{i}. {s}")
            lines.append("")

    decisions = ctx.get("decision_criteria") or []
    if decisions:
        lines.append("## Decisions you make")
        for d in decisions:
            name = d.get("name", "")
            inputs = d.get("inputs") or []
            criteria = d.get("criteria") or []
            kind = "judgment call" if d.get("is_judgment") else "rule-based"
            lines.append(f"### {name} _(— {kind})_")
            if inputs:
                lines.append(f"**Inputs:** {', '.join(inputs)}")
            if criteria:
                lines.append(f"**Criteria:**")
                for c in criteria:
                    lines.append(f"- {c}")
            lines.append("")

    escalations = ctx.get("escalation_paths") or []
    if escalations:
        lines.append("## When to escalate")
        for e in escalations:
            trigger = e.get("trigger", "")
            target = e.get("handoff_target", "")
            artifacts = e.get("artifacts_passed") or []
            line = f"- **{trigger}** → {target}"
            if artifacts:
                line += f" (hand off: {', '.join(artifacts)})"
            lines.append(line)
        lines.append("")

    vocab = ctx.get("domain_vocabulary") or {}
    if vocab:
        lines.append("## Vocabulary")
        for term, definition in vocab.items():
            lines.append(f"- **{term}** — {definition}")
        lines.append("")
        lines.append("_Items prefixed `[INFERRED]` are not explicitly defined in the source. If a user uses one and the meaning is ambiguous, ask them to clarify rather than guess._")
        lines.append("")

    edge_cases = ctx.get("common_edge_cases") or []
    if edge_cases:
        lines.append("## Edge cases")
        for ec in edge_cases:
            desc = ec.get("description", "")
            handling = ec.get("handling")
            line = f"- **{desc}**"
            if handling:
                line += f" — {handling}"
            lines.append(line)
        lines.append("")

    rules = ctx.get("unwritten_rules") or []
    if rules:
        lines.append("## Unwritten rules")
        for r in rules:
            lines.append(f"- {r}")
        lines.append("")

    gaps = ctx.get("flagged_unknowns") or []
    if gaps:
        lines.append("## What you don't know (acknowledge openly when asked)")
        for g in gaps:
            field = g.get("field", "")
            why = g.get("why_it_matters", "")
            lines.append(f"- **{field}** — {why}")
        lines.append("")
        lines.append("_If a user's question depends on something in this list, do NOT fabricate an answer. Tell them what specifically is undefined and ask them to clarify._")
        lines.append("")

    lines.append("## How to respond")
    lines.append("- If the question matches a workflow, walk through it concretely using the steps and decision criteria above.")
    lines.append("- If it hits an escalation trigger, say so and name the right person or team.")
    lines.append("- If it depends on something in 'What you don't know,' acknowledge the gap and probe — don't guess.")
    lines.append("- Be concise. Use the role's language (the vocabulary section). Don't pad answers with generic best-practices.")

    return "\n".join(lines).strip() + "\n"


# ---------------------------------------------------------------------------
# Pushing to harness
# ---------------------------------------------------------------------------

def push_to_harness(harness_url: str, system_prompt: str) -> None:
    """GET current config, replace system_prompt, PUT it back."""
    base = harness_url.rstrip("/")

    # Fetch current config
    try:
        with urllib.request.urlopen(f"{base}/api/config", timeout=10) as resp:
            current = json.loads(resp.read().decode("utf-8"))
    except urllib.error.URLError as exc:
        raise SystemExit(f"Could not reach harness at {base}: {exc}")

    cfg = current["config"]
    cfg["system_prompt"] = system_prompt

    # PUT back
    body = json.dumps({"config": cfg}).encode("utf-8")
    req = urllib.request.Request(
        f"{base}/api/config",
        data=body,
        headers={"content-type": "application/json"},
        method="PUT",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            _ = resp.read()
    except urllib.error.HTTPError as exc:
        raise SystemExit(f"Harness rejected config: HTTP {exc.code} — {exc.read().decode('utf-8', 'ignore')[:500]}")
    except urllib.error.URLError as exc:
        raise SystemExit(f"Could not push to harness: {exc}")

    print(f"✓ Pushed to {base}/api/config — system prompt updated.", file=sys.stderr)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Render a RoleContext into a system prompt for the harness."
    )
    parser.add_argument(
        "--role-id",
        required=True,
        help="Subdirectory under skills/ that contains a context.json. e.g. solutions-consultant",
    )
    parser.add_argument(
        "--push",
        action="store_true",
        help="Also PUT the rendered prompt to a running harness via /api/config.",
    )
    parser.add_argument(
        "--harness-url",
        default="http://localhost:8006",
        help="Harness base URL when --push is set. Default: http://localhost:8006",
    )
    args = parser.parse_args()

    ctx_path = SKILLS_DIR / args.role_id / "context.json"
    if not ctx_path.exists():
        raise SystemExit(f"Not found: {ctx_path}")

    ctx = json.loads(ctx_path.read_text())
    prompt = render_system_prompt(ctx)

    print(prompt)

    if args.push:
        push_to_harness(args.harness_url, prompt)


if __name__ == "__main__":
    main()
