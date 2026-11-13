---
paths:
  - "lib/**"
  - "packages/**"
  - "native/**"
  - "build-utils/**"
  - "test/**"
  - "tools/**"
  - ".github/diagnostics/**"
---

# RewindBox diagnostics

Follow the active task and diagnostic rules in `docs/AI_TASK_BOARD.md`.
Read its direct component evidence before changing behavior. The coordinator updates
the owned entry with meaningful findings and validation, including failures and input
identity. Delegated agents provide that update to the coordinator unless explicitly
assigned ownership of the board entry.
