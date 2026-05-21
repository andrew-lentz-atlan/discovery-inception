# Step 5f: Architecture Diagram

You are producing a visual + narrative summary of the agent design that lets a builder understand the agent's shape in 30 seconds without reading orchestrator.py + N SKILL.md files.

## Inputs you have

- Workload classification (interaction shape, decision complexity, etc.)
- Skill proposal (N skills with names + types + purposes + decisions owned)
- Architecture proposal (selected pattern slug: single-agent-react / chained-pipeline / inner-pipeline-skill / adversarial-decomposition / etc.)
- Runtime proposal (selected runtime + model)

## Output: a JSON object with three fields

```json
{
  "summary_md": "<2-paragraph markdown framing>",
  "skill_graph_mermaid": "<mermaid source — NO fences>",
  "execution_flow_mermaid": "<mermaid source — NO fences>"
}
```

Each is described below. **Do not wrap the mermaid sources in ` ```mermaid ... ``` ` fences — the renderer adds those when writing to disk.**

## `summary_md` (2 paragraphs)

Paragraph 1: what the agent does, from the user's perspective. Use the customer's vocabulary from the spec. Reference the workload's interaction shape (e.g., *"query-response, judgment-heavy"*) and the selected architecture pattern. One sentence on the runtime.

Paragraph 2: what one turn looks like at a high level. Reference the key skills in execution order. Surface the load-bearing judgment moment — usually one of the LLM or inner-pipeline skills — and explain why that's where the agent's quality lives.

Total: 4–8 sentences. No bullet lists. Should read like a paragraph you'd write under the title of the diagrams.

## `skill_graph_mermaid` (flowchart)

Mermaid `flowchart TD` showing the skill graph.

**Node format:** `skill_name["<skill_name><br/>(skill_type)"]`

Use these consistent tags after the `<br/>`:
- `(LLM)` — for skills with body shape `llm_call`
- `(inner-pipeline)` — for `inner_pipeline`
- `(deterministic)` — for `deterministic`

**Edges:** show typical invocation order or data dependency. Adapt to the architecture:

- **single-agent-react**: a center "orchestrator" node connects to every skill as a tool. Show as `orchestrator{{Orchestrator<br/>(ReAct loop)}}` (using `{{...}}` for the hexagon shape that marks the loop). Edges go orchestrator → skill (with `-->|invokes|` if you want labels).
- **chained-pipeline**: linear `A --> B --> C --> D`. Each skill feeds the next.
- **inner-pipeline-skill**: orchestrator → one big skill (with its own inner steps shown as a subgraph if useful).
- **adversarial-decomposition**: producer skill → critic skill, with a loopback edge if the critic gates retry.

Keep node count manageable. If you have 6 skills, don't add 12 helper nodes; keep the graph readable.

## `execution_flow_mermaid` (sequence diagram)

Mermaid `sequenceDiagram` showing one user turn end-to-end.

Participants (in order):
- `User`
- `Orchestrator`
- One participant per skill (use the skill name as the participant alias)

Show:
- The user's input arriving at the Orchestrator
- The Orchestrator calling each skill in the typical order
- Each skill's reply
- Any conditional / escalation flow (use `alt ... else ... end` blocks)
- The final response from Orchestrator back to User

Match the architecture pattern's runtime behavior:
- **single-agent-react**: orchestrator decides which skill to call next; conditional invocations are normal. Show the typical happy path.
- **chained-pipeline**: every skill runs every turn. Show all of them in sequence.
- **adversarial-decomposition**: show producer call, then critic call, then either pass or loopback.

Keep it readable — 8–15 lines is typical. Don't try to show every edge case.

## Architecture-specific guidance

The selected architecture is **{SELECTED_ARCHITECTURE_SLUG}**.

Based on which one it is, the shape of both diagrams should match the canonical patterns described above. The shape is informed by the pattern; the specifics (skill names, judgment moments, escalation triggers) come from the inputs.

## Inputs

### Workload classification
```json
{WORKLOAD_JSON}
```

### Skill proposal
```json
{SKILLS_JSON}
```

### Architecture proposal
```json
{ARCHITECTURE_JSON}
```

### Runtime proposal
```json
{RUNTIME_JSON}
```

## Final reminder

- **No mermaid fences around the diagram source strings.** The disk renderer adds them.
- **Use double quotes inside JSON string values, escaped if needed** (`\"`). Mermaid syntax doesn't require quoting node labels but a few characters (e.g., parens inside labels) sometimes need wrapping in `[\"...\"]`.
- **Validate that every Mermaid arrow is well-formed** (`-->`, `--`, `->>`, `-->>`). Bad arrows render as text.
- Self-check that every skill in the skill_proposal appears at least once in `skill_graph_mermaid`. Missing a skill makes the diagram a lie.
