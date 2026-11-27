// SPDX-License-Identifier: GPL-2.0-or-later
// Owned C ABI: the frontend never reaches through to Dolphin C++ exports.
#include "DiscIO/NANDImporter.h"
#include "Common/IOFile.h"
#include <stdexcept>

namespace
{
std::atomic<bool> g_wiimmfi_cancel{false};
std::atomic<int> g_wiimmfi_progress{0}; // reading 0..100, extracting 1000..1100

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
  for (const char* name : {"clientca.pem", "clientcakey.pem", "rootca.pem"})
  {
    File::IOFile certificate(root + "/" + name, "rb");
    if (certificate.GetSize() < 32 || certificate.GetSize() > 64 * 1024) return false;
  }
  return File::IsDirectory(root + "/title") && File::IsDirectory(root + "/shared2");
}
}

extern "C" __attribute__((visibility("default")))
int32_t neostation_dolphin_wiimmfi_abi() { return 2; }

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
int32_t neostation_dolphin_wiimmfi_import_progress() { return g_wiimmfi_progress.load(); }

extern "C" __attribute__((visibility("default")))
void neostation_dolphin_wiimmfi_cancel_import() { g_wiimmfi_cancel = true; }

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
  if (enabled && (!g_initialized || !DOLWiimmfiNANDReady(g_user_directory + "/Wii"))) return 0;
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
}
