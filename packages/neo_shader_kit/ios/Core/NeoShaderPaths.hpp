// SPDX-License-Identifier: GPL-3.0-or-later
// Repository-relative paths shared by shader presets, includes, LUT
// textures and downloads. Portable C++17 (tested on Linux and macOS).
#pragma once

#include <string>

namespace neoshader {

/// Longest relative path accepted anywhere (bytes).
constexpr size_t kMaxRelativePathLength = 512;

/// A safe relative path: non-empty, '/'-separated, no leading '/', no empty,
/// "." or ".." segment, no backslash, NUL, control character, ':' or '$'
/// (RetroArch wildcards), at most kMaxRelativePathLength bytes. Every file
/// NeoStation reads or writes for a shader is named by such a path below
/// one root directory, so nothing can leave that directory.
bool isSafeRelativePath(const std::string& path);

/// Directory part of a safe relative path ("" for a file at the root).
std::string parentDirectory(const std::string& path);

/// Last segment of a path.
std::string baseName(const std::string& path);

/// Lower-case extension without the dot ("" when there is none).
std::string fileExtension(const std::string& path);

/// Resolves `reference`, written in the file `fromFile` (a safe relative
/// path), the way RetroArch resolves a preset entry or an #include: relative
/// to the directory of `fromFile`, "." and ".." folded. Fails when the
/// reference is absolute, uses a backslash or a wildcard, or the result
/// leaves the root or is not a safe relative path.
bool resolveRelative(const std::string& fromFile, const std::string& reference, std::string* out);

}  // namespace neoshader
