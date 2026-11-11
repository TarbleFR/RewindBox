#!/usr/bin/env python3
"""Compares the on-phone pack writers with S2Arm's own chain on synthetic export folders (CI only).

Usage: run_pack_test.py <s2arm_checkout> <s2a-rewrite> <s2arm_prepare_cli> <work_dir> [<nx_unpack command>]
       run_pack_test.py --mine-only <s2arm_prepare_cli> <work_dir>   (local: our chains only, code stage faked)

Reference chain, each step by S2Arm's tool as its packing pipeline calls it: pack/ns2_dump.py; the code
stage of run_code_stage_test.reference (addr_need.py, nro_to_nso.py, s2a-rewrite, nro_exports.py,
profile_guess.py --gpu-drivers); pack/gen_caps.sh --both with S2A_CAPS_TARGET=apple (pack/stage_caps.sh);
graphics/tools/direct/runtime_only_lib.sh and the move pack/stage_direct.sh makes; pack/ship_ext.py
place_game with the per-game steps of its container command (icon, banner, save_identity.py --check,
ctx_text); pack/pkg_srcs.py srcs + pack/pack.py.
Our chains: s2arm_prepare_cli ns2-dump, code, caps, direct-skeleton, module-dir, resource-pack, once on
a copied product root and once with --reference (RomFS and DLC read in place through relative links).
Compared after every stage: the product root (rewriter logs aside, .ns2_dump_key by presence), the
module directory and the image pack byte for byte, the resource pack (index.tsv and manifest.json byte
for byte, every file read through our links equal to S2Arm's copy, a link present on both sides compared
as a string). A stage where S2Arm fails must fail on our side too. All input is synthetic.
"""
import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import make_synth_exefs  # noqa: E402
import make_synth_nso as synth  # noqa: E402
import run_ns2_dump_test as ns2  # noqa: E402  (its export-folder helpers and tree())

TID = ns2.TID
GID = f'{TID:016X}'
TAG = 'ci-skeleton0'   # the inputs tag of the empty direct library (stage_direct.sh: 12 characters of its key)
LITTER = ('.DS_Store',)
state = {'ran': 0, 'failed': 0}


def report(ok, name, detail):
    state['ran'] += 1
    state['failed'] += not ok
    print(f"{'ok  ' if ok else 'FAIL'} {name} ({detail})", flush=True)


def w(path, data):
    ns2.w(path, data if isinstance(data, bytes) else data.encode())


# ---------------- synthetic export folders ----------------
def module(code=None, build_id=None, marker=b'', dynamic=True):
    """make_synth_nso's module with a dynamic section (profile_guess reads every NSO's symbols) and an
    optional marker string in its read-only segment, past the structures the builder writes."""
    data = bytearray(synth.build(code, build_id, dynamic=dynamic))
    if marker:
        at = 0x100 + synth.SEG + 0x800
        data[at:at + len(marker)] = marker
    return bytes(data)


def exefs(directory, marker=None, build=0x11, static_module=False):
    """marker None: make_synth_exefs's ExeFS, the one run_code_stage_test.py rewrites (main and sdk
    without dynamic section: the engine rule raises and counts as not found). Else every module with
    a dynamic section, main carrying the marker (b'' for none), and optionally one module without."""
    if marker is None:
        saved = sys.argv
        sys.argv = ['make_synth_exefs.py', str(directory)]
        try:
            make_synth_exefs.main()
        finally:
            sys.argv = saved
        w(directory / 'main', synth.build(build_id=bytes([build]) * 16))
        w(directory / 'main.npdm', make_synth_exefs.npdm(TID))
        return
    w(directory / 'main', module(marker=marker, build_id=bytes([build]) * 16))
    w(directory / 'main.npdm', make_synth_exefs.npdm(TID))
    w(directory / 'sdk', module(make_synth_exefs.SDK, bytes([0x53, 0x44]) + bytes(14)))
    w(directory / 'subsdk0', module(make_synth_exefs.SUBSDK0, bytes([0x53, 0x30]) + bytes(14)))
    if static_module:   # no dynamic section: profile_guess raises on it, the engine rule then counts as not found
        w(directory / 'subsdk1', module(make_synth_exefs.SUBSDK0, bytes([0x53, 0x31]) + bytes(14), dynamic=False))


def make_export(root, marker=None, romfs=None, delta=False, static_module=False):
    """base (+ a delta update when asked), an exported control folder with an icon, one DLC."""
    root = Path(root)
    exefs(root / 'base/exefs', marker, static_module=static_module)
    files = romfs if romfs is not None else {'Data/a.bin': b'alpha', 'Data/sub/b.bin': b'beta' * 300, 'top.txt': b'top\n'}
    for rel, data in files.items():
        w(root / 'base/romfs' / rel, data)
    w(root / 'base/control/control.nacp', ns2.nacp(b'Pack Test', b'', b'\xe6\xb5\x8b\xe8\xaf\x95', b'1.0.0'))
    w(root / 'base/control/icon_AmericanEnglish.dat', b'\xff\xd8\xff synthetic icon')
    if delta:   # no file identical to the base: the base overlaid by the update (per-file links in --reference)
        u = root / 'updates/65536'
        exefs(u / 'exefs', marker, build=0x12, static_module=static_module)
        w(u / 'romfs/Data/a.bin', b'alpha, updated')
        w(u / 'romfs/Data/new.bin', b'new in the update')
    w(root / 'dlc/040074a01bf13001/0/romfs/dlc.bin', b'dlc one')
    return root


TABLES = {   # every name of pkg_srcs.app_tables() a stage may leave in the root, decoys, and caps sources
    'widen_enable.handheld.tsv': '# synthetic\n0x1000\t1\n',
    'widen_enable.tsv': 'decoy: a caps source, not a shell table\n',
    'widen_full.docked.tsv': 'x\n',
    'widen_verified.tsv': 'verified\n',
    'cpatch.tsv': '\u7f16\u53f7\t\u540d\u79f0\nwidescreen:w1\tWide\nfps:f1\tFps\n',   # 编号 / 名称
    'fps.tsv': 'speed 1\n',
    'extra.widen.tsv': '0x10\t1\n',
    'notes.txt': 'not a table\n',
}
IDENTITY = {'id': GID, 'name': 'Pack Test \u00e9 "q"', 'version': 65536, 'contentIdentity': 'ab' * 32}


# ---------------- the two chains ----------------
class Chains:
    def __init__(self, checkout, rewriter, cli, work, nx_unpack, mine_only):
        self.checkout, self.rewriter, self.cli, self.work = checkout, rewriter, cli, work
        self.nx_unpack, self.mine_only = nx_unpack, mine_only
        self.chain_version = self.direct_chain() if checkout else '0123456789ab'

    def run(self, command, env=None, cwd=None):
        r = subprocess.run([str(c) for c in command], capture_output=True, text=True, env=env, cwd=cwd)
        return r.returncode, (r.stdout + r.stderr).strip()

    def env(self, **extra):
        e = {k: v for k, v in os.environ.items() if not k.startswith('S2A_') and k != 'IPA_APP_TABLES'}
        e.update(extra)
        return e

    def direct_chain(self):
        rc, out = self.run([sys.executable, '-c', 'import dmsh_chain; print(dmsh_chain.version())'], env=self.env(),
                           cwd=self.checkout / 'translator')
        if rc or not out:
            raise SystemExit(f'cannot read the direct library chain version: {out}')
        return out.splitlines()[-1]

    # --- reference steps (S2Arm) ---
    def ref_unpack(self, export, root):
        env = self.env(**({'S2A_NX_UNPACK': str(self.nx_unpack)} if self.nx_unpack else {}))
        return self.run([sys.executable, self.checkout / 'pack/ns2_dump.py', export, root], env=env)

    def ref_code(self, root):
        import run_code_stage_test as code_stage
        failed = code_stage.reference(self.checkout, self.rewriter, root / 'exefs', root / 'romfs', root)
        return (1, f'code stage failed at {failed}') if failed else (0, '')

    def ref_caps(self, root):
        return self.run(['bash', self.checkout / 'pack/gen_caps.sh', 'synthetic', root, root / 's2a_caps.tsv', '--both', root / 's2a_caps.all.tsv'],
                        env=self.env(S2A_CAPS_TARGET='apple', S2A_ROMFS_WALK='off'))

    def ref_direct(self, root, reason):
        script = ('D=$1/direct.tmp; rm -rf "$D" "$1/shaders/direct"; '
                  'TID=$(awk -F\'\\t\' \'$1 == "title_id" {print toupper($2); exit}\' "$1/unpack.tsv" 2> /dev/null) && [ -n "$TID" ] '
                  '&& bash "$2/graphics/tools/direct/runtime_only_lib.sh" "$D" "$3" "$TID" "$4" "$5" && mkdir -p "$1/shaders" && mv "$D" "$1/shaders/direct"')
        return self.run(['bash', '-c', script, 'stage_direct', root, self.checkout, self.chain_version, TAG, reason], env=self.env())

    def ref_module_dir(self, root, app):
        return self.run([sys.executable, Path(__file__).resolve(), '--reference-module-dir', self.checkout, root, app], env=self.env())

    def ref_pack(self, root, pack):
        srcs = subprocess.run([sys.executable, str(self.checkout / 'pack/pkg_srcs.py'), 'srcs', str(root)], capture_output=True, text=True,
                              env=self.env())
        if srcs.returncode:
            return srcs.returncode, (srcs.stdout + srcs.stderr).strip()
        listing = Path(str(pack) + '.srcs')   # beside the pack, as pack.py's own <pack>.state.tsv
        listing.parent.mkdir(parents=True, exist_ok=True)
        listing.write_text(srcs.stdout, encoding='utf-8')
        return self.run([sys.executable, self.checkout / 'pack/pack.py', pack, f'@{listing}'], env=self.env(J='2'))

    # --- our steps ---
    def our_unpack(self, export, root, views):
        return self.run([self.cli, 'ns2-dump', export, root, *(['--reference'] if views else [])])

    def our_code(self, root):
        if self.mine_only:
            return fake_code_stage(root)
        rc, out = self.run([self.cli, 'code', root / 'exefs', root / 'romfs', root])
        return (1 if rc else 0), out

    def our_caps(self, root):
        return self.run([self.cli, 'caps', root, root / 's2a_caps.tsv', root / 's2a_caps.all.tsv'])

    def our_direct(self, root, reason):
        return self.run([self.cli, 'direct-skeleton', root, self.chain_version, TAG, reason])

    def our_module_dir(self, root, app, identity):
        extra = ['--save-identity', identity['id'], identity['name'], str(identity['version']), identity['contentIdentity']] if identity else []
        return self.run([self.cli, 'module-dir', root, app / 'Games' / GID, '--images', app / f'Frameworks/S2AImages-{GID}.dylib', '--launch-ctx', *extra])

    def our_pack(self, root, pack, systemdata):
        extra = ['--systemdata', systemdata, '--link-systemdata'] if systemdata else []
        return self.run([self.cli, 'resource-pack', root, pack, *extra, '--applied'])


def fake_code_stage(root):
    """--mine-only: the rewriter is not available locally; write what it leaves, with a fixed layout."""
    for name in sorted(p.name for p in (root / 'exefs').iterdir() if p.is_file() and p.read_bytes()[:4] == b'NSO0'):
        if name == 'rtld':
            continue
        w(root / f'{name}.fixups.tsv', '# PATCH_OFF\t0xc000\n# KEY_PAGE_OFF\t0x8000\n# KEY_PAGE_SIZE\t0x4000\n# TEXT_END\t0x1100\n0x10\tx\n')
        w(root / f'{name}.gates.tsv', '0x100\tsvc\t1\t0x0\n')
        w(root / f'{name}.patched.bin', bytes((i * 7 + len(name)) & 255 for i in range(0xC000 + 0x2004)))
    shutil.copyfile(root / 'exefs/main.npdm', root / 'main.npdm')
    w(root / 'addr_need.tsv', 'synthetic\n')
    w(root / 'gpu_drivers.tsv', '')
    return 0, 'faked'


# ---------------- trees ----------------
def follow_tree(root, tops):
    """{relative path: bytes, or 'dir'} read through symlinks (followed); the links must be relative and
    resolve inside one of tops. Returns (tree, links, problem)."""
    out, links, root = {}, [0], Path(root)
    real_tops = [os.path.realpath(t) for t in tops]

    def visit(p, rel):
        for name in sorted(os.listdir(p)):
            q, r = p / name, (rel + '/' if rel else '') + name
            if q.is_symlink():
                links[0] += 1
                target, real = os.readlink(q), os.path.realpath(q)
                if os.path.isabs(target) or not os.path.exists(real) or not any(os.path.commonpath([real, t]) == t for t in real_tops):
                    return f'link {r} -> {target}'
            if q.is_dir():
                out[r + '/'] = 'dir'
                problem = visit(q, r)
                if problem:
                    return problem
            elif name == '.ns2_dump_key':
                out[r] = 'key'
            else:
                out[r] = q.read_bytes()
        return None
    if not root.is_dir():
        return None, 0, 'missing'
    problem = visit(root, '')
    return out, links[0], problem


def without(tree, names=(), suffixes=()):
    return {k: v for k, v in (tree or {}).items() if Path(k.rstrip('/')).name not in names and not k.endswith(suffixes)}


def differ(a, b):
    return sorted(k for k in set(a) | set(b) if a.get(k) != b.get(k))


def litter(name):
    base = Path(name.rstrip('/')).name
    return base in LITTER or base.startswith('._')


# ---------------- one case ----------------
STAGES = ('unpack', 'code', 'tables', 'caps', 'direct', 'module', 'pack')


def case(ch, name, export, *, tables=None, identity=None, systemdata=None, mutate=None, views=True, expect_fail=None, engine=None):
    """mutate: {stage: function(root)} applied to every product root just before that stage."""
    d = ch.work / name
    shutil.rmtree(d, ignore_errors=True)
    d.mkdir(parents=True)
    reason = d / 'direct_gap.txt'
    reason.write_text('synthetic: no shader extraction in this test\n', encoding='utf-8')
    sysdir = None
    if systemdata:
        sysdir = d / 'systemdata-src'
        for rel, data in systemdata.items():
            w(sysdir / rel, data)
    sides = ([] if ch.mine_only else ['ref']) + ['copy'] + (['view'] if views else [])
    roots = {s: d / f'{s}-root' for s in sides}
    apps = {s: d / f'{s}-app' for s in sides}
    packs = {s: d / f'{s}-docs/games/{GID}/pack' for s in sides}
    results = {}

    def step(side, stage):
        root = roots[side]
        if mutate and stage in mutate and stage != 'unpack':
            try:
                mutate[stage](root)
            except OSError as e:
                return 99, f'the test could not prepare the root: {e}'
        if stage == 'unpack':
            return ch.ref_unpack(export, root) if side == 'ref' else ch.our_unpack(export, root, side == 'view')
        if stage == 'code':
            return ch.ref_code(root) if side == 'ref' else ch.our_code(root)
        if stage == 'tables':
            for n, text in (tables or {}).items():
                w(root / n, text)
            if identity:   # S2Arm reads it from the root (save_identity.py --check rewrites it); ours gets the values
                w(root / 'save-identity.json', json.dumps(identity, ensure_ascii=False, indent=2) + '\n')
            if systemdata:   # <root>/systemdata everywhere; the view chain's pack links the shared tree instead
                shutil.copytree(sysdir, root / 'systemdata')
            w(root / 'banner.jpg', b'\xff\xd8 synthetic banner')
            return 0, ''
        if stage == 'caps':
            return ch.ref_caps(root) if side == 'ref' else ch.our_caps(root)
        if stage == 'direct':
            return ch.ref_direct(root, reason) if side == 'ref' else ch.our_direct(root, reason)
        if stage == 'module':
            return ch.ref_module_dir(root, apps[side]) if side == 'ref' else ch.our_module_dir(root, apps[side], identity)
        if stage == 'pack':
            return ch.ref_pack(root, packs[side]) if side == 'ref' else ch.our_pack(root, packs[side], sysdir if side == 'view' else None)

    for stage in STAGES:
        for side in sides:
            results[(side, stage)] = step(side, stage)
        rcs = {s: results[(s, stage)][0] for s in sides}
        lead = 'ref' if 'ref' in sides else 'copy'
        if expect_fail == stage and rcs[lead] == 0:
            report(False, name, f'{lead} succeeds at {stage}, the case expects a failure there')
            return
        if rcs[lead] != 0:
            ok = all(rc != 0 for rc in rcs.values()) and expect_fail == stage
            lasts = {s: (results[(s, stage)][1].splitlines() or [''])[-1][-140:] for s in sides}
            report(ok, name, f'{stage} fails on every side as expected: {lasts}' if ok else f'{stage}: rc {rcs}; {lasts}')
            return
        if any(rc != 0 for rc in rcs.values()):
            bad = {s: results[(s, stage)][1][-300:] for s in sides if rcs[s]}
            report(False, name, f'{stage}: {lead} succeeds, ours fails: {bad}')
            return
        problem = compare(ch, name, stage, sides, lead, roots, apps, packs, export, sysdir, engine, results)
        if problem:
            report(False, name, f'after {stage}: {problem}')
            return
    if expect_fail:
        report(False, name, f'every stage succeeded, the case expects a failure at {expect_fail}')
        return
    links = {s: follow_tree(packs[s], [export, roots[s]] + ([sysdir] if sysdir else []))[1] for s in sides if s != 'ref'}
    report(True, name, f'{len(sides)} chains identical through the resource pack; links in our packs {links}')


def compare(ch, name, stage, sides, lead, roots, apps, packs, export, sysdir, engine, results):
    ours = [s for s in sides if s != lead]
    if stage in ('unpack', 'code', 'tables', 'caps', 'direct'):
        want = without(ns2.tree(roots[lead]), suffixes=('.rewrite.log',))
        for s in ours:
            got, _, problem = follow_tree(roots[s], [export])
            if problem:
                return f'{s} root: {problem}'
            got = without(got, suffixes=('.rewrite.log',))
            diff = differ(want, got)
            if diff:
                return f'{s} root differs from {lead}: {diff[:8]}'
        if stage == 'caps' and engine is not None:
            out = results[('copy', 'caps')][1]
            if f'engine_l1={engine}' not in out:
                return f'engine rule: expected engine_l1={engine}, got {out!r}'
        return None
    if stage == 'module':
        want = ns2.tree(apps[lead] / 'Games' / GID)
        image = (apps[lead] / f'Frameworks/S2AImages-{GID}.dylib').read_bytes()
        for s in ours:
            got = ns2.tree(apps[s] / 'Games' / GID)
            diff = differ(want or {}, got or {})
            if diff or want is None:
                return f'{s} module directory differs from {lead}: {diff[:8]}'
            if (apps[s] / f'Frameworks/S2AImages-{GID}.dylib').read_bytes() != image:
                return f'{s} image pack differs from {lead} ({len(image)} bytes)'
            if sorted(os.listdir(apps[s])) != sorted(os.listdir(apps[lead])) or sorted(os.listdir(apps[s] / 'Frameworks')) != [f'S2AImages-{GID}.dylib']:
                return f'{s}: unexpected files beside the module directory: {sorted(os.listdir(apps[s]))}'
        return None
    if stage == 'pack':
        want = ns2.tree(packs[lead]) if lead == 'ref' else follow_tree(packs[lead], [export, roots[lead]] + ([sysdir] if sysdir else []))[0]
        want = without(want, names=('.applied', 'index.applied.tsv'))
        index = (packs[lead] / 'index.tsv').read_bytes()
        manifest = (packs[lead] / 'manifest.json').read_bytes()
        for s in ours:
            p = packs[s]
            if (p / 'index.tsv').read_bytes() != index or (p / 'manifest.json').read_bytes() != manifest:
                return f'{s} index.tsv / manifest.json differ from {lead}'
            m = json.loads(manifest)
            if (p / '.applied').read_bytes() != m['index_sha256'].encode() or (p / 'index.applied.tsv').read_bytes() != index:
                return f'{s}: .applied / index.applied.tsv are not the bookkeeping of pack_apply'
            if hashlib.sha256(index).hexdigest() != m['index_sha256']:
                return f'{s}: manifest index_sha256 does not match index.tsv'
            got, _, problem = follow_tree(p, [export, roots[s]] + ([sysdir] if sysdir else []))
            if problem:
                return f'{s} pack: {problem}'
            got = without(got, names=('.applied', 'index.applied.tsv'))
            extra = [k for k in differ(want, got) if k not in want and litter(k)]   # left out of index.tsv, visible through the links
            diff = [k for k in differ(want, got) if k not in extra]
            if diff:
                return f'{s} pack differs from {lead} (through the links): {diff[:8]}'
            for k in want if lead == 'ref' else ():   # a symlink on both sides: same target string (our two chains link different roots)
                a, b = packs[lead] / k.rstrip('/'), p / k.rstrip('/')
                if a.is_symlink() and b.is_symlink() and os.readlink(a) != os.readlink(b):
                    return f'{s}: link {k} -> {os.readlink(b)}, {lead} -> {os.readlink(a)}'
        return None
    return None


# ---------------- the reference module directory (run in a child process) ----------------
def reference_module_dir(checkout, root, app):
    """pack/ship_ext.py container, the per-game part, with S2Arm's own functions."""
    import importlib.util

    def load(name, path):
        spec = importlib.util.spec_from_file_location(name, path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    ship_ext = load('ship_ext', checkout / 'pack/ship_ext.py')
    pkg_srcs = load('pkg_srcs', checkout / 'pack/pkg_srcs.py')
    tables = pkg_srcs.app_tables()
    ship_ext.check_root(root)
    gid, _ = ship_ext.npdm_ident(root / 'main.npdm')
    gd = app / ship_ext.GAMES / gid
    ship_ext.place_game(root, gd, app / ship_ext.game_images(gid), tables)
    if (root / 'icon.jpg').is_file():
        shutil.copyfile(root / 'icon.jpg', gd / 'icon.jpg')
    ship_ext._place_banner(gid, root, gd, {}, None)
    si = root / 'save-identity.json'
    if si.is_file():
        c = subprocess.run([sys.executable, str(checkout / 'pack/save_identity.py'), '--check', str(si), '--output', str(gd / 'save-identity.json')])
        if c.returncode:
            sys.exit(1)
    (gd / ship_ext.CTX).write_text(ship_ext.ctx_text(gid), encoding='utf-8', newline='\n')
    print(f'module directory {gd}, tables {" ".join(tables)}')


def main():
    a = sys.argv[1:]
    if a[:1] == ['--reference-module-dir']:
        reference_module_dir(Path(a[1]), Path(a[2]), Path(a[3]))
        return
    mine_only = a[:1] == ['--mine-only']
    if mine_only:
        checkout, rewriter, cli, work, nx_unpack = None, None, Path(a[1]).resolve(), Path(a[2]).resolve(), None
    else:
        checkout, rewriter, cli, work = Path(a[0]).resolve(), Path(a[1]).resolve(), Path(a[2]).resolve(), Path(a[3]).resolve()
        nx_unpack = Path(a[4]).resolve() if len(a) > 4 else None
    shutil.rmtree(work, ignore_errors=True)
    work.mkdir(parents=True)
    ch = Chains(checkout, rewriter, cli, work, nx_unpack, mine_only)
    inputs = work / 'inputs'

    if checkout:
        # The premise of the caps port: S2Arm's registries say nothing about the synthetic program id.
        registries = sorted((checkout / 'docs').glob('名单_*.tsv')) + sorted((checkout / 'docs').glob('名单_*/*.tsv'))   # 名单_*
        listed = [str(p.relative_to(checkout)) for p in registries if GID.lower() in p.read_text(encoding='utf-8', errors='replace').lower()]
        report(not listed, 'registries-silent-on-the-synthetic-game', f'{GID} listed in {listed}' if listed else f'{GID} in no registry')
        # The shell's table list compiled into the module directory writer.
        rc, out = ch.run([sys.executable, checkout / 'pack/pkg_srcs.py', 'app-tables'], env=ch.env())
        source = (HERE.parent.parent / 'native/s2arm/prepare/s2arm_pack.c').read_text(encoding='utf-8')
        start = source.index('APP_TABLES[] = {')
        ours = [s.strip().strip('"') for s in source[start + len('APP_TABLES[] = {'):source.index('};', start)].split(',') if s.strip()]
        report(rc == 0 and out.split() == ours, 'app-tables', f'S2Arm {out.split()}, ours {ours}')
        report(len(ch.chain_version) == 12, 'direct-chain-version', ch.chain_version)

    plain = make_export(inputs / 'Plain')
    case(ch, 'plain', plain, engine=0)
    case(ch, 'tables-identity-systemdata', make_export(inputs / 'Tables'), tables=TABLES, identity=IDENTITY,
         systemdata={'fonts/synthetic.bfttf': b'font', '0100000000000802/data.bin': b'mii', '010000000000080E/zoneinfo/UTC': b'TZif'})
    case(ch, 'delta-update-per-file-links', make_export(inputs / 'Delta', delta=True))
    case(ch, 'litter-in-romfs', make_export(inputs / 'Litter', romfs={'Data/a.bin': b'a', 'Data/._a.bin': b'mac', '.DS_Store': b'mac', 'b.bin': b'b'}))
    # The engine rule (fps60 from Unity / Unreal with .pak or .utoc data; any exception means no engine)
    case(ch, 'engine-unity', make_export(inputs / 'Unity', marker=b'UnityEngine\0'), engine=1)
    case(ch, 'engine-unreal-pak', make_export(inputs / 'Unreal', marker=b'Unreal\0', romfs={'Game/Content/Paks/a.PAK': b'pak', 'x.bin': b'x'}), engine=1)
    case(ch, 'engine-unreal-without-pak', make_export(inputs / 'UnrealNoPak', marker=b'Unreal\0'), engine=0)
    case(ch, 'engine-unity-with-a-module-without-symbols', make_export(inputs / 'UnityStatic', marker=b'UnityEngine\0', static_module=True), engine=0)

    # failures (copy chain only: the mutations would write into the export folder through the links)
    def drop_line(key):
        def f(root):
            p = root / 'main.fixups.tsv'
            p.write_text(''.join(l for l in p.read_text(encoding='utf-8').splitlines(True) if not l.startswith(f'# {key}')), encoding='utf-8')
        return f

    def truncate(root):
        p = root / 'main.patched.bin'
        p.write_bytes(p.read_bytes()[:0x200])

    case(ch, 'image-pack-header-without-patch-off', plain, mutate={'module': drop_line('PATCH_OFF')}, views=False, expect_fail='module')
    case(ch, 'image-pack-truncated-patched-bin', plain, mutate={'module': truncate}, views=False, expect_fail='module')
    case(ch, 'module-dir-missing-gates', plain, mutate={'module': lambda r: (r / 'main.gates.tsv').unlink()}, views=False, expect_fail='module')
    case(ch, 'module-dir-invalid-save-identity', plain, identity=dict(IDENTITY, id='not hex'), views=False, expect_fail='module')
    case(ch, 'pack-without-romfs', plain, mutate={'pack': lambda r: shutil.rmtree(r / 'romfs')}, views=False, expect_fail='pack')
    case(ch, 'pack-tab-in-a-path', plain, mutate={'pack': lambda r: w(r / 'romfs/Data/a\tb.bin', b'tab')}, views=False, expect_fail='pack')

    print(f"{state['ran']} cases, {state['failed']} failed")
    sys.exit(1 if state['failed'] or state['ran'] < (14 if mine_only else 17) else 0)


if __name__ == '__main__':
    main()
