#!/usr/bin/env python3
"""Proven, whole-program data conversions for engines already present.

No ROM lookup, network, decryption, execution, region guessing or activation.
Unsupported instructions retain the entire native source program in reserve.
The caller still applies its identity, dependency and runtime size gates.
"""
from __future__ import annotations

import copy
import hashlib
import io
from pathlib import PurePosixPath
import re
import struct
import zipfile

from unified_formats import FormatError, cheat, game
from unified_reserve import parse_cheatdevice_ps2


PROOFS = {
    "mister-nes-rom-to-nestopia": [
        "https://github.com/MiSTer-devel/NES_MiSTer/blob/49a0a662e244469ca77b2155746a066df704ffae/rtl/cheatcodes.sv",
        "https://github.com/MiSTer-devel/NES_MiSTer/blob/49a0a662e244469ca77b2155746a066df704ffae/rtl/nes.v",
        "https://github.com/MiSTer-devel/NES_MiSTer/blob/49a0a662e244469ca77b2155746a066df704ffae/NES.sv",
        "https://github.com/libretro/nestopia/blob/135dfa6dfda5e7603d61e751b9ddd0cc42546bc3/libretro/libretro.cpp",
        "https://github.com/libretro/nestopia/blob/135dfa6dfda5e7603d61e751b9ddd0cc42546bc3/source/core/NstCheats.cpp",
    ],
    "mister-psx-write-to-gameshark": [
        "https://github.com/MiSTer-devel/PSX_MiSTer/blob/cd17b5a0ad261005c321d9d5ba41b8dbe313a7d3/rtl/cheats.vhd",
        "https://github.com/MiSTer-devel/PSX_MiSTer/blob/cd17b5a0ad261005c321d9d5ba41b8dbe313a7d3/PSX.sv",
        "https://github.com/MiSTer-devel/PSX_MiSTer/blob/cd17b5a0ad261005c321d9d5ba41b8dbe313a7d3/rtl/sdram.sv",
        "https://github.com/libretro/beetle-psx-libretro/blob/10e4b0c6ceae20daa65ddf436a4445dddd0982d2/libretro.c",
        "https://github.com/libretro/beetle-psx-libretro/blob/10e4b0c6ceae20daa65ddf436a4445dddd0982d2/mednafen/mempatcher.c",
    ],
    "ps2rd-simple-write-to-pnach": [
        "https://github.com/root670/CheatDevicePS2/blob/7d9c525a3a8377ff0b8fe782ea692ed0f245b92c/engine/engine_asm.S",
        "https://github.com/mlafeldt/ps2rd/blob/master/Documentation/code_types.txt",
        "https://github.com/PCSX2/pcsx2-net-www/blob/main/docs/advanced/writing-patches.md#raw-codes",
    ],
    "mister-gba-ram-to-vba": [
        "https://github.com/MiSTer-devel/GBA_MiSTer/blob/93790a023395bbd90e5eaf4dfb2cb5910afd55f5/rtl/gba_cheats.vhd",
        "https://github.com/MiSTer-devel/GBA_MiSTer/blob/93790a023395bbd90e5eaf4dfb2cb5910afd55f5/rtl/gba_top.vhd",
        "https://github.com/MiSTer-devel/GBA_MiSTer/blob/93790a023395bbd90e5eaf4dfb2cb5910afd55f5/rtl/gba_memorymux.vhd",
        "https://github.com/mgba-emu/mgba/blob/7a12d6d4b9acb14c0ae62c9166b6a2f3d08007f6/src/gba/cheats.c",
        "https://github.com/mgba-emu/mgba/blob/7a12d6d4b9acb14c0ae62c9166b6a2f3d08007f6/src/core/cheats.c",
    ],
}

UNCONVERTED_REASONS = {
    "gb": "mister-gb-rom-bank-and-read-override-equivalence-not-established",
    "snes": "mister-snes-bus-read-override-is-not-a-periodic-ram-write",
    "md": "mister-md-read-override-cartridge-mapping-and-compare-not-native-par",
    "sms": "mister-sms-banked-read-override-not-native-action-replay-write",
    "mcd": "mister-megacd-program-ram-bank-and-read-override-not-native-par",
    "gba": "mister-gba-decoded-operation-byte-mask-is-not-a-device-code",
    "n64": "mister-n64-operation-byte-mask-and-endian-not-gameshark-encoding",
    "pce": "pce-native-cheat-activation-adapter-not-present",
    "pccd": "pce-cd-native-cheat-activation-adapter-not-present",
    "lynx": "lynx-native-cheat-activation-adapter-not-present",
    "vb": "virtualboy-native-cheat-activation-adapter-not-present",
    "jaguar": "jaguar-native-cheat-activation-adapter-not-present",
}


def _reserved(name: str, raw: bytes, reason: str) -> dict:
    return cheat(name, "\n".join(raw[n:n + 16].hex().upper() for n in range(0, len(raw), 16)),
                 "mister-native-tuples", status="requires_engine", reason=reason,
                 enabled=False)


def convert_mister_program(raw: bytes, system: str, name: str = "") -> dict:
    """Convert a complete binary tuple program or preserve all of it.

    NES only converts ROM bus reads, never RAM reads into frame-based writes.
    PSX converts 8/16-bit RAM writes and single EQ/NE/GT tests immediately
    preceding one write; adjacent tests have different semantics and stay raw.
    Multi-line source programs are never shortened to their supported subset.
    """
    if not isinstance(raw, bytes) or not raw or len(raw) % 16 or len(raw) > 128 * 1024:
        raise FormatError("invalid-mister-tuple-program-size")
    rows = list(struct.iter_unpack("<IIII", raw))
    if (system == "nes" and len(rows) > 100) or (system == "gba" and len(rows) > 128):
        return _reserved(name, raw, "mister-program-exceeds-reviewed-conversion-boundary")
    lines, addresses = [], set()
    if system == "nes":
        for flags, address, compare, value in rows:
            if flags not in (0, 1) or not 0x8000 <= address <= 0xFFFF or value > 0xFF or compare > 0xFF:
                return _reserved(name, raw, "mister-nes-needs-rom-byte-read-with-known-flags")
            if address in addresses:
                return _reserved(name, raw, "mister-overlapping-read-priority-not-equivalent")
            addresses.add(address)
            lines.append(f"{address:04X}?{compare:02X}:{value:02X}" if flags else f"{address:04X}:{value:02X}")
        conversion, dialect = "mister-nes-rom-to-nestopia", "nes-raw"
    elif system == "psx":
        for index, (flags, address, compare, value) in enumerate(rows):
            # 0x10/20/30 are byte-enable masks0001/0010/0011, ALWAYS0.
            # SDRAM ch3 takes addr[25:1]: the low two byte enables therefore
            # address the even base and base+1, respectively. No CPU mapper
            # or physical ROM offset is inferred from this RAM bus address.
            # Only ordinary cached/uncached 2MiB main RAM addresses are mapped.
            offset = address & 0x1FFFFFFF
            operation, mask = flags & 15, flags & 0xF0
            # Operation3/4 names disagree with the RTL inequalities. Do not
            # substitute their labels for the actual hardware behavior.
            if (flags > 255 or mask not in (0x10, 0x20, 0x30) or operation not in (0, 1, 2, 6)
                    or address >> 24 not in (0x00, 0x80, 0xA0)
                    or offset >= 0x200000 or offset % 2):
                return _reserved(name, raw, "mister-psx-condition-mask-or-address-needs-native-interpreter")
            width = 2 if mask == 0x30 else 1
            if mask == 0x20:
                if value > 0xFFFF or value & 0xFF:
                    return _reserved(name, raw, "mister-psx-unused-byte-fields-not-canonical")
                offset += 1
                value >>= 8
            if value >= 1 << (8 * width) or offset % width or offset + width > 0x200000:
                return _reserved(name, raw, "mister-psx-value-width-or-alignment-not-equivalent")
            if operation:
                # MiSTer skips its immediate next tuple. Beetle accumulates
                # consecutive GS conditions, so only condition+one-write is
                # equivalent. The fourth tuple word stores the tested value;
                # bits63:32 (the generic "compare" word) are never consumed
                # by this PSX RTL interpreter and remain in source_code.
                if index + 1 >= len(rows) or rows[index + 1][0] & 15:
                    return _reserved(name, raw, "mister-skip-next-is-not-consecutive-gameshark-condition-and")
                opcode = (0xE0 if width == 1 else 0xD0) + {1: 0, 2: 3, 6: 1}[operation]
            else:
                if any(offset + byte in addresses for byte in range(width)):
                    return _reserved(name, raw, "mister-overlapping-writes-need-order-review")
                addresses.update(range(offset, offset + width))
                opcode = 0x30 if width == 1 else 0x80
            lines.append(f"{(opcode << 24) | offset:08X} {value:04X}")
        conversion, dialect = "mister-psx-write-to-gameshark", "ps1-gameshark"
    elif system == "gba":
        for flags, address, unused_compare, value in rows:
            if (not flags or flags & ~0xF0 or address % 4
                    or not (0x02000000 <= address <= 0x0203FFFC or 0x03000000 <= address <= 0x03007FFC)):
                return _reserved(name, raw, "mister-gba-needs-unconditional-aligned-ewram-iwram-byte-mask")
            # Proven vblank RAM read/modify/write with the CPU halted. Byte
            # assignments in the same tuple/lane order preserve overlap too.
            # Neither CodeBreaker opcodes nor encrypted-device seeds are used.
            for lane in range(4):
                if flags & (0x10 << lane):
                    lines.append(f"{address + lane:08X}:{(value >> (8 * lane)) & 0xFF:02X}")
        conversion, dialect = "mister-gba-ram-to-vba", "gba-vba-raw"
    else:
        return _reserved(name, raw, UNCONVERTED_REASONS.get(system, "mister-source-platform-not-identified"))
    result = cheat(name, "\n".join(lines), dialect, enabled=False, status="available",
                   source_code="\n".join(raw[n:n + 16].hex().upper() for n in range(0, len(raw), 16)),
                   source_dialect="mister-native-tuples",
                   conversion={"id": conversion, "proofs": PROOFS[conversion]})
    if system == "psx":
        has_control = any(line[:2] not in ("30", "80") for line in lines)
        if has_control and len("+".join(line.replace(" ", "") for line in lines)) > 255:
            result.update(status="requires_engine", reason="psx-converted-program-exceeds-atomic-255-byte-boundary")
        elif not has_control and len("+".join(lines)) > 8192:
            result.update(status="requires_engine", reason="psx-independent-writes-exceed-8192-byte-input-boundary")
    if system == "gba":
        result["conversion"]["scope"] = "ewram-iwram-vblank-writes"
        if len(lines) > 128 or len("+".join(lines)) > 4096:
            result.update(status="requires_engine", reason="gba-converted-program-exceeds-128-line-or-4096-byte-boundary")
    # A source label explicitly describing a modifier can encode a missing
    # selection as zero in this binary export. Keep this ambiguity visible.
    if re.search(r"(?i)\bmodifier\b", name):
        result.update(status="unresolved", reason="mister-modifier-selection-not-attested")
    return result


def parse_mister_adapted_zip(data: bytes, options: dict) -> list[dict]:
    path = options.get("path", "")
    filename = PurePosixPath(path).name
    match = re.fullmatch(r"(.+?)\s+\[([0-9A-Fa-f]{8})\]\.zip", filename)
    title = match[1] if match else PurePosixPath(path).stem
    folders = {"NES": "nes", "PSX": "psx", "GameBoy": "gb", "SNES": "snes", "GBA": "gba",
               "MegaDrive": "md", "MegaCD": "mcd", "SMS": "sms", "N64": "n64",
               "TGFX16": "pce", "TGFX16-CD": "pccd", "AtariLynx": "lynx", "VirtualBoy": "vb", "Jaguar": "jaguar"}
    system = next((sid for folder, sid in folders.items() if folder in PurePosixPath(path).parts), "unknown")
    result = game(title, system, options)
    # A source filename checksum has no established runtime byte-range scheme.
    # Preserve it as source metadata, never turn it into a full-ROM CRC match.
    if match:
        result["source_identities"] = [{"type": "crc32", "value": match[2].upper(), "scheme": "mister-source-crc"}]
    if system == "psx" and re.fullmatch(r"(?:SL|SC)[A-Z]{2}-\d{5}", title):
        result["identities"].append({"type": "serial", "value": title, "scheme": "ps1-disc-serial"})
    if not result["regions"]:
        psx_regions = {"NTSC-U": "USA", "NTSC-J": "Japan", "PAL-E": "Europe", "PAL-F": "France", "PAL-I": "Italy"}
        result["regions"] = [region for token, region in psx_regions.items() if "(" + token + ")" in title]
    if not result["identities"]:
        result.update(matching_policy="title-edition-candidate", edition_confirmation_required=True)
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        if len(archive.infolist()) > 32768 or sum(i.file_size for i in archive.infolist()) > 64 * 1024 * 1024:
            raise FormatError("mister-nested-archive-limit")
        for info in archive.infolist():
            if info.is_dir() or not info.filename.endswith(".gg"):
                continue
            member = PurePosixPath(info.filename)
            if member.is_absolute() or ".." in member.parts or info.file_size > 128 * 1024:
                raise FormatError("unsafe-or-oversized-mister-program")
            raw = archive.read(info)
            try:
                item = convert_mister_program(raw, system, member.stem)
            except FormatError as error:
                result.setdefault("conversion_errors", []).append({"path": info.filename, "reason": str(error)})
                continue
            item["source_member"] = info.filename
            item.setdefault("provenance", []).append({
                "archive_member": path, "program_member": info.filename,
                "native_program_sha256": hashlib.sha256(raw).hexdigest(),
                "source_identities": copy.deepcopy(result.get("source_identities", [])),
            })
            if archive.comment:
                item["notes"] = archive.comment.decode("utf-8", errors="replace")
            result["cheats"].append(item)
    return [result]


def convert_ps2rd_simple_program(code: str) -> str:
    """Only decrypted ps2rd0/1/2 writes, no hooks or partial conditionals.

    These opcodes are shared by the documented PNACH extended interpreter.
    The source's identity must be reviewed separately; this function cannot
    derive an executable CRC from a title or infer a region/revision.
    """
    lines = [line.strip().upper() for line in code.splitlines() if line.strip()]
    if not lines or len(lines) > 4096:
        raise FormatError("empty-or-oversized-ps2-raw-program")
    for line in lines:
        if not re.fullmatch(r"[012][0-9A-F]{7} [0-9A-F]{8}", line):
            raise FormatError("ps2-raw-needs-simple-constant-writes-only")
        left, right = line.split(); address, value = int(left, 16) & 0x0FFFFFFF, int(right, 16)
        width = (1, 2, 4)[int(left[0])]
        if address >= 0x2000000 or address % width or value >= 1 << (width * 8):
            raise FormatError("ps2-raw-address-alignment-or-value-width")
    return "\n".join("patch=1,EE," + line.replace(" ", ",extended,") for line in lines)


def parse_cheatdevice_pnach(data: bytes, options: dict) -> list[dict]:
    """Profiled CheatDevice PS2 import; never decode encrypted codes by guess.

    game_profiles maps an exact source title to independently attested typed
    identities (serial or executable CRC). Without a profile the conversion is
    preserved but unresolved: the official database has no edition identity.
    """
    result = parse_cheatdevice_ps2(data, options)
    for record in result:
        profile = options.get("game_profiles", {}).get(record["title"], {})
        for field in ("identities", "regions", "languages", "revision", "identity_provenance"):
            if field in profile:
                record[field] = copy.deepcopy(profile[field])
        exact = any(i.get("type") == "ps2_crc" and i.get("scheme") == "pcsx2-executable-crc"
                    and re.fullmatch(r"[0-9A-Fa-f]{8}", i.get("value", ""))
                    or i.get("type") == "serial" and i.get("scheme") == "ps2-disc-serial"
                    and re.fullmatch(r"[A-Z]{4}-\d{5}", i.get("value", "")) for i in record["identities"])
        programs = []
        for item in record["cheats"]:
            if not item["code"].strip():
                record.setdefault("source_headings", []).append(item["name"])
                continue
            original = item["code"]
            try:
                converted = convert_ps2rd_simple_program(original)
            except FormatError as error:
                item["reason"] = str(error)
            else:
                item.update(code=converted, source_code=original, source_dialect="ps2-raw", dialect="pnach",
                            status="available" if exact else "unresolved",
                            reason="" if exact else "ps2-source-edition-identity-not-established", enabled=False,
                            conversion={"id": "ps2rd-simple-write-to-pnach", "proofs": PROOFS["ps2rd-simple-write-to-pnach"]})
            programs.append(item)
        record["cheats"] = programs
    return result


PARSERS = {"mister-adapted-zip": parse_mister_adapted_zip,
           "cheatdevice-pnach": parse_cheatdevice_pnach}
