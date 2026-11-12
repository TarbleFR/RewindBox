#!/usr/bin/env python3
"""Patch 0012: a texture reports its sparse tile layout, and a 0-byte virtual pool mapping succeeds (plain python3).

Mario Kart World on IPA 732 (engine log, 12 Nov): the boot went through and the game ran nnMain, created the NVN2 device on
Metal 4, then asked nvnTextureGetSparseTileLayout. It got an empty layout from the engine's stub, sent 0-byte tile mappings
into its virtual pool, MapVirtual failed 9 times (vm_remap refuses a 0-byte range: 4), and the game crashed on a null pointer
(address 0x4) 30 s after nnMain. The builder query already answered with nvn_tex_sparse_layout, which also lays sparse
textures out (nvn_tex.c), so the texture query now gives the same answer for the description it was built from. A valid
0-byte request maps nothing and is accepted. The patch is compiled by s2arm-engine.yml.

    python3 -B test/s2arm_sparse_layout_test.py
"""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PATCHES = ROOT / 'build-utils/s2arm/engine/patches'
PATCH = PATCHES / '0012-guest-sparse-texture-layout-and-empty-mappings.patch'
failures, checks = [], 0


def check(condition, message):
    global checks
    checks += 1
    if not condition:
        failures.append(message)


def ordered(text, *parts):
    at = -1
    for part in parts:
        at = text.find(part, at + 1)
        if at < 0:
            return False
    return True


patch = PATCH.read_text(encoding='utf-8') if PATCH.is_file() else ''
check(bool(patch), 'patch 0012 exists')
check(re.findall(r'^diff --git a/(\S+) b/', patch, re.M) == ['graphics/nvn/gfx/nvn/hle_nvn.c'], 'patch 0012 touches hle_nvn.c only')
added = '\n'.join(line[1:] for line in patch.splitlines() if line.startswith('+') and not line.startswith('+++'))
removed = '\n'.join(line[1:] for line in patch.splitlines() if line.startswith('-') and not line.startswith('---'))

# The texture query: the builder's computation on the description the texture was initialized with.
check('nvnTextureGetSparseTileLayout: sparse tiled textures are not supported' in removed
      and '(void)t; if (layout) memset(layout, 0, sizeof *layout);' in removed,
      'the empty-layout stub of the texture query is what the patch replaces')
query = patch[patch.find(' NVN(nvnTextureGetSparseTileLayout,'):]
query = query[:query.find('\n }\n')]
check(ordered(query, 'uint32_t tile[4] = {0, 0, 0, 0};', 'if (t) nvn_tex_sparse_layout(&CTX(t)->d, tile);',
              'if (layout) memcpy(layout, tile, sizeof tile);'),
      'the texture query fills the layout from nvn_tex_sparse_layout on its own description, zeros otherwise')
check('static _Atomic int logged; if (tile[0] && !atomic_exchange(&logged, 1))' in query,
      'the first non-empty answer is logged once, for the next device log')
check(' NVN(nvnTextureBuilderGetSparseTileLayout, void, const NVNtextureBuilder *b, NVNtextureSparseTileLayout *layout) {' not in patch,
      'the builder query (the reference the texture now follows) is left as it is')

# The 0-byte request: accepted after the validity checks, before the page table and vm_remap.
mapping = patch[patch.find('static int vpool_map(struct vpool *v, const map_req *r)'):]
check(ordered(mapping, 'cannot supply %#llx+%#llx', 'if (!r->size) {', 'return 1;', 'vpt_set(v, (uint64_t)r->voff, r->size, ph ? ph->mem + r->poff : NULL);'),
      'a 0-byte request returns success after the bounds, alignment and physical-pool checks, before any mapping')
zero = mapping[mapping.find('if (!r->size) {'):mapping.find('vpt_set(')]
check('mmap(' not in zero and 'vm_remap(' not in zero and 'atomic_fetch_add(&zero, 1)' in zero,
      'the 0-byte case maps nothing and logs its first case only')
check(not re.search(r'^-.*(return 0;|LOG\("【红】 virtual pool)', patch, re.M), 'no existing failure of vpool_map is removed')

check(added.count('RewindBox (patch 0012)') == 2, 'both changes are marked RewindBox (patch 0012)')
series = sorted(p.name for p in PATCHES.glob('*.patch'))
check(series[-1] == PATCH.name and len(series) == 12, f'0012 is the last of 12 engine patches: {series[-2:]}')
notices = (ROOT / 'docs/s2arm-legal-notices.md').read_text(encoding='utf-8')
check(PATCH.name in notices and 'RewindBox patches 0001–0012' in notices, 'the legal notices list patch 0012 and the series 0001–0012')
bridge_yml = (ROOT / '.github/workflows/s2arm-bridge-ios.yml').read_text(encoding='utf-8')
check('python3 -B test/s2arm_sparse_layout_test.py' in bridge_yml and 'test/s2arm_sparse_layout_test.py' in bridge_yml.split('jobs:')[0],
      's2arm-bridge-ios.yml runs this test and is triggered by it')

for failure in failures:
    print('FAIL ' + failure)
print(json.dumps({'result': 'failed' if failures else 'passed', 'checks': checks}))
sys.exit(1 if failures else 0)
