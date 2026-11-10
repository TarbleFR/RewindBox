#!/usr/bin/env python3
"""REWINDBOX_HOST_MEMORY_BEFORE_CORE_650: the RPCS3 bridge measures the process right before the Core loads.

IPA 650 device logs (4 November 2026, private): the Assassin's Creed process that lost its GPU
(VK_ERROR_DEVICE_LOST in poke_query) carried 2.5 GB of compressed pages at its first in-game memory
sample, after 6.5 minutes in the RewindBox UI; the process relaunched 15 s after its start had 0. No
host line measured the process before the Core loaded, so the pre-game memory could not be
attributed. The bridge now writes one milestone, host_memory_before_core_load, right before
core_load_begin: footprint, resident, compressed (TASK_VM_INFO), jetsam headroom
(os_proc_available_memory), thermal state, then malloc_zone_pressure_relief(NULL, 0) (free malloc
pages back to the kernel, nothing live) and the same measures after it. Source contract only: the
Objective-C++ compiles on the macOS delivery jobs, not here.
"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PLUGIN = ROOT / 'packages/rpcs3_internal_bridge/ios/Classes/Rpcs3InternalBridgePlugin.mm'
MARK = 'REWINDBOX_HOST_MEMORY_BEFORE_CORE_650'
MILESTONE = 'RPCS3Milestone(@"host_memory_before_core_load"'


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit('FAIL: ' + message)


def main() -> None:
    text = PLUGIN.read_text(encoding='utf-8')
    require(text.count(MARK) == 1 and text.count(MILESTONE) == 1, 'one marked milestone')
    require('#import <malloc/malloc.h>' in text and '#import <os/proc.h>' in text and '#import <mach/mach.h>' in text,
            'malloc, os/proc and mach headers imported')
    start = text.index(MARK)
    end = text.index('RPCS3Milestone(@"core_load_begin"', start)
    block = text[start:end]
    require(text.index('static BOOL RPCS3TaskVMInfo(task_vm_info_data_t* info)') < start, 'the TASK_VM_INFO helper precedes its use')
    require(MILESTONE in block, 'the milestone is written before core_load_begin')
    require(block.count('RPCS3TaskVMInfo(&before)') == 1 and block.count('RPCS3TaskVMInfo(&after)') == 1,
            'measured before and after the relief')
    require(block.count('malloc_zone_pressure_relief(NULL, 0)') == 1, 'the relief returns free malloc pages of every zone')
    require(block.index('RPCS3TaskVMInfo(&before)') < block.index('malloc_zone_pressure_relief(NULL, 0)') <
            block.index('RPCS3TaskVMInfo(&after)'), 'measure, relieve, measure')
    fields = ['valid', 'footprint', 'resident', 'compressed', 'available', 'thermal', 'malloc_relief', 'valid_after',
              'footprint_after', 'compressed_after', 'available_after', 'physical']
    literal = ''.join(re.findall(r'@"((?:[^"\\]|\\.)*)"', block[block.index(MILESTONE):]))
    for field in fields:
        require(field + '=%' in literal, 'field missing from the milestone: ' + field)
    for value in ('before.phys_footprint', 'before.resident_size', 'before.compressed', 'after.phys_footprint', 'after.compressed',
                  'NSProcessInfo.processInfo.thermalState', 'NSProcessInfo.processInfo.physicalMemory'):
        require(value in block, 'value not reported: ' + value)
    require(block.count('os_proc_available_memory()') == 2, 'the jetsam headroom is read before and after')
    # Nothing live is released: no cache clear, no Core call, no notification posted from this block.
    for forbidden in ('clear', 'Notification', '_api.', 'stop_emulation', 'dlopen'):
        require(forbidden not in block, 'the block only measures and relieves free malloc pages: ' + forbidden)
    print('PASS: the RPCS3 bridge measures footprint/resident/compressed/headroom/thermal before the Core loads, '
          'relieves free malloc pages and measures again (host_memory_before_core_load before core_load_begin)')


if __name__ == '__main__':
    main()
