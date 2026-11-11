# Receipts of the Switch 2 (S2Arm) test IPA line

Receipts of the private test IPAs of this line (builds from 801), written by
`python3 -B .github/diagnostics/s2arm/standard_delivery_s2arm.py record <N> …` into
`docs/evidence/rewind<N>/` and then moved here.

They are not receipts of the common line: their run is a run of
`.github/workflows/s2arm-delivery.yml` on `work/s2arm-switch2-prototype-20261110`. Kept under
`docs/evidence/rewind<N>/`, the common contract test (`test/standard_delivery_contract_test.py`,
"record replays the latest receipt") would take the newest of them as the latest common receipt
and replay it with the common branch and workflow, which it can never match. No build of either
line uses them as a base: the test line builds from a delivered common base.
