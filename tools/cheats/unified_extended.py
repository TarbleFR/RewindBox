"""Bounded Project64, FBNeo and MAME source readers; never execute cheats.

N64 header CRC pairs, arcade driver names and software-list names retain their
source namespaces. They are not hashes of an entire ROM. Native arcade XML/INI
programs retain their lifecycle, choices and processor/address-space semantics.
The optional 7z package reader needs host libarchive only during regeneration.
"""
from __future__ import annotations

import ctypes
import ctypes.util
import copy
import io
import json
from pathlib import PurePosixPath
import re
import xml.etree.ElementTree as ET
import zipfile


MAX_INPUT = 128 * 1024 * 1024
MAX_MEMBER = 32 * 1024 * 1024
MAX_EXPANDED = 512 * 1024 * 1024
MAX_MEMBERS = 250_000


def _text(data):
    if not isinstance(data, bytes) or len(data) > MAX_INPUT:
        raise ValueError("input-not-bytes-or-too-large")
    try:
        return data.decode("utf-8-sig")
    except UnicodeDecodeError:
        return data.decode("cp1252")


def _game(title, system, options, identities=None):
    return {"title": title, "system": system, "identities": identities or [],
            "regions": list(options.get("regions", [])), "languages": list(options.get("languages", [])),
            "revision": options.get("revision", ""), "cheats": [],
            "status": "requires_engine", "reason": "native-source-interpreter-not-connected"}


def _cheat(name, code, dialect, **extra):
    return {"name": name, "code": code, "dialect": dialect, "dependencies": [], "parameters": [],
            "enabled": False, "status": "requires_engine", "reason": "native-source-interpreter-not-connected", **extra}


def _fail(item, reason, status="invalid"):
    item.update(status=status, reason=reason)


def _native_integer(value):
    """C strtol(...,0) decimal/hex/octal semantics, without truncation."""
    return int(value, 16 if value.lower().startswith("0x") else 8 if len(value) > 1 and value.startswith("0") else 10)


def parse_project64_cht(data: bytes, options: dict) -> list[dict]:
    """Current Project64 [CRC1-CRC2-C:country], $name, ordered-code format.

    Parameter choices remain attached to the whole program, unresolved. With
    activation_reviewed=True a complete ordinary program is an available
    candidate for the builder's mandatory opcode/size/engine gate. A
    Project64 restore-value suffix is preserved as project64-native rather than
    silently losing its original value or declaring it ordinary GameShark.
    """
    games, game, item = [], None, None
    seen_choices = set()
    def finish():
        if item is None:
            return
        lines = item.pop("_lines")
        item["code"] = "\n".join(lines)
        if not lines:
            _fail(item, "heading-without-program")
        elif item.get("parameters") and item.get("status") != "invalid":
            _fail(item, "project64-parameter-selection-required", "unresolved")
        elif options.get("activation_reviewed") and item.get("status") == "requires_engine" and item["dialect"] == "n64-gameshark":
            item.update(status="available", reason="")
    for number, raw in enumerate(_text(data).splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith(("//", ";", "#")):
            continue
        if line.startswith("["):
            finish(); item = None
            header = re.fullmatch(r"\[([0-9A-Fa-f]{8})-([0-9A-Fa-f]{8})-C:([0-9A-Fa-f]{1,2})\]", line)
            if not header:
                raise ValueError("invalid-project64-game-header-at-line-" + str(number))
            value = header[1].upper() + "-" + header[2].upper() + "-C:" + header[3].upper().zfill(2)
            game = _game(options.get("title", ""), "n64", options,
                         [{"type": "n64_header", "value": value, "scheme": "n64-crc1-crc2-country"}])
            if options.get("activation_reviewed"):
                game.update(status="available", reason="")
            game["source_header"] = {"crc1": header[1].upper(), "crc2": header[2].upper(),
                                     "country": header[3].upper().zfill(2), "scope": "N64 header fields, not complete-ROM CRC32"}
            games.append(game)
        elif line.startswith("Name=") and game is not None and item is None:
            game["title"] = line[5:]
        elif line.startswith("$") and game is not None:
            finish()
            item = _cheat(line[1:], "", "n64-gameshark", _lines=[], source_line=number)
            game["cheats"].append(item); seen_choices = set()
        elif item is not None and line.startswith("Note="):
            item["notes"] = item.get("notes", "") + ("\n" if item.get("notes") else "") + line[5:]
        elif item is not None:
            code = re.fullmatch(r"([0-9A-Fa-f]{8})\s+([0-9A-Fa-f?]{4})(?::([0-9A-Fa-f]{4}))?", line)
            choice = re.fullmatch(r"([0-9A-Fa-f]{1,4})\s+(.+)", line)
            if code:
                item["_lines"].append(line.upper())
                if "?" in code[2] and not item["parameters"]:
                    item["parameters"] = [{"name": "value", "choices": []}]
                if code[3]:
                    item["dialect"] = "project64-native"
            elif choice:
                if not item["parameters"]:
                    item["parameters"] = [{"name": "value", "choices": []}]
                value = choice[1].upper()
                item["parameters"][0]["choices"].append({"value": value, "name": choice[2]})
                if value in seen_choices:
                    item["duplicate_choice_values"] = True
                seen_choices.add(value)
            else:
                # Retain malformed lines as evidence, never drop them from a
                # conditional program and pretend the remaining writes are safe.
                item["_lines"].append(line)
                _fail(item, "unrecognized-project64-program-line-" + str(number))
        elif game is not None:
            game.setdefault("unparsed_metadata", []).append(line)
    finish()
    return games


_QUOTED = r'"((?:[^"\\]|\\.)*)"'


def _unquote(value):
    return value.replace('\\"', '"').replace("\\\\", "\\")


def _driver_identity(options, scheme):
    driver = options.get("game_id") or options.get("romset") or PurePosixPath(options.get("path", "")).stem
    if not re.fullmatch(r"[A-Za-z0-9_.+-]+", driver or ""):
        return "", []
    return driver, [{"type": "romset", "value": driver, "scheme": scheme}]


def parse_fbneo_ini(data: bytes, options: dict) -> list[dict]:
    """FBNeo native text INI, not generic INI sections or RetroArch CHT.

    One record per complete `cheat` block. Every CPU/address/value triplet and
    every choice remains inside that block. Includes are dependencies of the
    source document, never renamed to standalone memory-write programs.
    available_driver_names, when supplied, is an exact delivered-driver list;
    absent romsets remain auditable but cannot be activated through an alias.
    """
    driver, ids = _driver_identity(options, "fbneo-driver-name")
    game = _game(options.get("title") or driver, "arcade", options, ids)
    item, raw_lines = None, []
    def finish():
        if item is None:
            return
        item["code"] = "\n".join(raw_lines)
        enabled = [c for c in item["choices"] if c["writes"]]
        if not enabled and item.get("status") != "invalid":
            game["skipped_headings"] = game.get("skipped_headings", 0) + 1
            if item["name"].strip():
                game.setdefault("source_notes", []).append(item["name"])
            game["cheats"].remove(item)
        elif len(enabled) > 1 and item.get("status") != "invalid" and not options.get("activation_reviewed"):
            item["parameters"] = [{"name": "choice", "choices": enabled}]
            _fail(item, "fbneo-choice-selection-required", "unresolved")
    for number, raw in enumerate(_text(data).splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith(("//", ";", "#")):
            continue
        # Existing upstream names contain literal inner quotes. A declaration
        # has no numeric suffix: its first and last quotes bound the label.
        declaration = re.fullmatch(r'cheat\s+"(.*)"', line)
        include = re.fullmatch(r"include\s+" + _QUOTED, line)
        if declaration:
            finish()
            item = _cheat(_unquote(declaration[1]), "", "fbneo-ini", choices=[], source_line=number)
            game["cheats"].append(item); raw_lines = [line]
            continue
        if include:
            game.setdefault("source_includes", []).append(_unquote(include[1]))
            continue
        if item is None:
            game.setdefault("unparsed_metadata", []).append(line)
            continue
        raw_lines.append(line)
        default = re.fullmatch(r"default\s+(\d+)", line)
        choice = re.fullmatch(r"(\d+)\s+" + _QUOTED + r"(?:\s*,\s*(.*))?", line)
        if default:
            try:
                item["source_default"] = _native_integer(default[1])
            except ValueError:
                _fail(item, "malformed-fbneo-native-default")
        elif choice:
            values = [word.strip() for word in (choice[3] or "").split(",")] if choice[3] else []
            try:
                option_index = _native_integer(choice[1])
            except ValueError:
                _fail(item, "malformed-fbneo-native-choice-index")
                continue
            option = {"index": option_index, "name": _unquote(choice[2]), "writes": []}
            if len(values) % 3 or any(not re.fullmatch(r"(?:0[xX][0-9A-Fa-f]+|\d+)", v) for v in values):
                _fail(item, "malformed-fbneo-cpu-address-value-triplets")
            else:
                for start in range(0, len(values), 3):
                    try:
                        triple = [_native_integer(v) for v in values[start:start + 3]]
                    except ValueError:
                        _fail(item, "malformed-fbneo-native-cpu-address-value")
                        break
                    if triple[0] > 255 or any(v > 0xFFFFFFFF for v in triple[1:]):
                        _fail(item, "fbneo-triplet-out-of-bounds")
                    option["writes"].append({"cpu": triple[0], "address": values[start + 1], "value": values[start + 2]})
            if any(c["index"] == option["index"] for c in item["choices"]):
                _fail(item, "duplicate-fbneo-choice-index")
            item["choices"].append(option)
        else:
            _fail(item, "unrecognized-fbneo-program-line-" + str(number))
    finish()
    if not ids:
        _fail(game, "missing-fbneo-driver-identity", "unresolved")
    if game.get("source_includes"):
        game["include_resolution"] = "Required source definitions retained; sibling include content is not inferred."
    if options.get("activation_reviewed") and ids and not game.get("source_includes"):
        # The reviewed adapter imports this native block disabled, restarts the
        # core and exposes its own complete choices. A choice is not flattened
        # into a generic memory write or preselected during catalogue import.
        game.update(status="available", reason="")
        for item in game["cheats"]:
            if item.get("status") == "invalid":
                continue
            choices = {c["index"]: c for c in item["choices"]}
            if ("source_default" not in item or 0 not in choices
                    or choices[0]["writes"] or item["source_default"] not in choices):
                _fail(item, "fbneo-explicit-disabled-choice-and-valid-default-required", "unresolved")
                continue
            if (sorted(choices) != list(range(len(choices))) or len(choices) > 127
                    or len(item["name"].encode("utf-8")) > 126
                    or len(item["code"].encode("utf-8")) > 1024 * 1024
                    or any(len(line.encode("utf-8")) >= 8192 for line in item["code"].splitlines())
                    or any(len(c["writes"]) > 512 for c in choices.values())
                    or any(w["cpu"] >= 8 or _native_integer(w["value"]) > 255
                           for c in choices.values() for w in c["writes"])):
                _fail(item, "fbneo-native-ui-cpu-byte-value-or-size-boundary", "requires_engine")
                continue
            item.update(status="available", reason="", choice_control="native-ui-after-restart")
            item["native_document"] = {"source_default": item["source_default"],
                                       "import_default": 0, "choices": item["choices"]}
    if "available_driver_names" in options and driver not in options["available_driver_names"]:
        _fail(game, "fbneo-romset-absent-from-delivered-driver-table", "requires_engine")
    return [game]


def _xml_content(node):
    # Comments can precede the first expression or interrupt it. Element.text
    # alone loses the comment tails; itertext() also includes comment prose.
    values = [node.text or ""]
    for child in node:
        if isinstance(child.tag, str):
            values.append(_xml_content(child))
        values.append(child.tail or "")
    return "".join(values)


def parse_mame_xml(data: bytes, options: dict) -> list[dict]:
    """Preserve one entire MAME XML cheat and all on/off/run/change scripts.

    Debugger expressions are never interpreted as generic RAM writes. A
    parameter stays unresolved; headings with no script are omitted.
    """
    if len(data) > MAX_MEMBER or re.search(br"<!\s*(?:DOCTYPE|ENTITY)\b", data, re.I):
        raise ValueError("oversized-mame-xml-or-forbidden-dtd")
    parser = ET.XMLParser(target=ET.TreeBuilder(insert_comments=True))
    root = ET.fromstring(data, parser=parser)
    if root.tag != "mamecheat" or root.get("version") != "1":
        raise ValueError("unsupported-mame-xml-root-or-version")
    path = PurePosixPath(options.get("path", ""))
    software_list = options.get("software_list", "")
    if not software_list and len(path.parts) > 1 and options.get("package_root_paths"):
        software_list = path.parts[0]
    driver, ids = _driver_identity(options, "mame-machine-name")
    system = options.get("system", "arcade")
    if software_list:
        system = options.get("software_systems", {}).get(software_list, "mame_" + software_list)
        if not re.fullmatch(r"[A-Za-z0-9_.-]{1,160}", system):
            system = "unknown"
        ids = [{"type": "softwarelist", "value": software_list + ":" + driver, "scheme": "mame-software-list-name"}]
    game = _game(options.get("title") or driver, system, options, ids)
    for node in root.findall("cheat"):
        scripts = node.findall("script")
        if not scripts:
            game["skipped_headings"] = game.get("skipped_headings", 0) + 1
            continue
        fragment = ET.tostring(node, encoding="unicode").strip()
        item = _cheat(node.get("desc", ""), '<mamecheat version="1">\n' + fragment + '\n</mamecheat>', "mame-xml")
        item["scripts"] = []
        for script in scripts:
            state = script.get("state", "run")
            if state not in ("on", "off", "run", "change"):
                _fail(item, "invalid-mame-script-state")
            actions = [{"expression": _xml_content(a), "condition": a.get("condition", "")} for a in script.findall("action")]
            if any(not a["expression"].strip() for a in actions):
                _fail(item, "empty-mame-action")
            item["scripts"].append({"state": state, "actions": actions,
                                     "outputs": [ET.tostring(o, encoding="unicode").strip() for o in script.findall("output")]})
        parameters = node.findall("parameter")
        if parameters:
            item["parameters"] = [{**dict(p.attrib), "items": [{"value": i.get("value", ""), "name": "".join(i.itertext())} for i in p.findall("item")]} for p in parameters]
            if item["status"] != "invalid":
                _fail(item, "mame-parameter-selection-required", "unresolved")
        comments = ["".join(n.itertext()) for n in node.findall("comment")]
        if comments:
            item["notes"] = "\n".join(comments)
        if not any(s["actions"] for s in item["scripts"]):
            if not any(s["outputs"] for s in item["scripts"]):
                game["skipped_headings"] = game.get("skipped_headings", 0) + 1
                continue
            item["kind"] = "diagnostic"
        game["cheats"].append(item)
    return [game] if game["cheats"] else []


def parse_mame_json(data: bytes, options: dict) -> list[dict]:
    """Native MAME Lua-cheat JSON; all script/device/parameter fields retained.

    Pugsy's actual JSON permits literal newlines in Lua strings and appends a
    Lua provenance comment after the JSON array. Only that recognized footer
    is accepted, using a JSON decoder boundary, never a regex over Lua code.
    Neither scripts nor expressions are evaluated, and imports stay disabled.
    """
    text = _text(data).lstrip()
    decoder = json.JSONDecoder(strict=False)
    _, end = decoder.raw_decode(text)
    footer = text[end:].strip()
    if footer and not (footer.startswith("--[[-- Cheat file downloaded from https://www.mamecheat.co.uk,")
                       and footer.endswith("]]") and "]]" not in footer[:-2]):
        raise ValueError("unrecognized-mame-json-trailing-content")
    root = json.loads(text[:end], strict=False)
    if not isinstance(root, list):
        raise ValueError("mame-json-cheat-array-required")
    path = PurePosixPath(options.get("path", ""))
    software_list = options.get("software_list", "")
    if not software_list and len(path.parts) > 1 and options.get("package_root_paths"):
        software_list = path.parts[0]
    driver, ids = _driver_identity(options, "mame-machine-name")
    system = options.get("system", "arcade")
    if software_list:
        system = options.get("software_systems", {}).get(software_list, "mame_" + software_list)
        if not re.fullmatch(r"[A-Za-z0-9_.-]{1,160}", system):
            system = "unknown"
        ids = [{"type": "softwarelist", "value": software_list + ":" + driver, "scheme": "mame-software-list-name"}]
    game = _game(options.get("title") or driver, system, options, ids)
    if footer:
        game["source_footer"] = footer
    for node in root:
        if not isinstance(node, dict) or not isinstance(node.get("desc"), str):
            raise ValueError("mame-json-native-cheat-description-required")
        scripts = node.get("script")
        if not scripts:
            game["skipped_headings"] = game.get("skipped_headings", 0) + 1
            continue
        if not isinstance(scripts, dict) or any(k not in ("on", "off", "run", "change")
                                               or not isinstance(v, str) for k, v in scripts.items()):
            raise ValueError("mame-json-native-script-state-map-required")
        if not any(v.strip() for v in scripts.values()):
            game["skipped_headings"] = game.get("skipped_headings", 0) + 1
            continue
        document = [copy.deepcopy(node)]
        code = json.dumps(document, ensure_ascii=False, separators=(",", ":"))
        item = _cheat(node["desc"], code, "mame-json", native_document=document,
                      scripts=copy.deepcopy(scripts), reason="mame-lua-cheat-interpreter-not-connected")
        if node.get("parameter") is not None:
            item["parameters"] = [copy.deepcopy(node["parameter"])]
            item["parameter_selection_required"] = True
        if isinstance(node.get("comment"), str):
            item["notes"] = node["comment"]
        if "hitbox" in node["desc"].lower() or "viewer" in node["desc"].lower():
            item["kind"] = "diagnostic"
        game["cheats"].append(item)
    return [game] if game["cheats"] else []


def _safe_path(value):
    path = PurePosixPath(value)
    if not value or path.is_absolute() or ".." in path.parts or "\\" in value or ":" in value or str(path) != value:
        raise ValueError("unsafe-archive-member-path")
    return path


def archive_members_7z(data: bytes):
    """Yield bounded regular-file bytes from 7z with Linux/macOS libarchive.

    Never extracts onto disk, follows a link or executes data. Missing host
    libarchive raises a clear error; callers must report a conditional source.
    """
    if not isinstance(data, bytes) or len(data) > MAX_INPUT:
        raise ValueError("7z-input-too-large-or-not-bytes")
    library = ctypes.util.find_library("archive")
    if not library:
        raise ValueError("host-libarchive-required-for-7z-regeneration")
    lib = ctypes.CDLL(library)
    signatures = {
        "archive_read_new": ([], ctypes.c_void_p),
        "archive_read_support_filter_all": ([ctypes.c_void_p], ctypes.c_int),
        "archive_read_support_format_7zip": ([ctypes.c_void_p], ctypes.c_int),
        "archive_read_open_memory": ([ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t], ctypes.c_int),
        "archive_read_next_header": ([ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p)], ctypes.c_int),
        "archive_entry_pathname": ([ctypes.c_void_p], ctypes.c_char_p),
        "archive_entry_size": ([ctypes.c_void_p], ctypes.c_int64),
        "archive_entry_filetype": ([ctypes.c_void_p], ctypes.c_uint),
        "archive_entry_symlink": ([ctypes.c_void_p], ctypes.c_char_p),
        "archive_entry_hardlink": ([ctypes.c_void_p], ctypes.c_char_p),
        "archive_read_data": ([ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t], ctypes.c_ssize_t),
        "archive_read_free": ([ctypes.c_void_p], ctypes.c_int),
    }
    for name, (args, result) in signatures.items():
        getattr(lib, name).argtypes = args; getattr(lib, name).restype = result
    handle = lib.archive_read_new()
    if not handle:
        raise ValueError("libarchive-allocation-failed")
    buffer = ctypes.create_string_buffer(data)
    total, count = 0, 0
    try:
        lib.archive_read_support_filter_all(handle); lib.archive_read_support_format_7zip(handle)
        if lib.archive_read_open_memory(handle, buffer, len(data)) != 0:
            raise ValueError("invalid-7z-archive")
        entry = ctypes.c_void_p()
        while True:
            result = lib.archive_read_next_header(handle, ctypes.byref(entry))
            if result == 1:  # ARCHIVE_EOF
                break
            if result != 0:
                raise ValueError("invalid-7z-entry-header")
            count += 1
            if count > MAX_MEMBERS:
                raise ValueError("7z-member-count-limit")
            name_bytes = lib.archive_entry_pathname(entry)
            if not name_bytes:
                raise ValueError("7z-member-without-name")
            name = name_bytes.decode("utf-8", errors="strict")
            kind = lib.archive_entry_filetype(entry)
            _safe_path(name.rstrip("/") if kind == 0o040000 else name)
            if lib.archive_entry_symlink(entry) or lib.archive_entry_hardlink(entry):
                raise ValueError("7z-links-forbidden")
            if kind == 0o040000:  # directory; no filesystem mutation
                continue
            if kind not in (0, 0o100000):
                raise ValueError("7z-special-file-forbidden")
            size = lib.archive_entry_size(entry)
            if not 0 <= size <= MAX_MEMBER or total + size > MAX_EXPANDED:
                raise ValueError("7z-expanded-size-limit")
            total += size
            chunks, received = [], 0
            block = ctypes.create_string_buffer(65536)
            while True:
                n = lib.archive_read_data(handle, block, len(block))
                if n < 0:
                    raise ValueError("7z-data-error")
                if not n:
                    break
                received += n
                if received > size:
                    raise ValueError("7z-member-size-mismatch")
                chunks.append(block.raw[:n])
            if received != size:
                raise ValueError("7z-truncated-member")
            yield name, b"".join(chunks)
    finally:
        lib.archive_read_free(handle)


def parse_mame_package(data: bytes, options: dict) -> list[dict]:
    """Official Pugsy ZIP -> cheat.7z -> complete nonempty XML definitions.

    Individual malformed definitions are isolated. Native Lua JSON definitions
    are preserved separately from the debugger-expression XML dialect.
    """
    if len(data) > MAX_INPUT:
        raise ValueError("mame-package-too-large")
    with zipfile.ZipFile(io.BytesIO(data)) as package:
        if len(package.infolist()) > 1000:
            raise ValueError("mame-outer-member-count-limit")
        candidates = [m for m in package.infolist() if m.filename == "cheat.7z"]
        if len(candidates) != 1 or candidates[0].file_size > MAX_INPUT:
            raise ValueError("mame-package-requires-one-bounded-cheat-7z")
        archive = package.read(candidates[0])
    records, errors = [], []
    stats = {"xml_files": 0, "json_files": 0, "json_files_not_imported": 0,
             "nonempty_xml_games": 0, "nonempty_json_games": 0,
             "json_programs": 0, "failed_xml_files": 0}
    for path, member in archive_members_7z(archive):
        if path.lower().endswith(".json"):
            stats["json_files"] += 1
            try:
                parsed = parse_mame_json(member, {**options, "path": path, "package_root_paths": True})
                if not parsed:
                    raise ValueError("json-file-without-native-cheat-program")
            except (ValueError, TypeError, RecursionError) as error:
                stats["json_files_not_imported"] += 1
                if len(errors) < 100:
                    errors.append({"path": path, "format": "mame-json", "status": "conditional", "reason": str(error)[:200]})
                continue
            records.extend(parsed); stats["nonempty_json_games"] += len(parsed)
            stats["json_programs"] += sum(len(g["cheats"]) for g in parsed)
            continue
        if not path.lower().endswith(".xml"):
            continue
        stats["xml_files"] += 1
        if b"<script" not in member:
            continue
        try:
            parsed = parse_mame_xml(member, {**options, "path": path, "package_root_paths": True})
        except (ValueError, ET.ParseError) as error:
            stats["failed_xml_files"] += 1
            if len(errors) < 100:
                errors.append({"path": path, "reason": str(error)[:200]})
            continue
        records.extend(parsed); stats["nonempty_xml_games"] += len(parsed)
    if records:
        records[0]["package_diagnostics"] = {**stats, "errors": errors}
    return records


PARSERS = {"project64-cht": parse_project64_cht, "fbneo-ini": parse_fbneo_ini,
           "mame-xml": parse_mame_xml, "mame-json": parse_mame_json, "mame-package": parse_mame_package}
