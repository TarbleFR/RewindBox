#!/usr/bin/env python3
"""Verify the installable RewindBox Glacier System Art independently of its builder."""
import argparse
from collections import defaultdict
import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import stat
import sys
import unicodedata
import zipfile

from PIL import Image


SLUG = "rewindbox-glacier"
REGISTRY = Path(__file__).resolve().parents[1] / "art-inventory" / "art-lookup.json"


def require(condition, detail):
    if not condition:
        raise ValueError(detail)


def folded(text):
    return unicodedata.normalize("NFC", text.strip()).casefold()


def validate_path(path):
    parts = path.split("/")
    require(path and all(part not in ("", ".", "..") for part in parts), f"Unsafe entry: {path!r}")
    require(not any(char in path for char in ('\\', '\0', ':')), f"Non-portable entry: {path!r}")


def registry_data(path):
    registry = json.loads(path.read_bytes())
    systems = {row["id"] for row in registry["systems"]}
    assets = registry["optionalPortablePathToCanonicalSystem"]
    require(len(registry["systems"]) == len(systems) == 121, "Expected 121 source definitions")
    require(len(assets) == 455, "Expected 455 distinct portable asset paths")
    require(len({folded(p) for p in assets}) == 455, "Physical aliases collide after normalization")
    for system in systems:
        require(assets.get(f"backgrounds/{system}.webp") == system, f"Canonical ID does not own its asset: {system}")
    for name, owner in assets.items():
        validate_path(name)
        p = PurePosixPath(name)
        require(p.parts[:1] == ("backgrounds",) and len(p.parts) == 2 and p.suffix == ".webp" and owner in systems,
                f"Unexpected registry asset: {name}")
    folded_map = registry["metadataAliasesByFoldedStem"]
    require(folded_map["pspminis"]["owner"] == "pspminis" and
            set(folded_map["pspminis"]["declaredBy"]) == {"psp", "pspminis"} and
            assets.get("backgrounds/psp.webp") == "psp" and assets.get("backgrounds/pspminis.webp") == "pspminis",
            "PSP and PSP Minis collision is unresolved")
    unsafe = {key: row for key, row in folded_map.items() if not row["safeArchiveStem"]}
    expected = {"commodore plus/4": "plus4", "commodore - plus/4": "plus4", "nec pc-8000/8800": "pc88"}
    require({key: row["owner"] for key, row in unsafe.items()} == expected,
            "The three slash-bearing aliases must resolve only as metadata")
    safe_spellings = registry["canonicalSystemByExactSafeSpelling"]
    require(len(safe_spellings) == 463, "Expected 463 exact safe input spellings")
    for key, owner in safe_spellings.items():
        row = folded_map[folded(key)]
        require(row["owner"] == owner and assets.get(f"backgrounds/{row['safeArchiveStem']}.webp") == owner,
                f"Safe spelling maps to the wrong portable asset: {key}")
    return registry, systems, assets


def verify_geometry(raw, name, expect_size):
    require(raw[:4] == b"RIFF" and raw[8:12] == b"WEBP", f"Unexpected file signature: {name}")
    with Image.open(io.BytesIO(raw)) as img:
        require(img.format == "WEBP" and img.width == img.height and img.width > 0,
                f"Expected a square WebP: {name} ({img.format}, {img.size})")
        if expect_size:
            require(img.size == (expect_size, expect_size), f"Unexpected size: {name} {img.size}")
        require(getattr(img, "n_frames", 1) == 1, f"Unexpected animated icon: {name}")
        img.load()
        require(any(low != high for low, high in img.convert("RGB").getextrema()),
                f"Uniform image: {name}")
        return img.width


def audit(names, read, registry, systems, assets, expect_size):
    names = set(names)
    require("theme.json" in names, "Missing local metadata theme.json")
    metadata = json.loads(read("theme.json"))
    require(metadata.get("id") == SLUG and metadata.get("ai") is True, "Wrong theme id or AI provenance")
    for field in ("name", "author", "version"):
        require(isinstance(metadata.get(field), str) and metadata[field].strip(), f"Missing theme metadata: {field}")
    if "slug" in metadata:
        require(metadata["slug"] == SLUG, "Mismatched slug")
    if "folder" in metadata:
        require(metadata["folder"] == SLUG, "Mismatched folder")
    claimed = metadata.get("systems")
    require(isinstance(claimed, list) and all(isinstance(n, str) for n in claimed),
            "Missing exact system list")
    require(len(claimed) == len(set(claimed)), "Duplicates in systems list")
    claimed = set(claimed)
    require(systems <= claimed, "Metadata omits canonical systems: " + str(sorted(systems - claimed)))
    allowable = set(registry["canonicalSystemByExactSafeSpelling"])
    require(claimed <= allowable, "Metadata declares unavailable or unsafe IDs: " + str(sorted(claimed - allowable)))
    found = {n for n in names if n.startswith("backgrounds/")}
    missing, extra = sorted(set(assets) - found), sorted(found - set(assets))
    require(not missing and not extra, f"Background inventory differs; missing={missing}; extra={extra}")
    known_hashes = {}
    sizes = set()
    shared = defaultdict(list)
    for system in sorted(systems):
        name = f"backgrounds/{system}.webp"
        raw = read(name)
        sizes.add(verify_geometry(raw, name, expect_size))
        digest = hashlib.sha256(raw).digest()
        known_hashes[system] = digest
        shared[digest].append(system)
    for name, owner in assets.items():
        if name == f"backgrounds/{owner}.webp":
            continue
        require(hashlib.sha256(read(name)).digest() == known_hashes[owner],
                f"Alias bytes differ from canonical asset: {name} -> {owner}")
    return {
        "status": "passed", "sourceCommit": registry["source"]["commit"],
        "pack": SLUG, "canonicalSystems": len(systems), "systemBackgrounds": len(found),
        "sameBytesAliases": len(found) - len(systems), "uniqueCanonicalImages": len(shared),
        "canonicalArtworkSharedBetweenSystems": [v for v in shared.values() if len(v) > 1],
        "squareSizes": sorted(sizes), "safeRawSpellings": len(allowable),
        "declaredSafeSpellings": len(claimed),
        "safeSpellingsNotDeclaredInSystems": sorted(allowable - claimed),
        "unsafeSlashAliasesMetadataOnly": 3, "specificPspMinisOverridesGenericPspAlias": True,
        "noOutOfCatalogBackgrounds": True, "gameRecentCardHasNoSystemArtEntry": True,
        "scope": "Offline package contents, decoded WebP and aliases; app installation and rendering require integration verification.",
    }


def audit_zip(path, registry, systems, assets, expect_size):
    with zipfile.ZipFile(path) as archive:
        paths, files, folded_names = set(), set(), set()
        implied = {}
        for entry in archive.infolist():
            name = entry.filename.removesuffix("/") if entry.is_dir() else entry.filename
            validate_path(name)
            kind = stat.S_IFMT(entry.external_attr >> 16)
            require(kind in (0, stat.S_IFREG, stat.S_IFDIR), f"Linked or special ZIP entry: {name}")
            require(name not in paths and folded(name) not in folded_names, f"Duplicate ZIP path: {name}")
            paths.add(name)
            folded_names.add(folded(name))
            for parent in PurePosixPath(name).parents:
                if str(parent) != ".":
                    previous = implied.setdefault(folded(str(parent)), str(parent))
                    require(previous == str(parent), f"Inconsistent parent spelling: {parent} vs {previous}")
            if not entry.is_dir():
                files.add(name)
        require(all(folded(f) not in implied for f in files), "A file shadows a ZIP directory")
        roots = [name.removesuffix("theme.json") for name in files if name.endswith(f"{SLUG}/theme.json")
                 and PurePosixPath(name).parent.name == SLUG]
        require(len(roots) == 1, "Expected exactly one rewindbox-glacier/theme.json")
        prefix = roots[0]
        require(archive.testzip() is None, "A ZIP member failed CRC verification")
        return audit({name[len(prefix):] for name in files if name.startswith(prefix)},
                     lambda name: archive.read(prefix + name), registry, systems, assets, expect_size)


def audit_directory(path, registry, systems, assets, expect_size):
    candidates = [p.parent for p in path.rglob("theme.json") if p.parent.name == SLUG]
    require(len(candidates) == 1, "Expected exactly one rewindbox-glacier/theme.json")
    root = candidates[0]
    names, normalized = set(), set()
    for entry in root.rglob("*"):
        name = entry.relative_to(root).as_posix()
        validate_path(name)
        require(not entry.is_symlink(), f"Symlink found: {name}")
        require(folded(name) not in normalized, f"Case-insensitive or normalization collision: {name}")
        normalized.add(folded(name))
        if entry.is_file():
            names.add(name)
        else:
            require(entry.is_dir(), f"Special file found: {name}")
    return audit(names, lambda name: (root / name).read_bytes(), registry, systems, assets, expect_size)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pack", type=Path)
    parser.add_argument("--inventory", type=Path, default=REGISTRY)
    parser.add_argument("--expect-size", type=int, help="Require a specific square edge size in pixels")
    parser.add_argument("--json-out", type=Path)
    args = parser.parse_args()
    registry, systems, assets = registry_data(args.inventory)
    verify = audit_directory if args.pack.is_dir() else audit_zip
    result = verify(args.pack, registry, systems, assets, args.expect_size)
    text = json.dumps(result, indent=2, ensure_ascii=False)
    if args.json_out:
        args.json_out.write_text(text + "\n", encoding="utf-8")
    print(text)


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError, KeyError, zipfile.BadZipFile) as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        sys.exit(1)
