// SPDX-License-Identifier: GPL-2.0-or-later
// Owned C ABI: the frontend never reaches through to Dolphin C++ exports.
#include "DiscIO/NANDImporter.h"
#include "Common/IOFile.h"
#include "Common/SettingsHandler.h"
#include "Common/Version.h"
#include <stdexcept>

extern "C" bool neostation_dolphin_wiimmfi_tls_files_valid(const std::string& root);

namespace
{
std::atomic<bool> g_wiimmfi_cancel{false};
std::atomic<int> g_wiimmfi_progress{0}; // reading 0..100, extracting 1000..1100
std::atomic<int32_t> g_wiimmfi_nand_stage{0}; // 1 armed, 2 verified before IOS, negative: refused
std::array<std::atomic<uint32_t>, 9> g_wiimmfi_network_events{};

bool DOLWiimmfiNANDReady(const std::string& root)
{
  // Structural readiness only. The real service validates console identity.
  File::IOFile keys(root + "/keys.bin", "rb");
  std::array<u8, 0x400> bytes{};
  if (keys.GetSize() != bytes.size() || !keys.ReadBytes(bytes.data(), bytes.size())) return false;
  const u32 id = Common::swap32(bytes.data() + 0x124);
  if (id == 0 || id == 0xffffffff || id == 0x0403ac68) return false;
  const auto nonzero = [](auto begin, auto end) {
    return std::any_of(begin, end, [](u8 b) { return b != 0; }) &&
           std::any_of(begin, end, [](u8 b) { return b != 0xff; });
  };
  if (!nonzero(bytes.begin() + 0x128, bytes.begin() + 0x146)) return false;
  // IOSC builds the device certificate from both ECC signature components and
  // its CA/MS issuers. Missing components cannot be repaired by a TLS probe.
  if (!nonzero(bytes.begin() + 0x20c, bytes.begin() + 0x22a) ||
      !nonzero(bytes.begin() + 0x22a, bytes.begin() + 0x248)) return false;
  for (const size_t offset : {size_t{0x200}, size_t{0x204}})
  {
    const u32 issuer = Common::swap32(bytes.data() + offset);
    if (issuer == 0 || issuer == 0xffffffff) return false;
  }
  File::IOFile settings(root + "/title/00000001/00000002/data/setting.txt", "rb");
  Common::SettingsBuffer settings_bytes{};
  if (settings.GetSize() != settings_bytes.size() ||
      !settings.ReadBytes(settings_bytes.data(), settings_bytes.size())) return false;
  const auto serial = Common::SettingsReader(settings_bytes).GetValue("SERNO");
  // Boot must not invent a serial number for an online console identity.
  if (serial.empty() || serial == "000000000") return false;
  for (const char* name : {"clientca.pem", "clientcakey.pem", "rootca.pem"})
  {
    File::IOFile certificate(root + "/" + name, "rb");
    if (certificate.GetSize() < 32 || certificate.GetSize() > 64 * 1024) return false;
  }
  return File::IsDirectory(root + "/title") && File::IsDirectory(root + "/shared2");
}
}

extern "C" __attribute__((visibility("default")))
int32_t neostation_dolphin_wiimmfi_abi() { return 5; }

extern "C" __attribute__((visibility("default")))
const char* neostation_dolphin_wiimmfi_core_revision() { return Common::GetScmRevGitStr().c_str(); }

extern "C" bool neostation_dolphin_wiimmfi_network_allowed()
{
  return g_wiimmfi_network_allowed.load();
}

extern "C" __attribute__((visibility("default")))
int32_t neostation_dolphin_wiimmfi_nand_ready(const char* root)
{
  return root && DOLWiimmfiNANDReady(root) ? 1 : 0;
}

extern "C" __attribute__((visibility("default")))
int32_t neostation_dolphin_wiimmfi_tls_ready(const char* root)
{
  return root && neostation_dolphin_wiimmfi_tls_files_valid(root) ? 1 : 0;
}

extern "C" void neostation_dolphin_wiimmfi_observe(int32_t event)
{
  if (neostation_dolphin_wiimmfi_network_allowed() && event >= 0 &&
      static_cast<size_t>(event) < g_wiimmfi_network_events.size())
    g_wiimmfi_network_events[event].fetch_add(1, std::memory_order_relaxed);
}

extern "C" __attribute__((visibility("default")))
int32_t neostation_dolphin_wiimmfi_diagnostic(int32_t field)
{
  if (field == -1) return g_wiimmfi_nand_stage.load();
  if (field < 0 || static_cast<size_t>(field) >= g_wiimmfi_network_events.size()) return 0;
  return static_cast<int32_t>(g_wiimmfi_network_events[field].load(std::memory_order_relaxed));
}

extern "C" __attribute__((visibility("default")))
int32_t neostation_dolphin_wiimmfi_import_progress() { return g_wiimmfi_progress.load(); }

extern "C" __attribute__((visibility("default")))
void neostation_dolphin_wiimmfi_cancel_import() { g_wiimmfi_cancel = true; }

// May be called by the foreground observer while the runtime queue is booting.
// Never change the network/log policy or touch Core services from that thread.
extern "C" __attribute__((visibility("default")))
void neostation_dolphin_wiimmfi_interrupt_boot()
{
  g_wiimmfi_boot_interrupted = true;
}

extern "C" __attribute__((visibility("default")))
int32_t neostation_dolphin_wiimmfi_import(const char* image, const char* keys, const char* stage)
{
  std::lock_guard<std::mutex> lock(g_state_mutex);
  if (!image || !stage || g_running || g_cleanup_started ||
      !Core::IsUninitialized(Core::System::GetInstance())) return 2;
  g_wiimmfi_cancel = false;
  g_wiimmfi_progress = 0;
  try
  {
    // A fresh, private stage is required. No process-wide NAND path is changed.
    if (!File::IsDirectory(stage)) return 3;
    DiscIO::NANDImporter importer(stage);
    importer.ImportNANDBin(image, [&] {
      if (g_wiimmfi_cancel) throw std::runtime_error("cancelled");
      g_wiimmfi_progress = (importer.IsExtracting() ? 1000 : 0) + importer.GetProgress();
    }, [keys] { return keys ? std::string(keys) : std::string{}; });
    if (!importer.Succeeded() || !DOLWiimmfiNANDReady(stage)) return 3;
    return 0;
  }
  catch (...) { return g_wiimmfi_cancel ? 1 : 3; }
}

extern "C" __attribute__((visibility("default")))
int32_t neostation_dolphin_wiimmfi_configure(int32_t enabled)
{
  if (g_running || g_cleanup_started || !Core::IsUninitialized(Core::System::GetInstance())) return 0;
  // Reconfiguration is allowed while idle, including after a failed preflight.
  // Return the previous NAND ownership before saving a new session override.
  g_wiimmfi_network_allowed = false;
  g_wiimmfi_session = false;
  if (!g_wiimmfi_previous_nand_root.empty())
  {
    DOLHostQueueRunSync(^{
      File::SetUserPath(D_WIIROOT_IDX, std::exchange(g_wiimmfi_previous_nand_root, {}));
    });
  }
  if (enabled)
  {
    for (auto& counter : g_wiimmfi_network_events) counter = 0;
    g_wiimmfi_nand_stage = 0;
    const std::string root = g_user_directory + "/Wii";
    if (!g_initialized || !DOLWiimmfiNANDReady(root)) { g_wiimmfi_nand_stage = -1; return 0; }
    if (!neostation_dolphin_wiimmfi_tls_files_valid(root)) { g_wiimmfi_nand_stage = -2; return 0; }
    DOLHostQueueRunSync(^{
      g_wiimmfi_previous_nand_root = File::GetUserPath(D_WIIROOT_IDX);
      File::SetUserPath(D_WIIROOT_IDX, root);
    });
    g_wiimmfi_nand_stage = 1;
  }
  g_wiimmfi_boot_interrupted = false;
  g_wiimmfi_session = enabled != 0;
  g_wiimmfi_network_allowed = enabled != 0;
  return 1;
}

extern "C" void neostation_dolphin_wiimmfi_boot_policy()
{
  // BootManager calls this after metadata and per-title settings are loaded.
  // CurrentRun is removed by upstream RestoreConfig; offline preferences stay.
  if (!g_wiimmfi_session) return;
  Config::SetCurrent(Config::MAIN_ENABLE_CHEATS, false);
  Config::SetCurrent(Config::MAIN_EMULATION_SPEED, 1.0f);
  Config::SetCurrent(Config::MAIN_OVERCLOCK_ENABLE, false);
  Config::SetCurrent(Config::MAIN_VI_OVERCLOCK_ENABLE, false);
  Config::SetCurrent(Config::MAIN_SYNC_GPU_OVERCLOCK, 1.0f);
  // Session diagnostics must not inherit optional decrypted-payload dumps.
  Config::SetCurrent(Config::MAIN_NETWORK_SSL_DUMP_READ, false);
  Config::SetCurrent(Config::MAIN_NETWORK_SSL_DUMP_WRITE, false);
  Config::SetCurrent(Config::MAIN_NETWORK_SSL_DUMP_ROOT_CA, false);
  Config::SetCurrent(Config::MAIN_NETWORK_SSL_DUMP_PEER_CERT, false);
  Config::SetCurrent(Config::MAIN_NETWORK_DUMP_BBA, false);
  Config::SetCurrent(Config::MAIN_NETWORK_DUMP_AS_PCAP, false);
  Config::SetCurrent(Config::MAIN_NETWORK_SSL_VERIFY_CERTIFICATES, true);
}

extern "C" bool neostation_dolphin_wiimmfi_validate_boot_nand(bool deterministic)
{
  if (!g_wiimmfi_session) return true;
  if (deterministic || File::GetUserPath(D_WIIROOT_IDX) != g_user_directory + "/Wii/")
  {
    g_wiimmfi_nand_stage = -3;
    return false;
  }
  g_wiimmfi_nand_stage = 2;
  return true;
}

extern "C" void neostation_dolphin_wiimmfi_observe_ios_identity(bool personal)
{
  if (neostation_dolphin_wiimmfi_network_allowed())
    g_wiimmfi_nand_stage = personal &&
        File::GetUserPath(D_SESSION_WIIROOT_IDX) == g_user_directory + "/Wii/" ? 3 : -4;
}
