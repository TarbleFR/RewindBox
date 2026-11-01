// Explicit adapters for MoltenVK debug-only helpers (SPIR-V logging and shader
// dumping). The probe disables both; reaching one aborts the run.
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <string>
#include <vector>
namespace mvk {
void logSPIRV(std::vector<uint32_t>&, std::string&) { std::fputs("adapter reached: logSPIRV\n", stderr); std::abort(); }
void spirvToBytes(const std::vector<uint32_t>&, std::vector<char>&) { std::fputs("adapter reached: spirvToBytes\n", stderr); std::abort(); }
bool writeFile(const std::string&, const std::vector<char>&, std::string&) { std::fputs("adapter reached: writeFile\n", stderr); std::abort(); }
std::string absolutePath(const std::string&) { std::fputs("adapter reached: absolutePath\n", stderr); std::abort(); }
}
