#!/usr/bin/env python3
"""REWINDBOX_MOLTENVK_COMPILE_QOS_V1: give MoltenVK's Metal compiles the QoS of the thread that waits for them.

MoltenVK 1.4.2 (MVKMetalCompiler::compile, MVKSync.mm:451) builds every Metal
library and pipeline with
    dispatch_async(dispatch_get_global_queue(DISPATCH_QUEUE_PRIORITY_DEFAULT, 0), block)
and blocks the caller on a condition variable until the block finishes. GCD
propagates a user-interactive caller as user-initiated, and the condition
variable donates no priority: the RSX thread waits for a compile that runs
below the user-interactive SPU, PPU and RSX threads. Pipelines of God of War
III took 0.6-4 s each on the iPhone (build 547 logs).

The release archive is one prelinked object whose only relocation to
_dispatch_get_global_queue is that call. This tool renames the undefined
symbol, in place and with the same length, to _rbx_mvk_compile_qos_queue,
which the RPCS3 Core defines (rpcs3/ios/RPCS3IOSPlatform.mm). Nothing else in
the archive changes. Input and output digests are pinned.

Usage: patch_moltenvk_compile_qos.py <libMoltenVK.a> [--check]
"""
import hashlib, struct, sys
from pathlib import Path

ORIGINAL_SHA256 = '245e7e05926c55ae97ace1b1822190139d87bda5aaefbcfd2f5156e1287f448b'
PATCHED_SHA256 = 'b91a46f74456949aa2a6cb73de9696d0b5508efe3a7c30041e0ff07232fc9de4'
OLD = b'_dispatch_get_global_queue\0'
NEW = b'_rbx_mvk_compile_qos_queue\0'
assert len(OLD) == len(NEW)
MH_MAGIC_64, CPU_TYPE_ARM64, MH_OBJECT, LC_SYMTAB = 0xFEEDFACF, 0x0100000C, 1, 0x2
N_TYPE, N_EXT, N_UNDF = 0x0E, 0x01, 0x00


def members(data):
    """(name, payload offset, payload size) of each archive member."""
    assert data[:8] == b'!<arch>\n', 'not an ar archive'
    at = 8
    while at < len(data):
        header = data[at:at + 60]
        assert header[58:60] == b'`\n', 'bad archive member header'
        name, size = header[:16].decode().strip(), int(header[48:58].decode().strip())
        start = at + 60
        if name.startswith('#1/'):  # BSD long name stored before the payload
            length = int(name[3:])
            name = data[start:start + length].rstrip(b'\0').decode()
            start, size = start + length, size - length
        yield name, start, size
        at = start + size + ((start + size) & 1)


def symbol(data, old_name):
    """The single Mach-O nlist that names old_name, checked to be undefined and external."""
    objects = [(n, s, z) for n, s, z in members(data) if not n.startswith('__.SYMDEF')]
    assert len(objects) == 1, [n for n, _, _ in objects]
    name, base, size = objects[0]
    magic, cputype, _, filetype, ncmds = struct.unpack_from('<IiiII', data, base)
    assert (magic, cputype, filetype) == (MH_MAGIC_64, CPU_TYPE_ARM64, MH_OBJECT), (hex(magic), cputype, filetype)
    at = base + 32
    for _ in range(ncmds):
        cmd, cmdsize = struct.unpack_from('<II', data, at)
        if cmd == LC_SYMTAB:
            symoff, nsyms, stroff, strsize = struct.unpack_from('<IIII', data, at + 8)
            break
        at += cmdsize
    else:
        raise AssertionError('no LC_SYMTAB')
    strings = data[base + stroff:base + stroff + strsize]
    assert strings.count(old_name) == 1 and data.count(old_name) == 1, 'name must occur once, in the string table'
    offset = strings.index(old_name)
    hits = []
    for i in range(nsyms):
        n_strx, n_type, n_sect, n_desc, n_value = struct.unpack_from('<IBBhQ', data, base + symoff + 16 * i)
        if n_strx == offset:
            hits.append((n_type, n_sect, n_value))
    assert hits == [(N_UNDF | N_EXT, 0, 0)], hits
    return name, base + stroff + offset


def main():
    path = Path(sys.argv[1])
    check = '--check' in sys.argv[2:]
    data = path.read_bytes()
    digest = hashlib.sha256(data).hexdigest()
    if digest == PATCHED_SHA256:
        symbol(data, NEW)
        print(f'MoltenVK compile QoS: already patched ({digest})')
        return
    assert not check, f'{path} is not the patched archive ({digest})'
    assert digest == ORIGINAL_SHA256, f'unexpected MoltenVK archive {digest}'
    member, at = symbol(data, OLD)
    assert NEW not in data
    patched = data[:at] + NEW + data[at + len(NEW):]
    assert len(patched) == len(data) and sum(a != b for a, b in zip(data, patched)) <= len(NEW)
    symbol(patched, NEW)
    out = hashlib.sha256(patched).hexdigest()
    assert out == PATCHED_SHA256, out
    tmp = path.with_suffix('.qos-tmp')
    tmp.write_bytes(patched)
    tmp.replace(path)
    print(f'MoltenVK compile QoS: {member}: _dispatch_get_global_queue -> _rbx_mvk_compile_qos_queue ({digest} -> {out})')


if __name__ == '__main__':
    main()
