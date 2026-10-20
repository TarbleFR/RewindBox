#!/usr/bin/env python3
"""Inspect committed runtime dependencies without copying them into the app."""
import hashlib
import importlib.util
import json
from pathlib import Path
import struct
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
pin = json.loads((ROOT / 'build-utils/melonx/source.json').read_text())
source = Path(sys.argv[1]).resolve()
assert subprocess.check_output(['git', '-C', str(source), 'rev-parse', 'HEAD'], text=True).strip() == pin['revision']
assert not subprocess.check_output(['git', '-C', str(source), 'status', '--porcelain'], text=True).strip()
spec = importlib.util.spec_from_file_location('existing_macho_reader', ROOT / 'build-utils/libretro/build_cores.py')
reader = importlib.util.module_from_spec(spec)
spec.loader.exec_module(reader)
base = source / 'src/MeloNX/MeloNX/Dependencies'
names = ['libMoltenVK.dylib', 'BreakpointJIT.framework/BreakpointJIT',
         'SDL3.xcframework/ios-arm64/SDL3.framework/SDL3', 'libavcodec.dylib', 'libavutil.dylib']
for module in ['libavcodec', 'libavutil', 'libswresample', 'libswscale', 'libavformat', 'libavfilter']:
    names.append(f'{module}.xcframework/ios-arm64/{module}.framework/{module}')
binaries = []
for name in names:
    path = base / name
    data = path.read_bytes()
    thin = reader.thin_arm64(data)
    info = reader.macho(thin)
    assert info['platform'] == reader.PLATFORM_IOS and info['fileType'] == 6, name
    # Retain strong/weak load commands: a strong noncanonical system path is
    # materially different from an optional weak link.
    commands = []
    offset = 32
    count = struct.unpack_from('<I', thin, 16)[0]
    for _ in range(count):
        command, size = struct.unpack_from('<II', thin, offset)
        assert size >= 8 and offset + size <= len(thin)
        if command in [0xC, 0x80000018, 0x8000001F, 0xD]:
            name_offset = struct.unpack_from('<I', thin, offset + 8)[0]
            dependency = thin[offset + name_offset:offset + size].split(b'\0', 1)[0].decode()
            current = reader.version(struct.unpack_from('<I', thin, offset + 16)[0])
            commands.append(dict(command=hex(command), path=dependency, currentVersion=current))
        offset += size
    licenses = {str(p.relative_to(source)): hashlib.sha256(p.read_bytes()).hexdigest()
                for p in sorted(path.parent.glob('LICENSE*')) if p.is_file()}
    binaries.append(dict(path=str(path.relative_to(source)), bytes=len(data),
                         sha256=hashlib.sha256(data).hexdigest(),
                         arm64SliceSha256=hashlib.sha256(thin).hexdigest(),
                         **info, loadCommands=commands, adjacentLicenseFiles=licenses,
                         binaryBuildSourceIdentified=False))
surfaces = ['src/Ryujinx.Library/Library.cs', 'src/Ryujinx.Memory/DualMappedJitAllocator.cs',
            'src/Ryujinx.Graphics.Vulkan/MoltenVK/MVKInitialization.cs',
            'src/Ryujinx.Graphics.Vulkan/MoltenVK/MoltenVkMetalInterop.cs',
            'src/Ryujinx.Graphics.Nvdec.FFmpeg/Native/FFmpegApi.cs',
            'src/Ryujinx.Input.Native/NativeGamepad.cs',
            'src/Ryujinx.Memory/DonatedMemory.cs', 'src/Ryujinx.Memory/MachJitWorkaround.cs']
report = dict(engineRepository=pin['repository'], engineRevision=pin['revision'], binaries=binaries,
              inspectedSourceInputs={p: hashlib.sha256((source / p).read_bytes()).hexdigest() for p in surfaces},
              findings={
                  'strongVersionedSystemFrameworkPaths': [dict(binary=b['path'], **c) for b in binaries
                      for c in b['loadCommands'] if c['command'] == '0xc' and '/Versions/' in c['path']],
                  'ffmpegResolverRequestedNames': ['libavcodec.60.dylib', 'libavcodec.59.dylib', 'libavutil.58.dylib', 'libavutil.57.dylib'],
                  'ffmpegFrameworkIdentitiesNeedAnExplicitResolver': True,
                  'binaryPresenceDoesNotProveCorrespondingBuildSource': True,
                  'nativeGamepadDisposeAlsoDisconnectsSharedDriverObject': True,
                  'nativeGamepadConfigurationCurrentlyDisposesThatSharedObject': True,
                  'donatedMemoryOfferAndWithdrawResetLiveAllocationOwnership': True,
                  'unrecognizedSharedMemoryReleaseFallsBackToVmDeallocate': True,
              }, copiedIntoNeoStation=False, packagingApproved=False, deviceLoaded=False)
out = Path(sys.argv[2]).resolve()
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps(report, indent=2) + '\n')
print(f'Inspected {len(binaries)} pinned ARM64/iOS libraries; no dependency packaged or device-load claim.')
