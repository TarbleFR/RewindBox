#!/usr/bin/env python3
"""Fetch only the native runtimes NeoStation reuses from the Build 350 IPA.

The published NeoStation 0.0.1 IPA (Build 350) also contains the old KartPad
donor, whose KartPadRuntime links code translated from Mario Kart Wii, and
the Dusklight Core, built from the Twilight Princess decompilation. Neither
may enter a GitHub Actions job, cache or artifact any more (KartPad removed
on 19 October 2026, Dusklight on 20 October 2026). Instead of downloading the
whole IPA, this reads its ZIP central directory with HTTP range requests,
checks it against a pinned SHA-256, then downloads and decompresses only the
members prepare_fast_native_runtime.py needs (Dolphin, RPCS3 and ARMSX2
Cores, the Dolphin Sys tree, Dolphin touch resources and cacert.pem).

No byte range of a KartPad or Dusklight member is ever requested: requests are planned
from the pinned central directory, ranges that would cover a refused member
are never merged, and every response must be a 206 for exactly the bytes
asked. The selected members must reproduce a pinned aggregate digest of
their names and SHA-256 values. The output is a small IPA-shaped ZIP that
prepare_fast_native_runtime.py consumes unchanged.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import struct
import urllib.request
import zipfile
import zlib
from dataclasses import dataclass
from pathlib import Path

DONOR_URL = "https://github.com/TarbleFR/neostation-ios/releases/download/0.0.1/NeoStation.ipa"
DONOR_BYTES = 143538718
CENTRAL_DIRECTORY_SHA256 = "777010fd3a2d5ae1b3b01d64ef6a99dbe77768948e7f94d8936b2e3e06d4311d"
SELECTED_AGGREGATE_SHA256 = "2f73382bc15c56f425e19aa29afd11e6a29a4c547e1aa7f40f29547204a85536"
SELECTED_MEMBERS = 2656
APP = "Payload/NeoStation.app/"

ALLOWED_PREFIXES = (
    "Frameworks/DolphinCore.framework/",
    "Frameworks/ARMSX2Core.framework/",
    "Sys/",
)
ALLOWED_FILES = (
    "Frameworks/libRPCS3Core.dylib",
    "cacert.pem",
)
TOUCH_PREFIX = "Frameworks/dolphin_internal_bridge.framework/"
# Members of the old KartPad donor and its runtime resources copied to the
# application root, and of the removed Dusklight Core (framework, notices,
# identity). Their bytes are never requested.
REFUSED = re.compile(
    r"(?i)(kartpad|dusklight|^wii_bootstrap/|^dsp_coef\.bin$|^initial_pipeline_cache\.db$)")

MAX_GAP = 4 * 1024 * 1024


@dataclass(frozen=True)
class Member:
    name: str
    method: int
    crc: int
    compressed: int
    size: int
    header_offset: int
    external_attr: int


def wanted(relative: str) -> bool:
    if REFUSED.search(relative):
        return False
    if relative in ALLOWED_FILES or relative.startswith(ALLOWED_PREFIXES):
        return True
    if relative.startswith(TOUCH_PREFIX):
        rest = relative[len(TOUCH_PREFIX):]
        top = rest.split("/", 1)[0]
        return top.endswith(".png") or top.endswith(".nib")
    return False


class RangeReader:
    def __init__(self, url: str, size: int, opener=None):
        self.url = url
        self.size = size
        self.opener = opener or urllib.request.build_opener()
        self.requests: list[tuple[int, int]] = []

    def read(self, start: int, end: int) -> bytes:
        """Return bytes [start, end) and refuse anything but that exact range."""
        if not 0 <= start < end <= self.size:
            raise SystemExit(f"ERROR: range {start}-{end} outside the pinned donor")
        request = urllib.request.Request(
            self.url, headers={"Range": f"bytes={start}-{end - 1}",
                               "User-Agent": "neostation-native-donor-subset"})
        with self.opener.open(request, timeout=120) as response:
            status = getattr(response, "status", None) or response.getcode()
            if status != 206:
                # A 200 would stream the whole IPA, KartPad donor included.
                raise SystemExit(f"ERROR: server ignored the range request (HTTP {status})")
            content_range = response.headers.get("Content-Range", "")
            if content_range != f"bytes {start}-{end - 1}/{self.size}":
                raise SystemExit(f"ERROR: unexpected Content-Range {content_range!r}")
            data = response.read(end - start + 1)
        if len(data) != end - start:
            raise SystemExit("ERROR: short range response")
        self.requests.append((start, end))
        return data


def central_directory(reader: RangeReader,
                      expected_sha256: str = CENTRAL_DIRECTORY_SHA256) -> tuple[int, list[Member]]:
    # Read exactly the 22-byte end record: a wider tail could reach member
    # data in front of a small central directory. The IPA has no ZIP comment.
    tail = reader.read(reader.size - 22, reader.size)
    (signature, disk, cd_disk, entries_here, entries, cd_size, cd_offset,
     comment) = struct.unpack("<IHHHHIIH", tail)
    if signature != 0x06054B50 or comment:
        raise SystemExit("ERROR: end of central directory not found")
    if (disk or cd_disk or entries_here != entries or
            cd_offset + cd_size != reader.size - 22):
        raise SystemExit("ERROR: unsupported or inconsistent donor ZIP layout")
    directory = reader.read(cd_offset, cd_offset + cd_size)
    if hashlib.sha256(directory).hexdigest() != expected_sha256:
        raise SystemExit("ERROR: donor central directory differs from the pinned Build 350 IPA")
    members = []
    cursor = 0
    for _ in range(entries):
        (signature, _, _, flags, method, _, _, crc, compressed, size, name_length,
         extra_length, comment_length, _, _, external_attr,
         header_offset) = struct.unpack_from("<IHHHHHHIIIHHHHHII", directory, cursor)
        if signature != 0x02014B50 or flags & 0x1:
            raise SystemExit("ERROR: invalid or encrypted central directory entry")
        name = directory[cursor + 46:cursor + 46 + name_length].decode("utf-8")
        members.append(Member(name, method, crc, compressed, size, header_offset, external_attr))
        cursor += 46 + name_length + extra_length + comment_length
    if cursor != len(directory):
        raise SystemExit("ERROR: trailing bytes in the donor central directory")
    return cd_offset, members


def plan(members: list[Member], directory_offset: int
         ) -> tuple[list[Member], list[tuple[int, int, list[Member]]]]:
    """Group selected members into ranges; a member's record ends where the
    next one (or the central directory) starts."""
    ordered = sorted(members, key=lambda item: item.header_offset)
    bounds = {}
    for index, member in enumerate(ordered):
        end = ordered[index + 1].header_offset if index + 1 < len(ordered) else directory_offset
        bounds[member.name] = (member.header_offset, end)
    selected = []
    refused_spans = []
    for member in ordered:
        if not member.name.startswith(APP):
            refused_spans.append(bounds[member.name])
            continue
        relative = member.name[len(APP):]
        if member.name.endswith("/"):
            continue
        if wanted(relative):
            selected.append(member)
        elif REFUSED.search(relative):
            refused_spans.append(bounds[member.name])
    ranges: list[tuple[int, int, list[Member]]] = []
    for member in selected:
        start, end = bounds[member.name]
        if ranges:
            current_start, current_end, items = ranges[-1]
            gap_clear = not any(span_start < start and span_end > current_end
                                for span_start, span_end in refused_spans)
            if start - current_end <= MAX_GAP and gap_clear:
                ranges[-1] = (current_start, end, items + [member])
                continue
        ranges.append((start, end, [member]))
    for start, end, _ in ranges:
        for span_start, span_end in refused_spans:
            if span_start < end and span_end > start:
                raise SystemExit("ERROR: planned range overlaps a refused donor member")
    return selected, ranges


def member_bytes(block: bytes, block_start: int, member: Member) -> bytes:
    offset = member.header_offset - block_start
    (signature, _, _, method, _, _, _, _, _, name_length,
     extra_length) = struct.unpack_from("<IHHHHHIIIHH", block, offset)
    if signature != 0x04034B50 or method != member.method:
        raise SystemExit(f"ERROR: invalid local header for {member.name}")
    data_start = offset + 30 + name_length + extra_length
    payload = block[data_start:data_start + member.compressed]
    if len(payload) != member.compressed:
        raise SystemExit(f"ERROR: truncated data for {member.name}")
    if member.method == 0:
        data = payload
    elif member.method == 8:
        data = zlib.decompress(payload, -15)
    else:
        raise SystemExit(f"ERROR: unsupported compression for {member.name}")
    if len(data) != member.size or zlib.crc32(data) & 0xFFFFFFFF != member.crc:
        raise SystemExit(f"ERROR: size/CRC mismatch for {member.name}")
    return data


def aggregate(lines: list[str]) -> str:
    return hashlib.sha256("".join(lines).encode("utf-8")).hexdigest()


def fetch(output: Path, report: Path | None, reader: RangeReader,
          expected_aggregate: str = SELECTED_AGGREGATE_SHA256,
          expected_members: int = SELECTED_MEMBERS,
          expected_directory: str = CENTRAL_DIRECTORY_SHA256) -> dict:
    if output.exists():
        raise SystemExit(f"ERROR: output already exists: {output}")
    directory_offset, members = central_directory(reader, expected_directory)
    selected, ranges = plan(members, directory_offset)
    lines = []
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        for start, end, items in ranges:
            block = reader.read(start, end)
            for member in items:
                data = member_bytes(block, start, member)
                lines.append(f"{hashlib.sha256(data).hexdigest()}  {member.name}\n")
                info = zipfile.ZipInfo(member.name, date_time=(1980, 1, 1, 0, 0, 0))
                info.external_attr = member.external_attr
                info.compress_type = zipfile.ZIP_DEFLATED
                archive.writestr(info, data)
    lines.sort(key=lambda line: line.split("  ", 1)[1])
    digest = aggregate(lines)
    result = {
        "donorUrl": reader.url,
        "donorBytes": reader.size,
        "centralDirectorySha256": expected_directory,
        "selectedMembers": len(lines),
        "selectedAggregateSha256": digest,
        "requestedRanges": len(reader.requests),
        "requestedBytes": sum(end - start for start, end in reader.requests),
    }
    if report:
        report.parent.mkdir(parents=True, exist_ok=True)
        report.write_text(json.dumps(result, indent=2) + "\n" + "".join(lines))
    if digest != expected_aggregate or len(lines) != expected_members:
        output.unlink()
        raise SystemExit(f"ERROR: selected donor members differ from the pin ({digest}, {len(lines)})")
    with zipfile.ZipFile(output) as archive:
        leaked = [name for name in archive.namelist() if REFUSED.search(name[len(APP):])]
    if leaked:
        output.unlink()
        raise SystemExit(f"ERROR: refused members in the subset: {leaked[:3]}")
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path, help="subset IPA to write")
    parser.add_argument("--report", type=Path)
    parser.add_argument("--url", default=DONOR_URL)
    args = parser.parse_args()
    print(json.dumps(fetch(args.output, args.report, RangeReader(args.url, DONOR_BYTES)), indent=2))
