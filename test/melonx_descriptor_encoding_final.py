"""Shared checks of the final-source runs of the DescriptorSetUpdater fixtures (build 631).

The scalar-texture and fallback-scratch fixtures compile production members of DescriptorSetUpdater
extracted by signature. Run on the final prepared source (--candidate-source), they compare the
delivered members (the 'delivered' control) with the final ones, run with the encoding policy off and
on: the final members are the delivered ones with the reviewed encoding hunks only, plus the template
scratch helper, and the constructor sizes that the fixtures' scratch doubles mirror are checked here.
"""
from pathlib import Path
import hashlib
import importlib
import json
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'build-utils/melonx'))
sys.path.insert(0, str(ROOT / 'test'))
import adapt_host_qos_pipeline_budget as host  # noqa: E402
from adapt_descriptor_updates import method  # noqa: E402
from melonx_adapter_control import ORDER, apply_present, reverse_present  # noqa: E402

RELATIVE = host.DESCRIPTOR_UPDATER
CONSTANTS = 'src/Ryujinx.Graphics.Vulkan/Constants.cs'
PIPELINE_BASE = host.PIPELINE_BASE
# The members the encoding hunks change, and the helper they add.
ENCODED = {'public void UpdateAndBindDescriptorSets(',
           'private void UpdateAndBind(CommandBufferScoped cbs, ShaderCollection program, int setIndex, PipelineBindPoint pbp)'}
TEMPLATE_SCRATCH = '        private static Span<T> TemplateScratch<T>('
DELIVERED_SIZES = ('_textures = new DescriptorImageInfo[Constants.MaxTexturesPerStage];',
                   '_images = new DescriptorImageInfo[Constants.MaxImagesPerStage];',
                   '_bufferTextures = new BufferView[Constants.MaxTexturesPerStage];',
                   '_bufferImages = new BufferView[Constants.MaxImagesPerStage];')
FINAL_SIZES = ('_textures = new DescriptorImageInfo[Constants.MaxTextureBindings * 2];',
               '_images = new DescriptorImageInfo[Constants.MaxImageBindings * 2];',
               '_bufferTextures = new BufferView[Constants.MaxTextureBindings * 2];',
               '_bufferImages = new BufferView[Constants.MaxImageBindings * 2];')
# The adapters of the preparation order that edit DescriptorSetUpdater.cs: all of them run after the encoding hunks
# (adapt_host_qos_pipeline_budget is a Core 631 step). Derived, so that an adapter added to the order is taken out and
# re-applied below without a list to extend here.
LATER = [name for name in ORDER if RELATIVE in importlib.import_module(name).BASELINE]
INPUTS = ['test/melonx_descriptor_encoding_final.py', 'build-utils/melonx/adapt_host_qos_pipeline_budget.py',
          *('build-utils/melonx/' + name + '.py' for name in LATER), 'test/melonx_adapter_control.py',
          'test/melonx_scalar_texture_descriptors/Encoding.cs']


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def restore(body):
    """A final member with the encoding hunks reversed: the delivered member when only they changed it."""
    for old, new in reversed(host.DESCRIPTOR_UPDATER_HUNKS):
        body = body.replace(new, old)
    return body


def without_later(candidate_root):
    """The final DescriptorSetUpdater without the adapters of the preparation order that edit it after the encoding hunks
    (LATER: Core 705 adapt_same_program_descriptors, Core 715 adapt_extra_set_binds, Core 723 adapt_extra_array_dirty,
    then adapt_buffer_mirror_windows, adapt_descriptor_and_block_usage, adapt_hogwarts_frame_budget and
    adapt_hogwarts_steady_render). Each is taken out latest first, down to the bytes it pins (its recorded preimage, or
    its replacements undone, each present once); re-applied in order to what is left they must give the final file back
    byte for byte, so the final file is exactly the returned text plus those adapters.

    Limit, as since Core 705: the members these fixtures compile and run are the returned text's, the encoding hunks on
    the delivered members; what the later adapters change in the same members (SetProgram, Rebind, SetImage, the extra
    set binds) is not executed here. The first four have a gate of their own; on 23 November 2026 the plan has none that
    executes the last three's DescriptorSetUpdater edits."""
    final = Path(candidate_root) / RELATIVE
    with tempfile.TemporaryDirectory(prefix='melonx-descriptor-encoding-chain-') as chain:
        chain = Path(chain)
        held = chain / RELATIVE
        held.parent.mkdir(parents=True)
        shutil.copyfile(final, held)
        for name in reversed(LATER):
            assert reverse_present(chain, name, only={RELATIVE}) == [RELATIVE], name
        text = held.read_text(encoding='utf-8-sig')
        for name in LATER:
            assert apply_present(chain, name, only={RELATIVE}) == [RELATIVE], name
        assert held.read_bytes() == final.read_bytes(), 'the final DescriptorSetUpdater is not the encoding postimage plus the later adapters of the preparation order'
    return text


def check_sources(control_root, candidate_root, signatures):
    """The delivered and final DescriptorSetUpdater: members, encoding hunks, scratch sizes and policy declaration."""
    control = (Path(control_root) / RELATIVE).read_text(encoding='utf-8-sig')
    candidate = without_later(candidate_root)
    for old, new in host.DESCRIPTOR_UPDATER_HUNKS:
        assert control.count(old) == 1 and candidate.count(new) == 1 and candidate.count(old) == (old in new), old[:80]
    assert restore(candidate) == control, 'the final DescriptorSetUpdater differs from the delivered one beyond the encoding hunks'
    assert all(control.count(line) == 1 and line not in candidate for line in DELIVERED_SIZES), 'delivered scratch sizes'
    assert all(candidate.count(line) == 1 and line not in control for line in FINAL_SIZES), 'final scratch sizes'
    base = (Path(candidate_root) / PIPELINE_BASE).read_text(encoding='utf-8-sig')
    policy = base[base.index('    public static class EncodingPolicy'):base.index('    static class RenderDetail')]
    assert ('public static bool BindingSizedDescriptorScratch { get; set; }\n' in policy and
            'public static bool IncrementalArrayDescriptors { get; set; }\n' in policy and
            'public static readonly long[] TemplateFallbacks = new long[4];' in base), 'policy and counters of the final source'
    members, hashes = {}, {}
    for variant, text in (('control', control), ('candidate', candidate)):
        listed = list(signatures) + ([TEMPLATE_SCRATCH] if variant == 'candidate' else [])
        members[variant] = [method(text, signature) for signature in listed]
        hashes[variant] = {signature.strip(): hashlib.sha256(body.encode()).hexdigest()
                           for signature, body in zip(listed, members[variant], strict=True)}
    assert TEMPLATE_SCRATCH not in control
    for signature, old, new in zip(signatures, members['control'], members['candidate']):
        if signature.strip() in ENCODED:
            assert new != old and restore(new) == old, 'encoding member beyond its hunks: ' + signature.strip()
        else:
            assert new == old, 'member changed outside the encoding hunks: ' + signature.strip()
    return members, hashes


def run(project, dotnet, environment, arguments, build):
    """dotnet run of a fixture project (built once), its JSON report line."""
    command = [dotnet, 'run', '--project', str(project), '-c', 'Release']
    if not build:
        command.append('--no-build')
    result = subprocess.run([*command, '--', *arguments], cwd=Path(project).parent, capture_output=True, text=True,
                            timeout=300, env=environment)
    if result.returncode:
        print(result.stdout[-6000:], result.stderr[-3000:], flush=True)
    result.check_returncode()
    return json.loads(next(line for line in result.stdout.splitlines() if line.startswith('{')))
