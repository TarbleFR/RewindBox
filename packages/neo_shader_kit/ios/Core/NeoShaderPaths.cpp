// SPDX-License-Identifier: GPL-3.0-or-later
#include "NeoShaderPaths.hpp"

#include <vector>

namespace neoshader {

namespace {

bool splitSegments(const std::string& path, std::vector<std::string>* segments) {
  size_t start = 0;
  while (start <= path.size()) {
    size_t end = path.find('/', start);
    if (end == std::string::npos) end = path.size();
    segments->push_back(path.substr(start, end - start));
    start = end + 1;
  }
  return true;
}

bool forbiddenCharacter(unsigned char character) {
  return character < 0x20 || character == 0x7F || character == '\\' || character == ':' || character == '$';
}

}  // namespace

bool isSafeRelativePath(const std::string& path) {
  if (path.empty() || path.size() > kMaxRelativePathLength || path.front() == '/') return false;
  for (unsigned char character : path) {
    if (forbiddenCharacter(character)) return false;
  }
  std::vector<std::string> segments;
  splitSegments(path, &segments);
  for (const std::string& segment : segments) {
    if (segment.empty() || segment == "." || segment == "..") return false;
  }
  return true;
}

std::string parentDirectory(const std::string& path) {
  const size_t slash = path.rfind('/');
  return slash == std::string::npos ? std::string() : path.substr(0, slash);
}

std::string baseName(const std::string& path) {
  const size_t slash = path.rfind('/');
  return slash == std::string::npos ? path : path.substr(slash + 1);
}

std::string fileExtension(const std::string& path) {
  const std::string name = baseName(path);
  const size_t dot = name.rfind('.');
  if (dot == std::string::npos || dot + 1 >= name.size()) return std::string();
  std::string extension = name.substr(dot + 1);
  for (char& character : extension) {
    if (character >= 'A' && character <= 'Z') character = static_cast<char>(character - 'A' + 'a');
  }
  return extension;
}

bool resolveRelative(const std::string& fromFile, const std::string& reference, std::string* out) {
  if (reference.empty() || reference.front() == '/' || reference.size() > kMaxRelativePathLength) return false;
  for (unsigned char character : reference) {
    if (forbiddenCharacter(character)) return false;
  }
  std::vector<std::string> folded;
  const std::string directory = parentDirectory(fromFile);
  if (!directory.empty()) {
    std::vector<std::string> base;
    splitSegments(directory, &base);
    for (const std::string& segment : base) {
      if (segment.empty() || segment == "." || segment == "..") return false;
      folded.push_back(segment);
    }
  }
  std::vector<std::string> relative;
  splitSegments(reference, &relative);
  for (size_t index = 0; index < relative.size(); index++) {
    const std::string& segment = relative[index];
    if (segment.empty()) {
      // "a//b" folds like a single slash; a trailing slash names a directory.
      if (index + 1 == relative.size()) return false;
      continue;
    }
    if (segment == ".") continue;
    if (segment == "..") {
      if (folded.empty()) return false;
      folded.pop_back();
      continue;
    }
    folded.push_back(segment);
  }
  if (folded.empty()) return false;
  std::string result;
  for (size_t index = 0; index < folded.size(); index++) {
    if (index > 0) result += '/';
    result += folded[index];
  }
  if (!isSafeRelativePath(result)) return false;
  *out = result;
  return true;
}

}  // namespace neoshader
