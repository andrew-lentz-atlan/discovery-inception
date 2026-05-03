# Step 1: Classifier

You will read a single document and classify what kind of artifact it is.

## Your job
Look at the document below. Decide which of these categories best describes it:

- `job_description` — a formal role posting or internal role definition. Sections like Responsibilities, Qualifications, About the Role.
- `runbook` — a how-to document for executing a recurring process. Step-by-step instructions, often with branches and exceptions.
- `process_doc` — a description of a workflow or process at a higher level than a runbook. Often discusses why and when, not just how.
- `interview_transcript` — a literal transcript of a spoken conversation. Speaker names, turn-taking dialogue, fillers.
- `slack_thread` — a Slack export with timestamps, channel context, threaded replies.
- `meeting_notes` — bullet-point or paragraph notes from a meeting. Less formal than a process doc.
- `policy_doc` — a rules / governance document. "Must," "shall," approval matrices, RACI tables.
- `other` — pick this only if none of the above fits.

## Output
Respond with valid JSON matching this exact shape:

```json
{
  "artifact_type": "<one of the categories above>",
  "confidence": <float between 0.0 and 1.0>,
  "rationale": "<one sentence explaining why>"
}
```

Do not include any other text. Just the JSON.

## Document to classify

{ARTIFACT_TEXT}
