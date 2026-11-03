"""Run the delivered and the final Vulkan TextureArray, compiled whole with doubles (build 631).

The control compiles the delivered TextureArray.cs and ResourceArray.cs, the candidate the final ones, run with
EncodingPolicy.IncrementalArrayDescriptors off and on, through the history of test/melonx_array_descriptor_ranges/
Program.cs. Off, the final array must behave exactly as the delivered one (same descriptor writes, hashed in order, same
sets, gets, barriers and invalidations). On, every bound set must hold the array's elements, no set may be written while a
pending command buffer uses it, each bound set must be held by its command buffer and every view and sampler it references
owned by it, with far fewer descriptors written. In both the array consumes the caller's arrays during the call: they are
overwritten as soon as it returns. Used by the single-resource-binding and bounded-binding-snapshot fixtures, whose
borrowed and pooled caller arrays rely on that contract of the Vulkan TextureArray.
"""
from pathlib import Path
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'build-utils/melonx'))
import adapt_host_qos_pipeline_budget as host  # noqa: E402

TEXTURE_ARRAY = 'src/Ryujinx.Graphics.Vulkan/TextureArray.cs'
RESOURCE_ARRAY = 'src/Ryujinx.Graphics.Vulkan/ResourceArray.cs'
assert TEXTURE_ARRAY == host.TEXTURE_ARRAY and RESOURCE_ARRAY == host.RESOURCE_ARRAY
FILES = [TEXTURE_ARRAY, RESOURCE_ARRAY]
FIXTURE = ['test/melonx_array_descriptor_ranges/Program.cs', 'test/melonx_array_descriptor_ranges/Boundaries.cs']
INPUTS = ['test/melonx_array_descriptor_ranges.py', *FIXTURE]
PROJECT = '''<Project Sdk="Microsoft.NET.Sdk"><PropertyGroup>
<OutputType>Exe</OutputType><TargetFramework>net10.0</TargetFramework><AllowUnsafeBlocks>true</AllowUnsafeBlocks>
<Nullable>disable</Nullable><ImplicitUsings>disable</ImplicitUsings><EnableNETAnalyzers>false</EnableNETAnalyzers>
<NuGetAudit>false</NuGetAudit><NoWarn>0649;0169;0414</NoWarn></PropertyGroup></Project>'''


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def execute(project, dotnet, environment, mode, build):
    command = [dotnet, 'run', '--project', str(project), '-c', 'Release', *([] if build else ['--no-build']), '--', mode]
    result = subprocess.run(command, cwd=Path(project).parent, capture_output=True, text=True, timeout=600, env=environment)
    if result.returncode:
        print(result.stdout[-6000:], result.stderr[-3000:], flush=True)
    result.check_returncode()
    return json.loads(next(line for line in result.stdout.splitlines() if line.startswith('{')))


def run(control_root, candidate_root, temporary, dotnet, environment, version):
    """Compile and run both variants; return the receipt section (reports, compared fields, compiled sources)."""
    reports, compiled = {}, {}
    for variant, tree in (('control', Path(control_root)), ('candidate', Path(candidate_root))):
        work = Path(temporary) / ('array-descriptor-ranges-' + variant)
        work.mkdir()
        for relative in [*FILES, *FIXTURE]:
            shutil.copyfile((tree if relative in FILES else ROOT) / relative, work / Path(relative).name)
        (work / 'Arrays.csproj').write_text(PROJECT)
        (work / 'nuget.config').write_text('<configuration><packageSources><clear /></packageSources></configuration>')
        (work / 'global.json').write_text(json.dumps({'sdk': {'version': version, 'rollForward': 'disable'}}))
        compiled[variant] = {name: sha(work / Path(name).name) for name in FILES}
        if variant == 'control':
            reports['control'] = execute(work / 'Arrays.csproj', dotnet, environment, 'off', build=True)
        else:
            reports['candidateOff'] = execute(work / 'Arrays.csproj', dotnet, environment, 'off', build=True)
            reports['candidateOn'] = execute(work / 'Arrays.csproj', dotnet, environment, 'on', build=False)
    control, off, on = reports['control'], reports['candidateOff'], reports['candidateOn']
    assert {k: v for k, v in control.items() if k != 'mode'} == {k: v for k, v in off.items() if k != 'mode'}, \
        'policy off, the final array differs from the delivered one'
    assert control['violations'] == off['violations'] == on['violations'] == 0, (control, on)
    assert control['staleAfterDestroy'] and not on['staleAfterDestroy'], 'a destroyed view: delivered binds its old set, final writes it'
    assert all(value == 0 for value in control['detail'].values()), control['detail']
    detail = on['detail']
    assert (on['binds'] == control['binds'] and on['barriers'] == control['barriers'] and
            on['textureDirty'] == control['textureDirty']), 'the policy changed binds, barriers or invalidations'
    assert on['descriptors'] * 4 < control['descriptors'] and on['gets'] * 4 < control['gets'], (on, control)
    assert (detail['ArrayRangeWrites'] > 0 and detail['ArrayWholeWrites'] >= 2 and detail['ArrayCurrentBinds'] > 0 and
            0 < detail['ArraySlotsAdded'] <= 8 and detail['ArrayFallbacks'] >= 2 and
            detail['ArrayRangeElements'] < detail['ArrayElementsKept']), detail
    assert on['released'] == int(on['cachedAtDispose']) + detail['ArraySlotsAdded'], on
    return dict(reports=reports, compiledSourceInputs=compiled, policyOffEqualsDelivered=True, violations=0,
                callerArraysReusedAtOnce=True, descriptorsWritten=dict(control=control['descriptors'], candidateOn=on['descriptors']),
                resourceGets=dict(control=control['gets'], candidateOn=on['gets']))


def method_body(text, signature):
    """The body of the one method with this signature (braces counted)."""
    assert text.count(signature) == 1, signature
    opening = text.index('{', text.index(signature))
    depth, end = 1, opening + 1
    while depth:
        depth += (text[end] == '{') - (text[end] == '}')
        end += 1
    return text[opening:end]


def reads_only(body, name):
    """The parameter is only indexed or measured: the method keeps no reference to the caller's array (comments aside)."""
    body = re.sub(r'//[^\n]*', '', body)
    found = list(re.finditer(r'\b%s\b' % name, body))
    return bool(found) and all(body[match.end():].startswith(('[', '.Length')) for match in found)


def final_receipt(control_root, candidate_root, gal_files, backend_inputs, inputs):
    """Build 631: the receipt of a GAL binding fixture rerun on the final source.

    Its GAL files and the other backends are unchanged by this lot (byte for byte), so its historical GAL comparison
    stands for them; what changed is the Vulkan TextureArray its borrowed or pooled caller arrays rely on. The delivered
    TextureArray is the reviewed backend postimage, the final one adds the reviewed encoding hunks only, its setters only
    read the caller's array, and the arrays run (run above) with the caller's arrays overwritten at once.
    """
    control_root, candidate_root = Path(control_root), Path(candidate_root)
    unchanged = [*gal_files, *(path for path in backend_inputs if path != TEXTURE_ARRAY)]
    for relative in unchanged:
        assert sha(control_root / relative) == sha(candidate_root / relative), 'changed by this lot: ' + relative
    assert sha(control_root / TEXTURE_ARRAY) == backend_inputs[TEXTURE_ARRAY], 'the delivered TextureArray is not the reviewed postimage'
    final = (candidate_root / TEXTURE_ARRAY).read_text(encoding='utf-8-sig')
    restored = final
    for old, new in reversed(host.TEXTURE_ARRAY_HUNKS):
        restored = restored.replace(new, old)
    assert restored == (control_root / TEXTURE_ARRAY).read_text(encoding='utf-8-sig'), 'TextureArray beyond the encoding hunks'
    for signature, name in (('public void SetTextures(int index, ITexture[] textures)', 'textures'),
                            ('public void SetSamplers(int index, ISampler[] samplers)', 'samplers')):
        assert reads_only(method_body(final, signature), name), 'the final setter may keep the caller array: ' + signature
    resource = (candidate_root / RESOURCE_ARRAY).read_text(encoding='utf-8-sig')
    for old, new in reversed(host.RESOURCE_ARRAY_HUNKS):
        resource = resource.replace(new, old)
    assert resource == (control_root / RESOURCE_ARRAY).read_text(encoding='utf-8-sig'), 'ResourceArray beyond the encoding hunk'
    pin = json.loads((ROOT / 'build-utils/melonx/source.json').read_text())
    environment = dict(os.environ, DOTNET_CLI_TELEMETRY_OPTOUT='1', DOTNET_NOLOGO='1', DOTNET_TieredCompilation='0')
    with tempfile.TemporaryDirectory(prefix='melonx-array-descriptor-ranges-') as temporary:
        section = run(control_root, candidate_root, temporary, os.environ.get('DOTNET', 'dotnet'), environment, pin['dotnet'])
    sources = [*gal_files, *backend_inputs, RESOURCE_ARRAY]
    return dict(result='passed', physicalDeviceTested=False, fpsGainProven=False,
                sourceKind='deliveredPreparedWithFinalCandidate', finalPreparedSourceBound=True,
                galSourcesUnchanged=True, otherBackendsUnchanged=True, historicalGalComparisonReexecuted=False,
                backendContractReviewed=True, backendContractExecuted=True, settersReadCallerArraysOnly=True,
                arrayDescriptorRanges=section,
                inputs={p: sha(ROOT / p) for p in [*inputs, *INPUTS, 'build-utils/melonx/adapt_host_qos_pipeline_budget.py']},
                preimages={p: sha(control_root / p) for p in sources},
                postimages={p: sha(candidate_root / p) for p in sources})
