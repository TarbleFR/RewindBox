// SPDX-License-Identifier: GPL-3.0-or-later
#include "NeoShaderFiles.hpp"

#include <sys/stat.h>

#include <cstdio>
#include <utility>

#include "NeoShaderPaths.hpp"

namespace neoshader {

DirectoryFileProvider::DirectoryFileProvider(std::string root, size_t maxFileBytes)
    : root_(std::move(root)), maxFileBytes_(maxFileBytes) {}

bool DirectoryFileProvider::read(const std::string& path, std::string* contents) {
  if (!isSafeRelativePath(path)) return false;
  const std::string full = root_ + "/" + path;
  struct stat status;
  // lstat: a symbolic link (even to a file below the root) is not followed.
  if (lstat(full.c_str(), &status) != 0 || !S_ISREG(status.st_mode)) return false;
  if (static_cast<unsigned long long>(status.st_size) > maxFileBytes_) return false;
  FILE* file = std::fopen(full.c_str(), "rb");
  if (file == nullptr) return false;
  std::string data;
  data.resize(static_cast<size_t>(status.st_size));
  const size_t read = data.empty() ? 0 : std::fread(&data[0], 1, data.size(), file);
  // A file growing while it is read is cut at its size when it was checked.
  std::fclose(file);
  if (read != data.size()) return false;
  *contents = std::move(data);
  return true;
}

bool MemoryFileProvider::read(const std::string& path, std::string* contents) {
  auto found = files_.find(path);
  if (found == files_.end()) return false;
  *contents = found->second;
  return true;
}

}  // namespace neoshader
