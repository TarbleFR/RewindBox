#!/usr/bin/env python3
r"""Build pack/shaders/direct from one game's exported shaders and pso_user.tsv.

On a Mac with the iPhoneOS Metal toolchain, from the RewindBox checkout:

  python3 build-utils/s2arm/build_nvn2_shader_pack.py /export/shaders \
      --history /export/pso_user.tsv --title-id <16-hex> --build-id <main-NSO-id> \
      --engine-source /src/patched-s2arm --out /tmp/export

Use the same S2Arm tree as the target engine (pin in tools/s2arm_prototype/pin.json,
plus build-utils/s2arm/engine/patches applied in order). Install the generated
pack/shaders/direct in the game's prepared pack before launch. S2A_RB_CAPTURE_PACK=0
disables generated packs. Console keys and game executables are unnecessary.
Only stages present in the capture have offline AIR. The device builds PSOs for
its GPU from the retained recipes. This command writes to a fresh export directory.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import runpy
import shutil
import struct
import subprocess
import sys
import tempfile

STAGES = {'vs': 'vertex', 'ps': 'pixel', 'cs': 'compute', 'gs': 'geometry',
          'ts': 'task', 'ms': 'mesh', 'hs': 'hull', 'ds': 'domain'}
STAGE_FILE = re.compile(r'([0-9a-f]{16})_([a-zA-Z0-9_]+)$')
KINDS = {'b': (0, 1), 'bf': (2, None), 'bv': (3, None), 'bgv': (48, 49),
         'ft': (50, None), 'se': (51, None), 'bgc': (96, 97)}
for i in range(3):
    KINDS[f'b_t{i}'] = (4 + i, None)
for i in range(10):
    KINDS[f'bg{i}'] = (16 + i, 32 + i)
    KINDS[f'bgs{i}'] = (64 + i, 80 + i)


def write_container(directory, chain, entries, stamp, shard_size=64 << 20):
    """lib_pack.inc v1. Copy each sorted, aligned segment without accumulating shards in RAM."""
    sizes, records = [], bytearray()
    for (key, kind), (path, skip) in sorted(entries.items()):
        length = path.stat().st_size - skip
        if not 0 < length <= shard_size:
            raise ValueError(f'Invalid segment length {length}: {path.name}')
        offset = (sizes[-1] + 15) & ~15 if sizes else 0
        if not sizes or offset + length > shard_size:
            sizes.append(0)
            offset = 0
        shard = len(sizes) - 1
        if shard >= 256:
            raise ValueError('The direct library exceeds the 256-shard format limit')
        with (directory / f'lib.{shard:03d}.pak').open('ab') as out, path.open('rb') as stage:
            out.write(bytes(offset - sizes[shard]))
            stage.seek(skip)
            shutil.copyfileobj(stage, out)
            if out.tell() != offset + length:
                raise ValueError(f'Changed during pack generation: {path}')
        sizes[shard] = offset + length
        records.extend(struct.pack('<QBBHIQ', key, kind, shard, 0, length, offset))
    with (directory / 'lib.idx').open('wb') as idx:
        receipt = hashlib.sha256(stamp.encode('ascii')).digest()[:12]
        idx.write(struct.pack('<8sIII4s12s12s', b'S2ALIB\0\0', 1, len(entries),
                              len(sizes), b'RBC1', chain.encode(), receipt))
        for size in sizes:
            idx.write(struct.pack('<Q8x', size))
        idx.write(records)


def build(args, output, work):
    engine = args.engine_source
    host = engine / 'graphics/nvn/gfx/nvn'
    direct_tools = engine / 'graphics/tools/direct'
    chain = re.search(r'^#define DMSH_CHAIN "([a-z0-9]{1,12})"$',
                      (host / 'dmsh_chain.h').read_text(), re.M)
    if not chain:
        raise ValueError('Cannot read DMSH_CHAIN from the engine source')
    chain = chain[1]
    air_tool = runpy.run_path(str(direct_tools / 'prepare_stage_air.py'))
    root = output / ('b-' + chain)
    root.mkdir(parents=True)
    # Stage binaries for dynamic variants use the existing digest envelope.
    # Base stages enter lib.NNN.pak as native MTLB slices, without the envelope.
    air = root / air_tool['SUFFIX'] / 'iphoneos'
    air.mkdir(parents=True)
    all_files = sorted(args.shaders.iterdir())
    entries, stages, fingerprints = {}, {}, set()
    sources = {}
    for path in all_files:
        if path.suffix not in ('.metal', '.msl') or not STAGE_FILE.fullmatch(path.stem):
            continue
        if path.stem in sources:
            if sources[path.stem].read_bytes() != path.read_bytes():
                raise ValueError(f'Conflicting .metal and .msl sources for {path.stem}')
            continue
        sources[path.stem] = path
    for path in all_files:
        m = STAGE_FILE.fullmatch(path.stem)
        if path.suffix != '.json' or not m or m[2] not in KINDS or KINDS[m[2]][1] is None:
            continue
        meta = json.loads(path.read_bytes())
        if (meta.get('key') != path.stem or meta.get('chain') != chain or
                not re.fullmatch('[0-9a-f]{16}', str(meta.get('xfp', ''))) or meta.get('fn_lib')):
            raise ValueError(f'Stale or mismatched translated reflection: {path.name}')
        fingerprints.add(meta['xfp'])
        if m[2] == 'b':
            if meta['stage'] not in STAGES:
                raise ValueError(f'Unknown stage in {path.name}: {meta["stage"]}')
            stages[m[1]] = STAGES[meta['stage']]
        if path.stem not in sources and not meta.get('gs_slice'):
            raise ValueError(f'Missing source for {path.name}')
        entries[(int(m[1], 16), KINDS[m[2]][1])] = (path, 0)
    if not stages or len(fingerprints) != 1:
        raise ValueError('Expected translated stage pairs from exactly one translator fingerprint')
    if not sources:
        raise ValueError('No translated Metal stages in the shader directory')
    subprocess.run(['xcrun', '--sdk', 'macosx', 'clang', '-std=c11', '-D_DARWIN_C_SOURCE',
                    '-O2', str(direct_tools / 'rb_stage_base_instance.c'), '-o', str(work / 'rewrite')], check=True)
    # Keep base binaries outside the published digest directory, unless another
    # dynamic variant genuinely needs the same bytes in it.
    base = work / 'base'
    base.mkdir()
    for source in sources.values():
        key, suffix = STAGE_FILE.fullmatch(source.stem).groups()
        if key not in stages:
            raise ValueError(f'No base-stage reflection for {source.name}')
        raw = source.read_bytes()
        raw.decode('utf-8')
        kinds = KINDS.get(suffix)
        if kinds and kinds[1] is not None and (int(key, 16), kinds[1]) not in entries:
            raise ValueError(f'No reflection for {source.name}')
        destination = base if kinds else air
        air_tool['prepare'](raw, 'iphoneos', destination, work)
        if kinds:
            tag = hashlib.sha256(raw).hexdigest()[:40]
            path = destination / (tag + '.airlib')
            with path.open('rb') as f:
                f.seek(80)
                if f.read(4) != b'MTLB':
                    raise ValueError(f'Metal produced an invalid library for {source.name}')
            entries[(int(key, 16), kinds[0])] = (path, 80)
        # The runtime still consults MSL for reflection and generated variants.
        if kinds and kinds[1] is not None:
            (root / (source.stem + '.metal')).write_bytes(raw)
        if b'(*spvDescriptorSet0.vp_c0)._m0[100].y' in raw:
            rewritten = subprocess.run([str(work / 'rewrite')], input=raw, stdout=subprocess.PIPE, check=True).stdout
            if raw != rewritten:
                air_tool['prepare'](rewritten, 'iphoneos', air, work)
    # Some sampler, blend, and vertex-input variants are generated in memory.
    # Their exact successful compiler inputs have no original <stage>_b.metal.
    for source in air_tool['captured_sources'](args.shaders):
        name = hashlib.sha256(source).hexdigest()[:40] + '.airlib'
        if (base / name).is_file():
            shutil.copyfile(base / name, air / name)
        else:
            air_tool['prepare'](source, 'iphoneos', air, work)
    stamp = '\t'.join(('rb-capture-v1', args.title_id.upper(), args.build_id[:32].lower(), chain, fingerprints.pop()))
    write_container(root, chain, entries, stamp)
    (root / 'inputs.tsv').write_text(f'game\t{args.title_id.upper()}\ninputs\truntime-only-capture\n{stamp}\n')
    keys = output / 'keys.tsv'
    mapping = output / 'shader_map.tsv'
    keys.write_text(''.join(k + '\n' for k in sorted(stages)))
    mapping.write_text('# ' + stamp + '\n' + ''.join(f'capture\t0\t{stages[k]}\t{k}\n' for k in sorted(stages)))
    for table in ('shader_facts.tsv', 'shader_pairs.tsv'):
        origin = args.shaders / table
        if origin.is_file():
            shutil.copyfile(origin, output / table)
        else:
            (output / table).touch()
    size = json.loads((direct_tools / 'pso_layout.json').read_text())['skey_size']
    subprocess.run([sys.executable, str(direct_tools / 'pso_seed.py'), str(output / 'pso_manifest.tsv'),
                    str(keys), str(mapping), str(size), str(args.history)], check=True)
    return len(entries), len(stages)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('shaders', type=Path)
    parser.add_argument('--history', required=True, type=Path, help='pso_user.tsv from the same game and build')
    parser.add_argument('--title-id', required=True)
    parser.add_argument('--build-id', required=True, help='Game main NSO build ID from the same capture')
    parser.add_argument('--engine-source', required=True, type=Path)
    parser.add_argument('--out', required=True, type=Path)
    args = parser.parse_args()
    if not re.fullmatch('[0-9a-fA-F]{16}', args.title_id) or not re.fullmatch('(?:[0-9a-fA-F]{32}|[0-9a-fA-F]{64})', args.build_id):
        parser.error('Supply the 16-digit title ID and 32- or 64-digit main NSO build ID')
    if not args.history.is_file():
        parser.error('The PSO history does not exist')
    dest = args.out / 'pack/shaders/direct'
    if dest.exists():
        parser.error(f'Export already exists: {dest}')
    dest.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=dest.parent, prefix='.build-') as temp:
        work = Path(temp)
        entries, stages = build(args, work / 'direct', work)
        (work / 'direct').rename(dest)
    print(f'{stages} stages, {entries} native container records: {dest}')


if __name__ == '__main__':
    main()
