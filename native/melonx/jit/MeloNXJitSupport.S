// Copyright (c) 2026 RewindBox contributors. SPDX-License-Identifier: MIT
// RewindBox's existing authenticated universal JIT helper implements this
// register/trap protocol. These are independent protocol trampolines, not the
// unlicensed upstream BreakpointJIT binary. Never install a SIGTRAP skipper.
// x0 = requested address (zero permits allocation); x1 = byte count.
.text
.p2align 2
.globl _rewindbox_melonx_jit_map
_rewindbox_melonx_jit_map:
    mov x16, #1
    brk #0xf00d
    ret

.p2align 2
.globl _rewindbox_melonx_jit_mark
_rewindbox_melonx_jit_mark:
    brk #0x69
    ret

.p2align 2
.globl _rewindbox_melonx_jit_detach
_rewindbox_melonx_jit_detach:
    mov x16, #0
    brk #0xf00d
    ret
