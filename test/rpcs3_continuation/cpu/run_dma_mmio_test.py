#!/usr/bin/env python3
"""Complete production DMA-transfer body with bounded VM/CPU/atomic/lock adapters."""
from pathlib import Path
from production_harness import arguments, extract_block, run_program, sha256

FIXTURES = Path(__file__).resolve().parent


def build_program(baseline, source):
    parts, hashes = [], {}
    for label, root in (("old", baseline), ("new", source)):
        text = (root / "rpcs3/Emu/Cell/SPUThread.cpp").read_text()
        body = extract_block(text, "void spu_thread::do_dma_transfer(")
        hashes[label] = sha256(body)
        parts.append(body.replace("void spu_thread::do_dma_transfer(", "void " + label + "_dma_transfer("))
    program = (FIXTURES / "dma_mmio_prefix.cpp").read_text() + "\n" + "".join(parts) + (FIXTURES / "dma_mmio_suffix.cpp").read_text()
    return program, hashes


def main():
    args = arguments(__doc__)
    program, hashes = build_program(args.baseline, args.source)
    return run_program(args, "dma-mmio", program, hashes,
        "Complete production do_dma_transfer, with bounded VM and CPU/atomic/lock adapters; vm range-lock implementations independently exercised in vm-mmio-program.cpp. No native race or iPhone claim; 128-byte atomic helper uses destination-resolution adapter.",
        ["The 128-byte atomic helper adapter models effective-address resolution and copying; it does not execute the real concurrent atomic helper.",
         "Native ARM64 instructions and iOS vector-copy specialization are not compiled/executed.",
         "VM range-lock bodies are validated separately by run_vm_mmio_test.py; this harness uses their tested MMIO gate contract.",
         "Invalid offset cases are explicitly rejected by the production MMIO dispatcher; unmapped absent-thread MMIO faults are not modeled by the placeholder mapping.",
         "No FPS, device RSS, or game-scene resolution claim."])


if __name__ == "__main__":
    raise SystemExit(main())
