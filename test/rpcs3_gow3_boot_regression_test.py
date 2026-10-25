#!/usr/bin/env python3
"""Run production boot fragments and the VMA policy with portable adapters.

Filesystem fixtures replace the mounted ISO; the SFO parser and logger are
adapters. This checks path selection/identity, not ISO decoding or iOS gameplay.
Pass the materialized canonical Core directory as the sole argument.
"""
from pathlib import Path
import os
import shlex
import shutil
import subprocess
import sys
import tempfile

core = Path(sys.argv[1]).resolve()
system = (core / "rpcs3/Emu/System.cpp").read_text()
begin = system.index("\t\t// Load PARAM.SFO (TODO)")
end = system.index("\n\t\tconst auto version_app", begin)
metadata = system[begin:end]
notice = system.index('sys_log.notice("Savestate: Loading iso archive")')
begin = system.rfind("\t\t\tif (launching_from_disc_archive)", 0, notice)
end = system.index("\n\t\t}\n\t\telse if (m_path.starts_with(vfs_boot_prefix))", notice)
remount = system[begin:end]
cpu_marker = "// REWINDBOX_GOW3_GAME_CPU_DIAGNOSTICS_V1"
cpu_diagnostics = ""
if cpu_marker in system:
    begin = system.index("\n\t\t\t{", system.index(cpu_marker))
    end = system.index("\n#endif", begin)
    cpu_diagnostics = system[begin:end]
    assert system.index("format_config_layers_line(ios_layers)") < begin
    assert begin < system.index("// Backup config", begin)

prefix = r'''
#include <cassert>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <map>
#include <sstream>
#include <string>
#include <string_view>
#include <vector>
#include "ios/IOSMemoryPressurePolicy.h"
#include "Emu/RSX/VK/vkutils/VRAMBudgetPolicy.h"
namespace fs {
const std::string delim = "/\\";
bool is_dir(const std::string& path) { return std::filesystem::is_directory(path); }
std::string get_parent_dir(const std::string& path) {
    return std::filesystem::path(path).parent_path().string();
}
}
namespace iso_device { std::string virtual_device_name; }
namespace psf {
using registry = std::map<std::string, std::string>;
registry load_object(const std::string& path) {
    registry result;
    std::ifstream input(path);
    std::string key, value;
    while (input >> key >> value) result[key] = value;
    return result;
}
std::string_view get_string(const registry& obj, const std::string& key,
        std::string_view fallback = {}) {
    const auto found = obj.find(key);
    return found == obj.end() ? fallback : found->second;
}
}
std::string hdd0;
namespace rpcs3::utils {
std::string get_hdd0_dir() { return hdd0; }
std::string get_sfo_dir_from_game_path(const std::string& path, const std::string&) {
    return std::filesystem::exists(path + "/PS3_DISC.SFB") ? path + "/PS3_GAME" : path;
}
}
struct Logger {
    std::vector<std::string> lines;
    template<class... T> void notice(const char* format, T&&... args) {
        std::ostringstream out;
        out << format;
        ((out << " " << args), ...);
        lines.push_back(out.str());
    }
} sys_log;
struct Setting { std::string value; std::string to_string() const { return value; } };
struct { struct { Setting llvm_cpu; } core; } g_cfg;
struct jit_compiler {
    static const std::vector<std::string>& target_attributes() {
        static const std::vector<std::string> features{"+sha3", "+dotprod", "+i8mm", "-sve", "-sve2"};
        return features;
    }
    static std::string cpu(const std::string& configured) { return configured.empty() ? "apple-m4" : configured; }
    static std::string triple1() { return "aarch64-unknown-linux-android"; }
    static std::string triple2() { return triple1(); }
};
std::string mounted;
void load_iso(const std::string& path) { mounted = path; }
struct Boot {
    std::string m_path, m_path_real, disc, m_cat = "DG", m_sfo_dir;
    std::string m_title, m_title_id, m_game_dir = "PS3_GAME", elf_dir;
    bool launching_from_disc_archive = false;
    bool m_ar = false;
    std::string disc_info;
    std::vector<std::string> argv{"PS3_GAME/USRDIR/EBOOT.BIN"};
    bool resolve_path_as_vfs_path = true;
    void restore_iso() {
'''
suffix = r'''
    }
};
void write_sfo(const std::string& path, const std::string& id) {
    std::filesystem::create_directories(path);
    std::ofstream(path + "/PARAM.SFO") << "TITLE GodOfWarIII\nTITLE_ID " << id << "\nCATEGORY DG\n";
}
void check_identity(Boot boot, const std::string& expected_dir, const std::string& id) {
    boot.elf_dir = fs::get_parent_dir(boot.m_path);
    boot.metadata();
    assert(boot.m_sfo_dir == expected_dir);
    assert(boot.m_title_id == id);
    assert(rpcs3::ios::is_god_of_war_iii_title(boot.m_title_id) ==
        (id == "BCES00510" || id == "BCUS98111"));
}
int main(int argc, char** argv) {
    assert(argc == 2);
    const std::string root = argv[1];
    iso_device::virtual_device_name = root + "/mounted_iso";
    write_sfo(iso_device::virtual_device_name + "/PS3_GAME", "BCES00510");
    write_sfo(iso_device::virtual_device_name + "/PS3_GM01", "BCUS98111");
    const std::string archive = root + "/God of War III.iso";
    std::ofstream(archive) << "fixture";
    Boot boot;
    boot.launching_from_disc_archive = true;
    boot.m_path = iso_device::virtual_device_name + "/PS3_GAME/USRDIR/EBOOT.BIN";
    // Fresh boot and a portable-state boot whose disc is the real ISO file.
    check_identity(boot, iso_device::virtual_device_name + "/PS3_GAME", "BCES00510");
    boot.disc = archive;
    check_identity(boot, iso_device::virtual_device_name + "/PS3_GAME", "BCES00510");
    boot.disc_info = archive;
    boot.m_path_real = root + "/obsolete_container/other.iso";
    boot.restore_iso();
    assert(mounted == archive && boot.m_path_real == archive);
    assert(!boot.resolve_path_as_vfs_path);
    assert(boot.m_path == iso_device::virtual_device_name + "/PS3_GAME/USRDIR/EBOOT.BIN");
    // Select the saved game directory on multi-game discs, never a stale ID.
    boot.m_game_dir = "PS3_GM01";
    boot.m_title_id = "BCES00510";
    check_identity(boot, iso_device::virtual_device_name + "/PS3_GM01", "BCUS98111");
    boot.m_game_dir = "MISSING";
    check_identity(boot, iso_device::virtual_device_name + "/MISSING", "");
    // Folder, PSN and installed-data metadata retain the existing branches.
    boot = {};
    const std::string folder = root + "/folder_game";
    write_sfo(folder + "/PS3_GAME", "BCES00510");
    boot.disc = folder;
    boot.m_path = folder + "/PS3_GAME/USRDIR/EBOOT.BIN";
    check_identity(boot, folder + "/PS3_GAME", "BCES00510");
    boot.disc.clear();
    check_identity(boot, folder + "/PS3_GAME", "BCES00510");
    boot.m_path = folder + "/PS3_GAME";
    check_identity(boot, folder + "/PS3_GAME", "BCES00510");
    boot.m_cat = "HG";
    boot.disc = root + "/psn_game";
    boot.m_path = boot.disc + "/USRDIR/EBOOT.BIN";
    write_sfo(boot.disc, "NPUB00001");
    check_identity(boot, boot.disc, "NPUB00001");
    hdd0 = root + "/hdd0/";
    boot.m_cat = "GD";
    boot.m_title_id = "BCES00510";
    write_sfo(hdd0 + "game/BCES00510", "BCES00510");
    check_identity(boot, hdd0 + "game/BCES00510", "BCES00510");
    // Report every game boot with its final configured CPU; self-test state
    // must not suppress the resume log or silently replace an explicit CPU.
    sys_log.lines.clear();
    boot.m_title_id = "BCES00510";
    g_cfg.core.llvm_cpu.value.clear();
    boot.report_cpu();
    assert(sys_log.lines.size() == 1);
    assert(sys_log.lines.back().find("BCES00510 0 auto apple-m4") != std::string::npos);
    assert(sys_log.lines.back().find("+sha3,+dotprod,+i8mm,-sve,-sve2") != std::string::npos);
    boot.m_ar = true;
    g_cfg.core.llvm_cpu.value = "generic";
    boot.report_cpu();
    assert(sys_log.lines.size() == 2);
    assert(sys_log.lines.back().find("BCES00510 1 generic generic") != std::string::npos);
    std::cout << "PASS production ISO metadata, restored archive ownership, multi-game/folder/PSN identities\n";
}
'''

policy = r'''
#include <cassert>
#include <cstdint>
#include <iostream>
#include "Emu/RSX/VK/vkutils/VRAMBudgetPolicy.h"
int main() {
    constexpr std::uint64_t MiB = 1ull << 20, GiB = 1024 * MiB;
    // 508 device-reported heap, rather than an assumed physical RAM size.
    constexpr std::uint64_t reported = 7989460992;
    assert(vk::get_preferred_vram_block_size(0) == 0);
#if defined(RPCS3_IOS) && !defined(RPCS3_MACOS)
    assert(vk::get_preferred_vram_block_size(1) == 32 * MiB);
    assert(vk::get_preferred_vram_block_size(4 * GiB) == 32 * MiB);
    assert(vk::get_preferred_vram_block_size(4 * GiB + 1) == 64 * MiB);
    assert(vk::get_preferred_vram_block_size(reported) == 64 * MiB);
    assert(vk::get_preferred_vram_block_size(8 * GiB) == 64 * MiB);
    assert(vk::get_preferred_vram_block_size(8 * GiB + 1) == 0);
    assert(vk::get_effective_vram_pressure_limit(reported, 4 * GiB) <= 2 * GiB);
#else
    for (auto heap : {4 * GiB, reported, 8 * GiB, 16 * GiB})
        assert(vk::get_preferred_vram_block_size(heap) == 0);
#endif
    // Preferred granularity changes no explicit allocation ceiling.
    assert(vk::get_requested_vram_allocation_limit(reported, GiB) == GiB);
    assert(vk::get_requested_vram_allocation_limit(reported, 16 * GiB) == reported);
    assert(vk::get_available_vram_budget(GiB, 2 * GiB) == 0);
    std::cout << "PASS VMA reported-heap boundaries and explicit ceiling preservation\n";
}
'''
cxx = shlex.split(os.environ.get("CXX") or shutil.which("clang++") or "c++")
if sdk := os.environ.get("HOST_MACOS_SDK"):
    cxx += ["-isysroot", sdk]
flags = [*cxx, "-std=c++20", "-O1", "-g", "-Wall", "-Wextra", "-Werror",
         "-fsanitize=address,undefined", "-fno-sanitize-recover=all", "-I" + str(core / "rpcs3")]
with tempfile.TemporaryDirectory(prefix="rpcs3-gow3-boot-") as temporary:
    work = Path(temporary)
    (work / "boot.cpp").write_text(prefix + remount + "\n    }\n    void report_cpu() {\n" +
        cpu_diagnostics + "\n    }\n    void metadata() {\n" + metadata + suffix)
    subprocess.run([*flags, "-DRPCS3_IOS", work / "boot.cpp", "-o", work / "boot"], check=True, timeout=90)
    subprocess.run([work / "boot", work], check=True, timeout=15)
    (work / "policy.cpp").write_text(policy)
    for name, macros in [("ios", ["-DRPCS3_IOS"]), ("macos", ["-DRPCS3_IOS", "-DRPCS3_MACOS"]), ("desktop", [])]:
        subprocess.run([*flags, *macros, work / "policy.cpp", "-o", work / name], check=True, timeout=90)
        subprocess.run([work / name], check=True, timeout=15)
print("PASS God of War III boot regressions; no device FPS or footprint claim")
