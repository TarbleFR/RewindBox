// Emits the real RPCS3 vertex-program prologue (glsl::insert_subheader_block and
// glsl::insert_glsl_legacy_function, compiled from the candidate GLSLCommon.cpp)
// with the properties VKVertexDecompilerThread::insertMainStart sets on an Apple
// GPU (no float64: zclip fallback; not NVIDIA: no low-precision compare).
#include "Emu/RSX/Program/GLSLCommon.h"
#include "Emu/RSX/Program/GLSLTypes.h"
#include <iostream>
#include <sstream>
#include <string_view>
int main(int argc, char** argv) {
  const std::string_view part = argc > 1 ? argv[1] : "";
  std::stringstream os;
  if (part == "subheader") { glsl::insert_subheader_block(os); std::cout << os.str(); return 0; }
  glsl::shader_properties p{};
  p.domain = glsl::glsl_vertex_program;
  p.require_lit_emulation = false;
  p.require_clip_plane_functions = true;
  p.emulate_zclip_transform = true;
  p.emulate_depth_clip_only = false;
  p.low_precision_tests = false;
  p.require_explicit_invariance = part == "invariant";
  p.require_instanced_render = false;
  glsl::insert_glsl_legacy_function(os, p);
  std::cout << os.str();
}
