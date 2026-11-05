#!/usr/bin/env python3
"""Core gate of adapt_nativeaot_gc_runtime: the final preparation links the pinned, rebuilt workstation GC and fails closed.

Usage: melonx_nativeaot_gc_runtime_gate_test.py <Core 658 prepared MeloNX tree>
       melonx_nativeaot_gc_runtime_gate_test.py <control> --candidate-source <final preparation containing the adapter>

test/melonx_nativeaot_gc_test.py proves the mechanism against dotnet/runtime v10.0.0 and the official runtime packs (it needs
those trees and packages, so it runs where they are and its receipt is kept as evidence). This gate needs only the
repository and the preparation, as the Core build's fresh gates do:
- Ryujinx.Library.csproj is the Core 658 project plus exactly the adapter's target (control_source's forward check and an
  undo-and-compare of the one replacement);
- the target fails closed: an error for an unknown RuntimeIdentifier, server GC, a missing or other runtime-pack library,
  an unset pin digest, a missing or other patched library, and a replacement that is not exactly one linker input; the
  replacement is in place (same position among LinkerArg and NativeLibrary);
- the reviewed official digests are the source pin's (nativeaot-gc-rebuild.json) and the run pin's
  (nativeaot-gc-rebuild-pin.json), which pins both RIDs, the run, the artifact and the patch;
- build_core.sh fetches the pinned libraries before publishing, passes the pinned digest of the RID being built, requires
  the patch marker in the linked engine and records the GC identity; melonx-core.yml gives the fetch a token and
  rebuilds the Core when any of these inputs changes.
Writes dist/melonx/nativeaot-gc-runtime-gate-checks.json. No device; the link itself is proven by the Core build.
"""
import hashlib
import json
from pathlib import Path
import re
import shutil
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
SOURCE = Path(sys.argv[sys.argv.index('--candidate-source') + 1] if '--candidate-source' in sys.argv else sys.argv[1]).resolve()
sys.path.insert(0, str(ROOT / 'build-utils/melonx'))
sys.path.insert(0, str(ROOT / 'test'))
from melonx_adapter_control import control_source  # noqa: E402
_HOLD = []
FINAL_SOURCE = SOURCE
SOURCE, FINAL_PREPARATION = control_source(SOURCE, 'adapt_nativeaot_gc_runtime', _HOLD)
import adapt_nativeaot_gc_runtime as adapter  # noqa: E402

PROJECT = 'src/Ryujinx.Library/Ryujinx.Library.csproj'
checks = 0


def check(condition, message):
    global checks
    checks += 1
    if not condition:
        raise SystemExit('FAILED: ' + message)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


check(list(adapter.BASELINE) == [PROJECT], 'the adapter edits the Library project only')
check(sha(SOURCE / PROJECT) == adapter.BASELINE[PROJECT], 'control is the Core 658 project')
with tempfile.TemporaryDirectory(prefix='melonx-nativeaot-gc-gate-') as temporary:
    work = Path(temporary)
    (work / PROJECT).parent.mkdir(parents=True)
    shutil.copyfile(SOURCE / PROJECT, work / PROJECT)
    changed = adapter.apply(work)
    check([str(p) for p in changed] == [PROJECT], 'apply reports the project')
    candidate = (work / PROJECT).read_text(encoding='utf-8-sig')
    if FINAL_PREPARATION:
        check((work / PROJECT).read_bytes() == (FINAL_SOURCE / PROJECT).read_bytes(), 'final preparation is the adapter')
control = (SOURCE / PROJECT).read_text(encoding='utf-8-sig')
target = adapter.TARGET
check(candidate.count(target) == 1 and candidate.replace(target, '</Project>', 1).rstrip() == control.rstrip(),
      'undo-and-compare: the project is the control plus the target only')
check(candidate.rstrip().endswith('</Project>') and len(re.findall(r'<Project[\s>]', candidate)) == 1, 'one project element')

# Fail closed.
errors = re.findall(r'<Error Condition="([^"]+)"', target)
for needle in ("'$(_RewindBoxGcOfficialExpected)' == ''", "'$(FullRuntimeName)' != 'libRuntime.WorkstationGC'",
               "'$(RewindBoxNativeAotGcSha256)' == ''", "!Exists('$(_RewindBoxGcOfficial)')", "!Exists('$(_RewindBoxGcPatched)')",
               "'$(_RewindBoxGcOfficialActual)' != '$(_RewindBoxGcOfficialExpected)'",
               "'$(_RewindBoxGcPatchedActual)' != '$(RewindBoxNativeAotGcSha256)'",
               "'$(_RewindBoxGcLinkerArgPaths)' != '$(_RewindBoxGcOfficialFull)'",
               "'$(_RewindBoxGcLinkedPaths)' != '$(_RewindBoxGcPatchedFull)'"):
    check(any(needle in condition for condition in errors), 'fails closed: ' + needle)
check('AfterTargets="SetupOSSpecificProps"' in target and target.count('<LinkerArg Remove="@(LinkerArg)" />') == 1 and
      target.count('<NativeLibrary Remove="@(NativeLibrary)" />') == 1 and 'In place' in target,
      'replaced in place among the linker inputs and native libraries, after the ILCompiler sets them')
check(target.count('Algorithm="SHA256"') == 2, 'both libraries are hashed')

# Pins agree.
source_pin = json.loads((ROOT / 'build-utils/melonx/nativeaot-gc-rebuild.json').read_text())
run_pin = json.loads((ROOT / 'build-utils/melonx/nativeaot-gc-rebuild-pin.json').read_text())
patch = ROOT / source_pin['patch']
check(sha(patch) == source_pin['patchSha256'] == run_pin['patchSha256'], 'the patch is the pinned one')
check('bgc_thread_running && commit_mark_array_bgc_init()' in patch.read_text() and source_pin['marker'] in patch.read_text(),
      'the patch is the upstream start check plus the marker')
check(run_pin['revision'] == source_pin['revision'] and run_pin['tag'] == source_pin['tag'] == 'v10.0.0', 'same source')
check(set(adapter.OFFICIAL) == set(source_pin['runtimePacks']) == set(run_pin['libraries']), 'both RIDs everywhere')
for rid, official in adapter.OFFICIAL.items():
    check(official == source_pin['runtimePacks'][rid]['librarySha256'] == run_pin['libraries'][rid]['officialSha256'],
          rid + ': reviewed official library')
    check(official in target, rid + ': the target checks the official digest')
    patched = run_pin['libraries'][rid]['sha256']
    check(isinstance(patched, str) and re.fullmatch('[0-9a-f]{64}', patched) and patched != official and
          isinstance(run_pin['libraries'][rid]['bytes'], int), rid + ': a patched library is pinned')
check(all(isinstance(run_pin[key], int) for key in ('run', 'job', 'artifact', 'artifactBytes')) and
      run_pin['artifactDigest'].startswith('sha256:') and re.fullmatch('[0-9a-f]{40}', run_pin['headSha']),
      'the run and its artifact are pinned')

# Build wiring.
build = (ROOT / 'build-utils/melonx/build_core.sh').read_text()
fetch_at, publish_at = build.find('fetch_nativeaot_gc.py" "$SOURCE_DIR"'), build.find("'dotnet', 'publish'")
check(build.find('prepare_embedded.py" "$SOURCE_DIR"') < fetch_at < publish_at and fetch_at > 0,
      'the pinned libraries are fetched after the preparation and before publishing')
check("gc['libraries'][os.environ['MELONX_RUNTIME']]['sha256']" in build and "'-p:RewindBoxNativeAotGcSha256=' + gc_sha" in build,
      'the digest of the RID being built is passed')
check("grep -q -a -F 'RewindBox NativeAOT GC patch 1:" in build and source_pin['marker'].startswith('RewindBox NativeAOT GC patch 1:'),
      'the linked engine must hold the patch marker')
check("receipt['nativeAotGc']" in build, 'the Core identity records the GC')
fetch = (ROOT / 'build-utils/melonx/fetch_nativeaot_gc.py').read_text()
check("DESTINATION" in fetch and 'RewindBoxNativeAotGc' in fetch and "'sha256:' + sha(data) == run['artifactDigest']" in fetch,
      'the fetch checks the artifact digest and writes where the target reads')
workflow = (ROOT / '.github/workflows/melonx-core.yml').read_text()
for path in ('build-utils/melonx/fetch_nativeaot_gc.py', 'build-utils/melonx/nativeaot_gc_archive.py',
             'build-utils/melonx/nativeaot-gc-rebuild.json', 'build-utils/melonx/nativeaot-gc-rebuild-pin.json',
             'build-utils/melonx/adapt_nativeaot_gc_runtime.py'):
    check('    - ' + path + '\n' in workflow, 'the Core build triggers on ' + path)
check('GH_TOKEN: ${{ github.token }}' in workflow, 'the fetch has a token')

receipt = dict(result='passed', checks=checks, finalPreparationBound=FINAL_PREPARATION,
               sourceKind='finalPreparationWithReversedControl' if FINAL_PREPARATION else 'core658Preparation',
               postimages={PROJECT: sha(FINAL_SOURCE / PROJECT)} if FINAL_PREPARATION else {}, physicalDeviceTested=False,
               sourceBaseline=adapter.BASELINE, patchedLibraries={rid: item['sha256'] for rid, item in run_pin['libraries'].items()},
               run=run_pin['run'], inputs={p: sha(ROOT / p) for p in (
                   'build-utils/melonx/adapt_nativeaot_gc_runtime.py', 'build-utils/melonx/nativeaot-gc-rebuild.json',
                   'build-utils/melonx/nativeaot-gc-rebuild-pin.json', 'build-utils/melonx/build_core.sh',
                   'build-utils/melonx/fetch_nativeaot_gc.py', source_pin['patch'], 'test/melonx_nativeaot_gc_runtime_gate_test.py')})
out = ROOT / 'dist/melonx/nativeaot-gc-runtime-gate-checks.json'
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps(receipt, indent=2) + '\n')
print(json.dumps(dict(result='passed', checks=checks, finalPreparationBound=FINAL_PREPARATION)))
