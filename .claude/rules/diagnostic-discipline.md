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

# Evidence before repeated diagnosis

- Consult the component record located by `docs/AI_EVIDENCE_INDEX.md` before
  changing its behavior. Compare its tested inputs with the current source.
- Reopen an old conclusion only for a named input change, contradictory evidence
  or untested path. Preserve negative results so a resumed session does not repeat
  a failed idea without a reason.
- For performance work, connect each proposed patch to the measured bottleneck,
  expected journal field and comparison conditions. Do not substitute CPU time,
  GPU time, queued time, launch time or FPS for one another.
- For an environment failure, record the command, actual error, host/tool and
  missing prerequisite once. Retry only if that prerequisite or permitted route
  changed; continue independent local work instead of repeating blocked downloads.
- Validate the real implementation. Reuse a prior successful check only with its
  exact source, dependencies, toolchain, fixtures and configuration unchanged.
  Rerun affected checks after a relevant change/failure; keep failed results visible.
- Check the effective build/pin before interpreting device logs. A source commit
  does not establish what the installed IPA contains. Never announce device gains
  from source inspection or host-only tests.
