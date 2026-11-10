// Host stub (REWINDBOX_ISO_IMAGE_LIFETIME_621 test).
#pragma once
#include "stdafx.h"
#include "Utilities/File.h"
namespace psf
{
struct registry { u64 size = 0; };
inline registry load_object(const fs::file& file, std::string_view) { registry result; result.size = file ? file.size() : 0; return result; }
}
