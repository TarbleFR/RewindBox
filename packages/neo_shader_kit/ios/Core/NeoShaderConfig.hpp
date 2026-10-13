// SPDX-License-Identifier: GPL-3.0-or-later
// The subset of RetroArch's config_file format used by .slangp presets
// (libretro-common/file/config_file.c): "key = value" lines, quoted or bare
// values, '#' comments, and the "#reference" directive.
#pragma once

#include <string>
#include <utility>
#include <vector>

namespace neoshader {

class ConfigFile {
 public:
  /// Parses `text`. Like RetroArch:
  /// - a line whose first character is '#' is a comment, except
  ///   "#reference <path>" (kept in `references`, in order) and
  ///   "#include <path>" (recorded in `includes`; presets never use it);
  /// - elsewhere '#' starts a trailing comment unless it is inside a quoted
  ///   value;
  /// - a key is a run of printable non-space characters followed by '=';
  /// - a quoted value runs to the next quote ("\"" and "\\" are unescaped),
  ///   a bare value to the next space;
  /// - when a key appears twice, the first value is kept.
  static ConfigFile parse(const std::string& text);

  const std::vector<std::string>& references() const { return references_; }
  const std::vector<std::string>& includes() const { return includes_; }
  const std::vector<std::pair<std::string, std::string>>& entries() const { return entries_; }

  bool has(const std::string& key) const { return find(key) != nullptr; }
  const std::string* find(const std::string& key) const;
  /// config_get_bool: "true"/"1" or "false"/"0"; anything else fails.
  bool getBool(const std::string& key, bool* value) const;
  /// config_get_float: strtod of the value; fails when nothing parses.
  bool getFloat(const std::string& key, float* value) const;
  /// config_get_int / config_get_uint: strtol / strtoul, base 0.
  bool getInt(const std::string& key, int* value) const;
  bool getUnsigned(const std::string& key, unsigned* value) const;

 private:
  std::vector<std::string> references_;
  std::vector<std::string> includes_;
  std::vector<std::pair<std::string, std::string>> entries_;
};

}  // namespace neoshader
