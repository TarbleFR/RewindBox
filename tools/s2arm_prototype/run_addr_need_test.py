#!/usr/bin/env python3
"""Compares native/s2arm/prepare/s2arm_addr_need.c with S2Arm's tools/addr_need.py (CI only).

Usage: run_addr_need_test.py <s2arm_checkout> <s2arm_prepare_cli> <work_dir>

The fixture builders (nso, npdm, bl, movz and the instruction constants) are taken from S2Arm's own
tests/addr_need_test.py without importing or running it: only its function definitions and constant
assignments are executed, selected through ast. The case layouts mirror the cases that file tests. For every
case the original and the C command line run on the same files; the table bytes must be identical, or both
must fail. Synthetic input only.
"""
import ast
import random
import struct
import subprocess
import sys
from pathlib import Path

WANTED_FUNCTIONS = {"nso", "bl", "movz", "npdm"}
WANTED_NAMES = [
    "PROGRAM", "BUILD", "GIB60", "GIB64", "GIB3", "RET", "PRO", "PLT", "GOT", "MOV_62", "MOVK9", "GIB1", "STR_PRE", "ADD1", "MOVW3", "B_",
    "GIB56", "SA_INIT", "MOV60_X1", "MOV_X1_XZR", "AMP_NAME", "AMP_PLT", "AMP_GOT", "SA_PLT", "SA_GOT", "MOV_62_X1", "MOV_X1_X0", "LDR_X0",
    "LDR_X2", "ADD_X0", "MOV_X1_ZR", "GIB16", "TBZ_W2_BIT0_PLUS8",
]


def load_helpers(test_path):
    """Executes only def nso/bl/movz/npdm and constant assignments (no calls to anything but those helpers)."""
    tree = ast.parse(Path(test_path).read_text(encoding="utf-8"))
    ns = {"struct": struct}
    statements = []
    for node in tree.body:
        statements.append(node)
        if isinstance(node, ast.With):
            statements.extend(node.body)   # constants defined inside the `with tempfile...` blocks
    for node in statements:
        if isinstance(node, ast.FunctionDef) and node.name in WANTED_FUNCTIONS:
            exec(compile(ast.Module([node], []), str(test_path), "exec"), ns)
        elif isinstance(node, ast.Assign):
            lam = {a.arg for n in ast.walk(node.value) for a in (n.args.args if isinstance(n, ast.Lambda) else [])}
            safe = all(isinstance(t, ast.Name) or (isinstance(t, ast.Tuple) and all(isinstance(e, ast.Name) for e in t.elts)) for t in node.targets)
            for n in ast.walk(node.value):
                if isinstance(n, ast.Attribute):
                    safe = False
                if isinstance(n, ast.Name) and n.id not in ns and n.id not in lam:
                    safe = False
            if safe:
                try:
                    exec(compile(ast.Module([node], []), str(test_path), "exec"), ns)
                except Exception:
                    pass
    missing = [n for n in list(WANTED_FUNCTIONS) + WANTED_NAMES if n not in ns]
    if missing:
        raise SystemExit("FAIL fixture helpers missing from addr_need_test.py: " + ", ".join(missing))
    return ns


def main():
    if len(sys.argv) != 4:
        raise SystemExit(__doc__)
    checkout, cli, work = Path(sys.argv[1]).resolve(), str(Path(sys.argv[2]).resolve()), Path(sys.argv[3]).resolve()
    original = checkout / "tools" / "addr_need.py"
    h = load_helpers(checkout / "tests" / "addr_need_test.py")
    nso, npdm, bl, movz = h["nso"], h["npdm"], h["bl"], h["movz"]
    RET, PRO, PLT, GOT = h["RET"], h["PRO"], h["PLT"], h["GOT"]
    work.mkdir(parents=True, exist_ok=True)
    state = {"ran": 0, "failed": 0}

    def run_case(name, main_bytes, npdm_bytes, c_only_rc=None):
        d = work / name
        d.mkdir(parents=True, exist_ok=True)
        main_bytes = bytearray(main_bytes)
        if main_bytes[:4] == b"NSO0" and len(main_bytes) >= 0x50:
            main_bytes[0x40:0x50] = bytes(range(0x11, 0x21))   # a distinct build id, read from the NSO by the C side
        build = bytes(main_bytes[0x40:0x50]).hex() if len(main_bytes) >= 0x50 else "00" * 16
        (d / "main").write_bytes(bytes(main_bytes))
        (d / "main.npdm").write_bytes(npdm_bytes)
        c = subprocess.run([cli, "addr-need", str(d / "main"), str(d / "main.npdm"), str(d / "c.tsv")], capture_output=True, text=True)
        if c_only_rc is not None:
            ok, detail = c.returncode == c_only_rc, f"C exit {c.returncode}, want {c_only_rc}: {c.stdout.strip()}"
        else:
            ref = subprocess.run([sys.executable, str(original), build, str(d / "ref.tsv"), "--npdm", str(d / "main.npdm"), "--key", "--main", str(d / "main")],
                                 capture_output=True, text=True)
            if ref.returncode != 0:
                ok, detail = c.returncode != 0, f"original failed (exit {ref.returncode}), C exit {c.returncode}: {c.stdout.strip()}"
                kind = "both fail"
            else:
                ok = c.returncode == 0 and (d / "c.tsv").is_file() and (d / "c.tsv").read_bytes() == (d / "ref.tsv").read_bytes()
                detail = f"C exit {c.returncode}: {c.stdout.strip()}"
                kind = "identical"
            if ok:
                detail = kind
        state["ran"] += 1
        state["failed"] += not ok
        print(f"{'ok  ' if ok else 'FAIL'} {name} ({detail})", flush=True)

    good = npdm(0x0100AAAA00000000, sysres=0x1000000)

    def direct_call(word):
        return nso([(0x1000, RET), (0x1004, word), (0x1008, bl(0x1008, PLT)), (0x100C, RET)], GOT, PLT)

    def caller_of_wrapper(prologue, body):
        words = [(0x1000, RET), (0x1004, prologue), (0x1008, bl(0x1008, PLT)), (0x100C, RET)]
        at = 0x1010
        for w in body + [bl(at + 4 * len(body), 0x1004), RET]:
            words.append((at, w))
            at += 4
        return nso(words, GOT, PLT)

    def thunk_chain(imp, const):
        B_ = h["B_"]
        return nso([(0x1000, RET), (0x1004, h["MOVW3"]), (0x1008, B_(0x1008, PLT)), (0x100C, RET), (0x1010, PRO), (0x1014, bl(0x1014, 0x1004)), (0x1018, RET),
                    (0x101C, B_(0x101C, 0x1010)), (0x1020, PRO), (0x1024, bl(0x1024, 0x101C)), (0x1028, RET),
                    (0x102C, const), (0x1030, bl(0x1030, 0x1020)), (0x1034, RET)], GOT, PLT, imp)

    def wario(entry):
        B_ = h["B_"]
        return nso([(0x1000, RET), (0x1004, PRO), (0x1008, h["MOV_X1_XZR"]), (0x100C, bl(0x100C, 0x1018)), (0x1010, RET), (0x1014, RET),
                    (0x1018, h["MOVW3"]), (0x101C, B_(0x101C, PLT)), (0x1020, RET), (0x1024, h["MOV60_X1"]), (0x1028, bl(0x1028, 0x1004)), (0x102C, RET)],
                   GOT, PLT, entry)

    more = ((h["AMP_NAME"], h["AMP_GOT"], h["AMP_PLT"]), (h["SA_INIT"], h["SA_GOT"], h["SA_PLT"]))
    ub_head = [(0x1000, RET), (0x1004, h["MOV_62_X1"]), (0x1008, bl(0x1008, PLT)), (0x100C, RET),
               (0x1010, PRO), (0x1014, h["MOV_X1_X0"]), (0x1018, bl(0x1018, PLT)), (0x101C, RET)]

    def unbounded(tail, head=None):
        return nso((head or ub_head) + tail, GOT, PLT, more=more)

    LDR_X0, ADD_X0, GIB16 = h["LDR_X0"], h["ADD_X0"], h["GIB16"]
    ub_tails = {
        "ub-const": [(0x1020, GIB16), (0x1024, bl(0x1024, 0x1010)), (0x1028, RET)],
        "ub-load": [(0x1020, LDR_X0), (0x1024, bl(0x1024, 0x1010)), (0x1028, RET)],
        "ub-compute": [(0x1020, ADD_X0), (0x1024, bl(0x1024, 0x1010)), (0x1028, RET)],
        "ub-allocator-null": [(0x1020, PRO), (0x1024, h["MOV_X1_ZR"]), (0x1028, h["LDR_X2"]), (0x102C, bl(0x102C, h["SA_PLT"])), (0x1030, RET),
                              (0x1040, GIB16), (0x1044, bl(0x1044, 0x1010)), (0x1048, RET)],
        "ub-allocator-buffer": [(0x1020, PRO), (0x1024, LDR_X0), (0x1028, h["MOV_X1_X0"]), (0x102C, h["LDR_X2"]), (0x1030, bl(0x1030, h["SA_PLT"])),
                                (0x1034, RET), (0x1040, GIB16), (0x1044, bl(0x1044, 0x1010)), (0x1048, RET)],
    }
    many = []   # twelve callers of the wrapper: the reason line passes the 400-byte limit and the tail is counted
    at = 0x1020
    for _ in range(12):
        many += [(at, LDR_X0), (at + 4, bl(at + 4, 0x1010)), (at + 8, RET)]
        at += 12

    cases = {}
    cases["no-claim"] = (nso([(0x1000, RET), (0x1004, bl(0x1004, PLT)), (0x1008, RET)], GOT, PLT), good)
    cases["direct-62gib"] = (direct_call(h["MOV_62"]), good)
    cases["direct-64gib-cap"] = (direct_call(h["GIB64"]), good)
    cases["constant-under-4gib"] = (direct_call(h["GIB3"]), good)
    cases["movz-movk-direct"] = (nso([(0x1000, RET), (0x1004, h["GIB1"]), (0x1008, h["MOVK9"]), (0x100C, bl(0x100C, PLT)), (0x1010, RET)], GOT, PLT), good)
    cases["movz-movk-wrapper"] = (caller_of_wrapper(h["STR_PRE"], [h["GIB1"], h["MOVK9"]]), good)
    cases["movk-clobbered"] = (caller_of_wrapper(h["STR_PRE"], [h["GIB1"], h["ADD1"], h["MOVK9"]]), good)
    cases["movk-only"] = (caller_of_wrapper(h["STR_PRE"], [h["MOVK9"]]), good)
    cases["wrapper"] = (nso([(0x1000, RET), (0x1004, PRO), (0x1008, 0xAA0003E1), (0x100C, bl(0x100C, PLT)), (0x1010, RET),
                             (0x1014, h["GIB60"]), (0x1018, bl(0x1018, 0x1004)), (0x101C, RET)], GOT, PLT), good)
    cases["tail-call-thunk-allocator"] = (thunk_chain(h["SA_INIT"], h["GIB56"]), good)
    cases["tail-call-thunk-region"] = (thunk_chain(b"_ZN2nn2os21AllocateAddressRegionEPmm", h["GIB56"]), good)
    cases["tail-call-thunk-small"] = (thunk_chain(h["SA_INIT"], h["GIB3"]), good)
    cases["wario-allocator"] = (wario(h["SA_INIT"]), good)
    cases["wario-not-a-claim"] = (wario(b"_ZN2nn3mem17StandardAllocator8AllocateEm"), good)
    cases["nlib-virtual-direct"] = (nso([(0x1000, RET), (0x1004, h["MOV60_X1"]), (0x1008, bl(0x1008, PLT)), (0x100C, RET)], GOT, PLT,
                                        b"nnmem_nlib_virtual_alloc"), good)
    for name, tail in ub_tails.items():
        cases[name] = (unbounded(tail), good)
    cases["ub-reason-line-limit"] = (unbounded(many), good)
    cases["ub-committed"] = (nso([(0x1000, RET), (0x1004, h["MOV_62_X1"]), (0x1008, bl(0x1008, PLT)), (0x100C, RET), (0x1010, PRO), (0x1014, h["MOV_X1_X0"]),
                                  (0x1018, bl(0x1018, PLT)), (0x101C, bl(0x101C, h["AMP_PLT"])), (0x1020, RET), (0x1024, LDR_X0), (0x1028, bl(0x1028, 0x1010)),
                                  (0x102C, RET)], GOT, PLT, more=more[:1]), good)
    cases["ub-conditional-commit"] = (nso([(0x1000, RET), (0x1004, h["MOV_62_X1"]), (0x1008, bl(0x1008, PLT)), (0x100C, RET), (0x1010, PRO),
                                           (0x1014, h["MOV_X1_X0"]), (0x1018, bl(0x1018, PLT)), (0x101C, h["TBZ_W2_BIT0_PLUS8"]),
                                           (0x1020, bl(0x1020, h["AMP_PLT"])), (0x1024, RET), (0x1028, LDR_X0), (0x102C, bl(0x102C, 0x1010)),
                                           (0x1030, RET)], GOT, PLT, more=more[:1]), good)
    claim = direct_call(h["MOV_62"])
    cases["vamm-off-sysres-0"] = (claim, npdm(0x0100AAAA00000000, sysres=0))
    cases["vamm-on-sysres"] = (claim, npdm(0x0100AAAA00000000, sysres=1))
    cases["npdm-aci-at-0x200"] = (claim, npdm(0x010019C00E9CC000, 0x200, 0x1000000))
    cases["vamm-off-main-not-nso"] = (b"\0" * 0x100, npdm(0x0100AAAA00000000, sysres=0))
    # malformed inputs
    cases["npdm-no-meta"] = (claim, b"XXXX" + good[4:])
    cases["npdm-no-aci0"] = (claim, good.replace(b"ACI0", b"ACIX"))
    cases["npdm-too-short"] = (claim, good[:0x70])
    cases["npdm-aci-offset-out-of-range"] = (claim, good[:0x70] + (0x10000).to_bytes(4, "little") + good[0x74:])
    cases["main-not-nso"] = (b"XXXX" * 0x40, good)
    cases["main-truncated-header"] = (claim[:0x50], good)
    broken = bytearray(claim)
    struct.pack_into("<I", broken, 0x18, len(claim) - 0x100 + 0x1000)   # text size beyond the image once the segment is stored
    cases["text-size-mismatch"] = (bytes(broken), good)
    # LZ4-compressed text segment, as the NSO flag bit 0 says
    try:
        import lz4.block
    except ImportError:
        raise SystemExit("FAIL the lz4 module is required (pip install lz4==4.4.5)")

    def compressed(raw):
        head, image = bytearray(raw[:0x100]), raw[0x100:]
        blob = lz4.block.compress(image, store_size=False)
        struct.pack_into("<I", head, 0xC, struct.unpack_from("<I", head, 0xC)[0] | 1)
        struct.pack_into("<I", head, 0x60, len(blob))
        for header in (0x20, 0x30):
            struct.pack_into("<I", head, header, 0x100 + len(blob))
        return bytes(head) + blob

    cases["lz4-direct-claim"] = (compressed(direct_call(h["MOV_62"])), good)
    cases["lz4-unbounded-reasons"] = (compressed(unbounded(ub_tails["ub-load"])), good)
    cases["lz4-corrupt"] = (compressed(claim)[:-3] + b"\xff\xff\xff", good)

    for name, (main_bytes, npdm_bytes) in cases.items():
        run_case(name, main_bytes, npdm_bytes)

    # ZBIC (flag 0x80) is not implemented in C: it must report UNSUPPORTED (3). The original needs dotnet, so it is not run.
    zbic = bytearray(claim)
    struct.pack_into("<I", zbic, 0xC, 0x80)
    run_case("zbic-unsupported-c-only", bytes(zbic), good, c_only_rc=3)

    # Deterministic mutation of the fixtures: random and interesting instruction words at random code addresses.
    rng = random.Random(20261111)
    pool = [RET, PRO, h["ADD1"], h["MOVK9"], h["GIB1"], h["MOV_X1_X0"], LDR_X0, ADD_X0, h["MOV_X1_ZR"], h["LDR_X2"], h["STR_PRE"], h["TBZ_W2_BIT0_PLUS8"],
            0xD503201F, 0, 0x14000001, 0x94000000, 0xD65F0000, 0xA9BF7BFD, 0x2A0203E1, 0x91000020, 0x12800001, 0xAA0103E1, 0xF9400041]
    bases = [ub_head + t for t in ub_tails.values()] + [ub_head + many]
    for i in range(48):
        base = rng.choice(bases)
        words = dict(base)
        for _ in range(rng.randint(1, 3)):
            where = rng.choice(list(words) + [rng.randrange(0x1000, 0x1080, 4)])
            roll = rng.random()
            if roll < 0.45:
                value = rng.choice(pool)
            elif roll < 0.6:
                value = bl(where, rng.choice([0x1004, 0x1010, 0x1020, PLT, h["AMP_PLT"], h["SA_PLT"], rng.randrange(0x1000, 0x1100, 4)]))
            else:
                value = rng.getrandbits(32)
            words[where] = value
        run_case(f"fuzz-{i:02d}", nso(sorted(words.items()), GOT, PLT, more=more), good)

    print(f"{state['ran']} cases, {state['failed']} failed")
    if state["failed"] or state["ran"] < 8:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
