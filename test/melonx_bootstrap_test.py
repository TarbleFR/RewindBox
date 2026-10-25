#!/usr/bin/env python3
"""Execute the actual storage boundary; no emulator or Apple SDK is required."""
from pathlib import Path
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
with tempfile.TemporaryDirectory(prefix='melonx-bootstrap-') as temporary:
    work = Path(temporary)
    (work / 'Root.cs').write_bytes((root / 'native/melonx/EmbeddedDataRoot.cs').read_bytes())
    (work / 'State.cs').write_bytes((root / 'native/melonx/EmbeddedInitializationState.cs').read_bytes())
    (work / 'Bootstrap.csproj').write_text('''<Project Sdk="Microsoft.NET.Sdk">
      <PropertyGroup><OutputType>Exe</OutputType><TargetFramework>net8.0</TargetFramework></PropertyGroup>
    </Project>''')
    (work / 'Program.cs').write_text('''using System;
using System.IO;
using System.Threading;
using System.Threading.Tasks;
using Ryujinx.Library;
string docs = Path.Combine(Path.GetTempPath(), "melonx-owned-" + Guid.NewGuid());
Directory.CreateDirectory(docs);
string root = Path.Combine(docs, "MeloNX");
int checkedCases = 0;
void Accepted(string path) {
    if (EmbeddedDataRoot.Resolve(docs, path) != root) throw new Exception("Wrong root");
    checkedCases++;
}
void Rejected(string path) {
    try { EmbeddedDataRoot.Resolve(docs, path); }
    catch (ArgumentException) { checkedCases++; return; }
    throw new Exception("Unsafe root accepted: " + path);
}
try {
    string sentinel = Path.Combine(docs, "existing-save");
    File.WriteAllText(sentinel, "preserve");
    Accepted(root);
    Accepted(root + Path.DirectorySeparatorChar);
    Accepted(Path.Combine(root, "..", "MeloNX"));
    Rejected(docs);
    Rejected(Path.GetTempPath());
    Rejected(Path.Combine(docs, "other-engine"));
    Rejected(Path.Combine(root, ".."));
    Rejected("MeloNX");
    Rejected("");
    Rejected(null);
    // Merely resolving the root must not create an engine directory or touch
    // an existing user file. Import/initialization owns the later write.
    if (Directory.Exists(root) || File.ReadAllText(sentinel) != "preserve")
        throw new Exception("The resolver modified personal data");
    Directory.CreateSymbolicLink(root, docs);
    Rejected(root);
    Directory.Delete(root);
    int calls = 0;
    var state = new EmbeddedInitializationState();
    Parallel.For(0, 16, _ => {
        int result = state.Initialize(docs, root, () => false, p => Interlocked.Increment(ref calls));
        if (result != 0) throw new Exception("Concurrent initialize failed");
    });
    if (calls != 1) throw new Exception("Multiple initialization of native handles");
    checkedCases++;
    var invalid = new EmbeddedInitializationState();
    if (invalid.Initialize(docs, "relative", () => false, p => calls++) != 1 ||
        invalid.Initialize(docs, root, () => false, p => calls++) != 0 || calls != 2)
        throw new Exception("Invalid input incorrectly poisoned the runtime");
    checkedCases++;
    var conflict = new EmbeddedInitializationState();
    if (conflict.Initialize(docs, root, () => true, p => calls++) != 2 || calls != 2)
        throw new Exception("An existing engine initialization was overwritten");
    checkedCases++;
    var failure = new EmbeddedInitializationState();
    if (failure.Initialize(docs, root, () => false, p => { calls++; throw new IOException("sentinel failure"); }) != 3 ||
        failure.Initialize(docs, root, () => false, p => calls++) != 3 || calls != 3 ||
        !failure.LastFailure.Contains("sentinel failure"))
        throw new Exception("Partial initialization was retried or lost its error");
    checkedCases++;
    Console.WriteLine($"Embedded storage and initialization: {checkedCases} cases passed.");
} finally { Directory.Delete(docs, true); }
''')
    subprocess.run(['dotnet', 'run', '--project', str(work / 'Bootstrap.csproj'), '-c', 'Release'], check=True, timeout=120)
