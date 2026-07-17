---
title: "UPDATE — memory-operations: storability gate ahead of the write policy"
update_target: skill-design/memory-operations.md
category: skill-design
status: draft
last_updated: 2026-07-16
source_external:
  - Anthropic — "Effective context engineering for AI agents" (https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents)
  - Anthropic — "Memory tool" docs (https://platform.claude.com/docs/en/agents-and-tools/tool-use/memory-tool)
  - Mem0 — "Platform FAQs" (extraction/classification criteria) (https://docs.mem0.ai/platform/faqs)
  - Sumers et al. — "Cognitive Architectures for Language Agents (CoALA)" (arXiv:2309.02427)
  - "How Memory Management Impacts LLM Agents: An Empirical Study of Experience-Following Behavior" (ACL 2026, arXiv:2505.16067)
  - Redis — "AI agent context engine FAQ: RAG, memory & caching" (https://redis.io/blog/faq-real-time-context-engine-agent-memory-and-retrieval/)
---

# Proposed update to `skill-design/memory-operations.md`

## What changes and why

The current write policy (§1 "Write — what to persist, and when") gates on **salience** — "salient facts, decisions, outcomes, corrections, stable preferences, new entities" — and on **timing** (every-turn / reflection / event). It mentions the third axis only in passing: "anything reconstructable from a tool on demand" appears as one clause in the noise list. Salience and **stability/ownership** are independent axes: a salient-but-volatile fact ("table X's current owner") passes the existing gate and should not, because a queryable system of record owns it. The result is the shadow-copy failure (`anti-patterns/memory-as-shadow-copy.md`): staleness machinery gets built to defend copies that should never have been written.

## Insertion 1 — new subsection at the top of "### 1. Write — what to persist, and when"

> **The storability gate — before salience, ownership.** Three questions, in order, applied to each candidate fact *category* (not each individual write):
>
> 1. **Does a queryable system of record own this?** → Do not persist the value. Store the pointer (GUID, URL, saved query) and fetch at use time. A memory reproducible by `GET /record/{id}` is a shadow copy (see `anti-patterns/memory-as-shadow-copy.md`). Exception: a deliberate point-in-time snapshot stored *as a conclusion* ("schema as of the 2026-03-14 decision") — that is a fact about a moment, not a mirror of current state.
> 2. **Is it volatile relative to session frequency?** → It is a tool call, not a memory — even without a clean system of record. A fact that changes faster than the sessions that would consume it is stale on arrival. If it must be kept locally for latency, it is an **explicit cache** — declared TTL/invalidation, named owner, bypass for fast-changing values — not a memory entry.
> 3. **Is it stable AND either expensive to re-derive or underivable in principle?** → Persist. This is memory's comparative advantage: conclusions, decisions and their rationale, corrections, preferences, learned procedure. CoALA's framing — a memory write is a *learning* action, tool use is *environment interaction* — is the theoretical version of this gate; mem0's extraction criteria (personal/experiential in; definitional/general knowledge rejected) are a shipping-product version of it.
>
> Only facts that pass question 3 proceed to the salience test and timing policy below. Empirical stakes: stored content steers future behavior — retrieved memories act as demonstrations, and errors in them propagate (experience-following, arXiv:2505.16067) — so the write gate is a policy decision, not housekeeping.

## Insertion 2 — amend the closing inception hook

The entry's minimal valid memory section currently reads: *kind → tool/rung → write policy → retrieval policy → eviction/consolidation policy → conflict-resolution choice → eval hook.* Amend the write-policy element to require the gate:

> *…→ write policy (including storability reasoning: which fact categories are persisted vs. referenced-by-pointer vs. declared-cache, and why) → …*

A memory section whose write policy shows no storability reasoning is flagged incomplete for the same reason an un-operated store is: it predictably ships the shadow-copy failure.

## Consistency notes

- The existing noise-list clause "anything reconstructable from a tool on demand" becomes a cross-reference to the gate rather than the only trace of the idea.
- No change to timing policies, retrieval, eviction, consolidation, or conflict resolution.
- Cross-references assume promotion of the co-proposed `anti-patterns/memory-as-shadow-copy` and `decision-guides/memory-placement-spectrum` entries.
