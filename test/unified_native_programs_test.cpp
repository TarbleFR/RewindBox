#include "NeoUnifiedNativeProgram.h"
#include <cassert>
#include <iostream>
int main() {
  using NeoUnifiedNative::parse;
  auto pnach=parse("[Full program]\npatch=1,EE,D0000000,extended,00000001\n\npatch=1,EE,20000004,extended,00000002\n","pnach","Selected","Author",true);
  assert(pnach && pnach.entries.size()==1 && pnach.entries[0].lines.size()==2);
  assert(!parse("patch=1,EE,20000000,extended,00000001\nBROKEN=PROGRAM","pnach","Bad","",true));
  auto gecko=parse("[Gecko]\n$Ordered\nC2000000 00000002\n60000000 00000000\n60000000 00000000","gecko","Selected","",false);
  assert(gecko && gecko.entries.size()==1 && gecko.entries[0].lines.size()==3);
  assert(!parse("04000000 00000001\n04000004 XXXXXXXX","gecko","Bad","",false));
  assert(!parse("[ActionReplay]\n$A\n04000000 00000001","gecko","Wrong dialect","",false));
  assert(!parse("04000000 00000001","gecko","Wrong engine","",true));
  assert(!parse("04000000 00000001","pnach","Wrong engine","",false));
  auto ar=parse("[ActionReplay]\n$AR\n04000000 00000001","actionReplay","AR","",false);
  assert(ar && ar.entries[0].type=="actionReplay");
  std::cout << "PASS: complete native programs, preserved order and dialect/placeholder rejection\n";
}
