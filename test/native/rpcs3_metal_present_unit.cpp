// REWINDBOX_METAL_NATIVE: host unit test of rpcs3/Emu/RSX/Metal/MTLPresent.h (display buffer conversion and fit).
#include "Emu/RSX/Metal/MTLPresent.h"

#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <vector>

static int failures = 0;
#define CHECK(condition) do { if (!(condition)) { std::fprintf(stderr, "FAIL %s:%d: %s\n", __FILE__, __LINE__, #condition); ++failures; } } while (0)

int main()
{
	// Big-endian A8R8G8B8 words in guest memory: A, R, G, B bytes in that order.
	const u8 guest[8] = {0x11, 0x22, 0x33, 0x44, 0xff, 0x00, 0x80, 0x01};
	u32 converted[2] = {};
	mtl::present_pass::convert_row(guest, converted, 2);
	// The value of each word, stored natively: BGRA8 bytes B, G, R, A in memory.
	CHECK(converted[0] == 0x11223344u);
	CHECK(converted[1] == 0xff008001u);
	const u8* bytes = reinterpret_cast<const u8*>(converted);
	CHECK(bytes[0] == 0x44 && bytes[1] == 0x33 && bytes[2] == 0x22 && bytes[3] == 0x11); // B G R A

	// Same as the Vulkan renderer's loop over be_t<u32>: value = (A << 24) | (R << 16) | (G << 8) | B.
	std::vector<u8> row(4 * 1280);
	for (usz i = 0; i < row.size(); ++i) row[i] = static_cast<u8>(i * 37 + 11);
	std::vector<u32> out(1280);
	mtl::present_pass::convert_row(row.data(), out.data(), 1280);
	for (u32 x = 0; x < 1280; ++x)
	{
		const u32 expected = (u32{row[x * 4]} << 24) | (u32{row[x * 4 + 1]} << 16) | (u32{row[x * 4 + 2]} << 8) | row[x * 4 + 3];
		CHECK(out[x] == expected);
	}

	// Fit keeps the aspect ratio and fills one dimension.
	const auto wide = mtl::present_pass::fit(1280, 720, 2796, 1290); // 16:9 into an iPhone landscape drawable
	CHECK(std::fabs(wide.top - 1.0f) < 1e-6f && std::fabs(wide.bottom + 1.0f) < 1e-6f);
	CHECK(wide.right < 1.0f && std::fabs(wide.right + wide.left) < 1e-6f);
	CHECK(std::fabs((wide.right - wide.left) * 2796 / ((wide.top - wide.bottom) * 1290) - 1280.0 / 720.0) < 1e-3);
	const auto tall = mtl::present_pass::fit(640, 480, 1000, 2000);
	CHECK(std::fabs(tall.right - 1.0f) < 1e-6f && tall.top < 1.0f);
	const auto none = mtl::present_pass::fit(0, 720, 100, 100);
	CHECK(none.left == 0 && none.right == 0 && none.top == 0 && none.bottom == 0);

	if (failures)
	{
		std::fprintf(stderr, "%d failure(s)\n", failures);
		return 1;
	}
	std::puts("PASS: Metal present conversion (Vulkan byte order) and aspect fit");
	return 0;
}
