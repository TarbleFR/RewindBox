#import <stdint.h>

// Lot 13, RAM: who allocated the native heap. IPA 725 (Hogwarts Legacy, t=150 s): the default malloc zone holds
// 907 MiB of a 4 640 MiB footprint, 80 % of it compressed, and nothing in the journals says whose it is.
//
// Between Start and Stop, libmalloc's logging hook (malloc_logger) is set to a function that samples allocations by
// size (one in every MeloNXHeapSamplerInterval bytes on average; a block of that size or more always) and remembers,
// for each sampled block still allocated, its weight and the return addresses of the call (frame pointers, within the
// thread's own stack). A free looks its pointer up in that table (one probe sequence, no lock when absent). The hook
// allocates nothing, uses no thread-local storage and takes its one lock only for a sampled block. Stop removes the
// hook; Report then lists the call stacks by the bytes still allocated.
//
// Measurement only, for a bounded window at the start of a session (the hook costs a few tens of nanoseconds on every
// malloc and free while it is set). Swift resolves these functions with dlsym (MeloNXHeapSamplerLink).

#define MeloNXHeapSamplerFrames 14

typedef struct {
    uint64_t liveBytes;      // estimated bytes still allocated (sum of the weights of the live samples)
    uint64_t liveSamples;
    uint64_t totalBytes;     // estimated bytes allocated in the window
    uint64_t totalSamples;
    uint32_t frameCount;
    uint32_t reserved;
    uint64_t frames[MeloNXHeapSamplerFrames];   // return addresses, innermost first
} MeloNXHeapSamplerStack;

typedef struct {
    uint64_t liveBytes, liveSamples, totalBytes, totalSamples;
    uint64_t droppedSamples;     // sampled blocks not recorded: the live table or the stack table was full
    uint64_t unwalkedSamples;    // sampled blocks whose call could not be walked (a thread on a stack that is not its own)
    uint64_t stacks;             // distinct call stacks recorded
    uint64_t intervalBytes;
} MeloNXHeapSamplerTotals;

/// Empties the tables and sets the hook. Returns 1 when it was set, 0 when it already is, -1 when another logger
/// owns malloc_logger, -3 when the system exports no malloc_logger.
int MeloNXHeapSamplerStart(void);
/// Removes the hook (the tables keep what they hold until the next Start). Returns 1 when it was set.
int MeloNXHeapSamplerStop(void);
/// The totals and up to `capacity` stacks, most live bytes first. Returns the number of stacks written.
int MeloNXHeapSamplerReport(MeloNXHeapSamplerTotals *totals, MeloNXHeapSamplerStack *stacks, int capacity);
