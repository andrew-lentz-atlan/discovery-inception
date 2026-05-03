# 00 — Vision, Design Principles, and Glossary

## The thesis

Software engineering has always been about translation. You take a fuzzy half-articulated process living in someone's head and translate it into something a machine can execute. The hard part was never syntax. The hard part was the translation itself: which steps a person takes that they never wrote down, which decisions are rule-based versus judgment-based, what state lives where, what error recovery actually looks like.

That skill has not gone away. It is the same skill in a new medium.

The new medium is natural language. Instead of writing functions and conditionals, we now write decompositions and prompts. Instead of teaching a compiler to follow a recipe, we teach a language model what a recipe even is. The fuzzy implicit knowledge an expert carries is what has to get translated. The model can read English. It cannot read minds. Someone has to do the work of pulling the implicit into the explicit.

The bottleneck of the next few years is not models. It is people who can sit with an expert, watch them work, and translate what they see into structured steps a model can execute. This project tests that thesis by building the tool that does the translation, end to end, for a customer's use case.

## The economic angle (why this matters now)

Frontier models keep getting smarter. Their harnesses keep getting bloated. Harnesses burn tokens because customers pay per token and don't notice. The real edge for the next few years is on the other side: people who can take a fuzzy human job, decompose it into actual steps (rule-based, judgment, lookup, generation), and run each step on the cheapest model that can do it well. Frontier model for the hard 10%, commodity for the easy 80%. That chain costs a fraction of "throw Opus at it" and often produces better outcomes because each step gets just enough context, no more.

## Design principles

These are the opinions we landed on. Reread them when a design decision feels ambiguous.

1. **Decompose first, fill second.** Bottom-up context (descriptions, READMEs, asset metadata, unstructured ingestion) only matters if there is a top-down decomposition to point it at. Without that, "more context" is "more bloat."
2. **Templatize the discovery, not the agent.** A churn-agent template is just another opinionated PaaS. A discovery template is reusable infrastructure. The methodology is the moat.
3. **Models are confidently wrong without flagging it.** Engineer humility into every stage. Default to "we still need to ask" rather than "we have enough."
4. **Imperfect intermediate output is a feature, not a bug.** Strawman move. Easier for a customer to react to a wrong artifact than to generate a right one. *But* once you commit to building an agent, context fidelity matters disproportionately because debugging an agent is harder than debugging a spec. So get to high quality on the slice the first agent depends on.
5. **MVA-scoped quality bar.** 10/10 on the slice the Minimum Viable Agent uses. Marked uncertainty on the rest. The full spec can keep growing as the agent's scope grows.
6. **Customer-as-user is the harder path, but the right one.** A customer-facing tool produces lower-quality output than an FDE-augmenting tool, but it scales discovery in ways an FDE alone never could. Bake BS detection into the system to compensate.
7. **Full trace is the introspection layer.** The harness gives us full visibility into every step an agent took. That's how we close the loop: discovery → build → trace reveals gaps → patch the discovery → rebuild.
8. **Don't go generic-first.** Generic discovery is everyone's discovery, which is no one's discovery. Tune prompts hard for one type of artifact at first. Generalize after.

## Glossary

Terms we coined or repurposed in this project. Use them consistently.

| Term | Meaning |
|---|---|
| **Discovery Inception agent** | The whole project. A multi-stage AI system that runs structured discovery for an agentic use case, producing a deployable spec. Adapted from ThoughtWorks Lean Inception. |
| **MVA** (Minimum Viable Agent) | The smallest version of an agent that proves the hypothesis behind the use case. The discovery system produces both a full spec and an MVA-scoped subset. |
| **CaaS** (Context as a Skill) | The pattern of taking customer-provided unstructured artifacts (runbooks, job descriptions, transcripts) and converting them into a structured "starter kit" skill the discovery agent can call. Customer's tribal knowledge made queryable. |
| **Bedrock** | First-principles termination of a "why" chain. The point where asking another "why" returns a tautology or domain truism. The stop condition for discovery on a given topic. |
| **Why-prober** | A sub-agent that takes any captured statement and tries to generate the next meaningful "why" question. Used to decide whether bedrock has been hit. |
| **Gap finder** | A sub-agent that reads the captured spec and identifies vagueness, contradictions, untested assertions, and templatey answers. Biased hard toward "we still need to ask." |
| **BS meter** | The combined system of in-conversation probes ("how would you know if this were wrong?") and output uncertainty markers (tagging claims that weren't probed to bedrock). |
| **Strawman provocation** | Showing the customer a deliberately imperfect intermediate artifact to surface implicit knowledge. "No, that's wrong because XYZ" extracts more than open-ended questions. |
| **Trace as black-box piercer** | The principle that full per-step trace data lets us debug at the *product* level ("which decision went wrong and what context drove it") even if we can't debug at the *model* level ("why did Gemma sample that token"). |
| **Closed loop** | discovery system produces context repo → harness consumes it → trace from harness reveals gaps → feedback patches the discovery output. |
| **FDE** | Forward Deployed Engineer, in the Palantir sense. The role whose primary job is process discovery, not just process configuration. The shape this project tries to emulate or augment. |
| **Lean Inception** | The ThoughtWorks methodology this project is loosely modeled on. Structured discovery exercises (Vision Board, Is/Is Not, Lean Personas, User Journey, Sequencer, MVP Canvas) that produce an MVP spec. |

## What this project is not

- **Not a generic agent-building platform.** We're not competing with LangGraph, DSPy, CrewAI, or Pi at that layer.
- **Not an attempt to replace the FDE role.** The honest version is FDE-with-this-tool > FDE-without-this-tool > customer-with-this-tool > customer-alone.
- **Not a frontier-model demo.** The whole point is that decomposed pipelines of small models often beat one big-model call.
- **Not Atlan-specific in design**, even though it sits inside the Atlan thesis (structured context layer, but for processes instead of assets).
