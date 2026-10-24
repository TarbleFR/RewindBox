// SPDX-License-Identifier: MIT
// Real extracted production file constructors, serial/endian, layouts/enums.
// Host mounts, file opening, FXO, logs and trace capture are explicit adapters.
#include <algorithm>
#include <cstdlib>
#include <iostream>
#include <span>
#include <string_view>
#include <vector>
#include "util/types.hpp"
namespace utils { struct serial; }
template<class T> bool serialize(utils::serial&, T&) { std::fputs("Unsupported host serialization adapter\n",stderr); std::abort(); }
#include "util/serialization.hpp"
#include "util/endian.hpp"
using namespace std::literals;

struct Event { std::string_view stage; u32 id, type; u64 value, position; };
static std::vector<Event> events;
static utils::serial* observed_archive = nullptr;
static std::vector<u8> saved_archive;
static std::string_view failure_mode;
static unsigned lookups = 0, opens = 0, errors = 0, successes = 0;
[[noreturn]] static void failure_adapter(std::source_location loc);
[[noreturn]] static void throw_adapter();
namespace fmt {
[[noreturn]] void raw_verify_error(std::source_location loc, const char8_t*, usz) { failure_adapter(loc); }
[[noreturn]] void raw_verify_error(std::source_location loc, std::source_location, const char8_t*, usz) { failure_adapter(loc); }
template<class... Args> [[noreturn]] void throw_exception(const char*, Args&&...) { throw_adapter(); }
}
namespace stx {
void serial_restore_fs_trace(utils::serial& ar, std::string_view stage, u32 id, u32 type, u64 value) noexcept
{
    events.push_back({stage,id,type,value,static_cast<u64>(ar.pos)});
}
}
namespace fs {
#include "layout.inc"
struct file
{
    bool valid = false;
    s64 seek_pos = -1;
    std::vector<u8> bytes;
    stat_t stat{};
    explicit operator bool() const { return valid; }
    void seek(s64 value) { seek_pos = value; }
};
template<class T> file make_stream(T&& data, stat_t stat) { return {true,-1,std::move(data),stat}; }
}
#include "enum.inc"
struct lv2_fs_mount_info { bool read_only = false; };
struct lv2_fs_mount_info_map
{
    lv2_fs_mount_info mount;
    const lv2_fs_mount_info& lookup(std::string_view name)
    {
        ensure(!name.empty()); ++lookups; return mount;
    }
};
struct loaded_npdrm_keys
{
    std::array<u8,16> one_time_key{};
    struct { u32 count=0; u32& raw() { return count; } } npdrm_fds;
};
struct FXO
{
    lv2_fs_mount_info_map mounts;
    loaded_npdrm_keys keys;
    template<class T> T& get()
    {
        if constexpr (std::is_same_v<T,loaded_npdrm_keys>) return keys;
        else return mounts;
    }
} fixed_objects;
static auto* g_fxo = &fixed_objects;
namespace idm { static u32 last_id() { return 3; } }
struct lv2_fs_object
{
    const std::array<char,0x420> name;
    const lv2_fs_mount_info& mp;
    lv2_fs_object(utils::serial& ar,bool);
};
static constexpr s32 CELL_FS_O_ACCMODE=3;
#undef GET_SERIALIZATION_VERSION
#define GET_SERIALIZATION_VERSION(name) 2
struct lv2_file : lv2_fs_object
{
    fs::file file;
    const s32 mode,flags;
    std::string real_path;
    const lv2_file_type type;
    u32 lock=0;
    lv2_file(utils::serial& ar);
#include "open-result.inc"
    static open_result_t open(std::string_view,s32,s32,const void*,u64);
};
struct Open { std::string path; s32 flags,mode; u64 argument,size; std::array<u8,16> key; } last_open{};
static bool host_open_valid=true;
static CellError host_error=static_cast<CellError>(0);
lv2_file::open_result_t lv2_file::open(std::string_view path,s32 flags,s32 mode,const void* argument,u64 size)
{
    ++opens;
    last_open={std::string(path),flags,mode,argument?static_cast<u64>(*static_cast<const be_t<u64>*>(argument)):0,size,g_fxo->keys.one_time_key};
    return {host_error,"/host-adapter/ppath","/host-adapter/file",{host_open_valid,-1,{},{}},lv2_file_type::regular};
}
struct Log {
    template<class... Args> void error(const char*,Args&&...) { ++errors; }
    template<class... Args> void success(const char*,Args&&...) { ++successes; }
} sys_fs;
static struct { struct { bool state_inspection_mode=false; } savestate; } g_cfg;
#ifdef FS_BASELINE
#include "before.inc"
#else
#include "after.inc"
#endif

static std::array<char,0x420> saved_name(std::string_view value)
{
    std::array<char,0x420> name; name.fill('p');
    ensure(value.size()<name.size());std::copy(value.begin(),value.end(),name.begin());name[value.size()]='\0';return name;
}
static std::vector<u8> payload()
{
    std::vector<u8> bytes(37);for (usz i=0;i<bytes.size();++i) bytes[i]=static_cast<u8>(i*19+7);return bytes;
}
static void archive(utils::serial& ar,std::string_view path,lv2_file_type type,s32 flags,bool memory)
{
    const auto name=saved_name(path); const s32 mode=0600;const u32 lock=7;const std::string real(path);
    ar(name,mode,flags,type,lock,real);
    if (type==lv2_file_type::edata) { const std::array<u8,16> key{1,2,3};ar(key); }
    ar(memory);
    if (memory)
    {
        fs::stat_t stat{};stat.size=37;stat.atime=123;stat.mtime=456;stat.ctime=789;stat.is_writable=true;ar(stat);
        const auto bytes=payload();ar(std::span<const u8>(bytes));
    }
    const s64 seek=9;ar(seek);ar.set_reading_state();
}
static void reset(bool valid,bool readonly,CellError error,bool inspection=false)
{
    events.clear();lookups=opens=errors=successes=0;host_open_valid=valid;host_error=error;
    g_fxo->mounts.mount.read_only=readonly;g_cfg.savestate.state_inspection_mode=inspection;
    g_fxo->keys={};g_fxo->keys.one_time_key={0xa5,0x7e};g_fxo->keys.npdrm_fds.count=11;
}
static bool has(std::string_view stage) { return std::ranges::any_of(events,[&](const Event& e){return e.stage==stage;}); }
[[maybe_unused]] static const Event& event(std::string_view stage)
{
    const auto it=std::ranges::find_if(events,[&](const Event& e){return e.stage==stage;});ensure(it!=events.end());
    ensure(std::ranges::count_if(events,[&](const Event& e){return e.stage==stage;})==1);return *it;
}
static bool added(std::string_view stage)
{
    return stage=="file_path_class"||stage=="file_mount_read_only"||stage=="file_open_error"||stage=="file_in_memory"||stage=="file_unavailable";
}
static unsigned new_events=0;
static void diagnostics(u64 path_class,bool readonly,bool valid,bool memory,bool unavailable,lv2_file_type type)
{
#ifdef FS_BASELINE
    (void)path_class;(void)readonly;(void)valid;(void)memory;(void)unavailable;(void)type;
    ensure(std::ranges::none_of(events,[](const Event& e){return added(e.stage);}));
#else
    ensure(event("file_path_class").value==path_class&&event("file_mount_read_only").value==readonly);
    ensure(event("file_in_memory").value==memory);
    ensure(has("file_open_error")==!valid&&has("file_unavailable")==unavailable);
    if (!valid) ensure(event("file_open_error").value==static_cast<u32>(host_error));
    if (unavailable) ensure(event("file_unavailable").value==static_cast<u32>(host_error));
    ensure(event("file_path_class").position==event("file_path_ready").position);
    ensure(event("file_in_memory").position>event("file_open_end").position);
    for (const auto& e:events) if (added(e.stage))
    {
        ensure(e.id==3&&e.type==static_cast<u32>(type));++new_events;
        // Every new record consists exclusively of a fixed stage plus numbers.
        ensure(e.stage.find('/')==std::string_view::npos);
    }
#endif
}
[[noreturn]] static void failure_adapter(std::source_location loc)
{
    const auto reject=[] { std::fputs("Unexpected fixture verification failure\n",stderr);std::abort(); };
    if (!observed_archive||observed_archive->data!=saved_archive) reject();
    if (failure_mode.starts_with("unavailable-"))
    {
        if (lookups!=1||opens!=1||errors!=1||successes||observed_archive->pos!=saved_archive.size()||g_fxo->keys.one_time_key!=std::array<u8,16>{}) reject();
        const auto type=failure_mode=="unavailable-regular"?lv2_file_type::regular:failure_mode=="unavailable-sdata"?lv2_file_type::sdata:lv2_file_type::edata;
        if (last_open.flags!=0||last_open.mode!=0600||g_fxo->keys.npdrm_fds.count!=(type==lv2_file_type::regular?11u:12u)) reject();
        diagnostics(1,true,false,false,true,type);
        if (has("file_seek_begin")||has("file_ready")) reject();
        std::fputs("EXPECTED unchanged failed-file fatal path; error=0x80010006\n",stderr);std::fflush(stderr);std::_Exit(91);
    }
    if (failure_mode=="truncated-seek"||failure_mode=="truncated-memory")
    {
        if (std::string_view(loc.file_name()).find("serialization.hpp")==std::string_view::npos||lookups!=1||opens!=1) reject();
        const bool memory=failure_mode=="truncated-memory";
        if (events.empty()||events.back().stage!=(memory?"file_memory_allocated":"file_seek_begin")||has("file_ready")) reject();
        if (g_fxo->keys.one_time_key!=std::array<u8,16>{}) reject();
        std::fputs("REJECT unchanged truncated archive through real serializer\n",stderr);std::fflush(stderr);std::_Exit(92);
    }
    std::fprintf(stderr,"Unexpected verification at %s:%u\n",loc.file_name(),loc.line());std::abort();
}
[[noreturn]] static void throw_adapter()
{
    if (failure_mode!="unterminated"||!observed_archive||observed_archive->pos!=0x420||lookups||opens||events.empty()||events.back().stage!="name_unterminated") std::abort();
    std::fputs("REJECT unchanged unterminated name before mount lookup\n",stderr);std::fflush(stderr);std::_Exit(88);
}
static u64 fingerprint=1469598103934665603ull;
static void mix(u64 value) { fingerprint=(fingerprint^value)*1099511628211ull; }
static void run(std::string_view path,u64 path_class,lv2_file_type type,s32 access,bool valid,bool memory,bool readonly,bool inspection)
{
    const auto error=type==lv2_file_type::regular?CELL_ENOENT:type==lv2_file_type::sdata?CELL_EACCES:CELL_ENOTMOUNTED;
    reset(valid,readonly,valid?static_cast<CellError>(0):error,inspection);
    utils::serial ar;const s32 flags=access|000100|001000|002000;archive(ar,path,type,flags,memory);const auto saved=ar.data;
    lv2_file file(ar);
    ensure(ar.data==saved&&ar.pos==saved.size()&&opens==1&&lookups==1);
    ensure(file.name==saved_name(path)&&file.mode==0600&&file.flags==flags&&file.lock==7&&file.type==type);
    ensure(last_open.path==path&&last_open.flags==access&&last_open.mode==0600);
    ensure(last_open.size==(type==lv2_file_type::regular?0:8));
    ensure(last_open.argument==(type==lv2_file_type::sdata?0x18000000010:type==lv2_file_type::edata?2:0));
    ensure(last_open.key[0]==(type==lv2_file_type::edata?1:0xa5));
    ensure(g_fxo->keys.one_time_key==std::array<u8,16>{}&&g_fxo->keys.npdrm_fds.count==(type==lv2_file_type::regular?11u:12u));
    const bool available=valid||memory;
    ensure(!!file.file==available&&file.real_path=="/host-adapter/file");
    ensure(file.file.seek_pos==(available?9:-1));
    ensure(errors==!available&&successes==available&&has("file_ready")==available);
    ensure(file.file.bytes==(memory?payload():std::vector<u8>{}));
    if (memory) ensure(file.file.stat.size==37&&file.file.stat.atime==123&&file.file.stat.mtime==456&&file.file.stat.ctime==789&&file.file.stat.is_writable);
    diagnostics(path_class,readonly,valid,memory,!available,type);
    mix(ar.pos);mix(file.mode);mix(file.flags);mix(file.lock);mix(static_cast<u32>(file.type));mix(static_cast<u64>(file.file.seek_pos));mix(available);mix(g_fxo->keys.npdrm_fds.count);
    for (const auto b:file.file.bytes) mix(b);
}
int main(int argc,char** argv)
{
    if (argc>1)
    {
        failure_mode=argv[1];reset(!failure_mode.starts_with("unavailable-"),true,CELL_ENOENT);
        utils::serial ar;
        if (failure_mode=="unterminated") { std::array<char,0x420> name;name.fill('x');ar(name);ar.set_reading_state(); }
        else
        {
            const auto type=failure_mode=="unavailable-sdata"?lv2_file_type::sdata:failure_mode=="unavailable-edata"?lv2_file_type::edata:lv2_file_type::regular;
            archive(ar,"/dev_bdvd/PS3_GAME/USRDIR/test.bin",type,0,failure_mode=="truncated-memory");
            if (failure_mode=="truncated-seek") ar.data.resize(ar.data.size()-1);
            if (failure_mode=="truncated-memory") ar.data.resize(ar.data.size()-9);
        }
        observed_archive=&ar;saved_archive=ar.data;lv2_file file(ar);return 99;
    }
    unsigned cases=0,path_cases=0;
    for (auto type:{lv2_file_type::regular,lv2_file_type::sdata,lv2_file_type::edata})
    for (s32 access:{0,1,2}) for (bool memory:{false,true})
    { run("/dev_hdd0/game/TEST/file.bin",2,type,access,true,memory,false,false);++cases; }
    for (auto type:{lv2_file_type::regular,lv2_file_type::sdata,lv2_file_type::edata})
    {
        const auto path=type==lv2_file_type::regular?"/dev_bdvd/PS3_GAME/USRDIR/file.bin":type==lv2_file_type::sdata?"/dev_flash/sys/file.bin":"/dev_usb000/TEST/file.bin";
        const u64 category=type==lv2_file_type::regular?1:type==lv2_file_type::sdata?4:5;
        run(path,category,type,0,false,true,type!=lv2_file_type::edata,false);++cases;
    }
    for (auto type:{lv2_file_type::regular,lv2_file_type::sdata,lv2_file_type::edata})
    {
        const auto path=type==lv2_file_type::regular?"/dev_hdd1/cache/file.bin":type==lv2_file_type::sdata?"/host_root/TEST/file.bin":"/unknown/TEST/file.bin";
        const u64 category=type==lv2_file_type::regular?3:type==lv2_file_type::sdata?6:0;
        run(path,category,type,2,false,false,false,true);++cases;
    }
#ifndef FS_BASELINE
    for (const auto& [path,expected]:std::array<std::pair<std::string_view,u64>,15>{{
        {"/dev_bdvd/file",1},{"/dev_hdd0/file",2},{"/dev_hdd1/file",3},{"/dev_flash/file",4},
        {"/dev_usb000/file",5},{"/dev_usb/file",5},{"/host_root/file",6},{"",0},
        {"/dev_bdvd",0},{"/dev_bdvdx/file",0},{"/dev_hdd00/file",0},{"/dev_flash2/file",0},
        {"relative/private/file",0},{"/host_root_other/file",0},{"/app_home/file",0}}})
    { ensure(lv2_fs_restore_path_class(path)==expected);++path_cases; }
#endif
    std::cout<<"{\"fileCases\":"<<cases<<",\"pathClassCases\":"<<path_cases<<",\"newDiagnosticEvents\":"<<new_events<<",\"stateFingerprint\":\""<<fingerprint<<"\"}\n";
}
