// Explicit adapters: logging, termination and main-thread id are not exercised by
// GLSL generation; they abort if a production error path is reached.
#include "Utilities/StrFmt.h"
#include "Utilities/Thread.h"
#include "util/logs.hpp"
#include <cstdlib>
#include <cstdio>
namespace logs {
void message::broadcast(const char*, const fmt_type_info*, ...) const { std::fputs("adapter: log broadcast reached\n", stderr); }
registerer::registerer(channel&) {}
}
void thread_ctrl::emergency_exit(std::string_view reason) { std::fprintf(stderr, "adapter: emergency_exit %.*s\n", int(reason.size()), reason.data()); std::abort(); }
namespace utils { u64 _get_main_tid() { return 0; } }
