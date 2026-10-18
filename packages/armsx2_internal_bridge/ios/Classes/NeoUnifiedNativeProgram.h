// SPDX-License-Identifier: GPL-3.0-or-later
#pragma once
#include "NeoCheatDocument.h"

namespace NeoUnifiedNative {
// Parse the whole source program before returning any instruction. Native
// formats are never exchanged by changing an extension or by clipping a code.
inline NeoCheat::Result parse(const std::string& content, const std::string& dialect,
                              const std::string& name, const std::string& author,
                              bool ps2) {
  NeoCheat::Result rejected; rejected.error = "format";
  if ((ps2 && dialect != "pnach") ||
      (!ps2 && dialect != "gecko" && dialect != "actionReplay")) return rejected;
  const auto actual = NeoCheat::detectedFormat(content, dialect);
  auto result = NeoCheat::parseDocument(content, actual, name, author);
  if (!result) return result;
  for (const auto& entry : result.entries)
    if (ps2 ? entry.type != "pnach" : entry.type != dialect) return rejected;
  return result;
}
} // namespace NeoUnifiedNative
