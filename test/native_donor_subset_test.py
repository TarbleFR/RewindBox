"""The native donor subset never requests a byte of a KartPad or Dusklight member.

A synthetic IPA interleaves allowed native members with KartPad donor members,
Dusklight Core members (removed on 20 October 2026) and root runtime resources. A local HTTP server honours byte ranges and records
every range it serves. The fetcher must:
- serve only planned 206 ranges, none intersecting a refused member's record;
- reproduce the allowed members byte for byte, with permissions;
- refuse a server that answers 200 (whole file), a different central
  directory, a different aggregate and a planned range that would touch a
  refused member.
"""
from __future__ import annotations

import hashlib
import http.server
import importlib.util
import io
import os
import struct
import sys
import tempfile
import threading
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "fetch_native_donor_subset", ROOT / "build-utils/fetch_native_donor_subset.py")
fetcher = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = fetcher
spec.loader.exec_module(fetcher)

APP = fetcher.APP
MEMBERS = [
    ("Frameworks/DolphinCore.framework/DolphinCore", os.urandom(300_000), 0o755),
    ("Frameworks/KartPadRuntime.framework/KartPadRuntime", b"func_80005F34 RVL_SDK " * 20_000, 0o755),
    ("Frameworks/libRPCS3Core.dylib", os.urandom(200_000), 0o755),
    ("KartPad-native-identity.json", b'{"mode":"official-ipa-donor"}', 0o644),
    ("Sys/GC/font.bin", b"font" * 1000, 0o644),
    ("wii_bootstrap/shared2/wc24/misc.bin", b"\0" * 4096, 0o644),
    ("Frameworks/App.framework/App", os.urandom(50_000), 0o755),
    ("Frameworks/dolphin_internal_bridge.framework/Pad.png", b"\x89PNG" + os.urandom(100), 0o644),
    ("Frameworks/dolphin_internal_bridge.framework/dolphin_internal_bridge", os.urandom(1000), 0o755),
    ("Frameworks/dolphin_internal_bridge.framework/Touch.nib/objects.nib", b"nib" * 50, 0o644),
    ("dsp_coef.bin", b"coef" * 100, 0o644),
    ("Dusklight-native-identity.json", b'{"abi_version":7}', 0o644),
    ("Frameworks/DusklightCore.framework/DusklightCore", os.urandom(20_000), 0o755),
    ("Dusklight-Licenses/aurora-LICENSE", b"MIT" * 100, 0o644),
    ("cacert.pem", b"-----BEGIN CERTIFICATE-----", 0o644),
    ("Frameworks/KartPadCore.framework/KartPadCore", os.urandom(10_000), 0o755),
]
ALLOWED = {
    "Frameworks/DolphinCore.framework/DolphinCore", "Frameworks/libRPCS3Core.dylib",
    "Sys/GC/font.bin", "Frameworks/dolphin_internal_bridge.framework/Pad.png",
    "Frameworks/dolphin_internal_bridge.framework/Touch.nib/objects.nib",
    "cacert.pem",
}


def build_ipa() -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for index, (name, data, mode) in enumerate(MEMBERS):
            info = zipfile.ZipInfo(APP + name, date_time=(2026, 1, 1, 0, 0, 0))
            info.external_attr = mode << 16
            info.compress_type = zipfile.ZIP_DEFLATED if index % 2 else zipfile.ZIP_STORED
            archive.writestr(info, data)
    return buffer.getvalue()


def spans(ipa: bytes) -> dict[str, tuple[int, int]]:
    archive = zipfile.ZipFile(io.BytesIO(ipa))
    ordered = sorted(archive.infolist(), key=lambda item: item.header_offset)
    directory = struct.unpack_from("<I", ipa, ipa.rfind(b"PK\x05\x06") + 16)[0]
    result = {}
    for index, info in enumerate(ordered):
        end = ordered[index + 1].header_offset if index + 1 < len(ordered) else directory
        result[info.filename[len(APP):]] = (info.header_offset, end)
    return result


class Server(http.server.ThreadingHTTPServer):
    allow_reuse_address = True


def serve(ipa: bytes, honour_ranges: bool = True):
    served: list[tuple[int, int]] = []

    class Handler(http.server.BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_GET(self):
            header = self.headers.get("Range")
            if not honour_ranges or not header:
                self.send_response(200)
                self.send_header("Content-Length", str(len(ipa)))
                self.end_headers()
                served.append((0, len(ipa)))
                try:
                    self.wfile.write(ipa)
                except ConnectionError:
                    pass  # the fetcher hangs up as soon as it sees the 200
                return
            start, end = (int(part) for part in header.removeprefix("bytes=").split("-"))
            body = ipa[start:end + 1]
            served.append((start, end + 1))
            self.send_response(206)
            self.send_header("Content-Range", f"bytes {start}-{end}/{len(ipa)}")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    server = Server(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, served


def refused(call, needle: str) -> None:
    try:
        call()
    except SystemExit as error:
        assert needle in str(error), error
        return
    raise AssertionError("expected refusal: " + needle)


ipa = build_ipa()
size, offset = struct.unpack_from("<II", ipa, ipa.rfind(b"PK\x05\x06") + 12)
directory_sha = hashlib.sha256(ipa[offset:offset + size]).hexdigest()
lines = sorted((f"{hashlib.sha256(data).hexdigest()}  {APP + name}\n" for name, data, _ in MEMBERS
                if name in ALLOWED), key=lambda line: line.split("  ", 1)[1])
aggregate = fetcher.aggregate(lines)
member_spans = spans(ipa)
refused_spans = [span for name, span in member_spans.items()
                 if fetcher.REFUSED.search(name)]
assert len(refused_spans) == 8, refused_spans

with tempfile.TemporaryDirectory() as temporary:
    temp = Path(temporary)
    server, served = serve(ipa)
    url = f"http://127.0.0.1:{server.server_address[1]}/NeoStation.ipa"
    reader = fetcher.RangeReader(url, len(ipa),
                                 opener=urllib.request.build_opener(
                                     urllib.request.ProxyHandler({})))
    result = fetcher.fetch(temp / "subset.ipa", temp / "report.txt", reader,
                           expected_aggregate=aggregate, expected_members=len(ALLOWED),
                           expected_directory=directory_sha)
    assert result["selectedMembers"] == len(ALLOWED)
    for start, end in served:
        for span_start, span_end in refused_spans:
            assert not (start < span_end and end > span_start), ("refused bytes served", start, end)
    with zipfile.ZipFile(temp / "subset.ipa") as subset:
        names = {name[len(APP):] for name in subset.namelist()}
        assert names == ALLOWED, names
        for name, data, mode in MEMBERS:
            if name in ALLOWED:
                assert subset.read(APP + name) == data
                assert subset.getinfo(APP + name).external_attr >> 16 == mode
    server.shutdown()

    # A server that ignores Range would stream the whole IPA: refuse it.
    server, served = serve(ipa, honour_ranges=False)
    url = f"http://127.0.0.1:{server.server_address[1]}/NeoStation.ipa"
    reader = fetcher.RangeReader(url, len(ipa), opener=urllib.request.build_opener(
        urllib.request.ProxyHandler({})))
    refused(lambda: fetcher.fetch(temp / "whole.ipa", None, reader, aggregate, len(ALLOWED),
                                  directory_sha), "ignored the range request")
    assert not (temp / "whole.ipa").exists()
    server.shutdown()

    server, served = serve(ipa)
    url = f"http://127.0.0.1:{server.server_address[1]}/NeoStation.ipa"
    opener = urllib.request.build_opener(
        urllib.request.ProxyHandler({}))
    refused(lambda: fetcher.fetch(temp / "other.ipa", None, fetcher.RangeReader(url, len(ipa), opener),
                                  aggregate, len(ALLOWED), "0" * 64), "central directory differs")
    refused(lambda: fetcher.fetch(temp / "agg.ipa", None, fetcher.RangeReader(url, len(ipa), opener),
                                  "0" * 64, len(ALLOWED), directory_sha), "differ from the pin")
    assert not (temp / "agg.ipa").exists()
    server.shutdown()

# The pins of the real Build 350 donor: the previous selection (2,698 members)
# minus exactly the 42 Dusklight members (framework, notices, identity).
assert fetcher.SELECTED_MEMBERS == 2656
assert fetcher.SELECTED_AGGREGATE_SHA256 == "2f73382bc15c56f425e19aa29afd11e6a29a4c547e1aa7f40f29547204a85536"
for name in ("Frameworks/DusklightCore.framework/DusklightCore", "Dusklight-Licenses/SDL-LICENSE.txt",
             "Dusklight-native-identity.json"):
    assert not fetcher.wanted(name) and fetcher.REFUSED.search(name), name
for name in ("Sys/Load/GraphicMods/The Legend of Zelda Twilight Princess/metadata.json",
             "Frameworks/DolphinCore.framework/DolphinCore"):
    assert fetcher.wanted(name), name  # Dolphin's own files for Twilight Princess stay

# A planned range never covers a refused member, even when the gap is small.
members = [fetcher.Member(APP + "Frameworks/libRPCS3Core.dylib", 0, 0, 10, 10, 0, 0),
           fetcher.Member(APP + "Frameworks/KartPadRuntime.framework/KartPadRuntime", 0, 0, 10, 10, 100, 0),
           fetcher.Member(APP + "cacert.pem", 0, 0, 10, 10, 200, 0),
           fetcher.Member(APP + "Sys/x", 0, 0, 10, 10, 300, 0)]
selected, ranges = fetcher.plan(members, 400)
assert [len(items) for _, _, items in ranges] == [1, 2], ranges
assert all(not (start < 200 and end > 100) for start, end, _ in ranges)
print("PASS: native donor subset — only planned 206 ranges, no KartPad or Dusklight member byte served "
      f"({len(refused_spans)} refused records), exact members and modes, whole-file/central-directory/"
      "aggregate refusals, gap planning never spans a refused member")
