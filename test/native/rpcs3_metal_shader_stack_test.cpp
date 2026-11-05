// REWINDBOX_METAL_NATIVE (M2): host test of the native Metal renderer's shader stack.
//
// Real RSX vertex and fragment programs (encoded below in the RSX ucode formats) go through the Metal
// decompilers (Emu/RSX/Metal/MTL{Vertex,Fragment}Program.cpp), glslang (Emu/RSX/Program/SPIRVCommon.cpp) and
// SPIRV-Cross (Emu/RSX/Metal/MTLShaderTranslator.cpp). The test checks the GLSL, the SPIR-V and the slot
// contract of every resource, and writes each MSL translation to the directory given as argv[1] so that the
// macOS job can compile it with Apple's offline Metal compiler for iOS. Exit 0 = pass.

#include "stdafx.h"

#include "Emu/RSX/Metal/MTLFragmentProgram.h"
#include "Emu/RSX/Metal/MTLVertexProgram.h"
#include "Emu/RSX/Program/RSXFragmentProgram.h"
#include "Emu/RSX/Program/RSXVertexProgram.h"
#include "Emu/RSX/Program/SPIRVCommon.h"
#include "Emu/RSX/gcm_enums.h"

#include <cstdio>
#include <fstream>
#include <string>
#include <vector>

namespace
{
	int g_failures = 0;

	void check(bool condition, const std::string& what)
	{
		if (!condition)
		{
			std::fprintf(stderr, "FAIL: %s\n", what.c_str());
			++g_failures;
		}
	}

	bool contains(const std::string& haystack, std::string_view needle)
	{
		return haystack.find(needle) != std::string::npos;
	}

	const mtl::resource_slot* find_slot(const mtl::translation_result& result, std::string_view name)
	{
		for (const auto& slot : result.slots)
		{
			if (slot.name == name)
			{
				return &slot;
			}
		}
		return nullptr;
	}

	void write_msl(const char* directory, const std::string& name, const std::string& msl)
	{
		if (!directory)
		{
			return;
		}

		std::ofstream out(std::string(directory) + "/" + name + ".metal", std::ios::binary);
		out << msl;
		check(out.good(), "write " + name + ".metal");
	}

	// ---- RSX vertex program encoding (RSXVertexProgram.h: D0..D3, SRC) ----

	enum : u32
	{
		vp_temp = RSX_VP_REGISTER_TYPE_TEMP,
		vp_input = RSX_VP_REGISTER_TYPE_INPUT,
		vp_constant = RSX_VP_REGISTER_TYPE_CONSTANT,
	};

	u32 vp_src(u32 reg_type, u32 tmp = 0)
	{
		SRC src{};
		src.reg_type = reg_type;
		src.tmp_src = tmp;
		src.swz_x = 0;
		src.swz_y = 1;
		src.swz_z = 2;
		src.swz_w = 3;
		return src.HEX;
	}

	struct vp_instruction
	{
		u32 vec_opcode;
		u32 output;        // o[] index (dst_regN)
		u32 write_mask;    // bit 3 = x .. bit 0 = w
		u32 src0;
		u32 src1;
		u32 src2;
		u32 input = 0;     // v[] index read by INPUT sources
		u32 constant = 0;  // c[] index read by CONSTANT sources
	};

	RSXVertexProgram make_vertex_program(const std::vector<vp_instruction>& code, u32 output_mask)
	{
		RSXVertexProgram prog{};
		for (usz i = 0; i < code.size(); ++i)
		{
			const auto& in = code[i];
			D0 d0{};
			D1 d1{};
			D2 d2{};
			D3 d3{};

			SRC s0{}, s1{}, s2{};
			s0.HEX = in.src0;
			s1.HEX = in.src1;
			s2.HEX = in.src2;

			d0.cond = 7;         // condition TR: always write (0 = FL never writes)
			d0.mask_x = 0;       // identity condition swizzle
			d0.mask_y = 1;
			d0.mask_z = 2;
			d0.mask_w = 3;
			d0.dst_tmp = 0x3f;   // no temporary destination
			d0.vec_result = 1;   // the vector result goes to o[]

			d1.src0h = s0.src0h;
			d1.input_src = in.input;
			d1.const_src = in.constant;
			d1.vec_opcode = in.vec_opcode;
			d1.sca_opcode = RSX_SCA_OPCODE_NOP;

			d2.src0l = s0.src0l;
			d2.src1 = s1.src1;
			d2.src2h = s2.src2h;

			d3.end = (i + 1 == code.size()) ? 1 : 0;
			d3.dst = in.output;
			d3.sca_dst_tmp = 0x3f;
			d3.vec_writemask_x = (in.write_mask >> 3) & 1;
			d3.vec_writemask_y = (in.write_mask >> 2) & 1;
			d3.vec_writemask_z = (in.write_mask >> 1) & 1;
			d3.vec_writemask_w = in.write_mask & 1;
			d3.src2l = s2.src2l;

			prog.data.push_back(d0.HEX);
			prog.data.push_back(d1.HEX);
			prog.data.push_back(d2.HEX);
			prog.data.push_back(d3.HEX);
			prog.instruction_mask.set(static_cast<u32>(i));
		}

		prog.output_mask = output_mask;
		return prog;
	}

	// ---- RSX fragment program encoding (RSXFragmentProgram.h: OPDEST, SRC0..2; stored as FPIR::compile does) ----

	u32 fp_src(u32 reg_type, u32 index = 0)
	{
		SRC0 src{};
		src.reg_type = reg_type;
		src.tmp_reg_index = index;
		src.swizzle_x = 0;
		src.swizzle_y = 1;
		src.swizzle_z = 2;
		src.swizzle_w = 3;
		src.exec_if_lt = 1;
		src.exec_if_eq = 1;
		src.exec_if_gr = 1;
		src.cond_swizzle_x = 0;
		src.cond_swizzle_y = 1;
		src.cond_swizzle_z = 2;
		src.cond_swizzle_w = 3;
		return src.HEX;
	}

	struct fp_instruction
	{
		u32 opcode;
		u32 dest_reg;
		u32 src0;
		u32 src1 = 0;
		u32 src2 = 0;
		u32 input_attr = 0;   // f[] index (rsx_fp_input_attr_regs)
		u32 tex_num = 0;
		bool constant = false; // one literal constant follows the instruction
	};

	struct fragment_ucode
	{
		std::vector<u32> words;
		RSXFragmentProgram prog{};
	};

	void push_fp_word(std::vector<u32>& out, u32 host_word)
	{
		// FPIR::compile(): each host word is read as two big-endian halves and stored low half first.
		const u8* bytes = reinterpret_cast<const u8*>(&host_word);
		const u16 low = static_cast<u16>((bytes[0] << 8) | bytes[1]);
		const u16 high = static_cast<u16>((bytes[2] << 8) | bytes[3]);
		out.push_back(static_cast<u32>(low) | (static_cast<u32>(high) << 16));
	}

	void make_fragment_program(fragment_ucode& ucode, const std::vector<fp_instruction>& code, u32 ctrl, u32 texture_dimensions)
	{
		for (usz i = 0; i < code.size(); ++i)
		{
			const auto& in = code[i];
			OPDEST dst{};
			dst.end = (i + 1 == code.size()) ? 1 : 0;
			dst.dest_reg = in.dest_reg;
			dst.mask_x = dst.mask_y = dst.mask_z = dst.mask_w = 1;
			dst.src_attr_reg_num = in.input_attr;
			dst.tex_num = in.tex_num;
			dst.prec = RSX_FP_PRECISION_REAL;
			dst.opcode = in.opcode & 0x3f;

			SRC1 src1{};
			src1.HEX = in.src1;
			src1.opcode_hi = (in.opcode >> 6) & 1;

			push_fp_word(ucode.words, dst.HEX);
			push_fp_word(ucode.words, in.src0);
			push_fp_word(ucode.words, src1.HEX);
			push_fp_word(ucode.words, in.src2);

			if (in.constant)
			{
				const f32 values[4] = { 0.25f, 0.5f, 0.75f, 1.f };
				for (const f32 value : values)
				{
					push_fp_word(ucode.words, std::bit_cast<u32>(value));
				}
			}
		}

		ucode.prog.data = RSXFragmentProgram::data_storage_helper(ucode.words.data());
		ucode.prog.ucode_length = static_cast<u32>(ucode.words.size() * 4);
		ucode.prog.total_length = ucode.prog.ucode_length;
		ucode.prog.ctrl = ctrl;
		ucode.prog.mrt_buffers_count = 1;
		ucode.prog.texture_state.texture_dimensions = texture_dimensions;
		ucode.prog.valid = true;
	}

	constexpr u32 fp_temp = RSX_FP_REGISTER_TYPE_TEMP;
	constexpr u32 fp_input = RSX_FP_REGISTER_TYPE_INPUT;
	constexpr u32 fp_constant = RSX_FP_REGISTER_TYPE_CONSTANT;
	constexpr u32 attr_col0 = 1;
	constexpr u32 attr_tex0 = 4;

	void test_vertex(const char* out_dir, const mtl::shader_device_caps& caps)
	{
		// DP4 o[0].xyzw = c[0..3] . v[0]; MOV o[1] = v[3] (colour); MOV o[7] = v[8] (texcoord 0)
		const std::vector<vp_instruction> code =
		{
			{ RSX_VEC_OPCODE_DP4, 0, 0b1000, vp_src(vp_constant), vp_src(vp_input), vp_src(vp_temp), 0, 0 },
			{ RSX_VEC_OPCODE_DP4, 0, 0b0100, vp_src(vp_constant), vp_src(vp_input), vp_src(vp_temp), 0, 1 },
			{ RSX_VEC_OPCODE_DP4, 0, 0b0010, vp_src(vp_constant), vp_src(vp_input), vp_src(vp_temp), 0, 2 },
			{ RSX_VEC_OPCODE_DP4, 0, 0b0001, vp_src(vp_constant), vp_src(vp_input), vp_src(vp_temp), 0, 3 },
			{ RSX_VEC_OPCODE_MOV, 1, 0b1111, vp_src(vp_input), vp_src(vp_temp), vp_src(vp_temp), 3 },
			{ RSX_VEC_OPCODE_MOV, 7, 0b1111, vp_src(vp_input), vp_src(vp_temp), vp_src(vp_temp), 8 },
		};

		const auto prog = make_vertex_program(code, CELL_GCM_ATTRIB_OUTPUT_MASK_FRONTDIFFUSE | CELL_GCM_ATTRIB_OUTPUT_MASK_TEX0);

		mtl::vertex_program vp{};
		vp.id = 1;
		vp.Decompile(prog, caps);

		check(contains(vp.glsl_source, "persistent_input_stream"), "vertex GLSL fetches the persistent stream");
		check(contains(vp.glsl_source, "_fetch_constant(0)") || contains(vp.glsl_source, "_fetch_constant(0 "), "vertex GLSL reads c[0]");
		check(contains(vp.glsl_source, "diff_color"), "vertex GLSL writes the colour");
		check(vp.constant_ids.size() == 4, "vertex program uses 4 constants");

		check(vp.Compile(), "vertex GLSL -> SPIR-V: " + vp.compile_error);
		if (vp.spirv.empty())
		{
			std::fprintf(stderr, "%s\n", vp.glsl_source.c_str());
			return;
		}

		for (const bool points : { false, true })
		{
			const auto& msl = vp.get_msl(points);
			const std::string label = points ? "vertex points" : "vertex";
			check(msl.ok, label + " SPIR-V -> MSL: " + msl.error);
			if (!msl.ok)
			{
				continue;
			}

			check(msl.entry_point == "main0", label + " entry point is main0 (" + msl.entry_point + ")");
			check(contains(msl.msl, "vertex "), label + " MSL has a vertex function");
			check(contains(msl.msl, "texture_buffer<uint>"), label + " streams are native texture buffers");
			check(contains(msl.msl, "[[buffer(30)]]"), label + " push constants at buffer 30");
			check(contains(msl.msl, "[[point_size]]") == points, label + " point size only for points");

			const auto* persistent = find_slot(msl, "persistent_input_stream");
			const auto* volatile_stream = find_slot(msl, "volatile_input_stream");
			const auto* draw_params = find_slot(msl, "DrawParametersBuffer");
			const auto* context = find_slot(msl, "VertexContextBuffer");
			const auto* constants = find_slot(msl, "VertexConstantsBuffer");
			const auto* push = find_slot(msl, "push_constants_block");
			check(persistent && persistent->texture == 0 && persistent->used, label + " persistent stream at texture 0");
			check(volatile_stream && volatile_stream->texture == 1, label + " volatile stream at texture 1");
			check(draw_params && draw_params->buffer == 2 && draw_params->used, label + " draw parameters at buffer 2");
			check(context && context->buffer == 3 && context->used, label + " vertex context at buffer 3");
			check(constants && constants->buffer == 4 && constants->used, label + " vertex constants at buffer 4");
			check(push && push->buffer == mtl::push_constant_buffer_slot && push->used && msl.uses_push_constants, label + " push constants used");
			check(contains(msl.msl, "[[texture(0)]]") && contains(msl.msl, "[[buffer(2)]]") && contains(msl.msl, "[[buffer(3)]]") && contains(msl.msl, "[[buffer(4)]]"),
				label + " MSL slots match the slot table");

			write_msl(out_dir, points ? "vp_transform_points" : "vp_transform", msl.msl);
		}
	}

	void test_fragment(const char* out_dir, const mtl::shader_device_caps& caps, const char* name,
		const std::vector<fp_instruction>& code, u32 ctrl, u32 texture_dimensions, bool expect_texture, bool expect_constants)
	{
		fragment_ucode ucode{};
		make_fragment_program(ucode, code, ctrl, texture_dimensions);

		mtl::fragment_program fp{};
		fp.id = 2;
		fp.Decompile(ucode.prog, caps);

		check(contains(fp.glsl_source, "ocol0"), std::string(name) + " GLSL writes ocol0");
		check(fp.Compile(), std::string(name) + " GLSL -> SPIR-V: " + fp.compile_error);
		if (fp.spirv.empty())
		{
			std::fprintf(stderr, "%s\n", fp.glsl_source.c_str());
			return;
		}

		const mtl::fragment_variant_key key{};
		const auto& msl = fp.get_msl(key);
		check(msl.ok, std::string(name) + " SPIR-V -> MSL: " + msl.error);
		if (!msl.ok)
		{
			std::fprintf(stderr, "%s\n", fp.glsl_source.c_str());
			return;
		}

		check(contains(msl.msl, "fragment "), std::string(name) + " MSL has a fragment function");
		check(contains(msl.msl, "[[color(0)]]"), std::string(name) + " MSL writes colour 0");

		const auto* context = find_slot(msl, "FragmentStateBuffer");
		const auto* tex_params = find_slot(msl, "TextureParametersBuffer");
		const auto* stipple = find_slot(msl, "RasterizerHeap");
		check(context && context->buffer == fp.binding_table.context_buffer_location, std::string(name) + " fragment context slot");
		check(tex_params && tex_params->buffer == fp.binding_table.tex_param_location, std::string(name) + " texture parameter slot");
		check(stipple && stipple->buffer == fp.binding_table.polygon_stipple_params_location, std::string(name) + " stipple slot");

		if (expect_texture)
		{
			const auto* tex0 = find_slot(msl, "tex0");
			check(tex0 && tex0->texture == fp.binding_table.ftex_location[0] && tex0->sampler == 0 && tex0->used, std::string(name) + " tex0 texture and sampler 0");
			check(contains(msl.msl, "texture2d<float>") && contains(msl.msl, "[[sampler(0)]]"), std::string(name) + " MSL samples a 2D texture with sampler 0");
		}

		if (expect_constants)
		{
			const auto* constants = find_slot(msl, "FragmentConstantsBuffer");
			check(!fp.constant_offsets.empty(), std::string(name) + " constant offsets recorded");
			check(constants && constants->buffer == fp.binding_table.cbuf_location && constants->used, std::string(name) + " fragment constants slot");
		}

		write_msl(out_dir, name, msl.msl);
	}

	void test_slot_contract()
	{
		std::string error;

		// Two inputs on one Metal buffer slot are refused.
		std::vector<mtl::glsl::program_input> clash =
		{
			mtl::glsl::program_input::make(::glsl::glsl_vertex_program, "a", mtl::glsl::input_type_uniform_buffer, mtl::glsl::binding_set_index_vertex, 3),
			mtl::glsl::program_input::make(::glsl::glsl_vertex_program, "b", mtl::glsl::input_type_storage_buffer, mtl::glsl::binding_set_index_vertex, 3),
		};
		check(mtl::assign_slots(mtl::shader_stage::vertex, clash, error).empty() && !error.empty(), "clashing buffer slots refused");

		// A fragment input in the vertex set is refused.
		error.clear();
		std::vector<mtl::glsl::program_input> wrong_set =
		{
			mtl::glsl::program_input::make(::glsl::glsl_fragment_program, "c", mtl::glsl::input_type_uniform_buffer, mtl::glsl::binding_set_index_fragment, 0),
		};
		check(mtl::assign_slots(mtl::shader_stage::vertex, wrong_set, error).empty() && !error.empty(), "wrong descriptor set refused");

		// Buffers stop below the push constant slot.
		error.clear();
		std::vector<mtl::glsl::program_input> too_high =
		{
			mtl::glsl::program_input::make(::glsl::glsl_fragment_program, "d", mtl::glsl::input_type_storage_buffer, mtl::glsl::binding_set_index_fragment, mtl::push_constant_buffer_slot),
		};
		check(mtl::assign_slots(mtl::shader_stage::fragment, too_high, error).empty() && !error.empty(), "buffer at the push constant slot refused");

		// Stencil mirrors and the depth-compare input get samplers baked into the shader.
		error.clear();
		std::vector<mtl::glsl::program_input> baked =
		{
			mtl::glsl::program_input::make(::glsl::glsl_fragment_program, "tex3", mtl::glsl::input_type_texture, mtl::glsl::binding_set_index_fragment, 4),
			mtl::glsl::program_input::make(::glsl::glsl_fragment_program, "tex3_stencil", mtl::glsl::input_type_texture, mtl::glsl::binding_set_index_fragment, 5),
			mtl::glsl::program_input::make(::glsl::glsl_fragment_program, "frag_depth", mtl::glsl::input_type_texture, mtl::glsl::binding_set_index_fragment, 6),
		};
		const auto slots = mtl::assign_slots(mtl::shader_stage::fragment, baked, error);
		check(slots.size() == 3 && error.empty(), "baked sampler inputs accepted: " + error);
		if (slots.size() == 3)
		{
			check(slots[0].sampler == 3 && slots[0].texture == 4, "tex3 uses sampler 3, texture 4");
			check(slots[1].sampler == umax && slots[1].texture == 5, "stencil mirror has a baked sampler");
			check(slots[2].sampler == umax && slots[2].texture == 6, "depth input has a baked sampler");
		}

		// An empty SPIR-V module is refused, not translated.
		const auto empty = mtl::translate_spirv_to_msl({}, mtl::shader_stage::vertex, {}, {});
		check(!empty.ok && !empty.error.empty(), "empty SPIR-V refused");
	}
}

int main(int argc, char** argv)
{
	const char* out_dir = argc > 1 ? argv[1] : nullptr;

	spirv::initialize_compiler_context();

	const mtl::shader_device_caps caps{};

	test_slot_contract();
	test_vertex(out_dir, caps);

	// MOV R0, f[COL0]
	test_fragment(out_dir, caps, "fp_color", {
		{ RSX_FP_OPCODE_MOV, 0, fp_src(fp_input), fp_src(fp_temp), fp_src(fp_temp), attr_col0 },
	}, CELL_GCM_SHADER_CONTROL_32_BITS_EXPORTS, 0, false, false);

	// TEX R0, f[TEX0], TEX0; MUL R0, R0, f[COL0]
	test_fragment(out_dir, caps, "fp_texture", {
		{ RSX_FP_OPCODE_TEX, 0, fp_src(fp_input), fp_src(fp_temp), fp_src(fp_temp), attr_tex0, 0 },
		{ RSX_FP_OPCODE_MUL, 0, fp_src(fp_temp), fp_src(fp_input), fp_src(fp_temp), attr_col0 },
	}, CELL_GCM_SHADER_CONTROL_32_BITS_EXPORTS, 1u /* tex0: 2D */, true, false);

	// MUL R0, f[COL0], {0.25, 0.5, 0.75, 1} (literal constant -> FragmentConstantsBuffer)
	test_fragment(out_dir, caps, "fp_constant", {
		{ RSX_FP_OPCODE_MUL, 0, fp_src(fp_input), fp_src(fp_constant), fp_src(fp_temp), attr_col0, 0, true },
	}, CELL_GCM_SHADER_CONTROL_32_BITS_EXPORTS, 0, false, true);

	spirv::finalize_compiler_context();

	if (g_failures)
	{
		std::fprintf(stderr, "%d check(s) failed\n", g_failures);
		return 1;
	}

	std::puts("PASS: Metal shader stack (RSX programs -> GLSL -> SPIR-V -> MSL, slot contract)");
	return 0;
}
