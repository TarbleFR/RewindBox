// Runs MoltenVK 1.4.2's own SPIRVToMSLConverter (pinned db66022) on a SPIR-V file
// with the iOS options MoltenVK uses for a vertex stage, and reports what decides
// MTLCompileOptions.preserveInvariance (MVKShaderModule.mm:685-686).
#include "SPIRVToMSLConverter.h"
#include <cstdio>
#include <cstring>
#include <fstream>
#include <iterator>
#include <vector>
using namespace mvk;
int main(int argc, char** argv) {
  if (argc < 3) { std::fprintf(stderr, "usage: mvk_probe in.spv out.msl\n"); return 2; }
  std::ifstream in(argv[1], std::ios::binary);
  std::vector<char> bytes((std::istreambuf_iterator<char>(in)), {});
  std::vector<uint32_t> words(bytes.size() / 4);
  std::memcpy(words.data(), bytes.data(), words.size() * 4);
  SPIRVToMSLConverter converter;
  converter.setSPIRV(words);
  SPIRVToMSLConversionConfiguration config;
  config.options.entryPointStage = spv::ExecutionModelVertex;
  config.options.entryPointName = "main";
  config.options.mslOptions.platform = SPIRV_CROSS_NAMESPACE::CompilerMSL::Options::iOS;
  config.options.mslOptions.set_msl_version(3, 1, 0);
  config.options.mslOptions.enable_decoration_binding = true;
  SPIRVToMSLConversionResult result;
  const bool ok = converter.convert(config, result, false, false, false);
  std::ofstream(argv[2]) << result.msl;
  std::printf("converted=%d isPositionInvariant=%d fpFastMathFlags=0x%x log=%s\n", ok,
      int(result.resultInfo.isPositionInvariant), result.resultInfo.entryPoint.fpFastMathFlags,
      result.resultLog.c_str());
  return ok ? 0 : 1;
}
