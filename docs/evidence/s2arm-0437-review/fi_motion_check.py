"""Check the embedded motion shader from three engine revisions, independently of packaging."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys


def extract(path):
    source = path.read_text(encoding="utf-8")
    _, body = source.split("static int fi_mv_setup(NvPresentFI *f) {", 1)
    _, body = body.split("static const char *msl =", 1)
    lines = []
    for line in body.splitlines():
        line = line.strip()
        if not line or line.startswith("//"):
            continue
        match = re.fullmatch(r'("(?:[^"\\]|\\.)*")(;?)', line)
        if match is None:
            raise ValueError(f"{path}: unexpected C string syntax near {line[:60]}")
        lines.append(json.loads(match[1]))
        if match[2]:
            break
    else:
        raise ValueError(f"{path}: incomplete shader string")
    kernels = re.findall(r"\bkernel void (\w+)\(", "".join(lines))
    if sorted(kernels) != ["cut", "down", "down2", "match", "spread"]:
        raise ValueError(f"{path}: unexpected kernel list {kernels}")
    return "".join(lines).encode("utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for key in ("reference", "intermediate", "candidate", "output"):
        parser.add_argument(key, type=Path)
    parser.add_argument("--extract-only", action="store_true")
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    paths = []
    for name in ("reference", "intermediate", "candidate"):
        path = args.output / (name + ".metal")
        contents = extract(getattr(args, name))
        path.write_bytes(contents)
        print(name, "MSL bytes", len(contents), "SHA-256", hashlib.sha256(contents).hexdigest(), flush=True)
        paths.append(path.resolve())
    if args.extract_only:
        print("Extraction only. Neither Metal compiler nor GPU was exercised.")
        return 0
    if sys.platform != "darwin":
        print("Unavailable: iPhoneOS Metal compiler and macOS GPU require an Apple host.")
        return 77
    subprocess.run(["xcrun", "--sdk", "iphoneos", "metal", "-c", paths[2],
                    "-o", args.output / "candidate.air"], check=True)
    print("iPhoneOS metal compiled the candidate to AIR.", flush=True)
    executable = (args.output / "fi_motion_check").resolve()
    subprocess.run(["xcrun", "--sdk", "macosx", "clang", "-O2", "-fobjc-arc",
                    Path(__file__).with_suffix(".m"), "-framework", "Foundation",
                    "-framework", "Metal", "-o", executable], check=True)
    return subprocess.run([executable, *paths]).returncode


if __name__ == "__main__":
    raise SystemExit(main())
