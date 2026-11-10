#!/usr/bin/env python3
"""Differential audit of A64 liveness metadata against an independent decoder.

Optional local evidence, not a CI gate: it requires `capstone==6.0.0a4` (LLVM
TableGen-derived operand access). Seeded random encodings of every pinned
InstTable entry are decoded by the production A57 table and mask functions
(baseline = delivered preparation, candidate = plus adapt_register_liveness)
and by Capstone. Register and NZCV read/write sets are compared. Capstone is
an oracle with known gaps; remaining differences are listed and classified,
never silently accepted.
"""
from pathlib import Path
import collections, hashlib, json, random, re, shutil, struct, subprocess, sys, tempfile

import capstone

ROOT = Path(__file__).resolve().parents[1]
SOURCE = Path(sys.argv[1]).resolve()
sys.path.insert(0, str(ROOT / 'build-utils/melonx'))
from adapt_vector_register_masks import apply as vector_apply
from adapt_register_liveness import apply as liveness_apply

BASE = 'src/Ryujinx.Cpu/LightningJit/'
TABLE = BASE + 'Arm64/Target/Arm64/InstTable.cs'
REGISTERS = BASE + 'Arm64/RegisterUtils.cs'
SAMPLES = 24
# Differences that remain after the correction, with the reason they are not defects.
EXPLAINED = {
    ('Bl', 'missingWriteG'): 'Decoder.DecodeMulti adds LR for every IsCall instruction',
    ('Blr', 'missingWriteG'): 'Decoder.DecodeMulti adds LR for every IsCall instruction',
    ('Ld1AdvsimdSnglAsNoPostIndex', 'missingWriteG'): 'Capstone reports base writeback for a no-writeback form',
    ('Ld2AdvsimdSnglAsNoPostIndex', 'missingWriteG'): 'Capstone reports base writeback for a no-writeback form',
    ('Ld3AdvsimdSnglAsNoPostIndex', 'missingWriteG'): 'Capstone reports base writeback for a no-writeback form',
    ('Ld4AdvsimdSnglAsNoPostIndex', 'missingWriteG'): 'Capstone reports base writeback for a no-writeback form',
    ('Sysl', 'missingReadG'): 'SYSL writes Xt; Capstone reports a read',
    ('Sysl', 'extraWriteG'): 'SYSL writes Xt; Capstone reports a read',
    ('AutibSystem', 'missingReadG'): 'AUTIB1716 is a v8.3 hint, not Cortex-A57 guest code',
    ('AutibSystem', 'missingWriteG'): 'AUTIB1716 is a v8.3 hint, not Cortex-A57 guest code',
    ('MsrImm', 'missingNzcvRead'): 'AXFLAG/XAFLAG are v8.5 FlagM2 hints in MSR space, not A57 code',
    ('MsrImm', 'missingNzcvWrite'): 'AXFLAG/XAFLAG are v8.5 FlagM2 hints in MSR space, not A57 code',
    ('FmovFloatGen', 'extraReadV'): 'FMOV Vd.D[1], Xn keeps Vd<63:0> (Vpart[d,1]); Capstone omits the tied read',
}


def entries(text):
    pattern = re.compile(r'new\((0x[0-9A-Fa-f]+)u?,\s*(0x[0-9A-Fa-f]+)u?,(.*?)InstName\.(\w+),\s*IsaVersion\.(\w+),')
    return [(int(m.group(1), 16), int(m.group(2), 16), m.group(4), m.group(5)) for m in pattern.finditer(text)]


def harness(project, tree, words, output):
    lightning = SOURCE / BASE
    for name in ('Arm64/InstFlags.cs', 'Arm64/InstName.cs', 'IsaVersion.cs', 'IsaFeature.cs', 'AddressForm.cs',
                 'CpuPreset.cs', 'CpuPresets.cs'):
        shutil.copyfile(lightning / name, project / Path(name).name)
    for path in (lightning / 'Table').glob('*.cs'):
        shutil.copyfile(path, project / path.name)
    shutil.copyfile(tree / REGISTERS, project / 'RegisterUtils.cs')
    shutil.copyfile(tree / TABLE, project / 'InstTable.cs')
    (project / 'Stub.cs').write_text('namespace Ryujinx.Cpu.LightningJit.Arm64 { sealed class RegisterAllocator { public int RemapReservedGprRegister(int index) => index; } }\n')
    (project / 'Program.cs').write_text('''using System; using System.IO;
using Ryujinx.Cpu.LightningJit; using Ryujinx.Cpu.LightningJit.Arm64; using Ryujinx.Cpu.LightningJit.Arm64.Target.Arm64;
static class Program { static void Main(string[] a) {
 using var o = new StreamWriter(a[1]); var preset = CpuPresets.CortexA57;
 foreach (var line in File.ReadLines(a[0])) { uint w = Convert.ToUInt32(line, 16);
  var (n, f, _) = InstTable.GetInstNameAndFlags(w, preset.Version, preset.Features);
  var r = RegisterUtils.PopulateReadMasks(n, f, w); var x = RegisterUtils.PopulateWriteMasks(n, f, w);
  uint pr = 0, pw = 0;
  if (f.HasFlag(InstFlags.Nzcv) || (w & ~0x1fu) == 0xd53b4200u) pr = 0xfu << 28; else if (f.HasFlag(InstFlags.C)) pr = 1u << 29;
  if (f.HasFlag(InstFlags.S) || (w & ~0x1fu) == 0xd51b4200u) pw = 0xfu << 28;
  o.WriteLine($"{line} {n} {r.Item1:x8} {r.Item2:x8} {x.Item1:x8} {x.Item2:x8} {pr:x8} {pw:x8}"); } } }
''')
    (project / 'Audit.csproj').write_text('<Project Sdk="Microsoft.NET.Sdk"><PropertyGroup><OutputType>Exe</OutputType>'
                                          '<TargetFramework>net10.0</TargetFramework><LangVersion>preview</LangVersion>'
                                          '<NuGetAudit>false</NuGetAudit><ManagePackageVersionsCentrally>false</ManagePackageVersionsCentrally>'
                                          '</PropertyGroup></Project>')
    (project / 'global.json').write_text(json.dumps({'sdk': {'version': '10.0.100', 'rollForward': 'disable'}}))
    subprocess.run(['dotnet', 'run', '--project', str(project), '-c', 'Release', '-v', 'q', '--', str(words), str(output)],
                   check=True, timeout=600, capture_output=True)
    return [line.split() for line in output.read_text().splitlines()]


def access(md, word):
    insn = next(md.disasm(struct.pack('<I', word), 0x1000), None)
    if insn is None:
        return None
    read, write = insn.regs_access()
    def split(registers):
        g, v, flags = set(), set(), False
        for name in (insn.reg_name(r).lower() for r in registers):
            if name == 'nzcv':
                flags = True
            elif name in ('sp', 'wsp'):
                g.add(31)
            elif name in ('fp', 'lr'):
                g.add(29 if name == 'fp' else 30)
            elif re.fullmatch(r'[xw]\d+', name):
                g.add(int(name[1:]))
            elif re.fullmatch(r'[bhsdqv]\d+', name):
                v.add(int(name[1:]))
        return g, v, flags
    return insn.mnemonic + ' ' + insn.op_str, split(read), split(write)


def bits(value):
    return {i for i in range(32) if (int(value, 16) >> i) & 1}


def compare(rows, oracle, isa):
    found = collections.defaultdict(collections.Counter)
    example = {}
    for row in rows:
        word, name, rg, rv, wg, wv, pr, pw = row
        if isa[word] != 'v80' or name == 'UdfPermUndef' or oracle[word] is None:
            continue
        text, (crg, crv, crf), (cwg, cwv, cwf) = oracle[word]
        kinds = {'missingReadG': crg - bits(rg), 'missingReadV': crv - bits(rv), 'missingWriteG': cwg - bits(wg),
                 'missingWriteV': cwv - bits(wv), 'extraReadV': bits(rv) - crv, 'extraWriteG': bits(wg) - cwg,
                 'extraWriteV': bits(wv) - cwv, 'missingNzcvRead': crf and pr == '00000000',
                 'missingNzcvWrite': cwf and pw == '00000000', 'extraNzcvWrite': not cwf and pw != '00000000'}
        for kind, value in kinds.items():
            if value:
                found[name][kind] += 1
                example.setdefault(f'{name}/{kind}', f'{word} {text}')
    return found, example


pin = json.loads((ROOT / 'build-utils/melonx/source.json').read_text())
assert subprocess.check_output(['git', '-C', str(SOURCE), 'rev-parse', 'HEAD'], text=True).strip() == pin['revision']
with tempfile.TemporaryDirectory(prefix='melonx-liveness-audit-') as temporary:
    work = Path(temporary)
    trees = {}
    for kind in ('baseline', 'candidate'):
        tree = work / kind
        for name in (TABLE, REGISTERS):
            (tree / name).parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(SOURCE / name, tree / name)
        vector_apply(tree)
        if kind == 'candidate':
            liveness_apply(tree)
        trees[kind] = tree
    table = entries((trees['baseline'] / TABLE).read_text())
    md = capstone.Cs(capstone.CS_ARCH_AARCH64, capstone.CS_MODE_ARM)
    md.detail = True
    rng = random.Random(20261101)
    oracle, isa = {}, {}
    for encoding, mask, name, version in table:
        accepted = 0
        for _ in range(400):
            word = (rng.getrandbits(32) & ~mask) | encoding
            key = f'{word:08x}'
            if key in oracle:
                continue
            result = access(md, word)
            if result is None:
                continue
            oracle[key], isa[key] = result, version
            accepted += 1
            if accepted == SAMPLES:
                break
    words = work / 'words.txt'
    words.write_text('\n'.join(oracle) + '\n')
    results = {}
    for kind, tree in trees.items():
        project = work / ('project-' + kind)
        project.mkdir()
        found, example = compare(harness(project, tree, words, work / (kind + '.txt')), oracle, isa)
        results[kind] = (found, example)
    before, _ = results['baseline']
    after, examples = results['candidate']
    # A pre-existing extra read only loads a register early: it cannot lose a
    # guest value. It is reported, and must be unchanged by this correction.
    conservative = sorted(f'{name}/{kind}' for name, kinds in after.items() for kind, count in kinds.items()
                          if kind == 'extraReadV' and before.get(name, {}).get(kind) == count and (name, kind) not in EXPLAINED)
    unexplained = sorted(f'{name}/{kind}' for name, kinds in after.items() for kind in kinds
                         if (name, kind) not in EXPLAINED and f'{name}/{kind}' not in conservative)
    corrected = sorted(f'{name}/{kind}' for name, kinds in before.items() for kind in kinds
                       if kind.startswith('missing') or kind == 'extraNzcvWrite' if kind not in after.get(name, {}))
    report = dict(result='passed' if not unexplained else 'failed', oracle=f'capstone {capstone.__version__} (pip capstone==6.0.0a4)',
                  decoderPreset='CortexA57', samplesPerEntry=SAMPLES, encodings=len(oracle),
                  v80Encodings=sum(1 for value in isa.values() if value == 'v80'), tableEntries=len(table),
                  baseline={name: dict(kinds) for name, kinds in sorted(before.items())},
                  candidate={name: dict(kinds) for name, kinds in sorted(after.items())},
                  correctedFindings=corrected, unexplainedCandidateDifferences=unexplained,
                  unchangedConservativeExtraReads=conservative,
                  explainedCandidateDifferences={f'{n}/{k}': why for (n, k), why in sorted(EXPLAINED.items()) if k in after.get(n, {})},
                  candidateExamples={key: examples[key] for key in sorted(examples)},
                  generatedArm64Executed=False, physicalDeviceTested=False, upstreamRevision=pin['revision'],
                  inputs={str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in
                          [Path(__file__), ROOT / 'build-utils/melonx/adapt_register_liveness.py',
                           ROOT / 'build-utils/melonx/adapt_vector_register_masks.py']})
    out = ROOT / 'dist/melonx/register-liveness-audit.json'
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({key: report[key] for key in ('result', 'encodings', 'v80Encodings', 'unexplainedCandidateDifferences')}))
    print('corrected findings:', len(corrected))
    assert not unexplained, unexplained
