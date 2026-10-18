// SPDX-License-Identifier: GPL-3.0-or-later
#pragma once
#include <string>
#include <string_view>
// PPUModule.cpp at the retained Core's exact source revision emits this only
// for ppu_load_exec (PRX libraries use a separate message). Never parse a
// filename, cache key, arbitrary SHA-1, or another module's hash as the EBOOT.
static std::string RPCS3PPUIdentityFromLog(std::string_view message) {
  if(message.size()>1024) return {};
  constexpr std::string_view prefix="PPU executable hash: PPU-";
  const auto begin=message.find(prefix);if(begin==std::string_view::npos)return {};
  const auto offset=begin+prefix.size();if(message.size()<offset+40)return {};
  std::string result="PPU-";
  for(size_t i=0;i<40;i++) {
    char c=message[offset+i];if(c>='A'&&c<='F')c+=32;
    if(!((c>='0'&&c<='9')||(c>='a'&&c<='f')))return {};
    result+=c;
  }
  if(message.size()>offset+40 && message[offset+40]!=' ' && message[offset+40]!='\n')return {};
  return result;
}
