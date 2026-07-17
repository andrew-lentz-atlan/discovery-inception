---
title: "UPDATE — does-this-agent-need-memory: promote the host-tool check to a numbered question"
update_target: decision-guides/does-this-agent-need-memory.md
category: decision-guides
status: draft
last_updated: 2026-07-16
source_external:
  - Anthropic — "Effective context engineering for AI agents" (https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents)
  - Redis — "AI agent context engine FAQ: RAG, memory & caching" (https://redis.io/blog/faq-real-time-context-engine-agent-memory-and-retrieval/)
---

# Proposed update to `decision-guides/does-this-agent-need-memory.md`

## What changes and why

The decision procedure (Q1–Q6) routes at the agent level and never forces the question that separates a memory store from a live lookup. The idea exists only as the Q2 parenthetical "(Check whether the host tool already holds it before building a store)" and the co-pilot boundary case. Promoting it to a numbered question makes the routing explicit and gives downstream entries a stable anchor.

## Change — insert as a new question after Q2, renumbering Q3–Q6

> **Q2b. For each fact the agent needs: does a queryable system of record already hold it?**
> - Yes → **dynamic reference, not memory.** The design names the source and the tool that queries it; memory stores at most the pointer (GUID, URL, saved query). This is not a memory kind — it is the decision *not* to build one for that fact.
> - No, and the fact is stable / expensive to re-derive / underivable (preferences, corrections, decision rationale, experience) → continue; a memory kind from Q2–Q5 applies.

## Change — one line in "Hard rule for inception"

Add to rule 2 (each memory kind gets a verdict): *a verdict of "referenced — lives in <system>, queried via <tool>" is a valid and complete answer for a fact category, equivalent in status to "unneeded because X."*

## Consistency notes

- Aligns the entry with the storability gate proposed for `skill-design/memory-operations.md` (fact-level version of the same test) and with `decision-guides/memory-placement-spectrum` (placement of facts that do warrant persistence).
- The existing Q2 parenthetical and co-pilot boundary case become illustrations of Q2b rather than the only trace of the idea.
