# 02 — The Intake Agent (the concrete first build)

## Why this first

Before we build the full four-stage pipeline, we want to validate the most novel idea (CaaS — Context as a Skill) in isolation. The intake agent is small, scoped, and shippable. If it works, we've de-risked the most uncertain piece of the architecture. If it doesn't, we learn that early and can rethink before committing to the full pipeline.

It's also useful **standalone**, even if we never built the rest. A tool that takes a customer's runbook and converts it to a structured role-context object is shippable as its own thing — it could feed any harness, any framework, any FDE.

## What it does

**Input:** one or more unstructured customer artifacts about a job/role/process. Examples:
- A job description (PDF, Markdown, Google Doc paste)
- A team runbook (Confluence export, Markdown)
- A process diagram with text annotations (image + caption text)
- A recorded interview transcript (transcript text)
- A Slack channel export (subset)

**Output:** a structured `RoleContext` object representing the tribal knowledge in the input, plus an explicit "what's missing" report.

## RoleContext schema (sketch)

```python
class RoleContext(BaseModel):
    role_name: str                      # "Customer Success Manager"
    role_summary: str                   # 2-3 sentences of what the role exists to do
    primary_outcomes: list[str]         # measurable success states
    typical_workflows: list[Workflow]   # named end-to-end flows (e.g. "onboard new customer")
    decision_criteria: list[Decision]   # named decisions, with the inputs they take
    escalation_paths: list[Escalation]  # when does this role hand off, to whom
    domain_vocabulary: dict[str, str]   # role-specific terms and definitions
    common_edge_cases: list[EdgeCase]
    unwritten_rules: list[str]          # heuristics flagged in the source ("when 50/50, customer wins")
    confidence_per_field: dict[str, float]
    flagged_unknowns: list[Unknown]     # things the source DOESN'T cover, that the discovery agent should probe
```

The last field is critical. The intake agent isn't just structuring what's there. It's also explicitly noting what's NOT there. This becomes input to the discovery agent's gap-finder later.

## How it works

Single specialist agent (one instance of `run_loop`) with a tightly-prompted multi-step internal flow. No multi-stage pipeline needed for this piece.

```
input artifacts
    │
    ▼
1. Classifier
   "What kind of artifact is this? job description, runbook,
   transcript, etc.?" Picks the right downstream extractor.
    │
    ▼
2. Extractor (one per artifact type — different prompts)
   Pulls out role_summary, workflows, decisions, etc. from
   the source text. Conservative — only extracts what's there.
    │
    ▼
3. Vocabulary normalizer
   Identifies domain-specific terms in the source. Defines them
   in role_vocabulary. Deduplicates synonyms.
    │
    ▼
4. Unwritten-rules sniffer
   Specific sub-prompt looking for heuristics, biases, soft
   rules ("we always do X unless Y"). These often appear as
   asides or in transcript dialogue, not in formal sections.
    │
    ▼
5. Gap reporter
   Reads the structured output and lists what's missing.
   "No escalation paths defined." "No timing/SLA mentioned."
   "Decisions are listed but the inputs to them aren't."
    │
    ▼
6. Confidence scorer
   For each top-level field, scores 0-1 confidence based on
   how directly the source supported it. Backs each score with
   a 1-line rationale.
    │
    ▼
RoleContext object (saved to discovery-inception/skills/<role>/context.json)
```

Each numbered step is its own LLM call with its own tightly-scoped prompt. They all share the same context (the source artifacts) but produce different slices of the output. This is exactly the "decompose into atomic steps" pattern we believe in.

## Tools the intake agent uses

| Tool | Purpose |
|---|---|
| `read_file` (existing) | Load artifacts from disk |
| `web_fetch` (existing) | If artifact is a URL (e.g., public job posting) |
| `write_skill` (new) | Persist the RoleContext object as a JSON skill |

`write_skill` is a small new tool. Takes a `RoleContext` and writes it to `discovery-inception/skills/<role-id>/context.json`. The folder structure becomes the customer's growing library of role contexts.

## What we test it against

Pick **one real artifact**. Don't generalize prematurely. Best candidates from your work life:

1. **An Atlan job description** for an existing role (e.g., Solutions Architect, Customer Success Manager). Public source, easy to get, role you understand well, can sanity-check the output.
2. **A runbook or onboarding doc** from one of your customer accounts (with anything sensitive redacted). Higher signal because tribal knowledge is dense in runbooks.
3. **A transcript of one of your discovery calls** with a customer. Hardest case — implicit knowledge is the densest here, so if the intake agent extracts well from a transcript, it'll handle anything.

Recommended: start with **(1)**, move to **(2)** once it's working, push to **(3)** as the stretch goal.

## Success criteria for v0

The intake agent passes if:

1. Given a real role artifact, it produces a `RoleContext` that **a knowledgeable colleague would describe as accurate** (not "complete" — accurate. We don't expect it to invent missing info).
2. The `flagged_unknowns` field surfaces at least 3 specific things missing from the source that a discovery agent should probe.
3. The `unwritten_rules` field captures at least one heuristic that wasn't a section header in the source — the kind of thing that lives in asides or examples.
4. Running it twice on the same input produces stable output (low variance — important because downstream stages will rely on this).

If any of these fail, the failure tells us something specific. (1) failing means our extractor prompts are bad. (2) failing means our gap-reporter prompt is too lenient. (3) failing means we're doing surface-level extraction. (4) failing means we have temperature/top-p set wrong or our prompts are under-specified.

## Concrete implementation plan (when we're ready to code)

1. **Pick the artifact** (one — see above).
2. **Build the schemas** (`RoleContext`, `Workflow`, `Decision`, etc. as Pydantic models). Stored in `discovery-inception/intake/schemas.py`.
3. **Write the 6 prompts** (one per step in the internal flow). Stored as Markdown in `discovery-inception/intake/prompts/`. Iterate on these. **This is where 80% of the effort will go.**
4. **Wire it into the existing harness** as a new specialist agent. Reuse `core/loop.py`. Add the new `write_skill` tool.
5. **Test against the chosen artifact**, eyeball the output, refine the prompts, repeat.
6. **Eval set:** keep 3-5 artifacts you've manually annotated with what the "right" extraction looks like. Run them through the agent on every prompt change. Track regression.

Estimated build size: ~150-300 lines of code on top of the existing harness, plus the prompts.

## Open questions to resolve before/during the build

- **Should artifacts be normalized to plain text before extraction, or should the extractor handle different formats directly?** Probably normalize first (PDF → markdown, image+caption → text). Cleaner.
- **Should we ship multiple specialized intake agents (one per artifact type) or one general one?** v0: one general one with a classifier step. v1: split if the prompts diverge enough.
- **Where do skills live on disk?** Proposed: `discovery-inception/skills/<role-id>/context.json` plus the source artifacts in the same folder for traceability. Customer can rebuild from source if the schema changes.
- **What's the user interaction during intake?** v0: zero. Drop artifacts in, run command, get output. The discovery pipeline (later) is conversational; intake is batch.

## Why this small project carries the most weight

The intake agent is the cleanest test of the worldview. If a small focused agent with carefully-scoped prompts can take one customer artifact and produce a structured object that is meaningfully more useful than the source, the decomposition thesis is alive. If it can't, we need to rethink before scaling.

It's also the place where you'll feel — viscerally — how much of the work is **prompt design and decomposition** vs. how much is **code**. Almost all the value will live in those 6 prompts. The Python around them is plumbing.
