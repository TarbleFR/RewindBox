// The four helpers SPIRVToMSLConverter.cpp's debugging paths call (SPIR-V disassembly and file output, in
// SPIRVSupport.cpp and FileSupport.mm, which need SPIRV-Tools and Foundation). The cache key property test never
// reaches them: each stops the program if it is called.
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <string>
#include <vector>

namespace mvk {
    [[noreturn]] static void notReached(const char* name) {
        fprintf(stderr, "%s is not part of the cache key property test\n", name);
        abort();
    }
    std::string absolutePath(const std::string&) { notReached("absolutePath"); }
    bool writeFile(const std::string&, const std::vector<char>&, std::string&) { notReached("writeFile"); }
    void logSPIRV(std::vector<uint32_t>&, std::string&) { notReached("logSPIRV"); }
    void spirvToBytes(const std::vector<uint32_t>&, std::vector<char>&) { notReached("spirvToBytes"); }
}
