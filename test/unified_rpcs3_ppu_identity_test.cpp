#include "RPCS3PPUIdentity.h"
#include <cassert>
#include <iostream>
int main(){
 const std::string hash="PPU-0123456789abcdef0123456789abcdef01234567";
 assert(RPCS3PPUIdentityFromLog("PPU executable hash: "+hash)==hash);
 assert(RPCS3PPUIdentityFromLog("ppu_loader: PPU executable hash: "+hash+" (<- 4)")==hash);
 assert(RPCS3PPUIdentityFromLog("PRX library hash: "+hash).empty());
 assert(RPCS3PPUIdentityFromLog("cache/"+hash).empty());
 assert(RPCS3PPUIdentityFromLog("PPU executable hash: "+hash+"0").empty());
 assert(RPCS3PPUIdentityFromLog("PPU executable hash: "+hash.substr(0,43)).empty());
 assert(RPCS3PPUIdentityFromLog("PPU executable hash: PPU-0123456789abcdef0123456789abcdef0123456z").empty());
 assert(RPCS3PPUIdentityFromLog(std::string(1025,'x')).empty());
 std::cout<<"PASS 8 exact executable log identity vectors; PRX/cache/truncated/oversized rejected\n";
}
