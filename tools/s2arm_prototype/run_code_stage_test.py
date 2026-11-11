#!/usr/bin/env python3
"""Compares rb_s2arm_prepare_code with the same steps run by S2Arm's own tools (CI only).

Usage: run_code_stage_test.py <s2arm_checkout> <s2a-rewrite> <s2arm_prepare_cli> <work_dir> [<nx_unpack command>]

The reference is the core of pack/stage_rewrite.sh in its order, each step by the
original tool: addr_need.py, nro_to_nso.py, the rewriter command line per module
(spin gate on, Apple target), main.npdm, nro_exports.py, profile_guess.py
--gpu-drivers. Both sides get the same synthetic ExeFS/RomFS (no game content).
A successful reference needs the same files and bytes (rewriter logs aside);
a failing reference needs a failing library.

With <nx_unpack command> (an executable running S2Arm's nx_unpack), ZBIC cases are added:
the library gets an ExeFS whose modules are ZBIC-compressed (make_synth_zbic.py), the
reference gets the same ExeFS after `nx_unpack --nso-normalize` of every top-level file,
which is what S2Arm's unpack step hands to its code stage.
"""
import os
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import make_synth_exefs  # noqa: E402
import make_synth_zbic  # noqa: E402
import run_modules_test as fixtures  # noqa: E402  (only its synthetic NRO builder is used)

MODULES = ['main'] + [f'subsdk{i}' for i in range(10)] + ['sdk']
state = {'ran': 0, 'failed': 0}


def report(ok, name, detail):
    state['ran'] += 1
    state['failed'] += not ok
    print(f"{'ok  ' if ok else 'FAIL'} {name} ({detail})", flush=True)


def snapshot(root):
    return {str(p.relative_to(root)): p.read_bytes() for p in sorted(root.rglob('*'))
            if p.is_file() and not p.name.endswith('.rewrite.log')}


def reference(checkout, rewriter, exefs, romfs, out):
    """Returns 0, or the name of the first step that failed."""
    env = {k: v for k, v in os.environ.items() if not k.startswith('S2A_')}
    env['S2A_REWRITE_SPIN'] = '1'
    py = [sys.executable]
    build = (exefs / 'main').read_bytes()[0x40:0x50].hex() if (exefs / 'main').is_file() else '00' * 16

    def run(step, command, stdout=None):
        return step if subprocess.run(command, env=env, stdout=stdout or subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode else 0

    failed = run('addr_need', py + [str(checkout / 'tools/addr_need.py'), build, str(out / 'addr_need.tsv'),
                                    '--npdm', str(exefs / 'main.npdm'), '--key', '--main', str(exefs / 'main')])
    if failed:
        return failed
    nroexe = out / 'nroexe'
    if romfs:
        failed = run('nro_to_nso', py + [str(checkout / 'runtime/rewriter/nro_to_nso.py'), str(romfs), str(nroexe)])
        if failed:
            return failed
        if (nroexe / 'nro_modules.tsv').is_file():
            shutil.move(str(nroexe / 'nro_modules.tsv'), str(out / 'nro_modules.tsv'))
    inputs = [(exefs / m, m) for m in MODULES if (exefs / m).is_file()]
    if nroexe.is_dir():
        inputs += [(p, p.name) for p in sorted(nroexe.glob('nro*'))]
    for path, module in inputs:
        with open(out / f'{module}.rewrite.log', 'wb') as log:
            failed = run(f'rewrite {module}', [str(rewriter), str(path), str(out), module], stdout=log)
        if failed:
            return failed
    shutil.copyfile(exefs / 'main.npdm', out / 'main.npdm')
    if romfs:
        failed = run('nro_exports', py + [str(checkout / 'tools/nro_exports.py'), str(romfs), str(out / 'nro_exports.tsv')])
        if failed:
            return failed
    with open(out / 'gpu_drivers.tsv', 'wb') as table:
        failed = run('gpu_drivers', py + [str(checkout / 'graphics/nvn/games/profile_guess.py'), '--gpu-drivers', str(exefs)], stdout=table)
    shutil.rmtree(nroexe, ignore_errors=True)
    return failed


def normalised(nx_unpack, exefs, target):
    """S2Arm's unpack step for a ZBIC ExeFS: nx_unpack --nso-normalize on every top-level file."""
    target.mkdir(parents=True)
    for path in sorted(exefs.iterdir()):
        if path.is_file() and subprocess.run([str(nx_unpack), '--nso-normalize', str(path), str(target / path.name)],
                                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode:
            return None
    return target


def case(name, checkout, rewriter, cli, work, exefs, romfs, expect_success=None, nx_unpack=None):
    ref, mine = work / name / 'ref', work / name / 'out'
    for directory in (ref, mine):
        directory.mkdir(parents=True)
    ref_exefs = normalised(nx_unpack, exefs, work / name / 'ref-exefs') if nx_unpack else exefs
    failed = reference(checkout, rewriter, ref_exefs, romfs, ref) if ref_exefs else 'nx_unpack --nso-normalize'
    run = subprocess.run([str(cli), 'code', str(exefs), str(romfs) if romfs else '-', str(mine)], capture_output=True, text=True)
    last = (run.stdout.strip().splitlines() or [''])[-1]
    if expect_success is not None and (failed == 0) != expect_success:
        report(False, name, f'the reference {"failed at " + str(failed) if failed else "succeeded"}, the test expected otherwise')
        return
    if failed:
        report(run.returncode != 0, name, f'reference fails at {failed}; library: {last}')
        return
    a, b = snapshot(ref), snapshot(mine)
    different = sorted(k for k in set(a) | set(b) if a.get(k) != b.get(k))
    ok = run.returncode == 0 and not different
    report(ok, name, f'{len(a)} files identical' if ok else f'library: {last}; differing: {different[:8]}')


def main():
    checkout, rewriter, cli, work = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3]).resolve(), Path(sys.argv[4])
    nx_unpack = Path(sys.argv[5]).resolve() if len(sys.argv) > 5 else None
    shutil.rmtree(work, ignore_errors=True)
    work.mkdir(parents=True)

    def exefs(name, *flags):
        directory = work / 'inputs' / name
        saved = sys.argv
        sys.argv = ['make_synth_exefs.py', str(directory), *flags]
        try:
            make_synth_exefs.main()
        finally:
            sys.argv = saved
        return directory

    def romfs(name, files):
        directory = work / 'inputs' / name
        directory.mkdir(parents=True)
        for relative, data in files.items():
            path = directory / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
        return directory

    plain = exefs('exefs')
    arguments = (checkout, rewriter, cli, work)
    case('exefs-only', *arguments, plain, None, expect_success=True)
    case('romfs-without-nro', *arguments, plain, romfs('romfs-empty', {'data/readme.txt': b'synthetic\n'}), expect_success=True)
    # The synthetic NRO is built for the table tools; whether the rewriter accepts it is left to the reference.
    case('romfs-with-nro', *arguments, plain, romfs('romfs-nro', {'pkg/a.nro': fixtures.build_nro(1), 'pkg/b.NRO': fixtures.build_nro(2)}))
    case('unrewritable-code', *arguments, exefs('exefs-gap', '--gap'), None, expect_success=False)
    no_npdm = exefs('exefs-no-npdm')
    (no_npdm / 'main.npdm').unlink()
    case('missing-npdm', *arguments, no_npdm, None, expect_success=False)

    if nx_unpack:
        import random
        import struct
        zbic_exefs = exefs('exefs-zbic')
        for module, seed, extra in (('main', 1, 0x40), ('subsdk0', 2, 0), ('sdk', 3, 0)):
            data = (zbic_exefs / module).read_bytes()
            (zbic_exefs / module).write_bytes(make_synth_zbic.zbic_nso(data, random.Random(seed), extra_flags=extra))
        case('zbic-modules', *arguments, zbic_exefs, None, expect_success=True, nx_unpack=nx_unpack)
        case('zbic-modules-with-nro', *arguments, zbic_exefs, romfs('romfs-nro-zbic', {'pkg/a.nro': fixtures.build_nro(1)}),
             nx_unpack=nx_unpack)
        corrupt = exefs('exefs-zbic-corrupt')
        bad = bytearray(make_synth_zbic.zbic_nso((corrupt / 'main').read_bytes(), random.Random(4)))
        offset, size = struct.unpack_from('<I', bad, 0x10)[0], struct.unpack_from('<I', bad, 0x60)[0]
        bad[offset + size // 2:offset + size // 2 + 16] = b'\xAA' * 16
        (corrupt / 'main').write_bytes(bytes(bad))
        case('zbic-corrupt', *arguments, corrupt, None, expect_success=False, nx_unpack=nx_unpack)
        unknown = exefs('exefs-zbic-unknown-flag')
        data = bytearray(make_synth_zbic.zbic_nso((unknown / 'main').read_bytes(), random.Random(5)))
        data[0xD] |= 1   # flag bit 0x100: unknown to nx_unpack
        (unknown / 'sdk').write_bytes(bytes(data))
        main = make_synth_zbic.zbic_nso((unknown / 'main').read_bytes(), random.Random(6))
        (unknown / 'main').write_bytes(main)
        case('zbic-unknown-flag-bit', *arguments, unknown, None, expect_success=False, nx_unpack=nx_unpack)

    print(f"{state['ran']} cases, {state['failed']} failed")
    sys.exit(1 if state['failed'] or state['ran'] < (9 if nx_unpack else 5) else 0)


if __name__ == '__main__':
    main()
