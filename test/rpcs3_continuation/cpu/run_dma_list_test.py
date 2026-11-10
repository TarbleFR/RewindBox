#!/usr/bin/env python3
"""Complete production DMA-list and MFC-queue bodies with bounded host adapters."""
from pathlib import Path
from production_harness import arguments, run_program, sha256

FIXTURES = Path(__file__).resolve().parent


def build_program(baseline, source):
    def extract(text, name, next_name):
        start = text.index("bool spu_thread::" + name + "(")
        end = text.index("bool spu_thread::" + next_name + "(", start)
        return text[start:end]

    parts, hashes = [], {}
    for label, root in (("old", baseline), ("new", source)):
        text = (root / "rpcs3/Emu/Cell/SPUThread.cpp").read_text()
        list_fn = extract(text, "do_list_transfer", "do_putllc")
        mfc_fn = extract(text, "do_mfc", "check_mfc_interrupts")
        hashes[label] = {"list_sha256": sha256(list_fn), "queue_sha256": sha256(mfc_fn)}
        parts.append((list_fn + mfc_fn).replace("spu_thread::", "spu_" + label + "::"))
    program = (FIXTURES / "dma_list_harness_prefix.cpp").read_text() + "\n" + "\n".join(parts) + "\n" + (FIXTURES / "dma_list_harness_suffix.cpp").read_text()
    return program, hashes


def main():
    args = arguments(__doc__)
    program, hashes = build_program(args.baseline, args.source)
    return run_program(args, "dma-list", program, hashes,
        "Complete production do_list_transfer and do_mfc; bounded host adapters for VM, vector storage, locks, IRQ, timing, generic DMA; not real GPU/ARM64 concurrency or iPhone gameplay.",
        ["The original zero-element underflow is intercepted by the copy adapter after the initial 16-byte store and before the next 128-byte copy; no four-GiB overwrite is executed.",
         "Native ARM64 instructions, iOS vector-copy specialization, and hardware concurrency are not executed.",
         "No FPS, device RSS, or game-scene resolution claim."])


if __name__ == "__main__":
    raise SystemExit(main())
