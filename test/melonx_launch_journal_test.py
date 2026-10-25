#!/usr/bin/env python3
"""Prove native launch milestones survive termination without the Flutter relay.

Only synthetic diagnostics are used. The managed test executes production C#;
the Swift test extracts the production journal verbatim. Neither runs a guest.
Use --managed-only on hosts without Swift/Foundation (for example Linux CI).
"""
import argparse
import concurrent.futures
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
BASELINE = "433d0cf4735f248a3f624983b56f3be4b48ea786"
PREFIXES = ("[MeloNX:core] ", "[MeloNX:native] ")
SECRET = "a" * 64


def records(path):
    lines = path.read_text().splitlines()
    assert SECRET not in "\n".join(lines), "Unredacted synthetic key value"
    return [json.loads(line[len(prefix):]) for line in lines
            for prefix in PREFIXES if line.startswith(prefix)]


def run_managed(work):
    project = work / "managed"
    project.mkdir()
    shutil.copyfile(ROOT / "native/melonx/EmbeddedLaunchDiagnostics.cs", project / "Journal.cs")
    (project / "Probe.csproj").write_text("""<Project Sdk="Microsoft.NET.Sdk"><PropertyGroup>
      <OutputType>Exe</OutputType><TargetFramework>net10.0</TargetFramework><AllowUnsafeBlocks>true</AllowUnsafeBlocks>
      </PropertyGroup></Project>""")
    (project / "Program.cs").write_text(r'''using System;
using System.Diagnostics;
using System.IO;
using System.Text.Json;
using Ryujinx.Common;
string path=Path.GetFullPath(args[0]);string mode=args[1];
EmbeddedLaunchDiagnostics.ConfigureJournal(path);
if(mode=="invalid") {
 foreach(var invalid in new[]{"relative/app.log",Path.Combine(Path.GetDirectoryName(path),"prod.keys")}) {
  try{EmbeddedLaunchDiagnostics.ConfigureJournal(invalid);throw new Exception("Invalid journal path accepted");}
  catch(ArgumentException){}
 }
}
if(mode=="many") {
 for(int i=0;i<300;i++)EmbeddedLaunchDiagnostics.Record("keys","begin",detail:"header_key = "+new string('a',64));
 using var doc=JsonDocument.Parse(EmbeddedLaunchDiagnostics.Snapshot());
 if(doc.RootElement.GetProperty("events").GetArrayLength()!=64)throw new Exception("Unbounded ring");
}else {
 EmbeddedLaunchDiagnostics.Record("jitProbe","begin",detail:"header_key = "+new string('a',64));
 if(mode=="abort")Process.GetCurrentProcess().Kill();
}
''')
    subprocess.run(["dotnet", "build", str(project / "Probe.csproj"), "-c", "Release", "--nologo", "-v:q"], check=True)
    probe = ["dotnet", str(project / "bin/Release/net10.0/Probe.dll")]
    path = work / "managed-log/app.log"
    path.parent.mkdir()
    path.write_text("frontend sentinel\n")
    subprocess.run([*probe, str(path), "invalid"], check=True)
    assert path.read_text().startswith("frontend sentinel\n")
    assert records(path)[-1]["stage"] == "jitProbe"

    # Independent Core callers and a frontend-like O_APPEND writer share one
    # file. Every record must remain complete; a seek-to-end writer loses data.
    def frontend():
        fd = os.open(path, os.O_WRONLY | os.O_APPEND)
        try:
            for i in range(300):
                os.write(fd, f"frontend {i}\n".encode())
        finally:
            os.close(fd)
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
        futures = [pool.submit(subprocess.run, [*probe, str(path), "many"], check=True) for _ in range(2)]
        futures.append(pool.submit(frontend))
        for future in futures:
            future.result()
    data = records(path)
    assert len(data) == 601
    assert sum(line.startswith("frontend ") for line in path.read_text().splitlines()) == 301
    assert all(row["pid"] > 0 and row["timestamp"] and row["nativeStatus"] == 0 for row in data)

    # Failure to open the destination and the size ceiling never change native
    # behavior. The diagnostic ring is still bounded independently of the file.
    # Configuration reports an unavailable destination; the application catches
    # this optional failure. A destination removed after setup must also be safe.
    capped = work / "capped/app.log"
    capped.parent.mkdir()
    with capped.open("wb") as target:
        target.truncate(5 * 1024 * 1024)
    subprocess.run([*probe, str(capped), "once"], check=True)
    assert capped.stat().st_size == 5 * 1024 * 1024

    terminated = work / "terminated/app.log"
    terminated.parent.mkdir()
    child = subprocess.run([*probe, str(terminated), "abort"], capture_output=True)
    assert child.returncode != 0 and records(terminated)[-1]["stage"] == "jitProbe"

    # Old production Record only queues events in memory. No Flutter poll is
    # performed here, reproducing the journal gap after abrupt termination.
    old = subprocess.check_output(["git", "show", BASELINE + ":native/melonx/EmbeddedLaunchDiagnostics.cs"], cwd=ROOT, text=True)
    old = old.replace("public static class EmbeddedLaunchDiagnostics\n{", "public static class EmbeddedLaunchDiagnostics\n{\n    public static void ConfigureJournal(string path) {}")
    (project / "Journal.cs").write_text(old)
    subprocess.run(["dotnet", "build", str(project / "Probe.csproj"), "-c", "Release", "--nologo", "-v:q"], check=True)
    negative = work / "old/app.log"
    negative.parent.mkdir()
    child = subprocess.run([*probe, str(negative), "abort"], capture_output=True)
    assert child.returncode != 0 and not negative.exists()
    print("PASS managed journal: old loss reproduced; corrected abrupt termination, 601 concurrent native records, redaction, bounded ring, file cap and failed-I/O isolation.")


def run_swift(work):
    host = (ROOT / "packages/melonx_internal_bridge/ios/Classes/MeloNXSessionHost.swift").read_text()
    journal = host[host.index("enum MeloNXLaunchJournal {"):host.index("\nenum MeloNXHostError:")]
    imports = "import Foundation\nimport Darwin\n"
    if os.uname().sysname != "Darwin":
        imports = "import Foundation\nimport Glibc\n"
        journal = journal.replace("Darwin.", "Glibc.")
    source = work / "main.swift"
    source.write_text(imports + journal + r'''
let path=CommandLine.arguments[1]
MeloNXLaunchJournal.configure(path:path)
var relayed=0
MeloNXLaunchJournal.sink={_ in relayed += 1}
MeloNXLaunchJournal.record("jitProbe","begin",detail:"header_key = "+String(repeating:"a",count:64))
precondition(relayed==0,"The main queue should not have been drained")
if CommandLine.arguments.count > 2 { kill(getpid(),SIGKILL) }
''')
    executable = work / "swift-journal"
    subprocess.run(["swiftc", str(source), "-o", str(executable)], check=True)
    path = work / "swift/app.log"
    path.parent.mkdir()
    child = subprocess.run([str(executable), str(path), "abort"], capture_output=True)
    assert child.returncode != 0 and records(path)[-1]["stage"] == "jitProbe"
    assert records(path)[-1]["diagnostic"] == "[redacted key entry]"
    subprocess.run([str(executable), str(work / "no-swift-directory/app.log")], check=True)
    print("PASS production Swift journal survives termination without pumping the main queue; secrets redacted and failed I/O ignored.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--managed-only", action="store_true")
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="melonx-journal-") as temporary:
        work = Path(temporary)
        run_managed(work)
        if not args.managed_only:
            run_swift(work)
