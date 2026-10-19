"""Small read-only Mach-O helpers for the KartPad runtime checks (thin arm64)."""
from __future__ import annotations

import struct

MH_MAGIC_64 = 0xFEEDFACF
LC_SEGMENT_64 = 0x19
LC_SYMTAB = 0x2
LC_LOAD_DYLIB = 0xC
LC_LOAD_WEAK_DYLIB = 0x80000018
LC_ID_DYLIB = 0xD
LC_DYLD_INFO_ONLY = 0x80000022
LC_DYLD_EXPORTS_TRIE = 0x80000033
LC_BUILD_VERSION = 0x32
LC_MAIN = 0x80000028


def _uleb(data: bytes, offset: int) -> tuple[int, int]:
    result = shift = 0
    while True:
        byte = data[offset]
        offset += 1
        result |= (byte & 0x7F) << shift
        if byte < 0x80:
            return result, offset
        shift += 7


def parse(data: bytes) -> dict:
    magic, cpu, _, filetype, ncmds, sizeofcmds, flags, _ = struct.unpack_from("<8I", data)
    if magic != MH_MAGIC_64 or cpu != 0x0100000C:
        raise ValueError("expected a thin arm64 Mach-O")
    info = {"filetype": filetype, "flags": flags, "segments": [], "dylibs": [], "platform": None,
            "minos": None, "install_name": None, "exports_trie": None, "symtab": None, "has_main": False}
    offset = 32
    for _ in range(ncmds):
        cmd, size = struct.unpack_from("<2I", data, offset)
        if cmd == LC_SEGMENT_64:
            name = data[offset + 8:offset + 24].rstrip(b"\0").decode()
            vmaddr, vmsize, fileoff, filesize = struct.unpack_from("<4Q", data, offset + 24)
            nsects = struct.unpack_from("<I", data, offset + 64)[0]
            sections = []
            for index in range(nsects):
                base = offset + 72 + 80 * index
                sections.append((data[base:base + 16].rstrip(b"\0").decode("latin-1"),
                                 struct.unpack_from("<Q", data, base + 40)[0]))
            info["segments"].append({"name": name, "vmsize": vmsize, "filesize": filesize,
                                     "sections": sections})
        elif cmd in (LC_LOAD_DYLIB, LC_LOAD_WEAK_DYLIB, LC_ID_DYLIB):
            name_offset = struct.unpack_from("<I", data, offset + 8)[0]
            name = data[offset + name_offset:offset + size].split(b"\0", 1)[0].decode()
            if cmd == LC_ID_DYLIB:
                info["install_name"] = name
            else:
                info["dylibs"].append(name)
        elif cmd == LC_DYLD_INFO_ONLY:
            export_off, export_size = struct.unpack_from("<2I", data, offset + 40)
            info["exports_trie"] = (export_off, export_size)
        elif cmd == LC_DYLD_EXPORTS_TRIE:
            info["exports_trie"] = struct.unpack_from("<2I", data, offset + 8)
        elif cmd == LC_BUILD_VERSION:
            platform, minos = struct.unpack_from("<2I", data, offset + 8)
            info["platform"] = platform
            info["minos"] = f"{minos >> 16}.{(minos >> 8) & 0xFF}"
        elif cmd == LC_SYMTAB:
            info["symtab"] = struct.unpack_from("<4I", data, offset + 8)
        elif cmd == LC_MAIN:
            info["has_main"] = True
        offset += size
    return info


def exported_names(data: bytes, info: dict | None = None) -> list[str]:
    info = info or parse(data)
    if not info["exports_trie"] or not info["exports_trie"][1]:
        return []
    start, size = info["exports_trie"]
    trie = data[start:start + size]
    names: list[str] = []
    stack = [(0, b"")]
    seen = set()
    while stack:
        node, prefix = stack.pop()
        if node in seen:
            raise ValueError("cyclic export trie")
        seen.add(node)
        terminal, cursor = _uleb(trie, node)
        if terminal:
            names.append(prefix.decode("utf-8", "replace"))
        cursor += terminal
        children = trie[cursor]
        cursor += 1
        for _ in range(children):
            end = trie.index(b"\0", cursor)
            edge = trie[cursor:end]
            child, cursor = _uleb(trie, end + 1)
            stack.append((child, prefix + edge))
    return sorted(names)


def symbol_names(data: bytes, info: dict | None = None) -> list[str]:
    info = info or parse(data)
    if not info["symtab"]:
        return []
    symoff, nsyms, stroff, strsize = info["symtab"]
    strings = data[stroff:stroff + strsize]
    names = []
    for index in range(nsyms):
        name_offset = struct.unpack_from("<I", data, symoff + 16 * index)[0]
        end = strings.find(b"\0", name_offset)
        names.append(strings[name_offset:end].decode("utf-8", "replace"))
    return names
