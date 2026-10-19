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
from neo_shader_kit_test import slang, png  # noqa: E402
TARGET = 'arm64-apple-ios17.4-simulator'
BUNDLE_ID = 'com.neostation.libretro.probe'
DEFINES = ('GLES_SILENCE_DEPRECATION=1', 'COREVIDEO_SILENCE_GL_DEPRECATION=1', 'VK_USE_PLATFORM_METAL_EXT=1',
           'VK_NO_PROTOTYPES=1', 'RC_CLIENT_SUPPORTS_HASH=1')
# The bridge's frameworks, plus MetalKit for the external_display coordinator
# (its podspec's frameworks: it preserves an MTKView's drawable on the move).
FRAMEWORKS = ('UIKit', 'Foundation', 'Metal', 'MetalKit', 'QuartzCore', 'AVFoundation', 'GameController', 'OpenGLES',
              'CoreVideo', 'Security', 'ImageIO', 'CoreGraphics', 'UniformTypeIdentifiers')
# Lot 1 (docs/libretro-consoles-lot1.md): the cores added for the consoles
# of the Consoles tab that only the RetroArch app ran. Each runs a test
# program the probe writes itself (build_lot1_content: a few instructions
# that keep the console running, no third-party content).
LOT1_CORES = ('sameduck', 'potator', 'ardens', 'stella', 'prosystem', 'a5200', 'mednafen_pce_fast',
              'mednafen_ngp', 'mednafen_wswan', 'mednafen_vb', 'handy', 'pokemini', 'wasm4', 'gearcoleco',
              'uzem', 'gw')
# Lot 2 (docs/libretro-consoles-lot2.md): the same test for the four cores
# of lot 2 (build_lot2_content).
LOT2_CORES = ('freechaf', 'freeintv', 'o2em', 'mednafen_pcfx')
# Build 489: Beetle PSX HW in Vulkan, run only with --beetle (build_beetle_content).
BEETLE_CORE = 'mednafen_psx_hw'
REAL_CORES = ('ppsspp', 'azahar', 'desmume') + LOT1_CORES + LOT2_CORES + (BEETLE_CORE,)
# Built here from test/libretro_host for the simulator.
TEST_CORES = {'neotest': 'test_core.c', 'neovk': 'vulkan_test_core.c'}
# Shader fixtures exercise the actual session and presenter; network bytes
# are served from the app bundle through NeoShaderStorage's test seam.
# These are deliberately synthetic effects with known output colours, so a
# PNG from the real game's drawable establishes that a selection reached it.
SHADER_REVISION = '0123456789abcdef0123456789abcdef01234567'
SHADER_FIXTURES = {
    'simple.slang': slang('FragColor = vec4(0.90, 0.05, 0.05, 1.0);'),
    'simple.slangp': 'shaders = 1\nshader0 = simple.slang\nfilter_linear0 = false\n',
    'copy.slang': slang('FragColor = texture(Source, vTexCoord);'),
    'history.slang': slang('FragColor = mix(texture(Source, vTexCoord), '
                          'texture(OriginalHistory1, vTexCoord), 0.25);',
                          samplers=('Source', 'OriginalHistory1')),
    'complex.slang': slang('vec3 detail = texture(Source, vTexCoord).rgb * 0.01 + '
                          'texture(Palette, vec2(0.5)).rgb * 0.01;\n'
                          'FragColor = vec4(detail + vec3(0.05, 0.85 * global.STRENGTH + 0.03, 0.05), 1.0);',
                          ubo=('float STRENGTH',), samplers=('Source', 'Palette'),
                          pragmas=('#pragma parameter STRENGTH "Strength" 1.0 0.0 1.0 0.1',)),
    'complex.slangp': ('shaders = 3\nshader0 = copy.slang\nscale_type0 = source\nscale0 = 1.0\n'
                        'shader1 = history.slang\nscale_type1 = source\nscale1 = 1.0\n'
                        'shader2 = complex.slang\ntextures = Palette\nPalette = textures/palette.png\n'
                        'Palette_linear = false\n'),
    'textures/palette.png': png(1, 1, [[(255, 255, 255, 255)]]),
    'invalid.slangp': 'shaders = nope\nshader0 = copy.slang\n',
    'bad-compile.slang': slang('FragColor = THIS_DOES_NOT_COMPILE;'),
    'bad-compile.slangp': 'shaders = 1\nshader0 = bad-compile.slang\n',
    'incompatible.slang': slang('FragColor = texture(UnsupportedTexture, vTexCoord);',
                                samplers=('UnsupportedTexture',)),
    'incompatible.slangp': 'shaders = 1\nshader0 = incompatible.slang\n',
    'missing.slangp': 'shaders = 1\nshader0 = never-present.slang\n',
    'incomplete.slangp': 'shaders = 1\nshader0 = simple.slang\n',
}
SHADER_ENTRY_FILES = {
    'simple.slangp': ['simple.slangp', 'simple.slang'],
    'complex.slangp': ['complex.slangp', 'copy.slang', 'history.slang', 'complex.slang', 'textures/palette.png'],
    'invalid.slangp': ['invalid.slangp', 'copy.slang'],
    'bad-compile.slangp': ['bad-compile.slangp', 'bad-compile.slang'],
    'incompatible.slangp': ['incompatible.slangp', 'incompatible.slang'],
    'missing.slangp': ['missing.slangp'],
    'incomplete.slangp': ['incomplete.slangp', 'simple.slang'],
}
SHADER_ACTIONS = [
    # This first action invokes the existing entry/download/apply menu
    # handlers. Only those handlers write its saved selection. The later
    # stress/error actions exercise the underlying session/storage APIs.
    {'kind': 'menu-apply', 'preset': 'simple.slangp', 'success': True, 'colour': 'red', 'persist': True},
    {'kind': 'apply', 'preset': 'complex.slangp', 'success': True, 'colour': 'green', 'persist': True},
    {'kind': 'parameter', 'parameter': 'STRENGTH', 'value': 0.2, 'colour': 'dim-green'},
    {'kind': 'apply', 'preset': 'simple.slangp', 'success': True, 'colour': 'red'},
    {'kind': 'apply', 'preset': 'complex.slangp', 'success': True, 'colour': 'green'},
    {'kind': 'apply', 'preset': 'invalid.slangp', 'success': False, 'codePrefix': 'PRESET_', 'colour': 'green'},
    {'kind': 'apply', 'preset': 'bad-compile.slangp', 'success': False, 'code': 'GLSL_FRAGMENT_FAILED', 'colour': 'green'},
    {'kind': 'apply', 'preset': 'incompatible.slangp', 'success': False, 'code': 'REFLECT_TEXTURE_SEMANTIC', 'colour': 'green'},
    {'kind': 'apply', 'preset': 'missing.slangp', 'success': False, 'codePrefix': 'SOURCE_', 'colour': 'green'},
    {'kind': 'download-short', 'preset': 'incomplete.slangp', 'success': False, 'code': 'DOWNLOAD_SIZE',
     'colour': 'green'},
    {'kind': 'delete-dependency', 'preset': 'complex.slangp', 'path': 'textures/palette.png',
     'success': False, 'code': 'SHADER_NOT_INSTALLED', 'colour': 'green'},
    {'kind': 'repair', 'preset': 'complex.slangp', 'success': True, 'colour': 'green'},
    {'kind': 'disable', 'success': True},
    {'kind': 'supersede-builtin', 'preset': 'simple.slangp', 'success': True, 'colour': 'red', 'persist': True},
    # Persist an applied preset once again. The following session must load
    # it from the menu's frontend store and produce the same real pixels.
    {'kind': 'apply', 'preset': 'simple.slangp', 'success': True, 'colour': 'red', 'persist': True},
]
OFFICIAL_PSP = 'reshade/handheld-color-LUTs/PSP-2020.slangp'
OFFICIAL_CRT = 'crt/crt-geom-mini.slangp'
OFFICIAL_ACTIONS = [
    {'kind': 'menu-apply', 'preset': OFFICIAL_PSP, 'success': True, 'passes': 1, 'persist': True},
    {'kind': 'parameter', 'parameter': 'LUT_selector_param', 'value': 2.0},
    {'kind': 'menu-apply', 'preset': OFFICIAL_CRT, 'success': True, 'passes': 2, 'persist': True},
    {'kind': 'parameter', 'parameter': 'SAT', 'value': 0.0},
    {'kind': 'menu-apply', 'preset': OFFICIAL_PSP, 'success': True, 'passes': 1, 'persist': True},
    {'kind': 'disable', 'success': True},
    {'kind': 'menu-apply', 'preset': OFFICIAL_CRT, 'success': True, 'passes': 2, 'persist': True},
    {'kind': 'restore-console', 'preset': OFFICIAL_PSP, 'success': True, 'passes': 1},
    {'kind': 'menu-apply', 'preset': OFFICIAL_CRT, 'success': True, 'passes': 2, 'persist': True},
]
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
    # Separately run in the shaders CI job: it cannot be hidden behind the
    # independent ppsspp-crowded memory-address assertion of the main job.
    {'name': 'shader-software', 'core': 'neotest', 'content': 'content/Test Game.ntc', 'console': 'gb',
     'expect': 'run', 'default': False, 'shaders': {'menu': True, 'afterMenuColour': 'red', 'actions': SHADER_ACTIONS}},
    {'name': 'shader-software-relaunch', 'core': 'neotest', 'content': 'content/Test Game.ntc', 'console': 'gb',
     'expect': 'run', 'default': False, 'shaders': {'initial': 'slang:simple.slangp', 'colour': 'red',
                                                'actions': [{'kind': 'disable', 'success': True}]}},
    {'name': 'shader-vulkan', 'core': 'neovk', 'content': 'content/Test Game.ntc', 'console': 'gb',
     'expect': 'run', 'default': False, 'shaders': {'menu': True, 'afterMenuColour': 'red', 'actions': SHADER_ACTIONS},
     'requiredLog': ['neovk create_device: device created by the core',
                     "neovk unload_game: resources destroyed through the frontend's device"]},
    {'name': 'shader-vulkan-relaunch', 'core': 'neovk', 'content': 'content/Test Game.ntc', 'console': 'gb',
     'expect': 'run', 'default': False, 'shaders': {'initial': 'slang:simple.slangp', 'colour': 'red',
                                                'actions': [{'kind': 'disable', 'success': True}]}},
    {'name': 'shader-desmume', 'core': 'desmume', 'content': 'content/probe.nds', 'console': 'nds',
     'expect': 'run', 'default': False, 'shaders': {'menu': True, 'afterMenuColour': 'red', 'actions': SHADER_ACTIONS}},
    {'name': 'shader-desmume-relaunch', 'core': 'desmume', 'content': 'content/probe.nds', 'console': 'nds',
     'expect': 'run', 'default': False, 'shaders': {'initial': 'slang:simple.slangp', 'colour': 'red',
                                                'actions': [{'kind': 'disable', 'success': True}]}},
]

# Lot 1 (run by their own CI job with --only): every core launched, run
# for a few seconds, closed with "Quit game" and launched again on a test
# program written by build_lot1_content. The journal must show the content
# accepted, the startup confirmed after frames and, where the core's size
# is fixed, the size of the frames it drew. Gearcoleco without its BIOS,
# Uzem on an image without its UZEBOX header and GW on a package that is
# not one must refuse the content and leave nothing behind (GW last: the
# probe stops if a core takes the process down).
LOT1_RUNS = (
    ('sameduck', 'content/probe-duck.bin', 'duck', '160x144'),
    ('potator', 'content/probe-wsv.sv', 'wsv', '160x160'),
    ('ardens', 'content/probe-ard.hex', 'ard', '128x64'),
    ('stella', 'content/probe-2600.a26', '2600', None),
    ('prosystem', 'content/probe-7800.a78', '7800', None),
    ('a5200', 'content/probe-5200.a52', '5200', None),
    ('mednafen_pce_fast', 'content/probe-pce.pce', 'pce', None),
    ('mednafen_ngp', 'content/probe-ngp.ngc', 'ngpc', '160x152'),
    ('mednafen_wswan', 'content/probe-ws.ws', 'ws', '224x144'),
    ('mednafen_vb', 'content/probe-vb.vb', 'vb', '384x224'),
    ('handy', 'content/probe-lynx.o', 'lynx', '160x102'),
    ('pokemini', 'content/probe-mini.min', 'mini', '384x256'),
    ('wasm4', 'content/probe-wasm4.wasm', 'wasm4', '160x160'),
)
for core, content, console, size in LOT1_RUNS:
    for run_index in (1, 2):
        SCENARIOS.append({
            'name': f'lot1-{core}-{run_index}', 'core': core, 'content': content, 'console': console,
            'expect': 'run', 'runSeconds': 3.0, 'default': False, 'lot1': True,
            'requiredLog': ['load: content accepted', 'run: startup confirmed after',
                            f'run: frame {size}' if size else 'run: frame '],
        })
SCENARIOS += [
    {'name': 'lot1-gearcoleco-no-bios', 'core': 'gearcoleco', 'content': 'content/probe-cv.col', 'console': 'cv',
     'expect': 'rejected', 'default': False, 'lot1': True},
    {'name': 'lot1-uzem-not-uze', 'core': 'uzem', 'content': 'content/probe-not-uze.uze', 'console': 'uze',
     'expect': 'rejected', 'default': False, 'lot1': True},
    {'name': 'lot1-gw-not-mgw', 'core': 'gw', 'content': 'content/probe-not-mgw.mgw', 'console': 'gw',
     'expect': 'rejected', 'default': False, 'lot1': True},
]

# Lot 2 (run by their own CI job with --lot2), as lot 1. FreeChaF runs a
# cartridge with its own replacement BIOS (no Channel F BIOS in System);
# FreeIntv, without exec.bin and grom.bin, runs and draws its own "PUT
# GROM/EXEC IN SYSTEM DIRECTORY" screen (NeoStation refuses such a launch
# before the session; the run shows the core itself loads and draws); O2EM
# and Beetle PC-FX boot a BIOS the probe writes itself, a single jump to
# itself, never a console's BIOS.
LOT2_RUNS = (
    ('freechaf', 'content/probe-chf.chf', 'chf', '306x192'),
    ('freeintv', 'content/probe-intv.int', 'intv', '352x224'),
    ('o2em', 'content/probe-mo2.bin', 'mo2', None),
    ('mednafen_pcfx', 'content/probe-pcfx.cue', 'pcfx', None),
)
for core, content, console, size in LOT2_RUNS:
    for run_index in (1, 2):
        SCENARIOS.append({
            'name': f'lot2-{core}-{run_index}', 'core': core, 'content': content, 'console': console,
            'expect': 'run', 'runSeconds': 3.0, 'default': False, 'lot2': True,
            'requiredLog': ['load: content accepted', 'run: startup confirmed after',
                            f'run: frame {size}' if size else 'run: frame '],
        })

# Build 489 (run by their own CI job with --beetle): Beetle PSX HW with the
# options and the Vulkan context NeoStation gives it (libretro_core_catalog.dart),
# on a stand-in BIOS the probe writes (_mips_program: a 4-bit texture uploaded
# from the CPU and drawn as a quad). First run: the core dumps the texture it
# tracked (dumping is a probe-only override; NeoStation locks it off). Second
# run: those names, filled with green, are the game's replacement pack; the
# drawn quad must turn green, through the core's own replacement, in Vulkan.
# Third run: replacement off again, the original texture is back.
BEETLE_LOG = ['hd-textures: core=beetle renderer=vulkan']
SCENARIOS += [
    {'name': 'beetle-vulkan-dump', 'core': BEETLE_CORE, 'content': 'content/probe-psx.exe', 'console': 'psx',
     'expect': 'run', 'runSeconds': 6.0, 'default': False, 'beetle': True,
     'probeOptions': {'beetle_psx_hw_track_textures': 'enabled', 'beetle_psx_hw_dump_textures': 'enabled',
                      'beetle_psx_hw_replace_textures': 'disabled'},
     'beetleTextures': {'expectDump': True, 'colour': 'original'}, 'requiredLog': BEETLE_LOG},
    {'name': 'beetle-vulkan-replace', 'core': BEETLE_CORE, 'content': 'content/probe-psx.exe', 'console': 'psx',
     'expect': 'run', 'runSeconds': 8.0, 'default': False, 'beetle': True,
     'probeOptions': {'beetle_psx_hw_track_textures': 'enabled', 'beetle_psx_hw_replace_textures': 'enabled'},
     'beetleTextures': {'replaceFromDump': 'probe-psx', 'colour': 'green', 'recognized': True},
     'requiredLog': BEETLE_LOG},
    {'name': 'beetle-vulkan-off', 'core': BEETLE_CORE, 'content': 'content/probe-psx.exe', 'console': 'psx',
     'expect': 'run', 'runSeconds': 5.0, 'default': False, 'beetle': True,
     'probeOptions': {'beetle_psx_hw_track_textures': 'disabled', 'beetle_psx_hw_replace_textures': 'disabled'},
     'beetleTextures': {'colour': 'original'}, 'requiredLog': BEETLE_LOG},
]

# Real official catalog/downloads; the rendering is the actual embedded
# bridge, with a software test core, a Vulkan test core and real DeSmuME.
for suffix, core, content, console in (
        ('software', 'neotest', 'content/Shader Pattern.ntc', 'gb'),
        ('vulkan', 'neovk', 'content/Test Game.ntc', 'gb'),
        ('desmume', 'desmume', 'content/shader-pattern.nds', 'nds')):
    SCENARIOS += [
        {'name': 'official-' + suffix, 'core': core, 'content': content, 'console': console,
         'expect': 'run', 'default': False, 'shaders': {'official': True, 'menu': True,
                                                       'actions': OFFICIAL_ACTIONS}},
        {'name': 'official-' + suffix + '-relaunch', 'core': core, 'content': content, 'console': console,
         'expect': 'run', 'default': False, 'shaders': {'official': True, 'initial': 'slang:' + OFFICIAL_CRT,
                                                       'actions': [{'kind': 'disable', 'success': True}]}},
    ]
    if core == 'neovk':
        for scenario in SCENARIOS[-2:]:
            scenario['lockedOptions'] = {'neovk_shader_pattern': 'on'}
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


def build_nds(output_path, shader_pattern=False):
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
    if shader_pattern:
        # Original homebrew instructions executed by real DeSmuME: enable
        # both LCD engines and select their backdrop colours. The core
        # draws them normally; no image is injected into its video callback.
        writes = [(0x04000304, 0x8203, True), (0x04000000, 0x10000, False),
                  (0x04001000, 0x10000, False), (0x05000000, 0x5DC8, True),
                  (0x05000400, 0x211B, True)]
        instructions = []
        pool_offset = (len(writes) * 3 + 1) * 4
        for index, (address, value, half) in enumerate(writes):
            pc = len(instructions) * 4
            instructions += [0xE59F0000 | (pool_offset + index * 8 - pc - 8),
                             0xE59F1000 | (pool_offset + index * 8 + 4 - (pc + 4) - 8),
                             0xE1C010B0 if half else 0xE5801000]
        instructions += [0xEAFFFFFE]
        for address, value, half in writes:
            instructions += [address, value]
        struct.pack_into('<' + 'I' * len(instructions), rom, 0x200, *instructions)
        struct.pack_into('<IIII', rom, 0x020, 0x200, 0x02000000, 0x02000000, len(instructions) * 4)
        struct.pack_into('<IIII', rom, 0x030, 0x400, 0x02380000, 0x02380000, 4)
        struct.pack_into('<I', rom, 0x400, 0xEAFFFFFE)
    struct.pack_into('<H', rom, 0x15E, crc16(rom[:0x15E]))
    output_path.write_bytes(bytes(rom))


def _vectors_6502(rom, offset, address):
    """NMI, RESET and IRQ vectors of a 6502 ROM image, at [offset]."""
    struct.pack_into('<HHH', rom, offset, address, address, address)


def build_lot1_content(content):
    """Test programs for the lot 1 cores, written here (no third-party
    content). Each one keeps its console running without drawing anything
    in particular: the probe checks that the real core accepts it, runs
    frames and is closed and launched again cleanly."""
    # Mega Duck (SameDuck): execution starts at 0x0000; DI, JR -2.
    duck = bytearray(0x8000)
    duck[0:3] = bytes([0xF3, 0x18, 0xFE])
    (content / 'probe-duck.bin').write_bytes(bytes(duck))

    # Watara Supervision (Potator): the last 16 KiB are fixed at $C000;
    # SEI, CLD, LDX #$FF, TXS, JMP *.
    wsv = bytearray(0x8000)
    wsv[0x4000:0x4008] = bytes([0x78, 0xD8, 0xA2, 0xFF, 0x9A, 0x4C, 0x05, 0xC0])
    _vectors_6502(wsv, 0x7FFA, 0xC000)
    (content / 'probe-wsv.sv').write_bytes(bytes(wsv))

    # Arduboy (Ardens): Intel HEX, RJMP . at the reset vector.
    data = bytes([0xFF, 0xCF])
    record = bytes([len(data), 0x00, 0x00, 0x00]) + data
    checksum = (-sum(record)) & 0xFF
    (content / 'probe-ard.hex').write_text(':' + (record + bytes([checksum])).hex().upper() + '\n:00000001FF\n')

    # Atari 2600 (Stella): 4 KiB at $F000, a full frame kernel (VSYNC, 37
    # lines of VBLANK, 192 visible lines on a coloured background, 30 of
    # overscan).
    a26 = bytearray([0xEA]) * 0x1000
    kernel = [0x78, 0xD8, 0xA2, 0xFF, 0x9A,
              0xA9, 0x02, 0x85, 0x00, 0x85, 0x02, 0x85, 0x02, 0x85, 0x02, 0xA9, 0x00, 0x85, 0x00,
              0xA2, 0x25, 0x85, 0x02, 0xCA, 0xD0, 0xFB,
              0xA9, 0x00, 0x85, 0x01, 0xA9, 0x44, 0x85, 0x09,
              0xA2, 0xC0, 0x85, 0x02, 0xCA, 0xD0, 0xFB,
              0xA9, 0x02, 0x85, 0x01,
              0xA2, 0x1E, 0x85, 0x02, 0xCA, 0xD0, 0xFB,
              0x4C, 0x05, 0xF0]
    a26[0:len(kernel)] = bytes(kernel)
    _vectors_6502(a26, 0xFFA, 0xF000)
    (content / 'probe-2600.a26').write_bytes(bytes(a26))

    # Atari 7800 (ProSystem): a headerless 16 KiB cartridge at $C000.
    a78 = bytearray(0x4000)
    a78[0:8] = bytes([0x78, 0xD8, 0xA2, 0xFF, 0x9A, 0x4C, 0x05, 0xC0])
    _vectors_6502(a78, 0x3FFA, 0xC000)
    (content / 'probe-7800.a78').write_bytes(bytes(a78))

    # Atari 5200 (a5200, internal Altirra OS): 32 KiB at $4000-$BFFF; $BFFD
    # = $FF starts the cartridge at once from $BFFE.
    a52 = bytearray(0x8000)
    a52[0:8] = bytes([0x78, 0xD8, 0xA2, 0xFF, 0x9A, 0x4C, 0x05, 0x40])
    a52[0x7FE8:0x7FFC] = b'NEOSTATION PROBE    '
    a52[0x7FFD] = 0xFF
    struct.pack_into('<H', a52, 0x7FFE, 0x4000)
    (content / 'probe-5200.a52').write_bytes(bytes(a52))

    # PC Engine (Beetle PCE Fast): bank 0 is at $E000 at power-on; SEI, CSH,
    # LDX #$FF, TXS, BRA *.
    pce = bytearray(0x8000)
    pce[0:7] = bytes([0x78, 0xD4, 0xA2, 0xFF, 0x9A, 0x80, 0xFE])
    struct.pack_into('<HHHHH', pce, 0x1FF6, 0xE000, 0xE000, 0xE000, 0xE000, 0xE000)
    (content / 'probe-pce.pce').write_bytes(bytes(pce))

    # Neo Geo Pocket Color (Beetle NeoPop, its built-in BIOS): header with
    # the start address, then JR T,$ (TLCS-900H).
    ngp = bytearray(0x10000)
    ngp[0x00:0x1C] = b'COPYRIGHT BY SNK CORPORATION'
    struct.pack_into('<I', ngp, 0x1C, 0x200040)
    ngp[0x23] = 0x10
    ngp[0x24:0x30] = b'NEOSTATION  '
    ngp[0x40:0x42] = bytes([0x68, 0xFE])
    (content / 'probe-ngp.ngc').write_bytes(bytes(ngp))

    # WonderSwan (Beetle WonderSwan): 64 KiB; the V30 starts at FFFF:0000,
    # the footer's JMPF F000:0000 (ROM offset 0), where JMP $ loops. No
    # save memory, horizontal.
    ws = bytearray([0xFF]) * 0x10000
    ws[0:2] = bytes([0xEB, 0xFE])
    ws[-16:-11] = bytes([0xEA, 0x00, 0x00, 0x00, 0xF0])
    ws[-11:] = bytes([0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x04, 0x00, 0x00, 0x00])
    (content / 'probe-ws.ws').write_bytes(bytes(ws))

    # Virtual Boy (Beetle VB): 64 KiB (a power of two); the V810 starts at
    # 0xFFFFFFF0, the last 16 bytes: BR $.
    vb = bytearray(0x10000)
    vb[-16:-14] = bytes([0x00, 0x8A])
    (content / 'probe-vb.vb').write_bytes(bytes(vb))

    # Atari Lynx (Handy, without boot ROM): a BLL homebrew loaded at $0200.
    # Its header starts with BRA +8, executed first; then SEI, CLD, BRA *.
    code = bytes([0x78, 0xD8, 0x80, 0xFE])
    lynx = bytes([0x80, 0x08, 0x02, 0x00]) + struct.pack('>H', 10 + len(code)) + b'BS93' + code
    (content / 'probe-lynx.o').write_bytes(lynx)

    # Pokemon mini (PokeMini, built-in free BIOS): "MN" at $2100, then
    # JRS $ (S1C88).
    mini = bytearray(0x10000)
    mini[0x2100:0x2102] = b'MN'
    mini[0x2102:0x2104] = bytes([0xF1, 0xFE])
    (content / 'probe-mini.min').write_bytes(bytes(mini))

    # WASM-4: a module importing the 64 KiB env.memory and exporting an
    # empty update().
    wasm = (b'\0asm' + bytes([1, 0, 0, 0])
            + bytes([0x01, 0x04, 0x01, 0x60, 0x00, 0x00])
            + bytes([0x02, 0x10, 0x01, 0x03]) + b'env' + bytes([0x06]) + b'memory' + bytes([0x02, 0x01, 0x01, 0x01])
            + bytes([0x03, 0x02, 0x01, 0x00])
            + bytes([0x07, 0x0A, 0x01, 0x06]) + b'update' + bytes([0x00, 0x00])
            + bytes([0x0A, 0x04, 0x01, 0x02, 0x00, 0x0B]))
    (content / 'probe-wasm4.wasm').write_bytes(wasm)

    # ColecoVision (Gearcoleco): a cartridge header and a loop; refused
    # here because the probe has no BIOS (none is shipped).
    col = bytearray(0x2000)
    col[0:2] = bytes([0xAA, 0x55])
    struct.pack_into('<H', col, 0x0A, 0x8010)
    col[0x10:0x12] = bytes([0x18, 0xFE])
    (content / 'probe-cv.col').write_bytes(bytes(col))

    # Uzebox and Game & Watch: files that are not their formats.
    (content / 'probe-not-uze.uze').write_bytes(b'NOTUZE' + bytes(1024))
    (content / 'probe-not-mgw.mgw').write_bytes(b'not a game and watch package' + bytes(256))


def build_lot2_content(content, system):
    """Test programs for the lot 2 cores, and the two stand-in BIOS images
    O2EM and Beetle PC-FX need to start at all, written here: each image is
    a single jump to itself at the CPU's reset address, so nothing of a
    console's BIOS is used or shipped. `system` is the probe's bundled
    System folder (copied into Documents/Libretro/System at start)."""
    # Channel F (FreeChaF, replacement BIOS): the cartridge at $0800 starts
    # with $55, the BIOS then jumps to $0802: JMP $0802.
    chf = bytearray(0x800)
    chf[0:5] = bytes([0x55, 0x2B, 0x29, 0x08, 0x02])
    (content / 'probe-chf.chf').write_bytes(bytes(chf))

    # Intellivision (FreeIntv): any cartridge; without exec.bin and grom.bin
    # the core draws its own error screen.
    (content / 'probe-intv.int').write_bytes(bytes(0x2000))

    # Odyssey 2 (O2EM): a 1 KiB stand-in BIOS, JMP $000 at the 8048's reset
    # address; an O2EM cartridge is a multiple of 1 KiB.
    bios = bytearray(0x400)
    bios[0:2] = bytes([0x04, 0x00])
    (system / 'o2rom.bin').write_bytes(bytes(bios))
    (content / 'probe-mo2.bin').write_bytes(bytes(0x800))

    # PC-FX (Beetle PC-FX): a 1 MiB stand-in BIOS mapped at $FFF00000, BR to
    # itself (0x8A00) at the V810 reset address $FFFFFFF0, and a disc of 32
    # empty data sectors.
    pcfx = bytearray(0x100000)
    pcfx[0xFFFF0:0xFFFF2] = (0x8A00).to_bytes(2, 'little')
    (system / 'pcfx.rom').write_bytes(bytes(pcfx))
    (content / 'probe-pcfx.bin').write_bytes(bytes(2352 * 32))
    (content / 'probe-pcfx.cue').write_text(
        'FILE "probe-pcfx.bin" BINARY\n  TRACK 01 MODE1/2352\n    INDEX 01 00:00:00\n')


def _mips_program():
    """A stand-in PlayStation BIOS written here (never a console's BIOS): from
    the reset address it sets up the GPU, uploads a 16x16 4-bit texture and its
    palette from the CPU (what Beetle's texture tracker hashes) and draws it as
    a textured quad, again and again; every GP0 word waits for the FIFO."""
    T0, T1, T3, T4, T2 = 8, 9, 11, 12, 10
    words = []

    def emit(word):
        words.append(word & 0xFFFFFFFF)

    def lui(rt, imm):
        emit((0x0F << 26) | (rt << 16) | (imm & 0xFFFF))

    def ori(rt, rs, imm):
        emit((0x0D << 26) | (rs << 21) | (rt << 16) | (imm & 0xFFFF))

    def sw(rt, offset, base):
        emit((0x2B << 26) | (base << 21) | (rt << 16) | (offset & 0xFFFF))

    def lw(rt, offset, base):
        emit((0x23 << 26) | (base << 21) | (rt << 16) | (offset & 0xFFFF))

    def and_(rd, rs, rt):
        emit((rs << 21) | (rt << 16) | (rd << 11) | 0x24)

    def beq(rs, rt, offset):
        emit((0x04 << 26) | (rs << 21) | (rt << 16) | (offset & 0xFFFF))

    def bne(rs, rt, offset):
        emit((0x05 << 26) | (rs << 21) | (rt << 16) | (offset & 0xFFFF))

    def addiu(rt, rs, imm):
        emit((0x09 << 26) | (rs << 21) | (rt << 16) | (imm & 0xFFFF))

    def nop():
        emit(0)

    def load(value):
        lui(T1, value >> 16)
        if value & 0xFFFF:
            ori(T1, T1, value & 0xFFFF)

    def gp1(value):
        load(value)
        sw(T1, 0x1814, T0)

    def gp0(value):
        load(value)
        # Wait for GPUSTAT bit 28 (ready to receive a word): a full FIFO drops writes.
        lw(T3, 0x1814, T0)
        nop()
        and_(T3, T3, T4)
        beq(T3, 0, -4)
        nop()
        sw(T1, 0x1810, T0)

    lui(T0, 0x1F80)               # I/O base
    lui(T4, 0x1000)               # GPUSTAT bit 28
    gp1(0x00000000)               # reset
    gp1(0x08000000)               # 256x240, NTSC, 15-bit
    gp1(0x05000000)               # display start (0,0)
    gp1(0x06C60260)               # horizontal range
    gp1(0x07040010)               # vertical range
    gp1(0x03000000)               # display on
    loop = len(words)
    gp0(0xE1000408)               # texpage x=512, 4-bit, drawing to the displayed area
    gp0(0xE3000000)               # drawing area top-left
    gp0(0xE403BCFF)               # drawing area bottom-right (255, 239)
    gp0(0xE5000000)               # drawing offset
    for word in (0x02202020, 0x00000000, 0x00F00100):  # clear to dark grey
        gp0(word)
    # CLUT at (0, 480): index 0 red, index 1 blue, the rest red.
    for word in (0xA0000000, 0x01E00000, 0x00010010):
        gp0(word)
    for _ in range(8):
        gp0(0x7C00001F)
    # 16x16 4-bit texture at (512, 0): 4 halfwords per row, checkered red/blue.
    for word in (0xA0000000, 0x00000200, 0x00100004):
        gp0(word)
    for row in range(16):
        pattern = 0x10101010 if (row // 4) % 2 == 0 else 0x01010101
        gp0(pattern)
        gp0(pattern)
    # Raw textured quad (64,56)-(192,184), CLUT (0,480), texpage 8.
    for word in (0x2D808080, 0x00380040, 0x78000000, 0x003800C0, 0x0008000F,
                 0x00B80040, 0x00000F00, 0x00B800C0, 0x00000F0F):
        gp0(word)
    lui(T2, 0x0004)               # delay, then draw again
    delay = len(words)
    addiu(T2, T2, -1)
    bne(T2, 0, delay - (len(words) + 1))
    nop()
    # j loop (BIOS ROM, KSEG1 0xBFC00000)
    emit((0x02 << 26) | (((0xBFC00000 + loop * 4) >> 2) & 0x3FFFFFF))
    nop()
    return b''.join(word.to_bytes(4, 'little') for word in words)


def build_beetle_content(content, system):
    """Beetle PSX HW (Build 489): a PS-X EXE the core accepts as content (never
    run: the stand-in BIOS keeps the CPU) and the stand-in BIOS under the names
    Beetle looks for, written only into this probe's System folder."""
    exe = bytearray(0x1000)
    exe[0:8] = b'PS-X EXE'
    exe[0x10:0x14] = (0x80010000).to_bytes(4, 'little')   # PC
    exe[0x18:0x1C] = (0x80010000).to_bytes(4, 'little')   # text start
    exe[0x1C:0x20] = (0x800).to_bytes(4, 'little')        # text size
    exe[0x30:0x34] = (0x801FFF00).to_bytes(4, 'little')   # SP
    exe[0x800:0x804] = ((0x02 << 26) | ((0x80010000 >> 2) & 0x3FFFFFF)).to_bytes(4, 'little')  # j self
    (content / 'probe-psx.exe').write_bytes(bytes(exe))
    program = _mips_program()
    bios = bytearray(0x80000)
    bios[:len(program)] = program
    for name in ('scph5500.bin', 'scph5501.bin', 'scph5502.bin'):
        (system / name).write_bytes(bytes(bios))


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


def imports_cheat_catalog(sources):
    return any('<neo_cheat_catalog/' in path.read_text(encoding='utf-8', errors='replace')
               for path in (sources / 'Classes').glob('*.m'))


def cheat_catalog_units(sources):
    if not imports_cheat_catalog(sources):
        return []
    return sorted(path for path in (ROOT / 'packages/neo_cheat_catalog/ios/Classes').glob('*.m')
                  if path.name != 'NeoCheatCatalogPlugin.m')


def build_shader_fixtures(app, official=False):
    """Pinned fixture catalogue consumed by the real menu/storage/compiler.

    It uses the public catalogue-directory and data-loader test seams; no
    production catalogue is replaced or claimed as tested by these effects.
    """
    directory = app / 'ShaderFixtures'
    directory.mkdir()
    if official:
        shutil.copyfile(ROOT / 'packages/neo_shader_kit/ios/Resources/slang-catalog.json',
                        directory / 'slang-catalog.json')
        (directory / 'official').write_text('Real production network loader\n')
        return directory
    files = []
    indexes = {}
    for name, value in SHADER_FIXTURES.items():
        data = value.encode('utf-8') if isinstance(value, str) else value
        path = directory / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        indexes[name] = len(files)
        files.append([name, len(data), hashlib.sha256(data).hexdigest()])
    catalog = {
        'schema': 1, 'engine': 'libretro', 'format': 'slang',
        'source': {'name': 'NeoStation session test fixtures', 'repository': 'https://fixtures.invalid',
                   'commit': SHADER_REVISION, 'raw': 'https://fixtures.invalid/session/'},
        'compiler': 'test-only synthetic presets', 'categories': ['other'], 'files': files,
        'entries': [
            {'id': identifier, 'name': Path(identifier).stem, 'category': 'other', 'family': '.',
             'files': [indexes[name] for name in required], 'passes': 3 if identifier == 'complex.slangp' else 1,
             'luts': int(identifier == 'complex.slangp'), 'history': int(identifier == 'complex.slangp'),
             'parameters': int(identifier == 'complex.slangp'), 'preview': -1, 'validation': 'translated'}
            for identifier, required in SHADER_ENTRY_FILES.items()
        ],
    }
    (directory / 'slang-catalog.json').write_text(json.dumps(catalog, indent=2) + '\n')
    return directory


def compile_probe(sources, sdk, work, app):
    # <pod/Name.h> resolves as the bridge sees its pods: their public
    # headers and nothing else (test/libretro_ios_syntax_test.py).
    include = stage_dependency_headers(work)
    includes = [sources / 'Classes', sources / 'ThirdParty/include', sources / 'ThirdParty/include/libretro',
                sources / 'ThirdParty/rcheevos/include', sources / 'ThirdParty/rcheevos/src', include]
    base = ['xcrun', '--sdk', 'iphonesimulator', 'clang', '-target', TARGET, '-isysroot', sdk, '-O1',
            '-Wno-deprecated-declarations']
    sanitizer = os.environ.get('NEOSTATION_SIMULATOR_ASAN') == '1'
    if sanitizer:
        base += ['-fsanitize=address', '-fno-omit-frame-pointer', '-DNEOSTATION_ADDRESS_SANITIZER=1']
    for include in includes:
        base += ['-I', str(include)]
    for define in DEFINES:
        base += ['-D', define]
    if imports_shader_kit(sources):
        base += ['-DNEOSTATION_SHADER_SESSION_PROBE=1']
    units = [path for path in sorted((sources / 'Classes').glob('*.m')) if path.name != 'LibretroInternalBridgePlugin.m']
    units += cheat_catalog_units(sources)
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
    if sanitizer:
        link += ['-fsanitize=address']
    for framework in frameworks:
        link += ['-framework', framework]
    link += [*libraries, '-Wl,-rpath,@executable_path/Frameworks', '-o', str(app / 'Probe')]
    run(link)
    if sanitizer:
        resource = Path(output(['xcrun', '--sdk', 'iphonesimulator', 'clang', '-print-resource-dir']).strip())
        runtime = resource / 'lib/darwin/libclang_rt.asan_iossim_dynamic.dylib'
        shutil.copyfile(runtime, app / 'Frameworks' / runtime.name)


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
    cheat_data = sources / 'Resources/Cheats'
    if cheat_data.is_dir():
        bundle = app / 'NeoStationCheats.bundle'
        shutil.copytree(cheat_data, bundle)
        (bundle / 'Info.plist').write_bytes(plistlib.dumps({'CFBundleIdentifier':'ai.neostation.cheats','CFBundlePackageType':'BNDL'}))
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
    (content / 'Shader Pattern.ntc').write_bytes(b'SHADERPATTERN\0')
    shutil.copyfile(inputs / 'simple.prx', content / 'simple.prx')
    shutil.copyfile(inputs / 'ftpd.3dsx', content / 'ftpd.3dsx')
    build_iso(inputs / 'simple.prx', content / 'probe.iso', work)
    build_nds(content / 'probe.nds')
    build_nds(content / 'shader-pattern.nds', shader_pattern=True)
    build_lot1_content(content)
    if getattr(args, 'lot2', False):
        # Only the lot 2 run carries the stand-in BIOS images.
        build_lot2_content(content, app / 'LibretroSystem')
    if getattr(args, 'beetle', False):
        build_beetle_content(content, app / 'LibretroSystem')
    if imports_shader_kit(sources):
        build_shader_fixtures(app, args.official_shaders)
    if imports_cheat_catalog(sources):
        shutil.copytree(ROOT / 'packages/neo_cheat_catalog/ios/Resources', app / 'NeoCheatCatalog.bundle')
    catalog = CATALOG.read_text(encoding='utf-8')
    geometry = {}
    names = {}
    for console in sorted({'gb', 'psp', '3ds', 'nds'} | {scenario['console'] for scenario in SCENARIOS}):
        names[console], geometry[console] = console_geometry(catalog, console)
    scenarios = []
    for scenario in SCENARIOS:
        if getattr(args, 'lot1', False):
            if not scenario.get('lot1'):
                continue
        elif getattr(args, 'lot2', False):
            if not scenario.get('lot2'):
                continue
        elif getattr(args, 'beetle', False):
            if not scenario.get('beetle'):
                continue
        elif args.only and scenario['name'] not in args.only:
            continue
        elif not args.only and not scenario.get('default', True):
            continue
        if bool(scenario.get('shaders', {}).get('official')) != args.official_shaders:
            continue
        entry = dict(scenario)
        if scenario['core'] in REAL_CORES:
            entry.update(core_settings(catalog, scenario['core']))
            # The product's locked options, then the probe's own (Beetle's dumping run).
            entry['lockedOptions'] = {**entry.get('lockedOptions', {}), **scenario.get('probeOptions', {})}
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


def run_in_simulator(app, evidence, timeout, *, reset=True):
    udid, description = pick_device()
    # A fresh device for every run: nothing left by a previous probe.
    subprocess.run(['xcrun', 'simctl', 'shutdown', udid], capture_output=True)
    if reset:
        run(['xcrun', 'simctl', 'erase', udid])
    subprocess.run(['xcrun', 'simctl', 'boot', udid], capture_output=True)
    run(['xcrun', 'simctl', 'bootstatus', udid, '-b'], timeout=600)
    if reset:
        run(['xcrun', 'simctl', 'install', udid, app])
    data = Path(output(['xcrun', 'simctl', 'get_app_container', udid, BUNDLE_ID, 'data']).strip())
    documents = data / 'Documents'
    if not reset:
        for name in ('probe.json', 'probe-partial.json', 'probe-progress.log'):
            (documents / name).unlink(missing_ok=True)
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
    shader_frames = documents / 'ShaderFrames'
    if shader_frames.is_dir():
        shutil.copytree(shader_frames, evidence / 'ShaderFrames', dirs_exist_ok=True)
    skin_frames = documents / 'SkinFrames'
    if skin_frames.is_dir():
        shutil.copytree(skin_frames, evidence / 'SkinFrames', dirs_exist_ok=True)
    previews = documents / 'overlay-previews'
    if previews.is_dir():
        shutil.copytree(previews, evidence / 'OverlayPreviews', dirs_exist_ok=True)
    frontend = documents / 'Libretro/Config/Frontend'
    if frontend.is_dir():
        shutil.copytree(frontend, evidence / 'Frontend', dirs_exist_ok=True)
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
            if scenario.get('skinPress'):
                checks = result.get('skinChecks', [])
                if not checks:
                    problems.append(f'{name}: no skin press checks')
                problems += [f'{name}: {check["name"]}' for check in checks if not check.get('passed')]
            if scenario.get('skinLoading'):
                checks = result.get('skinLoadingChecks', [])
                if len(checks) < 7:
                    problems.append(f'{name}: missing installed-skin loading and persistence checks')
                problems += [f'{name}: {check["name"]}' for check in checks if not check.get('passed')]
            if scenario.get('previewProbe'):
                checks = result.get('previewChecks', [])
                if len(checks) != scenario.get('previewChecksExpected', 10): problems.append(f'{name}: missing native overlay compositions or texture budget checks')
                problems += [f'{name}: {check["name"]}' for check in checks if not check.get('passed')]
            if scenario.get('cheatProbe'):
                checks = result.get('cheatChecks', [])
                if len(checks) < 4: problems.append(f'{name}: missing real-core cheat checks')
                problems += [f'{name}: {check["name"]}' for check in checks if not check.get('passed')]
            if scenario.get('shaders'):
                problems += shader_problems(name, scenario['shaders'], result, launch)
            if scenario.get('beetleTextures'):
                problems += beetle_problems(name, scenario['beetleTextures'], result, launch)
        elif scenario['expect'] == 'rejected':
            # The core is loaded and initialised, refuses the content, and
            # the session tears down to nothing.
            if launch.get('success') or launch.get('code') != 'LIBRETRO_GAME_REJECTED':
                problems.append(f"{name}: expected a LIBRETRO_GAME_REJECTED launch failure, got "
                                f"{launch.get('success')} {launch.get('code')}: {launch.get('message')}")
            if result.get('presentedAtEnd') or result.get('activeAfterStop'):
                problems.append(f'{name}: the game view or session stayed after the refusal')
            if 'initialised' not in result.get('journal', ''):
                problems.append(f'{name}: the journal does not show the core initialised before the refusal')
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


def beetle_problems(name, expected, result, launch):
    """Beetle PSX HW in Vulkan: the renderer the core started, its dump, the
    replacement it reports, and the quad's pixels in the presented frame."""
    problems = []
    status = result.get('beetleStatus') or {}
    if launch.get('hardwareRendering') != 'vulkan' or status.get('renderer') != 'vulkan':
        problems.append(f"{name}: Beetle did not run in Vulkan (launch {launch.get('hardwareRendering')!r}, "
                        f"session {status.get('renderer')!r})")
    if expected.get('expectDump') and not result.get('beetleDumped'):
        problems.append(f'{name}: the core dumped no texture')
    if expected.get('replaceFromDump'):
        if not result.get('beetleReplacementsPrepared'):
            problems.append(f'{name}: no replacement could be written from the dump')
        if not status.get('replace') or int(status.get('recognized') or 0) <= 0:
            problems.append(f'{name}: the core reports no recognised replacement ({status})')
    grids = (result.get('frame') or {}).get('screenGridsRGB') or []
    if not grids:
        problems.append(f"{name}: no frame captured ({(result.get('frame') or {}).get('captureError')})")
        return problems
    # The quad covers (64,56)-(192,184) of 256x240: grid cells 5..10 x 5..10 are inside it.
    inside = [grids[0][gy * 16 + gx] for gy in range(5, 11) for gx in range(5, 11)]
    green = sum(1 for r, g, b in inside if g > 150 and r < 90 and b < 90)
    original = sum(1 for r, g, b in inside if (r > 150 and g < 90 and b < 90) or (b > 150 and r < 90 and g < 90))
    if expected.get('colour') == 'green' and green < len(inside) * 0.8:
        problems.append(f'{name}: the quad is not the green replacement ({green}/{len(inside)} green, '
                        f'{original} original cells)')
    if expected.get('colour') == 'original' and original < len(inside) * 0.8:
        problems.append(f'{name}: the quad is not the original red/blue texture ({original}/{len(inside)} cells, '
                        f'{green} green)')
    return problems


def shader_frame_problems(name, frame, colour=None):
    """Pixels from the same CAMetalDrawable buffer the real session presents.

    Both DS screens are checked independently. Colour tolerances cover
    quantisation and a possible sRGB drawable, while distinguishing red,
    green and a reduced strength without depending on a ROM's artwork.
    """
    problems = []
    if not isinstance(frame, dict) or frame.get('captureError'):
        return [f'{name}: no live game frame: {frame!r}']
    if frame.get('gpuCompleted') is not True or frame.get('gpuError'):
        problems.append(f'{name}: live game GPU buffer did not complete: {frame.get("gpuError", "")}')
    if frame.get('drawable') is not True:
        problems.append(f'{name}: pixels were not observed in the presented drawable path')
    if not frame.get('png'):
        problems.append(f'{name}: no PNG evidence from the presented drawable')
    centres = frame.get('screenCentresRGBA') or []
    if not centres:
        problems.append(f'{name}: no drawn game screen was observed')
    for index, pixel in enumerate(centres):
        if len(pixel) != 4:
            problems.append(f'{name}: screen {index} has invalid pixels {pixel!r}')
            continue
        red, green, blue, alpha = pixel
        valid = (colour is None or
                 (colour == 'red' and red >= 180 and green <= 90 and blue <= 90) or
                 (colour == 'green' and green >= 180 and red <= 90 and blue <= 90) or
                 (colour == 'dim-green' and 35 <= green <= 160 and red <= 90 and blue <= 90))
        if not valid or alpha < 240:
            problems.append(f'{name}: screen {index} pixels {pixel} do not show {colour or "an opaque game frame"}')
    return problems


def shader_problems(name, shaders, result, launch):
    problems = []
    if result.get('shaderProbeUnavailable'):
        return [f'{name}: shader session observation is unavailable in these bridge sources']
    initial = result.get('shaderInitial') or {}
    if shaders.get('official') and 'initial' not in shaders:
        if result.get('baselineDisableSuccess') is not True or initial.get('active') != '':
            problems.append(f'{name}: the visual baseline was not captured without a shader')
    problems += shader_frame_problems(name + ' initial', initial, shaders.get('colour'))
    if shaders.get('menu') and (result.get('shaderMenuOpened') is not True or result.get('shaderMenuPaused') is not True
                                or result.get('shaderCatalogOpened') is not True):
        problems.append(f'{name}: the existing in-game catalogue did not open and pause the real session')
    problems += shader_frame_problems(name + ' resumed', result.get('shaderAfterMenu'), shaders.get('afterMenuColour'))
    if 'initial' in shaders and initial.get('active') != shaders['initial']:
        problems.append(f'{name}: stored preset after relaunch is {initial.get("active")!r}, '
                        f'expected {shaders["initial"]!r}')
    if launch.get('hardwareRendering') == 'vulkan' and 'vulkan' not in name:
        problems.append(f'{name}: unexpected Vulkan renderer')
    if 'vulkan' in name and launch.get('hardwareRendering') != 'vulkan':
        problems.append(f'{name}: expected the true Vulkan renderer, got {launch.get("hardwareRendering")!r}')
    steps = result.get('shaderSteps') or []
    actions = shaders.get('actions') or []
    if len(steps) != len(actions):
        problems.append(f'{name}: {len(steps)} shader actions finished, expected {len(actions)}')
    active = initial.get('active', '')
    previous_frame = initial
    for index, (action, step) in enumerate(zip(actions, steps)):
        prefix = f'{name} step {index} {action["kind"]}'
        if step.get('observedSuccess') is not action.get('success', True):
            problems.append(f'{prefix}: success {step.get("observedSuccess")!r}, expected {action.get("success", True)}')
        code = step.get('observedCode', '')
        if 'code' in action and code != action['code']:
            problems.append(f'{prefix}: failure code {code!r}, expected {action["code"]!r}')
        if 'codePrefix' in action and not code.startswith(action['codePrefix']):
            problems.append(f'{prefix}: failure code {code!r}, expected prefix {action["codePrefix"]!r}')
        if action['kind'] in ('apply', 'menu-apply', 'supersede-builtin', 'restore-console') and action.get('success'):
            active = 'slang:' + action['preset']
            if action['kind'] != 'restore-console' and (step.get('installationSuccess') is not True or step.get('installationRegistered') is not True):
                problems.append(f'{prefix}: shader was not installed through the verified storage')
        elif action['kind'] == 'disable':
            active = ''
        frame = step.get('frame') or {}
        if frame.get('active') != active:
            problems.append(f'{prefix}: active shader {frame.get("active")!r}, expected {active!r}')
        if active and action.get('success') and action['kind'] in ('apply', 'menu-apply', 'supersede-builtin', 'restore-console'):
            if frame.get('textureBytes', 0) <= 0 or frame.get('passes') != action.get('passes', 3 if action['preset'] == 'complex.slangp' else 1):
                problems.append(f'{prefix}: completed shader has no expected active chains/passes: {frame!r}')
            if frame.get('failure'):
                problems.append(f'{prefix}: successful selection retains failure {frame["failure"]!r}')
        if action['kind'] == 'menu-apply':
            if any(step.get(field) is not True for field in
                   ('menuEntryHandler', 'menuDownloadHandler', 'menuApplyHandler', 'menuFreshInstallation')):
                problems.append(f'{prefix}: the real entry/download/apply handlers were not traversed: {step!r}')
            if step.get('manualPersistence') is not False or step.get('menuFlowTimeout'):
                problems.append(f'{prefix}: the menu selection was manually persisted or timed out')
            if shaders.get('official') and step.get('menuPresetCheckedBeforeApply') is not False:
                problems.append(f'{prefix}: the menu marked the unrendered stored selection as active')
            expected_files = SHADER_ENTRY_FILES.get(action['preset'])
            if shaders.get('official'):
                catalog = json.loads((ROOT / 'packages/neo_shader_kit/ios/Resources/slang-catalog.json').read_text())
                entry = next(e for e in catalog['entries'] if e['id'] == action['preset'])
                expected_files = [catalog['files'][i][0] for i in entry['files']]
            if set(step.get('menuDownloadedPaths') or []) != set(expected_files):
                problems.append(f'{prefix}: the menu did not download every expected fixture file')
            if step.get('menuStoredPreset') != active or step.get('menuStoredEnabled') is not True:
                problems.append(f'{prefix}: the menu completion did not persist the resolved active selection')
            if step.get('menuStoredScope') not in ('game', 'console'):
                problems.append(f'{prefix}: the real menu did not identify the saved scope')
        if action['kind'] == 'supersede-builtin':
            if step.get('supersededCallbackCount') != 1 or step.get('supersededSuccess') is not False or \
                    step.get('supersededCode') != 'SHADER_SUPERSEDED':
                problems.append(f'{prefix}: the superseded built-in choice was not completed once with its refusal: {step!r}')
            if step.get('newestCallbackCount') != 1:
                problems.append(f'{prefix}: the newest shader was completed {step.get("newestCallbackCount")} times')
        if action['kind'] == 'download-short':
            if step.get('installationRegistered') is not False or step.get('applyAfterFailedDownload') is not False or \
                    step.get('applyAfterFailedDownloadCode') != 'SHADER_NOT_INSTALLED':
                problems.append(f'{prefix}: interrupted download was registered/applied: {step!r}')
        if action['kind'] == 'delete-dependency' and step.get('dependencyRemoved') is not True:
            problems.append(f'{prefix}: the missing-dependency case never removed the file')
        problems += shader_frame_problems(prefix, frame, action.get('colour'))
        if shaders.get('official'):
            before = previous_frame.get('screenGridsRGB') or []
            after = frame.get('screenGridsRGB') or []
            differences = [sum(abs(a - b) for old, new in zip(left, right) for a, b in zip(old, new)) / (len(left) * 3)
                           for left, right in zip(before, after) if left and len(left) == len(right)]
            step['screenMeanAbsoluteDifferences'] = differences
            if len(differences) != len(after) or not differences or any(d < 0.25 for d in differences):
                problems.append(f'{prefix}: no demonstrated visual effect/parameter change on every screen: {differences}')
            if action['kind'] == 'disable' and 'initial' not in shaders:
                baseline = initial.get('screenGridsRGB') or []
                restored = [sum(abs(a - b) for old, new in zip(left, right) for a, b in zip(old, new)) / (len(left) * 3)
                            for left, right in zip(baseline, after) if left and len(left) == len(right)]
                if len(restored) != len(after) or any(d > 1.0 for d in restored):
                    problems.append(f'{prefix}: disabling did not restore the original game image: {restored}')
        centres = frame.get('screenCentresRGBA') or []
        if 'desmume' in name and len(centres) != 2:
            problems.append(f'{prefix}: expected both DeSmuME screens, got {len(centres)}')
        if action['kind'] == 'disable' and not shaders.get('official'):
            previous_centres = previous_frame.get('screenCentresRGBA') or []
            if len(centres) != len(previous_centres) or any(
                    max(abs(value - previous) for value, previous in zip(pixel[:3], old[:3])) <= 20
                    for pixel, old in zip(centres, previous_centres)):
                problems.append(f'{prefix}: disabling did not visibly remove the previous effect on every screen')
        if action.get('persist') or action['kind'] == 'disable':
            # The probe stores its real session game key in every frame.
            game = frame.get('gameKey')
            document = frame.get('frontend') or {}
            values = (document.get('console') or {}) if action['kind'] == 'menu-apply' and step.get('menuStoredScope') == 'console' \
                else (document.get('games') or {}).get(game, {})
            expected_enabled = action['kind'] != 'disable'
            if values.get('shader.enabled') is not expected_enabled:
                problems.append(f'{prefix}: frontend did not persist shader.enabled={expected_enabled}')
            if expected_enabled and values.get('shader.preset') != active:
                problems.append(f'{prefix}: frontend saved {values.get("shader.preset")!r}, expected {active!r}')
        previous_frame = frame
    after_stop = result.get('shaderAfterStop') or {}
    for kind in ('builtin', 'slang'):
        response = after_stop.get(kind) or {}
        if response.get('callbackCount') != 1 or response.get('success') is not False or \
                response.get('code') != 'SHADER_SUPERSEDED':
            problems.append(f'{name}: {kind} shader request after teardown did not complete once with a refusal: {response!r}')
    if after_stop.get('recoveryBefore') != after_stop.get('recoveryAfter'):
        problems.append(f'{name}: a shader request after teardown changed its recovery marker')
    recovery = after_stop.get('recoveryAfter') or {}
    if not isinstance(recovery, dict) or 'pending' in recovery or 'active' in recovery:
        problems.append(f'{name}: shader request after teardown left an activation marker: {recovery!r}')
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
        for index, step in enumerate(result.get('shaderSteps') or []):
            frame = step.get('frame') or {}
            print(f'    shader {index}: {step.get("kind")} {step.get("preset", "-")} '
                  f'success={step.get("observedSuccess")} code={step.get("observedCode", "")} '
                  f'active={frame.get("active", "")} pixels={frame.get("screenCentresRGBA")} '
                  f'PNG={frame.get("png", "-")}', flush=True)
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
    visual = [{'scenario': result['name'], 'initial': (result.get('shaderInitial') or {}).get('active'),
               'steps': [{'kind': step['kind'], 'preset': step.get('preset'),
                          'success': step.get('observedSuccess'), 'code': step.get('observedCode'),
                          'passes': (step.get('frame') or {}).get('passes'),
                          'screenMeanAbsoluteDifferences': step.get('screenMeanAbsoluteDifferences'),
                          'png': (step.get('frame') or {}).get('png')}
                         for step in result.get('shaderSteps') or []]}
              for result in report.get('results', []) if result.get('shaderInitial')]
    if visual:
        (evidence / 'visual-verdicts.json').write_text(json.dumps({'source': args.label, 'problems': problems,
                                                               'scenarios': visual}, indent=2) + '\n')
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
    run_parser.add_argument('--lot1', action='store_true',
                            help='Run only the lot 1 cores (docs/libretro-consoles-lot1.md)')
    run_parser.add_argument('--lot2', action='store_true',
                            help='Run only the lot 2 cores (docs/libretro-consoles-lot2.md)')
    run_parser.add_argument('--beetle', action='store_true',
                            help='Run only the Beetle PSX HW Vulkan texture replacement scenarios (Build 489)')
    run_parser.add_argument('--expect', choices=('fixed', 'unfixed'), default='fixed')
    run_parser.add_argument('--timeout', type=int, default=900)
    run_parser.add_argument('--official-shaders', action='store_true',
                            help='Use the shipped catalog and production HTTPS downloads, not synthetic fixtures')
    args = parser.parse_args()
    if args.command == 'fetch':
        fetch(Path(args.into))
    else:
        command_run(args)


if __name__ == '__main__':
    main()
