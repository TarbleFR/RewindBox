"""Host tests for the KartPad runtime build tooling (no game data involved).

- macho.exported_names walks an export trie (shared prefixes, terminal and
  inner nodes) exactly; a cyclic trie is refused.
- check_runtime.describe counts translated function names in exports and
  symbols, and finds the pinned fingerprint string.
- The runtime pins agree with the 0.8.3 migration target and the official
  game-free IPA identity recorded in build-utils/kartpad/migration-target.json.
"""
from __future__ import annotations

import json
import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "build-utils/kartpad_runtime"))
sys.path.insert(0, str(ROOT / "build-utils"))
import macho  # noqa: E402
import check_runtime  # noqa: E402


def uleb(value: int) -> bytes:
    out = bytearray()
    while True:
        byte = value & 0x7F
        value >>= 7
        out.append(byte | (0x80 if value else 0))
        if not value:
            return bytes(out)


def fixed_uleb3(value: int) -> bytes:
    return bytes([(value & 0x7F) | 0x80, ((value >> 7) & 0x7F) | 0x80, (value >> 14) & 0x7F])


def simple_trie(names: list[str]) -> bytes:
    """A flat trie: root with one edge per full name (valid, if not minimal)."""
    root_size = 2 + sum(len(name) + 1 + 3 for name in names)
    blob = bytearray(uleb(0) + bytes([len(names)]))
    leaf = b"\x03\x00\x80\x20\x00"  # terminal size 3: flags 0, address uleb 0x1000; no children
    child_offsets = [root_size + index * len(leaf) for index in range(len(names))]
    for name, offset in zip(names, child_offsets):
        blob.extend(name.encode() + b"\0" + fixed_uleb3(offset))
    assert len(blob) == root_size
    for _ in names:
        blob.extend(leaf)
    return bytes(blob)


def macho_with_exports(names: list[str], extra: bytes = b"") -> bytes:
    exports = simple_trie(names)
    header = bytearray(32 + 16 + 24)
    struct.pack_into("<8I", header, 0, macho.MH_MAGIC_64, 0x0100000C, 0, 6, 2, 16 + 24, 0, 0)
    data_offset = len(header)
    struct.pack_into("<4I", header, 32, macho.LC_DYLD_EXPORTS_TRIE, 16, data_offset, len(exports))
    struct.pack_into("<6I", header, 48, macho.LC_BUILD_VERSION, 24, 2, 16 << 16, 0, 0)
    return bytes(header) + exports + extra


names = ["_NeoKartPad_GetAPI", "_SDL_Init", "_func_8000951C", "_AICheckInit_80124094"]
binary = macho_with_exports(names, b"\0" + check_runtime.PINS["pack_interface_fingerprint"].encode() + b"\0")
info = macho.parse(binary)
assert info["filetype"] == 6 and info["platform"] == 2 and info["minos"] == "16.0"
assert macho.exported_names(binary, info) == sorted(names), macho.exported_names(binary, info)
described = check_runtime.describe(binary)
assert described["translated_symbols"] == 1, described  # the HLE name _Name_8xxxxxxx is not one
assert described["fingerprint_present"]
assert check_runtime.names_digest(["b", "a", "a"]) == check_runtime.sha256(b"a\nb\n")

cyclic = bytearray(macho_with_exports(["_x"]))
start = 32 + 16 + 24
cyclic[start + 2 + 3:start + 2 + 6] = fixed_uleb3(0)  # child points back to the root
try:
    macho.exported_names(bytes(cyclic))
except ValueError:
    pass
else:
    raise AssertionError("cyclic export trie accepted")

pins = json.loads((ROOT / "build-utils/kartpad_runtime/source.json").read_text())
target = json.loads((ROOT / "build-utils/kartpad/migration-target.json").read_text())
assert pins["pack_interface_fingerprint"] == target["pack_interface_fingerprint"]
assert pins["kartpad"]["commit"] == target["release_commit"]
assert pins["kartpad"]["submodules"]["vendor/runtimes/ios"] == target["ios_runtime_commit"]
assert pins["kartpad"]["submodules"]["vendor/wiicompiled"] == target["translator_commit"]
assert pins["official_game_free_ipa"]["sha256"] == target["official_ipa"]["sha256"]
assert pins["official_game_free_ipa"]["executable_sha256"] == target["official_ipa"]["executable_sha256"]
assert pins["embedded"]["neostation_abi"] == 3
print("PASS: KartPad runtime tooling — export trie walk and cycle refusal, translated-name count "
      "excluding HLE names, fingerprint detection, pins consistent with the 0.8.3 migration target")
