# Step 5e: Generate LLM-as-Judge Harness

You are part of the inception agent's `scaffold_writer` sub-pipeline. You produce the `eval/judge.py` source — the LLM-as-judge harness the builder uses to score the agent's outputs across multiple scoring dimensions.

The pattern is anchored on a published reference implementation that documented its evaluation methodology (see https://github.com/bladata1990/pg-brand-analyst-agent for the canonical 5-dimension diagnostic-agent template, scoring 97/100). The canonical 5 dimensions for diagnostic agents:

1. **Quantitative accuracy** — numerical claims match ground truth within tolerance
2. **Taxonomy classification** — correct category assignment against the workload's classification framework
3. **Hallucination check** — claims not supported by underlying data
4. **Reasoning quality** — logical chain from data to conclusion
5. **Actionability** — recommendations are specific and implementable

For different workloads, the dimensions adapt. A conversational discovery agent might score "question quality" and "fact coverage" instead of "taxonomy classification." A code-generation agent might score "syntactic correctness" and "test pass rate." Pick the dimensions that match the actual workload.

## What you receive

1. **Workload classification** — tells you what to score for
2. **Proposed skills** — tells you which intermediate outputs are testable
3. **Selected architecture + runtime** — tells you what API to call for the judge
4. **EvalSeed (the question set)** — tells you what's already being tested

## Your job

Produce a complete `eval/judge.py` Python file that:

1. **Imports the right libraries** for the judging LLM. For Claude-flavored agents, use the `anthropic` SDK with `claude-opus-4-7` as the judging model (independent of the agent's model is good practice — reduces self-evaluation bias).
2. **Defines N scoring dimensions** adapted to the workload. Use the canonical 5 as the starting template for diagnostic agents; adapt for other workloads.
3. **Defines a `ScoreReport` dataclass / Pydantic model** with one field per dimension (each 0-20, total 0-100).
4. **Implements a `Judge` class** with:
   - `__init__` taking optional judge_model + system prompt config
   - `score(question, agent_output, ground_truth=None)` method that scores one (question, agent_output) tuple
   - One private method per dimension: `_score_<dimension_name>()`, each with a TODO marker for the dimension-specific scoring prompt
   - An aggregate method that combines all dimension scores
5. **Has a `main()` entry** that:
   - Loads `eval/questions.json`
   - Loads agent outputs (TODO: from where? builder decides)
   - Loads ground truth (TODO: builder provides)
   - Iterates through questions, scoring each
   - Outputs a markdown report + a JSON detailed log
6. **Includes a clear comment block at the top** explaining the methodology and citing Bala's pattern.

## Hard rules

- **Use the customer's domain vocabulary verbatim** from the RoleContext. Whatever taxonomy / framework / business-view names the customer uses, the scoring prompt should reference them — don't substitute generic equivalents.
- **TODO markers must be concrete.** `# TODO: implement _score_quantitative_accuracy — compare agent_output's numerical claims against ground_truth using a tolerance threshold; deduct 5 points per significant discrepancy` beats `# TODO: implement`.
- **Each dimension has a 0-20 scoring scale**, total 0-100. Match the canonical reference pattern.
- **The judge model should be independent of the agent's model.** If the agent is Claude Opus 4.7, the judge should also be Opus or a different family — never reuse the same instance for self-evaluation.
- **Include a section explaining where ground truth comes from.** For diagnostic agents, this is typically synthetic data with embedded ground-truth signals (e.g., an embedded step-change at a known time index). For other workloads, this might be hand-curated reference answers.
- **No emojis. Production code style.** Type hints throughout. Docstrings on the public class + score method.

## Output

Respond with valid JSON. No prose outside the JSON.

```json
{
  "judge_py": "<full Python source as a single string>",
  "dimensions": ["<dimension name>", ...],
  "judging_model_recommended": "<model spec, e.g., 'claude-opus-4-7'>"
}
```

### CRITICAL: JSON-string escaping rules for `judge_py`

`judge_py` is a JSON string. Python source frequently contains characters that have special meaning in JSON. **All of these MUST be escaped properly**, or the JSON parse will fail and the whole step fails:

- **Triple-quoted docstrings:** Python uses `"""..."""` for docstrings. Inside a JSON string, every `"` MUST be escaped. The model frequently forgets this for the OPENING `"""` and the JSON parse fails at line 2 col 22 every time. **Solution: do NOT emit Python docstrings using `"""` syntax. Use single-line `#` comments instead.** Comments render the same way for human readers and parse reliably. So write:
  ```python
  # LLM-as-judge harness for <agent_name>.
  # Methodology: 5 dimensions, 0-20 each, total 0-100.
  ```
  NOT:
  ```python
  """LLM-as-judge harness for <agent_name>.
  Methodology: 5 dimensions, 0-20 each, total 0-100.
  """
  ```
- **Newlines:** Always `\n`, never raw line breaks.
- **Internal double-quotes** (e.g., dict keys, string literals): always `\"`, never raw `"`.
- **Backslashes** (e.g., regex patterns, escape sequences): always `\\`, never raw `\`.

**Self-check before you emit:** does every `"` and `\` inside `judge_py` have a `\` in front of it? If you used `"""` anywhere, the JSON will break — switch those constructs to `#` comments.

## Inputs

### Workload classification (step 1)

{WORKLOAD_CLASSIFICATION_JSON}

### Proposed skills (step 2)

{SKILL_PROPOSAL_JSON}

### Selected runtime (step 4)

{RUNTIME_PROPOSAL_JSON}

### Eval seed (step 5d)

{EVAL_SEED_JSON}

### RoleContext (priors) — for domain vocabulary in scoring prompts

{ROLE_CONTEXT_JSON}
