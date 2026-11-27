"""Execute real IOS IP/socket entry points; offline must dispatch no DNS/socket work."""
import argparse
import re
import shutil
import subprocess
import tempfile
from pathlib import Path


def function(source, signature):
    start = source.index(signature)
    return source[start:source.index('\n}', start) + 2]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--upstream', type=Path, required=True)
    root = parser.parse_args().upstream
    top = (root / 'Source/Core/Core/IOS/Network/IP/Top.cpp').read_text()
    socket = (root / 'Source/Core/Core/IOS/Network/Socket.cpp').read_text()
    ioctl = function(top, 'std::optional<IPCReply> NetIPTopDevice::IOCtl(')
    ioctlv = function(top, 'std::optional<IPCReply> NetIPTopDevice::IOCtlV(')
    new_socket = function(socket, 's32 WiiSockMan::NewSocket(')
    constants = sorted(set(re.findall(r'case (IOCTL\w+):', ioctl + ioctlv)))
    core = (Path(__file__).resolve().parents[1] /
            'packages/dolphin_internal_bridge/core/NeoStationWiimmfi.inc').read_text()
    policy = function(core, 'extern "C" bool neostation_dolphin_wiimmfi_network_allowed()')
    program = r'''
#include <atomic>
#include <optional>
#include <cassert>
#include <cstdint>
using s32=int32_t;
int host_work=0;
std::atomic<bool> g_wiimmfi_network_allowed{false};
constexpr int SO_ENETUNREACH=28,SO_EAFNOSUPPORT=5,SO_EPROTONOSUPPORT=6,SO_EPROTOTYPE=7;
constexpr int AF_INET=2,AF_INET6=10,IPC_SUCCESS=0,IPC_EACCES=-1;
namespace Core { bool WantsDeterminism() {return false;} }
namespace Common::Log { enum class LogType {IOS_NET}; }
struct IPCReply { int value; explicit IPCReply(int v):value(v){} };
struct Request { int request; template<class... T> void DumpUnknown(T...) const {} };
using IOCtlRequest=Request; using IOCtlVRequest=Request;
int socket(int,int,int) {++host_work;return 43;}
struct WiiSockMan {
  s32 NewSocket(s32,s32,s32);
  int AddSocket(int fd,bool) {assert(fd==43);return fd;}
};
'''
    program += policy + '\nenum { ' + ','.join(constants) + ' };\n'
    handlers = set(re.findall(r'(Handle\w+)\(', ioctl + ioctlv))
    handlers.update(re.findall(r'&NetIPTopDevice::(Handle\w+)', ioctl + ioctlv))
    program += 'struct NetIPTopDevice {\n'
    for name in sorted(handlers):
        program += f'IPCReply {name}(const Request&) {{++host_work;return IPCReply(77);}}\n'
    program += '''
  int GetSystem() const {return 0;} const char* GetDeviceName()const{return "test";}
  template<class F> IPCReply LaunchAsyncTask(F,const Request&) {++host_work;return IPCReply(77);}
  std::optional<IPCReply> IOCtl(const IOCtlRequest&);
  std::optional<IPCReply> IOCtlV(const IOCtlVRequest&);
};
'''
    program += ioctl + '\n' + ioctlv + '\n' + new_socket + '\n'
    program += 'int main(){NetIPTopDevice top;WiiSockMan sockets;\n'
    program += 'for(int cycle=0;cycle<100;++cycle){g_wiimmfi_network_allowed=false;int before=host_work;\n'
    for constant in constants:
        target = 'IOCtlV' if constant.startswith('IOCTLV') else 'IOCtl'
        program += f'assert(top.{target}(Request{{{constant}}})->value==-SO_ENETUNREACH);\n'
    program += '''
  assert(sockets.NewSocket(2,1,0)==-SO_ENETUNREACH);assert(host_work==before);
  g_wiimmfi_network_allowed=true;
  assert(top.IOCtl(Request{IOCTL_SO_GETHOSTBYNAME})->value==77);
  assert(sockets.NewSocket(2,1,0)==43);assert(host_work==before+2);
  assert(sockets.NewSocket(99,1,0)==-SO_EAFNOSUPPORT);
}}
'''
    with tempfile.TemporaryDirectory() as temp:
        source = Path(temp) / 'offline.cpp'
        binary = Path(temp) / 'offline'
        source.write_text(program)
        compiler = shutil.which('clang++') or shutil.which('c++')
        subprocess.run([compiler, '-std=c++20', '-DIPHONEOS', str(source), '-o', str(binary)], check=True)
        subprocess.run([str(binary)], check=True)
    print(f'PASS: real IOS IP/IOCtlV/NewSocket offline gates, {len(constants)} requests x100; zero host work offline')


if __name__ == '__main__':
    main()
