#!/usr/bin/env python3
"""Run NeoStation's embedded libretro session with real cores in the iOS Simulator (macOS).

`fetch` downloads the pinned test inputs: RetroArch's MoltenVK simulator
slice (same RetroArch revision as the delivered device slice), the
pspautotests GPU test program `simple.prx` and the ftpd 3DS homebrew
`ftpd.3dsx`. Every file is checked against its pinned identity.

`run` builds test/libretro_simulator/probe.m with the libretro bridge
sources (and the Flutter-free sources of the external_display pod the bridge
links against since Build 447, and of the neo_shader_kit pod it links
against since Build 450 when the bridge tree imports it, their public
headers staged as <pod/...> by test/libretro_ios_syntax_test.py) into a
small UIKit app and embeds:
- PPSSPP, Azahar and DeSmuME from the cores artifact the delivery pins,
  with their Mach-O platform switched from iOS (2) to iOS Simulator (7) -
  no other byte changes; DeSmuME's older LC_VERSION_MIN_IPHONEOS command is
  replaced by vtool, its code untouched - and signed ad hoc;
- the MoltenVK simulator slice;
- the NeoTest core and the Vulkan test core of test/libretro_host (the
  latter uses the frontend's Vulkan device like Azahar: it creates it,
  leaves it to the frontend and destroys its objects through it in
  retro_unload_game), built for the simulator;
- PPSSPP's system files, and the content: NeoTest's game, simple.prx, an
  ISO built here around simple.prx (PSP_GAME/SYSDIR/EBOOT.BIN, PARAM.SFO,
  "PSP GAME" system id: the ISO path of real games), ftpd.3dsx and a
  minimal homebrew Nintendo DS image written here (build_nds).
It boots a simulator, runs the scenarios (launch like the plugin, run,
"Quit game", relaunch) and checks each outcome, the session journal's
teardown order and that the game view is gone. Evidence (results, progress
log, journals, simulator log, crash reports) goes to --evidence; when the
process dies, the crashed thread of its crash report is printed too.

The internal resolution scenarios (Build 455) choose a resolution through
the in-game menu's session call while the game runs, then compare the
frames the real core produces before and after, and what the session saved
(docs/libretro-resolution.md): DeSmuME applies it during the game, keeps it
for the core across a relaunch and for one game; PPSSPP, which gets no
OpenGL ES context in the simulator and draws in its own software context,
must be offered nothing and keep running.

`ppsspp-crowded` and `ppsspp-crowded-prx` leave no base of PPSSPP's memory
window free except what the bridge reserved after launch (see probe.m), the
iPhone's state when PSP games failed with "Memory init failed", and only
holes smaller than 8 MiB below it: PPSSPP's arena must go to the reserved
arena slot (32 MiB of RAM) or above the window (64 MiB).

With --sources (another bridge tree, e.g. the commit before a fix) and
--expect unfixed, it records whether that tree's process dies while a
scenario is being closed, or whether PPSSPP finds no memory base in the
crowded window; it never fails on those outcomes.

Azahar itself cannot start in the simulator: the simulator GPU has no
arrays of textures or samplers, so its renderer throws
vk::FeatureNotPresentError (createDescriptorSetLayoutUnique) in
context_reset. Its scenarios run only when named with --only; the Vulkan
test core covers the teardown Azahar depends on.
"""
import argparse
import hashlib
import json
import os
import plistlib
import re
import shutil
import struct
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BRIDGE = ROOT / 'packages/libretro_internal_bridge/ios'
CATALOG = ROOT / 'lib/services/libretro_core_catalog.dart'
# Build 455: the internal resolution rules Dart sends to the session
# (LibretroResolution.nativeRules(), checked by test/libretro_resolution_test.dart).
RESOLUTION_RULES = ROOT / 'test/fixtures/libretro_resolution/native_rules.json'
# Build 447: the bridge imports <external_display/Name.h> and calls the pod's
# coordinator. The pod sources without Flutter (coordinator, preferences,
# scene delegate) are compiled and linked with the bridge; the plugin and the
# menu engine import Flutter and stay out, like the bridge's own plugin.
EXTERNAL_DISPLAY = ROOT / 'packages/external_display/ios/Classes'
EXTERNAL_DISPLAY_SOURCES = ('NeoExternalDisplayCoordinator.m', 'NeoExternalDisplayPreferences.m',
                            'NeoExternalDisplaySceneDelegate.m')
sys.path.insert(0, str(ROOT / 'test'))
from libretro_ios_syntax_test import stage_dependency_headers  # noqa: E402
# Build 450: the bridge imports <neo_shader_kit/Name.h> (slang shaders). The
# kit without its Flutter plugin class is compiled for the simulator and
# linked with the bridge, as the delivery links the pod.
from neo_shader_kit_ios_build import compile_kit, podspec_frameworks  # noqa: E402
TARGET = 'arm64-apple-ios17.4-simulator'
BUNDLE_ID = 'com.neostation.libretro.probe'
DEFINES = ('GLES_SILENCE_DEPRECATION=1', 'COREVIDEO_SILENCE_GL_DEPRECATION=1', 'VK_USE_PLATFORM_METAL_EXT=1',
           'VK_NO_PROTOTYPES=1', 'RC_CLIENT_SUPPORTS_HASH=1')
# The bridge's frameworks, plus MetalKit for the external_display coordinator
# (its podspec's frameworks: it preserves an MTKView's drawable on the move).
FRAMEWORKS = ('UIKit', 'Foundation', 'Metal', 'MetalKit', 'QuartzCore', 'AVFoundation', 'GameController', 'OpenGLES',
              'CoreVideo', 'Security', 'ImageIO', 'CoreGraphics')
REAL_CORES = ('ppsspp', 'azahar', 'desmume')
# Built here from test/libretro_host for the simulator.
TEST_CORES = {'neotest': 'test_core.c', 'neovk': 'vulkan_test_core.c'}
LC_BUILD_VERSION = 0x32
LC_VERSION_MIN_IPHONEOS = 0x25
PLATFORM_IOS = 2
PLATFORM_IOS_SIMULATOR = 7

RETROARCH_REVISION = 'df16ef193cbe385b87e8a1cf27b66da35bf3c0e0'
MOLTENVK_SIMULATOR = 'pkg/apple/Frameworks/MoltenVK.xcframework/ios-arm64_x86_64-simulator/MoltenVK.framework'
PSPAUTOTESTS_REVISION = 'cd3d49c4c5d8fa4d84779a216270db7408842017'
# name: (url, git blob SHA-1 or None, size, SHA-256 or None)
INPUTS = {
    'MoltenVK.framework/MoltenVK': (
        f'https://raw.githubusercontent.com/libretro/RetroArch/{RETROARCH_REVISION}/{MOLTENVK_SIMULATOR}/MoltenVK',
        'ded496ced533a5397532741e600ea75be97dda41', 13804080, None),
    'MoltenVK.framework/Info.plist': (
        f'https://raw.githubusercontent.com/libretro/RetroArch/{RETROARCH_REVISION}/{MOLTENVK_SIMULATOR}/Info.plist',
        '231e8d6e5dde1cb651564d25d6443ef507bd89e4', 728, None),
    'simple.prx': (
        f'https://raw.githubusercontent.com/hrydgard/pspautotests/{PSPAUTOTESTS_REVISION}/tests/gpu/simple/simple.prx',
        'dd010448eb8d19f91e409fc280023f823b5fc209', 133594, None),
    'ftpd.3dsx': (
        'https://github.com/mtheall/ftpd/releases/download/v3.2.1/ftpd.3dsx', None, 1408252, None),
}

# Journal lines of a PSP boot in a crowded window: the reserved span's view
# ranges and arena slot released, PPSSPP's memory at that base, the span
# held again after the session.
CROWDED_LOG = ['view ranges and arena slot released for this boot', "PPSSPP's memory at the reserved base",
               'teardown: [HOST] PPSSPP window held at']
# Scenarios run in this order; a process that dies stops the rest.
SCENARIOS = [
    {'name': 'neotest-1', 'core': 'neotest', 'content': 'content/Test Game.ntc', 'console': 'gb', 'expect': 'run'},
    {'name': 'neotest-2', 'core': 'neotest', 'content': 'content/Test Game.ntc', 'console': 'gb', 'expect': 'run'},
    {'name': 'neotest-startup-stop', 'core': 'neotest', 'content': 'content/Test Game.ntc', 'console': 'gb',
     'lockedOptions': {'neotest_shutdown_frame': '3'}, 'expect': 'core-stopped'},
    {'name': 'ppsspp-prx', 'core': 'ppsspp', 'content': 'content/simple.prx', 'console': 'psp', 'expect': 'run'},
    {'name': 'ppsspp-iso-1', 'core': 'ppsspp', 'content': 'content/probe.iso', 'console': 'psp', 'expect': 'run'},
    {'name': 'ppsspp-iso-2', 'core': 'ppsspp', 'content': 'content/probe.iso', 'console': 'psp', 'expect': 'run'},
    # A crowded window (see probe.m): the ISO boots with 32 MiB of RAM (a
    # 40 MiB arena, which must go to the arena slot), the PRX with 64 MiB
    # (PSP-2000 model; a 72 MiB arena, which fits neither slot nor RAM range).
    {'name': 'ppsspp-crowded', 'core': 'ppsspp', 'content': 'content/probe.iso', 'console': 'psp', 'expect': 'run',
     'crowdWindow': True, 'requiredLog': CROWDED_LOG + ['PPSSPP memory base 0x', ', 32 MiB of PSP RAM']},
    {'name': 'ppsspp-crowded-prx', 'core': 'ppsspp', 'content': 'content/simple.prx', 'console': 'psp',
     'expect': 'run', 'crowdWindow': True,
     'requiredLog': CROWDED_LOG + ['PPSSPP memory base 0x', ', 64 MiB of PSP RAM']},
    {'name': 'neovk-1', 'core': 'neovk', 'content': 'content/Test Game.ntc', 'console': 'gb', 'expect': 'run',
     'requiredLog': ['neovk create_device: device created by the core',
                     "neovk unload_game: resources destroyed through the frontend's device"]},
    {'name': 'neovk-2', 'core': 'neovk', 'content': 'content/Test Game.ntc', 'console': 'gb', 'expect': 'run',
     'requiredLog': ["neovk unload_game: resources destroyed through the frontend's device"]},
    # Build 455: the in-game menu's internal resolution with real cores,
    # through the session call of the menu (docs/libretro-resolution.md).
    # DeSmuME (software rasterizer, a live option) on a minimal homebrew
    # image (build_nds): native 256x192 per screen, both screens stacked
    # (256x384); x2 chosen for every game of the core doubles the frames once
    # the game runs again and is saved for the core; a relaunch starts at x2
    # and native chosen for this game only gives 256x384 again at once, saved
    # for this game while the core keeps x2.
    {'name': 'desmume-resolution-live', 'core': 'desmume', 'content': 'content/probe.nds', 'console': 'nds',
     'expect': 'run', 'runSeconds': 5.0,
     'resolution': {'beforeSeconds': 2.0, 'select': '512x384', 'beforeWidth': 256, 'scale': 2,
                    'key': 'desmume_internal_resolution', 'apply': 'live', 'core': '512x384', 'game': None},
     'requiredLog': ['load: resolution desmume_internal_resolution (live, profile) in effect 256x192',
                     'menu: resolution desmume_internal_resolution=512x384 for every game of the core']},
    {'name': 'desmume-resolution-relaunch', 'core': 'desmume', 'content': 'content/probe.nds', 'console': 'nds',
     'expect': 'run', 'runSeconds': 5.0,
     'resolution': {'beforeSeconds': 2.0, 'select': '256x192', 'gameScope': True, 'beforeWidth': 512, 'scale': 0.5,
                    'key': 'desmume_internal_resolution', 'apply': 'live', 'core': '512x384', 'game': '256x192'},
     'requiredLog': ['load: resolution desmume_internal_resolution (live, profile) in effect 512x384',
                     'menu: resolution desmume_internal_resolution=256x192 for this game']},
    # PPSSPP draws in its own software context when it gets no OpenGL ES
    # context (the simulator's): its frames stay 480x272 (480x270, cropped to
    # 16:9 by default) whatever the option, and a change during the game
    # would reset a hardware context it does not have. NeoStation must offer
    # nothing then, refuse the menu's choice and keep the game running. With
    # an OpenGL ES context the same scenario expects the live x2 instead.
    {'name': 'ppsspp-resolution', 'core': 'ppsspp', 'content': 'content/simple.prx', 'console': 'psp',
     'expect': 'run', 'runSeconds': 5.0,
     'resolution': {'beforeSeconds': 2.0, 'select': '960x544', 'beforeWidth': 480, 'byRenderer': {
         'software': {'scale': 1, 'refused': True, 'inapplicable': 'ppsspp_internal_resolution', 'core': None,
                      'requiredLog': ['load: resolution ppsspp_internal_resolution of PPSSPP does not apply '
                                      '(renderer software)']},
         'gles': {'scale': 2, 'key': 'ppsspp_internal_resolution', 'apply': 'live', 'core': '960x544',
                  'requiredLog': ['load: resolution ppsspp_internal_resolution (live, profile) in effect 480x272',
                                  'menu: resolution ppsspp_internal_resolution=960x544 for every game of the core']},
     }}},
    # Only with --only: the simulator GPU cannot start Azahar (see above).
    {'name': 'azahar-1', 'core': 'azahar', 'content': 'content/ftpd.3dsx', 'console': '3ds', 'expect': 'run',
     'runSeconds': 4.0, 'default': False},
    {'name': 'azahar-2', 'core': 'azahar', 'content': 'content/ftpd.3dsx', 'console': '3ds', 'expect': 'run',
     'runSeconds': 4.0, 'default': False},
]
# Journal lines of a closed session, in the order RetroArch tears a core down.
TEARDOWN_ORDER = (
    'teardown: started',
    'teardown: context_destroy called',
    'teardown: context_destroy returned',
    'teardown: retro_unload_game called',
    'teardown: retro_unload_game returned',
    'teardown: retro_deinit called',
    'teardown: retro_deinit returned',
    'teardown: releasing the',
    'teardown: renderer released',
    'teardown: dlclose called',
    'teardown: dlclose returned',
    'stop: game view dismissed, returning to NeoStation',
)


def run(arguments, **options):
    print('+ ' + ' '.join(str(argument) for argument in arguments), flush=True)
    return subprocess.run([str(argument) for argument in arguments], check=True, **options)


def output(arguments):
    return subprocess.run([str(argument) for argument in arguments], check=True, capture_output=True,
                          text=True).stdout


def git_blob_sha1(data):
    return hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest()


# --- fetch ---------------------------------------------------------------

def fetch(destination):
    destination.mkdir(parents=True, exist_ok=True)
    identities = {}
    for name, (url, blob, size, digest) in INPUTS.items():
        request = urllib.request.Request(url, headers={'User-Agent': 'NeoStation-CI'})
        with urllib.request.urlopen(request, timeout=300) as response:
            data = response.read()
        if len(data) != size:
            raise SystemExit(f'{name}: {len(data)} bytes, pinned {size}')
        if blob is not None and git_blob_sha1(data) != blob:
            raise SystemExit(f'{name}: git blob {git_blob_sha1(data)}, pinned {blob}')
        sha256 = hashlib.sha256(data).hexdigest()
        if digest is not None and sha256 != digest:
            raise SystemExit(f'{name}: SHA-256 {sha256}, pinned {digest}')
        target = destination / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        identities[name] = {'url': url, 'bytes': size, 'sha256': sha256, 'gitBlob': git_blob_sha1(data)}
        print(f'{name}: {size} bytes, SHA-256 {sha256}', flush=True)
    (destination / 'identities.json').write_text(json.dumps(identities, indent=2) + '\n')


# --- catalog -------------------------------------------------------------

def catalog_block(text, kind, identifier):
    match = re.search(rf"^    '{re.escape(identifier)}': {kind}\((.*?)^    \),", text, flags=re.M | re.S)
    if match is None:
        raise SystemExit(f'{kind} {identifier} not found in {CATALOG.relative_to(ROOT)}')
    return match.group(1)


def string_map(block, field):
    match = re.search(rf'{field}: \{{(.*?)\}}', block, flags=re.S)
    if match is None:
        return {}
    return dict(re.findall(r"'([^']+)':\s*'([^']*)'", match.group(1)))


def core_settings(text, core):
    block = catalog_block(text, 'LibretroCore', core)
    context = re.search(r'preferredHardwareContext: LibretroHardwareContext\.(\w+)', block)
    contexts = {'none': 0, 'openGLES3': 4, 'vulkan': 6}
    return {
        'preferredHardwareContext': contexts[context.group(1)] if context else 0,
        'optionDefaults': string_map(block, 'optionDefaults'),
        'noJitOverrides': string_map(block, 'noJitOverrides'),
        'lockedOptions': string_map(block, 'lockedOptions'),
    }


def console_geometry(text, console):
    block = catalog_block(text, 'LibretroConsole', console)
    name = re.search(r"name: '([^']+)'", block).group(1)
    width = int(re.search(r'width: (\d+)', block).group(1))
    height = int(re.search(r'height: (\d+)', block).group(1))
    entry = {'size': [width, height]}
    regions = dict((key, [float(value) for value in values.split(',')])
                   for key, values in re.findall(r"'(\w+)': \[([^\]]+)\]", block))
    if regions:
        entry['regions'] = regions
    return name, entry


# --- content -------------------------------------------------------------

def param_sfo(entries):
    """A PSP PARAM.SFO: text values UTF-8 (0x0204), numbers int32 (0x0404)."""
    keys = b''
    data = b''
    index = b''
    for key, value in sorted(entries.items()):
        key_offset = len(keys)
        keys += key.encode() + b'\0'
        if isinstance(value, int):
            payload = struct.pack('<I', value)
            index += struct.pack('<HHIII', key_offset, 0x0404, 4, 4, len(data))
        else:
            raw = value.encode() + b'\0'
            capacity = (len(raw) + 3) & ~3
            payload = raw.ljust(capacity, b'\0')
            index += struct.pack('<HHIII', key_offset, 0x0204, len(raw), capacity, len(data))
        data += payload
    keys = keys.ljust((len(keys) + 3) & ~3, b'\0')
    key_table = 20 + len(index)
    data_table = key_table + len(keys)
    return struct.pack('<4sIIII', b'\0PSF', 0x101, key_table, data_table, len(entries)) + index + keys + data


def crc16(data):
    """CRC-16 of the Nintendo DS header (initial 0xFFFF, reflected 0x8005)."""
    value = 0xFFFF
    for byte in data:
        value ^= byte
        for _ in range(8):
            value = (value >> 1) ^ 0xA001 if value & 1 else value >> 1
    return value


def build_nds(output_path):
    """A minimal homebrew Nintendo DS image written by the probe itself (no
    third-party content): both processors loop on one branch. Its ARM9
    binary below 0x4000 makes it homebrew for DeSmuME (no secure area, no
    logo check, no firmware needed), which boots it directly and draws both
    screens every frame."""
    rom = bytearray(0x8000)
    rom[0x000:0x00C] = b'NEOPROBE'.ljust(12, b'\0')
    rom[0x00C:0x010] = b'####'
    # ARM9 and ARM7: ROM offset, entry, RAM address, size.
    struct.pack_into('<IIII', rom, 0x020, 0x200, 0x02000000, 0x02000000, 4)
    struct.pack_into('<IIII', rom, 0x030, 0x204, 0x02380000, 0x02380000, 4)
    struct.pack_into('<II', rom, 0x080, len(rom), 0x4000)
    struct.pack_into('<I', rom, 0x200, 0xEAFFFFFE)  # b .
    struct.pack_into('<I', rom, 0x204, 0xEAFFFFFE)  # b .
    struct.pack_into('<H', rom, 0x15E, crc16(rom[:0x15E]))
    output_path.write_bytes(bytes(rom))


def build_iso(program, output_path, work):
    """An ISO 9660 image like a PSP disc: PSP_GAME/PARAM.SFO and
    PSP_GAME/SYSDIR/EBOOT.BIN, system id "PSP GAME"."""
    staging = work / 'iso'
    (staging / 'PSP_GAME/SYSDIR').mkdir(parents=True)
    shutil.copyfile(program, staging / 'PSP_GAME/SYSDIR/EBOOT.BIN')
    (staging / 'PSP_GAME/PARAM.SFO').write_bytes(param_sfo({
        'BOOTABLE': 1, 'CATEGORY': 'UG', 'DISC_ID': 'NEOS00001', 'DISC_NUMBER': 1, 'DISC_TOTAL': 1,
        'DISC_VERSION': '1.00', 'PARENTAL_LEVEL': 1, 'PSP_SYSTEM_VER': '1.00', 'REGION': 0x8000,
        'TITLE': 'NeoStation probe',
    }))
    target = work / 'probe.iso'
    run(['hdiutil', 'makehybrid', '-iso', '-joliet', '-default-volume-name', 'NEOPROBE', '-o', target, staging])
    image = bytearray(target.read_bytes())
    if image[0x8001:0x8006] != b'CD001':
        raise SystemExit('hdiutil did not produce an ISO 9660 primary volume descriptor')
    image[0x8008:0x8028] = b'PSP GAME'.ljust(32, b' ')
    output_path.write_bytes(image)


# --- build ---------------------------------------------------------------

def sdk_path():
    return output(['xcrun', '--sdk', 'iphonesimulator', '--show-sdk-path']).strip()


def imports_shader_kit(sources):
    """Bridge trees from Build 450 on import the neo_shader_kit pod."""
    return any('<neo_shader_kit/' in path.read_text(encoding='utf-8', errors='replace')
               for path in (sources / 'Classes').glob('*.m'))


def compile_probe(sources, sdk, work, app):
    # <pod/Name.h> resolves as the bridge sees its pods: their public
    # headers and nothing else (test/libretro_ios_syntax_test.py).
    include = stage_dependency_headers(work)
    includes = [sources / 'Classes', sources / 'ThirdParty/include', sources / 'ThirdParty/include/libretro',
                sources / 'ThirdParty/rcheevos/include', sources / 'ThirdParty/rcheevos/src', include]
    base = ['xcrun', '--sdk', 'iphonesimulator', 'clang', '-target', TARGET, '-isysroot', sdk, '-O1',
            '-Wno-deprecated-declarations']
    for include in includes:
        base += ['-I', str(include)]
    for define in DEFINES:
        base += ['-D', define]
    units = [path for path in sorted((sources / 'Classes').glob('*.m')) if path.name != 'LibretroInternalBridgePlugin.m']
    units += [EXTERNAL_DISPLAY / name for name in EXTERNAL_DISPLAY_SOURCES]
    units += sorted((sources / 'ThirdParty/rcheevos/src').rglob('*.c'))
    units.append(ROOT / 'test/libretro_simulator/probe.m')
    objects = []
    for index, unit in enumerate(units):
        target = work / f'{index:03d}_{unit.stem}.o'
        arguments = list(base)
        if unit.suffix == '.m':
            arguments += ['-fobjc-arc', '-fmodules']
        result = subprocess.run(arguments + ['-c', str(unit), '-o', str(target)], capture_output=True, text=True)
        if result.returncode != 0:
            print(result.stderr, flush=True)
            raise SystemExit(f'simulator compilation failed: {unit}')
        objects.append(target)
    print(f'compiled {len(units)} sources for the simulator', flush=True)
    frameworks = list(FRAMEWORKS)
    libraries = ['-lz']
    if imports_shader_kit(sources):
        objects += compile_kit('iphonesimulator', TARGET, sdk, work / 'neo_shader_kit', plugin=False,
                               optimization='-O1')
        frameworks += [name for name in podspec_frameworks() if name not in frameworks]
        libraries.append('-lc++')
    link = ['xcrun', '--sdk', 'iphonesimulator', 'clang', '-target', TARGET, '-isysroot', sdk, '-fobjc-arc',
            *(str(item) for item in objects)]
    for framework in frameworks:
        link += ['-framework', framework]
    link += [*libraries, '-Wl,-rpath,@executable_path/Frameworks', '-o', str(app / 'Probe')]
    run(link)


def build_test_cores(sdk, frameworks):
    for core, source in TEST_CORES.items():
        name = f'{core}_libretro'
        target = frameworks / f'{name}.framework'
        target.mkdir(parents=True)
        run(['xcrun', '--sdk', 'iphonesimulator', 'clang', '-target', TARGET, '-isysroot', sdk, '-dynamiclib', '-O1',
             '-Wall', '-I', BRIDGE / 'ThirdParty/include', '-I', BRIDGE / 'ThirdParty/include/libretro',
             ROOT / 'test/libretro_host' / source, '-install_name', f'@rpath/{name}.framework/{name}',
             '-o', target / name])
        framework_plist(target, name)


def framework_plist(target, executable):
    with open(target / 'Info.plist', 'wb') as handle:
        plistlib.dump({'CFBundleExecutable': executable, 'CFBundleIdentifier': f'{BUNDLE_ID}.{executable}',
                       'CFBundlePackageType': 'FMWK', 'CFBundleVersion': '1', 'CFBundleShortVersionString': '1.0',
                       'CFBundleSupportedPlatforms': ['iPhoneSimulator'], 'MinimumOSVersion': '17.4'}, handle)


def platform_commands(data, binary):
    """The LC_BUILD_VERSION and LC_VERSION_MIN_IPHONEOS commands of a thin
    64-bit Mach-O: [(command, offset)]."""
    magic, _, _, _, count = struct.unpack_from('<IiiII', data, 0)
    if magic != 0xFEEDFACF:
        raise SystemExit(f'{binary}: not a thin 64-bit Mach-O')
    cursor = 32
    found = []
    for _ in range(count):
        command, size = struct.unpack_from('<II', data, cursor)
        if command in (LC_BUILD_VERSION, LC_VERSION_MIN_IPHONEOS):
            found.append((command, cursor))
        cursor += size
    return found


def retarget_to_simulator(binary):
    """Switches LC_BUILD_VERSION's platform from iOS to iOS Simulator (only
    that byte changes). An older build that names its platform with
    LC_VERSION_MIN_IPHONEOS instead (DeSmuME's) gets an LC_BUILD_VERSION
    for the simulator from Apple's vtool in its place; its code and data
    do not change."""
    data = bytearray(binary.read_bytes())
    commands = platform_commands(data, binary)
    builds = [offset for command, offset in commands if command == LC_BUILD_VERSION]
    if not builds and [command for command, _ in commands] == [LC_VERSION_MIN_IPHONEOS]:
        sdk = output(['xcrun', '--sdk', 'iphonesimulator', '--show-sdk-version']).strip()
        converted = binary.with_name(binary.name + '.simulator')
        run(['xcrun', 'vtool', '-set-build-version', str(PLATFORM_IOS_SIMULATOR), '17.4', sdk, '-replace',
             '-output', converted, binary])
        data = bytearray(converted.read_bytes())
        converted.unlink()
        commands = platform_commands(data, binary)
        builds = [offset for command, offset in commands if command == LC_BUILD_VERSION]
        if len(commands) != 1 or len(builds) != 1 or \
                struct.unpack_from('<I', data, builds[0] + 8)[0] != PLATFORM_IOS_SIMULATOR:
            raise SystemExit(f'{binary}: vtool did not leave one iOS Simulator LC_BUILD_VERSION')
        binary.write_bytes(data)
        binary.chmod(0o755)
        return
    if len(builds) != 1:
        raise SystemExit(f'{binary}: {len(builds)} LC_BUILD_VERSION commands, expected 1')
    platform = struct.unpack_from('<I', data, builds[0] + 8)[0]
    if platform != PLATFORM_IOS:
        raise SystemExit(f'{binary}: platform {platform}, expected iOS')
    struct.pack_into('<I', data, builds[0] + 8, PLATFORM_IOS_SIMULATOR)
    binary.write_bytes(data)
    binary.chmod(0o755)


def assemble(args, sources, work):
    sdk = sdk_path()
    app = work / 'Probe.app'
    frameworks = app / 'Frameworks'
    frameworks.mkdir(parents=True)
    compile_probe(sources, sdk, work, app)
    build_test_cores(sdk, frameworks)
    cores = Path(args.cores)
    for core in REAL_CORES:
        source = cores / 'Frameworks' / f'{core}_libretro.framework'
        target = frameworks / source.name
        shutil.copytree(source, target)
        retarget_to_simulator(target / f'{core}_libretro')
        framework_plist(target, f'{core}_libretro')
    inputs = Path(args.inputs)
    shutil.copytree(inputs / 'MoltenVK.framework', frameworks / 'MoltenVK.framework')
    (frameworks / 'MoltenVK.framework/MoltenVK').chmod(0o755)
    shutil.copytree(cores / 'LibretroSystem', app / 'LibretroSystem')
    content = app / 'content'
    content.mkdir()
    (content / 'Test Game.ntc').write_bytes(bytes(range(1, 101)))
    shutil.copyfile(inputs / 'simple.prx', content / 'simple.prx')
    shutil.copyfile(inputs / 'ftpd.3dsx', content / 'ftpd.3dsx')
    build_iso(inputs / 'simple.prx', content / 'probe.iso', work)
    build_nds(content / 'probe.nds')
    catalog = CATALOG.read_text(encoding='utf-8')
    geometry = {}
    names = {}
    for console in ('gb', 'psp', '3ds', 'nds'):
        names[console], geometry[console] = console_geometry(catalog, console)
    scenarios = []
    for scenario in SCENARIOS:
        if args.only and scenario['name'] not in args.only:
            continue
        if not args.only and not scenario.get('default', True):
            continue
        entry = dict(scenario)
        if scenario['core'] in REAL_CORES:
            entry.update(core_settings(catalog, scenario['core']))
        entry['consoleName'] = names[scenario['console']]
        scenarios.append(entry)
    config = {'source': args.label, 'consoleGeometry': geometry, 'scenarios': scenarios}
    if RESOLUTION_RULES.is_file():
        config['resolution'] = json.loads(RESOLUTION_RULES.read_text(encoding='utf-8'))
    (app / 'probe-config.json').write_text(json.dumps(config, indent=2) + '\n')
    with open(app / 'Info.plist', 'wb') as handle:
        plistlib.dump({'CFBundleIdentifier': BUNDLE_ID, 'CFBundleExecutable': 'Probe',
                       'CFBundleName': 'Libretro Probe', 'CFBundlePackageType': 'APPL', 'CFBundleVersion': '1',
                       'CFBundleShortVersionString': '1.0', 'LSRequiresIPhoneOS': True, 'MinimumOSVersion': '17.4',
                       'UIDeviceFamily': [1, 2], 'UILaunchScreen': {},
                       'CFBundleSupportedPlatforms': ['iPhoneSimulator'],
                       'UISupportedInterfaceOrientations': ['UIInterfaceOrientationLandscapeLeft',
                                                            'UIInterfaceOrientationLandscapeRight',
                                                            'UIInterfaceOrientationPortrait']}, handle)
    for framework in sorted(frameworks.iterdir()):
        run(['codesign', '--force', '--sign', '-', '--timestamp=none', framework])
    run(['codesign', '--force', '--sign', '-', '--timestamp=none', app])
    return app, scenarios


# --- simulator -----------------------------------------------------------

def pick_device():
    listing = json.loads(output(['xcrun', 'simctl', 'list', 'devices', 'available', '--json']))
    candidates = []
    for runtime, devices in listing['devices'].items():
        match = re.search(r'iOS-(\d+)-(\d+)', runtime)
        if match is None:
            continue
        for device in devices:
            if device.get('isAvailable') and device['name'].startswith('iPhone'):
                candidates.append(((int(match.group(1)), int(match.group(2))), device['name'], device['udid']))
    if not candidates:
        raise SystemExit('No iPhone simulator available')
    candidates.sort(reverse=True)
    version, name, udid = candidates[0]
    print(f'simulator: {name}, iOS {version[0]}.{version[1]} ({udid})', flush=True)
    return udid, f'{name} iOS {version[0]}.{version[1]}'


def probe_pid(console_path):
    """`simctl launch` prints "<bundle id>: <pid>" first."""
    try:
        match = re.search(rf'{re.escape(BUNDLE_ID)}: (\d+)', console_path.read_text(errors='replace'))
    except OSError:
        return None
    return int(match.group(1)) if match else None


def run_in_simulator(app, evidence, timeout):
    udid, description = pick_device()
    # A fresh device for every run: nothing left by a previous probe.
    subprocess.run(['xcrun', 'simctl', 'shutdown', udid], capture_output=True)
    run(['xcrun', 'simctl', 'erase', udid])
    subprocess.run(['xcrun', 'simctl', 'boot', udid], capture_output=True)
    run(['xcrun', 'simctl', 'bootstatus', udid, '-b'], timeout=600)
    run(['xcrun', 'simctl', 'install', udid, app])
    data = Path(output(['xcrun', 'simctl', 'get_app_container', udid, BUNDLE_ID, 'data']).strip())
    documents = data / 'Documents'
    console_path = evidence / 'probe-console.log'
    console = open(console_path, 'w')
    launched_at = time.time()
    process = subprocess.Popen(['xcrun', 'simctl', 'launch', '--console-pty', '--terminate-running-process', udid,
                                BUNDLE_ID], stdout=console, stderr=subprocess.STDOUT)
    finished = False
    exited = False
    silent_sampled = False
    deadline = time.time() + timeout
    while time.time() < deadline:
        if (documents / 'probe.json').is_file():
            finished = True
            break
        if process.poll() is not None:
            exited = True
            break
        progress = documents / 'probe-progress.log'
        if not silent_sampled and time.time() - launched_at > 120 and not progress.is_file():
            # Launched but silent: record where its threads are.
            silent_sampled = True
            pid = probe_pid(console_path)
            print(f'the probe wrote no progress in 120 s (pid {pid}); sampling it', flush=True)
            if pid:
                subprocess.run(['sample', str(pid), '3', '-file', str(evidence / 'probe-silent-sample.txt')],
                               capture_output=True)
        time.sleep(1)
    if not finished and not exited:
        pid = probe_pid(console_path)
        if pid:
            subprocess.run(['sample', str(pid), '3', '-file', str(evidence / 'probe-timeout-sample.txt')],
                           capture_output=True)
    time.sleep(1)
    subprocess.run(['xcrun', 'simctl', 'terminate', udid, BUNDLE_ID], capture_output=True)
    try:
        process.wait(timeout=15)
    except subprocess.TimeoutExpired:
        process.kill()
    console.close()
    for name in ('probe.json', 'probe-partial.json', 'probe-progress.log'):
        if (documents / name).is_file():
            shutil.copyfile(documents / name, evidence / name)
    logs = documents / 'Libretro/Logs'
    if logs.is_dir():
        shutil.copytree(logs, evidence / 'Logs', dirs_exist_ok=True)
    reports = Path.home() / 'Library/Logs/DiagnosticReports'
    for report in sorted(reports.glob('Probe*')) if reports.is_dir() else []:
        if report.stat().st_mtime >= launched_at - 5:
            shutil.copyfile(report, evidence / report.name)
    with open(evidence / 'simulator-system.log', 'w') as handle:
        subprocess.run(['xcrun', 'simctl', 'spawn', udid, 'log', 'show', '--last', '20m', '--style', 'compact',
                        '--predicate', 'process == "Probe"'], stdout=handle, stderr=subprocess.STDOUT)
    subprocess.run(['xcrun', 'simctl', 'shutdown', udid], capture_output=True)
    return {'simulator': description, 'finished': finished, 'exitedEarly': exited and not finished,
            'seconds': round(time.time() - launched_at, 1)}


# --- evaluation ----------------------------------------------------------

def journal_order_problems(journal):
    lines = journal.splitlines()
    position = 0
    for step in TEARDOWN_ORDER:
        found = next((index for index in range(position, len(lines)) if step in lines[index]), None)
        if found is None:
            return f'journal lacks "{step}" after the previous teardown step'
        position = found + 1
    if not any(line == 'END closed' for line in lines[position:]):
        return 'journal lacks its END closed line'
    return None


def evaluate(report, scenarios):
    results = {result['name']: result for result in report.get('results', [])}
    problems = []
    for scenario in scenarios:
        name = scenario['name']
        result = results.get(name)
        if result is None:
            problems.append(f'{name}: no result (the process died or timed out before it; see probe-progress.log)')
            continue
        launch = result.get('launch', {})
        if result.get('timeout'):
            problems.append(f'{name}: the launch never answered')
            continue
        if scenario['expect'] == 'run':
            if not launch.get('success'):
                problems.append(f"{name}: launch failed {launch.get('code')}: {launch.get('message')}")
                continue
            if not result.get('stopped') or not result.get('ended'):
                problems.append(f'{name}: closing did not complete (stopped={result.get("stopped")}, '
                                f'ended={result.get("ended")})')
            if result.get('presentedAfterStop') or result.get('presentedAtEnd') or result.get('activeAfterStop'):
                problems.append(f'{name}: the game view or session outlived "Quit game"')
            problem = journal_order_problems(result.get('journal', ''))
            if problem:
                problems.append(f'{name}: {problem}')
            for line in scenario.get('requiredLog', []):
                if line not in result.get('journal', ''):
                    problems.append(f'{name}: the core log lacks "{line}"')
            resolution = scenario.get('resolution')
            if resolution:
                problems += resolution_problems(name, resolution, result, launch)
        elif scenario['expect'] == 'core-stopped':
            if launch.get('success') or launch.get('code') != 'LIBRETRO_CORE_STOPPED':
                problems.append(f"{name}: expected a LIBRETRO_CORE_STOPPED launch failure, got "
                                f"{launch.get('success')} {launch.get('code')}")
            elif scenario.get('stopMessage', 'neotest boot failed: simulated') not in launch.get('message', ''):
                problems.append(f"{name}: the failure does not quote the core's error: {launch.get('message')}")
            if result.get('presentedAtEnd') or result.get('activeAfterStop'):
                problems.append(f'{name}: the game view or session stayed after the failure')
            if 'END launch failed LIBRETRO_CORE_STOPPED' not in result.get('journal', ''):
                problems.append(f'{name}: the journal does not end with the launch failure')
    return problems


def stored_value(document, key, game=None):
    """The value a session saved: Config/<library>.json ({"values": ...}) or,
    with `game`, Config/Games/<library>.json ({"games": {game: ...}})."""
    if not isinstance(document, dict):
        return None
    values = document.get('values') if game is None else (document.get('games') or {}).get(game)
    return values.get(key) if isinstance(values, dict) else None


def resolution_problems(name, resolution, result, launch):
    """The in-game menu's internal resolution: frames before the choice,
    accepted or refused, frames once the game ran again (the core's real
    output), and what the session saved (its record of the core's option,
    the value for every game of the core, the value of this game)."""
    problems = []
    expected = resolution
    renderer = launch.get('hardwareRendering', '')
    if 'byRenderer' in resolution:
        expected = dict(resolution, **resolution['byRenderer'].get(renderer, {}))
        if renderer not in resolution['byRenderer']:
            return [f'{name}: renderer {renderer!r} has no expectation']
    journal = result.get('journal', '')
    for line in expected.get('requiredLog', []):
        if line not in journal:
            problems.append(f'{name}: the core log lacks "{line}"')
    before = result.get('resolutionBefore') or [0, 0]
    after = result.get('resolutionAfter') or [0, 0]
    if before[0] != expected['beforeWidth'] or before[1] <= 0:
        problems.append(f"{name}: frames {before} before the choice, expected {expected['beforeWidth']} wide")
    selected = bool(result.get('resolutionSelected'))
    if expected.get('refused'):
        if selected:
            problems.append(f"{name}: the session accepted {expected['select']} with the {renderer} renderer")
    elif not selected:
        problems.append(f"{name}: the session refused {expected['select']}")
    scaled = [round(side * expected['scale']) for side in before]
    if after != scaled:
        problems.append(f'{name}: frames {after} after the choice, expected {scaled} (x{expected["scale"]} of {before})')
    snapshot = result.get('resolutionSnapshot')
    if not isinstance(snapshot, dict) or snapshot.get('renderer') != renderer:
        problems.append(f'{name}: Config/Resolution record {snapshot!r} does not name the {renderer} renderer')
    else:
        internal = snapshot.get('internalResolution')
        if 'inapplicable' in expected:
            if internal is not None or snapshot.get('inapplicableKey') != expected['inapplicable']:
                problems.append(f'{name}: Config/Resolution record {snapshot!r} does not report '
                                f"{expected['inapplicable']} as not applicable")
        elif not isinstance(internal, dict) or internal.get('key') != expected.get('key') or \
                internal.get('apply') != expected.get('apply'):
            problems.append(f'{name}: Config/Resolution record {internal!r} does not describe '
                            f"{expected.get('key')} ({expected.get('apply')})")
    key = expected.get('key') or expected.get('inapplicable')
    if 'core' in expected and stored_value(result.get('resolutionCoreFile'), key) != expected['core']:
        problems.append(f"{name}: {key} saved for the core is "
                        f"{stored_value(result.get('resolutionCoreFile'), key)!r}, expected {expected['core']!r}")
    if 'game' in expected:
        game = stored_value(result.get('resolutionGameFile'), key, result.get('gameKey'))
        if game != expected['game']:
            problems.append(f"{name}: {key} saved for {result.get('gameKey')} is {game!r}, expected {expected['game']!r}")
    return problems


# VM_MEMORY_* user tags of <mach/vm_statistics.h> the crowd report names.
VM_TAGS = {0: 'untagged', 1: 'MALLOC', 2: 'MALLOC_SMALL', 3: 'MALLOC_LARGE', 4: 'MALLOC_HUGE', 7: 'MALLOC_TINY',
           8: 'MALLOC_LARGE_REUSABLE', 9: 'MALLOC_LARGE_REUSED', 11: 'MALLOC_NANO', 12: 'MALLOC_MEDIUM',
           30: 'STACK', 31: 'GUARD', 33: 'DYLIB', 51: 'LAYERKIT', 60: 'DYLD', 61: 'DYLD_MALLOC', 66: 'GLSL',
           73: 'OS_ALLOC_ONCE', 74: 'LIBDISPATCH', 88: 'IOSURFACE', 100: 'IOACCELERATOR'}
CROWD_BASES = range(0x100000000, 0x17FFF0000, 0x800000)


def crowd_evidence(result):
    """Evidence only (no verdict): the bases whose scratchpad slot another
    mapping held when the window was crowded, that mapping, and whether it
    was still there once the game had started."""
    after = result.get('regionsAfterCrowd') or []
    launched = {(region[0], region[1]) for region in result.get('regionsAtLaunch') or []}
    crowd = set(result.get('crowdSlots') or [])
    kept = 0
    lines = []
    for base in CROWD_BASES:
        slot = base + 0x10000
        if slot in crowd:
            continue
        holder = next((region for region in after if region[0] <= slot < region[0] + region[1]), None)
        if holder is None:
            lines.append(f'base 0x{base:x}: slot free after crowding')
            continue
        address, size, tag, protection = holder
        if (address, size) in launched:
            kept += 1
            continue
        lines.append(f'base 0x{base:x}: slot in 0x{address:x}+0x{size:x} {VM_TAGS.get(tag, tag)} '
                     f'prot {protection}, released before the launch ended')
    # A crowd slot is still the probe's at launch when that very 16 KiB
    # region, without access, is still mapped there.
    held = {(region[0], region[1], region[3]) for region in result.get('regionsAtLaunch') or []}
    gone = [slot for slot in sorted(crowd) if (slot, 0x4000, 0) not in held]
    if gone:
        occupants = []
        for slot in gone[:6]:
            occupant = next((region for region in result.get('regionsAtLaunch') or []
                             if region[0] <= slot < region[0] + region[1]), None)
            occupants.append(f'0x{slot:x}' + (f' (now 0x{occupant[0]:x}+0x{occupant[1]:x} '
                                                f'{VM_TAGS.get(occupant[2], occupant[2])} prot {occupant[3]})'
                                                if occupant else ' (now unmapped)'))
        lines.append(f'{len(gone)} crowd slots no longer held at launch: ' + ', '.join(occupants))
    bases = re.findall(r'PPSSPP memory base 0x([0-9a-f]+)', result.get('journal', ''))
    if bases:
        used = int(bases[-1], 16)
        slot = used + 0x10000
        state = ('a crowd slot' if slot in crowd else
                 'free after crowding' if not any(region[0] <= slot < region[0] + region[1] for region in after)
                 else 'held by another mapping after crowding')
        lines.append(f'base PPSSPP used 0x{used:x}: its scratchpad slot was {state}')
    return [f'crowd: {len(crowd)} scratchpad slots taken, {len(after)} regions mapped then; '
            f'{kept} other slots held by mappings still there at launch'] + lines


def summarise(report, scenarios):
    results = {result['name']: result for result in report.get('results', [])}
    for scenario in scenarios:
        result = results.get(scenario['name'])
        if result is None:
            print(f"  {scenario['name']:22} no result", flush=True)
            continue
        launch = result.get('launch', {})
        print(f"  {scenario['name']:22} launch={'ok' if launch.get('success') else launch.get('code')} "
              f"renderer={launch.get('hardwareRendering') or '-'} launch={result.get('launchSeconds', 0):.1f}s "
              f"stop={result.get('stopSeconds', 0):.1f}s stopped={result.get('stopped', False)} "
              f"ended={result.get('ended', False)}", flush=True)
        if not launch.get('success'):
            print(f"    message: {launch.get('message')}", flush=True)
        if 'resolutionBefore' in result or 'resolutionAfter' in result:
            print(f"    resolution: frames {result.get('resolutionBefore')} -> {result.get('resolutionAfter')}, "
                  f"choice accepted {result.get('resolutionSelected')}", flush=True)
        for line in result.get('journal', '').splitlines():
            if 'unavailable' in line or 'PPSSPP memory window' in line or 'PPSSPP window' in line or \
                    (scenario.get('resolution') and ('resolution' in line or 'run: frame' in line)):
                print(f'    {line.split(" ", 2)[-1]}', flush=True)
        if 'regionsAfterCrowd' in result:
            for line in crowd_evidence(result):
                print(f'    {line}', flush=True)


def crash_summary(evidence, limit=24):
    """The crashed thread of the newest Probe crash report copied to the
    evidence (.ips: a JSON header line, then the JSON report), printed in
    the job log next to the progress lines."""
    reports = sorted(evidence.glob('Probe*.ips'), key=lambda path: path.stat().st_mtime)
    if not reports:
        return ['no crash report of the probe was found']
    _, _, body = reports[-1].read_text(errors='replace').partition('\n')
    try:
        report = json.loads(body)
    except ValueError:
        return [f'{reports[-1].name}: unreadable']
    exception = report.get('exception') or {}
    lines = [f"{reports[-1].name}: {exception.get('type', '?')} {exception.get('signal', '')} "
             f"{exception.get('subtype', '')}".rstrip()]
    termination = report.get('termination') or {}
    if termination.get('indicator'):
        lines.append(f"termination: {termination['indicator']}")
    for owner, texts in (report.get('asi') or {}).items():
        for text in (texts if isinstance(texts, list) else [texts])[:3]:
            lines.append(f'{owner}: {text}')
    images = report.get('usedImages') or []
    for thread in report.get('threads') or []:
        if not thread.get('triggered'):
            continue
        lines.append(f"crashed thread: {thread.get('name') or thread.get('queue') or '-'}")
        for frame in (thread.get('frames') or [])[:limit]:
            index = frame.get('imageIndex')
            image = images[index].get('name', '?') if isinstance(index, int) and 0 <= index < len(images) else '?'
            symbol = frame.get('symbol')
            where = f"{symbol} + {frame.get('symbolLocation', 0)}" if symbol else f"+0x{frame.get('imageOffset', 0):x}"
            lines.append(f'  {image} {where}')
    return lines


def command_run(args):
    if sys.platform != 'darwin':
        raise SystemExit('The simulator probe runs on macOS.')
    evidence = Path(args.evidence)
    evidence.mkdir(parents=True, exist_ok=True)
    sources = Path(args.sources) if args.sources else BRIDGE
    with tempfile.TemporaryDirectory(prefix='libretro-probe-') as temporary:
        app, scenarios = assemble(args, sources, Path(temporary))
        outcome = run_in_simulator(app, evidence, args.timeout)
    report_path = evidence / ('probe.json' if (evidence / 'probe.json').is_file() else 'probe-partial.json')
    report = json.loads(report_path.read_text()) if report_path.is_file() else {'results': []}
    progress = (evidence / 'probe-progress.log').read_text() if (evidence / 'probe-progress.log').is_file() else ''
    outcome['label'] = args.label
    (evidence / 'outcome.json').write_text(json.dumps(outcome, indent=2) + '\n')
    print(f"\nProbe on {outcome['simulator']} ({args.label}): finished={outcome['finished']} "
          f"exitedEarly={outcome['exitedEarly']} in {outcome['seconds']} s", flush=True)
    if outcome['exitedEarly']:
        for line in crash_summary(evidence):
            print(f'  crash: {line}', flush=True)
    summarise(report, scenarios)
    if args.expect == 'unfixed':
        # Informational: does this tree's process die while closing a game,
        # does PPSSPP find no memory base in the crowded window?
        died_closing = [scenario['name'] for scenario in scenarios
                        if f"{scenario['name']}: stop requested" in progress
                        and f"{scenario['name']}: stopped" not in progress]
        results = {result['name']: result for result in report.get('results', [])}
        no_base = [scenario['name'] for scenario in scenarios if scenario.get('crowdWindow')
                   and not results.get(scenario['name'], {}).get('launch', {}).get('success', True)
                   and 'Failed finding a memory base' in results[scenario['name']].get('journal', '')]
        if died_closing and not outcome['finished']:
            print(f'REPRODUCED with {args.label}: the process died while closing {", ".join(died_closing)}')
        elif no_base:
            print(f'REPRODUCED with {args.label}: PPSSPP found no memory base in {", ".join(no_base)}')
        else:
            print(f'NOT REPRODUCED with {args.label} in the simulator (finished={outcome["finished"]})')
        return
    problems = evaluate(report, scenarios)
    if not outcome['finished']:
        problems.insert(0, 'the probe did not finish (process ended or timed out); last progress lines:\n'
                        + '\n'.join(progress.splitlines()[-8:]))
    if problems:
        print('\nSimulator probe problems:', flush=True)
        for problem in problems:
            print('  - ' + problem, flush=True)
        raise SystemExit(f'{len(problems)} simulator probe problem(s)')
    print(f'All {len(scenarios)} simulator scenarios behaved as expected')


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    commands = parser.add_subparsers(dest='command', required=True)
    fetch_parser = commands.add_parser('fetch')
    fetch_parser.add_argument('--into', required=True)
    run_parser = commands.add_parser('run')
    run_parser.add_argument('--cores', required=True, help='LibretroCores artifact (Frameworks/, LibretroSystem/)')
    run_parser.add_argument('--inputs', required=True, help='directory filled by `fetch`')
    run_parser.add_argument('--evidence', required=True)
    run_parser.add_argument('--sources', help='libretro bridge ios/ directory (default: this tree)')
    run_parser.add_argument('--label', default='this tree')
    run_parser.add_argument('--only', nargs='*', default=[])
    run_parser.add_argument('--expect', choices=('fixed', 'unfixed'), default='fixed')
    run_parser.add_argument('--timeout', type=int, default=900)
    args = parser.parse_args()
    if args.command == 'fetch':
        fetch(Path(args.into))
    else:
        command_run(args)


if __name__ == '__main__':
    main()
