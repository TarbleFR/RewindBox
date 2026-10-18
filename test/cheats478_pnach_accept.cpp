// The actual portable native PNACH document parser; no emulator or ROM.
#include "NeoUnifiedNativeProgram.h"
#include <iostream>
static bool field(std::string& value) {
  uint32_t n=0;
  if (!std::cin.read(reinterpret_cast<char*>(&n),4)) return false;
  if (n>2*1024*1024) std::exit(2);
  value.resize(n); return bool(std::cin.read(value.data(),n));
}
int main() {
  std::string name,code,author;
  while (field(name)) {
    if (!field(code) || !field(author)) return 2;
    auto parsed=NeoUnifiedNative::parse(code,"pnach",name,author,true);
    std::cout << (parsed ? "ok" : parsed.error) << '\n';
  }
}
