#!/usr/bin/env python3
"""Lossless data import for reserved native dialects, never activation by ABI.

Future-platform data remains requires_engine. This is deliberately separate
from the bounded adapters whose execution has been reviewed in NeoStation.
"""
import io
import json
import re
import tarfile
import zipfile
from pathlib import PurePosixPath

from unified_formats import FormatError, cheat, game, text


def parse_vita(data, options):
    raw = text(data)
    name = re.search(r"(?im)^#\s*Title\s*:\s*(.+)", raw)
    version = re.search(r"(?im)^#\s*Version\s*:\s*(.+)", raw)
    tid = re.search(r"PC[A-Z]{2}\d{5}", options.get("path", "") + "\n" + raw[:2000])
    ids = [{"type": "serial", "value": tid[0], "scheme": "vita-title-id"}] if tid else []
    g = game(name[1] if name else (tid[0] if tid else options.get("title", "Vita codes")), "vita", options, ids)
    if version:
        g["revision"] = version[1].strip()
    c = None
    for line in raw.splitlines():
        line = line.strip()
        if re.match(r"_V[01]\s", line):
            c = cheat(line[4:], "", "vitacheat", status="requires_engine", reason="vitacheat-plugin-interpreter-not-integrated")
            g["cheats"].append(c)
        elif c is not None and line.startswith("$"):
            c["code"] += ("\n" if c["code"] else "") + line
    return [g]


def switch_identity(path, options):
    tid = options.get("title_id", "")
    bid = options.get("build_id", "")
    parts = PurePosixPath(path).parts
    for n, part in enumerate(parts):
        if re.fullmatch(r"[a-fA-F0-9]{16}", part) and (n + 1 < len(parts) and parts[n + 1] == "cheats"):
            tid = part
    stem = PurePosixPath(path).stem
    if re.fullmatch(r"[a-fA-F0-9]{16}", stem):
        bid = bid or stem
    return [{"type": typ, "value": value.upper(), "scheme": scheme}
            for typ, value, scheme in (("title_id", tid, "switch-title-id"), ("build_id", bid, "switch-nso-build-id")) if value]


def parse_atmosphere(data, options):
    path = options.get("path", "")
    g = game(options.get("title", PurePosixPath(path).stem), "switch", options, switch_identity(path, options))
    c = None
    for line in text(data).splitlines():
        line = line.strip()
        if line.startswith(("[", "{")) and line.endswith(("]", "}")):
            c = cheat(line[1:-1], "", "atmosphere", status="requires_engine", reason="switch-atmosphere-interpreter-not-integrated", kind=options.get("kind", "gameplay"))
            g["cheats"].append(c)
        elif c is not None and line and not line.startswith(("#", ";")):
            c["code"] += ("\n" if c["code"] else "") + line
    return [g]


def parse_switch_json(data, options):
    root = json.loads(text(data)); result = []
    tid = options.get("title_id", PurePosixPath(options.get("path", "")).stem)
    if not re.fullmatch(r"[a-fA-F0-9]{16}", tid):
        raise FormatError("Switch JSON requires exact TitleID")
    for bid, entry in root.items():
        if not re.fullmatch(r"[a-fA-F0-9]{16}", bid):
            continue  # attribution is metadata, never a BuildID/code.
        if not isinstance(entry, dict):
            continue
        options = {**options, "title_id": tid, "build_id": bid}
        g = game(options.get("title", tid), "switch", options, switch_identity("", options))
        for name, instructions in entry.items():
            code = "\n".join(instructions) if isinstance(instructions, list) else instructions
            if not isinstance(code, str):
                continue
            g["cheats"].append(cheat(name, code, "atmosphere", status="requires_engine", reason="switch-atmosphere-interpreter-not-integrated", attribution=root.get("attribution", {})))
        result.append(g)
    return result


def parse_artemis_ncl(data, options):
    raw = text(data)
    path = options.get("path", "")
    serial = re.search(r"[BN][A-Z]{3}\d{5}", path + "\n" + raw[:1000])
    version = re.search(r"(?i)(?:v|ver(?:sion)?\s*[:=]?)\s*(\d+\.\d+)", path + "\n" + raw[:1000])
    ids = [{"type": "serial", "value": serial[0], "scheme": "ps3-title-id"}] if serial else []
    g = game(PurePosixPath(path).stem, "ps3", options, ids)
    if version:
        g["revision"] = version[1]
    # NCL's block/program metadata, variables and instructions remain together.
    # Renaming this text to YAML would silently change its semantics.
    g["cheats"].append(cheat(g["title"], raw, "artemis-ncl", status="requires_engine", reason="artemis-semantic-conversion-required"))
    return [g]


def parse_cheatdevice_ps2(data, options):
    raw = text(data); result = []; g = c = None
    for line in raw.splitlines():
        line = line.strip()
        if not line or line.startswith(("//", "#")):
            continue
        if line.startswith('"') and line.endswith('"'):
            g = game(line[1:-1], "ps2", options)
            serial = re.search(r"[A-Z]{4}[-_]?\d{5}", line)
            if serial:
                g["identities"] = [{"type": "serial", "value": serial[0].replace("_", "-"), "scheme": "ps2-disc-serial"}]
            result.append(g); c = None
        elif g is not None and re.fullmatch(r"[0-9A-Fa-f]{8}\s+[0-9A-Fa-f?]{8}", line):
            if c is not None:
                c["code"] += ("\n" if c["code"] else "") + line
        elif g is not None:
            c = cheat(line, "", "ps2-raw", status="requires_engine", reason="raw-ps2-semantic-conversion-required")
            g["cheats"].append(c)
    return result


def parse_dreamcast_markdown(data, options):
    raw = text(data)
    g = game(options.get("title", PurePosixPath(options.get("path", "")).stem), "dc", options)
    for n, block in enumerate(re.findall(r"```[^\n]*\n(.*?)```", raw, re.S), 1):
        if re.search(r"(?im)^\s*[a-f0-9]{8}\s+[a-f0-9]{8}\s*$", block):
            g["cheats"].append(cheat(f"Source program {n}", block, "dreamcast-codebreaker", status="requires_engine", reason="flycast-dialect-not-reviewed", kind=options.get("kind", "gameplay")))
    result = [g] if g["cheats"] else []
    for line in raw.splitlines():
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) < 7 or cells[1] not in {"NA", "EU", "JP"}:
            continue
        code = cells[-1]
        if not re.search(r"(?i)\b[0-9A-F]{7,8}\s+[0-9A-F]{8}\b", code):
            continue
        region = {"NA": "USA", "EU": "Europe", "JP": "Japan"}[cells[1]]
        item = game(cells[0] + " (" + region + ")", "dc", options)
        # Retain the author's notes/commas and even malformed 7-digit words;
        # no zero-padding or invented native compatibility.
        item["cheats"].append(cheat("Widescreen / FPS source code", code, "dreamcast-codebreaker", status="requires_engine", reason="flycast-source-dialect-and-revision-not-reviewed", kind="graphics"))
        result.append(item)
    return result


def parse_mister_zip(data, options):
    path = options.get("path", "")
    match = re.search(r"([^/]+)\s+\[([A-Fa-f0-9]{8})\]\.zip$", path)
    title = match[1] if match else PurePosixPath(path).stem
    folders = {"Gameboy": "gb", "GameBoy": "gb", "GBA": "gba", "NES": "nes", "SNES": "snes", "Genesis": "md", "MegaDrive": "md", "GameGear": "gg", "MasterSystem": "sms", "PSX": "psx", "AtariLynx": "lynx"}
    system = next((sid for folder, sid in folders.items() if "/" + folder + "/" in path), "unknown")
    ids = [{"type": "crc32", "value": match[2].upper(), "scheme": "mister-source-crc"}] if match else []
    g = game(title, system, options, ids)
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        if len(archive.infolist()) > 20000:
            raise FormatError("MiSTer nested archive has too many programs")
        for info in archive.infolist():
            if not info.filename.endswith(".gg") or info.is_dir():
                continue
            member = PurePosixPath(info.filename)
            if member.is_absolute() or ".." in member.parts or info.file_size > 128 * 1024:
                continue
            raw = archive.read(info)
            if not raw or len(raw) % 16:
                continue
            # Native 128-bit MiSTer tuples retain flag/address/compare/write
            # words verbatim; they are NOT renamed to RetroArch handler-0.
            code = "\n".join(raw[n:n+16].hex().upper() for n in range(0, len(raw), 16))
            g["cheats"].append(cheat(member.stem, code, "mister-native-tuples", status="requires_engine", reason="mister-flag-aware-semantic-conversion-required", notes=archive.comment.decode("utf-8", errors="replace")))
    return [g]


def parse_cemu_archive(data, options):
    packages = {}
    with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as archive:
        for member in archive:
            if not member.isfile() or "/Cheats/" not in member.name or not member.name.endswith(".txt"):
                continue
            p = PurePosixPath(member.name)
            if p.is_absolute() or ".." in p.parts or member.size > 2 * 1024 * 1024:
                continue
            # One folder is one self-contained native Cemu graphic pack.
            folder = str(p.parent)
            packages.setdefault(folder, {})[p.name] = text(archive.extractfile(member).read())
    result = []
    for folder, files in sorted(packages.items()):
        rules = files.get("rules.txt")
        if not rules:
            continue
        ids = re.search(r"(?im)^\s*titleIds\s*=\s*(.+)$", rules)
        tids = re.findall(r"\b[0-9a-fA-F]{16}\b", ids[1]) if ids else []
        matches = sorted({m.upper() for f in files.values() for m in re.findall(r"(?i)moduleMatches\s*=\s*([^\n]+)", f) for m in re.findall(r"0x([0-9a-fA-F]{8})", m)})
        title = re.search(r"(?im)^\s*name\s*=\s*(.+)$", rules)
        code = "\n\n".join(f"# FILE {name}\n{body}" for name, body in sorted(files.items()))
        if len(code) > 256 * 1024:
            continue
        for tid in tids:
            identities = [{"type": "title_id", "value": tid.upper(), "scheme": "wiiu-title-id"}]
            identities.extend({"type": "wiiu_module_hash", "value": m, "scheme": "cemu-module-matches"} for m in matches)
            g = game(title[1] if title else PurePosixPath(folder).name, "wiiu", options, identities)
            g["cheats"].append(cheat(g["title"], code, "cemu-patch", status="requires_engine", reason="cemu-patch-adapter-not-reviewed", native_document={"files": files}))
            result.append(g)
    return result


PARSERS = {"vitacheat-psv": parse_vita, "atmosphere-txt": parse_atmosphere,
           "atmosphere-json": parse_switch_json, "artemis-ncl": parse_artemis_ncl,
           "cheatdevice-ps2": parse_cheatdevice_ps2, "dreamcast-markdown": parse_dreamcast_markdown,
           "cemu-archive": parse_cemu_archive, "mister-zip": parse_mister_zip}
