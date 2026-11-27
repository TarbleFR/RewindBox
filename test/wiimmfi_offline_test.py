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



def check_session_network_config(root):
    header = (root / 'Source/Core/Core/IOS/Network/NCD/WiiNetConfig.h').read_text()
    source = (root / 'Source/Core/Core/IOS/Network/NCD/WiiNetConfig.cpp').read_text()
    program = r'''
#include <cassert>
#include <cstring>
#include <array>
#include <string>
#include "Common/CommonTypes.h"
bool online=false;
unsigned profiles=0;
extern "C" bool neostation_dolphin_wiimmfi_network_allowed() { return online; }
extern "C" void neostation_dolphin_wiimmfi_observe(s32 event) {
  assert(event==8 && online); ++profiles;
}
'''
    # Use the real packed config layout. Expose its data only to this fixture.
    program += header.replace('#pragma once', '').replace('private:', 'public:')
    program += r'''
namespace Memory {
class MemoryManager {
public:
  mutable std::string data;
  void CopyToEmu(u32 address,const void* source,size_t length) {
    assert(address==16); data.assign(static_cast<const char*>(source),length);
  }
};
}
namespace IOS::HLE::Net {
WiiNetConfig::WiiNetConfig() = default;
'''
    program += function(source, 'void WiiNetConfig::WriteToMem(') + '\n}\n'
    program += r'''
int main() {
  using namespace IOS::HLE::Net;
  WiiNetConfig config;
  auto& original=config.m_data;
  std::memset(&original,0xa5,sizeof original); // Old Wi-Fi / proxy / static IP profile
  original.connType=WiiNetConfig::ConfigData::IF_WIFI;
  const auto backup=original;
  Memory::MemoryManager memory;
  for (unsigned i=0;i<100;++i) {
    online=false; config.WriteToMem(memory,16);
    assert(memory.data.size()==sizeof original &&
           std::memcmp(memory.data.data(),&backup,sizeof backup)==0);
    online=true; config.WriteToMem(memory,16);
    WiiNetConfig::ConfigData expected{};
    expected.version=original.version;
    expected.linkTimeout=original.linkTimeout;
    expected.nwc24Permission=original.nwc24Permission;
    expected.connType=WiiNetConfig::ConfigData::IF_WIRED;
    expected.connection[0].flags=ConnectionSettings::WIRED_IF | ConnectionSettings::DNS_DHCP |
        ConnectionSettings::IP_DHCP | ConnectionSettings::CONNECTION_SELECTED |
        ConnectionSettings::CONNECTION_TEST_OK;
    assert(memory.data.size()==sizeof expected &&
           std::memcmp(memory.data.data(),&expected,sizeof expected)==0);
    assert(std::memcmp(&original,&backup,sizeof backup)==0);
    assert(profiles==i+1);
  }
}
'''
    with tempfile.TemporaryDirectory() as temp:
        cpp=Path(temp)/'network_config.cpp'
        cpp.write_text(program)
        binary=Path(temp)/'network_config'
        compiler=shutil.which('clang++') or shutil.which('c++')
        subprocess.run([compiler,'-std=c++20','-Wall','-Wextra','-Werror','-DIPHONEOS',
                        '-I',str(root/'Source/Core'),str(cpp),'-o',str(binary)],check=True)
        subprocess.run([str(binary)],check=True)
    print('PASS: actual Wii network config, session-only wired DHCP profile, 100 online/offline cycles')

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--upstream', type=Path, required=True)
    root = parser.parse_args().upstream
    check_session_network_config(root)
    top = (root / 'Source/Core/Core/IOS/Network/IP/Top.cpp').read_text()
    socket = (root / 'Source/Core/Core/IOS/Network/Socket.cpp').read_text()
    ioctl = function(top, 'std::optional<IPCReply> NetIPTopDevice::IOCtl(')
    ioctlv = function(top, 'std::optional<IPCReply> NetIPTopDevice::IOCtlV(')
    new_socket = function(socket, 's32 WiiSockMan::NewSocket(')
    logger = (root / 'Source/Core/Common/Logging/LogManager.cpp').read_text()
    resolver = function(top, 'IPCReply NetIPTopDevice::HandleGetAddressInfoRequest(')
    hints = resolver[resolver.index('  addrinfo hints'):resolver.index('  // getaddrinfo allows')]
    constants = sorted(set(re.findall(r'case (IOCTL\w+):', ioctl + ioctlv)))
    core = (Path(__file__).resolve().parents[1] /
            'packages/dolphin_internal_bridge/core/NeoStationWiimmfi.inc').read_text()
    policy = function(core, 'extern "C" bool neostation_dolphin_wiimmfi_network_allowed()')
    program = r'''
#include <atomic>
#include <optional>
#include <cassert>
#include <cstdint>
#include <array>
#include <string>
#include <vector>
using s32=int32_t;
int host_work=0;
int socket_observations=0;
extern "C" void neostation_dolphin_wiimmfi_observe(s32 event) {
  assert(event==2); ++socket_observations;
}
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
struct addrinfo {
  int ai_flags, ai_family, ai_socktype, ai_protocol, ai_addrlen;
  void *ai_addr, *ai_canonname, *ai_next;
};
struct ResolverVector { unsigned address, size; };
struct ResolverMemory {
  mutable unsigned fields=0;
  unsigned Read_U32(unsigned offset) const { assert(offset<16); ++fields; return offset/4+4; }
};
'''
    program += '''void CheckResolverHints(unsigned size) {
  ResolverMemory memory;
  struct { std::vector<ResolverVector> in_vectors; } request{{{0, 0}, {0, 0}, {0, size}}};
''' + hints + '''
  assert(!hints.ai_addrlen && !hints.ai_addr && !hints.ai_next && !hints.ai_canonname);
  if (size >= 16) {
    assert(hints_valid && memory.fields==4 && hints.ai_flags==4 && hints.ai_family==5 &&
           hints.ai_socktype==6 && hints.ai_protocol==7);
  } else {
    assert(!hints_valid && memory.fields==0);
  }
}
'''
    # Keep the real policy in its own translation unit, like the Core bridge.
    # The logger imports it weakly on Apple; ELF uses the equivalent weak symbol.
    program += r'''
#ifdef __APPLE__
extern "C" bool neostation_dolphin_wiimmfi_network_allowed() __attribute__((weak_import));
#else
extern "C" bool neostation_dolphin_wiimmfi_network_allowed() __attribute__((weak));
#endif
'''
    program += '\nenum { ' + ','.join(constants) + ' };\n'
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
    program += r'''
using LogLevel=int; using LogType=int;
int log_formats=0, log_writes=0;
constexpr char LOG_LEVEL_TO_CHAR[]="N";
namespace fmt { template<class... T> std::string format(T...) {++log_formats;return "public fixture";} }
struct Listener { void Log(LogLevel,const char*) {++log_writes;} };
struct LogManager {
  struct Entry { bool m_enable=true; };
  Entry m_log[1]; Listener listener;
  std::array<int,1> m_listener_ids{0};
  std::array<Listener*,1> m_listeners{&listener};
  LogLevel GetLogLevel() const {return 0;}
  const char* GetTimestamp()const{return "test";}
  const char* GetShortName(LogType)const{return "test";}
  bool IsEnabled(LogType,LogLevel)const;
  void LogWithFullPath(LogLevel,LogType,const char*,int,const char*);
};
'''
    program += function(logger, 'bool LogManager::IsEnabled(') + '\n'
    program += function(logger, 'void LogManager::LogWithFullPath(') + '\n'
    program += 'int main(){NetIPTopDevice top;WiiSockMan sockets;for(unsigned size:{0, 8, 15, 16, 32}) CheckResolverHints(size);\n'
    program += 'for(int cycle=0;cycle<100;++cycle){g_wiimmfi_network_allowed=false;int before=host_work;\n'
    for constant in constants:
        target = 'IOCtlV' if constant.startswith('IOCTLV') else 'IOCtl'
        program += f'assert(top.{target}(Request{{{constant}}})->value==-SO_ENETUNREACH);\n'
    program += '''
  assert(sockets.NewSocket(2,1,0)==-SO_ENETUNREACH);assert(host_work==before);
  assert(socket_observations==cycle);
  g_wiimmfi_network_allowed=true;
  assert(top.IOCtl(Request{IOCTL_SO_GETHOSTBYNAME})->value==77);
  assert(sockets.NewSocket(2,1,0)==43);assert(host_work==before+2);
  assert(socket_observations==cycle+1);
  assert(sockets.NewSocket(99,1,0)==-SO_EAFNOSUPPORT);
}
  LogManager logger;
  for(int cycle=0;cycle<100;++cycle) {
    g_wiimmfi_network_allowed=true;
    assert(!logger.IsEnabled(0,0));
    logger.LogWithFullPath(0,0,"fixture",1,"public diagnostic");
    assert(log_writes==cycle && log_formats==cycle);
    g_wiimmfi_network_allowed=false;
    assert(logger.IsEnabled(0,0));
    logger.LogWithFullPath(0,0,"fixture",1,"public diagnostic");
    assert(log_writes==cycle+1 && log_formats==cycle+1);
  }
}
'''
    with tempfile.TemporaryDirectory() as temp:
        source = Path(temp) / 'offline.cpp'
        binary = Path(temp) / 'offline'
        source.write_text(program)
        policy_source = Path(temp) / 'policy.cpp'
        policy_source.write_text('#include <atomic>\n'
                                 'extern std::atomic<bool> g_wiimmfi_network_allowed;\n' + policy)
        compiler = shutil.which('clang++') or shutil.which('c++')
        subprocess.run([compiler, '-std=c++20', '-Werror', '-DIPHONEOS',
                        str(source), str(policy_source), '-o', str(binary)], check=True)
        subprocess.run([str(binary)], check=True)
    print(f'PASS: real IOS IP/IOCtlV/NewSocket offline gates, {len(constants)} requests x100; zero host work offline')
    print('PASS: actual logger entry points suppress formatting/listeners online and restore offline x100')
    print('PASS: Wii resolver hints initialize Darwin output-only members and read only the four input fields')


if __name__ == '__main__':
    main()
