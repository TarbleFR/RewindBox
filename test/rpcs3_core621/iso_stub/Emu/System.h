// Host stub (REWINDBOX_ISO_IMAGE_LIFETIME_621 test).
#pragma once
#include "stdafx.h"
struct emulator_stub
{
	bool IsPathInsideDir(std::string_view path, std::string_view dir, bool) const { return path.substr(0, dir.size()) == dir; }
};
inline emulator_stub Emu;
