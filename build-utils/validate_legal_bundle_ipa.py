#!/usr/bin/env python3
"""Validate that a packaged NeoStation IPA contains the legal/source bundle."""

from __future__ import annotations

import argparse
import hashlib
import json
import zipfile
from pathlib import Path

from embed_legal_bundle import (
    REQUIRED_LEGAL_FILES,
    validate_additional_notices,
    validate_libretro_notices,
)

REQUIRED = (
    "NeoStation-NOTICE.md",
    "LEGAL_AND_CREDITS.md",
    "BUILD_SOURCE_IDENTITY.json",
    *REQUIRED_LEGAL_FILES,
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("ipa", type=Path)
    parser.add_argument("--build-number", required=True)
    parser.add_argument("--commit", required=True)
    args = parser.parse_args()

    with zipfile.ZipFile(args.ipa) as archive:
        names = archive.namelist()
        app_roots = sorted(
            {
                name.split("/", 2)[1]
                for name in names
                if name.startswith("Payload/")
                and name.count("/") >= 2
                and name.split("/", 2)[1].endswith(".app")
            }
        )
        if len(app_roots) != 1:
            raise SystemExit(f"Expected one app bundle, found: {app_roots}")
        prefix = f"Payload/{app_roots[0]}/Legal/"

        missing = [name for name in REQUIRED if prefix + name not in names]
        if missing:
            raise SystemExit("Missing legal files: " + ", ".join(missing))

        for name in REQUIRED:
            member = prefix + name
            if names.count(member) != 1 or not archive.getinfo(member).file_size:
                raise SystemExit(f"Empty or duplicate legal file: {name}")

        for name, digest in validate_libretro_notices().items():
            member = prefix + "Libretro/" + name
            if names.count(member) != 1:
                raise SystemExit(f"Missing or duplicate Libretro notice: {name}")
            if hashlib.sha256(archive.read(member)).hexdigest() != digest:
                raise SystemExit(f"Changed packaged Libretro notice: {name}")

        additional = validate_additional_notices()
        for name, (_, digest) in additional.items():
            member = prefix + name
            if names.count(member) != 1:
                raise SystemExit(f"Missing or duplicate additional notice: {name}")
            if hashlib.sha256(archive.read(member)).hexdigest() != digest:
                raise SystemExit(f"Changed packaged additional notice: {name}")

        identity = json.loads(
            archive.read(prefix + "BUILD_SOURCE_IDENTITY.json").decode("utf-8")
        )
        if identity["build_number"] != str(args.build_number):
            raise SystemExit(
                f"Legal identity build mismatch: {identity['build_number']}"
            )
        if identity["host_commit"] != args.commit:
            raise SystemExit(
                f"Legal identity commit mismatch: {identity['host_commit']}"
            )
        if identity.get("additional_notice_sha256") != {
            name: digest for name, (_, digest) in additional.items()
        }:
            raise SystemExit("Additional notice identity differs from packaged sources")

        notice = archive.read(prefix + "NeoStation-NOTICE.md").decode("utf-8")
        if "UPSTREAM NEOSTATION ATTRIBUTION" not in notice:
            raise SystemExit("NeoStation notice is incomplete")

        credits = archive.read(prefix + "LEGAL_AND_CREDITS.md").decode("utf-8")
        for marker in (
            "Dolphin / DolphiniOS",
            "RPCS3 / XITRIX",
            "ARMSX2 / PCSX2",
            "StikJIT",
            "GameDB / GameDB-PS3",
        ):
            if marker not in credits:
                raise SystemExit(f"Missing legal credit marker: {marker}")

    print("NeoStation IPA legal bundle validated.")


if __name__ == "__main__":
    main()
