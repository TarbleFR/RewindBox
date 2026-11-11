#!/usr/bin/env python3
"""Compares native/s2arm/prepare/s2arm_modules.c and s2arm_nro.c with S2Arm's originals (CI only).

Usage: run_modules_test.py <s2arm_checkout> <s2arm_prepare_cli> <work_dir>

Originals (run as `python3 <checkout>/...`, never imported):
  graphics/nvn/games/profile_guess.py --gpu-drivers <exefs>      <-> cli gpu-drivers <exefs> <output>
  tools/nro_exports.py <romfs> <output tsv>                      <-> cli nro-exports <romfs> <output>
  runtime/rewriter/nro_to_nso.py <romfs> <output dir>            <-> cli nro-to-nso <romfs> <output dir>
Packages the originals need: lz4 (python-lz4, pinned in the workflow; only for LZ4-compressed NSO segments).
Both sides run on the same synthetic input (built here, no game content). Success needs the same file set and the
same bytes; a failing original needs a failing C side. NRR-registered hashes that no *.nro file has need zstd in
the original: the C side must refuse them with exit code 3 (UNSUPPORTED); the original is not run for that case.
"""
import hashlib
import shutil
import struct
import subprocess
import sys
from pathlib import Path

state = {"ran": 0, "failed": 0}


def report(ok, name, detail):
    state["ran"] += 1
    state["failed"] += not ok
    print(f"{'ok  ' if ok else 'FAIL'} {name} ({detail})", flush=True)


def snapshot(root):
    root = Path(root)
    if not root.is_dir():
        return {}
    return {str(p.relative_to(root)): p.read_bytes() for p in sorted(root.rglob("*")) if p.is_file()}


# ---------------------------------------------------------------- fixtures

def build_nso(comps=(), compress=False, bad_mod0=False, exports=(b"exported_fn",)):
    """NSO with text / ro / data of 0x1000 each: MOD0 in text, dynamic segment in data, symbols in ro."""
    text = bytearray(0x1000)
    struct.pack_into("<I", text, 4, 8)
    text[8:12] = b"XXXX" if bad_mod0 else b"MOD0"
    struct.pack_into("<i", text, 12, 0x2000 - 8)
    ro = bytearray(0x1000)
    strtab = bytearray(b"\0")
    for i, name in enumerate(exports, 1):
        struct.pack_into("<IBBHQQ", ro, 24 * i, len(strtab), 0x12, 0, 1, 0x1000, 8)
        strtab += name + b"\0"
    ro[0x100:0x100 + len(strtab)] = strtab
    at = 0x200
    for c in comps:
        ro[at:at + len(c) + 1] = c + b"\0"
        at += len(c) + 8
    data = bytearray(0x1000)
    struct.pack_into("<qQqQqQ", data, 0, 5, 0x1100, 6, 0x1000, 0, 0)
    segs = [bytes(text), bytes(ro), bytes(data)]
    header = bytearray(0x100)
    header[0:4] = b"NSO0"
    blobs = segs
    if compress:
        import lz4.block
        blobs = [lz4.block.compress(s, store_size=False) for s in segs]
        struct.pack_into("<I", header, 0xC, 7)
    fo = 0x100
    for i, blob in enumerate(blobs):
        struct.pack_into("<III", header, 0x10 + i * 0x10, fo, i * 0x1000, 0x1000)
        struct.pack_into("<I", header, 0x60 + i * 4, len(blob))
        fo += len(blob)
    return bytes(header) + b"".join(blobs)


def build_nro(tag=1, syms=((b"fn_a", 0x12, 1), (b"fn_b", 0x22, 2), (b"undef", 0x12, 0), (b"local", 0x02, 1)), size=0x3000, magic=True, mod0=True):
    text = bytearray(0x1000)
    struct.pack_into("<I", text, 4, 0x1000)
    if magic:
        text[0x10:0x14] = b"NRO0"
    struct.pack_into("<I", text, 0x18, size)
    struct.pack_into("<6I", text, 0x20, 0, 0x1000, 0x1000, 0x1000, 0x2000, 0x1000)
    struct.pack_into("<I", text, 0x38, 0x1000)
    text[0x40:0x60] = bytes([tag]) * 0x20
    text[0x68:0x80] = bytes(range(0x30, 0x48))
    ro = bytearray(0x1000)
    if mod0:
        struct.pack_into("<4sIi", ro, 0, b"MOD0", 0, 0)
        struct.pack_into("<i", ro, 4, 0x100)
        struct.pack_into("<qQqQqQ", ro, 0x100, 5, 0x1400, 6, 0x1200, 0, 0)
    strtab = bytearray(b"\0")
    for i, (name, info, shndx) in enumerate(syms, 1):
        struct.pack_into("<IBBHQQ", ro, 0x200 + 24 * i, len(strtab), info, 0, shndx, 0x1000, 8)
        strtab += name + b"\0"
    ro[0x400:0x400 + len(strtab)] = strtab
    return bytes(text) + bytes(ro) + bytes(0x1000)


def build_nrr(hashes, magic=b"NRR0", size=0x350):
    d = bytearray(size)
    d[0:4] = magic
    struct.pack_into("<II", d, 0x340, 0x350, len(hashes))
    return bytes(d) + b"".join(hashes)


def sha(data):
    return hashlib.sha256(data).digest()


def put(root, rel, data):
    p = Path(root) / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(data)


# ---------------------------------------------------------------- runners

def fresh(work, name):
    d = work / name
    if d.exists():
        shutil.rmtree(d)
    d.mkdir(parents=True)
    return d


def finish(name, ref_rc, c, ref_files, c_files):
    if ref_rc != 0:
        report(c.returncode != 0, name, f"original failed (exit {ref_rc}), C exit {c.returncode}: {c.stdout.strip()}" if c.returncode == 0 else "both fail")
    elif c.returncode != 0:
        report(False, name, f"C exit {c.returncode}: {c.stdout.strip()}")
    else:
        same = ref_files == c_files
        report(same, name, "identical, files: " + ",".join(sorted(ref_files)) if same else f"differ: original {sorted(ref_files)} C {sorted(c_files)}")


def drivers_case(checkout, cli, work, name, files):
    d = fresh(work, name)
    for rel, data in files.items():
        put(d / "exefs", rel, data)
    (d / "exefs").mkdir(exist_ok=True)
    ref = subprocess.run([sys.executable, str(checkout / "graphics/nvn/games/profile_guess.py"), "--gpu-drivers", str(d / "exefs")], capture_output=True)
    c = subprocess.run([cli, "gpu-drivers", str(d / "exefs"), str(d / "c.tsv")], capture_output=True, text=True)
    ref_files = {"gpu_drivers.tsv": ref.stdout}
    c_files = {"gpu_drivers.tsv": (d / "c.tsv").read_bytes()} if (d / "c.tsv").is_file() else {}
    finish(name, ref.returncode, c, ref_files, c_files)


def exports_case(checkout, cli, work, name, files):
    d = fresh(work, name)
    (d / "romfs").mkdir()
    for rel, data in files.items():
        put(d / "romfs", rel, data)
    ref = subprocess.run([sys.executable, str(checkout / "tools/nro_exports.py"), str(d / "romfs"), str(d / "ref.tsv")], capture_output=True, text=True)
    c = subprocess.run([cli, "nro-exports", str(d / "romfs"), str(d / "c.tsv")], capture_output=True, text=True)
    ref_files = {"nro_exports.tsv": (d / "ref.tsv").read_bytes()} if (d / "ref.tsv").is_file() else {}
    c_files = {"nro_exports.tsv": (d / "c.tsv").read_bytes()} if (d / "c.tsv").is_file() else {}
    finish(name, ref.returncode, c, ref_files, c_files)


def nso_case(checkout, cli, work, name, files):
    d = fresh(work, name)
    (d / "romfs").mkdir()
    for rel, data in files.items():
        put(d / "romfs", rel, data)
    ref = subprocess.run([sys.executable, str(checkout / "runtime/rewriter/nro_to_nso.py"), str(d / "romfs"), str(d / "ref")], capture_output=True, text=True)
    c = subprocess.run([cli, "nro-to-nso", str(d / "romfs"), str(d / "c")], capture_output=True, text=True)
    finish(name, ref.returncode, c, snapshot(d / "ref"), snapshot(d / "c"))
    return d


def main():
    if len(sys.argv) != 4:
        raise SystemExit(__doc__)
    checkout, cli, work = Path(sys.argv[1]).resolve(), str(Path(sys.argv[2]).resolve()), Path(sys.argv[3]).resolve()
    work.mkdir(parents=True, exist_ok=True)
    VK, GL, OTHER = b"NintendoSDK_Vulkan-1_0_1234", b"NintendoSDK_OpenGL-4_5_77", b"NintendoSDK_Audio-2_3"

    # ---- gpu_driver_modules
    drivers_case(checkout, cli, work, "gpu-no-module", {"main": build_nso(), "sdk": build_nso([VK]), "main.npdm": b"META" + bytes(60)})
    drivers_case(checkout, cli, work, "gpu-no-driver", {"main": build_nso(), "subsdk0": build_nso([OTHER])})
    drivers_case(checkout, cli, work, "gpu-one", {"main": build_nso(), "subsdk0": build_nso([OTHER]), "subsdk1": build_nso([VK])})
    drivers_case(checkout, cli, work, "gpu-several", {"subsdk0": build_nso([GL]), "subsdk1": build_nso([OTHER]), "subsdk2": build_nso([VK]), "subsdk10": build_nso([VK]),
                                                     "rtld": build_nso([VK]), "sdk": build_nso([VK]), "main.npdm": b"META" + bytes(60), "notes.txt": b"x"})
    drivers_case(checkout, cli, work, "gpu-smallest-component-decides", {"a": build_nso([VK, b"NintendoSDK_Aaa-1_0"]), "b": build_nso([b"NintendoSDK_nnSdk-1_0", GL]),
                                                                    "c": build_nso([b"NintendoSDK_OpenGLES-3_2", VK])})
    drivers_case(checkout, cli, work, "gpu-lz4-segments", {"subsdk0": build_nso([VK], compress=True), "subsdk1": build_nso([OTHER], compress=True)})
    drivers_case(checkout, cli, work, "gpu-empty-exefs", {})
    drivers_case(checkout, cli, work, "gpu-bad-mod0", {"subsdk0": build_nso([VK], bad_mod0=True)})
    drivers_case(checkout, cli, work, "gpu-truncated-nso", {"subsdk0": b"NSO0" + bytes(0x20)})
    good = build_nso([VK], compress=True)
    drivers_case(checkout, cli, work, "gpu-corrupt-lz4", {"subsdk0": good[:0x100] + b"\xff" * (len(good) - 0x100)})

    # ---- nro_exports.py
    n1 = build_nro(1, syms=((b"fn_a", 0x12, 1), (b"fn_b", 0x22, 2), (b"undef", 0x12, 0), (b"local", 0x02, 1), (b"bad\xff\xfename", 0x12, 1), ("日本".encode(), 0x12, 1)))
    n2 = build_nro(2, syms=((b"other", 0x12, 1),))
    exports_case(checkout, cli, work, "exports-no-nro", {"data/file.bin": b"abc"})
    exports_case(checkout, cli, work, "exports-empty-table", {"a.nro": build_nro(1, syms=((b"undef", 0x12, 0), (b"local", 0x02, 1)))})
    exports_case(checkout, cli, work, "exports-nonempty-mixed-case", {"x.nro": n1, "Y.NRO": n2, "z.Nro": n1})
    exports_case(checkout, cli, work, "exports-nested-sorted", {"a.nro": n1, "a/b.nro": n2, "B.nro": n2, "a/B/c.nro": n1, ".dot/e.nro": n2, "._junk.nro": b"junk", ".DS_Store": b"x",
                                                           "deep/er/still/f.NRO": n1, "dir.nro/inner.bin": b"not a file entry"})
    exports_case(checkout, cli, work, "exports-header-size-not-checked", {"a.nro": build_nro(1, size=0x4000)})
    exports_case(checkout, cli, work, "exports-malformed-no-magic", {"a.nro": n1, "b.nro": build_nro(2, magic=False)})
    exports_case(checkout, cli, work, "exports-malformed-no-mod0", {"a.nro": build_nro(1, mod0=False)})
    exports_case(checkout, cli, work, "exports-malformed-truncated", {"a.nro": n1[:0x1100]})

    # ---- nro_to_nso.py
    nso_case(checkout, cli, work, "nso-no-nro", {"data/file.bin": b"abc"})
    d = nso_case(checkout, cli, work, "nso-one", {"x.nro": n1})
    report("nro_modules.tsv" in snapshot(d / "c") and "nro0" in snapshot(d / "c"), "nso-one-outputs-exist", "nro0 and nro_modules.tsv")
    nso_case(checkout, cli, work, "nso-several-nested-mixed-case", {"a/x.nro": n1, "b/X.NRO": n1, "z.nro": n2, "a.nro": build_nro(3), "a/b/c.Nro": build_nro(4),
                                                                   "B.nro": build_nro(5), "._junk.nro": b"junk", "dir.nro/inner.bin": b"x", "data/other.bin": b"y"})
    nso_case(checkout, cli, work, "nso-malformed-size-mismatch", {"a.nro": n1, "b.nro": build_nro(2, size=0x4000)})
    nso_case(checkout, cli, work, "nso-malformed-no-magic", {"a.nro": build_nro(1, magic=False)})
    nso_case(checkout, cli, work, "nso-malformed-no-mod0", {"a.nro": build_nro(1, mod0=False)})
    nso_case(checkout, cli, work, "nso-malformed-short", {"a.nro": n1[:0x40]})
    nso_case(checkout, cli, work, "nso-nrr-registers-present-nro", {"a.nro": n1, "z.nro": n2, ".nrr/r.nrr": build_nrr([sha(n2), sha(n1), sha(n2)]), ".nrr/readme.txt": b"ignored"})
    nso_case(checkout, cli, work, "nso-nrr-bad-magic", {"a.nro": n1, ".nrr/r.nrr": build_nrr([sha(n1)], magic=b"XXXX")})
    nso_case(checkout, cli, work, "nso-nrr-short", {"a.nro": n1, ".nrr/r.nrr": bytes(0x300)})
    nso_case(checkout, cli, work, "nso-nrr-table-out-of-range", {"a.nro": n1, ".nrr/r.nrr": build_nrr([sha(n1)])[:0x360]})

    # ---- unsupported: hashes only findable by scanning other files (raw or zstd); C only
    for name, files in (("unsupported-nrr-hash-not-in-nro-files", {"a.nro": n1, ".nrr/r.nrr": build_nrr([sha(n1), sha(b"hidden nro")]), "data.arc": b"\x28\xb5\x2f\xfd" + bytes(64)}),
                        ("unsupported-nrr-without-any-nro-file", {".nrr/r.nrr": build_nrr([sha(b"hidden nro")])})):
        d = fresh(work, name)
        for rel, data in files.items():
            put(d / "romfs", rel, data)
        c = subprocess.run([cli, "nro-to-nso", str(d / "romfs"), str(d / "c")], capture_output=True, text=True)
        report(c.returncode == 3 and not (d / "c" / "nro_modules.tsv").exists(), name, f"C exit {c.returncode}, want 3: {c.stdout.strip()}")

    print(f"{state['ran']} cases, {state['failed']} failed")
    if state["failed"] or state["ran"] < 12:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
