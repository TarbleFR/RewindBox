// The complete production getObject body is inserted in Cache by the driver.
// LLVM objects are lightweight adapters; filesystem reads below are real.
struct Buffer { std::string bytes; std::size_t getBufferSize() const { return bytes.size(); } };
namespace llvm {
using MemoryBuffer = Buffer;
struct Module { std::string name; const std::string& getName() const { return name; } };
}
struct Outcome { bool loaded = false; std::size_t object_bytes = 0; };
struct Logger { template<class... T> void notice(T&&...) {} template<class... T> void error(T&&...) {} } jit_log;
namespace fs { void remove_file(const std::string& p) { std::filesystem::remove(p); } }
struct Base { virtual std::unique_ptr<Buffer> getObject(const llvm::Module*) = 0; virtual ~Base() = default; };
struct Cache : Base {
    std::unique_ptr<Buffer> m_preloaded;
    Outcome* m_outcome = nullptr;
    bool m_spu = false;
    std::string m_path;
    unsigned opens = 0, validations = 0;
    std::unique_ptr<Buffer> load(const std::string& path) {
        for (const auto& suffix : {".gz", ""}) {
            ++opens; std::ifstream f(path + suffix, std::ios::binary);
            if (f) return std::make_unique<Buffer>(Buffer{std::string(std::istreambuf_iterator<char>(f), {})});
        }
        return {};
    }
    bool validate(const Buffer& b, const std::string&) { ++validations; return b.bytes == "validated-object"; }
    // PRODUCTION_BODY
};
void test(const std::filesystem::path& directory, bool fixed) {
    std::filesystem::create_directories(directory);
    llvm::Module mod{"module"}; const std::string path = directory.string() + "/";
    Cache cache; cache.m_path = path; cache.m_spu = true;
    assert(!cache.getObject(&mod)); assert(cache.opens == (fixed ? 0u : 2u));
    Outcome outcome; cache.m_outcome = &outcome;
    cache.m_preloaded = std::make_unique<Buffer>(Buffer{"validated-object"});
    auto* exact = cache.m_preloaded.get(); const auto old_opens = cache.opens;
    assert(cache.getObject(&mod).get() == exact);
    assert(outcome.loaded && outcome.object_bytes == 16 && cache.opens == old_opens);
    // A file appearing after the required-symbol probe must not be reconsidered.
    { std::ofstream f(path + "module"); f << "validated-object"; }
    auto late = cache.getObject(&mod); assert(bool(late) == !fixed);
    cache.m_spu = false; cache.opens = cache.validations = 0;
    assert(cache.getObject(&mod)); assert(cache.opens == 2 && cache.validations == 1);
    { std::ofstream f(path + "module", std::ios::trunc); f << "invalid"; }
    assert(!cache.getObject(&mod)); assert(!std::filesystem::exists(path + "module"));
    cache.opens = 0; assert(!cache.getObject(&mod)); assert(cache.opens == 2);
    // A previously validated buffer is returned without disk access in both paths.
    cache.m_preloaded = std::make_unique<Buffer>(Buffer{"validated-object"});
    cache.opens = 0; assert(cache.getObject(&mod)); assert(cache.opens == 0);
}
