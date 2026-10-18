#!/usr/bin/env python3
"""Build/validate the single downloadable NeoStation cheat source.

Usage: unified_catalogue.py build --sources tools/cheats/unified-sources.json
       --output native/cheats/catalogue --cache /path/to/cache [--offline]

Only regeneration needs network/PyYAML. The iOS consumer reads verified JSON
and gzip packs. Source failures are isolated and recorded in the manifest.
"""
from __future__ import annotations

import argparse
import base64
import concurrent.futures
import fnmatch
import gzip
import hashlib
import io
import inspect
import json
import os
import re
import sqlite3
import sys
import tarfile
import tempfile
import urllib.error
import urllib.request
import zipfile
import zlib
from collections import Counter
from pathlib import Path, PurePosixPath

from unified_formats import PARSERS, FormatError, MAX_INPUT

SCHEMA = 1
MAX_CHUNK = 2 * 1024 * 1024
PACK_TARGET = 4 * 1024 * 1024
MAX_PACK_RAW = 16 * 1024 * 1024
MAX_PACK_GZIP = 8 * 1024 * 1024
MAX_ARCHIVE_ENTRIES = 100000
SUPPORTED = {"nes", "snes", "gb", "gbc", "gba", "md", "sms", "gg", "mcd", "nds", "psx", "ps2", "ps3", "gc", "wii", "psp", "n64", "arcade", "32x", "pico", "pce", "pccd", "tg16", "tgcd", "ws", "wsc"}
SIMPLE_PATTERNS = {
    "nes-gamegenie": r"(?:[APZLGITYEOXUKSVN]{6}|[APZLGITYEOXUKSVN]{8})",
    "nes-raw": r"(?:[0-9A-F]{8}|[0-9A-F]{4}(?:\?[0-9A-F]{2})?:[0-9A-F]{2})",
    "snes-gamegenie": r"[0-9A-F]{4}-[0-9A-F]{4}",
    "snes-par": r"(?:[0-9A-F]{8}|[0-9A-F]{6}:[0-9A-F]{2})",
    "gb-gameshark": r"[0-9A-F]{8}",
    "gb-gamegenie": r"[0-9A-F]{3}-[0-9A-F]{3}(?:-[0-9A-F]{3})?",
    "md-gamegenie": r"[0-9ABCDEFGHJKLMNPRSTVWXYZ]{4}-[0-9ABCDEFGHJKLMNPRSTVWXYZ]{4}",
    "md-raw": r"[0-9A-F]{6}:[0-9A-F]{4}",
    "sega8-gamegenie": r"[0-9A-F]{3}-[0-9A-F]{3}-[0-9A-F]{3}",
    "sega8-raw": r"[0-9A-F]{6}:[0-9A-F]{2}",
}


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8") + b"\n"


def sha(data):
    return hashlib.sha256(data).hexdigest()


def gzip_bytes(data):
    """Stable header on Linux/macOS: no filename, no clock, OS byte 255."""
    stream = io.BytesIO()
    with gzip.GzipFile(fileobj=stream, filename="", mode="wb", compresslevel=9, mtime=0) as output:
        output.write(data)
    return stream.getvalue()


def reusable_packs(directory):
    """Bounded local cache keyed by exact expanded bytes, never by a title.

    Reusing a pack changes no JSON byte or compression header. Every cache
    candidate must first pass the previously published size/hash/expansion
    checks; the ordinary final validator still checks the resulting catalogue.
    """
    result = {}
    try:
        index = directory / "manifest.json.gz"
        if index.stat().st_size > 12 * 1024 * 1024:
            return result
        with gzip.GzipFile(fileobj=io.BytesIO(index.read_bytes())) as stream:
            raw = stream.read(64 * 1024 * 1024 + 1)
        if len(raw) > 64 * 1024 * 1024:
            return result
        manifest = json.loads(raw)
        for pack in manifest.get("packs", []):
            path = directory / str(safe_path(pack["path"]))
            if path.stat().st_size != pack["size"] or pack["size"] > MAX_PACK_GZIP:
                continue
            data = path.read_bytes()
            if sha(data) != pack["sha256"] or data[:10] != b"\x1f\x8b\x08\x00\x00\x00\x00\x00\x02\xff":
                continue
            with gzip.GzipFile(fileobj=io.BytesIO(data)) as stream:
                expanded = stream.read(MAX_PACK_RAW + 1)
            if len(expanded) != pack["uncompressed_size"] or len(expanded) > MAX_PACK_RAW:
                continue
            result[sha(expanded)] = path
    except (OSError, EOFError, zlib.error, ValueError, KeyError, TypeError, FormatError):
        # A missing or damaged cache cannot remove otherwise valid sources.
        pass
    return result


def atomic(path, data):
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp = tempfile.mkstemp(prefix=".new-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
        os.replace(temp, path)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)


def safe_path(value):
    p = PurePosixPath(value)
    if not value or p.is_absolute() or ".." in p.parts or "\\" in value or ":" in value or value != str(p):
        raise FormatError("unsafe relative catalogue path")
    return p


def fetch(source, cache, offline=False, base=Path(".")):
    expected = source.get("sha256", "")
    local = source.get("local_path")
    if local:
        path = Path(local)
        if not path.is_absolute():
            path = base / path
        if path.exists():
            data = path.read_bytes()
            if expected and sha(data) != expected:
                raise FormatError("local source SHA-256 mismatch")
            return data
    if not re.fullmatch(r"[a-f0-9]{64}", expected):
        raise FormatError("source requires a pinned SHA-256")
    path = cache / (expected + ".source")
    if path.exists():
        data = path.read_bytes()
        if sha(data) == expected:
            return data
        path.unlink()
    if offline:
        raise FormatError("pinned input absent from offline cache")
    url = source.get("download_url", source.get("url", ""))
    if not url.startswith("https://"):
        raise FormatError("source download must use HTTPS")
    request = urllib.request.Request(url, headers={"User-Agent": "NeoStation-Cheat-Catalogue/1", "Accept-Encoding": "identity"})
    limit = min(512 * 1024 * 1024, int(source.get("max_download_bytes", MAX_INPUT)))
    with urllib.request.urlopen(request, timeout=120) as stream:
        data = stream.read(limit + 1)
    if len(data) > limit:
        raise FormatError("source exceeds bounded download size")
    if sha(data) != expected:
        raise FormatError("download SHA-256 mismatch")
    atomic(path, data)
    return data


def archive_members(data, kind, errors=None, wanted=None):
    def accepted(name):
        p = PurePosixPath(name)
        if p.is_absolute() or ".." in p.parts or "\\" in name or "\0" in name or re.match(r"^[A-Za-z]:[/\\]", name):
            if errors is not None:
                errors.append({"path": name[:300], "reason": "unsafe-archive-member"})
            return False
        return wanted is None or wanted(name)
    total = 0
    if kind == "zip":
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            entries = archive.infolist()
            if len(entries) > MAX_ARCHIVE_ENTRIES:
                raise FormatError("archive contains too many entries")
            for entry in entries:
                if entry.is_dir():
                    continue
                if not accepted(entry.filename):
                    continue
                total += entry.file_size
                if entry.file_size > MAX_INPUT or total > 1024 * 1024 * 1024:
                    raise FormatError("archive expansion limit")
                yield entry.filename, archive.read(entry)
    elif kind == "tar.gz":
        with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as archive:
            for n, entry in enumerate(archive):
                if n >= MAX_ARCHIVE_ENTRIES:
                    raise FormatError("archive contains too many entries")
                if not entry.isfile():
                    continue
                if not accepted(entry.name):
                    continue
                total += entry.size
                if entry.size > MAX_INPUT or total > 1024 * 1024 * 1024:
                    raise FormatError("archive expansion limit")
                yield entry.name, archive.extractfile(entry).read()
    else:
        raise FormatError("unsupported archive type")


def parse_source(source, data):
    options = dict(source.get("options", {}))
    if source.get("system"):
        options.setdefault("system", source["system"])
    if source.get("archive"):
        result, errors = [], []
        rules = source.get("members", [])
        def matching(path, rule):
            return fnmatch.fnmatchcase(path, rule.get("glob", "*")) and (not rule.get("regex") or re.fullmatch(rule["regex"], path))
        for path, member in archive_members(data, source["archive"], errors, lambda path: any(matching(path, r) for r in rules)):
            for rule in source.get("members", []):
                if matching(path, rule):
                    merged = {**options, **rule.get("options", {}), "path": path}
                    if rule.get("system"):
                        merged["system"] = rule["system"]
                    if rule.get("title_from_filename"):
                        merged["title"] = PurePosixPath(path).stem
                    if rule.get("game_id_from_filename"):
                        merged["game_id"] = PurePosixPath(path).stem
                    if options.get("identities_by_title"):
                        title_key = re.sub(r"\s+", " ", re.sub(r"(?i)\s*\((?:Game Genie|GameShark|Game Shark|Action Replay|Pro Action Replay|Game Buster|Xploder|CodeBreaker|Code Breaker)\)", "", merged.get("title", "")).strip().lower())
                        merged["identities"] = options["identities_by_title"].get(merged.get("system", "") + ":" + title_key, [])
                    fmt = rule.get("format", source.get("format"))
                    try:
                        result.extend(PARSERS[fmt](member, merged))
                    except Exception as exc:
                        errors.append({"path": path, "reason": str(exc)[:300]})
                    break
        return result, errors
    return PARSERS[source["format"]](data, options), []


def struct_error():
    import struct
    return struct.error


def program_lines(code, dialect):
    if dialect in {"pnach", "rpcs3-yaml"}:
        return code.splitlines()
    if dialect in SIMPLE_PATTERNS:
        return [p.upper() for p in re.split(r"[+;,\s]+", code) if p]
    if dialect == "gba-vba-raw":
        return [p.upper() for p in re.split(r"[+;,\s]+", code) if p]
    if dialect in {"pce-raw", "wswan-raw"}:
        lines = [p.upper() for p in re.split(r"[+;,\s]+", code) if p]
        if dialect == "wswan-raw":
            lines = [f"{int(p.split(':')[0], 16):04X}:" + p.split(':')[1]
                if re.fullmatch(r"[0-9A-F]{1,8}:[0-9A-F]{2}", p) and int(p.split(':')[0], 16) <= 0xFFFF else p for p in lines]
        return lines
    if dialect == "cwcheat":
        return [line.upper().replace("0X", "") for line in code.splitlines() if line.strip()]
    # Preserve a whole Action Replay program, including payload data. Tokenize
    # paired words, never split a conditional away from its following writes.
    if dialect in {"ds-actionreplay", "ps1-gameshark", "gba-gameshark-v1", "gba-gameshark-v3", "gba-codebreaker", "gba-unknown", "gba-auto", "n64-gameshark", "gateshark", "ctrpf", "gecko", "actionReplay"}:
        tokens = [s for s in re.split(r"[+;,\s]+", code.upper()) if s]
        if dialect == "n64-gameshark":
            tokens = [s[2:] if s.startswith("0X") else s for s in tokens]
        width = 4 if dialect in {"ps1-gameshark", "n64-gameshark", "gba-codebreaker"} else 8
        lines, n = [], 0
        while n < len(tokens):
            token = tokens[n]
            if re.fullmatch(r"(?:[A-F0-9]{12}|[A-F0-9]{16})" if dialect == "gba-auto" else r"[A-F0-9]{" + str(8 + width) + r"}", token):
                lines.append(token[:8] + " " + token[8:]); n += 1
            elif n + 1 < len(tokens):
                lines.append(token + " " + tokens[n + 1]); n += 2
            else:
                lines.append(token); n += 1
        return lines
    return code.splitlines()


def pico_md_decode(code):
    """Math counterpart of test/unified_native_picodrive_decode.h (1890c29).

    The header is differentially tested against the shipped core's real
    decoder. No SH2 address projection or odd-word repair is performed.
    """
    if re.fullmatch(r"[0-9A-F]{6}:[0-9A-F]{4}", code):
        left, right = code.split(":")
        return int(left, 16), int(right, 16)
    alphabet = "ABCDEFGHJKLMNPRSTVWXYZ0123456789"
    if not re.fullmatch(r"[" + alphabet + r"]{4}-[" + alphabet + r"]{4}", code):
        return None
    address, value = 0, 0
    for index, char in enumerate(code):
        if index == 4:
            continue
        n = alphabet.index(char)
        if index == 0: value |= n << 3
        elif index == 1: value |= n >> 2; address |= (n & 3) << 14
        elif index == 2: address |= n << 9
        elif index == 3: address |= ((n & 15) << 20) | ((n >> 4) << 8)
        elif index == 5: value |= (n & 1) << 12; address |= (n >> 1) << 16
        elif index == 6: value |= ((n & 1) << 15) | ((n >> 1) << 8)
        elif index == 7: value |= (n >> 3) << 13; address |= (n & 7) << 5
        elif index == 8: address |= n
    return address, value


def pico_program_allowed(lines, system):
    if system not in {"32x", "pico", "md", "mcd"} or len("+".join(lines)) > 8192:
        return False
    for line in lines:
        decoded = pico_md_decode(line)
        if not decoded:
            return False
        address, value = decoded
        if address & 1 or value == 0xFFFF or not ((system != "mcd" and address < 0x400000) or 0xFF0000 <= address <= 0xFFFFFE):
            return False
    return bool(lines)


def ps1_program_mode(lines):
    """Beetle's reviewed byte/word writes and bounded control grammar."""
    if not lines or any(not re.fullmatch(r"[0-9A-F]{8} [0-9A-F]{4}", line) for line in lines):
        return None
    words = [(int(line[:8], 16), int(line[9:], 16)) for line in lines]
    if any((address >> 24) == 0x30 and value > 0xFF for address, value in words):
        return None
    if all((address >> 24) in {0x30, 0x80} for address, _ in words):
        return "writes"
    index = 0
    while index < len(words):
        address, value = words[index]
        opcode = address >> 24
        if opcode in {0xD0, 0xD1, 0xD2, 0xD3, 0xE0, 0xE1, 0xE2, 0xE3}:
            if opcode >= 0xE0 and value > 0xFF:
                return None
            index += 1
        if index < len(words) and words[index][0] >> 24 == 0x50:
            address, value = words[index]
            if (address >> 16) & 0xFF or not ((address >> 8) & 0xFF) or value > 0xFF:
                return None
            index += 1
        if index >= len(words) or words[index][0] >> 24 not in {0x30, 0x80}:
            return None
        index += 1
    return "atomic"


def review_program(item, system, engines):
    item = dict(item)
    code = item.get("code", "")
    dialect = item.get("dialect", "unknown")
    name = str(item.get("name", "")).strip()
    if not name:
        name = "Code " + sha(code.encode("utf-8"))[:12]
    if len(name) > 1024:
        item["source_name"] = name
        name = name[:1024]
    item["name"] = name
    lines = program_lines(code, dialect)
    item.update(lines=lines, code=code.strip(), handler=item.get("handler", 0), enabled=False,
                dependencies=item.get("dependencies", []), parameters=item.get("parameters", []), kind=item.get("kind", "gameplay"))
    status, reason = item.get("status", "available"), item.get("reason", "")
    if not code.strip():
        status, reason = "invalid", "heading-without-program"
    elif item["handler"] != 0:
        status, reason = "requires_engine", "memory-handler-not-enabled"
    elif dialect in SIMPLE_PATTERNS:
        if not lines or any(not re.fullmatch(SIMPLE_PATTERNS[dialect], p) for p in lines):
            status, reason = "invalid", "malformed-instruction"
        elif system in {"32x", "pico"}:
            if not pico_program_allowed(lines, system):
                status, reason = "requires_engine", "program-outside-reviewed-picodrive-md-profile"
            else:
                item["activation_profiles"] = ["picodrive"]
        elif len(lines) > 99:
            if system in {"md", "mcd"} and {"32x", "pico"} & engines and pico_program_allowed(lines, system):
                item["activation_profiles"] = ["picodrive"]
            else:
                status, reason = "requires_engine", "program-exceeds-99-native-call-boundary"
    elif dialect == "pce-raw":
        if not lines or any(not re.fullmatch(r"[0-9A-F]{6}:[0-9A-F]{2}", p) for p in lines):
            status, reason = "invalid", "malformed-pce-raw-instruction"
        elif len("+".join(lines)) > 8192:
            status, reason = "requires_engine", "program-exceeds-pce-batched-input-boundary"
        elif any(not (0x1F0000 <= int(p[:6], 16) <= 0x1F1FFF or 0xF82000 <= int(p[:6], 16) <= 0xF83FFF
                or (system in {"pccd", "tgcd"} and 0x0D0000 <= int(p[:6], 16) <= 0x10FFFF)) for p in lines):
            status, reason = "requires_engine", "pce-address-outside-reviewed-main-or-cd-ram-profile"
    elif dialect == "wswan-raw":
        if not lines or any(not re.fullmatch(r"[0-9A-F]{4}:[0-9A-F]{2}", p) for p in lines):
            status, reason = "requires_engine", "wswan-address-or-value-outside-reviewed-physical-ram-profile"
        elif len(lines) > 128 or len("+".join(lines)) > 1023:
            status, reason = "requires_engine", "program-exceeds-wswan-128-write-single-call-boundary"
    elif dialect == "gba-vba-raw":
        if not lines or any(not re.fullmatch(r"[0-9A-F]{8}:(?:[0-9A-F]{2}|[0-9A-F]{4}|[0-9A-F]{8})", p) for p in lines):
            status, reason = "invalid", "malformed-vba-address-value-program"
        elif len(lines) > 128 or sum(13 if len(p) == 11 else len(p) for p in lines) + len(lines) - 1 > 4096:
            status, reason = "requires_engine", "program-exceeds-gba-vba-core-boundary"
        else:
            for line in lines:
                address, width = int(line[:8], 16), (len(line) - 9) // 2
                ram_end = 0x02040000 if 0x02000000 <= address < 0x02040000 else (0x03008000 if 0x03000000 <= address < 0x03008000 else 0)
                if not ((ram_end and address % width == 0 and address + width <= ram_end)
                        or (width == 4 and 0x08000000 <= address <= 0x0DFFFFFF)):
                    status, reason = "requires_engine", "vba-address-width-not-in-reviewed-ram-or-rom-profile"
                    break
    elif dialect in {"ds-actionreplay", "ps1-gameshark", "gba-gameshark-v1", "gba-gameshark-v3", "gba-codebreaker", "gba-unknown", "gba-auto", "n64-gameshark", "gateshark", "ctrpf", "gecko", "actionReplay", "cwcheat"}:
        width = 4 if dialect in {"ps1-gameshark", "n64-gameshark", "gba-codebreaker"} else 8
        pattern = r"[0-9A-F]{8} (?:[0-9A-F]{4}|[0-9A-F]{8})" if dialect == "gba-auto" else r"[0-9A-F]{8} [0-9A-F]{" + str(width) + r"}"
        if re.search(r"(?i)(?:\?\?|[XYZ]{2,}|pokemon\s+code|level\s+code)", code):
            status, reason = "unresolved", "unresolved-parameter-or-program-reference"
        elif any(not re.fullmatch(pattern, p) for p in lines):
            status, reason = "invalid", "malformed-instruction"
        elif dialect == "ps1-gameshark" and ps1_program_mode(lines) is None:
            status, reason = "requires_engine", "ps1-opcode-or-control-grammar-not-in-reviewed-adapter"
        elif dialect == "ps1-gameshark" and ps1_program_mode(lines) == "atomic" and len("+".join(p.replace(" ", "") for p in lines)) > 255:
            status, reason = "requires_engine", "ps1-atomic-program-exceeds-255-byte-core-boundary"
        elif dialect == "ds-actionreplay" and len("+".join(lines)) > 1023:
            status, reason = "requires_engine", "program-exceeds-1023-byte-ds-core-boundary"
        elif dialect == "ps1-gameshark" and len("+".join(lines)) > 8192:
            status, reason = "requires_engine", "program-exceeds-8192-byte-ps1-adapter-boundary"
        elif dialect.startswith("gba-") and (len(lines) > 128 or len("+".join(lines)) > 4096):
            status, reason = "requires_engine", "program-exceeds-gba-core-boundary"
        elif dialect == "gba-unknown":
            status, reason = "unresolved", "gba-dialect-version-not-established"
        elif dialect == "cwcheat" and (len(lines) > 128 or len("+".join(lines)) > 4096):
            status, reason = "requires_engine", "program-exceeds-psp-core-boundary"
        elif dialect == "n64-gameshark" and (len(lines) > 128 or len("+".join(lines)) > 1791 or any(p[:2] not in {"80", "81", "A0", "A1", "D0", "D1", "D2", "D3", "50"} for p in lines)):
            status, reason = "requires_engine", "program-exceeds-n64-adapter-boundary-or-opcodes"
        elif dialect == "n64-gameshark" and lines[-1][:2] in {"D0", "D1", "D2", "D3", "50"}:
            status, reason = "unresolved", "n64-program-ends-with-orphaned-condition-or-slide"
        if dialect == "cwcheat" and item["code"] != "\n".join(lines):
            item["source_code"] = item["code"]
            item["code"] = "\n".join(lines)
    elif dialect == "pnach":
        patches = [p.split("//", 1)[0].strip() for p in lines if re.match(r"\s*patch\s*=", p)]
        pattern = r"patch\s*=\s*[01]\s*,\s*(?:EE|IOP)\s*,\s*[0-9a-fA-F]{8}\s*,\s*(?:byte|short|word|double|extended)\s*,\s*[0-9a-fA-F]{1,16}"
        if not patches or any(not re.fullmatch(pattern, p, re.I) for p in patches):
            status, reason = "invalid", "malformed-pnach-program"
    elif dialect == "rpcs3-yaml":
        document = item.get("native_document")
        ppu_keys = [k for k in document if re.fullmatch(r"PPU-[a-fA-F0-9]{40}", k)] if isinstance(document, dict) else []
        if not document or document.get("Version") not in {1.2, "1.2"} or len(ppu_keys) != 1:
            status, reason = "requires_engine", "missing-validated-native-rpcs3-document"
        else:
            patches = document[ppu_keys[0]]
            if not isinstance(patches, dict) or len(patches) != 1:
                status, reason = "invalid", "rpcs3-document-must-contain-one-complete-patch"
            else:
                patch = next(iter(patches.values()))
                if patch.get("Configurable Values") or patch.get("ConfigurableValues"):
                    status, reason = "unresolved", "rpcs3-configurable-values-require-selection"
                elif not patch.get("Games") or not isinstance(patch.get("Patch"), list) or any(not isinstance(p, list) or len(p) != 3 for p in patch["Patch"]):
                    status, reason = "invalid", "rpcs3-incomplete-patch-or-game-scope"
    elif dialect == "fbneo-ini":
        document = item.get("native_document")
        if not isinstance(document, dict) or document.get("import_default") != 0 or not document.get("choices") or item.get("choice_control") != "native-ui-after-restart":
            status, reason = "requires_engine", "fbneo-native-disabled-import-contract-not-established"
    elif dialect == "sega8-actionreplay":
        status, reason = "requires_engine", "sega8-actionreplay-mapping-to-reviewed-native-channel-not-proved"
    else:
        status, reason = "requires_engine", "dialect-not-implemented"
    if system not in engines and status == "available":
        status, reason = "requires_engine", "activation-adapter-not-yet-reviewed"
    if item["parameters"] and status == "available":
        status, reason = "unresolved", "parameter-selection-required"
    if status == "available" and (len(item["code"]) > 131072 or len(lines) > 4096):
        status, reason = "requires_engine", "program-exceeds-shared-native-boundary"
    if status == "available" and (dialect in SIMPLE_PATTERNS or dialect in {"ds-actionreplay", "ps1-gameshark", "gba-gameshark-v1", "gba-gameshark-v3", "gba-codebreaker", "gba-auto", "gba-vba-raw", "n64-gameshark", "cwcheat", "pce-raw", "wswan-raw"}):
        normalized = "+".join(p.replace(" ", "") for p in lines) if dialect == "ps1-gameshark" and ps1_program_mode(lines) == "atomic" else "\n".join(lines)
        if item["code"] != normalized:
            item.setdefault("source_code", item["code"])
            item["code"] = normalized
    item.update(status=status, reason=reason)
    return item


def identity_key(g):
    key = {"system": g.get("system", ""), "title": g["title"] if not g.get("identities") else "",
            "revision": g.get("revision", ""), "version_scope": g.get("version_scope", ""), "regions": sorted(g.get("regions", [])),
            "languages": sorted(g.get("languages", [])),
            "identities": sorted(g.get("identities", []), key=lambda x: (x["type"], x.get("scheme", ""), x["value"]))}
    if g.get("source_identities"):
        # A source checksum with unknown byte range distinguishes publications
        # but is never promoted to a runtime ROM hash or exact edition match.
        key["source_identities"] = sorted(g["source_identities"], key=lambda x: (x["type"], x.get("scheme", ""), x["value"]))
    return key


def source_signature(source, engines):
    formats = {source.get("format")} | {r.get("format") for r in source.get("members", [])}
    formats.discard(None)
    return sha(canonical({"source": source, "engines": engines,
        "parsers": {fmt: inspect.getsource(PARSERS[fmt]) if fmt in PARSERS else "unsupported-format" for fmt in sorted(formats)}}))


def provenance_producer(provenance, dialect):
    # Attribution is not the input which produced the normalized program.
    # Older snapshots predate import_source_id; the authored NCL crosswalk is
    # the only legacy cross-source attribution in those snapshots.
    return provenance.get("import_source_id") or ("artemisrpcs3" if provenance.get("source_id") == "artemis" and dialect == "rpcs3-yaml" else provenance.get("source_id"))


def build(lock_path, output, cache, offline=False, reuse_normalised=False, refresh_sources=()):
    lock = json.loads(lock_path.read_bytes())
    sources = lock["sources"]
    if len({s["id"] for s in sources}) != len(sources):
        raise FormatError("duplicate source id")
    engines = set(lock.get("available_systems", sorted(SUPPORTED)))
    output.mkdir(parents=True, exist_ok=True); cache.mkdir(parents=True, exist_ok=True)
    pack_cache = reusable_packs(output) if reuse_normalised else {}
    summary = []
    temporary_db = tempfile.TemporaryDirectory(prefix="unified-normalise-", dir=cache)
    database = sqlite3.connect(str(Path(temporary_db.name) / "games.sqlite"))
    snapshot, snapshot_meta = cache / "active-normalised.sqlite", cache / "active-normalised-meta.json"
    old_meta, unchanged = {}, set()
    signatures = {s["id"]: source_signature(s, lock.get("available_systems", sorted(SUPPORTED))) for s in sources}
    refresh_sources = set(refresh_sources)
    if refresh_sources - set(signatures):
        raise FormatError("refresh requested an unknown source")
    if reuse_normalised:
        old_meta = json.loads(snapshot_meta.read_bytes())
        # Adding an engine cannot invalidate already reviewed programs. A
        # stricter rule for an existing dialect must bump policy and rebuild;
        # broader bounds explicitly refresh their source IDs to recover codes.
        old_engines = old_meta.get("available_systems", [])
        if old_meta.get("normalisation_policy") != 1 or not set(old_engines).issubset(engines):
            raise FormatError("normalised cache policy or reviewed engines changed; rebuild required")
        with sqlite3.connect(str(snapshot)) as saved:
            saved.backup(database)
        unchanged = {s["id"] for s in sources if s["id"] not in refresh_sources
                     and old_meta.get("source_signatures", {}).get(s["id"]) == source_signature(s, old_engines)}
        changed = set(old_meta.get("source_signatures", {})) - unchanged
        if changed:
            marks = ",".join("?" for _ in changed)
            affected = [r[0] for r in database.execute("SELECT DISTINCT game_id FROM sources WHERE source_id IN (" + marks + ")", sorted(changed))]
            for gid in affected:
                for pid, body in list(database.execute("SELECT id,body FROM programs WHERE game_id=?", (gid,))):
                    c = json.loads(body)
                    c["provenance"] = [p for p in c["provenance"] if provenance_producer(p, c.get("dialect")) not in changed]
                    if c["provenance"]:
                        database.execute("UPDATE programs SET body=? WHERE game_id=? AND id=?", (canonical(c), gid, pid))
                    else:
                        database.execute("DELETE FROM programs WHERE game_id=? AND id=?", (gid, pid))
            database.execute("DELETE FROM sources WHERE source_id IN (" + marks + ")", sorted(changed))
        database.commit()
    else:
        database.executescript("""
        PRAGMA journal_mode=OFF; PRAGMA synchronous=OFF;
        PRAGMA cache_size=-65536; PRAGMA temp_store=FILE;
        CREATE TABLE games (id TEXT PRIMARY KEY, body BLOB NOT NULL) WITHOUT ROWID;
        CREATE TABLE programs (game_id TEXT, id TEXT, body BLOB NOT NULL,
            PRIMARY KEY (game_id,id)) WITHOUT ROWID;
        CREATE TABLE sources (game_id TEXT, source_id TEXT,
            PRIMARY KEY (game_id,source_id)) WITHOUT ROWID;
        """)
    database.executescript("PRAGMA journal_mode=OFF; PRAGMA synchronous=OFF; PRAGMA cache_size=-65536; PRAGMA temp_store=FILE;")

    def process(source):
        source = dict(source)
        if source.get("identity_index_directory"):
            directory = lock_path.parent / source["identity_index_directory"]
            mapping = {}
            for file in sorted(directory.glob("libretro-*.json")):
                index = json.loads(file.read_bytes())
                system = index.get("console", "")
                for row in index.get("identities", []):
                    scheme = {"nes": "ines-prg-chr", "snes": "snes-headerless", "n64": "n64-big-endian", "psx": "redump-disc"}.get(system, "rom-full")
                    ids = [{"type": typ, "value": row[typ], "scheme": scheme} for typ in ("md5", "sha1") if row.get(typ)]
                    if row.get("serial"):
                        ids.append({"type": "serial", "value": row["serial"], "scheme": "ps1-disc-serial"})
                    key = system + ":" + re.sub(r"\s+", " ", row["title"].strip().lower())
                    mapping.setdefault(key, []).extend(ids)
            source["options"] = {**source.get("options", {}), "identities_by_title": mapping}
        info = {k: source[k] for k in ("id", "name", "url", "revision", "license", "status", "reason", "import_scope", "publication", "sha256", "research_id") if k in source}
        info.setdefault("status", "available")
        if source.get("publication", {}).get("enabled") is False:
            info.update(status="excluded", reason=source["publication"]["reason"], game_count=0)
            return info, []
        if info["status"] in {"conditional", "disabled", "duplicate", "future_engine"} and not source.get("sha256"):
            return info, []
        try:
            data = fetch(source, cache, offline, lock_path.parent)
            parsed, errors = parse_source(source, data)
            if source.get("decoder_proof"):
                from unified_verification import apply_gba_proof
                proof_data = fetch(source["decoder_proof"], cache, offline, lock_path.parent)
                apply_gba_proof(parsed, source["id"], json.loads(proof_data), sha(proof_data))
            info.update(sha256=sha(data), bytes=len(data), game_count=len(parsed), rejected_members=errors)
            bad_games = [{"title": g.get("title", ""), "reason": g["import_error"]} for g in parsed if g.get("import_error")]
            if bad_games:
                info["rejected_games"] = bad_games
            if errors:
                info["status"] = "partial"
            return info, parsed
        except Exception as exc:
            info.update(status="conditional", reason=str(exc)[:500], game_count=0)
            return info, []

    # Network transfer is parallel and SHA checked; parsing/normalisation is
    # deliberately bounded to one publication. Queuing all parsed catalogues
    # retained millions of dictionaries and exceeded the host memory limit.
    fetch_errors = {}
    if not offline:
        def prime(source):
            if source["id"] in unchanged or not source.get("sha256") or source.get("publication", {}).get("enabled") is False:
                return
            try:
                fetch(source, cache, False, lock_path.parent)
            except Exception as exc:
                fetch_errors[source["id"]] = str(exc)[:500]
        with concurrent.futures.ThreadPoolExecutor(max_workers=min(4, max(1, int(lock.get("download_workers", 4))))) as pool:
            list(pool.map(prime, sources))

    def store_game(g, rejected):
        if not g.get("title") or not isinstance(g.get("cheats"), list):
            return
        key = sha(canonical(identity_key(g)))[:32]
        header = {**{k: g.get(k, [] if k in {"identities", "regions", "languages"} else "") for k in ("system", "title", "identities", "regions", "languages", "revision", "version_scope")}, "id": key,
                  "edition_confirmation_required": bool(g.get("edition_confirmation_required", not bool(g.get("identities"))))}
        if g.get("source_identities"):
            header["source_identities"] = g["source_identities"]
        database.execute("INSERT OR IGNORE INTO games VALUES (?,?)", (key, canonical(header)))
        source_ids = set()
        for raw in g["cheats"]:
            if not raw.get("code", "").strip():
                continue
            c = review_program(raw, g.get("system", ""), engines)
            if g.get("status") in {"unresolved", "invalid", "requires_engine"} and c["status"] == "available":
                c.update(status=g["status"], reason=g.get("reason", "identity-not-established"))
            if c["status"] != "available":
                rejected[c.get("reason") or c["status"]] += 1
                continue
            fingerprint = sha(canonical({"dialect": c["dialect"], "lines": c["lines"], "dependencies": c["dependencies"], "parameters": c["parameters"], "handler": c["handler"],
                "exclusive_group": c.get("exclusive_group", ""), "group": c.get("group", ""), "memory_operation": c.get("memory_operation"), "native_document": c.get("native_document"),
                **({"exclusive_groups": c["exclusive_groups"]} if c.get("exclusive_groups") else {}),
                **({"mgba_auto_isolated": True} if c.get("mgba_auto_isolated") else {})}))[:32]
            c["id"] = fingerprint
            if raw.get("id"):
                c["source_id"] = raw["id"]
            cursor = database.execute("INSERT OR IGNORE INTO programs VALUES (?,?,?)", (key, fingerprint, canonical(c)))
            if cursor.rowcount == 0:
                old = json.loads(database.execute("SELECT body FROM programs WHERE game_id=? AND id=?", (key, fingerprint)).fetchone()[0])
                old["provenance"] = sorted({canonical(p): p for p in old["provenance"] + c["provenance"]}.values(), key=lambda p: canonical(p))
                old.setdefault("aliases", [])
                if c["name"] != old["name"] and c["name"] not in old["aliases"]:
                    old["aliases"].append(c["name"])
                database.execute("UPDATE programs SET body=? WHERE game_id=? AND id=?", (canonical(old), key, fingerprint))
            source_ids.update(p["source_id"] for p in c["provenance"])
        database.executemany("INSERT OR IGNORE INTO sources VALUES (?,?)", ((key, sid) for sid in sorted(source_ids)))

    for source in sources:
        if source["id"] in unchanged:
            cached_info = next(dict(s) for s in old_meta["summary"] if s["id"] == source["id"])
            cached_info.update({k: source[k] for k in ("id", "name", "url", "revision", "license", "import_scope", "publication", "sha256", "research_id") if k in source})
            summary.append(cached_info)
            print(source["id"], "cached", flush=True)
            continue
        info, parsed = process(source) if source["id"] not in fetch_errors else ({"id": source["id"], "name": source["name"], "status": "conditional", "reason": fetch_errors[source["id"]]}, [])
        summary.append(info)
        provenance = {"source_id": source["id"], "import_source_id": source["id"], "url": source.get("url", ""), "author": source.get("author", ""),
                      "revision": source.get("revision", source.get("sha256", "")), "license": source.get("license", "Unspecified; original authors retain their rights")}
        count = len(parsed)
        rejected = Counter()
        for g in parsed:
            for c in g.get("cheats", []):
                c["provenance"] = [{**provenance, **existing, "import_source_id": source["id"]} for existing in c.get("provenance", [])]
                c.setdefault("provenance", []).append({**provenance, **({"author": c["author"]} if c.get("author") else {})})
            store_game(g, rejected)
        info["rejected_programs"] = dict(sorted(rejected.items()))
        database.commit()
        parsed.clear()
        print(source["id"], info["status"], count, flush=True)

    # The cache holds reviewed normalized programs, not network responses. Its
    # per-source parser/input signatures permit a narrow repeat for conversions
    # while retaining the expensive DS/Libretro normalization unchanged.
    target = cache / "active-normalised.new.sqlite"
    target.unlink(missing_ok=True)
    with sqlite3.connect(str(target)) as saved:
        database.backup(saved)
    os.replace(target, snapshot)
    atomic(snapshot_meta, canonical({"schema_version": 1, "normalisation_policy": 1,
        "source_signatures": signatures, "available_systems": lock.get("available_systems", sorted(SUPPORTED)), "summary": summary}))

    games = []
    packs, current, current_size = [], [], 0
    def flush():
        nonlocal current, current_size
        if not current:
            return
        raw = canonical({"schema_version": SCHEMA, "files": [{"game_id": m["id"], "data": base64.b64encode(b).decode("ascii")} for m, b in current]})
        if len(raw) > MAX_PACK_RAW:
            raise FormatError("pack expansion exceeds 16MiB")
        reused = pack_cache.get(sha(raw))
        packed = reused.read_bytes() if reused else gzip_bytes(raw)
        if len(packed) > MAX_PACK_GZIP:
            raise FormatError("compressed pack exceeds 8MiB")
        digest = sha(packed); pid = "pack-" + digest[:24]; path = "packs/" + pid + ".json.gz"
        if reused != output / path:
            atomic(output / path, packed)
        packs.append({"id": pid, "path": path, "sha256": digest, "size": len(packed), "uncompressed_size": len(raw), "game_ids": [m["id"] for m, _ in current]})
        for m, _ in current:
            m["pack_id"] = pid
        current, current_size = [], 0

    rejected_games, used_sources, published_programs, identity_groups = [], Counter(), 0, 0
    for gid, header in database.execute("SELECT id,body FROM games ORDER BY id"):
        chunk = {"schema_version": SCHEMA, "game": json.loads(header),
            "cheats": sorted((json.loads(row[0]) for row in database.execute("SELECT body FROM programs WHERE game_id=?", (gid,))), key=lambda c: (c["name"].casefold(), c["id"])),
            "sources": [row[0] for row in database.execute("SELECT source_id FROM sources WHERE game_id=? ORDER BY source_id", (gid,))]}
        if not chunk["cheats"]:
            continue
        for c in chunk["cheats"]:
            for p in c["provenance"]:
                p.setdefault("import_source_id", provenance_producer(p, c.get("dialect")))
        chunk["cheats"] = [review_program(c, chunk["game"]["system"], engines) for c in chunk["cheats"]]
        by_id = {c["id"]: c for c in chunk["cheats"]}
        aliases = {}
        for c in chunk["cheats"]:
            for alias in (c["id"], c.get("source_id"), c["name"]):
                if alias:
                    aliases.setdefault(alias, set()).add(c["id"])
        for c in chunk["cheats"]:
            resolved = []
            for dep in c["dependencies"]:
                matches = aliases.get(dep, set())
                if len(matches) != 1:
                    c.update(status="unresolved", reason="missing-or-ambiguous-program-dependency")
                else:
                    resolved.append(next(iter(matches)))
            c["dependencies"] = resolved

        def closure(items):
            selected, visiting = {}, set()
            def add(c):
                if c["id"] in selected:
                    return
                if c["id"] in visiting:
                    c.update(status="unresolved", reason="cyclic-program-dependency")
                    return
                visiting.add(c["id"])
                for dependency in c["dependencies"]:
                    if dependency in by_id:
                        add(by_id[dependency])
                visiting.remove(c["id"])
                selected[c["id"]] = c
            for c in items:
                add(c)
            return sorted(selected.values(), key=lambda c: (c["name"].casefold(), c["id"]))

        # Resolve cycles and propagate a missing prerequisite before publication.
        # An available write may never outlive its master/condition program.
        closure(chunk["cheats"])
        for c in chunk["cheats"]:
            if c["status"] != "available":
                continue
            requirements = closure([c])
            total_lines = sum(len(p["lines"]) for p in requirements)
            total_bytes = sum(len("+".join(p["lines"]).encode("utf-8")) for p in requirements) + max(0, len(requirements) - 1)
            dialects = {p["dialect"] for p in requirements}
            ps1_atomic = "ps1-gameshark" in dialects and any(ps1_program_mode(p["lines"]) == "atomic" for p in requirements if p["dialect"] == "ps1-gameshark")
            ps1_bytes = sum(len("+".join(line.replace(" ", "") for line in p["lines"])) for p in requirements) + max(0, len(requirements) - 1)
            simple_overflow = any(d in SIMPLE_PATTERNS for d in dialects) and total_lines > 99
            pico_lines = [line for p in requirements for line in p["lines"]]
            pico_closure = dialects.issubset({"md-raw", "md-gamegenie"}) and pico_program_allowed(pico_lines, chunk["game"]["system"])
            if simple_overflow and pico_closure and {"32x", "pico"} & engines:
                c["activation_profiles"] = ["picodrive"]
                simple_overflow = False
            exceeds = (("ds-actionreplay" in dialects and total_bytes > 1023)
                or ("ps1-gameshark" in dialects and (ps1_bytes > 255 if ps1_atomic else total_bytes > 8192))
                or ("cwcheat" in dialects and (total_lines > 128 or total_bytes > 4096))
                or ("n64-gameshark" in dialects and (total_lines > 128 or total_bytes > 1791))
                or (any(d.startswith("gba-") for d in dialects) and (total_lines > 128 or total_bytes > 4096))
                or ("fbneo-ini" in dialects and len(requirements) > 1)
                or ("pce-raw" in dialects and total_bytes > 8192)
                or ("wswan-raw" in dialects and (total_lines > 128 or total_bytes > 1023))
                or (chunk["game"]["system"] in {"32x", "pico"} and not pico_closure)
                or simple_overflow)
            if exceeds:
                c.update(status="requires_engine", reason="complete-dependency-group-exceeds-reviewed-adapter-boundary")
        changed = True
        while changed:
            changed = False
            for c in chunk["cheats"]:
                if c["status"] == "available" and any(by_id[d]["status"] != "available" for d in c["dependencies"]):
                    c.update(status="unresolved", reason="unavailable-program-dependency")
                    changed = True
        removed = [c for c in chunk["cheats"] if c["status"] != "available"]
        if removed:
            rejected_games.append({"game_id": gid, "rejected_programs": dict(sorted(Counter(c["reason"] for c in removed).items()))})
        chunk["cheats"] = [c for c in chunk["cheats"] if c["status"] == "available"]
        if not chunk["cheats"]:
            continue
        published_programs += len(chunk["cheats"])
        identity_groups += 1
        chunk["sources"] = sorted({p["source_id"] for c in chunk["cheats"] for p in c["provenance"]})
        for c in chunk["cheats"]:
            used_sources.update({p["source_id"] for p in c["provenance"]})

        # A transport part is a bounded slice of one game, never half a code.
        # Every part carries all prerequisite programs required by its codes.
        parts, pending, pending_size = [], [], 0
        for c in chunk["cheats"]:
            weight = len(canonical(c))
            if pending and pending_size + weight > 1024 * 1024:
                parts.append(closure(pending)); pending, pending_size = [], 0
            pending.append(c); pending_size += weight
        if pending:
            parts.append(closure(pending))
        for index, items in enumerate(parts, 1):
            part_id = sha((gid + ":" + str(index)).encode())[:32] if len(parts) > 1 else gid
            game_info = {**chunk["game"], "id": part_id, "identity_group": gid, "part": index, "parts": len(parts)}
            part = {**chunk, "game": game_info, "cheats": items}
            encoded = canonical(part)
            if len(encoded) > MAX_CHUNK:
                raise FormatError("dependency-complete game part exceeds 2MiB; change partition policy")
            meta = {**game_info, "path": "games/" + part_id + ".json", "sha256": sha(encoded), "size": len(encoded),
                    "cheat_count": len(items), "available_count": sum(c["status"] == "available" for c in items)}
            games.append(meta)
            weight = (len(encoded) + 2) // 3 * 4 + 100
            if current and current_size + weight > PACK_TARGET:
                flush()
            current.append((meta, encoded)); current_size += weight

    flush()
    database.close()
    temporary_db.cleanup()
    active_sources = []
    for info in summary:
        info["available_programs"] = used_sources[info["id"]]
        if info["available_programs"]:
            if info.get("rejected_programs") and info["status"] == "available":
                info["status"] = "partial"
            active_info = {k: v for k, v in info.items() if k not in {"rejected_members", "rejected_games", "rejected_programs", "publication"}}
            active_info["publication_scope"] = "Only complete compatible programs from the documented pinned input; reference portals are not claimed exhaustively downloaded."
            if info["status"] == "excluded":
                active_info.update(status="partial", reason="Provenance crosswalk to already authored compatible native programs; no direct execution of the source format")
            active_sources.append(active_info)
        elif info["status"] not in {"conditional", "excluded"}:
            info.update(status="excluded", reason="no-complete-program-supported-by-current-activation-adapters")
    audit = {"schema_version": SCHEMA, "sources": summary, "rejected_games": rejected_games,
             "policy": "Only complete programs executable by reviewed current adapters are published; edition candidates require explicit user confirmation. Unavailable or unsupported source inputs remain in the historical lock, with adaptation diagnostics."}
    atomic(output / "audit.json.gz", gzip_bytes(canonical(audit)))
    manifest = {"schema_version": SCHEMA, "catalogue_id": "neostation-unified", "sources": active_sources, "games": games, "packs": packs,
                "totals": {"sources": len(active_sources), "games": len(games), "identity_groups": identity_groups,
                           "programs": published_programs, "cheats": sum(g["cheat_count"] for g in games),
                           "available": sum(g["available_count"] for g in games), "download_bytes": sum(p["size"] for p in packs)},
                "identity_policy": "Require exact typed identity including hash scheme, region/language/revision. Titles propose candidates only. Never fall back across regions.",
                "validation": "Parser and format validation only. Available means a reviewed activation adapter, not physical-device gameplay verification."}
    manifest["counting_policy"] = "programs counts deduplicated programs within exact typed edition-identity groups before dependency duplication in transport parts; games counts transport records/parts, not unique commercial games. Different identity schemes are never merged by title alone."
    manifest["revision"] = sha(canonical(manifest))
    manifest_raw = canonical(manifest)
    if len(manifest_raw) > 64 * 1024 * 1024:
        raise FormatError("manifest expansion exceeds runtime 64MiB limit")
    manifest_gzip = gzip_bytes(manifest_raw)
    if len(manifest_gzip) > 12 * 1024 * 1024:
        raise FormatError("compressed manifest exceeds runtime 12MiB limit")
    atomic(output / "manifest.json.gz", manifest_gzip)
    atomic(cache / "manifest.json", manifest_raw)
    (output / "manifest.json").unlink(missing_ok=True)
    expected_paths = {p["path"] for p in packs}
    for old in (output / "packs").glob("*.json.gz"):
        if old.relative_to(output).as_posix() not in expected_paths:
            old.unlink()
    validate(output)
    return manifest


def validate(directory):
    index = directory / "manifest.json.gz"
    if index.exists():
        packed = index.read_bytes()
        if len(packed) > 12 * 1024 * 1024:
            raise FormatError("compressed manifest exceeds 12MiB")
        with gzip.GzipFile(fileobj=io.BytesIO(packed)) as stream:
            data = stream.read(64 * 1024 * 1024 + 1)
        if len(data) > 64 * 1024 * 1024:
            raise FormatError("manifest expansion exceeds 64MiB")
        manifest = json.loads(data)
    else:
        manifest = json.loads((directory / "manifest.json").read_bytes())
    if manifest.get("schema_version") != SCHEMA:
        raise FormatError("unsupported schema")
    games = {g["id"]: g for g in manifest["games"]}
    if len(games) != len(manifest["games"]) or any(not re.fullmatch(r"[A-Za-z0-9_.-]{1,160}", g.get("system", "")) for g in games.values()):
        raise FormatError("duplicate game id or unsafe/empty system")
    seen = set()
    for pack in manifest["packs"]:
        p = directory / str(safe_path(pack["path"]))
        packed = p.read_bytes()
        if len(packed) != pack["size"] or sha(packed) != pack["sha256"] or len(packed) > MAX_PACK_GZIP:
            raise FormatError("pack size/hash mismatch")
        with gzip.GzipFile(fileobj=io.BytesIO(packed)) as stream:
            raw = stream.read(MAX_PACK_RAW + 1)
        if len(raw) != pack["uncompressed_size"] or len(raw) > MAX_PACK_RAW:
            raise FormatError("pack expansion mismatch")
        payload = json.loads(raw)
        if payload.get("schema_version") != SCHEMA:
            raise FormatError("pack schema mismatch")
        actual = []
        for f in payload["files"]:
            gid = f["game_id"]
            if gid in seen or gid not in games:
                raise FormatError("duplicate/unknown game in pack")
            encoded = base64.b64decode(f["data"], validate=True)
            meta = games[gid]
            if len(encoded) != meta["size"] or sha(encoded) != meta["sha256"] or len(encoded) > MAX_CHUNK:
                raise FormatError("game size/hash mismatch")
            if meta["pack_id"] != pack["id"]:
                raise FormatError("game pack id mismatch")
            chunk = json.loads(encoded)
            if chunk.get("schema_version") != SCHEMA or chunk["game"]["id"] != gid or chunk["game"].get("system") != meta.get("system"):
                raise FormatError("game identity/schema mismatch")
            if any(c.get("enabled") is not False for c in chunk["cheats"]):
                raise FormatError("downloaded code cannot be enabled")
            by_id = {c["id"]: c for c in chunk["cheats"]}
            if len(by_id) != len(chunk["cheats"]) or any(c.get("status") != "available" or c.get("parameters") or any(d not in by_id for d in c.get("dependencies", [])) for c in chunk["cheats"]):
                raise FormatError("active chunk includes an unavailable or incomplete program")
            seen.add(gid); actual.append(gid)
        if actual != pack["game_ids"]:
            raise FormatError("pack game list mismatch")
    if seen != set(games):
        raise FormatError("missing game packs")
    return manifest


def main():
    try:
        from unified_curated import PARSERS as curated
        PARSERS.update(curated)
    except ImportError:
        pass
    from unified_reserve import PARSERS as reserve
    PARSERS.update(reserve)
    try:
        from unified_extended import PARSERS as extended
        PARSERS.update(extended)
    except ImportError:
        pass
    from unified_adapt import PARSERS as adapted
    PARSERS.update(adapted)
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest="command", required=True)
    b = sub.add_parser("build"); b.add_argument("--sources", type=Path, required=True)
    b.add_argument("--output", type=Path, required=True); b.add_argument("--cache", type=Path, required=True)
    b.add_argument("--offline", action="store_true")
    b.add_argument("--reuse-normalised", action="store_true", help="Reuse unchanged SHA/parser-pinned normalized sources from the previous successful input pass")
    b.add_argument("--refresh-sources", default="", help="Comma-separated source IDs to review again after deliberately broader adapter bounds")
    b.add_argument("--bundle-index", type=Path, default=Path(__file__).resolve().parents[2] / "packages/neo_cheat_catalog/ios/Resources/manifest.json.gz")
    v = sub.add_parser("validate"); v.add_argument("--input", type=Path, required=True)
    args = p.parse_args()
    m = build(args.sources, args.output, args.cache, args.offline, args.reuse_normalised, filter(None, args.refresh_sources.split(","))) if args.command == "build" else validate(args.input)
    if args.command == "build":
        atomic(args.bundle_index, (args.output / "manifest.json.gz").read_bytes())
        args.bundle_index.with_name("manifest.json").unlink(missing_ok=True)
        from unified_report import report
        report(args.output)
    print(json.dumps(m["totals"], sort_keys=True))


if __name__ == "__main__":
    main()
