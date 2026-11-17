# MeloNX memory, RAM donor and shader system: audit and lot — 17 November 2026

Maintainer's request after IPA 771: make MeloNX use less RAM, optimise the RAM donor, improve the shader system. Read
from the code (prepared Core 1df78c52, MoltenVK v1.4.2 with the eight-part patch, XNU kernel sources for the
footprint rules) and the IPA 767/771 journals. Nothing below is measured on an iPhone.

## 1. RAM donor: what it does and what it does not

- The host reserves one 4 GiB range and fills it with 256 MiB chunks from up to 4 donor app-extension processes
  (MLXRamDonor, MeloNXMemoryLease.swift); each chunk is a purgeable memory object the donor creates and never touches,
  remapped into the host (xpc_shmem, mach_vm_remap). The guest heap's 1 MiB blocks come from that lease
  (DonatedMemory.TryAllocate); a full lease falls back to the host's own memory ("Donated memory is full").
- Mappings of a purgeable object are charged to its owner (XNU vm_map.c / vm_fault.c alternate accounting): the guest
  heap's pages, resident or compressed, are on the donors' footprint, not the host's. So the donor lifts the host's
  per-process limit; it does not reduce the device's physical memory use. Hogwarts' kills are device-wide (4 %
  available with 2 GiB still inside the host's limit): the donor cannot prevent them.
- Freed guest memory is not given back: madvise(MADV_FREE_REUSABLE) on these mappings is a no-op in XNU, and
  DonatedMemory.Free only marks the range, whose reuse then writes every page again (NativeMemory.Clear), pulling
  compressed pages back in. Candidate fix (not in this lot: native Mach calls that can only be checked on the device):
  VM_BEHAVIOR_ZERO on freed donor ranges instead of the clear, and purgeable EMPTY for a wholly free chunk.
- A file-backed guest heap (unlinked sparse file) is the only change that would relieve the device itself (pages
  written to flash instead of compressed); high risk (flash I/O stalls), an experiment for later.
- Measurement needed first: the donors' own footprint and the lease's used bytes in the per-second line, and the iOS
  JetsamEvent report of the kill (Settings, Privacy, Analytics), which names the reason and every process's pages.

## 2. Before the game: the JIT arena

- The 1 GiB JIT code arena is prepared before the session and the helper writes one byte to each of its 16 KiB pages,
  so all of it is dirty from the start (adapt_jit_arena). It counts in the host's footprint whether resident or
  compressed; its physical cost is small if the pages compress, up to 1 GiB if not. It is most of the 1.47 GiB before
  the game. Kept at 1 GiB for every title (maintainer's choice); the breakdown at the journal's start (f365bf01, now
  deliverable) will say what the arena really costs.

## 3. Shader system

| Finding | Change | Status |
| --- | --- | --- |
| The shader cache load keeps every cached program's host code (the whole cache's SPIR-V, uncompressed) in managed memory until the load ends, for a rebuild that is rare: SSBU about 695 MiB, Hogwarts about 205 MiB; arrays of 85 000 bytes or more go to the large object heap, which matches SSBU's 735 MiB LOH with 490 MiB free after the first minute | adapt_shader_load_binary_release: a program created from the host cache keeps no host code in the loader; a rebuild reads it back from the host cache files before clearing them | Implemented; gate shader-load-binary-release (24 checks: 120 MiB still reachable at the end of a 120-program load in the control, 1 MiB in the candidate; rebuild writes the same code per program, read back before the clear); Core contract de62252f (115 gates) |
| MoltenVK compiles every Metal library of a pipeline cache file as soon as the file loads and keeps every one (35-50 % never used in Hogwarts' statistics; SSBU's 201 MiB of Metal libraries) | MoltenVK ninth part: compile a cached library at its first use | Next lot (measured on macOS by melonx-cache-keys); not in this one |
| A new program's vertex and fragment libraries are compiled one after the other (SSBU: 24-34 ms of about 98 ms per new program) | MoltenVK: start both compilations together | Later; needs the cold-cache measurement |
| Idle Metal libraries kept under memory pressure | Release them at a memory pressure event once lazy compilation exists | After the ninth part |

## 4. Other managed and Vulkan memory (recorded, not changed here)

- Every Vulkan allocation is dedicated (upstream EnableSuballocationPooling = false; MoltenVK makes one MTLHeap per
  allocation, 15 330 in Hogwarts): page rounding is not in the journal's sum; a waste counter comes first.
- Mirror copies of whole Vulkan buffers (48 MiB in Hogwarts, BufferHolder _pendingData) kept until the buffer is
  disposed; mid-size managed arrays from texture readbacks and large bindless arrays churn the large object heap.
