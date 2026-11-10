# LR full-queue follow-up — no retained production correction

`lr-probe.cpp` is the exact standalone generated program executed for this
read-only follow-up. Its SHA256 equals `generated_sha256` in `lr-probe.json`.
The JSON also retains the production SPUThread input digest, original compiler
command and observed result. It ran with GCC 13 on Linux x86-64, without
sanitizers; no Apple or iPhone execution is claimed.

The program retains extracted production `process_mfc_cmd` prefix, MFC drain,
`cpu_work`, event collection, interrupt entry and thread wait/latch methods from
the decrementer harness. A **test-only reservation predicate** is changed from
always false to a controlled `reservation_lost` field. There is no real guest
reservation memory, writer thread, VM notifier or native kernel wait backend.
The CPU-state dispatcher and timer/clock infrastructure remain adapters.

With the event mask set to LR, a lost reservation, disabled ordinary cpu_work
IRQ collection and a full MFC queue, the current prefix blocks with no collected
event. An explicit test call to the owner's real `get_events(SPU_EVENT_LR)`
then permits an IRQ at the same WRCH PC, without accepting the pending command.
That call is an observation of the missing collection, **not a production fix**.

The next design must register and revalidate the reservation and its contents
while retaining host stop/SNR notifications. Merely waiting on the VM notifier
is insufficient: ordinary direct stores do not all generate that notification.
The existing `SPU_RdEventStat` path has bounded 50–200 microsecond host waits
and checks both reservation generation and contents for this reason. This
probe does not justify copying such polling into every full-queue wait, nor
adding a guest timeout or forcing a label value.

The historical GOW3 `0x60300510` producer is still unknown, and build 601 did
not reach guest execution for GOW3. The result therefore establishes neither
that LR caused the observed introduction freeze nor that the retained TM
correction resolves it. No upstream correction or performance gain is claimed.

Recompile the frozen program with the recorded flags, replacing only the
`-I` path with the tested materialized Core's `rpcs3` directory and the output
paths with local equivalents. `IOSSignalTrace.h` must match the source recorded
by the neighboring final decrementer test reports. The generated program is
an explicit adapter fixture, not an alternative emulator source tree.
