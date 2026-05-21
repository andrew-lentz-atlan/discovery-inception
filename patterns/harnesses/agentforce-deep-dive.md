---
title: Agentforce — Builder's Deep Dive
category: harnesses
status: validated
last_updated: 2026-05-22
source_findings: []
source_external:
  - Internal Atlan research doc — "Agentforce — Builder's Deep Dive" (2026-05-21, owner Himanshu Sikaria)
applies_when:
  workloads: [salesforce-resident-agents, crm-grounded-conversational-agents, enterprise-governed-agents]
  constraints: [team-on-salesforce, enterprise-governance-non-negotiable, agent-acts-on-salesforce-data]
contradicts: []
related: [harnesses/landscape-2026-may, architectures/single-agent-react, anti-patterns/definitions-without-context]
snapshot_date: 2026-05-22
---

# Agentforce — Builder's Deep Dive

The first per-framework deep-dive in `patterns/harnesses/`. Salesforce Agentforce (now the **Agentforce 360 Platform**) is fundamentally different from the other harnesses in `landscape-2026-may.md`: there's no `pip install`, no agent loop you write, no model you pick directly. It's a vertically-integrated agent product configured through Agent Builder and extended through Apex, Flow, and Prompt Templates. For a class of Salesforce-resident problems, that opinion is exactly right and saves years of work; outside that footprint, one of the other five-now-six headline frameworks fits better.

This entry exists because the landscape survey can't carry the depth needed to actually decide for or against Agentforce on a specific use case. Apex specifics, the 15/15/20 wall, topic-classification failure modes, the Trust Layer's non-optional posture — these matter, and they don't fit a row in a comparison table.

## The five primitives (Salesforce's framing)

Every Agentforce agent is described by five attributes:

| Primitive | What it is |
|---|---|
| **Role** | What the agent does — sales SDR, service rep, IT desk, etc. |
| **Data** | What it knows. Grounded via Data Cloud, RAG over Salesforce objects + file libraries + external sources via MCP. |
| **Actions** | What it can do. Invocable Apex methods, Flows, Prompt Templates, standard Salesforce actions, MCP tools. |
| **Guardrails** | What it *can't* do. Topic scope, instructions, Einstein Trust Layer policies. |
| **Channel** | Where it operates. Salesforce UI, Slack, WhatsApp, voice, web embed, API. |

Underneath: **Topics** (renamed to **subagents** in the April 2026 docs — same functionality) group related actions + instructions for a particular intent. An agent is a coordinator over topics; each topic has 1–15 actions.

## The Atlas Reasoning Engine

Atlas is the loop. Not a general-purpose LLM — its job is **classify intent → pick a topic → plan actions → execute → reflect → respond** within the bounded world of an agent's configured capabilities.

| Component | Job |
|---|---|
| Planner | Translates user goals into step-wise plans (LLM-driven) |
| Action Selector | Picks the tool/action that fits the plan |
| Tool Execution Engine | Invokes the action (Apex, Flow, MCP tool) |
| Memory Module | Conversation history, context embeddings, long-term recall |
| Reflection Module | Retries or optimizes actions using critique agents or scoring functions |

Atlas implements **ReAct (Reason–Act–Observe) plus topic-classification routing as the first hop** — incoming messages match a topic before any action runs. Salesforce reports ~2× higher response relevance and 33% higher end-to-end accuracy vs. DIY LLM setups (their own A/B numbers; take with appropriate salt).

The output of Atlas isn't the final response — it's the **grounded prompt + executed actions**. Response generation happens via a separate LLM call (Salesforce-hosted gateway to OpenAI/Anthropic/Google with zero-data-retention agreements), passed through the **Einstein Trust Layer** for toxicity scoring, PII masking, and policy validation before display.

## The minimum viable agent (low-code)

```
1. Setup → Einstein Setup → Turn on Einstein.
2. Setup → Agent Studio → Turn on Agentforce.
3. Open Agent Builder. Pick a template (Service Agent / Sales SDR / Setup Assistant) or start blank.
4. Define topics. Each topic has: name, classification description ("when to use this topic"), scope, instructions, action list.
5. Wire actions. Standard library, your Flows, your @InvocableMethod Apex classes, or external MCP tools.
6. Test in the Builder's chat panel. Iterate.
7. Activate.
```

## Custom action via Apex (the pro-code path — where builders actually live)

An Agentforce action is **an Apex class with the `@InvocableMethod` annotation**. The `description=...` text on the method, the inputs, and the outputs is *the tool definition*. Atlas reads it to decide when and how to call your action.

```apex
global class GetAccountHealth {

    global class Request {
        @InvocableVariable(
            label='Account Name'
            description='The name of the account to look up. Supports partial matching — no need to provide the exact legal entity name.'
            required=true
        )
        global String accountName;
    }

    global class Response {
        @InvocableVariable(
            label='Health Score'
            description='Account health rating. One of: Strong, Moderate, At Risk, Weak.'
        )
        global String healthScore;

        @InvocableVariable(
            label='Days Until Close'
            description='Days until the next renewal opportunity closes. Negative values mean overdue.'
        )
        global Integer daysUntilClose;

        @InvocableVariable(
            label='Key Risks'
            description='Top 3 risks identified, as a bulleted list. Empty if no risks.'
        )
        global String keyRisks;
    }

    @InvocableMethod(
        label='Get Account Health'
        description='Returns a synthesized account health rating, days until next renewal, and top risks for a named account. Use when a sales rep or CSM asks "how is account X doing" or similar.'
        category='Sales'
    )
    global static List<Response> getHealth(List<Request> requests) {
        List<Response> results = new List<Response>();
        for (Request req : requests) {
            Account a = [SELECT Id, Health_Score__c, Next_Renewal__c, Top_Risks__c
                         FROM Account
                         WHERE Name LIKE :('%' + req.accountName + '%')
                         LIMIT 1];
            Response r = new Response();
            r.healthScore = a.Health_Score__c;
            r.daysUntilClose = (a.Next_Renewal__c - Date.today()).daysBetween();
            r.keyRisks = a.Top_Risks__c;
            results.add(r);
        }
        return results;
    }
}
```

Two patterns to internalize:

1. **`global` (not `public`) is required** for MCP tool discovery and cross-namespace agent access.
2. **The `description=` text IS the tool definition.** Sloppy descriptions cause 30%+ misrouting (per the Markaicode analysis). Treat every description field as prompt engineering, not Javadoc.

### The "deep module" pattern (Ousterhout)

Each action should **absorb interpretive logic** so the agent receives *insight*, not raw data. Don't return a 47-field `SObject` — return a synthesized verdict. This is the same principle as [`anti-patterns/definitions-without-context.md`](../anti-patterns/definitions-without-context.md) from a different angle: the orchestrating LLM should not be the one figuring out what raw rows mean.

## Invoking agents from outside (the inverse pattern)

April 2025 added **invocable agent actions** — any active Agentforce agent can be triggered from Apex, Flow, REST, or external systems:

```apex
ConnectApi.AgentforceAgentInputs inputs = new ConnectApi.AgentforceAgentInputs();
inputs.userMessage = 'What is the health of Acme Corp?';
inputs.sessionId = sessionId;  // null for a new session

ConnectApi.AgentforceAgentResponse response = ConnectApi.AgentforceAgents.invokeAgent(
    'Sales_Coach_Agent',  // Agent API name
    inputs
);
System.debug(response.responseText);
```

This is how you embed agents into Lightning Web Components, Quick Actions, scheduled jobs, or expose them as REST services to anything in your stack.

## MCP support

Native MCP client landed in Pilot July 2025. Agentforce now has **MCP support across the platform**:

- **Inbound MCP** — agents can connect to external MCP servers (AWS, Box, IBM, Cisco, Google Cloud, ~40 partners). The **AI Agent Gateway** is the unified registry with policy enforcement, rate limiting, identity control.
- **Outbound MCP — Salesforce-Hosted MCP** — your Apex actions get exposed *as* MCP tools, so external agents (Claude, Cursor, Codex, an OpenAI Agents SDK agent — anyone) can discover and invoke your Salesforce business logic over MCP. **The same `@InvocableMethod` class powers a Flow, an Agentforce action, and an external MCP tool.** Write the logic once, runs everywhere.

The MCP Server Registry is the governance layer: authorized admins maintain a central catalog of which MCP servers are approved, which tools they expose, who can use them. Salesforce's bet on being the **enterprise control plane for agent-to-tool connectivity**.

## Skills

Agentforce doesn't have skills in the Anthropic `SKILL.md` sense. The closest analogs:

- **Topics (subagents)** — bundle of related instructions + actions, fired by intent classification. Rough equivalent of a skill.
- **Prompt Templates** — reusable prompt fragments with merge fields, callable as actions.
- **Instructions on Topic** — natural-language guidance for *when* and *how* to use the actions in that topic.

The topic/subagent is the closest mental model — but it's bound to a single agent rather than being a portable artifact. If you're encoding work as `SKILL.md` to preserve portability across runtimes (the bet `landscape-2026-may.md` makes), Agentforce is the one harness where that bet doesn't carry over directly.

## The Trust Layer (the part most builders underestimate)

The Einstein Trust Layer sits between Atlas and any LLM call. Non-optional, runs on every model call. It enforces:

| Mechanism | What it does |
|---|---|
| Dynamic grounding | Only data the user is authorized to see enters the prompt |
| Data masking | PII replaced with tokens before leaving Salesforce; de-masked in the response |
| Zero data retention | Contractual with LLM providers (OpenAI, Anthropic, Google, etc.) |
| Toxicity detection | Model output is scored before display |
| Audit trail | Every prompt + response is logged |
| Prompt defense | Guards against injection and jailbreaks |

If your use case demands no governance layer between you and the model, Agentforce isn't the right tool. If your use case demands exactly this kind of governance, replicating it from outside Salesforce is extremely expensive.

## The twelve gotchas (where Agentforce projects actually break)

1. **The 15/15/20 wall.** 15 topics per agent × 15 actions per topic × 20 active agents per org. Hit fast on enterprise workloads. Official workaround: **multi-agent A2A orchestration** — an orchestrator agent delegating to specialized headless worker agents via Platform Events as durable async transport. Real fix, but architectural redesign work, not configuration.

2. **Apex governor limits.** Synchronous Apex from an agent gets the standard 100 SOQL / 150 DML per transaction. Because Atlas uses a ReAct loop, **it may call the same action multiple times in one transaction**. Heavy actions exhaust governor limits and throw. Fix: `@future`, Queueable Apex, or Platform Events for anything substantive; keep the synchronous path narrow.

3. **60-second action timeout.** Hard ceiling. Long-running work needs async + callback.

4. **Topic classification is the #1 source of agent failure.** Off-topic queries, ambiguous queries, queries that loosely match multiple topics — all cause misrouting. Realfast.ai testing showed significant variance on borderline inputs. Mitigations: stay at **8–13 topics** (Salesforce's recommended sweet spot, not 15); explicitly handle out-of-scope via a tuned "Off Topic" topic; iterate topic descriptions like prompts.

5. **No version control on agents.** No Git-equivalent. To modify an active agent: deactivate, edit, reactivate. Bites teams that want CI/CD discipline. Metadata API / source-tracked dev orgs / packaging are workarounds, but heavier than the platform should require.

6. **Industry-specific topics get deleted permanently** if removed from an agent. Reinstall the package to restore. Trap for tidying-up admins.

7. **Description fields are tool definitions.** Sloppy `@InvocableMethod(description=...)` causes 30%+ misrouting per Markaicode. Treat every description field — on the action, on each input variable, on each output variable — as a prompt that the LLM uses to decide whether and how to call this tool.

8. **Edition lock-out.** Enterprise Edition or higher required. Essentials and Starter are excluded. Pricing is consumption-based, which makes ROI modeling hard — 67% of orgs report difficulty achieving measurable ROI per industry surveys.

9. **Chat-first UX disrupts workflow.** Salespeople have to leave their CRM tasks to engage in a separate chat. Adoption rates < 20% observed in deployments where this isn't addressed. Embedded actions, Quick Actions, and proactive notifications work better than passive chat.

10. **Data Cloud dependency.** Agents are grounded in Data Cloud. Bad data → bad agents. Healthcare deployments saw 23% inaccuracies due to duplicate prescription records. Manufacturers reported 40% longer lead times because the agent couldn't adapt to vendor changes. The platform amplifies the data quality you bring.

11. **Configuration changes in production are dangerous.** Per the Clientell case study, an admin made a topic-scope change in production without review; within 48 hours the agent was answering medication-interaction questions that had been explicitly out-of-scope for compliance reasons. Treat agent configuration like code: staging, review, audit log.

12. **Latency from topic classification.** Salesforce built **HyperClassifier**, a single-token-prediction model, specifically to fix this — general-purpose LLMs were generating unnecessary reasoning tokens during classification and blowing voice-app TTFT budgets. For real-time use cases (Agentforce Voice), ensure the latest classifier is in use.

## When to use Agentforce

- Your team is on Salesforce
- The agent's job is bounded to Salesforce data + processes
- Enterprise governance (trust layer, audit, identity, data masking) is non-negotiable
- Your team is more admin + Apex developer than Python developer
- You want the agent embedded in the tools users already use (Sales Cloud, Service Cloud, Slack) rather than as a separate experience

## When *not* to use Agentforce

- The agent lives outside Salesforce
- You need programmatic control over the agent loop
- Your team lacks Salesforce expertise
- You're cost-sensitive (consumption pricing + edition requirements compound)
- You need a prototype this week — the Salesforce learning curve is real

## The fair "is Agentforce really an agent framework" question

It's a fair question. Agentforce is closer to a **vertically-integrated agent product** than to a framework like LangGraph. You don't write the agent loop, you don't choose the reasoning engine, you don't pick the model directly. What you do is configure topics, write actions, ground in Data Cloud, and let Atlas handle the rest.

The right way to compare it to the other harnesses: **Agentforce is to agents what Salesforce is to CRM.** The opinionated platform with the broad market footprint, the enterprise governance story, and the architectural ceiling that makes you migrate to something more flexible if you outgrow it. For a huge class of business problems — especially ones already mapped to Salesforce processes — that opinion is exactly right and saves years of work.

## Empirical anchor

Salesforce's own published wins: Help (81% deflection, $50M savings). Customers: Heathrow, Workday, Adecco, FedEx, Wiley. The negative receipts in the gotchas section (healthcare 23% inaccuracies, manufacturing 40% longer lead times, < 20% adoption rates, 67% struggling-to-measure-ROI) are the failure-mode counterpart — Agentforce is a high-leverage product when its assumptions hold, and a poor fit when they don't. Neither set of numbers is independently auditable; both are useful as the shape of the wins-and-losses distribution.

Origin: internal Atlan research doc, 2026-05-21, owned by Himanshu Sikaria. Not co-located in this repo; the source is the doc reviewed in conversation.
