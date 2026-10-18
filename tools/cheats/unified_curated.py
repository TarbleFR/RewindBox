"""Pure, bounded importers for reviewed cheat pages and curated supplements.

These parsers only establish data structure and syntax. They do not prove core
support or gameplay effects. A caller must supply an attested game identity;
titles, page language and file names do not establish one. Unresolved entries
are retained with their reason and must not be put in an activatable catalogue.

HTML profiles select DOM entries, names and complete code blocks, never every
hexadecimal-looking string on a page. The supported selector subset is a
descendant chain of tag, #id and .class tokens. FF7 uses its actual example
table structure within an explicitly named section. No parser performs I/O.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from html.parser import HTMLParser
import io
import json
import re
import xml.etree.ElementTree as ET
import zipfile


MAX_INPUT_BYTES = 32 * 1024 * 1024
MAX_XML_BYTES = 64 * 1024 * 1024
MAX_NODES = 200_000
MAX_TEXT = 2 * 1024 * 1024
_VOID = frozenset("area base br col embed hr img input link meta param source track wbr".split())
_IGNORED = frozenset(("script", "style", "noscript", "template"))


def _text(data: bytes) -> str:
    if not isinstance(data, bytes) or len(data) > MAX_INPUT_BYTES:
        raise ValueError("input-bytes-required-or-input-too-large")
    return data.decode("utf-8-sig", errors="strict")


def _reason(item: dict, status: str, reason: str) -> None:
    # A later missing identity must not disguise a malformed program.
    if item.get("status") == "invalid" and status != "invalid":
        return
    if (item.get("status") == "requires_engine" and status == "unresolved"
            and reason in ("unreviewed-dialect", "missing-explicit-identity")):
        status = "requires_engine"
    item["status"] = status
    previous = item.get("reason", "")
    reasons = previous.split(";") if isinstance(previous, str) and previous else []
    if reason not in reasons:
        reasons.append(reason)
    item["reason"] = ";".join(reasons)


def _strong_identity(identities: list) -> bool:
    return any(isinstance(i, dict) and all(isinstance(i.get(k), str) and i[k].strip()
               for k in ("type", "value", "scheme"))
               and i["type"].lower() not in ("name", "title", "filename")
               for i in identities)


def _widths(dialect: str, system: str) -> tuple[int, int] | None:
    if dialect == "ps1-gameshark":
        return 8, 4
    if dialect == "gba-codebreaker":
        return 8, 4
    if dialect in ("gba-gameshark-v1", "gba-gameshark-v3", "gba-unknown",
                   "ds-actionreplay", "gecko", "actionReplay", "cwcheat",
                   "n64-gameshark", "gateshark", "ctrpf"):
        return 8, 8 if dialect not in ("n64-gameshark",) else 4
    return None


def _program(code: str, dialect: str, system: str) -> tuple[str, str | None, str | None]:
    """Normalize presentation only; never guess a missing/excess hex digit."""
    if not isinstance(code, str) or not code.strip() or len(code) > MAX_TEXT:
        return "" if not isinstance(code, str) else code, "invalid", "empty-or-oversized-program"
    code = code.replace("\r\n", "\n").replace("\r", "\n").strip("\ufeff \n\t")
    widths = _widths(dialect, system)
    if ("?" in code or (widths and re.search(r"[xXyYzZ]{2,}", code))
            or re.search(r"\+\s*(?:Pokemon|Pokémon|Level|Item)\s+Code", code, re.I)):
        return code, "unresolved", "unresolved-parameters"
    if widths:
        left, right = widths
        lines = []
        for raw in code.splitlines():
            if not raw.strip():
                continue
            words = raw.split()
            if len(words) == 1 and re.fullmatch(r"[0-9a-fA-F]{%d}" % (left + right), words[0]):
                words = [words[0][:left], words[0][left:]]
            if len(words) % 2 or any(not re.fullmatch(r"[0-9a-fA-F]{%d}" % (left if i % 2 == 0 else right), word)
                                     for i, word in enumerate(words)):
                return code, "invalid", "invalid-hex-word-width-or-text"
            lines.extend(words[i].upper() + " " + words[i + 1].upper() for i in range(0, len(words), 2))
        normalized = "\n".join(lines)
        if dialect == "gba-unknown":
            return normalized, "unresolved", "gba-dialect-not-attested"
        return normalized, None, None
    patterns = {
        "gb-gameshark": r"[0-9A-F]{8}",
        "gb-gamegenie": r"[0-9A-F]{3}-[0-9A-F]{3}(?:-[0-9A-F]{3})?",
        "nes-gamegenie": r"[APZLGITYEOXUKSVN]{6}(?:[APZLGITYEOXUKSVN]{2})?",
        "snes-gamegenie": r"[0-9A-F]{4}-[0-9A-F]{4}",
        "snes-par": r"[0-9A-F]{8}",
    }
    if dialect in patterns:
        normalized = "\n".join(line.strip().upper() for line in code.splitlines() if line.strip())
        if not all(re.fullmatch(patterns[dialect], line) for line in normalized.splitlines()):
            return code, "invalid", "invalid-code-syntax"
        return normalized, None, None
    return code, "unresolved", "unreviewed-dialect"


def _cheat(name: str, code: str, options: dict, **extra) -> dict:
    dialect = options.get("dialect", "")
    result = {"name": str(name).strip(), "code": code, "dialect": dialect,
              "dependencies": [], "parameters": [], **copy.deepcopy(extra)}
    result["code"], status, reason = _program(code, dialect, options.get("system", ""))
    if status:
        _reason(result, status, reason)
    if not result["name"]:
        _reason(result, "unresolved", "missing-cheat-name")
    if options.get("source_url"):
        result.setdefault("provenance", []).append({"url": options["source_url"]})
    return result


def _record(options: dict, cheats: list[dict], *, title: str | None = None) -> dict:
    result = {"title": title if title is not None else options.get("title", ""),
              "system": options.get("system", ""),
              "identities": copy.deepcopy(options.get("identities", [])),
              "regions": copy.deepcopy(options.get("regions", [])),
              "languages": copy.deepcopy(options.get("languages", [])),
              "revision": options.get("revision", ""), "cheats": cheats}
    if not result["title"] or not result["system"]:
        _reason(result, "unresolved", "missing-game-title-or-system")
    if not _strong_identity(result["identities"]):
        _reason(result, "unresolved", "missing-explicit-identity")
    return result


def parse_curated(data: bytes, options: dict) -> list[dict]:
    """Validate reviewed JSON records, preserving unknown attributes verbatim.

    Accepts a game list, one game object, or {"games": [...]}. Structural errors
    raise ValueError; incomplete programs remain invalid/unresolved records.
    Options are defaults only; they never overwrite a per-game value.
    """
    root = json.loads(_text(data))
    records = root if isinstance(root, list) else root.get("games", [root]) if isinstance(root, dict) else None
    if not isinstance(records, list):
        raise ValueError("curated-games-list-required")
    output = []
    for record in records:
        if isinstance(record, dict) and options.get("select_source_id") and record.get("source_id") != options["select_source_id"]:
            continue
        if not isinstance(record, dict) or not isinstance(record.get("cheats"), list):
            raise ValueError("curated-game-object-with-cheats-required")
        result = copy.deepcopy(record)
        for key in ("title", "system", "identities", "regions", "languages", "revision"):
            result.setdefault(key, copy.deepcopy(options.get(key, [] if key in ("identities", "regions", "languages") else "")))
        if not all(isinstance(result[k], list) for k in ("identities", "regions", "languages")):
            raise ValueError("curated-identity-region-language-lists-required")
        if not isinstance(result["title"], str) or not isinstance(result["system"], str):
            raise ValueError("curated-game-title-system-strings-required")
        for cheat in result["cheats"]:
            if not isinstance(cheat, dict) or not isinstance(cheat.get("name"), str) or not isinstance(cheat.get("code"), str):
                raise ValueError("curated-cheat-name-code-strings-required")
            cheat.setdefault("dialect", options.get("dialect", ""))
            if result.get("source_id"):
                for provenance in cheat.get("provenance", []):
                    if isinstance(provenance, dict):
                        provenance.setdefault("source_id", result["source_id"])
            for key in ("dependencies", "parameters"):
                cheat.setdefault(key, [])
                if not isinstance(cheat[key], list):
                    raise ValueError("curated-dependency-parameter-lists-required")
            # Import is data discovery; never copy a source's enabled state.
            for key in ("enabled", "active"):
                if key in cheat:
                    cheat[key] = False
            cheat["code"], status, reason = _program(cheat["code"], cheat["dialect"], result["system"])
            if status:
                _reason(cheat, status, reason)
            if cheat["parameters"]:
                _reason(cheat, "unresolved", "parameters-require-resolution")
        # Reviewed title/edition candidates stay selectable with confirmation;
        # this is not an invented hash or an automatic identity match.
        if (not _strong_identity(result["identities"])
                and result.get("matching_policy") != "title-edition-candidate"):
            _reason(result, "unresolved", "missing-explicit-identity")
        output.append(result)
    return output


@dataclass(eq=False)
class _Node:
    tag: str
    attrs: dict = field(default_factory=dict)
    children: list = field(default_factory=list)
    parent: "_Node | None" = None

    def nodes(self):
        for child in self.children:
            if isinstance(child, _Node):
                yield child
                yield from child.nodes()

    def text(self) -> str:
        if self.tag in _IGNORED:
            return ""
        text = "".join(child.text() if isinstance(child, _Node) else child for child in self.children)
        if self.tag in ("br",):
            return "\n"
        return text + ("\n" if self.tag in ("p", "div", "pre", "li", "tr", "h1", "h2", "h3", "h4") else "")


class _DOM(HTMLParser):
    def __init__(self, text: str):
        super().__init__(convert_charrefs=True)
        self.root = _Node("document")
        self.stack = [self.root]
        self.count = 0
        self.feed(text)
        self.close()

    def handle_starttag(self, tag, attrs):
        self.count += 1
        if self.count > MAX_NODES or len(self.stack) > 256:
            raise ValueError("html-node-or-depth-limit")
        # Common optional end tags in legacy cheat tables.
        if tag in ("td", "th") and self.stack[-1].tag in ("td", "th"):
            self.stack.pop()
        if tag == "tr":
            while self.stack[-1].tag in ("td", "th", "tr"):
                self.stack.pop()
        node = _Node(tag, dict(attrs), parent=self.stack[-1])
        self.stack[-1].children.append(node)
        if tag not in _VOID:
            self.stack.append(node)

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag not in _VOID:
            self.handle_endtag(tag)

    def handle_endtag(self, tag):
        for index in range(len(self.stack) - 1, 0, -1):
            if self.stack[index].tag == tag:
                del self.stack[index:]
                break

    def handle_data(self, data):
        self.stack[-1].children.append(data)


def _matches(node: _Node, selector: str) -> bool:
    parts = re.findall(r"(?:^[a-zA-Z][\w-]*|[.#][\w-]+)", selector)
    if not parts or "".join(parts) != selector:
        raise ValueError("unsupported-html-selector:" + selector)
    for part in parts:
        if part.startswith(".") and part[1:] not in node.attrs.get("class", "").split():
            return False
        if part.startswith("#") and node.attrs.get("id") != part[1:]:
            return False
        if part[0] not in ".#" and node.tag != part.lower():
            return False
    return True


def _visible(node: _Node) -> bool:
    while node is not None:
        if node.tag in _IGNORED:
            return False
        node = node.parent
    return True


def _select(root: _Node, selector: str) -> list[_Node]:
    if not isinstance(selector, str) or not selector.strip():
        raise ValueError("explicit-html-selector-required")
    selectors = selector.split()
    # Validate the whole expression even when there are no nodes.
    for token in selectors:
        _matches(_Node("selector-validation"), token)
    selected = []
    for node in root.nodes():
        if not _visible(node) or not _matches(node, selectors[-1]):
            continue
        ancestor = node.parent
        for token in reversed(selectors[:-1]):
            while ancestor is not None and ancestor is not root and not _matches(ancestor, token):
                ancestor = ancestor.parent
            if ancestor is None or ancestor is root:
                break
            ancestor = ancestor.parent
        else:
            selected.append(node)
    return selected


def _single_text(root: _Node, selector: str) -> str:
    selected = _select(root, selector)
    return selected[0].text().strip() if len(selected) == 1 else ""


def parse_html_profile(data: bytes, options: dict) -> list[dict]:
    """Import an explicitly profiled page (Pokemon/SquarePalace/Ethereal/PSX).

    Required: entry_selector, name_selector, code_selector, system and dialect.
    section_selector optionally restricts scope. Several selected code nodes are
    ambiguous unless combine_code_nodes=True explicitly declares one program.
    An entry with no selected code is a heading and produces no cheat.
    """
    dom = _DOM(_text(data))
    for key in ("entry_selector", "name_selector", "code_selector"):
        if not options.get(key):
            raise ValueError("missing-profile-field:" + key)
    scopes = _select(dom.root, options["section_selector"]) if options.get("section_selector") else [dom.root]
    cheats = []
    seen = set()
    for scope in scopes:
        for entry in _select(scope, options["entry_selector"]):
            if id(entry) in seen:
                continue
            seen.add(id(entry))
            code_nodes = _select(entry, options["code_selector"])
            if not code_nodes:
                continue
            name = _single_text(entry, options["name_selector"])
            code = "\n".join(n.text().strip() for n in code_nodes)
            cheat = _cheat(name, code, options)
            if len(code_nodes) != 1 and not options.get("combine_code_nodes", False):
                _reason(cheat, "unresolved", "ambiguous-multiple-code-blocks")
            if options.get("notes_selector"):
                cheat["notes"] = "\n".join(n.text().strip() for n in _select(entry, options["notes_selector"]))
            cheats.append(cheat)
    return [_record(options, cheats)] if cheats else []


def parse_pokemon_html(data: bytes, options: dict) -> list[dict]:
    return parse_html_profile(data, options)


def parse_squarepalace(data: bytes, options: dict) -> list[dict]:
    return parse_html_profile(data, options)


def parse_ethereal(data: bytes, options: dict) -> list[dict]:
    return parse_html_profile(data, options)


def parse_psxdatacenter(data: bytes, options: dict) -> list[dict]:
    return parse_html_profile(data, options)


def _nearest(node: _Node, tag: str) -> _Node | None:
    node = node.parent
    while node is not None and node.tag != tag:
        node = node.parent
    return node


def parse_ff7(data: bytes, options: dict) -> list[dict]:
    """FF7.fr examples within one exact h2 section, with row/cell boundaries.

    section_heading is mandatory. The shared explanatory introduction is never
    scanned. Template cells are retained unresolved when include_templates=True.
    The caller must attest French release serials/hashes separately.
    """
    if not isinstance(options.get("section_heading"), str) or not options["section_heading"].strip():
        raise ValueError("ff7-explicit-section-heading-required")
    profile = {"title": "Final Fantasy VII", "system": "psx", "dialect": "ps1-gameshark", **options}
    nodes = [n for n in _DOM(_text(data)).root.nodes() if _visible(n)]
    headings = [i for i, n in enumerate(nodes) if n.tag == "h2" and n.text().strip() == options["section_heading"].strip()]
    if len(headings) != 1:
        raise ValueError("ff7-section-missing-or-ambiguous")
    start = headings[0]
    end = next((i for i in range(start + 1, len(nodes)) if nodes[i].tag == "h2"), len(nodes))
    cheats = []
    for table in (n for n in nodes[start + 1:end] if n.tag == "table"):
        previous = []
        headers = []
        for row in (n for n in table.nodes() if n.tag == "tr" and _nearest(n, "table") is table):
            cells = [n for n in row.children if isinstance(n, _Node) and n.tag in ("td", "th")]
            if not cells:
                continue
            if all(c.tag == "th" for c in cells):
                headers = [c.text().strip() for c in cells]
            for column, cell in enumerate(cells):
                programs = _select(cell, "a.st7")
                if programs:
                    name = previous[column].text().strip() if column < len(previous) else ""
                    cheat = _cheat(name, "\n".join(n.text().strip() for n in programs), profile)
                    if len(programs) > 1:
                        _reason(cheat, "unresolved", "ambiguous-multiple-code-blocks")
                    cheats.append(cheat)
                elif options.get("include_templates", False) and re.fullmatch(r"[0-9A-Fa-f]{8}\s+[?xyXY]{4}(?:\s+[0-9A-Fa-f]{8}\s+[?xyXY]{4})*", cell.text().strip()):
                    labels = [cells[0].text().strip()] if column else []
                    if column < len(headers):
                        labels.append(headers[column])
                    cheats.append(_cheat(" — ".join(labels) or options["section_heading"], cell.text().strip(), profile))
            previous = cells
    return [_record(profile, cheats)] if cheats else []


def _xml(data: bytes):
    if len(data) > MAX_XML_BYTES or re.search(br"<!\s*(?:DOCTYPE|ENTITY)\b", data, re.I):
        raise ValueError("xlsx-xml-too-large-or-dtd")
    return ET.fromstring(data)


def _xlsx_rows(data: bytes, sheet_name: str):
    if not isinstance(data, bytes) or len(data) > MAX_INPUT_BYTES:
        raise ValueError("xlsx-input-too-large")
    ns = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
    with zipfile.ZipFile(io.BytesIO(data)) as package:
        if len(package.infolist()) > 1000 or sum(f.file_size for f in package.infolist()) > 256 * 1024 * 1024:
            raise ValueError("xlsx-expanded-size-or-file-count")
        def part(name):
            info = package.getinfo(name)
            if info.file_size > MAX_XML_BYTES:
                raise ValueError("xlsx-part-too-large")
            return _xml(package.read(info))
        strings = []
        if "xl/sharedStrings.xml" in package.namelist():
            strings = ["".join(si.itertext()) for si in part("xl/sharedStrings.xml").findall("m:si", ns)]
        relation_ns = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"
        sheets = part("xl/workbook.xml").findall("m:sheets/m:sheet", ns)
        selected = [s for s in sheets if s.attrib.get("name") == sheet_name]
        if len(selected) != 1:
            return []
        targets = {r.attrib["Id"]: r.attrib["Target"] for r in part("xl/_rels/workbook.xml.rels")}
        target = targets.get(selected[0].attrib[relation_ns], "")
        # Only workbook-local worksheets, never external relationships or paths.
        target = target[1:] if target.startswith("/xl/") else "xl/" + target
        if not re.fullmatch(r"xl/worksheets/[A-Za-z0-9_.-]+\.xml", target):
            raise ValueError("xlsx-nonlocal-worksheet")
        rows = []
        for row in part(target).findall("m:sheetData/m:row", ns):
            cells = {}
            for cell in row.findall("m:c", ns):
                column = re.sub(r"\d", "", cell.attrib.get("r", ""))
                kind = cell.attrib.get("t", "")
                value = cell.findtext("m:v", default="", namespaces=ns)
                if kind == "s":
                    value = strings[int(value)]
                elif kind == "inlineStr":
                    value = "".join(cell.find("m:is", ns).itertext())
                # Formula results and numbers must not be mistaken for code text.
                cells[column] = {"value": value, "text": kind in ("s", "inlineStr", "str"),
                                 "formula": cell.find("m:f", ns) is not None}
            rows.append((row.attrib.get("r", ""), cells))
        return rows


def parse_delta_xlsx(data: bytes, options: dict) -> list[dict]:
    """Delta's GBA table with parent+choice semantics and scoped metadata.

    game_profiles maps each exact worksheet game name to an attested identity,
    region, revision and explicit GBA dialect. Without those, data stays
    unresolved. Only recognized `+ Pokemon Code` / `+ Level Code` groups are
    assembled. Headers without a program never become executable entries.
    """
    rows = _xlsx_rows(data, options.get("sheet", "GBA"))
    expected = ["Game Name", "Cheat Name", "Code", "Code Type", "Attribution", "Notes"]
    if not rows or [rows[0][1].get(k, {}).get("value", "") for k in "ABCDEF"] != expected:
        raise ValueError("delta-unrecognized-header")
    attribution = {}
    for _, cells in _xlsx_rows(data, "Attribution Key"):
        symbol = cells.get("A", {}).get("value", "")
        host = cells.get("B", {}).get("value", "")
        if symbol and host:
            attribution[symbol] = host if host.startswith(("http://", "https://")) else "https://" + host
    records, current, group = [], None, None
    profile = {}
    for number, cells in rows[1:]:
        values = {key: value["value"].strip() for key, value in cells.items()}
        if not any(values.values()):
            group = None
            continue
        if values.get("A"):
            title = values["A"]
            profile = {"system": "gba", "dialect": "gba-unknown", **options.get("game_profiles", {}).get(title, {})}
            if options.get("source_url"):
                profile["source_url"] = options["source_url"]
            current = _record(profile, [], title=title)
            records.append(current)
            group = None
        if current is None:
            continue
        name, code = values.get("B", ""), values.get("C", "")
        explicit_type = values.get("D", "")
        symbol = values.get("E", "")
        notes = values.get("F", "")
        if explicit_type:
            group = None
        reference = re.search(r"\+\s*((?:Pokemon|Pokémon|Level) Code)\s*$", code, re.I)
        if reference or (name and not code and explicit_type):
            group = {"name": name, "prefix": code[:reference.start()].strip() if reference else "",
                     "parameter": reference[1] if reference else "", "symbol": symbol,
                     "notes": notes, "row": number,
                     "literal_prefix": not reference or (cells.get("C", {}).get("text") and not cells.get("C", {}).get("formula"))}
            if reference:
                template = _cheat(name, code, profile, parameters=[reference[1]], notes=notes,
                                  source_row=number)
                if symbol in attribution:
                    template.setdefault("provenance", []).append({"url": attribution[symbol]})
                if not group["literal_prefix"]:
                    _reason(template, "invalid", "xlsx-code-must-be-literal-text")
                current["cheats"].append(template)
            continue
        if not code:
            continue
        if group:
            name = group["name"] + " — " + name
            if group["prefix"]:
                code = group["prefix"] + "\n" + code
            symbol = symbol or group["symbol"]
            notes = "\n".join(n for n in (group["notes"], notes) if n)
        cheat = _cheat(name, code, profile, source_row=number, notes=notes)
        cell = cells.get("C", {})
        if not cell.get("text") or cell.get("formula"):
            _reason(cheat, "invalid", "xlsx-code-must-be-literal-text")
        if group and not group["literal_prefix"]:
            _reason(cheat, "invalid", "xlsx-parent-code-must-be-literal-text")
        if symbol in attribution:
            cheat.setdefault("provenance", []).append({"url": attribution[symbol]})
        current["cheats"].append(cheat)
    return records


PARSERS = {
    "curated-json": parse_curated,
    "ff7-html": parse_ff7,
    "html-profile": parse_html_profile,
    "delta-xlsx": parse_delta_xlsx,
}

