# Measured race-path probes

These controlled microbenchmarks compare the source paths under equal inputs. They are not a replay of session801, an iPhone measurement, or a claim of increased game FPS. Unsupported resident-pool fallback cases abort instead of simulating Metal costs. Checksums and untimed field comparisons validate outputs. Timings alternate original/candidate across repetitions.

CPU functions derive from S2Arm6b6a5715 with RewindBox patches0001–0168; their parent engine licence/attribution remains applicable. The low-level alternative keeps the original resident lookup and only skips the out-of-line address conversion for addresses outside the guest GVA interval. Push cases include all-identical and frequently changed bytes. The real Metal resource-ID probe requires an actual Metal device.

Core ML uses a deterministic authored filter, not trained super-resolution weights. The model and Metal code must produce equivalent pixels before comparing their full processing latency. Device availability, selected compute devices, CPU fallback and excluded game/presentation time are explicit in the report. No reconstruction is enabled in the game.

Run `python3 build-utils/s2arm/engine/benchmarks/run_cpu.py` and `run_coreml.py` on an Apple SDK host. The existing engine workflow's optional `[s2arm-benchmark]` job runs only these probes; the standard IPA recipe is unchanged.
