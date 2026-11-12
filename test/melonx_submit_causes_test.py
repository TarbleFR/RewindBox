#!/usr/bin/env python3
"""adapt_submit_causes on the final preparation, against the Core 741 preparation as control.

Usage: melonx_submit_causes_test.py <control> [--candidate-source <final preparation containing the adapter>]

Diagnostics only: every submission is counted under the cause its caller names, every host sync under the GPU-side site
that created it. Required:
 1. additive: each replacement adds counter or text lines only (removing them gives the control's text back); the
    signature of GpuContext.CreateHostSyncIfNeeded gains an optional [CallerMemberName] parameter and no call site passes
    it; the render stages line gains a suffix after its unchanged text;
 2. complete: every FlushAllCommands / FlushCommandsImpl call of the Vulkan backend names its cause on the line before (the
    forwarding inside VulkanRenderer.FlushAllCommands excepted); every CreateHostSyncIfNeeded call of the Gpu project sits
    in a method the site table names, in the file it names;
 3. built: the production Ryujinx.Graphics.Vulkan and Ryujinx.Graphics.Gpu assemblies build with the adapter, with no
    compiler warning in the edited files; a drifted file is refused;
 4. executed (test/melonx_submit_causes/Program.cs): the production RenderStageTimer of each tree and the candidate's host
    sync members, under a fake clock (spliced for RenderStageTimer.Now and the window's Stopwatch read): the control's
    render stages line is a prefix of the candidate's, byte for byte, and both parse with tools/melonx/frame_report.py; the
    suffix gives the scripted causes exactly and starts again from zero in the next window; a submission without a named
    cause is "other" and the cause returns to "other" after each submission; the host sync line gives every scripted site
    (method names as the compiler passes them) and no line before 5 s.
Nothing depends on time or scheduling. No device, no MoltenVK. Writes dist/melonx/submit-causes-checks.json.
"""
from pathlib import Path
import hashlib, json, os, re, shutil, subprocess, sys, tempfile

ROOT = Path(__file__).resolve().parents[1]
SOURCE = Path(sys.argv[sys.argv.index('--candidate-source') + 1] if '--candidate-source' in sys.argv else sys.argv[1]).resolve()
sys.dont_write_bytecode = True
sys.path.insert(0, str(ROOT / 'build-utils/melonx'))
sys.path.insert(0, str(ROOT / 'test'))
sys.path.insert(0, str(ROOT / 'tools/melonx'))
from melonx_adapter_control import control_source, files_edited_later  # noqa: E402
_HOLD = []
FINAL_SOURCE = SOURCE
SOURCE, FINAL_PREPARATION = control_source(SOURCE, 'adapt_submit_causes', _HOLD)
import adapt_submit_causes as adapter  # noqa: E402
import frame_report  # noqa: E402

FIXTURE = ROOT / 'test/melonx_submit_causes'
DOTNET = os.environ.get('DOTNET', 'dotnet')
VULKAN = 'src/Ryujinx.Graphics.Vulkan/'
GPU = 'src/Ryujinx.Graphics.Gpu/'
checks = 0


def check(condition, message):
    global checks
    checks += 1
    if not condition:
        raise SystemExit('FAILED: ' + message)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read(tree, name):
    return (tree / name).read_text(encoding='utf-8-sig')


def untagged(text):
    return ''.join(line for line in text.splitlines(True) if adapter.TAG not in line)


# 1. The control, the candidate texts and the additive replacements.
check(sorted(adapter.BASELINE) == sorted({p[0] for p in adapter.PAIRS}) and len(adapter.BASELINE) == 10, 'ten files, each edited')
for name, expected in adapter.BASELINE.items():
    check(sha(SOURCE / name) == expected, 'control is the Core 741 preparation: ' + name)
control = {name: read(SOURCE, name) for name in adapter.BASELINE}
candidate = dict(control)
for name, old, new in adapter.PAIRS:
    check(control[name].count(old) == 1 and candidate[name].count(old) == 1, 'one site in the control: ' + name + ': ' + old.strip()[:60])
    candidate[name] = candidate[name].replace(old, new)
blocks = {adapter.TIMER_OLD: 'start', adapter.CONTEXT_MEMBERS_OLD: 'end', adapter.SUBMIT_OLD: 'start', adapter.MODE_OLD: 'start'}
for name, old, new in adapter.PAIRS:
    if old == adapter.SIGNATURE_OLD:
        check(new == old.replace('HostSyncFlags flags)', 'HostSyncFlags flags, [System.Runtime.CompilerServices.CallerMemberName] string caller = "")'),
              'the signature gains only the optional caller name')
    elif old == adapter.LOG_OLD:
        check(new == old[:-2] + ' +\n                SubmitCausesText(); // ' + adapter.TAG + '\n', 'the line gains only its suffix')
    elif old in blocks:
        check(new.startswith(old) if blocks[old] == 'start' else new.endswith(old), 'a block added beside its anchor only')
    else:
        check(untagged(new) == old and new != old, 'only tagged lines added: ' + old.strip()[:60])
added = '\n'.join(new for _, old, new in adapter.PAIRS)
fragments = []
for name, old, new in adapter.PAIRS:
    if old in blocks:
        fragments.append(new[len(old):] if blocks[old] == 'start' else new[:-len(old)])
    elif old in (adapter.SIGNATURE_OLD, adapter.LOG_OLD):
        fragments.append(new.replace(old[:-2], ''))
    else:
        fragments.append(''.join(line for line in new.splitlines(True) if adapter.TAG in line))
for fragment in fragments:
    code_only = re.sub(r'"[^"\n]*"', '""', re.sub(r'//[^\n]*', '', fragment))  # comments and string literals left out
    check(not re.search(r'FlushAllCommands|FlushCommandsImpl|\.Wait\(|WaitFor|lock \(|Monitor\.|Interlocked|Thread\.|Volatile|'
                        r'CreateSync|AddWaitable|Return\(|Rent\(', code_only), 'no submission, wait or lock added: ' + fragment.strip()[:80])
check(all(new.count('FlushAllCommands();') + new.count('FlushCommandsImpl();') == old.count('FlushAllCommands();') +
          old.count('FlushCommandsImpl();') for _, old, new in adapter.PAIRS), 'no submission added or removed')
check(all(untagged(candidate[name]).count('if (') == control[name].count('if (') for name in adapter.BASELINE
          if name not in (adapter.BASE, adapter.CONTEXT)), 'no condition added in the cause sites')
check(control[adapter.BASE].count('if (') == candidate[adapter.BASE].count('if (') and
      control[adapter.CONTEXT].count('if (') + 2 == candidate[adapter.CONTEXT].count('if ('),
      'conditions: none in the timer, two in the host sync window (its start, its 5 s)')

# 2. Completeness: every submission names its cause; every host sync site is in the table.
tree_texts = {}
for path in sorted((SOURCE / VULKAN).rglob('*.cs')):
    rel = path.relative_to(SOURCE).as_posix()
    tree_texts[rel] = candidate.get(rel, path.read_text(encoding='utf-8-sig'))
calls = untagged_sites = 0
for rel, text in tree_texts.items():
    lines = text.splitlines()
    for number, line in enumerate(lines):
        stripped = line.strip()
        if not re.search(r'\b(FlushAllCommands|FlushCommandsImpl)\(\);', stripped) or stripped.startswith(('//', 'internal void', 'public void')):
            continue
        if rel == VULKAN + 'VulkanRenderer.cs' and stripped == '_pipeline?.FlushCommandsImpl();':
            continue
        calls += 1
        previous = next(l.strip() for l in reversed(lines[:number]) if l.strip())
        if not previous.startswith('RenderStageTimer.NextSubmitCause = RenderStageTimer.SubmitCause.'):
            untagged_sites += 1
            print('untagged submission:', rel, number + 1, stripped)
check(calls == 16 and untagged_sites == 0, 'all 16 submissions of the Vulkan backend name their cause')
causes = re.findall(r'NextSubmitCause = RenderStageTimer\.SubmitCause\.(\w+);', added)
check(set(causes) == {'DrawAutoFlush', 'Query', 'DisposedWeight', 'AttachmentAutoFlush', 'StrictSync', 'SyncWait', 'BufferRead',
                      'StagingFull', 'TextureRead', 'Helper', 'Present'}, 'every cause but "other" is named somewhere')
gpu_calls = {}
method_line = re.compile(r'^\s+(?:public|private|internal|protected)[^=;(]*?\b(\w+)\s*\(')
for path in sorted((SOURCE / GPU).rglob('*.cs')):
    rel = path.relative_to(SOURCE).as_posix()
    text = candidate.get(rel, path.read_text(encoding='utf-8-sig'))
    lines = text.splitlines()
    for number, line in enumerate(lines):
        if 'CreateHostSyncIfNeeded(' not in line or 'internal void CreateHostSyncIfNeeded(' in line or line.strip().startswith('//'):
            continue
        enclosing = next(method_line.match(l).group(1) for l in reversed(lines[:number + 1]) if method_line.match(l))
        gpu_calls.setdefault(enclosing, set()).add(rel)
        check(line.count(',') == 0 or 'HostSyncFlags.Force |' in line, 'one argument: ' + line.strip())
check(set(gpu_calls) == set(adapter.SITES) and all(gpu_calls[m] == {adapter.SITES[m]} for m in gpu_calls),
      'every CreateHostSyncIfNeeded call is in a method the site table names, in its file: ' + json.dumps({k: sorted(v) for k, v in gpu_calls.items()}))
check(sum(1 for m in adapter.SITES if f'"{m}" =>' in adapter.CONTEXT_MEMBERS_NEW) == len(adapter.SITES) == 9, 'each site has a case')
if FINAL_PREPARATION:
    later = files_edited_later('adapt_submit_causes')
    # Core 745: adapt_paced_strict_syncs, a later adapter, paces the strict host syncs in GpuContext.cs and the voluntary
    # submissions in AutoFlushCounter.cs. Its replacements are undone from the final text (each required once) before the
    # same exact comparison; no other later adapter may edit these files.
    import adapt_paced_strict_syncs as paced  # noqa: E402
    check(later <= {paced.GPU_CONTEXT, paced.AUTO_FLUSH},
          'no later adapter edits these files but adapt_paced_strict_syncs: ' + str(sorted(later)))
    for name in adapter.BASELINE:
        final = read(FINAL_SOURCE, name)
        for old, new in reversed(paced.FILE_PAIRS.get(name, ())):
            check(final.count(new) == 1, 'adapt_paced_strict_syncs: each replacement once in ' + name)
            final = final.replace(new, old)
        check(final == candidate[name], 'the final preparation is the control plus the adapter: ' + name)

environment = dict(os.environ, DOTNET_CLI_TELEMETRY_OPTOUT='1', DOTNET_NOLOGO='1')
pin = json.loads((ROOT / 'build-utils/melonx/source.json').read_text())


def timer_text(text):
    first = text.index('    static class RenderStageTimer\n')
    last = text.index('\n    }\n', first) + len('\n    }\n')
    body = text[first:last]
    now = '        public static long Now() => System.Diagnostics.Stopwatch.GetTimestamp();\n'
    check(body.count(now) == 1, 'RenderStageTimer.Now is the clock read')
    return body.replace(now, '        public static long Now() => Ryujinx.Graphics.Gpu.FakeClock.Now;\n')


def host_sync_text(text):
    first = text.index('        // RewindBox (adapt_submit_causes): host syncs created per GPU-side site')
    end = "            text.Append(')');\n        }\n"
    last = text.index(end, first) + len(end)
    body = text[first:last]
    check(body.count('System.Diagnostics.Stopwatch.GetTimestamp()') == 1, 'one clock read in the host sync window')
    return body.replace('System.Diagnostics.Stopwatch.GetTimestamp()', 'FakeClock.Now')


def run_probe(work, label, program, candidate_build):
    work.mkdir(parents=True)
    (work / 'Program.cs').write_text(program)
    defines = '<DefineConstants>$(DefineConstants);CANDIDATE</DefineConstants>' if candidate_build else ''
    (work / 'Probe.csproj').write_text(f'''<Project Sdk="Microsoft.NET.Sdk"><PropertyGroup>
<OutputType>Exe</OutputType><TargetFramework>net10.0</TargetFramework><Nullable>disable</Nullable><Optimize>true</Optimize>
<EnableNETAnalyzers>false</EnableNETAnalyzers><NuGetAudit>false</NuGetAudit><NoWarn>0649;0169;0414;CS0649;CS0169;CS0414</NoWarn>
{defines}</PropertyGroup></Project>''')
    (work / 'global.json').write_text(json.dumps({'sdk': {'version': pin['dotnet'], 'rollForward': 'disable'}}))
    build = subprocess.run([DOTNET, 'build', str(work / 'Probe.csproj'), '-c', 'Release', '-nologo'], cwd=work,
                           capture_output=True, text=True, env=environment, timeout=1200)
    if build.returncode:
        print(build.stdout[-5000:], build.stderr[-2000:], flush=True)
    check(build.returncode == 0, label + ' probe builds')
    out = subprocess.run([DOTNET, str(work / 'bin/Release/net10.0/Probe.dll')], capture_output=True, text=True,
                         env=environment, timeout=600)
    check(out.returncode == 0, label + ' probe runs: ' + out.stderr[-500:])
    return json.loads(next(line for line in out.stdout.splitlines() if line.startswith('{')))


with tempfile.TemporaryDirectory(prefix='melonx-submit-causes-') as temporary:
    temporary = Path(temporary).resolve()
    tree = temporary / 'candidate-tree'
    shutil.copytree(SOURCE, tree, ignore=shutil.ignore_patterns('.git', 'bin', 'obj', 'MeloNX'), symlinks=True)
    changed = adapter.apply(tree)
    check(sorted(p.relative_to(tree).as_posix() for p in changed) == sorted(adapter.BASELINE), 'the adapter changed its ten files')
    check(all(read(tree, name) == candidate[name] for name in adapter.BASELINE), 'applied tree is the candidate text')
    drift = temporary / 'drift'
    for name in adapter.BASELINE:
        (drift / name).parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(SOURCE / name, drift / name)
    (drift / adapter.SYNC).write_bytes((drift / adapter.SYNC).read_bytes() + b'\n// unreviewed drift\n')
    try:
        adapter.apply(drift)
        refused = False
    except AssertionError:
        refused = True
    check(refused, 'a drifted SyncManager.cs is refused')
    edited = [Path(name).name for name in adapter.BASELINE]
    for project in (VULKAN + 'Ryujinx.Graphics.Vulkan.csproj', GPU + 'Ryujinx.Graphics.Gpu.csproj'):
        result = subprocess.run([DOTNET, 'build', str(tree / project), '-c', 'Release', '-nologo', '-m:1', '-p:NuGetAudit=false'],
                                capture_output=True, text=True, timeout=2400, env=environment, cwd=tree)
        if result.returncode:
            print(result.stdout[-6000:], result.stderr[-2000:], flush=True)
        check(result.returncode == 0, 'production ' + Path(project).stem + ' builds with the adapter')
        warnings = sorted({line for line in result.stdout.splitlines() if 'warning' in line and any(f + '(' in line for f in edited)})
        check(not warnings, 'no compiler warning in the edited files: ' + '\n'.join(warnings[:5]))

    program = (FIXTURE / 'Program.cs').read_text()
    reports = {}
    for label, texts, candidate_build in (('control', control, False), ('candidate', candidate, True)):
        text = program.replace('//__RENDER_STAGE_TIMER__\n', timer_text(texts[adapter.BASE]))
        if candidate_build:
            text = text.replace('//__HOST_SYNC_MEMBERS__\n', host_sync_text(texts[adapter.CONTEXT]))
        reports[label] = run_probe(temporary / ('probe-' + label), label, text, candidate_build)

c, k = reports['control'], reports['candidate']
for window in ('first', 'second'):
    check(c[window].startswith('Vulkan render stages over ') and k[window].startswith(c[window]),
          window + ' window: the control line is the start of the candidate line, byte for byte')
    for label, line in (('control', c[window]), ('candidate', k[window])):
        match = frame_report.STAGE_LINE.search(line)
        check(match is not None, label + ' ' + window + ' line parses with frame_report.py')
    check(frame_report.STAGE_LINE.search(c[window]).groupdict() == frame_report.STAGE_LINE.search(k[window]).groupdict(),
          window + ' window: the same parsed values')
    check(c[window].endswith('unavailable pipelines 0'), window + ' window: the control line ends as delivered')
check(k['first'][len(c['first']):] ==
      '; submits by cause: strict sync 6, sync wait 2, draw auto-flush 9, attachment auto-flush 3, query 1, disposed resources 1, '
      'buffer read 0, texture read 0, staging buffer full 0, helper 0, present 1, other 2; syncs created submitting 6, waiting '
      'for the command buffer 14; fast flush mode 2 of 3 frames, sync waits 4.0 ms', 'the first window gives the scripted causes')
check(k['second'][len(c['second']):] ==
      '; submits by cause: strict sync 0, sync wait 0, draw auto-flush 0, attachment auto-flush 0, query 0, disposed resources 0, '
      'buffer read 0, texture read 0, staging buffer full 0, helper 0, present 0, other 3; syncs created submitting 0, waiting '
      'for the command buffer 0; fast flush mode 0 of 0 frames, sync waits 0.0 ms', 'the next window starts again from zero')
check(frame_report.STAGE_LINE.search(k['first'])['submits'] == '25', 'the 25 scripted submissions are the line\'s submits')
check(k['causeAfterSubmit'] == 'Other', 'the cause returns to "other" after each submission')
check(k['linesBeforeFiveSeconds'] == 0, 'no host sync line before 5 s')
names = ('GPFifo syncpoint', '3D syncpoint', 'SetReference', 'counter reports', 'queued syncpoints', 'DMA read-back',
         'DMA buffer read-back', 'texture unbind', 'WaitForIdle', 'other')


def sites(values):
    return ' (' + ', '.join(f'{n} {v}' for n, v in zip(names, values)) + ')'


check(k['hostSyncs'] == 'Host syncs created over 5000 ms: strict 18' + sites((8, 3, 2, 1, 1, 2, 0, 0, 0, 1)) + '; not strict 10' +
      sites((0, 0, 0, 0, 0, 0, 1, 4, 4, 1)) + ' (adapt_submit_causes)', 'the host sync line gives every scripted site')
check(k['hostSyncsNext'] == 'Host syncs created over 6000 ms: strict 1' + sites((0, 0, 1, 0, 0, 0, 0, 0, 0, 0)) + '; not strict 0' +
      sites((0,) * 10) + ' (adapt_submit_causes)', 'the next host sync window starts again from zero')
check(k['sites'] == {'Syncpointb': 0, 'IncrementSyncpoint': 1, 'SetReference': 2, 'FlushCounterReports': 3,
                     'QueueSyncpointBehindReports': 4, 'TryReadBackGpuRegion': 5, 'TryReadBackIntoBuffer': 6, 'SignalModifying': 7,
                     'CreatePendingSyncs': 8, 'Dispatch': 9, '': 9}, 'site table')

inputs = ['build-utils/melonx/adapt_submit_causes.py', 'build-utils/melonx/adapt_session.py', 'test/melonx_submit_causes_test.py',
          'test/melonx_submit_causes/Program.cs', 'test/melonx_adapter_control.py', 'tools/melonx/frame_report.py']
receipt = dict(result='passed', checks=checks, finalPreparationBound=FINAL_PREPARATION,
               sourceKind='finalPreparationWithReversedControl' if FINAL_PREPARATION else 'core741Preparation',
               postimages={name: sha(FINAL_SOURCE / name) for name in adapter.BASELINE} if FINAL_PREPARATION else {},
               physicalDeviceTested=False, productionVulkanAssemblyBuilt=True, productionGpuAssemblyBuilt=True,
               sourceBaseline=adapter.BASELINE, submissionSites=calls, hostSyncSites=sorted(adapter.SITES),
               lines=dict(control=c['first'], candidate=k['first'], hostSyncs=k['hostSyncs']),
               inputs={p: sha(ROOT / p) for p in inputs},
               limitation='Counters and log text only; which causes and sites dominate on Hogwarts Legacy is read in the next '
                          'device session (render stages suffix, "Host syncs created over" lines).')
out = ROOT / 'dist/melonx/submit-causes-checks.json'
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps(receipt, indent=2) + '\n')
print(json.dumps(dict(result='passed', checks=checks)))
