"""Run the production host initializer with controlled CPU feature probes.

Actual Foundation, dispatch and Apple SDKs; the escrow and sysctl results are
doubles. This proves bootstrap ordering, not iPhone JIT or game performance.
"""
import argparse
import hashlib
import json
import platform
from pathlib import Path
import subprocess
import tempfile

ROOT=Path(__file__).resolve().parents[1]
HOST='packages/rpcs3_internal_bridge/ios/Classes/Rpcs3InternalBridgePlugin.mm'
CORE_SOURCE='407ea8f7462db0645590e799adcdff9ed56b1b21'
CLASSES=ROOT/'packages/rpcs3_internal_bridge/ios/Classes'

def initializer(text):
    start=text.index('- (instancetype)init {',text.index('@implementation Rpcs3InternalBridgePlugin'))
    return text[start:text.index('\n- (NSString*)localized:',start)]

def main(report):
    assert platform.system()=='Darwin' and platform.machine()=='arm64', 'Apple ARM64 SDK host required'
    driver=subprocess.check_output(['xcrun','--find','clang++'],text=True).strip()
    mac_sdk=subprocess.check_output(['xcrun','--sdk','macosx','--show-sdk-path'],text=True).strip()
    ios_sdk=subprocess.check_output(['xcrun','--sdk','iphoneos','--show-sdk-path'],text=True).strip()
    current=(ROOT/HOST).read_text()
    prior=subprocess.check_output(['git','show',CORE_SOURCE+':'+HOST],cwd=ROOT,text=True)
    prefix=r'''
#import <Foundation/Foundation.h>
#include <sys/sysctl.h>
#include <cassert>
#include <cstdio>
#include <cstring>
#include <string>
static const char* missing=nullptr;
static bool unavailable=false,badSize=false;
static unsigned events=0,lastProbe=0,firstAcquire=0,acquires=0;
static int feature_probe(const char* key,void* output,size_t* bytes,void*,size_t) {
  lastProbe=++events;
  if(unavailable)return -1;
  assert(output && bytes && *bytes==sizeof(int));
  *static_cast<int*>(output)=!(missing && std::strcmp(key,missing)==0);
  *bytes=badSize?sizeof(int)-1:sizeof(int);
  return 0;
}
#define sysctlbyname feature_probe
#include "RPCS3CPUCompatibility.h"
#undef sysctlbyname
struct EscrowDouble {
  bool acquire(){++acquires;firstAcquire=++events;return true;}
  std::string detail()const{return "fixture";}
};
static void RPCS3Milestone(NSString*,NSString*){}
static void RPCS3Diagnostic(NSString*,NSString*){}
@interface BootstrapFixture : NSObject {
@public
 dispatch_queue_t _runtimeQueue;
 int _api;
 EscrowDouble _jitEscrow;
}
@end
@implementation BootstrapFixture
'''
    suffix=r'''
@end
static void exercise(bool expected) {
  @autoreleasepool {
    events=lastProbe=firstAcquire=acquires=0;
    BootstrapFixture* bridge=[BootstrapFixture new];
    assert(bridge && bridge->_runtimeQueue && bridge->_api==0);
    assert(acquires==(expected?1u:0u));
    assert(lastProbe>0);
    if(expected)assert(firstAcquire>lastProbe);
  }
}
int main(int argc,char**) {
  if(argc>1){missing=rewindbox::rpcs3::armv84_features[0];exercise(false);return 0;}
  exercise(true);
  for(const char* key:rewindbox::rpcs3::armv84_features){missing=key;exercise(false);}
  missing=nullptr;unavailable=true;exercise(false);
  unavailable=false;badSize=true;exercise(false);
  std::puts("PASS 8 production initializer scenarios; incompatible/unknown CPUs never reserve JIT escrow");
}
'''
    with tempfile.TemporaryDirectory(prefix='rpcs3-cpu-escrow-') as directory:
        work=Path(directory)
        for name,method in [('current',initializer(current)),('pre-fix',initializer(prior))]:
            file=work/(name+'.mm');file.write_text(prefix+method+suffix)
            flags=['-std=c++20','-fobjc-arc','-Wall','-Wextra','-Werror','-I',str(CLASSES)]
            # Both the header and production method must compile for the same
            # iPhone target; actual execution below uses the real macOS SDK.
            subprocess.run([driver,*flags,'-target','arm64-apple-ios18.0','-isysroot',ios_sdk,
                            '-fsyntax-only',str(file)],check=True)
            subprocess.run([driver,*flags,'-isysroot',mac_sdk,'-fsanitize=address,undefined',
                            str(file),'-framework','Foundation','-o',str(work/name)],check=True)
            result=subprocess.run([str(work/name),*(['incompatible'] if name=='pre-fix' else [])],capture_output=True,text=True,timeout=15)
            if name=='current':result.check_returncode();print(result.stdout,end='')
            else:assert result.returncode!=0 and 'acquires' in result.stderr,result.stdout+result.stderr
    record=dict(result='passed',productionInitializerCases=8,preFixReservationReproduced=True,
      actualFoundation=True,actualDispatch=True,iphoneSDKTypecheck=True,sysctlAndEscrowDouble=True,
      physicalDeviceTested=False,gameplayTested=False,
      inputs={p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in [HOST,
        'packages/rpcs3_internal_bridge/ios/Classes/RPCS3CPUCompatibility.h',
        'packages/rpcs3_internal_bridge/ios/Classes/RPCS3CPUCompatibilityPolicy.h',
        'test/rpcs3_cpu_escrow_test.py','test/fixtures/rpcs3_v012_host_escrow.diff']})
    report.parent.mkdir(parents=True,exist_ok=True);report.write_text(json.dumps(record,indent=2)+'\n')
    print('PASS pre-fix control reserves escrow on an incompatible CPU; current source blocks it before preparation')

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--report',type=Path,default=ROOT/'build/delivery/rpcs3-cpu-escrow-proof.json')
    main(p.parse_args().report)
