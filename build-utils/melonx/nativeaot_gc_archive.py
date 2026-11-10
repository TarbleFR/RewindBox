#!/usr/bin/env python3
"""Read Darwin static archives (BSD ar, as Xcode's libtool/ar and llvm-ar --format=darwin write them) and Mach-O objects.

Shared by build_nativeaot_gc_rebuild.py (macOS runner), fetch_nativeaot_gc.py and their tests (any host): no tool
needed to list members, read their bytes, map the archive symbol table (__.SYMDEF) to members, and read an
object's CPU type and LC_BUILD_VERSION platform.
"""
import hashlib
import struct

MAGIC = b'!<arch>\n'
PLATFORMS = {1: 'MACOS', 2: 'IOS', 3: 'TVOS', 4: 'WATCHOS', 6: 'MACCATALYST', 7: 'IOSSIMULATOR'}
CPU_ARM64 = 0x0100000C


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def members(data):
    """[(offset, name, bytes)] in archive order, the symbol table included."""
    assert data[:8] == MAGIC, 'not an ar archive'
    result, offset = [], 8
    while offset < len(data):
        header = data[offset:offset + 60]
        assert len(header) == 60 and header[58:60] == b'`\n', f'bad member header at {offset}'
        name = header[:16].decode('ascii').rstrip(' ')
        size = int(header[48:58].decode('ascii').strip())
        body = data[offset + 60:offset + 60 + size]
        if name.startswith('#1/'):
            length = int(name[3:])
            name, body = body[:length].rstrip(b'\0').decode('utf-8'), body[length:]
        elif name.endswith('/') and name not in ('/', '//'):
            name = name[:-1]
        result.append((offset, name, body))
        offset += 60 + size + (size & 1)
    return result


def objects(data):
    """{name: bytes} of the archive's object members (symbol table excluded); names must be unique."""
    found = [(name, body) for _, name, body in members(data) if not name.startswith('__.SYMDEF')]
    names = [name for name, _ in found]
    assert len(names) == len(set(names)), 'duplicate member names'
    return dict(found)


def symbol_table(data):
    """{symbol: member name} from the archive's __.SYMDEF (32- or 64-bit ranlib entries)."""
    listed = members(data)
    by_offset = {offset: name for offset, name, _ in listed}
    tables = [(name, body) for _, name, body in listed if name.startswith('__.SYMDEF')]
    assert len(tables) == 1, 'expected exactly one __.SYMDEF member'
    name, body = tables[0]
    wide = name.startswith('__.SYMDEF_64')
    word, fmt = (8, '<Q') if wide else (4, '<I')
    ranlib_bytes = struct.unpack_from(fmt, body, 0)[0]
    entries = body[word:word + ranlib_bytes]
    strings_at = word + ranlib_bytes
    string_bytes = struct.unpack_from(fmt, body, strings_at)[0]
    strings = body[strings_at + word:strings_at + word + string_bytes]
    table = {}
    for index in range(0, ranlib_bytes, 2 * word):
        strx, member_offset = struct.unpack_from('<QQ' if wide else '<II', entries, index)
        symbol = strings[strx:strings.index(b'\0', strx)].decode('utf-8')
        table[symbol] = by_offset[member_offset]
    return table


def macho(data):
    """CPU type and LC_BUILD_VERSION (platform, minos, sdk) of a 64-bit Mach-O object."""
    magic, cputype, _, filetype, ncmds, _, _, _ = struct.unpack_from('<IiiIIIII', data, 0)
    assert magic == 0xFEEDFACF, 'not a 64-bit little-endian Mach-O (an LLVM bitcode member would fail here)'
    offset, build = 32, None
    for _ in range(ncmds):
        cmd, size = struct.unpack_from('<II', data, offset)
        if cmd == 0x32:  # LC_BUILD_VERSION
            platform, minos, sdk = struct.unpack_from('<III', data, offset + 8)
            version = lambda v: f'{v >> 16}.{(v >> 8) & 0xFF}.{v & 0xFF}'
            build = {'platform': PLATFORMS.get(platform, str(platform)), 'minos': version(minos), 'sdk': version(sdk)}
        offset += size
    return {'cpu': 'arm64' if cputype == CPU_ARM64 else hex(cputype & 0xFFFFFFFF), 'filetype': filetype,
            'buildVersion': build}


def symbols(data):
    """The object's symbols from LC_SYMTAB: strong and weak external definitions, undefined externals, and the
    local symbols the linker must keep (N_NO_DEAD_STRIP)."""
    _, _, _, _, ncmds, _, _, _ = struct.unpack_from('<IiiIIIII', data, 0)
    offset = 32
    for _ in range(ncmds):
        cmd, size = struct.unpack_from('<II', data, offset)
        if cmd == 0x2:  # LC_SYMTAB
            symoff, nsyms, stroff, strsize = struct.unpack_from('<IIII', data, offset + 8)
            break
        offset += size
    else:
        raise AssertionError('no LC_SYMTAB')
    result = {'strong': set(), 'weak': set(), 'undefined': set(), 'noDeadStripLocal': set()}
    for index in range(nsyms):
        strx, ntype, _, desc, _ = struct.unpack_from('<IBBHQ', data, symoff + 16 * index)
        if ntype & 0xE0:  # debugging (stab) entries
            continue
        name = data[stroff + strx:data.index(b'\0', stroff + strx)].decode('utf-8', 'replace')
        external, kind = ntype & 0x01, ntype & 0x0E
        if kind == 0x0 and external:
            result['undefined'].add(name)
        elif kind == 0xE and external:
            result['weak' if desc & 0x0080 else 'strong'].add(name)
        elif kind == 0xE and desc & 0x0020:
            result['noDeadStripLocal'].add(name)
    return result


def compare(official, candidate, replaced):
    """Differences between two archives where only `replaced` may differ: [] when they agree.

    Same object names in the same order, every other object byte-identical, an archive symbol table that maps every
    symbol of the other members to the same member (its offsets necessarily differ), and a replaced member that
    defines the same strong external symbols, all listed in the symbol table. Weak definitions (inline functions a
    different compiler may or may not emit) and undefined references are reported by replaced_symbols() instead."""
    problems = []
    a, b = members(official), members(candidate)
    names_a = [name for _, name, _ in a if not name.startswith('__.SYMDEF')]
    names_b = [name for _, name, _ in b if not name.startswith('__.SYMDEF')]
    if names_a != names_b:
        problems.append('member names or order differ')
    objects_a, objects_b = objects(official), objects(candidate)
    for name in names_a:
        if name != replaced and objects_a.get(name) != objects_b.get(name):
            problems.append('member differs: ' + name)
    if replaced not in objects_b:
        return problems + ['replaced member missing: ' + replaced]
    table_a, table_b = symbol_table(official), symbol_table(candidate)
    others_a = {s: m for s, m in table_a.items() if m != replaced}
    others_b = {s: m for s, m in table_b.items() if m != replaced}
    if others_a != others_b:
        problems.append('archive symbol table differs for the unchanged members')
    strong_a, strong_b = symbols(objects_a[replaced])['strong'], symbols(objects_b[replaced])['strong']
    if strong_a != strong_b:
        problems.append(f'{replaced} strong definitions differ: {len(strong_a - strong_b)} missing, '
                        f'{len(strong_b - strong_a)} added')
    if not strong_b <= {s for s, m in table_b.items() if m == replaced}:
        problems.append('archive symbol table does not list every strong definition of ' + replaced)
    return problems


def replaced_symbols(official_object, candidate_object):
    """Informational differences of the replaced object (compiler-dependent weak definitions and references)."""
    a, b = symbols(official_object), symbols(candidate_object)
    return {key: {'missing': sorted(a[key] - b[key]), 'added': sorted(b[key] - a[key])}
            for key in ('weak', 'undefined')}
