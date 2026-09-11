# Architecture

```text
Professional request
      |
      v
Request compiler
      |
      v
WEXSPACE governed Strands agent
      |
      +--> deterministic inspect tool
      +--> deterministic reconciliation tool
      +--> review-package tool
      |
      v
Durable SQLite state + side-effect ledger
      |
      v
Evidence ledger (hash-bound JSONL)
      |
      v
HUMAN_REVIEW gate
      |
      v
Owner approve / reject
```

The live path uses Strands with a native Amazon Bedrock `BedrockModel`. Deterministic tests exercise the same durable workflow without pretending to qualify a live provider. Completed effects are idempotent and exact resume is process-independent.
