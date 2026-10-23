#!/usr/bin/env python3
"""Execute the production Darwin registration against SDK and live sigaction."""
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'build-utils/melonx'))
from adapt_runtime import apply

with tempfile.TemporaryDirectory(prefix='melonx-signal-') as temporary:
    work = Path(temporary)
    source = work / 'source'; source.mkdir()
    archive = work / 'upstream.tar'
    with archive.open('wb') as output:
        subprocess.run(['git', '-C', sys.argv[1], 'archive', 'HEAD'], stdout=output, check=True)
    with tarfile.open(archive) as packed: packed.extractall(source, filter='data')
    apply(source)
    test = work / 'test'; test.mkdir()
    shutil.copy2(source / 'src/Ryujinx.Cpu/Signal/UnixSignalHandlerRegistration.cs', test)
    shutil.copy2(ROOT / 'native/melonx/EmbeddedDarwinSignals.cs', test)
    config = (source / 'src/Ryujinx.Cpu/Signal/NativeSignalHandler.cs').read_text()
    config = config[:config.index('    static class NativeSignalHandler')] + '}\n'
    config = config[config.index('namespace Ryujinx.Cpu.Signal'):]
    (test / 'Config.cs').write_text('using System;using ARMeilleure.Signal;using System.Runtime.CompilerServices;using System.Runtime.InteropServices;\n' + config)
    (test / 'Test.csproj').write_text('''<Project Sdk="Microsoft.NET.Sdk"><PropertyGroup>
      <OutputType>Exe</OutputType><TargetFramework>net10.0</TargetFramework><AllowUnsafeBlocks>true</AllowUnsafeBlocks>
      </PropertyGroup></Project>''')
    (test / 'Program.cs').write_text(r'''using System;
using System.Runtime.CompilerServices;
using System.Runtime.InteropServices;
using Ryujinx.Cpu.Signal;
namespace ARMeilleure.Signal {static class NativeSignalHandlerGenerator {public const int MaxTrackedRanges=16;}}
class Program {
 static int hitSegv,hitBus;static bool contextSeen;
 [UnmanagedCallersOnly]static void Handler(int signal,nint info,nint context) {
  if(signal==11)hitSegv++;if(signal==10)hitBus++;contextSeen=info!=0&&context!=0;
 }
 [DllImport("/usr/lib/libSystem.B.dylib")]static extern int raise(int signal);
 static void Check(bool condition) {if(!condition)throw new Exception("Darwin signal ABI assertion failed");}
 static unsafe void Main() {
  Check(Marshal.SizeOf<UnixSignalHandlerRegistration.DarwinSigAction>()==16);
  Check(Marshal.OffsetOf<UnixSignalHandlerRegistration.DarwinSigAction>("Mask").ToInt32()==8);
  Check(Marshal.OffsetOf<UnixSignalHandlerRegistration.DarwinSigAction>("Flags").ToInt32()==12);
  Check(Marshal.OffsetOf<SignalHandlerConfig>("Ranges").ToInt32()==32);
  Check(Marshal.OffsetOf<SignalHandlerConfig>("UnixOldBusSigaction").ToInt32()==20);
  Check(Marshal.OffsetOf<SignalHandlerConfig>("UnixOldBusSigaction3Arg").ToInt32()==28);
  Check(Unsafe.SizeOf<SignalHandlerRange>()==28);
  if(UnixSignalHandlerRegistration.IsDarwin) {
   var original=UnixSignalHandlerRegistration.GetSegfaultExceptionHandler();
   var originalBus=UnixSignalHandlerRegistration.GetBusExceptionHandler();
   var previous=UnixSignalHandlerRegistration.RegisterExceptionHandler((nint)(delegate* unmanaged<int,nint,nint,void>)&Handler);
   try {
    Check(previous.sa_handler==original.sa_handler&&previous.sa_flags==original.sa_flags);
    Check((UnixSignalHandlerRegistration.GetSegfaultExceptionHandler().sa_flags&0x40)!=0);
    Check((UnixSignalHandlerRegistration.GetBusExceptionHandler().sa_flags&0x40)!=0);
    Check(raise(11)==0&&raise(10)==0);Check(hitSegv==1&&hitBus==1&&contextSeen);
   } finally {Check(UnixSignalHandlerRegistration.RestoreExceptionHandler(previous));}
   var restored=UnixSignalHandlerRegistration.GetSegfaultExceptionHandler();
   var restoredBus=UnixSignalHandlerRegistration.GetBusExceptionHandler();
   Check(restored.sa_handler==original.sa_handler&&restored.sa_flags==original.sa_flags);
   Check(restoredBus.sa_handler==originalBus.sa_handler&&restoredBus.sa_flags==originalBus.sa_flags);
   Console.WriteLine("PASS live Darwin SIGSEGV/SIGBUS, three arguments and distinct previous-handler restoration.");
  }
  Console.WriteLine("PASS production Darwin layout and generated-handler packed offsets.");
 }
}''')
    subprocess.run(['dotnet', 'run', '--project', str(test / 'Test.csproj'), '-c', 'Release'], check=True, timeout=180)
    if sys.platform == 'darwin':
        sdk = work / 'sdk.c'
        sdk.write_text('''#include <signal.h>
#include <stddef.h>
_Static_assert(sizeof(struct sigaction)==16,"Darwin sigaction size");
_Static_assert(offsetof(struct sigaction,sa_mask)==8,"Darwin mask offset");
_Static_assert(offsetof(struct sigaction,sa_flags)==12,"Darwin flags offset");
_Static_assert(SA_SIGINFO==0x40,"Darwin SA_SIGINFO");
int main(void){return 0;}
''')
        for name, target in [('iphoneos', 'arm64-apple-ios18.0'), ('iphonesimulator', 'arm64-apple-ios18.0-simulator')]:
            subprocess.run(['xcrun', '--sdk', name, 'clang', '-target', target, '-fsyntax-only', str(sdk)], check=True)
        swift=work/'SignalInspection.swift'
        swift.write_text('import Darwin\nvar action=Darwin.sigaction()\nlet result=Darwin.sigaction(SIGSEGV,nil,&action)\nlet valid=action.sa_flags & SA_SIGINFO != 0\n')
        sdk_path=subprocess.check_output(['xcrun','--sdk','iphonesimulator','--show-sdk-path'],text=True).strip()
        subprocess.run(['xcrun','swiftc','-typecheck','-target','arm64-apple-ios18.0-simulator','-sdk',sdk_path,str(swift)],check=True)
        print('PASS exact iOS device and Simulator SDK signal declarations.')
