#!/usr/bin/env python3
"""Build Khronos MoltenVK from source for iOS arm64 (macOS runner): the pinned tag, unmodified or with a pinned patch.

The maintainer agreed on 3 Nov 2026 to recompiling MoltenVK 1.4.0. The kept binary of the default "MeloNX 1.4.0
(standalone)" variant embeds a MoltenVK revision (85d607a1) that is not in Khronos's history, so this build starts
from the Khronos v1.4.0 tag. The patch (build-utils/melonx/moltenvk/) changes only the argument buffer resource usage
walk of devices without a residency set (every iOS device in 1.4.0), behind REWINDBOX_MVK_ARGUMENT_BUFFER_USAGE
(unset: the original walk), and logs its counts with MoltenVK's performance statistics in both modes.

Output: dist/melonx-moltenvk-rebuild/ with ios/MoltenVK.framework (MoltenVK's own dynamic framework, unrenamed),
identity.json (pins, patch and binary digests, Mach-O build version, entry points, patch markers, linked libraries,
toolchain), sources/ (the Khronos source archive, the patch, the External sources fetchDependencies checked out, with
their notices), logs/ and commands.json. Nothing is packaged here: a delivery adopts the artifact by its digests.
The run is read through the API only, so the result and any failure are also written as job annotations.
"""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tarfile
import time

ROOT = Path(__file__).resolve().parents[2]
PIN = json.loads((ROOT / 'build-utils/melonx/moltenvk-rebuild.json').read_text())
OUT = ROOT / 'dist/melonx-moltenvk-rebuild'
WORK = ROOT / '.moltenvk-rebuild'
COMMANDS = []
# The markers of the pinned patch (patchMarkers); without a patch, those of the retired 1.4.0 argument buffer patch,
# which an unmodified build must not contain.
MARKERS = tuple(PIN.get('patchMarkers') or ('REWINDBOX_MVK_ARGUMENT_BUFFER_USAGE', 'Argument buffer resource usage (RewindBox)',
                                             'RewindBox argument buffer resource usage: %s walk'))
# The entry points MeloNX resolves in libMoltenVK (Silk.NET's loader, MVKInitialization.cs and the Metal interop).
ENTRY_POINTS = ('_vkGetInstanceProcAddr', '_vkCreateInstance', '_vk_icdGetInstanceProcAddr',
                '_vkGetMoltenVKConfigurationMVK', '_vkSetMoltenVKConfigurationMVK', '_vkGetMTLDeviceMVK',
                '_vkGetMTLCommandQueueMVK', '_vkGetMTLTextureMVK')
# Every Vulkan symbol the kept binary exports (llvm-nm -gU), to report the parity of the rebuild.
KEPT_EXPORTS = ROOT / 'build-utils/melonx/moltenvk/kept-binary-vulkan-exports.txt'


def sha(path):
    digest = hashlib.sha256()
    with open(path, 'rb') as stream:
        for block in iter(lambda: stream.read(1 << 20), b''):
            digest.update(block)
    return digest.hexdigest()


def annotate(kind, title, text):
    """GitHub annotations (at most 4000 characters each), the only part of a run read back through the API."""
    text = text.replace('%', '%25').replace('\r', '').replace('\n', '%0A')
    for index in range(0, min(len(text), 8 * 4000), 4000):
        print(f'::{kind} title={title} ({index // 4000 + 1})::{text[index:index + 4000]}', flush=True)


def run(args, cwd=None, capture=False):
    args = [str(arg) for arg in args]
    COMMANDS.append({'args': args, 'cwd': str(cwd or ROOT)})
    start = time.time()
    result = subprocess.run(args, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                            errors='replace')
    COMMANDS[-1].update(seconds=round(time.time() - start, 1), returncode=result.returncode)
    (OUT / 'logs' / f'{len(COMMANDS):02d}-{Path(args[0]).name}.log').write_text(result.stdout)
    if result.returncode:
        lines = result.stdout.splitlines()
        errors = [line for line in lines if ' error: ' in line or line.startswith('error:') or ': fatal error:' in line]
        annotate('error', f'{Path(args[0]).name} failed ({result.returncode})',
                 '\n'.join(['$ ' + ' '.join(args)] + errors[:60] + ['--- last lines ---'] + lines[-40:]))
        raise SystemExit(f'{args[0]} failed with {result.returncode}')
    return result.stdout.strip() if capture else None


def checkout():
    target = WORK / 'MoltenVK'
    run(['git', 'init', '-q', target])
    run(['git', '-C', target, 'remote', 'add', 'origin', PIN['repository']])
    run(['git', '-C', target, 'fetch', '-q', '--depth', '1', 'origin', PIN['revision']])
    run(['git', '-C', target, 'checkout', '-q', '--detach', 'FETCH_HEAD'])
    assert run(['git', '-C', target, 'rev-parse', 'HEAD'], capture=True) == PIN['revision']
    # A lightweight tag lists the commit itself, an annotated one also its peeled commit (^{}).
    refs = dict(reversed(line.split('\t')) for line in
                run(['git', 'ls-remote', PIN['repository'], f"refs/tags/{PIN['tag']}*"], capture=True).splitlines())
    tagged = refs.get(f"refs/tags/{PIN['tag']}^{{}}", refs.get(f"refs/tags/{PIN['tag']}"))
    assert tagged == PIN['revision'], ('the tag does not point at the pinned revision', refs)
    archive = OUT / 'sources' / f"MoltenVK-{PIN['revision']}.tar.gz"
    with archive.open('wb') as stream:
        subprocess.run(['git', '-C', str(target), 'archive', '--format=tar.gz', '--prefix', 'MoltenVK/', 'HEAD'],
                       stdout=stream, check=True)
    if not PIN.get('patch'):
        return target, ''
    patch = ROOT / PIN['patch']
    assert sha(patch) == PIN['patchSha256'], 'the patch differs from its pin'
    shutil.copy2(patch, OUT / 'sources' / patch.name)
    run(['git', '-C', target, 'apply', '--check', patch])
    run(['git', '-C', target, 'apply', patch])
    changed = run(['git', '-C', target, 'diff', '--stat'], capture=True)
    return target, changed


def build(target):
    run([target / 'fetchDependencies', '--ios'], cwd=target)
    run(['make', 'ios'], cwd=target)
    xcframework = target / 'Package/Latest/MoltenVK/dynamic/MoltenVK.xcframework'
    frameworks = [path for path in xcframework.glob('*/MoltenVK.framework') if 'simulator' not in path.parent.name]
    assert len(frameworks) == 1, frameworks
    destination = OUT / 'ios' / 'MoltenVK.framework'
    shutil.copytree(frameworks[0], destination, symlinks=True)
    with tarfile.open(OUT / 'sources/MoltenVK-external-sources.tar.gz', 'w:gz') as archive:
        archive.add(target / 'ExternalRevisions', arcname='ExternalRevisions')
        for child in sorted((target / 'External').iterdir()):
            if child.is_dir() and (child / '.git').exists():
                identity = run(['git', '-C', child, 'rev-parse', 'HEAD'], capture=True)
                archive.add(child, arcname=f'External/{child.name}-{identity}',
                            filter=lambda member: None if '/.git' in member.name else member)
    return destination / 'MoltenVK', frameworks[0].parent.name


def inspect(binary, slice_name, changed):
    data = binary.read_bytes()
    # The markers of the RewindBox patch, when one is pinned; an unmodified build must not contain them.
    markers = {marker: (marker.encode() in data) == bool(PIN.get('patch')) for marker in MARKERS}
    exported = set(line.split()[-1] for line in run(['nm', '-gU', binary], capture=True).splitlines() if line.strip())
    entry_points = {name: name in exported for name in ENTRY_POINTS}
    kept = KEPT_EXPORTS.read_text().split()
    assert (len(kept) == PIN['keptBinary']['exportedVulkanEntryPoints'] and
            hashlib.sha256('\n'.join(kept).encode()).hexdigest() == PIN['keptBinary']['exportedVulkanEntryPointsSha256'])
    missing = [name for name in kept if name not in exported]
    added = sorted(name for name in exported if name.startswith('_vk') and name not in kept)
    identity = {
        'pin': PIN,
        'patchApplied': changed.splitlines(),
        'xcframeworkSlice': slice_name,
        'binary': {'path': 'ios/MoltenVK.framework/MoltenVK', 'sha256': sha(binary), 'bytes': binary.stat().st_size},
        'architectures': run(['xcrun', 'lipo', '-archs', binary], capture=True),
        'buildVersion': run(['xcrun', 'vtool', '-show-build', binary], capture=True).splitlines()[1:],
        'installName': run(['otool', '-D', binary], capture=True).splitlines()[-1].strip(),
        'linkedLibraries': [line.strip().split(' (')[0] for line in
                            run(['otool', '-L', binary], capture=True).splitlines()[1:]],
        'markers': markers,
        'entryPoints': entry_points,
        'keptBinaryVulkanExports': {'count': len(kept), 'missing': missing, 'added': added},
        'toolchain': {'xcode': run(['xcodebuild', '-version'], capture=True).splitlines(),
                      'macOS': run(['sw_vers', '-productVersion'], capture=True)},
        'sourceArchives': [{'path': p.relative_to(OUT).as_posix(), 'sha256': sha(p), 'bytes': p.stat().st_size}
                           for p in sorted((OUT / 'sources').iterdir())],
        'status': 'source-built, not gameplay-tested',
    }
    (OUT / 'identity.json').write_text(json.dumps(identity, indent=2) + '\n')
    summary = (f"sha256 {identity['binary']['sha256']}, {identity['binary']['bytes']} bytes, "
               f"{identity['architectures']}, {' / '.join(identity['buildVersion'])}, install name "
               f"{identity['installName']}, slice {slice_name}, markers {sum(markers.values())}/{len(markers)}, "
               f"entry points {sum(entry_points.values())}/{len(entry_points)}, kept binary's Vulkan exports "
               f"{len(kept) - len(missing)}/{len(kept)} (missing: {' '.join(missing) or 'none'}; added: "
               f"{' '.join(added) or 'none'}), Xcode {' '.join(identity['toolchain']['xcode'])}")
    if not all(markers.values()) or not all(entry_points.values()):
        annotate('error', 'MoltenVK rebuild incomplete', summary + '\n' + json.dumps({'markers': markers,
                                                                                    'entryPoints': entry_points}))
        raise SystemExit('the rebuilt binary lacks a patch marker or an entry point')
    annotate('notice', 'MoltenVK rebuild', summary)


def main():
    shutil.rmtree(OUT, ignore_errors=True)
    shutil.rmtree(WORK, ignore_errors=True)
    for directory in (OUT / 'logs', OUT / 'sources', WORK):
        directory.mkdir(parents=True)
    try:
        target, changed = checkout()
        binary, slice_name = build(target)
        inspect(binary, slice_name, changed)
    finally:
        (OUT / 'commands.json').write_text(json.dumps(COMMANDS, indent=2) + '\n')
        timings = ', '.join(f"{Path(c['args'][0]).name} {c.get('seconds', '?')} s" for c in COMMANDS if c.get('seconds', 0) > 30)
        if timings:
            print('Long steps: ' + timings, flush=True)


if __name__ == '__main__':
    os.environ.setdefault('NSUnbufferedIO', 'YES')
    main()
