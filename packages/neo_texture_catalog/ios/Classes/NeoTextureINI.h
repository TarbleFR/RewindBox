// SPDX-License-Identifier: GPL-3.0-or-later
// One key of one INI section, every other byte of the file kept. Dolphin's
// game INIs and PCSX2's per-game INIs both use "[Section]" and "key = value".
#pragma once
#include <optional>
#include <string>
#include <vector>

namespace NeoTextureINI {

inline std::string Trim(const std::string& s) {
  size_t a = 0, b = s.size();
  while (a < b && (s[a] == ' ' || s[a] == '\t' || s[a] == '\r')) ++a;
  while (b > a && (s[b - 1] == ' ' || s[b - 1] == '\t' || s[b - 1] == '\r')) --b;
  return s.substr(a, b - a);
}

inline bool SameKey(const std::string& a, const std::string& b) {
  if (a.size() != b.size()) return false;
  for (size_t i = 0; i < a.size(); ++i) {
    char x = a[i], y = b[i];
    if (x >= 'A' && x <= 'Z') x = char(x - 'A' + 'a');
    if (y >= 'A' && y <= 'Z') y = char(y - 'A' + 'a');
    if (x != y) return false;
  }
  return true;
}

inline std::vector<std::string> Lines(const std::string& text) {
  std::vector<std::string> lines;
  size_t start = 0;
  while (start < text.size()) {
    size_t end = text.find('\n', start);
    if (end == std::string::npos) end = text.size();
    lines.push_back(text.substr(start, end - start));
    start = end + 1;
  }
  return lines;
}

// The last definition wins, as in Dolphin's IniFile and PCSX2's SimpleIni.
inline std::optional<std::string> Value(const std::string& text, const std::string& section, const std::string& key) {
  std::optional<std::string> found;
  std::string current;
  bool inSection = false;
  for (const auto& raw : Lines(text)) {
    const std::string line = Trim(raw);
    if (line.size() >= 2 && line.front() == '[' && line.back() == ']') {
      current = line.substr(1, line.size() - 2);
      inSection = current == section;
      continue;
    }
    if (!inSection || line.empty() || line[0] == '#' || line[0] == ';') continue;
    const size_t equals = line.find('=');
    if (equals == std::string::npos) continue;
    if (SameKey(Trim(line.substr(0, equals)), key)) found = Trim(line.substr(equals + 1));
  }
  return found;
}

// Replaces the last definition of key in section, or appends it at the end
// of the section (created at the end of the file when missing).
inline std::string Set(const std::string& text, const std::string& section, const std::string& key, const std::string& value) {
  std::vector<std::string> lines = Lines(text);
  const bool crlf = text.find("\r\n") != std::string::npos;
  long sectionEnd = -1, keyLine = -1;
  bool inSection = false;
  for (long i = 0; i < long(lines.size()); ++i) {
    const std::string line = Trim(lines[size_t(i)]);
    if (line.size() >= 2 && line.front() == '[' && line.back() == ']') {
      inSection = line.substr(1, line.size() - 2) == section;
      if (inSection) sectionEnd = i;
      continue;
    }
    if (!inSection) continue;
    if (!line.empty()) sectionEnd = i;
    if (line.empty() || line[0] == '#' || line[0] == ';') continue;
    const size_t equals = line.find('=');
    if (equals != std::string::npos && SameKey(Trim(line.substr(0, equals)), key)) keyLine = i;
  }
  const std::string eol = crlf ? "\r" : "";
  const std::string entry = key + " = " + value + eol;
  if (keyLine >= 0) {
    lines[size_t(keyLine)] = entry;
  } else if (sectionEnd >= 0) {
    lines.insert(lines.begin() + sectionEnd + 1, entry);
  } else {
    if (!lines.empty() && !Trim(lines.back()).empty()) lines.push_back(eol);
    lines.push_back("[" + section + "]" + eol);
    lines.push_back(entry);
  }
  std::string out;
  for (const auto& line : lines) out += line + "\n";
  return out;
}

}  // namespace NeoTextureINI
