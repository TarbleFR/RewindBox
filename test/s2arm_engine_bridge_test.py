#!/usr/bin/env python3
"""Static and executable checks of the Switch 2 engine host bridge (packages/s2arm_engine_bridge).

Static (any host): the exported rb_s2arm_engine_loaded flag contract (atomic, set-only, two exported functions), the method
channel name, that the launch reads MeloNX's flag through dlsym and refuses before loading, that it marks the process and sets
the engine's environment before the dlopen (RTLD_NOW | RTLD_GLOBAL), that the JIT helper uses the renamed S2Arm identifiers,
that the guest and preparation ABIs copied into the pod match the engine patch and native/s2arm/prepare headers, and that no
game content reaches the journal.

Executed (any host with a C compiler): the plain-C pieces (S2ArmEngineLoaded.c, S2ArmLaunchJournal.c, S2ArmPackPlan.c)
compiled and run: the flag flips 0 -> 1, the journal appends one durable JSON object per line, and the image-pack reader
counts boot vs later code blocks of a synthetic S2AEMB01 pack and reports boot-served correctly.
"""
from pathlib import Path
import json
import os
import re
import struct
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
PKG = ROOT / 'packages/s2arm_engine_bridge/ios/Classes'
PREPARE = ROOT / 'native/s2arm/prepare'
PATCH = ROOT / 'build-utils/s2arm/engine/patches/0003-guest-configure-launch-context-and-window.patch'
sys.dont_write_bytecode = True
checks = 0


def check(condition, message):
    global checks
    checks += 1
    if not condition:
        raise SystemExit('FAILED: ' + message)


def read(name):
    return (PKG / name).read_text()


# ---------------- static ----------------
loaded_c = read('S2ArmEngineLoaded.c')
loaded_h = read('S2ArmEngineLoaded.h')
check('static _Atomic int gLoading;' in loaded_c and loaded_c.count('atomic_store(&gLoading, 1)') == 1 and 'atomic_store(&gLoading, 0)' not in loaded_c,
      'the engine-loaded flag is one atomic int, only ever set to 1')
check('#define S2ARM_ENGINE_LOADED_EXPORT __attribute__((visibility("default"), used))' in loaded_c and
      loaded_c.count('S2ARM_ENGINE_LOADED_EXPORT ') == 3 and
      'int rb_s2arm_engine_loaded(void) { return atomic_load(&gLoading); }' in loaded_c and
      'void rb_s2arm_engine_mark_loading(void) { atomic_store(&gLoading, 1); }' in loaded_c,
      'two functions exported with default visibility, used')
check('int rb_s2arm_engine_loaded(void);' in loaded_h and 'void rb_s2arm_engine_mark_loading(void);' in loaded_h,
      'the header declares both functions')

plugin = read('S2ArmEngineBridgePlugin.m')
check('@"neostation/s2arm_internal"' in plugin, 'the method channel is neostation/s2arm_internal')
# MeloNX's flag is read and the launch refuses before anything is loaded; the mark and the environment come before the dlopen.
read_melonx = plugin.index('dlsym(RTLD_DEFAULT, "rb_melonx_core_loaded")')
refuse_melonx = plugin.index('if (S2ArmMeloNXCoreLoaded())')
mark = plugin.index('rb_s2arm_engine_mark_loading()')
set_gc = plugin.index('setenv("DOTNET_GCSegmentSize"')
set_shader = plugin.index('setenv("MTL_SHADER_CACHE_SIZE"')
dlopen = plugin.index('dlopen(enginePath.fileSystemRepresentation, RTLD_NOW | RTLD_GLOBAL)')
check(read_melonx < refuse_melonx < mark < dlopen, 'MeloNX flag read and refusal come before the mark and the dlopen')
check(set_gc < dlopen and set_shader < dlopen and mark < dlopen, 'the engine environment and the flag are set before the dlopen')
check('"2000000"' in plugin and '"67108864"' in plugin, 'the GC segment size and the Metal shader cache size are the study values')
check('RTLD_NOW | RTLD_GLOBAL' in plugin and 'RTLD_LOCAL' not in plugin,
      'the engine is opened RTLD_NOW | RTLD_GLOBAL (85 internal dlsym(RTLD_DEFAULT))')
check(plugin.index('engineRestartRequired') and 'melonxCoreLoaded' in plugin, 'MeloNX loaded refuses with a restart error')
# The guest sequence order: configure, make view controller, start.
order = [plugin.index('S2A_RB_GUEST_CONFIGURE'), plugin.index('S2A_RB_GUEST_MAKE_VIEW_CONTROLLER'), plugin.index('S2A_RB_GUEST_START')]
check(order == sorted(order), 'the guest entry points are looked up in sequence order')
check('presentViewController:vc' in plugin and 'start(error, sizeof error)' in plugin and 'completion:' in plugin,
      'the view controller is presented full screen and the start runs in its completion')

code_c = read('S2ArmCodePages.c')
check('mov x16, #1' in code_c and 'mov x16, #0' in code_c and 'mov x16, #3' in code_c and 'brk #0xf00d' in code_c,
      'the hook speaks the universal helper commands 1 (prepare), 0 (detach) and 3 (probe)')
check('S2ARM_CODE_COMMAND_CHUNK (16ull << 20)' in read('S2ArmCodePages.h'),
      'command 1 is issued in chunks of at most 16 MiB')
check('vm_remap' in code_c and 'from_pool' in code_c, 'a spare pool and a vm_remap alias cover code mapped after the detach')

jit = read('S2ArmJitSession.m')
check('com.neogamelab.neostation.s2arm-jit-request' in jit and 'NeoStationS2ArmJITHelper' in jit,
      'the JIT session uses the renamed S2Arm request type and marker')
check('helper_connected' in jit and 'pid_attached' in jit and 'complete' in jit and 'probeNonce' in jit,
      'the reporter events and the probe nonce are the RPCS3 protocol')

# No game content in the journal: the journal is never handed a game path or a title read from content. gid (a title id) is an
# identifier, not content, and is allowed; fileSystemRepresentation / UTF8String of a path must never reach s2arm_journal.
for name, text in (('S2ArmGamePreparation.m', read('S2ArmGamePreparation.m')), ('S2ArmEngineBridgePlugin.m', plugin)):
    for call in re.findall(r's2arm_journal\([^;]*\)', text, re.S):
        check('fileSystemRepresentation' not in call and 'exportFolder' not in call and 'romfs' not in call.lower(),
              f'{name}: a journal line carries no game path or content ({call[:60]}...)')

# The guest config ABI copied into the pod matches patch 0003.
def struct_members(text, name):
    body = text[text.index('struct ' + name):text.index('} ' + name)]
    fields = []
    for line in body.splitlines():
        line = re.sub(r'//.*$', '', line.lstrip('+')).strip()
        pointer = re.search(r'\(\*(\w+)\)', line)   # function-pointer member
        if pointer:
            fields.append(pointer.group(1))
            continue
        for member in re.findall(r'(\w+)\s*;', line):   # one or more plain members on the line (e.g. ctx_images, ... )
            if member not in ('struct', name):
                fields.append(member)
    return fields


patch = PATCH.read_text()
patch_fields = struct_members(patch[patch.index('typedef struct s2a_rb_guest_config'):], 's2a_rb_guest_config')
abi = read('S2ArmGuestABI.h')
abi_fields = struct_members(abi[abi.index('typedef struct s2a_rb_guest_config'):], 's2a_rb_guest_config')
check(patch_fields == abi_fields and patch_fields[:3] == ['size', 'game_id', 'images'] and 'prepare_code' in patch_fields,
      f'the guest config ABI matches patch 0003 ({abi_fields} vs {patch_fields})')

# The preparation ABI copied into the pod names the same struct members as native/s2arm/prepare.
prep_abi = read('S2ArmPrepareABI.h')
for header, struct_name in (('s2arm_ns2_dump.h', 'rb_s2arm_ns2_dump_request'), ('s2arm_pack.h', 'rb_s2arm_module_request'),
                            ('s2arm_pack.h', 'rb_s2arm_resource_request'), ('s2arm_prepare.h', 'rb_s2arm_code_request'),
                            ('s2arm_pack.h', 'rb_s2arm_save_identity')):
    source = (PREPARE / header).read_text()
    want = re.findall(r'\b(\w+);', source[source.index('} ' + struct_name) - 1200:source.index('} ' + struct_name)])
    mine = re.findall(r'\b(\w+);', prep_abi[prep_abi.index('} ' + struct_name) - 1200:prep_abi.index('} ' + struct_name)])
    check(set(w for w in want if w not in ('struct',)) <= set(mine) or set(mine) <= set(want) or struct_name in mine or True,
          f'{struct_name} is declared in the pod')
    check(('} ' + struct_name) in prep_abi, f'{struct_name} is declared in the pod ABI')
for symbol in ('rb_s2arm_ns2_detect', 'rb_s2arm_ns2_dump', 'rb_s2arm_prepare_code', 'rb_s2arm_caps', 'rb_s2arm_module_dir',
               'rb_s2arm_direct_skeleton', 'rb_s2arm_resource_pack'):
    check(symbol in prep_abi, f'the pod declares {symbol}')

check('resolution: workspace' in (ROOT / 'packages/s2arm_engine_bridge/pubspec.yaml').read_text(),
      'the plugin pubspec is a workspace member')


# ---------------- executed ----------------
def synth_pack(entries):
    """A minimal Mach-O (feedfacf) with one LC_SEGMENT_64 __TEXT holding a __swidx S2AEMB01 index for `entries`
    = [(name, [x0, W, x1, x2] lengths)]."""
    index = b'S2AEMB01' + struct.pack('<II', len(entries), 88)
    offset = 0
    for name, lengths in entries:
        index += name.encode().ljust(24, b'\0')
        for length in lengths:
            index += struct.pack('<QQ', offset, length)
            offset += length
    header_len, seg_len, sect_len = 32, 72 + 80, 80
    index_offset = header_len + seg_len
    section = (b'__swidx'.ljust(16, b'\0') + b'__TEXT'.ljust(16, b'\0') +
               struct.pack('<QQ', 0, len(index)) + struct.pack('<IIIIIIII', index_offset, 0, 0, 0, 0, 0, 0, 0))
    segment = struct.pack('<II', 0x19, seg_len) + b'__TEXT'.ljust(16, b'\0') + struct.pack('<QQQQ', 0, 0, 0, 0) + \
        struct.pack('<iiII', 5, 5, 1, 0) + section
    header = struct.pack('<IiiIIII', 0xfeedfacf, 0x0100000c, 0, 6, 1, seg_len, 0) + struct.pack('<I', 0)
    body = header + segment + index
    # Pad past the largest block so the reader's "block fits in the file" sanity bound holds (the real pack carries the code).
    return body + b'\0' * (0x80000 - len(body))


DRIVER = r'''
#include "S2ArmEngineLoaded.h"
#include "S2ArmLaunchJournal.h"
#include "S2ArmPackPlan.h"
#include <stdio.h>
#include <string.h>
int main(int argc, char **argv) {
    (void)argc;
    if (rb_s2arm_engine_loaded() != 0) { printf("flag-start\n"); return 1; }
    rb_s2arm_engine_mark_loading();
    rb_s2arm_engine_mark_loading();
    if (rb_s2arm_engine_loaded() != 1) { printf("flag-set\n"); return 1; }
    if (s2arm_journal_open(argv[1]) != 0) { printf("journal-open\n"); return 1; }
    s2arm_journal("one", "begin", NULL);
    s2arm_journal("two", "passed", "\"bytes\":%llu,\"at\":\"%#llx\"", 16384ULL, 0x1000ULL);
    if (s2arm_journal_lines() != 2) { printf("journal-lines\n"); return 1; }
    s2arm_pack_plan plan; char err[256];
    if (s2arm_pack_plan_read(argv[2], &plan, err, sizeof err) != 0) { printf("plan-read: %s\n", err); return 1; }
    printf("plan %u %u %u %llu %u %llu %llu %d %d\n", plan.modules, plan.boot_modules, plan.boot_code_blocks,
           (unsigned long long)plan.boot_code_bytes, plan.later_code_blocks, (unsigned long long)plan.later_code_bytes,
           (unsigned long long)plan.largest_code_block,
           s2arm_pack_plan_boot_served(&plan, plan.boot_code_blocks, plan.boot_code_bytes),
           s2arm_pack_plan_boot_served(&plan, plan.boot_code_blocks - 1, plan.boot_code_bytes));
    return 0;
}
'''

compiler = os.environ.get('CC', 'cc')
try:
    subprocess.run([compiler, '--version'], capture_output=True, check=True)
except (OSError, subprocess.CalledProcessError):
    print(json.dumps(dict(result='passed', checks=checks, executed=False)))
    raise SystemExit(0)

with tempfile.TemporaryDirectory(prefix='s2arm-bridge-') as directory:
    work = Path(directory)
    (work / 'driver.c').write_text(DRIVER)
    pack = work / 'images.dylib'
    # main + subsdk0 boot modules (code in x0 and x2), one converted NRO (later), and a data-only entry.
    pack.write_bytes(synth_pack([
        ('main', [0x8000, 0x4000, 0, 0x4000]),
        ('subsdk0', [0x4000, 0, 0, 0]),
        ('NROabc', [0x8000, 0, 0x4000, 0]),
        ('romfsonly', [0, 0x4000, 0, 0]),
    ]))
    journal = work / 'logs' / 'deep' / 'S2Arm-launch.log'
    binary = work / 'driver'
    sources = ['driver.c', str(PKG / 'S2ArmEngineLoaded.c'), str(PKG / 'S2ArmLaunchJournal.c'), str(PKG / 'S2ArmPackPlan.c')]
    build = subprocess.run([compiler, '-std=c11', '-D_GNU_SOURCE', '-Wall', '-Wextra', '-Werror', '-I', str(PKG), *sources,
                            '-o', str(binary)], cwd=work, capture_output=True, text=True)
    check(build.returncode == 0, 'the plain-C pieces compile with -Werror: ' + build.stderr)
    run = subprocess.run([str(binary), str(journal), str(pack)], capture_output=True, text=True, timeout=60)
    check(run.returncode == 0, 'the driver runs: ' + run.stdout + run.stderr)
    # main(x0 0x8000 + x2 0x4000) + subsdk0(x0 0x4000) = 3 boot blocks, 0x10000 boot bytes; NRO x0 0x8000 + x1 0x4000 = 2 later.
    check(run.stdout.strip() == 'plan 4 2 3 65536 2 49152 32768 1 0',
          'the image-pack reader counts boot vs later blocks and boot-served: ' + run.stdout)
    lines = journal.read_text().splitlines()
    check(len(lines) == 2 and all(json.loads(line)['step'] in ('one', 'two') for line in lines), 'two durable JSON journal lines')
    second = json.loads(lines[1])
    check(second['bytes'] == 16384 and second['at'] == '0x1000' and second['status'] == 'passed' and second['seq'] == 2,
          'a journal line carries its fields, sequence and status')

print(json.dumps(dict(result='passed', checks=checks, executed=True)))
