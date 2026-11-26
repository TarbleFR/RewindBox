"""Compare public results from the reference, the rejected trial and the corrected classifier."""
import argparse
import os
from pathlib import Path
import shutil
import subprocess

from reference import restore_reference


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("engine", type=Path)
    ap.add_argument("patches", type=Path)
    ap.add_argument("out", type=Path)
    args = ap.parse_args()
    modes = ("base", "all", "compatible")
    source = args.engine / "graphics/widen/WidenRewriter.cs"
    project = """<Project Sdk="Microsoft.NET.Sdk">
    <PropertyGroup>
        <OutputType>Exe</OutputType><TargetFramework>net10.0</TargetFramework>
        <LangVersion>preview</LangVersion><AllowUnsafeBlocks>true</AllowUnsafeBlocks>
    </PropertyGroup>
</Project>"""
    for mode in modes:
        root = args.out / mode
        build = root / "graphics/widen"
        build.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, build / source.name)
        restore_reference(root)
        if mode != "base":
            with (args.patches / (mode + ".patch")).open("rb") as change:
                subprocess.run(["patch", "--batch", "-p1"], cwd=root, stdin=change, check=True)
        shutil.copyfile(Path(__file__).with_name("Review.cs"), build / "Review.cs")
        (build / "review.csproj").write_text(project)
        with (root / "build.log").open("w") as log:
            subprocess.run(["dotnet", "build", "-c", "Release", "--nologo"], cwd=build, stdout=log, check=True)
        for disabled in ("0", "1"):
            env = dict(os.environ, S2A_WIDEN_NOCAM=disabled, DOTNET_TieredCompilation="0")
            fixture = build / "bin/Release/net10.0/review.dll"
            result = subprocess.check_output(["dotnet", fixture.resolve()], env=env, text=True)
            (root / f"nocam-{disabled}.txt").write_text(result)

    for disabled in ("0", "1"):
        name = f"nocam-{disabled}.txt"
        original, rejected, candidate = ((args.out / label / name).read_bytes() for label in modes)
        if candidate != original:
            raise ValueError(f"output mismatch for {name}")
        if rejected == original or rejected.splitlines()[3:] != original.splitlines()[3:]:
            raise ValueError(f"failed to reproduce the rejected trial's length error for {name}")
    print("Corrected candidate matches all outputs for both camera settings. Short inputs reject the original trial.")


if __name__ == "__main__":
    main()
