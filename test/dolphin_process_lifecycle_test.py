"""Execute the shipped lifecycle across alternating consoles and failed launches."""
from __future__ import annotations

import importlib.util
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


def bridge_source():
    spec = importlib.util.spec_from_file_location('dolphin_bridge_lifecycle',
        ROOT / 'build-utils/patch_dolphin_internal_core_v2.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.BRIDGE_SOURCE


def function(source, signature):
    start = source.index(signature)
    opening = source.index('\n{', start)
    closing = source.index('\n}', opening)
    # Queue blocks have the same capture/lifetime here as the production
    # synchronous host call. The harness instruments host affinity and joins.
    return source[start:closing + 2].replace('^{', '[&]{')


class DolphinProcessLifecycleTests(unittest.TestCase):
    def test_alternating_consoles_keep_process_services_and_release_each_game(self):
        compiler = shutil.which('c++') or shutil.which('clang++')
        if not compiler:
            self.skipTest('C++ compiler required')
        source = bridge_source()
        harness = r'''
#include <atomic>
#include <array>
#include <cassert>
#include <cstdint>
#include <mutex>
#include <optional>
#include <string>
#include <utility>
#include <vector>
int ui_init=0, controllers_init=0, process_shutdown=0, joins=0, host_depth=0, achievement_clears=0;
bool uninitialized=true, stop_requested=false, achievement_configuration_active=false;
std::vector<std::string> stages;
std::mutex g_state_mutex;
std::atomic<bool> g_initialized{false}, g_running{false}, g_cleanup_started{false};
std::atomic<bool> g_jit_handshake{false}, g_executable_probe{false}, g_devices_changed{false};
std::atomic<int> g_boot_language{-1};
std::string g_user_directory, g_system_directory, g_log_path, g_validated_game, g_validated_system;
std::string g_game_id, g_gametdb_id;
uint16_t g_game_revision=0;
bool g_validated_wii_menu=false;
bool g_wiimmfi_session=false;
std::atomic<bool> g_wiimmfi_network_allowed{false};
std::atomic<bool> g_wiimmfi_boot_interrupted{false};
std::string g_wiimmfi_previous_nand_root;
std::atomic<int32_t> g_wiimmfi_nand_stage{0};
std::array<std::atomic<uint32_t>, 8> g_wiimmfi_network_events{};
constexpr int D_WIIROOT_IDX=0;
constexpr int D_SESSION_WIIROOT_IDX=1;
namespace File {
std::string wii_root="User/Wii/", session_root="User/Wii/";
const std::string& GetUserPath(int index) { return index==D_WIIROOT_IDX?wii_root:session_root; }
void SetUserPath(int, std::string path) { wii_root=std::move(path); }
}
bool DOLWiimmfiNANDReady(const std::string&) { return true; }
bool tls_files_valid=true;
bool neostation_dolphin_wiimmfi_tls_files_valid(const std::string&) { return tls_files_valid; }
void* g_metal_surface=nullptr;
double g_metal_scale=1;
std::optional<int> g_devices_callback;
std::optional<int> g_capture_previous_scale;
int current_scale=4;
namespace Core {
struct System { static System& GetInstance() { static System s; return s; } };
bool IsUninitialized(System&) { return uninitialized; }
void Stop(System&) { assert(host_depth); stop_requested=true; }
void Shutdown(System&) {
 assert(host_depth && stop_requested); ++joins; uninitialized=true; stop_requested=false;
 // Real BootManager::RestoreConfig clears CurrentRun during core teardown.
 current_scale=0;
}
}
namespace Config {
 constexpr int GFX_EFB_SCALE=0;
 void SetCurrent(int, int value) { assert(host_depth); current_scale=value; }
 void Save() { assert(host_depth); } void Load() { assert(host_depth); }
}
enum class WindowSystemType { iOS };
struct WindowSystemInfo { WindowSystemType type; };
namespace UICommon {
void SetUserDirectory(const std::string&) { assert(host_depth); }
void CreateDirectories() { assert(host_depth); }
void Init() { assert(host_depth); ++ui_init; }
void InitControllers(WindowSystemInfo) { assert(host_depth); ++controllers_init; }
void ShutdownControllers() { ++process_shutdown; }
void Shutdown() { ++process_shutdown; }
}
struct ControllerInterface {
 template<class F> int RegisterDevicesChangedCallback(F) { assert(host_depth); return 7; }
 void UnregisterDevicesChangedCallback(int) { ++process_shutdown; }
} g_controller_interface;
struct DolphinAnalytics {
 static DolphinAnalytics& Instance() { static DolphinAnalytics d; return d; }
 void ReportDolphinStart(const char*) {}
};
namespace ciface::iOS {
struct StateManager {
 static StateManager* GetInstance() { static StateManager s; return &s; }
 void Init() { assert(host_depth); assert(uninitialized); }
};
}
void ApplyConsolePreferences() { assert(host_depth); }
// The RA implementation is exercised separately by dolphin_ra_session_test.
// This lifecycle boundary proves it runs on the host queue after the VM join,
// including a launch that obtained credentials but never started a game.
void DOLClearAchievementSession() {
 assert(host_depth && uninitialized && !stop_requested);
 achievement_configuration_active=false;
 ++achievement_clears;
}
void ConfigurePhysicalControllers() { assert(host_depth); }
void ResetInputProfiles() {}
void DeclareMainAsHostThread() {}
void UndeclareMainAsHostThread() {}
void Log(const std::string& stage, const std::string&) { stages.push_back(stage); }
template<class F> void DOLHostQueueRunSync(F block) { ++host_depth; block(); --host_depth; }
'''
        for signature in ('void ResetSessionFlags()', 'void ShutdownRuntime(',
                          'int32_t neostation_dolphin_initialize(',
                          'int32_t neostation_dolphin_stop(',
                          'bool neostation_dolphin_wiimmfi_network_allowed()',
                          'void neostation_dolphin_wiimmfi_observe(int32_t',
                          'int32_t neostation_dolphin_wiimmfi_diagnostic(',
                          'int32_t neostation_dolphin_wiimmfi_configure(',
                          'bool neostation_dolphin_wiimmfi_validate_boot_nand(',
                          'void neostation_dolphin_wiimmfi_observe_ios_identity(',
                          'void neostation_dolphin_wiimmfi_interrupt_boot()'):
            harness += '\n' + function(source, signature)
        harness += r'''
int main() {
 neostation_dolphin_wiimmfi_interrupt_boot();
 assert(g_wiimmfi_boot_interrupted && !g_wiimmfi_network_allowed);
 assert(neostation_dolphin_initialize(nullptr,"Sys","bad")==0);
 assert(ui_init==0);
 for (int cycle=0; cycle<20; ++cycle) {
   const std::string logfile="session"+std::to_string(cycle);
   assert(neostation_dolphin_initialize("User","Sys",logfile.c_str())==1);
   assert(g_log_path==logfile);
   assert(ui_init==1 && controllers_init==1);
   assert(!g_running && !g_jit_handshake && !g_executable_probe);
   assert(!g_wiimmfi_boot_interrupted);
   assert(g_validated_game.empty() && g_validated_system.empty() && !g_validated_wii_menu);
   assert(g_game_id.empty() && g_gametdb_id.empty() && g_game_revision==0);
   assert(g_metal_surface==nullptr && g_boot_language==-1);
   assert(neostation_dolphin_initialize("anotherUser","Sys","bad")==0);
   assert(g_log_path==logfile && g_user_directory=="User");
   if (cycle%2==0) {
     File::wii_root="OtherNand/";
     tls_files_valid=false;
     assert(!neostation_dolphin_wiimmfi_configure(1));
     assert(!g_wiimmfi_network_allowed && neostation_dolphin_wiimmfi_diagnostic(-1)==-2);
     tls_files_valid=true;
     assert(neostation_dolphin_wiimmfi_configure(1)==1 && g_wiimmfi_network_allowed);
     assert(File::wii_root=="User/Wii" && g_wiimmfi_previous_nand_root=="OtherNand/");
     // A second setup before boot must not replace the original NAND owner.
     assert(neostation_dolphin_wiimmfi_configure(1)==1);
     assert(g_wiimmfi_previous_nand_root=="OtherNand/");
     assert(neostation_dolphin_wiimmfi_configure(0)==1);
     assert(!g_wiimmfi_network_allowed && !g_wiimmfi_session);
     assert(File::wii_root=="OtherNand/" && g_wiimmfi_previous_nand_root.empty());
     assert(neostation_dolphin_wiimmfi_configure(1)==1);
     tls_files_valid=false;
     assert(!neostation_dolphin_wiimmfi_configure(1));
     assert(!g_wiimmfi_network_allowed && !g_wiimmfi_session);
     assert(File::wii_root=="OtherNand/" && g_wiimmfi_previous_nand_root.empty());
     tls_files_valid=true;
     assert(neostation_dolphin_wiimmfi_configure(1)==1);
     assert(!neostation_dolphin_wiimmfi_validate_boot_nand(false));
     File::wii_root="User/Wii/";
     assert(!neostation_dolphin_wiimmfi_validate_boot_nand(true));
     assert(neostation_dolphin_wiimmfi_validate_boot_nand(false));
     neostation_dolphin_wiimmfi_observe_ios_identity(false);
     assert(neostation_dolphin_wiimmfi_diagnostic(-1)==-4);
     File::session_root="OtherNand/";
     neostation_dolphin_wiimmfi_observe_ios_identity(true);
     assert(neostation_dolphin_wiimmfi_diagnostic(-1)==-4);
     File::session_root="User/Wii/";
     neostation_dolphin_wiimmfi_observe_ios_identity(true);
     assert(neostation_dolphin_wiimmfi_diagnostic(-1)==3);
     neostation_dolphin_wiimmfi_observe(5);
     assert(neostation_dolphin_wiimmfi_diagnostic(5)==1);
   }
   g_validated_system=cycle%2 ? "gc" : "wii";
   g_validated_game="game";
   g_running=true; uninitialized=false;
   g_wiimmfi_session=cycle%2==0;
   g_wiimmfi_network_allowed=g_wiimmfi_session;
   neostation_dolphin_wiimmfi_interrupt_boot();
   assert(g_wiimmfi_boot_interrupted && g_wiimmfi_network_allowed==g_wiimmfi_session);
   achievement_configuration_active=true;
   g_jit_handshake=true; g_executable_probe=true;
   g_metal_surface=reinterpret_cast<void*>(uintptr_t{42});
   g_boot_language=3;
   g_capture_previous_scale=4; current_scale=2;
   assert(neostation_dolphin_initialize("User","Sys","overlap")==0);
   assert(g_log_path==logfile);
   assert(neostation_dolphin_stop(logfile.c_str())==1);
   assert(uninitialized && !g_running && !g_cleanup_started);
   assert(!g_wiimmfi_session);
   assert(!g_wiimmfi_network_allowed);
   assert(!g_wiimmfi_boot_interrupted);
   assert(File::wii_root=="OtherNand/" && g_wiimmfi_previous_nand_root.empty());
   neostation_dolphin_wiimmfi_observe(5);
   assert(neostation_dolphin_wiimmfi_diagnostic(5)==1);
   assert(g_initialized && process_shutdown==0);
   assert(g_metal_surface==nullptr && g_validated_game.empty());
   assert(current_scale==0 && !g_capture_previous_scale);
   assert(joins==cycle+1);
   assert(achievement_clears==cycle+1 && !achievement_configuration_active);
 }
 // An aborted launch has no running core. Cleanup remains safe and permits
 // another validated session without rebuilding the controller callbacks.
 assert(neostation_dolphin_initialize("User","Sys","failed")==1);
 achievement_configuration_active=true;
 assert(neostation_dolphin_stop("failed")==1);
 assert(!achievement_configuration_active && achievement_clears==21);
 assert(neostation_dolphin_stop("failed")==1);
 assert(!achievement_configuration_active && achievement_clears==22);
 assert(neostation_dolphin_initialize("User","Sys","next")==1);
 assert(ui_init==1 && controllers_init==1 && process_shutdown==0);
}
'''
        with tempfile.TemporaryDirectory() as temporary:
            directory=Path(temporary)
            cpp=directory/'lifecycle.cpp'
            executable=directory/'lifecycle'
            cpp.write_text(harness)
            result=subprocess.run([compiler,'-std=c++17','-pthread',str(cpp),'-o',str(executable)],
                                  capture_output=True,text=True,timeout=60)
            self.assertEqual(result.returncode,0,result.stderr)
            result=subprocess.run([str(executable)],capture_output=True,text=True,timeout=10)
            self.assertEqual(result.returncode,0,result.stderr)


    def test_identity_readiness_rejects_missing_certificate_components(self):
        compiler = shutil.which('c++') or shutil.which('clang++')
        if not compiler:
            self.skipTest('C++ compiler required')
        source = bridge_source()
        harness = r'''
#include <algorithm>
#include <array>
#include <cassert>
#include <cstdint>
#include <cstring>
#include <string>
using u8=uint8_t; using u32=uint32_t;
std::array<u8,0x400> fixture{};
namespace Common {
u32 swap32(const u8* p) { return (u32(p[0])<<24)|(u32(p[1])<<16)|(u32(p[2])<<8)|p[3]; }
using SettingsBuffer=std::array<u8,256>;
struct SettingsReader {
  explicit SettingsReader(const SettingsBuffer&) {}
  std::string GetValue(const char*) { return "SYNTHETIC"; }
};
}
namespace File {
struct IOFile {
  std::string path;
  IOFile(std::string name,const char*) : path(std::move(name)) {}
  size_t GetSize() const {
    return path.ends_with("keys.bin") ? fixture.size() : path.ends_with("setting.txt") ? 256 : 32;
  }
  bool ReadBytes(void* out,size_t size) {
    if (path.ends_with("keys.bin")) std::memcpy(out,fixture.data(),size);
    else std::memset(out,0,size);
    return true;
  }
};
bool IsDirectory(const std::string&) { return true; }
}
'''
        harness += function(source, 'bool DOLWiimmfiNANDReady(')
        harness += r'''
int main() {
  fixture[0x124]=1; fixture[0x128]=1;
  fixture[0x203]=1; fixture[0x207]=1;
  fixture[0x20c]=1; fixture[0x22a]=1;
  assert(DOLWiimmfiNANDReady("synthetic"));
  for (const auto& [begin,end] : {std::pair{0x128,0x146},std::pair{0x20c,0x22a},
                                std::pair{0x22a,0x248},std::pair{0x200,0x204},
                                std::pair{0x204,0x208}}) {
    const auto valid=fixture;
    for (const u8 fill : {u8{0},u8{0xff}}) {
      std::fill(fixture.begin()+begin,fixture.begin()+end,fill);
      assert(!DOLWiimmfiNANDReady("synthetic"));
    }
    fixture=valid;
  }
}
'''
        with tempfile.TemporaryDirectory() as temporary:
            path=Path(temporary)
            cpp=path/'identity.cpp'
            cpp.write_text(harness)
            subprocess.run([compiler,'-std=c++20','-Wall','-Wextra','-Werror',
                            str(cpp),'-o',str(path/'identity')],check=True)
            result=subprocess.run([str(path/'identity')],capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)


if __name__ == '__main__':
    unittest.main()
