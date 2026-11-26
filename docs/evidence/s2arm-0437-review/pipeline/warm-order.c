#include "rb_warm_order.h"

// Run the engine's existing ordering on a series of recorded render rows.
void observed_order(unsigned n, const uint64_t *frames, unsigned *out,
                    rb_warm_slot *rows, unsigned *scratch) {
    for (unsigned i = 0; i < n; ++i) {
        rows[i] = (rb_warm_slot){.kind = RB_WARM_ROW_RENDER, .recorded = 1,
                                .frame = frames[i], .wait = 0};
    }
    rb_warm_first_use_order(rows, n, out, scratch);
}

size_t warm_row_bytes(void) { return sizeof(rb_warm_slot); }
