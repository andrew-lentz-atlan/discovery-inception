---
title: Atlan Skills as First-Class Assets
category: skill-design
status: draft
last_updated: 2026-05-29
source_external:
  - Atlan Documentation — "Skill | Atlan Documentation" (docs.atlan.com agentic types reference)
  - Atlan Documentation — "Agentic | Atlan Documentation" (base class for agentic assets)
  - Atlan Documentation — "Agent | Atlan Documentation"
  - Atlan Documentation — "SkillArtifact | Atlan Documentation"
  - Atlan Documentation — "Extraction pipeline | Atlan Documentation" (knowledge folder → skill files)
  - atlan.com — "Enterprise Skills 2026: A Governance Guide for AI Teams"
  - Internal Atlan research — "Context Studio — MCP Capabilities, Architecture & Code Provenance" (Wisdom routers / TPuf architecture)
  - Internal Atlan research — "Skills as Assets Project" (Slack: temp-skills-asset-project, Apr–May 2026)
  - Internal Atlan research — Conversational Studio release notes (skills as first-class asset, Skills Hub, atlanfs POC)
  - Internal Atlan research — issue-tracker tickets, 2026-05 (skill failure modes)
applies_when:
  workloads:
    - multi-team-agent-reuse
    - governed-data-reach-by-agents
    - skills-with-lineage-requirements
    - tenant-curated-playbook-libraries
  constraints:
    - atlan-is-source-of-truth-for-governance
    - skill-content-stable-enough-to-version
    - consumer-can-discover-via-search-or-mcp
contradicts: []
related:
  - skill-design/atlan-context-repos
  - skill-design/atlan-mcp-integration
  - harnesses/claude-agent-sdk-deep-dive
  - skill-design/inner-pipeline
snapshot_date: 2026-05-29
---

# Atlan Skills as First-Class Assets

Mid-2026: Atlan ships a **`Skill`** entity type in its metamodel. Each skill is its own catalog asset — GUID, qualified name, ownership, certification, lineage, the full machinery — sitting in the same metadata graph as tables, dashboards, and glossary terms. The `agentic` package in the metamodel includes `Skill`, `SkillArtifact`, `ContextRepository`, `Agent`, and `KnowledgeFile`, all extending `Catalog` so they participate in lineage like everything else.

This is one of several places an agent's "skills" can live. Others: the agent's own filesystem (Claude Agent SDK's `.claude/skills/<name>/SKILL.md`), a context repo bundled in Git (an `atlan-skills`-style repo), a Snowflake/Databricks stage, an internal tool's plugin format, an MCP server's tool inventory. **Atlan-managed skills are one option among those.** This entry covers when they fit, when they don't, and what the practitioner needs to know about the current state.

## What "skill as asset" actually means

In the Anthropic Agent Skills spec, a skill is a folder with a `SKILL.md` (frontmatter + body) plus optional companion files. Atlan didn't invent that format — it adopted it. What Atlan added is **catalog identity**:

| Anthropic Agent Skills baseline | What Atlan adds on top |
|---|---|
| `SKILL.md` with `name` + `description` frontmatter | GUID, qualifiedName, slug, displayName |
| Companion files in the same folder | `SkillArtifact` entities (one per file), with `filePath`, `fileType`, version |
| `description` text drives invocation | Same — plus `userDescription`, `aiGeneratedDescription`, certificate status |
| Folder lives on disk | Folder + content live in S3 under `skills/<slug>/v<N>/<rel_path>` (REST-authored) or `context-repos/<repo_guid>/<rel_path>` (context-repo-produced) |
| No notion of owner/cert/policy | `ownerUsers`, `ownerGroups`, `adminUsers`, `viewerUsers`, `certificateStatus`, RBAC policies |
| No lineage | Lineage edges: `agents`, `sourceRepository`, `skillReferencedAssets`, `artifacts`, knowledge-file input |

The skill is still navigable as a folder of Markdown for any agent that wants to read it that way (this is the point of the `atlanfs` POC — mount the tenant as a virtual filesystem so external harnesses see `./atlan/skills/<slug>/SKILL.md` and can `cat` it). What sits underneath is a typed entity in the metastore with the rest of Atlan's governance plumbing attached.

## The `Skill` type — what Atlan tracks

Per the public docs at `docs.atlan.com/.../agentic/skill`, the entity has 5 own properties on top of the ~200 it inherits from `Asset`:

| Property | Values | Meaning |
|---|---|---|
| `slug` | URL-safe string | Stable handle (`asset-deep-dive-report`) |
| `type` | `SYSTEM` \| `CONTEXT_REPO` \| `CUSTOM` | Origin. System = Atlan-shipped. Context_repo = produced by a `ContextRepository`. Custom = user- or agent-authored. |
| `status` | `DRAFT` \| `PUBLISHED` | Per-version lifecycle. Draft is creator-visible only. |
| `artifactPaths` | `Array<string>` | Denormalized file paths of attached `SkillArtifact`s |
| `artifactFileQualifiedNames` | `Array<string>` | Denormalized qNames of those artifacts |

Plus 35 relationships. The load-bearing ones for agent design:

- **`agents`** — back-edge from `Agent` entities that bind this skill (one `Agent` row per `(slug, version)` tuple; agent's own `skillNames` array is the forward edge).
- **`sourceRepository`** — the `ContextRepository` that produced this skill, if any. Context repos emit skills as outputs.
- **`artifacts`** — `SkillArtifact` children (the files in the bundle).
- **`skillReferencedAssets`** (added April 2026) — peer-to-peer, many-to-many: tables, views, columns, dashboards, files that this skill calls out by qualified name. Different from a context repo's input-assets relationship (which is about what feeds the *generation* process). `skillReferencedAssets` is what the *skill itself* reaches for at runtime, and it gives system/custom skills lineage even when there's no parent repo.
- **`asset.skillReferences`** — the reverse: from any asset, "which skills depend on me." Foundational for lineage and for impact analysis when a column's semantics change.

Two things to internalize from the schema:

1. **The skill is `Agentic`, which is `Catalog`, which is `Asset`.** That means it inherits readme, links, tags, custom metadata, certificate status, announcement, owner users/groups, lineage edges, all of it. From a tooling perspective the skill is no different than a table.
2. **A new version is a new entity.** Like `Agent` (which says explicitly "One Atlan entity is created per (slug, version) tuple"), skills version by entity creation, not by mutating in place. That's load-bearing for rollback and for `Agent.skillQualifiedNames` to pin to a specific version.

## SkillArtifact — the file layer

Each file in the bundle is a separate `SkillArtifact` entity, extending `Artifact` (for `version`, `fileType`, `filePath`). The artifact is what holds the actual content. The `Skill` denormalizes its artifact list into `artifactPaths` so a single read can render the file tree without a graph traversal.

Storage layout differs by writer:

- **REST-authored skill** (`SkillsService.create_skill`): files uploaded to S3 at `skills/<slug>/v<N>/<rel_path>` via presigned PUTs (parallel `asyncio.gather`).
- **Context-repo-produced skill** (`entities.create_context_repo`): files at `context-repos/<repo_guid>/<display_name>`. The repo GUID, not the skill GUID, is the key — because Context Studio's file browser resolves paths off the `ContextRepository`.

These are two parallel writer paths into the same TPuf vector namespace (`{tenant}_atlan_skills`). Both call `SkillsTpufSync.write_skill` under the hood. From a consumer's perspective: same lookup, same metadata; from the producer's perspective: two distinct code paths to be aware of.

## Discovery: how agents find a skill

There are at least four discovery paths in production today. They are NOT interchangeable.

1. **TurboPuffer semantic search** (the path Conversational Studio uses). Skills are indexed in the per-tenant `{tenant}_atlan_skills` namespace with a 1024-dim embedding of `name + description` (Cloudflare AI). The agent calls `search_skills_tool` with a natural-language query; TPuf returns hybrid vector + BM25 hits. The system prompt only carries the catalog (`name + description`); full content loads on-demand via `load_skill`. This is the **progressive-disclosure pattern**: keep the index in context, fetch bodies lazily.

2. **MCP tool inventory.** Skills surface through the Atlan MCP server as tools — `search_skills_tool`, `load_skill`, `list_platform_skills`, `get_platform_skill`. An external harness (Claude Code, Cursor, Codex, an OpenAI Agents SDK loop) talks to Atlan MCP and discovers skills the same way it discovers any other MCP-exposed capability. This is the path used when the agent doesn't live inside Atlan.

3. **Atlan catalog UI / `FluentSearch`.** A skill is browsable and searchable like any other asset. The Java SDK exposes `Skill.select(client)` returning a fluent search over all active skills. Useful for governance dashboards, not for runtime invocation.

4. **`atlanfs` virtual filesystem** (POC as of May 2026). Read-only FUSE mount that exposes `./atlan/skills/<slug>/SKILL.md` as real files. Drops Atlan-managed skills into any agent's working directory. Explicitly "experimental — mount it, point an agent at it, and tell us what breaks" per the engineer (Saravanan Elumalai) who built it. Treat it as an investigation, not a deployment surface.

There's also a **Skills Hub** — a curated cross-tenant marketplace. Tenants browse pre-built skills (governance coverage reports, data domain readiness assessments, year-in-review summaries, asset deep-dives) and install with one click. The Hub lives in a separate TPuf namespace (`atlan_skills`, no tenant prefix) and is accessed via `POST /api/v1/skill-hub` with `action=list|search|detail`. Installing copies the skill into the tenant's namespace so the tenant can tweak it.

## Governance: what the catalog gives you that a context repo doesn't

A context repo in Git gives you version control, code review, and reuse across agents. What Atlan-managed skills add on top:

- **Certificate status.** A skill can be marked `VERIFIED`, `DRAFT`, or `DEPRECATED` with a message, an updater, and a timestamp. Agents can be configured to prefer verified skills. Stewards can require certification before a skill is `enable in chat`-able.
- **Ownership + RBAC.** Per-skill `ownerUsers`, `ownerGroups`, `adminUsers`, `viewerUsers`. Policies in Wisdom enforce who can publish a new version, who can delete, who can install from Hub.
- **Two-layer lifecycle.** Per-version `status` (`DRAFT`/`PUBLISHED`) and per-asset `certificateStatus`. Draft skills are creator-only; published skills are visible to the tenant; certified skills carry trust beyond that.
- **"Enable in chat" toggle.** Per-tenant-skill control over whether Conversational Studio surfaces the skill at all. Default is OFF — you opt in deliberately. Keeps noisy context-only data out of chat. (This is also one of the active failure modes — see below.)
- **Lineage on data reach.** When a skill references columns or tables via `skillReferencedAssets`, an asset's downstream-skills view shows "an agent skill depends on me." This is what unlocks "what data did this agent reach for to produce X" — the audit-trail story that's hard to get from a context repo on its own.

The atlan.com governance guide frames it: a skill governs the *procedure*; a context layer governs the *substrate underneath*. Skills as assets is Atlan's attempt to make the same governance surface that already covered the substrate also cover the procedure.

## The runtime story (what actually happens at invocation)

Inside Conversational Studio:

1. Agent boots with a system prompt that includes the **skill catalog** for this tenant (name + description for every skill where `enable in chat` is true) plus the **system skills** (always visible — Gold Layer schema skills for metadata search).
2. User asks a question.
3. Agent decides which skills, if any, are relevant. Multiple skills can be selected in one call.
4. Agent calls `load_skill(slug)` for each selected skill — that pulls the `SKILL.md` body, plus any referenced artifacts, into context.
5. Agent executes — runs SQL via MDLH, calls MCP tools, hits internal services. The skill body tells it *how*.
6. Response streams back.

Externally (Claude Code, Cursor, Codex against Atlan MCP):

1. Agent connects to Atlan MCP server.
2. Discovers `search_skills_tool` / `load_skill` in the tool inventory.
3. Same flow: search → load → execute. The difference is the harness owns the loop and the LLM call; Atlan is just the skill store and tool provider.

Where it gets interesting: the skill body **is not executed by Atlan**. Atlan stores it and serves it. Execution happens in the agent's runtime, against whatever data plane the skill points to (Snowflake via Cortex, Databricks via Genie, MDLH, customer warehouse, etc.). The skill is a procedure spec the agent's runtime follows. This is the same model as Anthropic's Agent Skills — Atlan didn't change it, it wrapped it.

## Composition with other context-layer options

Atlan-managed skills aren't the only place agent capabilities live. Honest mapping:

| Capability lives in… | What it's good for | Where it falls short |
|---|---|---|
| **Atlan-managed `Skill`** | Multi-tenant reuse, governance, lineage, hot-swap without redeploy | Indirection: every change goes through Atlan UI/API. Friction during rapid iteration. |
| **Context repo (Git bundle)** | Single source of truth in code, PR review, CI/CD, branch isolation | No cross-tenant install, no certification flow, no lineage to assets out of the box |
| **Claude Agent SDK skills** (`~/.claude/skills/*/SKILL.md`) | Native to the harness, model-invoked by description, plugins distribute them | Bound to Claude Code/SDK; not portable to Cortex or Agentforce |
| **MCP tool** (raw, no skill layer) | Deterministic, callable, doesn't need an LLM to decide what arguments mean | No reusable procedural knowledge — every agent re-derives the same call sequences |
| **Raw SDK consumption (pyatlan)** | Targeted writes, exact control, no ambiguity | No discovery surface — has to be wrapped in something to be reusable by another agent |
| **Snowflake stage / Cortex agent skill** | Skill runs co-located with data, low latency, billed through warehouse | Bound to Snowflake; Atlan governance not native |

The reality in mid-2026 is that **most production agents mix several of these**. A Conversational Studio agent uses Atlan-managed skills *plus* MCP tools *plus* raw lakehouse queries. A Cursor-based customer demo pulls skills from `atlan-skills` GitHub *plus* connects to Atlan MCP for tool calls *plus* uses Claude Code's native skills for filesystem ops. Atlan-managed skills are a slot in the stack, not the stack.

There's also an unresolved question Slack-active in mid-May 2026: **should Wisdom (Conversational Studio's backend) be one of N consumers of the same skill registry, or is the registry tightly coupled to Wisdom?** Right now Wisdom owns the writer paths and the TPuf namespace, but the architecture intent ("one platform, many consumers") points toward decoupling. Today, **Wisdom is the registry's implementation**, which means non-Conversational-Studio consumers (external harnesses) are second-class — they get read access via MCP/atlanfs but don't share the same authoring or governance flow.

## When Atlan-managed skills are the right call

- **Multi-team or multi-agent reuse.** A single "asset-deep-dive-report" skill consumed by Conversational Studio, by a CSM's Cursor session, and by a scheduled Sherlock investigation — version it once, govern it once.
- **Skills that touch sensitive data.** RBAC + certificate status + lineage gives auditors a real story. "This skill is VERIFIED. Owner is Finance Data Stewardship. Last referenced column was `finance.revenue.net_revenue_q4`. Approved by Tara Flynn on 2026-04-12." That story is hard to construct from a Git repo and a Slack thread.
- **Skills that need lineage tracking against assets.** `skillReferencedAssets` + the back-edge `asset.skillReferences` means a column's downstream view includes "which agent skills depend on me." Required for impact analysis when schemas change.
- **Versioned skills with rollback.** Per-version entities mean pinning `Agent.skillQualifiedNames` to `skills/find-workbooks/v6` works even after v7 ships, and rollback is a pointer change.
- **Customer-installable playbooks.** The Skills Hub is the right surface for distributing curated content cross-tenant. Customers don't want a `git clone` step.

## When *not* to use Atlan-managed skills

- **Skills tightly coupled to one agent's prompt.** If the skill is essentially "this agent's system prompt continued," round-tripping through Atlan to edit it is friction with no payoff. Keep it in the agent's source.
- **Highly experimental skills under rapid iteration.** Per the platform team's own bug list (tracked bug: saved skill v7 wrote under wrong filename and reverted to v6 silently), the authoring path is still maturing. If you're iterating five times a day, the round-trip cost compounds.
- **Skills wrapping runtime-specific APIs.** A Claude Code skill that orchestrates `Read`/`Edit`/`Bash` doesn't belong in Atlan — it has no semantic value for a Cortex or Agentforce consumer. Keep runtime-bound skills in the runtime.
- **When the team isn't using Atlan for governance.** If certificates and ownership aren't a thing the team cares about, Atlan-managed skills add ceremony without payoff. A `~/.claude/skills/` folder or an `atlanhq/atlan-skills` Git repo is lighter.
- **For skills that don't reach Atlan data.** If the skill's job is to talk to ServiceNow, write Slack messages, or call a Stripe API, putting it in Atlan is metadata-for-its-own-sake. The substrate the skill governs isn't in Atlan.

## Failure modes and gotchas (real ones, from internal trackers, mid-May 2026)

These aren't hypothetical — they're what's failing on live tenants.

1. **Routing precedence is unsolved.** `Mandeep Singh Cheema (2026-05-11)`: enabled the `asset-deep-dive-report` skill, asked "tell me everything about finance domain," and the agent loaded `gold-layer-data-mesh` instead — a system skill that's always visible. **System skills outrank tenant skills in current routing.** No deterministic precedence control yet.
2. **"Enable in chat" toggle leaks** (tracked bug, fixed 2026-05-28). On a customer QA tenant, a `find-workbooks` skill with the toggle OFF was still being invoked by routing. The Atlas metastore stored only `skillVersion="7"` and dropped the rest of the metadata silently. Toggle state was not in the metastore at all.
3. **Silent filename corruption on save** (tracked bug, fixed 2026-05-27). A skill edit appeared to save and then reverted. Root cause: the v7 artifact wrote to `skills/find-workbooks/v7/Find Dashboards.md` instead of `skills/find-workbooks/v7/SKILL.md`. The read path falls back to v6 if `SKILL.md` is missing — no error surfaced.
4. **TPuf metadata drops** (Context Studio audit, May 2026). `_index_parent_in_tpuf()` accepted 5 extended params (`lifecycle_status`, `target_connection_qn`, `agent_instructions`, `input_asset_guids`, `skill_type`) but never wrote them into `skill_attrs`. All 5 silently dropped. Discovered via E2E test, not by any monitoring.
5. **Catalog naming risk** (tracked issue, in triage as of 2026-05). Context Repositories surface in the catalog as `SKILL` asset type, which "may be confusing since context repos are a distinct concept." Open question whether to introduce a dedicated `ContextRepository` asset type at the UI layer. (Internally it already is its own entity; the UI just defers to skill-typed display.)
6. **`type` enum is too narrow** (tracked request, under consideration as of 2026-05). `SYSTEM | CONTEXT_REPO | CUSTOM` doesn't fit "extracted from a Databricks workspace" or "synced from a Snowflake stage." Using `CUSTOM` for connector-sourced skills conflates tenant-authored with platform-sourced. Need a fourth value `CONNECTOR_SYNC`.
7. **Eager-loading skill content is a scaling cliff.** Sherlock (the internal incident agent) eager-loaded skill reference files into its system prompt and hit the Linux `MAX_ARG_STRLEN` ~128KB cap (`MER-59`). Had to drop `debug-atlas-401.md` to stay under. Fix is on-demand `read_skill_reference` — the same progressive-disclosure pattern Conversational Studio uses. **The lesson: if your harness doesn't do progressive disclosure, Atlan-managed skills will starve it of context budget.** External harnesses without progressive disclosure (CrewAI was called out specifically — Simone Useri 2026-05-18) need to either implement lazy fetch via MCP or restructure the skill to be smaller.
8. **No version control on the skill content path itself.** Skills version by `(slug, version)` tuple but there's no Git-equivalent for the body — you can't diff v6 vs v7 in the UI, you can't do a PR review of a skill edit, and rollback is "create a new version that's a copy of an old one." Several internal engineering threads are pushing for "Atlan AI registry" with a real registry feel. Not there yet.

## Maturity snapshot, May 2026

What ships and works today:

- `Skill` and `SkillArtifact` entities in production. Type defs deployed across tenants. Wisdom backend GA confirmed before the frontend Skills Hub UI merged (`2026-05-08`).
- Conversational Studio reads tenant skills + system skills, with progressive disclosure via TPuf.
- Frontend Skills Hub: browse, install, "enable in chat" toggle, drag-drop folder/zip upload.
- 11 system skills covering the full Gold Layer (assets, glossary, data mesh, DQ, tags, custom metadata, lineage, owners, pipelines, BI assets, query performance).
- Context Repo → Skill emission. Producing a context repo creates a back-linked `Skill(skillType=CONTEXT_REPO)`.
- MCP exposure: `search_skills_tool`, `load_skill`, `list_platform_skills`, `get_platform_skill`, `search_platform_skills`.
- Skill Hub backend (`POST /api/v1/skill-hub`) and `atlan_skills` cross-tenant namespace.

What's in flight or unresolved:

- **Routing precedence.** When tenant skill and system skill both match, which wins? No deterministic answer.
- **External harness discovery.** "Skill discovery and consumption on external agents would be the next thing we need to focus on" — platform-team engineering lead, 2026-05-05. `atlanfs` is the early bet; it's experimental.
- **Bidirectional sync with the consumers of skills.** A Skill that gets re-edited by an agent (`agent-created skills` — "learns new patterns during conversation and saves them for reuse") needs a different audit posture than a hand-authored skill. Skill `createdBy` field is supposed to disambiguate but isn't yet a first-class filter in most surfaces.
- **Connector-synced skills.** `CONNECTOR_SYNC` enum value pending. Means skills sitting in Databricks/Snowflake stages can't yet be reflected as Atlan-managed assets cleanly.
- **Simulation/eval per skill version.** Ankit Jaggi's April 2026 thread laid out simulation gating as part of the vision — every skill testable against the defined agent before promotion. Not built yet.
- **The "registry vs. one-of-N-consumers" debate.** Whether the skill store is its own service Wisdom happens to consume, or whether the skill store is "what Wisdom exposes." Today it's the latter. The team wants the former. Migration path unclear.

**Net read:** the type system and the storage layer are real and shipped. The governance affordances (cert status, RBAC, lineage edges) exist on the entity but haven't yet been wired into product flows that depend on them. The runtime story works in Conversational Studio and is shaky everywhere else. External-harness consumption is via MCP for tool-grade access, or `atlanfs` for filesystem-grade access — neither is GA-quality for an enterprise consumer.

## Designing an agent against this

If you're scoping a starter agent and considering Atlan-managed skills:

- **Default to Atlan-managed skills only for the data-reach layer** — the procedural knowledge that depends on the customer's catalog (which tables, which columns, which rules). Keep prompt-level orchestration and runtime-specific knowledge in the harness.
- **Plan for progressive disclosure.** Assume the agent will fetch skills on demand via MCP, not eager-load them. If your harness doesn't support this natively (CrewAI, some LangGraph patterns), wire it via MCP tool calls — `search_skills` then `load_skill`.
- **Pin to specific versions for production agents.** Don't let `latest` float in production. Use `Agent.skillQualifiedNames` with a versioned qName.
- **Decide upfront where the source of truth lives.** If skills are authored in Git and pushed to Atlan, the Git repo is canonical and Atlan is a read replica with governance. If skills are authored in Atlan UI and Git is exported, Atlan is canonical. **Two-way sync is not a thing today** — pick one direction.
- **Don't put runtime-specific skills here.** A Claude Agent SDK skill that orchestrates Read/Edit/Bash, a Cortex skill that needs `tool_resources` in Snowflake YAML — those belong in the runtime, with Atlan as an *input* (the data the runtime skill is grounded in) rather than the *home*.
- **For the lineage story to pay off, fill in `skillReferencedAssets`.** Skills that don't declare what they reach for are skills the catalog can't reason about. Manually populating this on legacy skills is real work; automate it from the SQL/queries inside the skill body when possible.

The bet Atlan is making is that the **substrate-plus-procedure unified governance story** is worth the indirection. For customers where governance is genuinely non-negotiable and skill reuse across teams is real, the bet pays. For customers in prototype mode, or for skills tightly coupled to one agent's loop, the indirection is overhead.

It's a slot in the stack, not the stack.
