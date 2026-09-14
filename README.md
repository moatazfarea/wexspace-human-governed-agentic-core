# WEXSPACE AI — Human-Governed Agentic Core

A Strands-powered professional execution core that performs real work through deterministic tools, preserves evidence and durable state, resumes exactly after interruption, and stops at an enforced human authority boundary.

## What problem it solves

Professional work is not safely reduced to a chatbot answer. A useful agent must know what it is trying to complete, use deterministic tools for deterministic work, prove what happened, survive interruption without duplicating effects, and stop when a human decision is required.

This project implements that execution discipline as a clean competition project for the Agents for Humans Professional Agents track.

## Core behavior

1. Compile an ordinary professional request into a controlled execution contract.
2. Inspect required inputs.
3. Reconcile evidence with deterministic tooling.
4. Persist each completed effect and evidence event.
5. Prepare a structured review package.
6. Stop at `HUMAN_REVIEW`; the agent cannot approve the consequential decision.
7. Resume from durable state after process termination without replaying completed effects.
8. Reject identical failed recovery routes when state has not materially changed.

## Strands + Amazon Bedrock

The live runtime uses the Strands Agents SDK and its native `BedrockModel` provider. Bedrock model and region are explicit runtime configuration discovered from the actual AWS account; the source does not silently hard-code an assumed entitlement.

Environment expected for a live run:

```bash
export AWS_REGION=<verified-region>
export WEXSPACE_BEDROCK_MODEL_ID=<verified-tool-capable-model>
```

Authentication uses the standard AWS credential/provider chain supported by the execution environment.

## Install

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e '.[test]'
```

## Deterministic qualification

```bash
pytest
```

## Local synthetic workflow

```bash
wexspace-core --state-dir .demo-state create AFH-DEMO-001 \
  "Reconcile the synthetic receiving evidence and prepare a human review package." \
  '{"request_id":"REQ-AFH-001","expected_quantity":120,"observed_quantity":118}'

wexspace-core --state-dir .demo-state run AFH-DEMO-001
wexspace-core --state-dir .demo-state status AFH-DEMO-001
wexspace-core --state-dir .demo-state export AFH-DEMO-001 demo-output
```

## Local judge Web UI

After installation:

```bash
python -m wexspace_human_governed_core.webapp --state-dir .web-demo-state --port 8080
```

Open http://127.0.0.1:8080. Start a synthetic receiving case, reconnect to saved work after a service restart, resume safe tools, and read the evidence receipt.

The server binds only to loopback, rejects cross-origin browser mutations, and exposes no approval endpoint. This mode uses deterministic tools without cloud model inference. It is a local judge demo, not a deployed multi-user service.

The **Browser and real display qualification** workflow records actual X11 display activity with FFmpeg while it kills and restarts the Python server. Unedited qualification segments and their hashes are preserved on the separate `afh-display-evidence-20260914` branch. These segments are not the final competition video.

## Live Strands / Bedrock qualification

After discovering a model and region that are actually available to the AWS account:

```bash
wexspace-core --state-dir .demo-state run-live AFH-DEMO-001 \
  "Complete the governed workflow using the available tools and stop at human review."
```

A live provider is **not** considered qualified until a real model response, real Strands tool selection, real tool execution, returned tool result, durable evidence, and the human gate are all observed.

## Exact resume

The state store records an execution cursor and idempotent side effects. A fresh process reopens the same SQLite state and continues at the first incomplete node. The test suite proves completed tool effects are not duplicated across restart.

## Human authority

The model may inspect, reason, call tools and prepare evidence. It may not approve/reject the final consequential decision. Approval or rejection is only available through the explicit `review` operation after the workflow reaches `HUMAN_REVIEW`.

## Evidence

Evidence is written as canonical JSONL records with per-record SHA-256 integrity digests. The product exports both a machine-readable decision package and evidence manifest.

## Root-corrective recovery

Failure attempts are fingerprinted by failure, route and material state token. An identical failed route under unchanged state is rejected; a materially different route or materially changed state can be attempted.

## Architecture

See [`docs/architecture.md`](docs/architecture.md).

## Safety and data

The repository uses synthetic competition-safe examples. Do not place employer-confidential information, credentials, API keys or private WEXSPACE governance artifacts in the public project.

## License

MIT.
