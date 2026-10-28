"""Rebuilds the code fields of a published program from its origin file.

A program of a source RewindBox does not host keeps everything but its code
fields (code, lines, source_code). Its recipe says where the code is in the
source's own file:

  {"m": <origin member index>, "r": [[start, end], "\n", [start, end, "x"], ...], "n": "plus"?}

Each range is a byte slice of the member, decoded with the member's encoding
and optionally transformed (TRANSFORMS); a string is a separator the
importer put between pieces (only SEPARATORS, never code). The pieces
concatenated are the program as the importer read it. The
fields are then derived exactly as unified_catalogue.review_program derives
them for an available program. This module is the reference for the app's
port (packages/neo_cheat_catalog/lib/src/origin_recipe.dart): both are tested
against every published program.
"""
import re

# unified_catalogue.SIMPLE_PATTERNS keys and the paired-word dialects whose
# code review_program rewrites to the normalised lines.
SIMPLE = {"nes-gamegenie", "nes-raw", "snes-gamegenie", "snes-par", "gb-gameshark", "gb-gamegenie",
          "md-gamegenie", "md-raw", "sega8-gamegenie", "sega8-raw"}
PAIRED = {"ds-actionreplay", "ps1-gameshark", "gba-gameshark-v1", "gba-gameshark-v3", "gba-codebreaker",
          "gba-unknown", "gba-auto", "n64-gameshark", "gateshark", "ctrpf", "gecko", "actionReplay"}
NORMALISED = SIMPLE | {"ds-actionreplay", "ps1-gameshark", "gba-gameshark-v1", "gba-gameshark-v3",
                       "gba-codebreaker", "gba-auto", "gba-vba-raw", "n64-gameshark", "cwcheat", "pce-raw", "wswan-raw"}
SEPARATORS = re.compile(r"[+;,\s]+")
# Separator literals a recipe may carry: punctuation, never code content.
LITERALS = {"\n", ":", "?", "+"}
# Text transforms of the importers, by recipe code.
TRANSFORMS = {
    # unified_formats.parse_mighty_mo: findtext().replace("0x", "").strip().upper()
    "x": lambda value: value.replace("0x", "").strip().upper(),
}


def decode(data, encoding):
    text = data.decode("cp1252" if encoding == "cp1252" else "utf-8")
    return text


def program_lines(code, dialect):
    """unified_catalogue.program_lines for the dialects of origin programs."""
    if dialect in {"pnach", "rpcs3-yaml", "ps3-static-be32"}:
        return code.splitlines()
    if dialect in SIMPLE or dialect == "gba-vba-raw":
        return [p.upper() for p in SEPARATORS.split(code) if p]
    if dialect in {"pce-raw", "wswan-raw"}:
        lines = [p.upper() for p in SEPARATORS.split(code) if p]
        if dialect == "wswan-raw":
            lines = [f"{int(p.split(':')[0], 16):04X}:" + p.split(':')[1]
                     if re.fullmatch(r"[0-9A-F]{1,8}:[0-9A-F]{2}", p) and int(p.split(':')[0], 16) <= 0xFFFF else p
                     for p in lines]
        return lines
    if dialect == "cwcheat":
        return [line.upper().replace("0X", "") for line in code.splitlines() if line.strip()]
    if dialect in PAIRED:
        tokens = [s for s in SEPARATORS.split(code.upper()) if s]
        if dialect == "n64-gameshark":
            tokens = [s[2:] if s.startswith("0X") else s for s in tokens]
        width = 4 if dialect in {"ps1-gameshark", "n64-gameshark", "gba-codebreaker"} else 8
        whole = r"(?:[A-F0-9]{12}|[A-F0-9]{16})" if dialect == "gba-auto" else r"[A-F0-9]{" + str(8 + width) + r"}"
        lines, n = [], 0
        while n < len(tokens):
            token = tokens[n]
            if re.fullmatch(whole, token):
                lines.append(token[:8] + " " + token[8:]); n += 1
            elif n + 1 < len(tokens):
                lines.append(token + " " + tokens[n + 1]); n += 2
            else:
                lines.append(token); n += 1
        return lines
    return code.splitlines()


def derive(raw, dialect, plus=False, source_code=None, drop=False):
    """The code fields review_program gives an available program read as `raw`.
    `drop`: the importer normalised the code itself and kept no source_code."""
    lines = program_lines(raw, dialect)
    code = raw.strip()
    fields = {"code": code, "lines": lines}
    if source_code is not None:
        fields["source_code"] = source_code
    if dialect == "cwcheat" and code != "\n".join(lines):
        fields["source_code"] = code
        fields["code"] = code = "\n".join(lines)
    if dialect in NORMALISED:
        normalised = "+".join(p.replace(" ", "") for p in lines) if plus else "\n".join(lines)
        if code != normalised:
            fields.setdefault("source_code", code)
            fields["code"] = normalised
    if drop:
        fields.pop("source_code", None)
    return fields


def raw_text(recipe, members):
    """The program text a recipe designates in the origin members
    (list of (bytes, encoding))."""
    data, encoding = members[recipe["m"]]
    parts = []
    for item in recipe["r"]:
        if isinstance(item, str):
            if item not in LITERALS:
                raise ValueError("recipe literal is not a separator")
            parts.append(item)
            continue
        value = decode(data[item[0]:item[1]], encoding)
        if len(item) > 2:
            value = TRANSFORMS[item[2]](value)
        parts.append(value)
    return "".join(parts)


def rebuild(recipe, members, dialect):
    """The code fields of one program from its recipe and the origin members."""
    return derive(raw_text(recipe, members), dialect, plus=recipe.get("n") == "plus", drop=recipe.get("d") == 1)


def mister(raw, system):
    """unified_adapt.convert_mister_program for a converted (available)
    program: (code, dialect, source_code), or None when the program is one
    the importer kept as native tuples."""
    import struct
    if not raw or len(raw) % 16 or len(raw) > 128 * 1024:
        return None
    rows = list(struct.iter_unpack("<IIII", raw))
    if (system == "nes" and len(rows) > 100) or (system == "gba" and len(rows) > 128):
        return None
    lines, addresses = [], set()
    if system == "nes":
        for flags, address, compare, value in rows:
            if flags not in (0, 1) or not 0x8000 <= address <= 0xFFFF or value > 0xFF or compare > 0xFF:
                return None
            if address in addresses:
                return None
            addresses.add(address)
            lines.append(f"{address:04X}?{compare:02X}:{value:02X}" if flags else f"{address:04X}:{value:02X}")
        dialect = "nes-raw"
    elif system == "psx":
        for index, (flags, address, compare, value) in enumerate(rows):
            offset = address & 0x1FFFFFFF
            operation, mask = flags & 15, flags & 0xF0
            if (flags > 255 or mask not in (0x10, 0x20, 0x30) or operation not in (0, 1, 2, 6)
                    or address >> 24 not in (0x00, 0x80, 0xA0) or offset >= 0x200000 or offset % 2):
                return None
            width = 2 if mask == 0x30 else 1
            if mask == 0x20:
                if value > 0xFFFF or value & 0xFF:
                    return None
                offset += 1
                value >>= 8
            if value >= 1 << (8 * width) or offset % width or offset + width > 0x200000:
                return None
            if operation:
                if index + 1 >= len(rows) or rows[index + 1][0] & 15:
                    return None
                opcode = (0xE0 if width == 1 else 0xD0) + {1: 0, 2: 3, 6: 1}[operation]
            else:
                if any(offset + byte in addresses for byte in range(width)):
                    return None
                addresses.update(range(offset, offset + width))
                opcode = 0x30 if width == 1 else 0x80
            lines.append(f"{(opcode << 24) | offset:08X} {value:04X}")
        dialect = "ps1-gameshark"
    elif system == "gba":
        for flags, address, _, value in rows:
            if (not flags or flags & ~0xF0 or address % 4
                    or not (0x02000000 <= address <= 0x0203FFFC or 0x03000000 <= address <= 0x03007FFC)):
                return None
            for lane in range(4):
                if flags & (0x10 << lane):
                    lines.append(f"{address + lane:08X}:{(value >> (8 * lane)) & 0xFF:02X}")
        dialect = "gba-vba-raw"
    else:
        return None
    source = "\n".join(raw[n:n + 16].hex().upper() for n in range(0, len(raw), 16))
    return "\n".join(lines), dialect, source


def rebuild_mister(recipe, data, dialect):
    """Code fields of a MiSTer program: `data` is its .gg member."""
    converted = mister(data, recipe["s"])
    if converted is None or converted[1] != dialect:
        raise ValueError("mister program does not convert")
    code, _, source = converted
    return derive(code, dialect, plus=recipe.get("n") == "plus", source_code=source)


FBNEO_QUOTED = r'"((?:[^"\\]|\\.)*)"'


def _fbneo_integer(value):
    """unified_extended._native_integer (C strtol base 0)."""
    return int(value, 16 if value.lower().startswith("0x") else 8 if len(value) > 1 and value.startswith("0") else 10)


def fbneo(raw):
    """Code fields of an available FBNeo block (unified_extended.parse_fbneo_ini):
    the block's stripped lines, its choices and native document."""
    choices, default = [], None
    for line in raw.split("\n")[1:]:
        match = re.fullmatch(r"default\s+(\d+)", line)
        if match:
            default = _fbneo_integer(match[1])
            continue
        choice = re.fullmatch(r"(\d+)\s+" + FBNEO_QUOTED + r"(?:\s*,\s*(.*))?", line)
        if not choice:
            raise ValueError("not an available FBNeo block")
        values = [word.strip() for word in choice[3].split(",")] if choice[3] else []
        writes = [{"cpu": _fbneo_integer(values[n]), "address": values[n + 1], "value": values[n + 2]}
                  for n in range(0, len(values) - len(values) % 3, 3)]
        name = choice[2].replace('\\"', '"').replace("\\\\", "\\")
        choices.append({"index": _fbneo_integer(choice[1]), "name": name, "writes": writes})
    return {"code": raw, "lines": raw.splitlines(), "choices": choices,
            "native_document": {"source_default": default, "import_default": 0, "choices": choices}}
