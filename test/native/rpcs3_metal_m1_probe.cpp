// REWINDBOX_METAL_NATIVE: Metal 4 probe of the native renderer's presentation path, run on a real Metal device.
//
// Built for macOS against rpcs3/Emu/RSX/Metal/MTLAPIApple.mm (the same Metal 4 calls the iOS renderer makes):
// MTL4 queue, allocator, command buffer, compiler, residency set, argument table, shared-event fence, and the
// presentation pass of MTLPresent.h drawn into an offscreen BGRA8 target that is read back and compared pixel
// by pixel with the expected conversion of a known big-endian A8R8G8B8 display buffer. Exit code 0 = pass,
// 1 = mismatch or error, 2 = this machine has no Metal 4 GPU (the caller decides whether that is allowed).

#include "Emu/RSX/Metal/MTLAPI.h"
#include "Emu/RSX/Metal/MTLPresent.h"

#include <cstdio>
#include <cstring>
#include <string>
#include <vector>

namespace
{
	int fail(const char* what, const std::string& detail = {})
	{
		std::fprintf(stderr, "FAIL: %s%s%s\n", what, detail.empty() ? "" : ": ", detail.c_str());
		return 1;
	}
}

int main()
{
	const mtl::object device = mtl::create_system_default_device();
	if (!device)
	{
		std::puts("NO METAL DEVICE");
		return 2;
	}

	const mtl::device_info info = mtl::query_device(device);
	std::printf("device '%s' Apple7=%d Apple8=%d Apple9=%d Metal4=%d BC=%d unified=%d\n", info.name.c_str(), info.apple7, info.apple8,
		info.apple9, info.metal4, info.bc_texture_compression, info.unified_memory);
	if (!info.metal4)
	{
		std::puts("NO METAL 4 GPU");
		return 2;
	}

	const mtl::object queue = mtl::new_command_queue(device);
	const mtl::object compiler = mtl::new_compiler(device);
	const mtl::object event = mtl::new_shared_event(device);
	const mtl::object residency = mtl::new_residency_set(device, 8);
	const mtl::object allocator = mtl::new_command_allocator(device);
	const mtl::object command_buffer = mtl::new_command_buffer(device);
	if (!queue || !compiler || !event || !residency || !allocator || !command_buffer)
	{
		return fail("Metal 4 object creation");
	}

	std::string error;
	const mtl::object library = mtl::compile_library(compiler, mtl::present_pass::source, error);
	if (!library)
	{
		return fail("present library", error);
	}

	mtl::render_pipeline_descriptor pipeline_desc{};
	pipeline_desc.library = library;
	pipeline_desc.vertex_function = std::string(mtl::present_pass::vertex_function);
	pipeline_desc.fragment_function = std::string(mtl::present_pass::fragment_function);
	pipeline_desc.color[0].format = mtl::pixel_format::bgra8_unorm;
	pipeline_desc.label = "probe present";
	const mtl::object pipeline = mtl::new_render_pipeline(compiler, pipeline_desc, error);
	if (!pipeline)
	{
		return fail("present pipeline", error);
	}

	// A 4x2 display buffer in guest byte order (A, R, G, B per pixel).
	constexpr u32 source_width = 4, source_height = 2;
	std::vector<u8> guest(source_width * source_height * 4);
	for (u32 i = 0; i < source_width * source_height; ++i)
	{
		guest[i * 4 + 0] = 0x80;                          // A (not shown)
		guest[i * 4 + 1] = static_cast<u8>(0x10 + i * 0x20); // R
		guest[i * 4 + 2] = static_cast<u8>(0xf0 - i * 0x10); // G
		guest[i * 4 + 3] = static_cast<u8>(0x08 * i);        // B
	}

	std::vector<u32> converted(source_width * source_height);
	for (u32 row = 0; row < source_height; ++row)
	{
		mtl::present_pass::convert_row(guest.data() + row * source_width * 4, converted.data() + row * source_width, source_width);
	}

	mtl::texture_descriptor source_desc{};
	source_desc.format = mtl::pixel_format::bgra8_unorm;
	source_desc.width = source_width;
	source_desc.height = source_height;
	source_desc.usage = mtl::usage_shader_read;
	source_desc.storage = mtl::storage_mode::shared;
	const mtl::object source = mtl::new_texture(device, source_desc);

	// The target: each source pixel covers 2x4 target pixels with nearest sampling and a full quad.
	constexpr u32 target_width = 8, target_height = 8;
	mtl::texture_descriptor target_desc{};
	target_desc.format = mtl::pixel_format::bgra8_unorm;
	target_desc.width = target_width;
	target_desc.height = target_height;
	target_desc.usage = mtl::usage_render_target | mtl::usage_shader_read;
	target_desc.storage = mtl::storage_mode::shared;
	const mtl::object target = mtl::new_texture(device, target_desc);
	const mtl::object constants = mtl::new_buffer(device, 256, mtl::storage_mode::shared);
	const mtl::object table = mtl::new_argument_table(device, 1, 1, 1);
	mtl::sampler_descriptor sampler_desc{};
	const mtl::object sampler = mtl::new_sampler(device, sampler_desc);
	if (!source || !target || !constants || !table || !sampler)
	{
		return fail("probe resources");
	}

	mtl::texture_replace_region(source, {{0, 0, 0}, {source_width, source_height, 1}}, 0, 0, converted.data(), source_width * 4, 0);
	mtl::residency_add(residency, source);
	mtl::residency_add(residency, target);
	mtl::residency_add(residency, constants);
	mtl::residency_commit(residency);
	mtl::queue_add_residency_set(queue, residency);

	mtl::present_pass::parameters params{};
	params.rect = {-1.f, -1.f, 1.f, 1.f};
	std::memcpy(mtl::buffer_contents(constants), &params, sizeof(params));

	mtl::begin_command_buffer(command_buffer, allocator, "probe frame");
	mtl::render_pass_descriptor pass{};
	pass.color[0].texture = target;
	pass.color[0].load = mtl::load_action::clear;
	pass.color[0].store = mtl::store_action::store;
	pass.color[0].clear = {0., 0., 0., 1.};
	const mtl::object encoder = mtl::begin_render_pass(command_buffer, pass, "probe present");
	if (!encoder)
	{
		return fail("render encoder");
	}

	mtl::table_set_buffer(table, constants, 0, 0);
	mtl::table_set_texture(table, source, 0);
	mtl::table_set_sampler(table, sampler, 0);
	mtl::set_render_pipeline(encoder, pipeline);
	mtl::set_argument_table(encoder, table, mtl::stage_vertex | mtl::stage_fragment);
	mtl::draw_primitives(encoder, mtl::primitive_type::triangle_strip, 0, 4);
	mtl::end_encoding(encoder);
	mtl::end_command_buffer(command_buffer);
	mtl::commit(queue, command_buffer);
	mtl::signal_event(queue, event, 1);
	if (!mtl::wait_signaled_value(event, 1, 10000))
	{
		return fail("the frame fence was not signalled within 10 s");
	}

	std::vector<u32> pixels(target_width * target_height);
	mtl::texture_get_bytes(target, pixels.data(), target_width * 4, 0, {{0, 0, 0}, {target_width, target_height, 1}}, 0, 0);

	int mismatches = 0;
	for (u32 y = 0; y < target_height; ++y)
	{
		for (u32 x = 0; x < target_width; ++x)
		{
			const u32 sx = x * source_width / target_width;
			const u32 sy = y * source_height / target_height;
			// The pass shows RGB and writes opaque alpha.
			const u32 expected = (converted[sy * source_width + sx] & 0x00ffffffu) | 0xff000000u;
			if (pixels[y * target_width + x] != expected && mismatches++ < 8)
			{
				std::fprintf(stderr, "pixel (%u,%u) = %08x, expected %08x\n", x, y, pixels[y * target_width + x], expected);
			}
		}
	}

	if (mismatches)
	{
		return fail("presented pixels differ from the converted display buffer", std::to_string(mismatches) + " of 64");
	}

	std::puts("PASS: Metal 4 presentation of a guest A8R8G8B8 buffer (queue, allocator, compiler, residency, argument table, fence)");
	return 0;
}
