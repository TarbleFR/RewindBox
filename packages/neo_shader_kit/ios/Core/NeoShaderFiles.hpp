// SPDX-License-Identifier: GPL-3.0-or-later
// File access and error reporting shared by the shader kit's portable core.
#pragma once

#include <map>
#include <string>

namespace neoshader {

/// Machine-readable reason a shader is refused, plus a technical detail for
/// diagnostics (file, line, compiler message). Codes are stable: the
/// application translates them, the detail is shown raw in diagnostics only.
struct ShaderError {
  std::string code;
  std::string detail;
};

/// Reads repository-relative files (isSafeRelativePath) below one root.
class FileProvider {
 public:
  virtual ~FileProvider() = default;
  /// False when the file is missing, unreadable or larger than the limit.
  virtual bool read(const std::string& path, std::string* contents) = 0;
};

/// Reads files below a directory of the local file system. Symbolic links
/// and files larger than `maxFileBytes` are refused.
class DirectoryFileProvider : public FileProvider {
 public:
  explicit DirectoryFileProvider(std::string root, size_t maxFileBytes = 16u * 1024u * 1024u);
  bool read(const std::string& path, std::string* contents) override;

 private:
  std::string root_;
  size_t maxFileBytes_;
};

/// In-memory files (tests, and files already read by the caller).
class MemoryFileProvider : public FileProvider {
 public:
  void add(const std::string& path, const std::string& contents) { files_[path] = contents; }
  bool read(const std::string& path, std::string* contents) override;

 private:
  std::map<std::string, std::string> files_;
};

}  // namespace neoshader
