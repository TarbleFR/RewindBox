#!/usr/bin/env python3
"""Pure, bounded importers for NeoStation's published cheat catalogue.

These readers preserve programs, never execute them, and never infer another
region's compatibility. A filename is a title hint; typed hashes/IDs retain
their original scope. No source parser is permitted to repair malformed code.
"""
from __future__ import annotations

import configparser
import io
import json
import re
import struct
import xml.etree.ElementTree as ET
from collections import defaultdict
from pathlib import PurePosixPath

MAX_INPUT = 128 * 1024 * 1024
MAX_GAMES = 100000
MAX_CHEATS = 1000000
MAX_CODE = 256 * 1024
SYSTEM_ALIASES = {
    "openemu.system.gb": "gb", "openemu.system.gbc": "gbc",
    "openemu.system.gba": "gba", "openemu.system.nes": "nes",
    "openemu.system.snes": "snes", "openemu.system.n64": "n64",
    "openemu.system.nds": "nds", "openemu.system.psx": "psx",
    "openemu.system.genesis": "md", "openemu.system.megadrive": "md",
    "openemu.system.mastersystem": "sms", "openemu.system.gamegear": "gg",
    # Official OpenEmu-Update/oecores-experimental.xml labels these short IDs.
    "openemu.system.sg": "md", "openemu.system.scd": "mcd",
    "openemu.system.sms": "sms", "openemu.system.gg": "gg",
}


class FormatError(ValueError):
    pass


def text(data: bytes) -> str:
    if len(data) > MAX_INPUT:
        raise FormatError("input exceeds 128 MiB")
    try:
        return data.decode("utf-8-sig")
    except UnicodeDecodeError:
        return data.decode("cp1252")


def xml(data: bytes):
    if len(data) > MAX_INPUT or re.search(br"<!\s*(?:DOCTYPE|ENTITY)", data, re.I):
        raise FormatError("oversized XML or forbidden entity/doctype")
    return ET.fromstring(data)


def title_metadata(title: str) -> dict:
    regions, languages = [], []
    region_names = {"USA", "Europe", "World", "Japan", "France", "Germany", "Spain", "Italy", "Korea", "Australia", "Brazil", "China", "Taiwan"}
    lang_names = {"En", "Fr", "De", "Es", "It", "Ja", "Ko", "Zh", "Nl", "Pt", "Sv", "Da", "No", "Fi"}
    revision = ""
    for part in re.findall(r"\(([^)]+)\)", title):
        for token in re.split(r",\s*", part):
            if token in region_names and token not in regions:
                regions.append(token)
            if token in lang_names and token not in languages:
                languages.append(token)
        if re.match(r"(?i)(?:Rev\s+|v\d)", part):
            revision = part
    return {"regions": regions, "languages": languages, "revision": revision}


def game(title: str, system: str, options=None, identities=None) -> dict:
    options = options or {}
    result = {"title": title.strip(), "system": system or "unknown", "identities": identities or [], "cheats": [], **title_metadata(title)}
    for key in ("regions", "languages", "revision"):
        if key in options:
            result[key] = options[key]
    if options.get("identities"):
        result["identities"].extend(options["identities"])
    if options.get("status"):
        result["status"] = options["status"]
    return result


def cheat(name, code, dialect, **kwargs):
    if not isinstance(code, str) or len(code) > MAX_CODE:
        raise FormatError("oversized or non-text program")
    return {"name": str(name).strip(), "code": code.strip(), "dialect": dialect,
            "dependencies": [], "parameters": [], **kwargs}


def dialect_for(system, code, declared=""):
    declared = declared.lower().replace(" ", "")
    compact = re.sub(r"[+;,\s]", "", code).upper()
    if system == "nes":
        return "nes-gamegenie" if re.fullmatch(r"[APZLGITYEOXUKSVN]{6}(?:[APZLGITYEOXUKSVN]{2})?", compact) else "nes-raw"
    if system == "snes":
        return "snes-gamegenie" if "-" in code else "snes-par"
    if system in {"gb", "gbc"}:
        return "gb-gamegenie" if "-" in code else "gb-gameshark"
    if system == "gba":
        if declared in {"codebreaker", "gamesharksp", "karabiner"}:
            return "gba-codebreaker"
        if declared in {"actionreplayv3", "gamesharkv3", "arv3", "gamesharkadvancev3"}:
            return "gba-gameshark-v3"
        if declared in {"gamesharkv1", "gamesharkv2", "actionreplayv1", "actionreplayv2"}:
            return "gba-gameshark-v1"
        return "gba-unknown"
    if system in {"sms", "gg"} and declared == "actionreplay" and re.fullmatch(r"[0-9A-F]{4}-[0-9A-F]{4}", compact):
        # Preserve the source dialect until its AR-to-native mapping is proved.
        return "sega8-actionreplay"
    return {"nds": "ds-actionreplay", "psx": "ps1-gameshark", "psp": "cwcheat",
            "n64": "n64-gameshark", "3ds": "gateshark", "ps2": "pnach",
            "md": "md-gamegenie" if "-" in code else "md-raw",
            "mcd": "md-gamegenie" if "-" in code else "md-raw",
            "32x": "md-gamegenie" if "-" in code else "md-raw",
            "pico": "md-gamegenie" if "-" in code else "md-raw",
            "pce": "pce-raw", "pccd": "pce-raw", "tg16": "pce-raw", "tgcd": "pce-raw",
            "ws": "wswan-raw", "wsc": "wswan-raw",
            "sms": "sega8-gamegenie" if "-" in code else "sega8-raw",
            "gg": "sega8-gamegenie" if "-" in code else "sega8-raw"}.get(system, "unknown")


def parse_openemu(data, options):
    result = []
    for system in xml(data).findall(".//system"):
        sid = SYSTEM_ALIASES.get(system.get("id", ""), options.get("system", ""))
        for entry in system.findall("game"):
            # XML contains an MD5 but does not attest header stripping,
            # deinterleaving or the original importer's exact byte domain.
            scheme = options.get("hash_scheme", "openemu-md5-unspecified")
            ids = [{"type": "md5", "value": h.get("md5", "").lower(), "scheme": scheme}
                   for h in entry.findall("hashes/hash") if re.fullmatch(r"[a-fA-F0-9]{32}", h.get("md5", ""))]
            g = game(entry.get("title", ""), sid, options, ids)
            if scheme == "openemu-md5-unspecified":
                g.update(edition_confirmation_required=True, matching_policy="title-edition-candidate")
            for c in entry.findall("cheats/cheat"):
                code = c.get("code", "")
                dialect = dialect_for(sid, code, c.get("type", ""))
                if sid == "gba" and dialect == "gba-unknown":
                    dialect = "gba-auto"  # reviewed existing mGBA AUTODETECT feed
                proof = options.get("system_alias_validation") if system.get("id") in {
                    "openemu.system.sg", "openemu.system.scd", "openemu.system.sms", "openemu.system.gg"} else None
                provenance = [{"system_alias_validation": proof, "source_system_id": system.get("id")}] if proof else []
                g["cheats"].append(cheat(c.get("description", ""), code, dialect, provenance=provenance))
            result.append(g)
    return result


def parse_mesen(data, options):
    root = json.loads(text(data))
    result = []
    system = options["system"]
    # Mesen overrides Sha1Cheat for NES (PRG only). SNES falls back to
    # Emulator::_rom.RomFile.GetSha1Hash(), i.e. the actual decoded ROM file.
    scheme = options.get("hash_scheme", "nes-prg" if system == "nes" else "rom-full")
    for entry in root["games"]:
        digest = entry.get("sha1", "").lower()
        ids = [{"type": "sha1", "value": digest, "scheme": scheme}] if re.fullmatch(r"[a-f0-9]{40}", digest) else []
        g = game(entry["name"], system, options, ids)
        for c in entry.get("cheats", []):
            g["cheats"].append(cheat(c["desc"], c["code"].replace(";", "+"), dialect_for(system, c["code"])))
        result.append(g)
    return result


def parse_mighty_mo(data, options):
    g = game(options["title"], "nes", options)
    pending = defaultdict(dict)
    for c in xml(data).findall("cheat"):
        name = c.findtext("description", "").strip()
        genie = c.findtext("genie", "").strip()
        address, value, compare = (c.findtext(t, "").replace("0x", "").strip().upper() for t in ("address", "value", "compare"))
        code = genie or (address + ("?" + compare if compare else "") + ":" + value if address and value else "")
        item = cheat(name, code, "nes-gamegenie" if genie else "nes-raw")
        part = re.fullmatch(r"(.+?)\s*\((\d+) of (\d+)\)", name)
        if part:
            key = (part[1], int(part[3])); number = int(part[2])
            if number in pending[key]:
                item.update(status="invalid", reason="duplicate-multipart-index")
                g["cheats"].append(item)
            else:
                pending[key][number] = item
        else:
            g["cheats"].append(item)
    for (name, total), parts in pending.items():
        ordered = [parts[i] for i in sorted(parts)]
        item = cheat(name, "+".join(c["code"] for c in ordered), ordered[0]["dialect"])
        if set(parts) != set(range(1, total + 1)) or len({c["dialect"] for c in ordered}) != 1:
            item.update(status="unresolved", reason="incomplete-or-mixed-multipart-program")
        g["cheats"].append(item)
    return [g]


def parse_bml(data, options):
    result, g, c = [], None, None
    systems = options.get("system_by_sha256", {})
    for line in text(data).splitlines():
        m = re.fullmatch(r"cartridge sha256:([a-fA-F0-9]{64})", line)
        if m:
            digest = m[1].lower()
            g = game("", systems.get(digest, options.get("system", "")), options,
                     [{"type": "sha256", "value": digest, "scheme": options.get("hash_scheme", "bsnes-cartridge") }])
            if digest in systems and options.get("system_mapping_provenance"):
                g["identity_provenance"] = options["system_mapping_provenance"]
            if g["system"] == "unknown":
                g.update(status="unresolved", reason="multi-system-hash-needs-system-mapping")
            result.append(g); c = None
        elif g is not None and line.startswith("  name:"):
            g["title"] = line.split(":", 1)[1]; g.update(title_metadata(g["title"]))
        elif g is not None and line == "  cheat":
            c = cheat("", "", "unknown"); g["cheats"].append(c)
        elif c is not None and line.startswith("    name:"):
            c["name"] = line.split(":", 1)[1]
        elif c is not None and line.startswith("    code:"):
            pieces = []
            for raw in line.split(":", 1)[1].split("+"):
                words = raw.upper().split("/")
                if len(words) == 2:
                    pieces.append(words[0] + ":" + words[1])
                elif len(words) == 3:
                    # bsnes BML address/compare/value; Nestopia uses address?compare:value.
                    pieces.append(words[0] + "?" + words[1] + ":" + words[2])
                else:
                    pieces.append(raw); c.update(status="invalid", reason="invalid-bml-instruction")
            c["code"] = "+".join(pieces); c["dialect"] = dialect_for(g["system"], c["code"])
            if g.get("identity_provenance"):
                c["provenance"] = [{**g["identity_provenance"], "validation": "Exact primary database SHA256 system classification"}]
    return result


def parse_usrcheat(data, options):
    """Read R4 binary structure, retaining categories and exclusive choices.

    Header CRC is the complement of the standard CRC32 of the first 512 ROM
    bytes. It is not a complete-ROM CRC. Definitions cross-checked against the
    melonDS ARDatabaseDAT format documentation; implementation is independent.
    """
    if len(data) > MAX_INPUT or data[:16] != b"R4 CheatCode\x00\x01\x00\x00":
        raise FormatError("invalid R4 signature/version")
    entries, pos = [], 0x100
    while pos + 16 <= len(data):
        code, crc, offset = struct.unpack_from("<4sIQ", data, pos); pos += 16
        if code == b"\0\0\0\0":
            break
        if not (0x100 <= offset < len(data)):
            raise FormatError("R4 index offset out of bounds")
        entries.append((code.decode("ascii"), crc, offset))
        if len(entries) > MAX_GAMES:
            raise FormatError("too many R4 games")
    else:
        raise FormatError("unterminated R4 index")

    def u32(p, end):
        if p + 4 > end:
            raise FormatError("truncated R4 integer")
        return struct.unpack_from("<I", data, p)[0], p + 4

    def string(p, end):
        e = data.find(b"\0", p, min(end, p + 65537))
        if e < 0:
            raise FormatError("unterminated R4 string")
        return data[p:e].decode("utf-8", errors="replace"), e + 1

    result = []
    offsets = sorted({e[2] for e in entries} | {len(data)})
    ends = dict(zip(offsets, offsets[1:]))
    def read_entry(code, crc, start):
        end = ends[start]
        name, p = string(start, end); p = (p + 3) & ~3
        flags, p = u32(p, end); p += 32
        if p > end:
            raise FormatError("truncated R4 game header")
        g = game(name, "nds", options, [{"type": "ds_game_code", "value": code, "scheme": "nds-header-gamecode"},
            {"type": "ds_crc", "value": f"{crc:08X}", "scheme": "r4-header512-crc32-inverted"}])
        category, remaining, exclusive = "", 0, False
        for _ in range(flags & 0xFFFFFF):
            item_start = p; f, p = u32(p, end)
            title, p = string(p, end); note, p = string(p, end); p = (p + 3) & ~3
            size = f & 0xFFFFFF
            if f & (1 << 28):
                if size == 0 or size >= 0x10000:
                    raise FormatError("invalid R4 category size")
                category, remaining, exclusive = title, size, bool(f & (1 << 24))
                continue
            count, p = u32(p, end)
            if count > MAX_CODE // 9 or p + count * 4 > end:
                raise FormatError(f"invalid R4 instruction count {count} in {name!r}/{title!r} at {p:08X}")
            expected = ((len(title.encode("utf-8")) + len(note.encode("utf-8")) + 2 + 3) // 4) + 1 + count
            # Compare byte positions, not re-encoded replacement text.
            if item_start + 4 + size * 4 != p + count * 4:
                raise FormatError("R4 item size mismatch")
            words = struct.unpack_from(f"<{count}I", data, p); p += count * 4
            lines = [f"{words[i]:08X} {words[i+1]:08X}" if i+1 < count else f"{words[i]:08X}" for i in range(0, count, 2)]
            item = cheat((category + "/" if remaining else "") + title, "\n".join(lines), "ds-actionreplay", notes=note)
            if count & 1:
                item.update(status="invalid", reason="odd-r4-instruction-word-count")
            if remaining and exclusive:
                item["exclusive_group"] = category
            g["cheats"].append(item)
            remaining = max(remaining - 1, 0)
        return g
    for code, crc, start in entries:
        try:
            result.append(read_entry(code, crc, start))
        except FormatError as exc:
            # The index gives an independent boundary for every game. A bad
            # record never suppresses the remaining verified source entries.
            g = game(code, "nds", options, [
                {"type":"ds_game_code","value":code,"scheme":"nds-header-gamecode"},
                {"type":"ds_crc","value":f"{crc:08X}","scheme":"r4-header512-crc32-inverted"}])
            g.update(status="invalid", import_error=str(exc))
            result.append(g)
    return result


def parse_cwcheat(data, options):
    result, g, c = [], None, None
    for line in text(data).splitlines():
        line = line.strip()
        if line.startswith("_S "):
            gid = line[3:].strip().replace("_", "").replace("-", "")
            g = game(gid, "psp", options, [{"type": "game_id", "value": gid, "scheme": "psp-param-sfo-disc-id"}])
            result.append(g); c = None
        elif g is not None and line.startswith("_G "):
            g["title"] = line[3:].strip(); g.update(title_metadata(g["title"]))
        elif g is not None and re.match(r"_C[01] ", line):
            c = cheat(line[4:], "", "cwcheat", kind=options.get("kind", "gameplay"), notes=options.get("notes", "")); g["cheats"].append(c)
        elif c is not None and line.startswith("_L "):
            words = re.findall(r"(?:0x)?([0-9A-Fa-f]{8})(?![0-9A-Fa-f])", line[3:])
            if len(words) != 2 or not re.fullmatch(r"(?:0x)?[0-9A-Fa-f]{8}\s+(?:0x)?[0-9A-Fa-f]{8}", line[3:]):
                c.update(status="invalid", reason="malformed-cwcheat-instruction")
            c["code"] += ("\n" if c["code"] else "") + line[3:]
        elif c is not None and line.startswith(("//", "#", ";")):
            c["notes"] = (c.get("notes", "") + "\n" + line).strip()
    return result


def parse_retroarch(data, options):
    values, invalid_keys = {}, set()
    lines, index = text(data).splitlines(), 0
    assignment = re.compile(r"^\s*([A-Za-z0-9_]+)\s*=(.*)$")
    def closing_quote(value):
        escaped = False
        for position, char in enumerate(value[1:], 1):
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                return position
        return None
    while index < len(lines):
        match = assignment.match(lines[index]); index += 1
        if not match:
            continue
        key, value = match[1], match[2].strip()
        if key in values:
            invalid_keys.add(key)
        if value.startswith('"'):
            end = closing_quote(value)
            # A continuation is real source text, never a synthesized quote.
            # Stop before another assignment so one malformed code does not
            # swallow the following independent programs in the same file.
            while end is None and index < len(lines) and not assignment.match(lines[index]):
                if len(value) + len(lines[index]) > MAX_CODE:
                    break
                value += "\n" + lines[index]; index += 1
                end = closing_quote(value)
            if end is None or (value[end + 1:].strip() and not value[end + 1:].lstrip().startswith("#")):
                invalid_keys.add(key)
                value = value[1:]  # exact incomplete source body, never active
            else:
                value = value[1:end].replace('\\"', '"').replace('\\\\', '\\')
        values[key] = value
    g = game(options["title"], options["system"], options)
    for n in sorted({int(m[1]) for k in values if (m := re.match(r"cheat(\d+)_", k))}):
        p = f"cheat{n}_"; code = values.get(p + "code", "")
        item = cheat(values.get(p + "desc", ""), code, dialect_for(g["system"], code, options.get("dialect", "")))
        if g["system"] == "gba" and item["dialect"] == "gba-unknown":
            item["dialect"] = "gba-auto"  # official CHT's existing mGBA channel
        if any(key.startswith(p) for key in invalid_keys):
            item.update(status="invalid", reason="unterminated-or-duplicate-retroarch-field")
        handler = values.get(p + "handler", "0")
        if handler != "0":
            item.update(status="requires_engine", reason="retroarch-handler1-memory-engine-not-enabled", handler=1)
            item["memory_operation"] = {k[len(p):]: v for k, v in values.items() if k.startswith(p)}
            if not code:
                item["code"] = json.dumps(item["memory_operation"], sort_keys=True, ensure_ascii=False)
                item["dialect"] = "retroarch-memory"
        g["cheats"].append(item)
    return [g]


def parse_duckstation(data, options):
    raw = re.sub(r"[ \t]+$", "", text(data), flags=re.M)
    stem = PurePosixPath(options.get("path", "")).stem
    serial = re.match(r"([A-Z]{4}-\d{5})(?:-([a-fA-F0-9]+))?", stem)
    ids = [{"type": "serial", "value": serial[1], "scheme": "ps1-disc-serial"}] if serial else []
    if serial and serial[2]:
        ids.append({"type": "executable_hash", "value": serial[2], "scheme": "duckstation-game-hash"})
    labelled = re.search(r"(?m)^\s*;\s*CHTDB:\s*;\s*\[\s*(.*?)\s*\]\s*$", raw)
    g = game(options.get("title", labelled[1] if labelled else stem), "psx", options, ids)
    c = None
    for line in raw.splitlines():
        line = line.strip()
        if line.startswith("[") and line.endswith("]"):
            c = cheat(line[1:-1], "", "ps1-gameshark", source_options={})
            g["cheats"].append(c)
        elif c is not None and line and not line.startswith(("#", ";")):
            if "=" in line:
                key, value = (s.strip() for s in line.split("=", 1))
                if key in {"Code", "Codes"}:
                    c["code"] += ("\n" if c["code"] else "") + value
                else:
                    c["source_options"][key] = value
                    if key == "Activation" and value not in {"EndFrame", "Manual"}:
                        c.update(status="requires_engine", reason="duckstation-activation-mode-not-reviewed")
            else:
                c["code"] += ("\n" if c["code"] else "") + line
    return [g]


def parse_pnach(data, options):
    raw = text(data)
    stem = PurePosixPath(options.get("path", "")).name
    gm = re.search(r"(?im)^\s*gametitle\s*=\s*(.+)$", raw)
    title = gm[1].strip() if gm else options.get("title", stem)
    # PNACH publications explicitly print executable CRCs in a leading filename
    # token or final [CRC] gametitle token. These are typed source identifiers,
    # not hashes derived from the displayed title or a different region.
    prefix = re.match(r"([A-Fa-f0-9]{8})(?:[._-]|$)", stem)
    suffix = re.search(r"\[([A-Fa-f0-9]{8})\]\s*$", title)
    crcs = {m[1].upper() for m in (prefix, suffix) if m}
    if len(crcs) > 1:
        raise FormatError("pnach-conflicting-executable-crc")
    ids = [{"type": "ps2_crc", "value": crc, "scheme": "pcsx2-executable-crc"} for crc in sorted(crcs) if crc != "00000000"]
    serials = set(re.findall(r"\[([A-Z]{4}-[0-9]{5})\]", title))
    if len(serials) > 1:
        raise FormatError("pnach-conflicting-disc-serial")
    ids += [{"type": "serial", "value": serial.replace("-", ""), "scheme": "ps2-disc-serial"} for serial in sorted(serials)]
    g = game(title, "ps2", options, ids)
    # Native PCSX2 [group] names delimit independent selections. The source
    # often repeats the same header before EVERY line: merge all occurrences
    # with the same name, keeping order and complete conditional sequences.
    groups, current, prefix_lines = {}, None, []
    for line in raw.splitlines():
        match = re.fullmatch(r"\s*\[([^\]\r\n]+)\]\s*", line)
        if match:
            current = match[1].strip()
            groups.setdefault(current, []).append(line)
        elif current is None:
            prefix_lines.append(line)
        else:
            groups[current].append(line)
    safe_groups = bool(groups) and not any(re.match(r"\s*patch\s*=", line, re.I) for line in prefix_lines)
    # A condition cannot end in the next independently selectable group. Some
    # old files use headings merely to annotate a single compound program.
    commands, current_name = [], None
    for line in raw.splitlines():
        header = re.fullmatch(r"\s*\[([^\]\r\n]+)\]\s*", line)
        if header:
            current_name = header[1].strip()
        command = re.match(r"\s*patch\s*=\s*[01]\s*,\s*(?:EE|IOP)\s*,\s*([0-9A-F]{8})\s*,\s*extended\s*,", line, re.I)
        if command:
            commands.append((int(command[1], 16), current_name))
    for i, (word, group_name) in enumerate(commands):
        op = word >> 28
        # Pointer/copy/slide payload counts need a separate interpreter proof.
        if op in {4, 5, 6}:
            safe_groups = False
        skip = ((word >> 16) & 255) if op == 14 else 1 if op == 13 else 0
        if skip and (i + skip >= len(commands) or any(name != group_name for _, name in commands[i+1:i+skip+1])):
            safe_groups = False
    if safe_groups:
        for name, lines in groups.items():
            body = "\n".join(prefix_lines + lines) + "\n"
            if not re.search(r"(?im)^\s*patch\s*=", body):
                continue
            kind = "graphics" if re.search(r"(?i)wide.?screen|(?:^|\b)(?:60|120)\s*fps|aspect.?ratio", name) else options.get("kind", "gameplay")
            g["cheats"].append(cheat(name, body, "pnach", kind=kind))
    elif re.search(r"(?im)^\s*patch\s*=", raw):
        entry = cheat(options.get("cheat_name", g["title"]), raw, "pnach", kind=options.get("kind", "gameplay"))
        if len(groups) > 1:
            entry.update(status="requires_engine", reason="pnach-group-control-flow-not-proven")
        g["cheats"].append(entry)
    return [g]


def parse_dolphin_ini(data, options):
    raw = text(data)
    gid = options.get("game_id", PurePosixPath(options.get("path", "")).stem)
    game_id = re.fullmatch(r"([A-Z0-9]{6})(?:_?r(\d+))?", gid)
    if not game_id:
        return []  # Global/partial GameINI applies settings, not exact-game cheats.
    gid = game_id[1]
    system = options.get("system", "gc" if gid.startswith(("G", "D")) else "wii")
    header = re.search(r"(?m)^#\s*" + re.escape(gid) + r"(?:r\d+)?\s*-\s*(.+)$", raw)
    g = game(options.get("title", header[1] if header else gid), system, options, [{"type": "game_id", "value": gid, "scheme": "dolphin-disc-game-id"}])
    if game_id[2] is not None:
        g["revision"] = game_id[2]
    section, c = "", None
    for line in raw.splitlines():
        line = line.strip()
        if line.startswith("[") and line.endswith("]"):
            section, c = line[1:-1], None
        elif section in {"ActionReplay", "Gecko"} and line.startswith("$"):
            m = re.match(r"\$(.*?)(?:\s*\[([^]]+)\])?$", line)
            c = cheat(m[1], "", "actionReplay" if section == "ActionReplay" else "gecko", author=m[2] or "", kind=options.get("kind", "gameplay"))
            g["cheats"].append(c)
        elif c is not None and line.startswith("*"):
            c["notes"] = (c.get("notes", "") + "\n" + line[1:]).strip()
        elif c is not None and line and not line.startswith(("#", ";")):
            c["code"] += ("\n" if c["code"] else "") + line
    for c in g["cheats"]:
        for vector in options.get("ar_decryption_vectors", []):
            if (c["dialect"] == "actionReplay" and gid == vector.get("game_id")
                    and vector.get("parity") == 0 and vector.get("crc_valid") is True
                    and c["code"].splitlines() == vector.get("encrypted")):
                c["source_code"] = c["code"]
                c["code"] = "\n".join(vector["decrypted"])
                c["conversion"] = {k: v for k, v in vector.items() if k not in {"encrypted", "decrypted"}}
                break
        if not g["revision"] and re.search(r"(?i)\brev(?:ision)?\s*[.:_-]?\s*\d", c["name"] + "\n" + c.get("notes", "")):
            c.update(status="unresolved", reason="source-revision-restriction-needs-reviewed-game-scope")
    return [g]


def parse_gecko(data, options):
    gid = options.get("game_id", "")
    g = game(options.get("title", gid), options.get("system", "gc" if gid.startswith(("G", "D")) else "wii"), options,
             [{"type": "game_id", "value": options["game_id"], "scheme": "dolphin-disc-game-id"}] if options.get("game_id") else [])
    c = None
    lines = text(data).splitlines()
    for line in lines:
        stripped = line.strip()
        if re.fullmatch(r"[0-9A-Fa-fXY?]{8}\s+[0-9A-Fa-fXY?]{8}", stripped):
            if c is None:
                c = cheat("Untitled program", "", "gecko"); g["cheats"].append(c)
            c["code"] += ("\n" if c["code"] else "") + stripped
        elif not stripped:
            c = None
        elif stripped.startswith(("*", "#")):
            if c:
                c["notes"] = (c.get("notes", "") + "\n" + stripped).strip()
        elif not re.fullmatch(r"[A-Z0-9]{6}", stripped):
            c = cheat(stripped, "", "gecko"); g["cheats"].append(c)
    return [g]


def parse_mupen(data, options):
    result, g, c = [], None, None
    for line in text(data).splitlines():
        m = re.match(r"crc ([0-9A-F]{8})-([0-9A-F]{8})-C:([0-9A-F]{2})", line)
        if m:
            g = game("", "n64", options, [{"type": "n64_header", "value": m[1] + "-" + m[2] + "-C:" + m[3], "scheme": "n64-crc1-crc2-country"}]); result.append(g); c = None
        elif g is not None and line.startswith("gn "):
            g["title"] = line[3:]
        elif g is not None and line.startswith(" cn "):
            c = cheat(line[4:], "", "n64-gameshark"); g["cheats"].append(c)
        elif c is not None and line.startswith("  cd "):
            c["notes"] = line[5:]
        elif c is not None and re.match(r"  [0-9A-F]{8} ", line):
            c["code"] += ("\n" if c["code"] else "") + line.strip()
    return result


def parse_gateshark(data, options):
    system = options.get("system", "3ds")
    tid = options.get("title_id", PurePosixPath(options.get("path", "")).stem)
    ids = [{"type": "title_id", "value": tid.upper(), "scheme": "3ds-title-id"}] if re.fullmatch(r"[a-fA-F0-9]{16}", tid) else []
    g = game(options.get("title", tid), system, options, ids)
    c = None
    for line in text(data).splitlines():
        line = line.strip()
        if line.startswith("[") and line.endswith("]"):
            c = cheat(line[1:-1], "", options.get("dialect", "gateshark")); g["cheats"].append(c)
        elif c is not None and line and not line.startswith(("#", ";")):
            c["code"] += ("\n" if c["code"] else "") + line
    return [g]


def parse_rpcs3_yaml(data, options):
    try:
        import yaml
    except ImportError as exc:
        raise FormatError("RPCS3 import requires PyYAML at regeneration only") from exc
    class RecentAnchorMixin:
        def compose_node(self, parent, index):
            # YAML 1.2 anchors may be reused: an alias refers to the most recent
            # preceding definition. Preserve earlier node objects, update only
            # the lookup for subsequent aliases (PyYAML otherwise rejects it).
            if not self.check_event(yaml.events.AliasEvent):
                event = self.peek_event()
                anchor = getattr(event, "anchor", None)
                if anchor in self.anchors:
                    del self.anchors[anchor]
            return super().compose_node(parent, index)

    class RecentSafeLoader(RecentAnchorMixin, yaml.SafeLoader):
        pass

    class RecentBaseLoader(RecentAnchorMixin, yaml.BaseLoader):
        pass

    raw = re.sub(r"[ \t]+$", "", text(data), flags=re.M)
    safe_loader, base_loader = RecentSafeLoader(raw), RecentBaseLoader(raw)
    try:
        root_node, strings_node = safe_loader.get_single_node(), base_loader.get_single_node()
        if not isinstance(root_node, yaml.nodes.MappingNode):
            raise FormatError("RPCS3 YAML root must be mapping")
        # Read node pairs before constructing dictionaries. Artemis publishes
        # repeated PPU keys and occasionally repeated patch labels; a dict
        # loader silently discards every earlier occurrence of those programs.
        version, entries = 1.2, []
        for (key_node, value_node), (_, string_value) in zip(root_node.value, strings_node.value):
            key = safe_loader.construct_object(key_node, deep=True)
            if key == "Version":
                version = safe_loader.construct_object(value_node, deep=True)
            if not isinstance(key, str) or not re.fullmatch(r"PPU-[a-fA-F0-9]{40}", key) or not isinstance(value_node, yaml.nodes.MappingNode):
                continue
            for (name_node, patch_node), (_, strings_patch_node) in zip(value_node.value, string_value.value):
                name = safe_loader.construct_object(name_node, deep=True)
                patch = safe_loader.construct_object(patch_node, deep=True)
                scalar_patch = base_loader.construct_object(strings_patch_node, deep=True)
                if isinstance(name, str) and isinstance(patch, dict) and isinstance(patch.get("Patch"), list):
                    entries.append((key, name, patch, scalar_patch))
    finally:
        safe_loader.dispose(); base_loader.dispose()
    variants = defaultdict(set)
    for ppu, name, patch, _ in entries:
        try:
            fingerprint = json.dumps(patch, sort_keys=True, allow_nan=False)
            variants[(ppu, name)].add(fingerprint)
        except (ValueError, TypeError):
            pass
    result = []
    def native_rows(rows, source_rows, depth=0):
        # RPCS3's pinned add_patch_data recursively expands load anchors. A
        # zero modifier preserves addresses/order; nonzero modifiers need a
        # separate reviewed conversion. Original hexadecimal scalar spelling
        # is necessary: the core rejects decimal address strings.
        if depth > 64 or not isinstance(rows, list) or not isinstance(source_rows, list) or len(rows) != len(source_rows):
            raise FormatError("unsupported-rpcs3-load-or-address")
        result = []
        for row, original in zip(rows, source_rows):
            if not isinstance(row, list) or not isinstance(original, list):
                raise FormatError("unsupported-rpcs3-load-or-address")
            if len(row) in {2, 3} and str(row[0]).lower() == "load":
                if len(row) == 3 and str(row[2]).lower() not in {"0", "0x0", "0x00000000"}:
                    raise FormatError("rpcs3-nonzero-load-modifier-needs-reviewed-conversion")
                result.extend(native_rows(row[1], original[1], depth + 1))
            elif (len(row) == 3 and len(original) == 3 and re.fullmatch(r"0x[0-9a-fA-F]{1,64}", str(original[1]))
                  and int(str(original[1]), 16) <= 0xFFFFFFFF):
                result.append([row[0], "0x" + format(int(str(original[1]), 16), "X"), row[2]])
            else:
                raise FormatError("unsupported-rpcs3-load-or-address")
        return result

    for ppu, source_name, patch, scalar_patch in entries:
        try:
            payload = json.dumps(patch, sort_keys=True, allow_nan=False)
            name = source_name
            if len(variants[(ppu, source_name)]) > 1:
                import hashlib
                name += " [source variant " + hashlib.sha256(payload.encode()).hexdigest()[:12] + "]"
            conversion_error = ""
            try:
                patch = {**patch, "Patch": native_rows(patch["Patch"], scalar_patch["Patch"])}
            except FormatError as exc:
                conversion_error = str(exc)
            games = patch.get("Games", {})
            for title, serials in games.items():
                if not isinstance(serials, dict):
                    continue
                for serial, versions in serials.items():
                    # Keep version scalar text: unquoted 01.01 is not 1.01.
                    versions = scalar_patch["Games"][str(title)][str(serial)]
                    for release in versions if isinstance(versions, list) else [versions]:
                        ids = [{"type": "ppu_hash", "value": ppu[4:], "scheme": "rpcs3-ppu-hash"},
                               {"type": "serial", "value": serial, "scheme": "ps3-title-id"}]
                        all_versions = str(release).lower() == "all"
                        g = game(str(title), "ps3", {**options, "revision": "" if all_versions else str(release)}, ids)
                        if all_versions:
                            g["version_scope"] = "all"
                        if not re.fullmatch(r"[A-Z]{4}\d{5}", str(serial)):
                            g.update(status="requires_engine", reason="rpcs3-patch-without-exact-title-serial")
                        document = {"Version": version, ppu: {name: {**patch, "Games": {title: {serial: [release]}}}}}
                        json.dumps(document, allow_nan=False)
                        code = yaml.safe_dump(document, sort_keys=False, allow_unicode=True)
                        g["cheats"].append(cheat(name, code, "rpcs3-yaml", native_document=document, source_name=source_name,
                            author=patch.get("Author", "") or "", notes=patch.get("Notes", "") or "",
                            exclusive_group=patch.get("Group", "") or "", kind=options.get("kind", "gameplay")))
                        if options.get("authored_ncl_provenance"):
                            import hashlib
                            document_hash = hashlib.sha256(json.dumps(document, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()
                            g["cheats"][-1]["provenance"] = options["authored_ncl_provenance"].get(document_hash, [])
                        if conversion_error:
                            g["cheats"][-1].update(status="requires_engine", reason=conversion_error)
                        result.append(g)
        except (ValueError, TypeError, KeyError, AttributeError) as exc:
            failed = game(str(source_name), "ps3", options)
            failed["import_error"] = "invalid-rpcs3-patch: " + str(exc)[:200]
            result.append(failed)

    return result


PARSERS = {
    "openemu-xml": parse_openemu, "mesen-json": parse_mesen,
    "nestopia-xml": parse_mighty_mo, "bsnes-bml": parse_bml,
    "usrcheat-dat": parse_usrcheat, "cwcheat-db": parse_cwcheat,
    "retroarch-cht": parse_retroarch, "duckstation-cht": parse_duckstation,
    "pnach": parse_pnach, "dolphin-ini": parse_dolphin_ini,
    "gecko-txt": parse_gecko, "mupen-txt": parse_mupen,
    "gateshark-txt": parse_gateshark, "rpcs3-yaml": parse_rpcs3_yaml,
}
