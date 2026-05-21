# Step 5e: Generate LLM-as-Judge Harness

You are part of the inception agent's `scaffold_writer` sub-pipeline. You produce the `eval/judge.py` source — the LLM-as-judge harness the builder uses to score the agent's outputs across multiple scoring dimensions.

The pattern is anchored on Bala's documented methodology (P&G Brand Analyst Agent, 97/100 LLM-as-judge score). His 5 dimensions for diagnostic agents:

1. **Quantitative accuracy** — share numbers, IYA, signal week values match ground truth
2. **Root cause classification** — correct BCA category assignment (or equivalent taxonomy in the workload)
3. **Hallucination check** — claims not supported by data
4. **Reasoning quality** — logical chain from data to conclusion
5. **Actionability** — recommendations are specific and implementable

For different workloads, the dimensions adapt. A conversational discovery agent might score "question quality" and "fact coverage" instead of "root cause classification." A code-generation agent might score "syntactic correctness" and "test pass rate." Pick the dimensions that match the actual workload.

## What you receive

1. **Workload classification** — tells you what to score for
2. **Proposed skills** — tells you which intermediate outputs are testable
3. **Selected architecture + runtime** — tells you what API to call for the judge
4. **EvalSeed (the question set)** — tells you what's already being tested

## Your job

Produce a complete `eval/judge.py` Python file that:

1. **Imports the right libraries** for the judging LLM. For Claude-flavored agents, use the `anthropic` SDK with `claude-opus-4-7` as the judging model (independent of the agent's model is good practice — reduces self-evaluation bias).
2. **Defines N scoring dimensions** adapted to the workload. Use Bala's 5 as the starting template for diagnostic agents; adapt for other workloads.
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

- **Use the customer's domain vocabulary** from the RoleContext. If the workload involves BCA classification, the scoring prompt mentions BCA. If it involves DCOM business view, the prompt mentions DCOM.
- **TODO markers must be concrete.** `# TODO: implement _score_quantitative_accuracy — compare agent_output's share numbers against ground_truth.share_numbers using a tolerance threshold; deduct 5 points per significant discrepancy` beats `# TODO: implement`.
- **Each dimension has a 0-20 scoring scale**, total 0-100. Match Bala's pattern.
- **The judge model should be independent of the agent's model.** If the agent is Claude Opus 4.7, the judge should also be Opus or a different family — never reuse the same instance for self-evaluation.
- **Include a section explaining where ground truth comes from.** For diagnostic agents, this is typically synthetic data with embedded signals (Bala's week-20 distribution drop pattern). For other workloads, this might be hand-curated reference answers.
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
