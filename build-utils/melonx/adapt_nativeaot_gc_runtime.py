"""Link the NativeAOT workstation GC rebuilt with the upstream background-GC start fix, failing closed otherwise.

IPA 658, 5 November 2026, Hogwarts Legacy (private Core journals of two players, not in the repository; aggregated
in docs/melonx-bgc-fallback-2026-11-05.md): in-play full blocking gen2 collections of 102, 332 and 952 ms. Each one
shares its index with the "background" record (GCKind.Background) whose payload is that of the background
collection two before it: .NET 10.0.0 decided a background gen2, stamped the next background slot in do_pre_gc, then
ran the collection blocking. All 19 such collections in the journals followed more than 20 s without a background
collection; none of the 143 requests within 25 s of the previous one fell back; 68 requests after such a gap did not.

Mechanism (dotnet/runtime v10.0.0, 60629d14; the iOS NativeAOT runtime pack 10.0.0 was built from dotnet/dotnet
b0f34d51, whose gc.cpp and NativeAOT gcenv.ee.cpp are byte-identical):
- gc.cpp bgc_thread_function: a workstation BGC thread waits 20000 ms for work (release, non-MULTIPLE_HEAPS) and exits
  when the wait times out (bgc_thread_running = FALSE, bgc_thread = 0);
- the next background gen2 (gc.cpp garbage_collect) calls prepare_bgc_thread -> create_bgc_thread, which sets
  bgc_thread_running from GCToEEInterface::CreateThread; NativeAOT's CreateThread (gcenv.ee.cpp) returns once the new
  thread signalled m_ThreadStartedEvent, which happens before the thread runs bgc_thread_stub, the code that sets
  bgc_thread;
- the workstation start check is `do_concurrent_p = (!!bgc_thread && commit_mark_array_bgc_init())`: when the new
  thread has not reached bgc_thread_stub yet, the GC falls back to a blocking, compaction-enabled gen2.
Upstream fixed the check to `bgc_thread_running` (dotnet/runtime#119383, commit f1f0a476, merged 5 Sep 2025, first
released in 11.0.0-preview.1; every 10.0.x tag up to 10.0.14 still has `!!bgc_thread`). No GC setting keeps the thread
or changes the 20 s wait. On the host CoreCLR 10.0.0, the same probe falls back on about 1 in 10 thread-creating
requests, and never on .NET 11 rc.3 (docs/melonx-bgc-fallback-2026-11-05.md).

Change (Ryujinx.Library.csproj only): after the ILCompiler's SetupOSSpecificProps target, the runtime pack's
libRuntime.WorkstationGC.a is replaced, among the linker inputs and NativeLibrary items, by the library of
.github/workflows/melonx-nativeaot-gc-rebuild.yml (the pack's archive with only gcwks.cpp.o rebuilt from v10.0.0 plus
build-utils/melonx/nativeaot-gc/wks-bgc-thread-running.patch). The build fails when the RuntimeIdentifier is not one of
the two reviewed packs, when server GC is selected, when the pack's library is not the reviewed 10.0.0 bytes, when
RewindBoxNativeAotGcSha256 (from build-utils/melonx/nativeaot-gc-rebuild-pin.json, passed by build_core.sh) is unset,
when the patched library is absent or has other bytes, or when the replacement is not exactly one linker input.
Fail closed on drift: the project must be the Core 658 preparation's.
"""
import hashlib
from adapt_session import once

BASELINE = {
    'src/Ryujinx.Library/Ryujinx.Library.csproj': '90efb63fec94331a7c78936a765d227967a08b870b58eb65c2d3743a6b954199',
}
# libRuntime.WorkstationGC.a of Microsoft.NETCore.App.Runtime.NativeAOT.<rid> 10.0.0 (nuget.org), the bytes the patch
# was made against (also in build-utils/melonx/nativeaot-gc-rebuild.json).
OFFICIAL = {
    'ios-arm64': '44b780ba8bcaa1261cca8f7a28fcc95de8623b242f1f94c290e2cb29f9757f33',
    'iossimulator-arm64': '39fea820ec5cf2cd9cdb8e20a42c5ca5f1eb91084a8ec131c2b6e384a0d68ec5',
}
TARGET = '''
  <!-- RewindBox (adapt_nativeaot_gc_runtime): link the workstation GC rebuilt with the upstream background-GC start fix
       (dotnet/runtime#119383) instead of the runtime pack's; fail closed when it is absent or differs. -->
  <PropertyGroup>
    <RewindBoxNativeAotGcDirectory Condition=" '$(RewindBoxNativeAotGcDirectory)' == '' ">$(MSBuildThisFileDirectory)RewindBoxNativeAotGc/</RewindBoxNativeAotGcDirectory>
  </PropertyGroup>

  <Target Name="RewindBoxPatchedNativeAotGc" AfterTargets="SetupOSSpecificProps">
    <PropertyGroup>
      <_RewindBoxGcOfficial>$(IlcSdkPath)libRuntime.WorkstationGC.a</_RewindBoxGcOfficial>
      <_RewindBoxGcPatched>$([MSBuild]::EnsureTrailingSlash('$(RewindBoxNativeAotGcDirectory)'))$(RuntimeIdentifier)/libRuntime.WorkstationGC.a</_RewindBoxGcPatched>
      <_RewindBoxGcOfficialExpected Condition=" '$(RuntimeIdentifier)' == 'ios-arm64' ">{ios}</_RewindBoxGcOfficialExpected>
      <_RewindBoxGcOfficialExpected Condition=" '$(RuntimeIdentifier)' == 'iossimulator-arm64' ">{simulator}</_RewindBoxGcOfficialExpected>
    </PropertyGroup>
    <Error Condition=" '$(_RewindBoxGcOfficialExpected)' == '' " Text="RewindBox NativeAOT GC: no reviewed runtime pack for RuntimeIdentifier '$(RuntimeIdentifier)'." />
    <Error Condition=" '$(FullRuntimeName)' != 'libRuntime.WorkstationGC' " Text="RewindBox NativeAOT GC: '$(FullRuntimeName)' is selected; only the workstation GC is rebuilt." />
    <Error Condition=" '$(RewindBoxNativeAotGcSha256)' == '' " Text="RewindBox NativeAOT GC: RewindBoxNativeAotGcSha256 is not set (build-utils/melonx/nativeaot-gc-rebuild-pin.json must pin the patched library)." />
    <Error Condition=" !Exists('$(_RewindBoxGcOfficial)') " Text="RewindBox NativeAOT GC: the runtime pack's library is missing: $(_RewindBoxGcOfficial)" />
    <Error Condition=" !Exists('$(_RewindBoxGcPatched)') " Text="RewindBox NativeAOT GC: the patched library is missing: $(_RewindBoxGcPatched)" />
    <GetFileHash Files="$(_RewindBoxGcOfficial)" Algorithm="SHA256">
      <Output TaskParameter="Hash" PropertyName="_RewindBoxGcOfficialActual" />
    </GetFileHash>
    <GetFileHash Files="$(_RewindBoxGcPatched)" Algorithm="SHA256">
      <Output TaskParameter="Hash" PropertyName="_RewindBoxGcPatchedActual" />
    </GetFileHash>
    <Error Condition=" '$(_RewindBoxGcOfficialActual)' != '$(_RewindBoxGcOfficialExpected)' " Text="RewindBox NativeAOT GC: the runtime pack's library is $(_RewindBoxGcOfficialActual), not the reviewed 10.0.0 library $(_RewindBoxGcOfficialExpected)." />
    <Error Condition=" '$(_RewindBoxGcPatchedActual)' != '$(RewindBoxNativeAotGcSha256)' " Text="RewindBox NativeAOT GC: the patched library is $(_RewindBoxGcPatchedActual), not the pinned $(RewindBoxNativeAotGcSha256)." />
    <ItemGroup>
      <_RewindBoxGcLinkerArg Include="@(LinkerArg)" Condition=" '%(Filename)%(Extension)' == 'libRuntime.WorkstationGC.a' " />
      <_RewindBoxGcNativeLibrary Include="@(NativeLibrary)" Condition=" '%(Filename)%(Extension)' == 'libRuntime.WorkstationGC.a' " />
    </ItemGroup>
    <PropertyGroup>
      <_RewindBoxGcOfficialFull>$([System.IO.Path]::GetFullPath('$(_RewindBoxGcOfficial)'))</_RewindBoxGcOfficialFull>
      <_RewindBoxGcPatchedFull>$([System.IO.Path]::GetFullPath('$(_RewindBoxGcPatched)'))</_RewindBoxGcPatchedFull>
      <_RewindBoxGcLinkerArgPaths>@(_RewindBoxGcLinkerArg->'%(FullPath)')</_RewindBoxGcLinkerArgPaths>
      <_RewindBoxGcNativeLibraryPaths>@(_RewindBoxGcNativeLibrary->'%(FullPath)')</_RewindBoxGcNativeLibraryPaths>
    </PropertyGroup>
    <Error Condition=" '$(_RewindBoxGcLinkerArgPaths)' != '$(_RewindBoxGcOfficialFull)' or '$(_RewindBoxGcNativeLibraryPaths)' != '$(_RewindBoxGcOfficialFull)' " Text="RewindBox NativeAOT GC: expected the runtime pack's library exactly once among the linker inputs, found '$(_RewindBoxGcLinkerArgPaths)' and '$(_RewindBoxGcNativeLibraryPaths)'." />
    <!-- In place: a single-pass linker resolves archives in command-line order. -->
    <ItemGroup>
      <LinkerArg>
        <_RewindBoxGcInput>%(Identity)</_RewindBoxGcInput>
      </LinkerArg>
      <LinkerArg Condition=" '%(Filename)%(Extension)' == 'libRuntime.WorkstationGC.a' ">
        <_RewindBoxGcInput>$(_RewindBoxGcPatchedFull)</_RewindBoxGcInput>
      </LinkerArg>
      <NativeLibrary>
        <_RewindBoxGcInput>%(Identity)</_RewindBoxGcInput>
      </NativeLibrary>
      <NativeLibrary Condition=" '%(Filename)%(Extension)' == 'libRuntime.WorkstationGC.a' ">
        <_RewindBoxGcInput>$(_RewindBoxGcPatchedFull)</_RewindBoxGcInput>
      </NativeLibrary>
      <_RewindBoxGcLinkerArgs Include="@(LinkerArg->'%(_RewindBoxGcInput)')" />
      <_RewindBoxGcNativeLibraries Include="@(NativeLibrary->'%(_RewindBoxGcInput)')" />
      <LinkerArg Remove="@(LinkerArg)" />
      <LinkerArg Include="@(_RewindBoxGcLinkerArgs)" />
      <NativeLibrary Remove="@(NativeLibrary)" />
      <NativeLibrary Include="@(_RewindBoxGcNativeLibraries)" />
      <_RewindBoxGcLinked Include="@(LinkerArg)" Condition=" '%(Filename)%(Extension)' == 'libRuntime.WorkstationGC.a' " />
    </ItemGroup>
    <PropertyGroup>
      <_RewindBoxGcLinkedPaths>@(_RewindBoxGcLinked->'%(FullPath)')</_RewindBoxGcLinkedPaths>
    </PropertyGroup>
    <Error Condition=" '$(_RewindBoxGcLinkedPaths)' != '$(_RewindBoxGcPatchedFull)' " Text="RewindBox NativeAOT GC: the linker inputs hold '$(_RewindBoxGcLinkedPaths)' after the replacement." />
    <Message Importance="high" Text="RewindBox NativeAOT GC: linking $(_RewindBoxGcPatchedFull) (SHA-256 $(_RewindBoxGcPatchedActual)) instead of the runtime pack's libRuntime.WorkstationGC.a ($(_RewindBoxGcOfficialActual))." />
  </Target>
</Project>'''.replace('{ios}', OFFICIAL['ios-arm64']).replace('{simulator}', OFFICIAL['iossimulator-arm64'])


def apply(source):
    paths = {name: source / name for name in BASELINE}
    for name, expected in BASELINE.items():
        assert hashlib.sha256(paths[name].read_bytes()).hexdigest() == expected, name
    project = paths['src/Ryujinx.Library/Ryujinx.Library.csproj']
    # The project's last line; adapt_gc wrote the two GC knobs above it (ConserveMemory 5, HighMemoryPercent 99).
    once(project, '''    <TrimMode>full</TrimMode>
  </PropertyGroup>
</Project>''', '''    <TrimMode>full</TrimMode>
  </PropertyGroup>
''' + TARGET)
    return list(BASELINE)
