#!/usr/bin/env python3
"""Complete production range-lock functions with deterministic VM/atomic adapters."""
from pathlib import Path
from production_harness import arguments, extract_block, run_program, sha256

FIXTURES = Path(__file__).resolve().parent


def build_program(baseline, source):
    parts, hashes = [], {}
    for label, root in (("old", baseline), ("new", source)):
        text = (root / "rpcs3/Emu/Memory/vm.cpp").read_text()
        header = (root / "rpcs3/Emu/Memory/vm_locking.h").read_text()
        fast = extract_block(header, "template <uint Size = 0>")
        slow = extract_block(text, "void range_lock_internal(")
        sweep = extract_block(text, "template <typename F>\n\tFORCE_INLINE static u64 for_all_range_locks")
        hashes[label] = {name: sha256(body) for name, body in (("slow", slow), ("fast", fast), ("sweep", sweep))}
        part = (FIXTURES / "vm_mmio_namespace.cpp").read_text() + sweep + slow + fast
        parts.append("namespace vm_" + label + " {\n" + part.replace("vm::", "vm_" + label + "::") + "\n}\n")
    program = (FIXTURES / "vm_mmio_prefix.cpp").read_text() + "\n" + "".join(parts) + (FIXTURES / "vm_mmio_suffix.cpp").read_text()
    return program, hashes


def main():
    args = arguments(__doc__)
    program, hashes = build_program(args.baseline, args.source)
    return run_program(args, "vm-mmio", program, hashes,
        "Complete production range_lock, range_lock_internal and lock sweep, with deterministic atomic/VM page and scheduler adapters; no native race or iPhone claim.",
        ["Conflicting-lock release is a deterministic scheduler callback, not a native race test.",
         "Guest page state and write-page faults are bounded adapters.",
         "No FPS, device RSS, or game-scene resolution claim."])


if __name__ == "__main__":
    raise SystemExit(main())
