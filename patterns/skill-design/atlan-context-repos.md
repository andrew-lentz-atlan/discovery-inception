---
title: Atlan Context Repos — The Composite-Asset Context Layer
category: skill-design
status: draft
last_updated: 2026-05-29
source_external:
  - Atlan Docs — "ContextRepository | Atlan Documentation" (typedef reference, 2026-05-20)
  - Atlan Docs — "Context Engineering Studio" (21 docs tagged, customer-facing concept pages, 2026-05-21)
  - Internal Atlan Confluence — "Context Studio — MCP Capabilities, Architecture & Code Provenance" (Abhinav Mathur, 2026-05-20)
  - Internal Atlan Confluence — "Atlan Context Engine" (Amit Prabhu / Austin Kronz, 2026-05-01)
  - Internal Atlan Confluence — "Context Studio Audit — feat/context-studio-wisdom-routers" (Abhinav Mathur, 2026-05-22)
  - Internal Atlan Linear — TTD-105 "Context Repository TypeDef" (Shivansh Pahwa, 2026-05-07)
  - Internal Atlan Linear — CTX-417 "Context Repositories display as SKILL asset type in catalog" (2026-05-29)
  - Internal Atlan GitHub — atlanhq/agent-toolkit PR #227 "feat(mcp): add create_context_repos and create_skills tools" (Anirudh Agarwal, 2026-05-21)
  - Internal Atlan GitHub — atlanhq/atlas-metastore PR #6571 "TTD-700 | Relationship policies for Skill and Context Repository associations" (Shivansh Pahwa, 2026-05-07)
  - Internal Atlan Slack — #collab-context-engineering-studio threads (Apr–May 2026)
  - Internal Atlan Pulse — "Q&A: Agent Development and Context Repositories" (Prashant Agrawal, Shivansh Pahwa, 2026-05-21)
  - Atlan Activate 2026 — "The Context Layer, Live" marketing site (atlan.com/activate)
applies_when:
  workloads: [atlan-internal-agent-builds, customer-facing-data-agents, nl2sql-agents, multi-runtime-agent-deployments, cross-team-agent-stacks]
  constraints: [agent-needs-atlan-metadata-context, governance-or-audit-required, context-shared-across-multiple-agents, dialect-portability-desired]
contradicts: []
related: [harnesses/claude-agent-sdk-deep-dive, skill-design/atlan-skills-as-assets, skill-design/atlan-context-without-repo, skill-design/atlan-mcp-integration]
snapshot_date: 2026-05-29
---

# Atlan Context Repos — The Composite-Asset Context Layer

A context repo is one option for the **context layer** in an agent build that touches Atlan. It is a composite Atlan asset — first-class, typed, governed — that bundles the YAMLs, `SKILL.md` files, SQL templates, agent instructions, and knowledge files an agent loads at runtime. Sitting between the raw metadata graph and the agent's process, it's Atlan's bet on what a *versioned, portable, governed unit of agent context* should look like.

This entry covers what's actually inside a context repo, how an agent gets bytes out of it, where it composes (and conflicts) with code-resident skills and other context sources, what the dialect-translation story really is in mid-2026, and the conditions where reaching for a context repo earns its weight — versus where it doesn't.

Context repos are one option among several. The SE/FDE decision is not *"should we use a context repo?"* in isolation — it's *"which slice of this agent's context belongs in a repo, which belongs as raw metadata pulled via MCP, and which belongs in code?"*

## What a context repo actually is

A `ContextRepository` is a concrete Atlas typedef in the `Agentic` supertype hierarchy. The shape, per the public type reference and the internal Linear ticket (TTD-105):

```
Catalog
└── Agentic
    ├── Artifact (extends Agentic + File)
    ├── Skill
    │   └── skillArtifacts → SkillArtifact
    ├── SkillArtifact (extends Artifact)
    └── Context
        ├── ContextRepository (extends Context + Skill)
        │   ├── contextRepositoryLifecycleStatus  (DRAFT | ACTIVE | DEPRECATED | ARCHIVED)
        │   ├── contextRepositoryAgentInstructions
        │   ├── contextRepositoryTargetConnectionQualifiedName
        │   ├── contextInputAssets    → Asset[]   (many-to-many)
        │   ├── contextOutputSkill    → Skill     (1:1, peer-to-peer)
        │   └── contextArtifacts      → ContextArtifact[]
        └── ContextArtifact (extends Context + Artifact)
```

A repo is *one* `ContextRepository` entity plus a paired `Skill` (with `skillType=CONTEXT_REPO`) plus N `SkillArtifact` entries — each artifact's bytes live in S3 at `context-repos/<repo_guid>/<display_name>`, and a vector index row lives in TurboPuffer keyed by the Skill GUID. The repo points at Atlan assets it was *built from* (`contextInputAssets`) and produces a Skill that downstream agents discover.

| Layer | What lives there |
|---|---|
| **ContextRepository entity** | Name, description, lifecycle, agent instructions, target connection, governance metadata, owner users |
| **Paired Skill (skillType=CONTEXT_REPO)** | The discoverable handle for the repo — what semantic search returns to an agent |
| **SkillArtifacts** | The actual files — typed as `yaml`, `sql`, `md`, `json`, `txt` |
| **S3 bytes** | Raw file content at `context-repos/<repo_guid>/<rel_path>` |
| **TurboPuffer row** | Embedding of name+description plus the metadata an agent filters on (`lifecycleStatus`, `targetConnectionQualifiedName`, `agentInstructions`, `inputAssetGuids`) |
| **contextInputAssets** | The tables, columns, knowledge files that *grounded* the repo — preserved as lineage |

The canonical bundle that ships from the agent-toolkit `create_context_repos` MCP tool today, per PR #227:

```
my-repo/
├── soul.md                          # personality, voice, style
├── AGENT.md                         # how to interpret outputs
├── skills/
│   ├── refunds/SKILL.md             # one skill = one bounded behavior
│   └── escalation-routing/SKILL.md
├── semantic_models/
│   ├── orders.yaml                  # Cortex / Genie model
│   └── headcount.yaml
├── queries.sql                      # verified query templates
├── quality-report.md                # repo health / coverage signal
└── eval.json                        # Braintrust config
```

Versioning is repo-level: every change creates a new `skillVersion` on the paired Skill; `GET /context-repos/{guid}/versions` lists history, `POST /context-repos/{guid}/rollback` restores a prior version non-destructively. Lifecycle is `DRAFT → ACTIVE → DEPRECATED → ARCHIVED` — and as of May 2026, creation now writes `ACTIVE` directly (the old two-step `DRAFT → activate` flow was friction that left invisible repos lying around).

Ownership is real ownership. `ownerUsers` is on the entity, RBAC is enforced via bootstrap relationship policies (atlas-metastore PR #6571 added `LINK_CONTEXT_REPOSITORY_TO_OUTPUT_SKILL` and `LINK_CONTEXT_REPOSITORY_TO_INPUT_ASSETS`), and changes show up in the catalog audit trail like any other asset. A context repo is a governed object, not a folder in someone's home directory.

## How agents actually consume a context repo

The discovery surface is not "the agent reads the repo." It's *the agent semantic-searches the skill index, gets back a Skill GUID, then progressively pulls the bytes it needs*. Concretely, with the wisdom router surface that exists today:

```
Agent prompt: "what's our refund rate this quarter?"
   │
   ▼  (TPuf vector search over {tenant}_atlan_skills)
search_skills_tool(query="refund metrics", scope="tenant")
   → [{skill_guid, name, description, agentInstructions, targetConnectionQN}, ...]
   │
   ▼  (agent picks a skill, resolves to its repo)
get_context_repo(repo_guid)
   → { artifacts: [{guid, displayName, fileType}, ...] }
   │
   ▼  (lazy fetch — only the artifacts the agent decides it needs)
GET /skill-artifacts/{artifact_guid}/content
   → raw bytes (YAML / SQL / Markdown / JSON)
```

This is "skill discovery via search → artifact fetch on demand" — not "stuff the whole repo into the context window." The lazy load matters: Hrushikesh's early E2E POC hit ~700k tokens trying to eagerly load everything via `query_assets_tool`, which is what motivated the per-artifact fetch endpoint.

There are three callable surfaces today, with different fit conditions:

| Surface | What it's good for | What it costs |
|---|---|---|
| **MCP tools** (`create_context_repos`, `search_skills_tool`, `get_context_repo`, `create_skill_artifact`) | Agents already speaking MCP. Discovery-then-pull. | Round-trips per artifact; agent has to reason about which to fetch. |
| **Wisdom REST API** (`/api/ai/context-repos/*`) | Direct programmatic access from a Python orchestrator. Used by Context Studio's own UI. | Same byte semantics as MCP; no MCP framing tax. |
| **`atlanfs` virtual filesystem** (POC, May 2026) | Agents that already speak filesystem — Cursor, Claude Code, Codex. `ls`, `cat`, `grep` over `./atlan/skills/<name>/SKILL.md`. | Read-only as of May 2026; bypasses MCP entirely; not yet GA on the platform. |

Pyatlan does not have a `ContextRepository` model class yet. `get_asset_tool` and `search_assets_tool` return base `Asset` attributes only — `lifecycleStatus`, `targetConnectionQualifiedName`, `agentInstructions` are all silently missing if you go that route. The internal workaround is `list_context_repos` / `get_context_repo`, which hit Atlas indexsearch with an explicit attributes list. If your build needs to read repos from Python before MCP is wired up, raw HTTP against `/api/meta/search/indexsearch` with `__typeName.keyword: ContextRepository` works and bypasses the pyatlan gap (this was Andrew Lentz's confirmed-working approach in April 2026).

One persistence subtlety worth knowing: Atlas + S3 are source of truth. TPuf is a derived view. The reindex hook (`_reindex_skill_tpuf`) fires after every artifact add and is *non-fatal* — if it fails, the Atlas/S3 write already succeeded and the agent will read stale search results until the next reindex. There's a manual escape hatch (`update_lifecycle`) to force re-sync. Important to know when debugging *"why doesn't the agent see the artifact I just added?"*

## Composition with the other context options

A context repo is never the whole context story. An agent typically has four context streams, and the design job is deciding which slice goes where.

| Source | Lives in | Read at runtime via | Best for |
|---|---|---|---|
| **Context repo** (this entry) | Atlan as `ContextRepository` + Skill + SkillArtifacts | MCP / wisdom REST / atlanfs | Curated, versioned, governed context bundles shared across agents |
| **Skills-as-assets** (standalone Skill with `skillType=SYSTEM` or `CUSTOM`) | Atlan as bare `Skill` + artifacts, no parent repo | Same surfaces | Reusable capability fragments that don't belong to one domain repo (platform skills, user-authored skills, agent-generated skills) |
| **Raw Atlan metadata** | The lakehouse / Atlas / glossaries / lineage | MDLH SQL, pyatlan, Atlan MCP tools | Live operational metadata — freshness, lineage, ownership, current schema |
| **Code-resident skills** (in your agent's repo) | The agent's own git repo as `SKILL.md` / Python / YAML | Filesystem at startup | Logic specific to *this* agent; iterating fast; not worth governing |

The composition pattern, in the framing Sushovan put on it in April: *"Agents will have tools, permissions, triggers, connectors and a context repository. The context repo will house all skills, semantic model, knowledge tables, etc."* The repo is the bounded box for *agent-consumable* context that needs to outlive any single agent process.

Where the boundaries get fuzzy in practice:

- **Repo vs standalone Skill** — Both produce `Skill` entities in Atlas; both get TPuf rows in `{tenant}_atlan_skills`; both are searchable by `search_skills_tool`. The difference is the parent: a Skill *with* a `contextSourceRepository` belongs to a repo; one without is standalone. SYSTEM and CUSTOM skills exist independently. Practically: if a behavior is one of many capabilities a domain agent needs, it lives inside a repo; if it's a platform-wide utility (`list-lineage-impact`, `find-data-product-owner`), it's a standalone Skill. The Atlan-skills GitHub repo (`atlanhq/atlan-skills`) is a parallel publishing surface for standalone skills, populated by Anirudh in early May 2026 for customer demos through Cursor and Claude Code.
- **Repo vs MDLH query** — A repo's `semantic_models/*.yaml` describes how to *talk about* a table. MDLH gives you the table itself. The agent ideally reads the YAML for definitions and joins, then queries MDLH for the actual rows. Trying to encode operational answers in repo artifacts (rather than as MDLH queries the agent runs) is a known anti-pattern; the repo gets stale fast.
- **Repo vs code-resident skill** — If your agent is single-purpose, single-team, and you don't need other agents to consume the same context, code-resident is faster. The repo earns its weight when *another agent* needs the same context.

The shared-context pitch is real but conditional. The headline on the Activate 2026 site — *"One Context Repo, shared across every agent in your stack via MCP and native integrations, and improved continuously"* — describes a working pattern (Medtronic's HR Cortex repo shared across the analyst agent + MoveWorks rollout is a live example). But the sharing-discipline assumes the *consuming agents* respect the repo's framing — if one agent treats `revenue.yml` as gospel and another silently overrides definitions in its prompt, the shared-repo guarantee dissolves.

## Per-output dialect translation

This is the most-discussed forward-looking play and the most-misunderstood one in mid-2026. The marketing claim is that a context repo authored once in Atlan's portable format translates to whatever dialect the consuming agent's runtime needs:

> "Translated into each platform's native dialect" — Snowflake Cortex semantic model YAML, Databricks Genie Metric View, LangGraph node spec, Claude Skill, generic MCP — all from one repo source.
> — Prukalpa's Context Layer deck (2026-05-29)

The state as of late May 2026:

- **Cortex Analyst YAML** — Implemented. Public docs page exists ("Certify and deploy a context repository to Snowflake Cortex Analyst"). Customer-running: Medtronic HR Headcount, ColPal P&L + Nielsen, others. The YAML *is* the semantic model the Cortex Analyst consumes.
- **Databricks Genie Metric Views + Genie Space** — Implemented. Public doc: "Deploy a context repository to Databricks Genie."
- **Generic MCP** — The default. Every repo is consumable via `search_skills_tool` / `get_context_repo` / `get_skill_artifact_content` regardless of runtime.
- **Claude Skills format** — Aspirational at the platform level, working at the demo level via `atlanfs` (the May 8 POC mounts repo artifacts as a `./atlan/skills/<name>/SKILL.md` tree). Conceptually clean — Claude Code reads it as native filesystem skills. Not yet a GA "publish to Claude Skill" path.
- **LangGraph nodes / OpenAI tools** — Aspirational. Referenced in Activate 2026 messaging ("LangGraph, Cortex, Genie, or your own") and the Prukalpa keynote deck but not implemented as a translator at the platform level. The pattern works *because* MCP is the universal substrate, not because Atlan generates LangGraph-specific code today.

The honest framing for an SE pitching this to a customer: *"Context repos are dialect-portable today via MCP for any MCP-speaking runtime, and have explicit translators to Cortex Analyst and Databricks Genie. Translation to other runtimes' native formats is on the roadmap and demonstrable via filesystem mount; you should not assume a one-button publish to LangGraph or OpenAI Agents SDK exists in mid-2026."*

The bet underneath — that *the right unit of agent context is a versioned, runtime-agnostic bundle that gets translated per-deploy* — is the strategic claim. It's a real product direction, not just marketing. But it's a roadmap claim, not a shipped feature, for any runtime past Cortex/Genie/MCP.

## When a context repo is the right call

- **Cross-agent context sharing.** Multiple agents (a Slack bot, a Cortex Analyst, a Genie space, a Claude Code session) all need the same definitions, metrics, joins, instructions. Authoring once and consuming everywhere is the headline use case. Without this, the overhead of governance doesn't pay back.
- **Governance is non-negotiable.** Audit trail, RBAC, certification (`VERIFIED` / `DEPRECATED`), ownership, change history. If the agent's context drift is itself a compliance question (regulated industries, customer-facing decisions, finance), the repo's first-class-asset status is the entire point.
- **Multi-runtime deployment.** You're deploying the same conceptual agent into Cortex and Genie, or into a chat app + an embedded copilot, and you want one definition of "revenue" across all of them. The dialect-translation story (where it's implemented) actually pays back here.
- **The context graph is structurally rich.** Semantic models with joins + named filters + sample values + verified queries — flattening that into a single Markdown file loses the structure. A repo with `semantic_models/*.yaml` + `queries.sql` + `AGENT.md` preserves it.
- **Bootstrap-able from existing assets.** You already have well-described tables, glossary terms, lineage in Atlan. The autonomous-creation flow (Sushovan's demo, April 2026) can crawl those `contextInputAssets`, draft a first version, and hand it to a domain expert for the last 10% — which is real time savings versus blank-page authoring.

## When a context repo is the wrong call

Be honest: most agent builds in mid-2026 don't need this.

- **Single-purpose, single-team agent.** A Slack bot answering one team's questions, owned by that team, never consumed by anyone else. A `SKILL.md` in the agent's git repo iterates faster and costs less. The repo's overhead is governance for governance's sake.
- **Context that changes per-customer at runtime.** Context repos are *static-ish.* The lifecycle assumes weeks-to-months between meaningful changes, with the autonomous-improvement loops as the steady-state delta. If your agent's context is a per-session config built from the user's question, the repo model fights you.
- **Early prototyping.** You're proving the agent can do the thing at all. Spec is unvalidated. Building governance scaffolding around context that will be thrown out in two weeks is premature. Iterate code-resident, validate, *then* graduate to a repo if multi-agent sharing emerges as a real requirement.
- **Small team, code-first culture.** Authoring YAML in Atlan's UI is slower than authoring in a code editor with git history. If the team owns deployment and doesn't need other consumers, the repo's velocity tax is real.
- **The agent's "context" is mostly tool calls.** If the agent's behavior is dominated by 5-6 well-defined tools and a thin prompt, MCP tool definitions plus a system prompt is the right surface. Putting that in a repo adds layers without buying anything.
- **Context that *has* to be code.** Imperative logic, conditional branching, retry policies, type-checked helpers. These belong in the agent's process, not as artifacts. The repo is a context layer, not a tool layer.

## Failure modes and gotchas

1. **The "SKILL asset type in catalog" UX bug.** Per Linear CTX-417 (open as of 2026-05-29), context repos display as `SKILL` asset type in the customer-facing catalog browser. Customers see "SKILL" and get confused — *"is this a context repo or a skill?"* The full repo structure renders correctly from the asset page; the type label is the wrong abstraction at the catalog list level. Workaround: explain the model when demoing.

2. **No update-in-place for artifacts.** As of May 2026: no `PATCH` for artifact content. To edit, add a new artifact with the same `display_name` — the old entity persists as an orphan in Atlas. Cleanup is manual. Anyone authoring repos via MCP at scale should expect orphans.

3. **`contextInputAssets` is set-once.** No way to update the input-asset links after creation via the current MCP/REST surface. If the agent's grounding moves to a different table, you create a new repo. Mid-2026 limitation flagged in the Confluence capabilities doc.

4. **TPuf-vs-Atlas staleness.** The reindex hook is non-fatal. If it fails, the agent will read stale search results until the next successful reindex. Symptom: *"I added artifact X but `search_skills_tool` doesn't return it."* Diagnosis: check TPuf row freshness; the manual `update_lifecycle` call is the escape hatch.

5. **Two TPuf namespaces look similar but are unrelated.** Platform Skills (`atlan_skills`, flat, keyed by `category/slug`, populated by MDLH self-learning) and Context Repo Skills (`{tenant}_atlan_skills`, keyed by Skill GUID, populated by repo writes) are independent. Confusing them ("I'll just search the skill hub for my repo") is a documented recurring source of bugs.

6. **Sync delay between Atlas and MDLH.** Once an asset (including a context repo) is created in Atlas, MDLH lag is ~15 minutes for new entities. Real-time sync for skills and context repos is being prioritized for upcoming releases; if your agent reads context via MDLH SQL rather than via the wisdom MCP tools, expect that delay.

7. **Skill knowledge is bootstrapped from input assets.** Ravi's question in May 2026 — *"where does the 'knowledge' in the generated skill files come from?"* — got the honest answer: from the input assets' descriptions, READMEs, and column enrichments. If the upstream metadata is thin, the generated repo is thin. Garbage in, garbage out, same as any retrieval system.

8. **Versioning is repo-level, not artifact-level.** A single typo fix bumps the whole repo's version. Fine for the GitHub-of-context framing; less fine if you want git-style per-file history. No current way to diff artifact-by-artifact across versions through the UI.

9. **Pyatlan model gap.** No `ContextRepository` Python model as of May 2026. Anything reading repos in code needs `list_context_repos` / `get_context_repo` MCP tools or raw Atlas indexsearch. Custom Python that uses `get_asset_tool` will silently miss every repo-specific attribute and the build will look correct in tests then fail in prod.

10. **V3 vs V2 tenant fragmentation.** Per Ghazal's clarification in April: typedefs are live on all tenants, but the demo-version-3 Context Studio is only on `home`, `dsm`, `projectred`. Customer tenants run V2. Don't assume parity between the demo tenant a customer was shown and the tenant they'll be using.

11. **The "is this an agent or a repo" naming controversy.** Internal Pulse Q&A (May 21, 2026, Prashant + Shivansh): audience asked *"why are these called 'agents' rather than 'repos'?"* Prashant's framing: the context repository *is* the agent's definition and consciousness; the model and runtime are commoditized. Worth knowing internally that the product framing is shifting — *"agent"* and *"context repo"* are increasingly the same thing in Atlan's marketing surface, which can confuse customers who think of an "agent" as the running process.

## Internal disagreement worth knowing

There's a live tension in the design docs (Amit Prabhu's "Atlan Context Engine" page, April–May 2026) between two framings:

- **Tightly-coupled context repo model** — the repo is a standalone primitive with its own approval workflows, versioning, lifecycle hooks. *Atlan owns the source of truth.*
- **Unified agent/skill model** — context repo becomes a skill builder on top of a shared agent/skill platform. CLI-driven, where customers store the canonical bytes in their own GitHub and use CI/CD to push to Atlan. *GitHub owns the source of truth, Atlan is a deploy target.*

Quoting the page directly: *"should this just be CLI driven, where Atlan is the source of truth and the user can store it in gh and use CI/CD to update on Atlan rather than us building a approval system on our end."*

The platform direction (per the same page) is moving toward the unified model: *"The platform moves from a tightly coupled context repo model to a unified agent/skill architecture. Context repo is no longer a standalone system — it becomes a skill builder on top of the shared platform."* This implies the long-term answer for sophisticated customers may be **"author in GitHub, deploy to Atlan as a context repo"** rather than authoring in Atlan's UI.

For an SE: if a customer's data team is git-native and asks *"can I author this in our own repo and push to Atlan?"* — the answer is *"that's the direction, not yet GA."* PR #227 in agent-toolkit (creating bundles via MCP from external sources) is a step in that direction.

## Maturity snapshot — mid-2026

| Capability | Status | Notes |
|---|---|---|
| `ContextRepository` typedef | GA | Live on all tenants, including the Java/Python SDKs (atlan-java, atlan-python) |
| Context Engineering Studio UI (V2) | GA on customer tenants | Authoring + simulation + deploy |
| Context Engineering Studio V3 | Preview | Only `home`, `dsm`, `projectred` as of late May |
| MCP tools (`create_context_repos`, `search_skills_tool`, etc.) | GA via agent-toolkit | PR #227 added the bundle-creation tools May 21, 2026 |
| Cortex Analyst deploy | GA | Published customer docs |
| Databricks Genie deploy | GA | Published customer docs |
| `atlanfs` filesystem mount | POC | May 8 announcement; read-only; not yet on the platform |
| Per-runtime dialect translation (LangGraph/OpenAI/etc.) | Roadmap | MCP is the universal substrate; native publish paths beyond Cortex/Genie not shipped |
| Pyatlan `ContextRepository` model | Gap | Workaround via raw Atlas search or wisdom MCP tools |
| Update artifacts in place | Gap | Workaround: add new + tolerate orphans |
| Update `contextInputAssets` post-create | Gap | Create new repo |
| GitHub-as-source-of-truth (CI/CD push to Atlan) | Roadmap | Discussed in design docs; not implemented |
| A2A write-back (agent corrections flow back into the repo) | Demoed | Activate 2026 demo flow; not GA across customer tenants |
| Real-time MDLH sync for skills/repos | In flight | ~15 min lag today |
| Demand-Driven Context skill (agent asks for context updates when it lacks them) | Aspirational | Adriel Pinto, May 25: *"the ability to demand for context improvements or updates or creation is a great default skill we should recommend in all context repos"* — not in any shipped repo template yet |

## The honest one-liner

A context repo is a real, governed, composable primitive for the agent context layer — useful when context is shared across agents, when governance matters, and when the dialect-translation roadmap pays back. It is not the default answer; the default answer is *"start with code-resident skills + Atlan MCP tools, graduate to a repo when sharing or governance becomes a real requirement."* For Atlan-internal builds where the customer expects to see context governed inside their tenant, the repo is the right call. For internal experiments and single-agent builds where speed matters more than reuse, it's not.

Origin: synthesized from the typedef reference on docs.atlan.com, the internal Confluence architecture audit, the open PRs in atlanhq/agent-toolkit and atlanhq/atlas-metastore, Linear tickets TTD-105 / TTD-700 / CTX-393 / CTX-417, the #collab-context-engineering-studio and #temp-skills-asset-project Slack channels, and the Activate 2026 / Mastercard / Lowes / Gap / Medtronic / ColPal customer-call corpus.
