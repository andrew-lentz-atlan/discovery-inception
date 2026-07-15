---
title: File-Based Agent Memory: Patterns, Limits, and the Storage-Search Split
category: skill-design
status: draft
last_updated: 2026-07-15
source_findings: []
source_external:
  - Claude Code auto-memory (Anthropic official docs, Feb 2026)
  - Anthropic memory tool (Messages API, GA)
  - Letta Context Repositories (blog, Feb 12 2026)
  - GitHub Agentic Workflows (official reference docs)
  - Cursor semantic-search A/B (blog, 2025)
  - mem0 LoCoMo benchmarks (vendor, Jul 2026)
  - Manus file-system-as-context (Yichao Ji, Medium, Jul 2025)
  - Anthropic context engineering (Sep 29 2025)
  - AgentLAB memory poisoning (arXiv 2602.16901)
  - Agent Skills spec (agentskills.io, Dec 18 2025)
applies_when:
  workloads:
    - multi-session-agent-with-audit-trail
    - co-pilot-with-human-review-loop
    - multi-agent-fleet-with-shared-memory
    - skill-consolidation-and-procedure-capture
  constraints:
    - memory-must-be-human-auditable
    - model-upgrade-free-no-reindexing
    - compliance-requires-version-history
    - memory-fits-in-context-under-200-lines
    - git-versioning-available
contradicts:
  - decision-guides/memory-architecture-selection
related:
  - decision-guides/does-this-agent-need-memory
  - decision-guides/memory-architecture-selection
  - decision-guides/subagent-vs-skill-tradeoffs
  - skill-design/memory-operations
  - skill-design/atlan-context-repos
  - anti-patterns/over-decomposition
snapshot_date: 2026-07-15
source_hash: 7b587dc4d4ae1ccf
---

# File-Based Agent Memory: Patterns, Limits, and the Storage-Search Split

File-based, agent-curated memory—markdown files the agent reads, writes, and maintains—has become the default persistent memory substrate for agent harnesses and co-pilots as of mid-2026, displacing opaque vector stores to the role of derived search indexes. This pattern surveys eight concrete implementations (Claude Code, Anthropic memory tool, Letta, OpenClaw, Manus, OpenAI Codex, Cursor, GitHub Agentic Workflows) and establishes that the strongest synthesis separates storage (files, versioned in git) from search (embeddings/BM25 as rebuildable indexes). Skills—SKILL.md-style capability documents—are best understood as crystallized procedural memory, graduating from episodic notes to consolidated procedures. The pattern holds at agent-harness scale with real limits: always-loaded files tax every session, retrieval over large file sets requires hybrid semantic+grep search, and concurrent writes remain unsolved without git coordination.

## The N, summarized

| # | Item | What it is | The one gotcha that bites |
|---|---|---|---|
| 1 | Claude Code (CLAUDE.md + auto-memory) | Hierarchy of human-authored CLAUDE.md (managed policy → ~/.claude/CLAUDE.md → project → CLAUDE.local.md) plus agent-curated auto-memory dir with MEMORY.md index (200 lines/25KB loaded per session) and topic files on demand; path-scoped rules via .claude/rules/*.md with glob frontmatter. | Always-loaded index taxes every session; machine-local auto-memory not git-backed by default; adherence degrades past ~200 lines of CLAUDE.md. |
| 2 | Anthropic memory tool (Messages API) | Client-side file operations (view/create/str_replace/insert/delete/rename) against storage you control; auto-injects 'ALWAYS VIEW YOUR MEMORY DIRECTORY BEFORE DOING ANYTHING ELSE' protocol; six file commands, ZDR-eligible. | Path traversal validation is your responsibility; you own size caps, expiration, and sensitive-data stripping; it's a contract for six commands, not a full memory system. |
| 3 | Letta Code (Context Repositories) | Markdown files with frontmatter descriptions in a MemFS; agent reorganizes hierarchy; every memory change is a git commit with explanatory message; subagents get isolated worktrees and merge back; defragmentation skill for cleanup. | Git resolves multi-writer problem; merge conflicts in prose are uglier than in code; nobody has published recall benchmarks for git-memory systems—wins claimed are operational, not accuracy. |
| 4 | OpenClaw (SOUL.md, USER.md, MEMORY.md, daily logs) | Long-term MEMORY.md plus daily logs (memory/YYYY-MM-DD.md); 'dreaming' background consolidation promotes daily-note items into MEMORY.md; community practice is to git the workspace. | Consolidation is lossy by design; stale facts and relative dates rot; dreaming pass must be human-reviewable to avoid self-inflicted amnesia. |
| 5 | Manus (file system as context) | File system as 'ultimate, unlimited context'; agent reads/writes files on demand; restorable compression (keep URL, drop page content) over lossy summarization. | Session sandbox (no persistent versioning); compression strategy is agent-managed; no published recall benchmarks. |
| 6 | OpenAI Codex / AGENTS.md (open standard) | AGENTS.md at repo root, nearest-file-wins hierarchy in monorepos, AGENTS.override.md for local overrides; open standard under Agentic AI Foundation (Linux Foundation); interops with Claude Code via @AGENTS.md import or symlink. | Conflicting rules across files produce arbitrary behavior; it's context, not enforcement—Anthropic explicitly says use hooks for hard guarantees. |
| 7 | Cursor (AGENTS.md + .cursor/rules/*.mdc) | AGENTS.md plus .cursor/rules/*.mdc with glob-scoped YAML frontmatter; human-authored; repo git versioning; semantic search over codebases improves agent QA accuracy ~12.5% avg. | Hybrid semantic+grep is optimal; pure grep misses paraphrase; semantic search adds new ops concern (index freshness). |
| 8 | GitHub Agentic Workflows (repo-memory branch) | Memory committed to a dedicated git branch; GPG-signed commits; enforced caps (100KB/100-file/10KB-patch default); concurrent pushes replayed on latest remote state with 'your changes win' conflict resolution. | 'Your changes win' auto-resolution silently drops the other writer's memory on conflict; commit noise needs its own hygiene; no published recall benchmarks. |
| 9 | mem0 / Zep (managed extraction pipeline, contrast) | Managed extraction pipeline → vector/graph store; pipeline-curated (LLM extraction), not agent-curated; LoCoMo 92.5 / LongMemEval 94.4 at ~6.9K tokens/query; opaque API-level versioning. | Wins published recall benchmarks at conversational scale; best for high-cardinality user-preference memory at consumer scale; not auditable by construction; vendor lock-in on embeddings. |
| 10 | Storage/search separation (P7 synthesis) | Files (markdown + YAML frontmatter) as canonical, versioned storage; vector/BM25/graph indexes as disposable, rebuildable derivatives; swap embedding models by re-indexing, never by migrating data. | Index freshness becomes a new ops concern; you've reintroduced the vector store, just demoted; don't let the index become the thing you back up. |
| 11 | Skills as crystallized procedural memory (SKILL.md) | Directory + SKILL.md (YAML frontmatter: name, description) + optional scripts/references; 3-tier progressive disclosure (metadata always in context → SKILL.md body on activation → referenced files on demand); episodic experience → consolidated procedure. | Description quality gates everything—a skill that doesn't trigger is dead memory; skills are static between edits and don't self-update from failures unless you build that loop; too many skills recreate the discovery problem. |

## The few that actually matter for most decisions

Three patterns dominate: **Claude Code auto-memory** (default for Anthropic-based harnesses, machine-local, simplest onboarding), **storage/search separation** (the architectural synthesis that survives model upgrades and multi-agent fleets), and **skills as crystallized procedures** (the graduation from episodic notes to reusable, discoverable capability). The rest are either vendor-specific implementations of these three or managed alternatives (mem0/Zep) that trade auditability for published recall benchmarks at consumer scale.

## Decision tree (when to pick which)

1. **Do you need published recall benchmarks at conversational scale (millions of users, thousands of facts per user)?** → Use mem0 or Zep. File-based systems don't publish comparable numbers; managed extraction wins here.

2. **Must memory be human-auditable and reviewable via git diff?** → Use file-based storage. Managed systems are opaque by construction.

3. **Do you have multiple concurrent writers (multi-agent fleet, subagents)?** → Use Letta Context Repositories (git commits per change, subagent worktrees) or GitHub Agentic Workflows (signed commits, replay-on-conflict). Raw files have no write coordination.

4. **Is memory small enough to fit in context (target <200 lines of always-loaded index)?** → Use Claude Code auto-memory or Anthropic memory tool. Both assume you're managing size discipline.

5. **Do you need to swap embedding models without re-indexing or migrating data?** → Use storage/search separation: files as canonical storage, vector/BM25 as rebuildable indexes. This is the only pattern that survives model upgrades free.

6. **Are you consolidating multi-step procedures or tool-specific workflows into reusable skills?** → Use SKILL.md pattern: YAML frontmatter (name, description) + body + optional scripts. Progressive disclosure (metadata in context, body on activation, scripts on demand) keeps retrieval cheap.

## Cross-cutting observation

The strongest file-based systems all separate storage from search. Claude Code, Letta, GitHub Agentic Workflows, and Cursor all treat files as canonical and indexes (or semantic search) as disposable derivatives. This separation is what makes model upgrades free—you never re-embed or migrate data, you just rebuild the index. Conversely, systems that conflate storage and search (raw MEMORY.md without a separate index, or opaque vector stores) force you to choose between auditability and recall accuracy. The managed vendors (mem0, Zep) win on recall benchmarks at conversational scale but lose on auditability; file-based systems win on auditability but require you to build or maintain the search layer yourself.

Skills emerge as the natural graduation from episodic memory. Early implementations (OpenClaw daily logs, Claude Code topic files) are episodic—one-off notes. Mature systems (Letta defragmentation, SKILL.md pattern) consolidate episodic experience into crystallized procedures: a SKILL.md with frontmatter (name, description, trigger conditions) that the agent can discover, activate, and refine. The key insight is 3-tier progressive disclosure: metadata always in context (so the agent knows the skill exists), body on activation (so the agent can read the procedure), referenced files on demand (so the agent doesn't load the entire skill library on every session).

## When to revisit

| Trigger | Action |
|---|---|
| Always-loaded index exceeds 200 lines or 25KB | Split into topic files; move episodic notes to daily logs; consolidate stale facts into skills. |
| Recall accuracy drops below acceptable threshold | Measure: run a test suite of queries against your memory and count hits. If <80%, add semantic search (hybrid semantic+grep) or switch to managed extraction (mem0/Zep). |
| Merge conflicts in memory files become frequent | Implement git-based coordination (Letta worktrees, GitHub Agentic Workflows replay) or switch to managed system. |
| Stale facts and contradictions accumulate | Run a consolidation pass (OpenClaw dreaming, Letta defragmentation). Make it human-reviewable; consolidation is lossy by design. |
| Model upgrade requires re-embedding or index migration | You've conflated storage and search. Refactor to storage/search separation: files as canonical, indexes as disposable. |
| Skills don't trigger or are discovered too late | Audit SKILL.md descriptions and trigger conditions. Description quality gates discovery; if a skill doesn't trigger, it's dead memory. |
| Concurrent writes cause silent data loss | Implement git-based conflict resolution (signed commits, replay-on-conflict) or switch to managed system. 'Your changes win' auto-resolution is a footgun. |
| Index freshness becomes a bottleneck | You've reintroduced the vector store as a derived layer. Don't let the index become the thing you back up; rebuild it on demand or on a schedule. |

## Key gotchas

- **Always-loaded index is the pressure point.** Everything in CLAUDE.md or MEMORY.md taxes every future session; Claude Code hard-caps MEMORY.md at 200 lines/25KB and warns adherence drops past ~200 lines of CLAUDE.md.

- **Rot is the default.** Stale facts, contradictions, and relative dates accumulate; every mature file-memory system has shipped a consolidation mechanism (Letta defragmentation, OpenClaw dreaming), which is evidence of the failure mode.

- **Conflicting rules across files produce arbitrary behavior.** Nearest-file-wins hierarchies (AGENTS.md, CLAUDE.md) can collide; imports still load at launch (organization ≠ context savings).

- **Machine-local, not synced by default.** Claude Code auto-memory is not git-backed by default and does not sync across machines or cloud.

- **Merge conflicts in prose are silent data loss.** GitHub Agentic Workflows uses 'your changes win' auto-resolution on conflict, silently dropping the other writer's memory.

- **Description quality gates skill discovery.** A skill that doesn't trigger is dead memory; skills are static between edits and don't self-update from failures unless you build that loop.

- **Consolidation is lossy by design.** An over-aggressive consolidation pass is self-inflicted amnesia with a clean diff; run it where a human can review the diff.

- **Index freshness becomes a new ops concern.** Storage/search separation reintroduces the vector store as a derived layer; don't let the index become the thing you back up.

- **Path traversal is your problem.** Client-side memory tools (Anthropic memory tool) require canonical-path validation; `/memories/../../secrets.env` is a real attack surface.

- **Indirect prompt injection can write persistent facts.** Memory poisoning (MINJA, MemoryGraft, AgentLAB) can survive sessions; files make the attack auditable but not impossible.

## Empirical anchor

Clause Code auto-memory landed ~Feb 2026 with per-repo dir at `~/.claude/projects/<project>/memory/`, MEMORY.md index loaded first 200 lines/25KB, topic files on demand, on by default, plain-markdown auditable. Anthropic memory tool (Messages API) is GA with six file commands and auto-injected 'assume interruption' protocol. Letta Context Repositories (Feb 12, 2026) git-commits every memory change with explanatory messages and ships subagent worktrees for concurrent memory writes plus a defragmentation skill for organizational rot. GitHub Agentic Workflows repo-memory uses git-branch memory with 100KB/100-file/10KB-patch default caps, signed commits, and replay-on-conflict. Cursor's semantic-search A/B showed +12.5% avg agent QA accuracy and up to 2.6% code-retention gain on large codebases; hybrid semantic+grep is optimal. mem0 LoCoMo scores 92.5 / LongMemEval 94.4 at ~6.9K tokens/query; no file-based system publishes comparable scores at conversational scale. Agent Skills spec opened Dec 18, 2025 at agentskills.io with OpenAI + Microsoft support within ~48h; ~32 tools by Mar 2026, ~40 by Jun 2026. AgentLAB (arXiv 2602.16901) demonstrates memory poisoning via indirect prompt injection; MINJA and MemoryGraft show persistent attack surface. Manus (Jul 2025) frames the file system as 'ultimate, unlimited context' with restorable compression over lossy summarization. Anthropic context engineering (Sep 29, 2025) notes that note-taking is 'persistent memory with minimal overhead' and just-in-time retrieval beats exhaustive pre-retrieval.

Origin: Anthropic official docs (Claude Code, memory tool), Letta blog (Context Repositories), GitHub official reference docs (Agentic Workflows), Cursor blog (semantic search), mem0 vendor benchmarks, Yichao Ji Medium post (Manus), Anthropic engineering post (context engineering), arXiv 2602.16901 (AgentLAB), agentskills.io (Agent Skills spec).
