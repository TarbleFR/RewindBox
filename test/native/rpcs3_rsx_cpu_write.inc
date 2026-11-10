
// Command/renderer boundary adapter. The complete inline/DMA transfer bodies
// are inserted below. The scaled-blit conversion/GPU helpers are controlled
// here to exercise every completion/early-return path without a GPU/FFmpeg.
#include <cmath>
#include <functional>
#include <span>
#include <tuple>

using f32 = float;
constexpr u32 CELL_GCM_LOCATION_MAIN = 1;
constexpr u32 CELL_GCM_CONTEXT_DMA_MEMORY_FRAME_BUFFER = 0xfeed0000;
constexpr u32 NV308A_COLOR = 0x400;
constexpr u32 RSX_METHOD_NON_INCREMENT_CMD_MASK = 0x40000000;
template <typename T> u32 size32(const T& x) { return static_cast<u32>(x.size()); }
template <typename T> struct be_t
{
    T raw;
    operator T() const { if constexpr (std::endian::native == std::endian::little) return __builtin_bswap32(raw); else return raw; }
};
namespace fmt { [[noreturn]] inline void throw_exception(const char*) { std::abort(); } }
struct logger
{
    template <typename... T> void error(const char*, T...) {}
    template <typename... T> void warning(const char*, T...) {}
    template <typename... T> void trace(const char*, T...) {}
} rsx_log;
struct configuration { struct { bool strict_rendering_mode = false, relaxed_zcull_sync = false, force_cpu_blit_processing = false; } video; } g_cfg;
namespace vm { template <typename T> T* _ptr(u32 addr) { return reinterpret_cast<T*>(g_sudo_addr + addr); } }
namespace utils
{
    template <typename T, typename U> T* bless(U* x) { return reinterpret_cast<T*>(x); }
    struct address_range64 { u64 start, size; static address_range64 start_length(u64 a, u64 n) { return {a,n}; } };
    using address_range32 = rsx::address_range32;
    template <typename F> struct deferred_op { F f; explicit deferred_op(F value) : f(value) {} ~deferred_op() { f(); } };
}

namespace rsx
{
    template <typename T> using simple_array = std::vector<T>;
    template <bool> struct reservation_lock
    {
        // The device title profiles have Accurate RSX reservation access off;
        // local memory also takes the no-op branch of the production lock.
        reservation_lock(u32, u32) {}
        reservation_lock(u32, u32, u32, u32) {}
        ~reservation_lock() {}
    };
    inline void mm_flush(const simple_array<utils::address_range64>&) {}
    inline u32 get_address(u32 addr, u32, u32 = 1)
    {
        return (addr >= constants::local_mem_base || (addr >= vm::main_base && addr < vm::main_base + vm::main_size)) ? addr : 0;
    }
    enum { result_zcull_intr = 1 };
    namespace blit_engine
    {
        enum class transfer_destination_format { a8r8g8b8, y32, r5g6b5 };
        enum class transfer_source_format { a8r8g8b8, r5g6b5 };
        enum class transfer_interpolator { zoh, foh };
        enum class context_surface { surface2d, swizzle2d };
    }
    struct regs
    {
        u32 dst = 0, dma = 0, pitch = 64, x = 3, y = 2, out_x = 64;
        blit_engine::transfer_destination_format format = blit_engine::transfer_destination_format::a8r8g8b8;
        u32 src = 0, src_dma = 0, columns = 64, rows = 1;
        s32 in_pitch = 64, out_pitch = 64;
        u8 in_stride = 1, out_stride = 1;
        u16 width = 8, height = 4;
        blit_engine::context_surface surface = blit_engine::context_surface::surface2d;
        u32 nv308a_size_out_x() const { return out_x; }
        u32 nv308a_x() const { return x; }
        u32 nv308a_y() const { return y; }
        u32 blit_engine_output_location_nv3062() const { return dma; }
        u32 blit_engine_output_offset_nv3062() const { return dst; }
        u32 blit_engine_output_pitch_nv3062() const { return pitch; }
        const auto* blit_engine_nv3062_color_format() const { return &format; }
        s32 nv0039_input_pitch() const { return in_pitch; }
        s32 nv0039_output_pitch() const { return out_pitch; }
        u32 nv0039_line_length() const { return columns; }
        u32 nv0039_line_count() const { return rows; }
        u8 nv0039_input_format() const { return in_stride; }
        u8 nv0039_output_format() const { return out_stride; }
        u32 nv0039_input_offset() const { return src; }
        u32 nv0039_output_offset() const { return dst; }
        u32 nv0039_input_location() const { return src_dma; }
        u32 nv0039_output_location() const { return dma; }
        auto blit_engine_input_inter() const { return blit_engine::transfer_interpolator::foh; }
        u16 blit_engine_output_width() const { return width; }
        u16 blit_engine_output_height() const { return height; }
        auto blit_engine_context_surface() const { return surface; }
    };
    struct fifo
    {
        u32 address = vm::main_base + (2u << 20), count = 4, span_count = 4, command = 0, skipped = 0;
        u32 get_pos() const { return address; }
        u32 get_remaining_args_count() const { return count - 1; }
        auto get_current_arg_ptr(u32 n) const { return std::span<const u32>(vm::_ptr<u32>(address), std::min(n,span_count)); }
        void skip_methods(u32 n) { skipped += n; }
        u32 last_cmd() const { return command; }
    };
    struct control { u64 put = 0; };
    struct blit_src_info
    {
        u8* pixels = nullptr;
        u32 rsx_address = 0, dma = 0, pitch = 32, width = 8, height = 4, bpp = 4;
        blit_engine::transfer_source_format format = blit_engine::transfer_source_format::a8r8g8b8;
    };
    struct blit_dst_info
    {
        u8* pixels = nullptr;
        u32 rsx_address = 0, dma = 0, pitch = 32, width = 8, height = 4, bpp = 4;
        u32 clip_x = 0, clip_y = 0, clip_width = 8, clip_height = 4;
        f32 scale_x = 1, scale_y = 1;
        blit_engine::transfer_destination_format format = blit_engine::transfer_destination_format::a8r8g8b8;
    };
    struct tile { u32 size = 512, bank = 0, pitch = 32; };
    struct tiled_region
    {
        rsx::tile* tile = nullptr;
        u32 base_address = 0;
        explicit operator bool() const { return tile != nullptr; }
    };
    struct renderer
    {
        fifo* fifo_ctrl;
        control* ctrl;
        u32 recovered = 0, fragment_invalidations = 0, rtt_barriers = 0, sync_calls = 0, gpu_calls = 0;
        bool zcull_deferred = false, gpu_success = false, tiled = false;
        rsx::tile storage;
        explicit renderer(fifo* f, control* c) : fifo_ctrl(f), ctrl(c) {}
        void recover_fifo() { recovered++; }
        void invalidate_fragment_program(u32, u32, u32) { fragment_invalidations++; }
        void sync() { sync_calls++; }
        u32 read_barrier(u32, u32, bool) const { return zcull_deferred ? result_zcull_intr : 0; }
        u32 copy_zcull_stats(u32, u32, u32) const { return zcull_deferred ? 0xffffffffu : 0; }
        void write_barrier(u32, u32) { rtt_barriers++; }
        bool scaled_image_from_memory(const blit_src_info&, const blit_dst_info&, bool) { gpu_calls++; return gpu_success; }
        tiled_region get_tiled_memory_region(const utils::address_range32& range) { return {tiled ? &storage : nullptr, range.start}; }
    };
    struct context
    {
        rsx::regs registers;
        rsx::fifo fifo;
        rsx::control ctrl;
        renderer engine{&fifo,&ctrl};
        bool decoded = true;
        blit_src_info src;
        blit_dst_info dst;
    };
    inline bool fcmp(float a, float b) { return a == b; }
    inline auto decode_transfer_registers(context* c) { return std::tuple{c->decoded,c->src,c->dst}; }
    inline std::vector<u8> _mirror_transform(const blit_src_info& src, bool, bool)
    {
        return {src.pixels,src.pixels + src.pitch * src.height};
    }
}
enum AVPixelFormat { AV_PIX_FMT_RGB565BE, AV_PIX_FMT_ARGB };
namespace rsx
{
    inline void linear_copy(blit_dst_info& dst, const blit_src_info& src, u16, u16, u32, AVPixelFormat, AVPixelFormat, bool, bool, bool, bool)
    {
        std::memcpy(dst.pixels,src.pixels,dst.pitch * dst.clip_height);
    }
    inline std::vector<u8> swizzled_copy_1(const blit_dst_info&, const blit_src_info&, u16, u16, u32, AVPixelFormat, AVPixelFormat, bool, bool, bool) { return {}; }
    inline void swizzled_copy_2(const u8* src, u8* dst, u32 pitch, u16, u16 height, u32) { std::memcpy(dst,src,pitch * height); }
    inline void tile_texel_data32(u8* dst, const u8* src, u32, u32, u32, u32, u32 pitch, u32, u32 height) { std::memcpy(dst,src,pitch * height); }
    inline void tile_texel_data16(u8* dst, const u8* src, u32 a, u32 b, u32 c, u32 d, u32 pitch, u32 width, u32 height) { tile_texel_data32(dst,src,a,b,c,d,pitch,width,height); }
    namespace nv308a_before { struct color { static void impl(context*,u32,u32); }; }
    namespace nv308a_after { struct color { static void impl(context*,u32,u32); }; }
    namespace nv308a_desktop { struct color { static void impl(context*,u32,u32); }; }
}
#define REGS(c) (&(c)->registers)
#define RSX(c) (&(c)->engine)
@PRODUCTION_HANDLERS@
#undef REGS
#undef RSX

namespace
{
    using handler_t = void (*)(rsx::context*,u32,u32);
    constexpr u32 texture_size = 64u << 10;
    u64 baseline_stale = 0, candidate_stale = 0, calls = 0, noops = 0;
    u64 baseline_hashes = 0, candidate_hashes = 0, retained_skips = 0, old_prehash_rejected = 0;
    u32 watched_address = 0;
    u64 watched_hash = 0, notifications = 0;
    void write_completed() noexcept
    {
        // This listener executes synchronously inside advance_epoch(). It must
        // observe the final guest bytes, including the tiled-copy finalization.
        ensure(tp::range_hash(vm::_ptr<u8>(watched_address),texture_size) != watched_hash);
        notifications++;
    }
    void fill(u32 address, u32 length, u32 seed)
    {
        for (u32 i = 0; i < length; i++) vm::_ptr<u8>(address)[i] = static_cast<u8>((i * 73u + i / 31u) ^ seed);
    }
    void check_write(int version, bool enabled, bool prehashed, int validation, u32 address, const std::function<void()>& transfer)
    {
        tv::epoch_enabled = enabled;
        tp::enabled = prehashed;
        rsx::after::buffered_section section(address,texture_size);
        section.protect(utils::protection::ro);
        watched_address = address;
        watched_hash = section.mem_hash;
        const u64 before_epoch = tv::current_epoch();
        tp::publish(address,texture_size,before_epoch,section.mem_hash);
        if (validation == 1) section.validated_epoch = 0;
        if (validation == 2) section.reset_validation();
        const u64 notify0 = notifications;
        tv::epoch_listener = write_completed;
        transfer();
        ensure(tp::range_hash(vm::_ptr<u8>(address),texture_size) != watched_hash);
        ensure(tv::current_epoch() == before_epoch + static_cast<u64>(version == 1 && enabled));
        ensure(notifications - notify0 == static_cast<u64>(version == 1 && enabled));
        if (enabled && version == 1)
        {
            u64 result = 0;
            ensure(!tp::lookup(address,texture_size,tv::current_epoch(),result));
            old_prehash_rejected++;
        }
        const u64 skip0 = tv::epoch_skips, hit0 = tp::hits;
        const bool accepted = section.sync();
        const bool expected_stale = version != 1 && enabled && validation != 2 && (validation == 0 || prehashed);
        ensure(accepted == expected_stale);
        const u64 hashes = 1 - (tv::epoch_skips - skip0) - (tp::hits - hit0);
        if (version == 0) { baseline_stale += accepted; baseline_hashes += hashes; }
        if (version == 1) { candidate_stale += accepted; candidate_hashes += hashes; }
        // A reuploaded, unchanged section still uses exactly the existing fast
        // epoch hit. The fix does not disable epochs or scoped revalidation.
        section.discard();
        section.protect(utils::protection::ro);
        const u64 unchanged0 = tv::epoch_skips;
        ensure(section.sync());
        if (enabled) { ensure(tv::epoch_skips == unchanged0 + 1); retained_skips++; }
        calls++;
    }
    void check_noop(handler_t handler, rsx::context& c, u32 reg)
    {
        tv::epoch_enabled = true;
        tp::enabled = false;
        tv::epoch_listener = nullptr;
        const u64 epoch = tv::current_epoch();
        handler(&c,reg,0);
        ensure(tv::current_epoch() == epoch);
        noops++;
    }
}

int main()
{
    constexpr u64 reservation = u64{rsx::constants::local_mem_base} + (2u << 20);
    void* base = mmap(nullptr,reservation,PROT_NONE,MAP_PRIVATE | MAP_ANONYMOUS | MAP_NORESERVE,-1,0);
    ensure(base != MAP_FAILED);
    vm::g_sudo_addr = static_cast<u8*>(base);
    ensure(mprotect(vm::g_sudo_addr + rsx::constants::local_mem_base,2u << 20,PROT_READ | PROT_WRITE) == 0);
    ensure(mprotect(vm::g_sudo_addr + vm::main_base,vm::main_size,PROT_READ | PROT_WRITE) == 0);
    for (auto& page : vm::g_main_pages) page.store(vm::page_readable | vm::page_writable);
    const handler_t inline_handlers[] = {rsx::nv308a_before::color::impl,rsx::nv308a_after::color::impl,rsx::nv308a_desktop::color::impl};
    const handler_t dma_handlers[] = {rsx::nv0039_before::buffer_notify,rsx::nv0039_after::buffer_notify,rsx::nv0039_desktop::buffer_notify};
    const handler_t blit_handlers[] = {rsx::nv3089_before::image_in,rsx::nv3089_after::image_in,rsx::nv3089_desktop::image_in};
    u64 inline_writes = 0, dma_writes = 0, blit_writes = 0;
    for (int version = 0; version < 3; version++)
    for (bool enabled : {false,true})
    for (bool prehashed : {false,true})
    for (int validation = 0; validation < 3; validation++)
    for (bool main_memory : {false,true})
    {
        const u32 address = main_memory ? vm::main_base : rsx::constants::local_mem_base;
        const u32 dma = main_memory ? CELL_GCM_LOCATION_MAIN : CELL_GCM_CONTEXT_DMA_MEMORY_FRAME_BUFFER;
        for (auto format : {rsx::blit_engine::transfer_destination_format::a8r8g8b8,rsx::blit_engine::transfer_destination_format::y32,rsx::blit_engine::transfer_destination_format::r5g6b5})
        for (bool non_incremental : {false,true})
        for (u32 count : {1u,4u,16u})
        {
            rsx::context c;
            c.registers.dst = address;
            c.registers.dma = dma;
            c.registers.format = format;
            c.fifo.count = c.fifo.span_count = count;
            c.fifo.command = non_incremental ? RSX_METHOD_NON_INCREMENT_CMD_MASK : 0;
            c.ctrl.put = c.fifo.address + count * 4;
            fill(address,texture_size,37);
            fill(c.fifo.address,count * 4,193);
            check_write(version,enabled,prehashed,validation,address,[&] { inline_handlers[version](&c,NV308A_COLOR + 2,0); });
            ensure(c.engine.fragment_invalidations == 1 && c.fifo.skipped == count - 1);
            inline_writes++;
        }
        for (int mode = 0; mode < 5; mode++)
        {
            rsx::context c;
            c.registers.dst = address;
            c.registers.dma = c.registers.src_dma = dma;
            c.registers.src = address + (128u << 10);
            if (mode == 1) { c.registers.columns = 16; c.registers.rows = 3; c.registers.in_pitch = 32; c.registers.out_pitch = 48; }
            if (mode == 2) { c.registers.columns = 10; c.registers.rows = 2; c.registers.in_stride = 2; c.registers.out_stride = 3; c.registers.in_pitch = 32; c.registers.out_pitch = 40; }
            if (mode == 3) { c.registers.src = address + 8; }
            if (mode == 4) { c.registers.src = address + 16; c.registers.columns = 16; c.registers.rows = 3; c.registers.in_pitch = c.registers.out_pitch = 32; }
            fill(address,texture_size,37);
            if (c.registers.src >= address + texture_size) fill(c.registers.src,512,193);
            check_write(version,enabled,prehashed,validation,address,[&] { dma_handlers[version](&c,0,0); });
            ensure(c.engine.fragment_invalidations == 1 && c.engine.rtt_barriers == 1);
            dma_writes++;
        }
        for (bool swizzled : {false,true})
        for (bool tiled : {false,true})
        for (bool mirrored : {false,true})
        for (u32 bpp : {2u,4u})
        {
            rsx::context c;
            c.registers.surface = swizzled ? rsx::blit_engine::context_surface::swizzle2d : rsx::blit_engine::context_surface::surface2d;
            c.src.rsx_address = address + (128u << 10);
            c.dst.rsx_address = address + 128;
            c.src.pixels = vm::_ptr<u8>(c.src.rsx_address);
            c.dst.pixels = vm::_ptr<u8>(c.dst.rsx_address);
            c.src.dma = c.dst.dma = dma;
            c.src.bpp = c.dst.bpp = bpp;
            c.src.pitch = c.dst.pitch = c.engine.storage.pitch = 8 * bpp;
            c.src.format = bpp == 2 ? rsx::blit_engine::transfer_source_format::r5g6b5 : rsx::blit_engine::transfer_source_format::a8r8g8b8;
            c.dst.format = bpp == 2 ? rsx::blit_engine::transfer_destination_format::r5g6b5 : rsx::blit_engine::transfer_destination_format::a8r8g8b8;
            c.dst.scale_x = mirrored ? -1.f : 1.f;
            c.engine.tiled = tiled;
            fill(address,texture_size,37);
            fill(c.src.rsx_address,512,193);
            check_write(version,enabled,prehashed,validation,address,[&] { blit_handlers[version](&c,0,0); });
            blit_writes++;
        }
    }
    for (int version = 0; version < 3; version++)
    {
        for (int mode = 0; mode < 3; mode++)
        {
            rsx::context c;
            c.ctrl.put = c.fifo.address + 16;
            c.registers.dst = rsx::constants::local_mem_base;
            if (mode == 0) c.registers.out_x = 0;
            if (mode == 1) c.ctrl.put = c.fifo.address;
            if (mode == 2) c.registers.dst = 0;
            check_noop(inline_handlers[version],c,NV308A_COLOR);
        }
        for (int mode = 0; mode < 5; mode++)
        {
            rsx::context c;
            c.registers.dst = rsx::constants::local_mem_base;
            c.registers.src = c.registers.dst + (128u << 10);
            if (mode == 0) c.registers.columns = 0;
            if (mode == 1) c.registers.rows = 0;
            if (mode == 2) c.registers.in_stride = 0;
            if (mode == 3) c.registers.out_stride = 5;
            if (mode == 4) c.engine.zcull_deferred = true;
            check_noop(dma_handlers[version],c,0);
        }
        for (bool gpu : {false,true})
        {
            rsx::context c;
            c.decoded = gpu;
            c.src.dma = CELL_GCM_CONTEXT_DMA_MEMORY_FRAME_BUFFER;
            c.engine.gpu_success = true;
            check_noop(blit_handlers[version],c,0);
            ensure(c.engine.gpu_calls == static_cast<u32>(gpu));
        }
    }
    tv::epoch_listener = nullptr;
    tp::stop();
    ensure(candidate_stale == 0 && baseline_stale > 0 && candidate_hashes > baseline_hashes);
    std::printf("{\"passed\":true,\"cpuWrites\":%llu,\"inlineWrites\":%llu,\"dmaWrites\":%llu,\"blitDispatchWrites\":%llu,"
                "\"noopsAndGpuReturns\":%llu,\"baselineStaleAccepted\":%llu,\"candidateStaleAccepted\":%llu,"
                "\"baselineValidationHashes\":%llu,\"candidateValidationHashes\":%llu,\"unchangedEpochSkipsPreserved\":%llu,"
                "\"oldPrehashResultsRejected\":%llu,\"notificationsAfterFinalBytes\":%llu,\"desktopPathIdentical\":true,\"epochDisabledIdentical\":true}\n",
                static_cast<unsigned long long>(calls),static_cast<unsigned long long>(inline_writes),static_cast<unsigned long long>(dma_writes),
                static_cast<unsigned long long>(blit_writes),static_cast<unsigned long long>(noops),static_cast<unsigned long long>(baseline_stale),
                static_cast<unsigned long long>(candidate_stale),static_cast<unsigned long long>(baseline_hashes),static_cast<unsigned long long>(candidate_hashes),
                static_cast<unsigned long long>(retained_skips),static_cast<unsigned long long>(old_prehash_rejected),static_cast<unsigned long long>(notifications));
    munmap(base,reservation);
    return 0;
}
