"""Verify the libretro, MeloNX and RPCS3 bridge fingerprints and optionally ARMSX2.

Read-only. An alternate fingerprint exchanges only the encoded references to two
equivalent objc_msgSend import slots. No executable or modified IPA is written.
"""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import sys
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "build-utils"))
from delivery_benchmark import payload_fingerprint


def require(condition, message):
    if not condition:
        raise ValueError(message)


def layout(data):
    require(data[:8] == bytes.fromhex("cffaedfe0c000001"), "Expected thin arm64 Mach-O")
    commands, sections = {}, {}
    cursor = 32
    for _ in range(struct.unpack_from("<I", data, 16)[0]):
        command, size = struct.unpack_from("<II", data, cursor)
        require(size >= 8 and cursor + size <= len(data), "Invalid load command")
        commands[command] = cursor
        if command == 0x19:  # LC_SEGMENT_64
            count = struct.unpack_from("<I", data, cursor + 64)[0]
            require(72 + count * 80 <= size, "Invalid section count")
            for i in range(count):
                pos = cursor + 72 + i * 80
                name, segment, address, length, offset = struct.unpack_from("<16s16sQQI", data, pos)
                key = (segment.rstrip(b"\0").decode(), name.rstrip(b"\0").decode())
                sections[key] = (address, offset, length)
        cursor += size
    return sections, commands


def msgsend_slots(data, got, fixups):
    """Decode an arm64 chained bind and its referenced dylib, symbol, weak flag and addend."""
    version, starts, imports, symbols, count, fmt, compressed = struct.unpack_from("<7I", data, fixups)
    require((version, fmt, compressed) == (0, 1, 0), "Unsupported chained imports format")
    start = fixups + starts
    segment_count = struct.unpack_from("<I", data, start)[0]
    pointer_formats = set()
    for segment in range(segment_count):
        delta = struct.unpack_from("<I", data, start + 4 + 4 * segment)[0]
        if delta:
            pointer_formats.add(struct.unpack_from("<H", data, start + delta + 6)[0])
    require(pointer_formats and pointer_formats <= {2, 6}, "Unsupported chained pointer format")
    addr, off, size = got
    matches = {}
    for i in range(0, size, 8):
        word = struct.unpack_from("<Q", data, off + i)[0]
        if not word >> 63:
            continue
        ordinal = word & 0xffffff
        require(ordinal < count, "Invalid GOT import ordinal")
        imp = struct.unpack_from("<I", data, fixups + imports + 4 * ordinal)[0]
        name_at = fixups + symbols + (imp >> 9)
        name = data[name_at:data.index(b"\0", name_at)]
        if name == b"_objc_msgSend":
            matches[addr + i] = (imp & 255, (imp >> 8) & 1, (word >> 24) & 255)
    require(len(matches) == 2 and len(set(matches.values())) == 1, "Expected two equivalent objc_msgSend binds")
    return matches


def alternate(data):
    sections, commands = layout(data)
    fixups = struct.unpack_from("<I", data, commands[0x80000034] + 8)[0]  # LC_DYLD_CHAINED_FIXUPS
    slots = msgsend_slots(data, sections["__DATA_CONST", "__got"], fixups)
    first, second = sorted(slots)
    require(second - first == 8 and first >> 12 == second >> 12, "Unexpected GOT layout")
    other = {first: second, second: first}
    alternate_bytes = bytearray(data)
    counts = {}
    for name, stride, adrp_offset in (("__stubs", 12, 0), ("__objc_stubs", 32, 8)):
        address, offset, size = sections["__TEXT", name]
        require(size % stride == 0, "Unexpected stub size")
        count = 0
        for i in range(0, size, stride):
            pos = offset + i + adrp_offset
            adrp, ldr, branch = struct.unpack_from("<III", data, pos)
            require(adrp & 0x9f00001f == 0x90000010 and ldr & 0xffc003ff == 0xf9400210
                    and branch == 0xd61f0200, "Unrecognized arm64 stub instructions")
            imm = ((adrp >> 5 & 0x7ffff) << 2) | (adrp >> 29 & 3)
            signed_pages = imm - (1 << 21) if imm & (1 << 20) else imm
            page = ((address + i + adrp_offset) & ~4095) + (signed_pages << 12)
            target = page + ((ldr >> 10) & 4095) * 8
            if target in other:
                displacement = (other[target] - target) // 8
                struct.pack_into("<I", alternate_bytes, pos + 4, ldr + (displacement << 10))
                count += 1
        require(count == (1 if name == "__stubs" else size // stride), "Unexpected objc_msgSend stub count")
        counts[name] = count
    return payload_fingerprint(bytes(alternate_bytes)), counts


def verify(ipa, receipt, reference, *, include_armsx2=False):
    with ipa.open("rb") as stream:
        require(hashlib.file_digest(stream, "sha256").hexdigest() == receipt["ipaSha256"], "IPA SHA-256 mismatch")
    result = {}
    with ZipFile(ipa) as archive:
        bridges = ("libretro", "melonx", "rpcs3")
        if include_armsx2:
            bridges += ("armsx2",)
        for prefix in bridges:
            bridge = prefix + "_internal_bridge"
            path = f"Frameworks/{bridge}.framework/{bridge}"
            data = archive.read("Payload/NeoStation.app/" + path)
            actual, expected = payload_fingerprint(data), reference["images"][path]
            require(actual == receipt["images"][path], "Bridge differs from signed IPA receipt: " + bridge)
            alternative, counts = alternate(data)
            require(expected in (actual, alternative), "Unexplained bridge fingerprint: " + bridge)
            result[bridge] = dict(actual=actual, reference=expected, alternate=alternative,
                                  exact=actual == expected, references=counts)
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("ipa", "receipt", "reference"):
        parser.add_argument(name, type=Path)
    parser.add_argument("--include-armsx2", action="store_true", help="Also check the ARMSX2 bridge using the same signed-payload rules")
    args = parser.parse_args()
    print(json.dumps(verify(args.ipa, json.loads(args.receipt.read_bytes()),
                            json.loads(args.reference.read_bytes()), include_armsx2=args.include_armsx2), indent=2))
