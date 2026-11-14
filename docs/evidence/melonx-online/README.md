# MeloNX online lot — local verification record (14 November 2026)

Record of what was checked on the engine lot of
[Switch profiles and Nextendo](../../melonx-switch-profiles-nextendo-2026-11-14.md). It is evidence, not a
gate: nothing here runs in a workflow, and the lot is in no Core.

- [receipt.json](receipt.json): hosts, sources, digests and counts.
- [harness-Program.cs.txt](harness-Program.cs.txt): the console program run against the candidate's
  `Ryujinx.HLE` (102 checks passed). It reaches the engine's internal resolver, blacklist and token
  generator by reflection. Kept as text so that no tool compiles it.

How it was produced: a copy of pristine MeloNX `13700519` prepared by one `prepare_embedded.py` pass,
LibHac rebuilt by `build_libhac.py`, `Ryujinx.HLE` built (control); the same tree with
`build-utils/melonx/online/adapt_nextendo_online.py` applied (candidate), `Ryujinx.HLE` and
`Ryujinx.Library` built, then the harness as a console project referencing the candidate's
`Ryujinx.HLE.csproj` (`dotnet run -c Release`).

When a Core takes the lot, this program is the natural starting point of its gate.
