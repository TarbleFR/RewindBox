// SPDX-License-Identifier: GPL-3.0-or-later
#include "NeoShaderConfig.hpp"

#include <cerrno>
#include <climits>
#include <cstdlib>

namespace neoshader {

namespace {

bool isGraph(char character) {
  const unsigned char value = static_cast<unsigned char>(character);
  return value > 0x20 && value != 0x7F;
}

bool isBlank(char character) { return character == ' ' || character == '\t' || character == '\r' || character == '\n'; }

/// Position of the quote closing a literal starting at `start` (just after
/// the opening quote): the first quote preceded by an even run of
/// backslashes. npos when unterminated.
size_t literalEnd(const std::string& line, size_t start, bool* escaped) {
  *escaped = false;
  for (size_t position = line.find('"', start); position != std::string::npos;
       position = line.find('"', position + 1)) {
    size_t backslashes = 0;
    while (position - backslashes > start && line[position - backslashes - 1] == '\\') backslashes++;
    if (backslashes % 2 == 0) return position;
    *escaped = true;
  }
  return std::string::npos;
}

std::string unescape(const std::string& value) {
  std::string result;
  result.reserve(value.size());
  for (size_t index = 0; index < value.size(); index++) {
    if (value[index] == '\\' && index + 1 < value.size() && (value[index + 1] == '"' || value[index + 1] == '\\')) {
      result += value[index + 1];
      index++;
    } else {
      result += value[index];
    }
  }
  return result;
}

/// config_file_extract_value on `line` from `position`.
std::string extractValue(const std::string& line, size_t position) {
  while (position < line.size() && isBlank(line[position])) position++;
  if (position >= line.size()) return std::string();
  if (line[position] == '"') {
    const size_t start = position + 1;
    bool escaped = false;
    size_t end = literalEnd(line, start, &escaped);
    if (end == std::string::npos) end = line.size();  // unterminated: to the end of the line
    const std::string raw = line.substr(start, end - start);
    return escaped ? unescape(raw) : raw;
  }
  size_t end = position;
  while (end < line.size() && isGraph(line[end])) end++;
  return line.substr(position, end - position);
}

}  // namespace

ConfigFile ConfigFile::parse(const std::string& text) {
  ConfigFile config;
  size_t lineStart = 0;
  while (lineStart <= text.size()) {
    size_t lineEnd = text.find('\n', lineStart);
    if (lineEnd == std::string::npos) lineEnd = text.size();
    std::string line = text.substr(lineStart, lineEnd - lineStart);
    lineStart = lineEnd + 1;

    const size_t hash = line.find('#');
    if (hash == 0) {
      // Whole-line comment, possibly a directive.
      const std::string comment = line.substr(1);
      std::vector<std::string>* target = nullptr;
      size_t length = 0;
      if (comment.compare(0, 10, "reference ") == 0) {
        target = &config.references_;
        length = 10;
      } else if (comment.compare(0, 8, "include ") == 0) {
        target = &config.includes_;
        length = 8;
      }
      if (target != nullptr) {
        const std::string path = extractValue(comment, length);
        if (!path.empty()) target->push_back(path);
      }
      continue;
    }
    if (hash != std::string::npos) {
      // A '#' inside a quoted value is kept; any other one ends the line.
      const size_t quote = line.find('"');
      bool keep = false;
      if (quote != std::string::npos && quote < hash) {
        bool escaped = false;
        const size_t end = literalEnd(line, quote + 1, &escaped);
        keep = end != std::string::npos && end > hash;
      }
      if (!keep) line.erase(hash);
    }

    size_t position = 0;
    while (position < line.size() && isBlank(line[position])) position++;
    const size_t keyStart = position;
    while (position < line.size() && isGraph(line[position])) position++;
    if (position == keyStart) continue;
    // The key is the run of printable characters; "key=value" without spaces
    // has no '=' after that run and is invalid in RetroArch too.
    const std::string key = line.substr(keyStart, position - keyStart);
    while (position < line.size() && isBlank(line[position])) position++;
    if (position >= line.size() || line[position] != '=') continue;
    const std::string value = extractValue(line, position + 1);
    if (config.find(key) == nullptr) config.entries_.emplace_back(key, value);
  }
  return config;
}

const std::string* ConfigFile::find(const std::string& key) const {
  for (const auto& entry : entries_) {
    if (entry.first == key) return &entry.second;
  }
  return nullptr;
}

bool ConfigFile::getBool(const std::string& key, bool* value) const {
  const std::string* text = find(key);
  if (text == nullptr) return false;
  if (*text == "true" || *text == "1") {
    *value = true;
    return true;
  }
  if (*text == "false" || *text == "0") {
    *value = false;
    return true;
  }
  return false;
}

bool ConfigFile::getFloat(const std::string& key, float* value) const {
  const std::string* text = find(key);
  if (text == nullptr || text->empty()) return false;
  char* end = nullptr;
  const double number = std::strtod(text->c_str(), &end);
  if (end == text->c_str()) return false;
  *value = static_cast<float>(number);
  return true;
}

bool ConfigFile::getInt(const std::string& key, int* value) const {
  const std::string* text = find(key);
  if (text == nullptr || text->empty()) return false;
  errno = 0;
  char* end = nullptr;
  const long number = std::strtol(text->c_str(), &end, 0);
  if (errno != 0 || end == text->c_str() || number < INT_MIN || number > INT_MAX) return false;
  *value = static_cast<int>(number);
  return true;
}

bool ConfigFile::getUnsigned(const std::string& key, unsigned* value) const {
  const std::string* text = find(key);
  if (text == nullptr || text->empty()) return false;
  errno = 0;
  char* end = nullptr;
  const unsigned long number = std::strtoul(text->c_str(), &end, 0);
  if (errno != 0 || end == text->c_str() || number > UINT_MAX) return false;
  *value = static_cast<unsigned>(number);
  return true;
}

}  // namespace neoshader
