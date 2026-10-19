// SPDX-License-Identifier: GPL-3.0-or-later
// HD replacement textures of the pinned ARMSX2 2.6 engine (Build 485, ABI 8).
//
// The engine already implements them (pcsx2/GS/Renderers/HW/GSTextureReplacements.cpp):
// with EmuCore/GS LoadTextureReplacements on, ReloadReplacementMap() indexes
// EmuFolders::Textures/<disc serial>/replacements by file name, the texture cache
// looks textures up by hash, a worker thread decodes them (LoadTextureReplacementsAsync,
// upstream default on) and ProcessAsyncLoadedTextures() uploads at most 16 MB per
// frame into a cache bounded by os_proc_available_memory()/2 on iOS, evicting the
// least recently used. GSUpdateConfig -> GSTextureReplacements::UpdateConfig starts or
// clears all of it when the option changes, so a change applies to the running game.
//
// This adapter only exposes it: the per-game INI key through the upstream accessors,
// the counts the engine itself reports, and the engine's own .tar.zst decoder
// (TexturePackZstd/TexturePackTar/TexturePackPaths) for packs imported in a game.
// NeoStation never preloads a whole pack (PrecacheTextureReplacements stays off).
// Included inside ARMSX2Core.mm's anonymous namespace: the engine headers it uses
// (MTGS, GS, GSDevice, GSRenderer, GSTextureReplacements, IOS/TexturePack*, os/proc)
// are included at the top of ARMSX2Core.mm, outside it.

struct TextureBootPreferences {
  std::mutex mutex;
  std::map<std::string, bool> games;  // disc serial -> NeoStation's choice for that game
};
TextureBootPreferences& texture_boot_preferences() {
  static TextureBootPreferences* value = new TextureBootPreferences;
  return *value;
}

// The running game's INI (gamesettings/<serial>_<crc>.ini), written by the upstream
// per-game writer, which also queues the native per-game reload.
void write_texture_choice(bool enabled) {
  [ARMSX2Bridge setPerGameINIBool:@"EmuCore/GS" key:@"LoadTextureReplacements" value:enabled ? YES : NO forISO:nil];
  if (enabled) {
    // Decode on the engine's worker thread and never preload the whole pack:
    // the per-frame upload bound and the memory budget keep applying.
    [ARMSX2Bridge setPerGameINIBool:@"EmuCore/GS" key:@"LoadTextureReplacementsAsync" value:YES forISO:nil];
    [ARMSX2Bridge setPerGameINIBool:@"EmuCore/GS" key:@"PrecacheTextureReplacements" value:NO forISO:nil];
  }
}

int set_texture_boot_preferences(const char* json, char* error, size_t capacity) {
  if (!json) return error_out("invalid", error, capacity);
  std::map<std::string, bool> games;
  @autoreleasepool {
    NSData* data = [NSData dataWithBytes:json length:strlen(json)];
    id decoded = [NSJSONSerialization JSONObjectWithData:data options:0 error:nil];
    NSDictionary* entries = [decoded isKindOfClass:NSDictionary.class] ? decoded[@"games"] : nil;
    if (![entries isKindOfClass:NSDictionary.class]) return error_out("invalid", error, capacity);
    for (id key in entries) {
      id value = entries[key];
      if (![key isKindOfClass:NSString.class] || [key length] == 0 || [key length] > 32 ||
          ![value isKindOfClass:NSNumber.class])
        return error_out("invalid", error, capacity);
      games[[key UTF8String]] = [value boolValue];
    }
  }
  auto& preferences = texture_boot_preferences();
  std::lock_guard lock(preferences.mutex);
  preferences.games = std::move(games);
  return 1;
}

// CPU thread, after VMManager::Initialize identified the disc and before the first
// frame: a choice made in NeoStation's library (where the game's CRC, hence its INI
// name, is unknown) becomes this game's INI value, then the settings are applied.
void apply_texture_boot_preference() {
  if (runtime().kind != NEO_ARMSX2_BOOT_DISC || !VMManager::HasValidVM()) return;
  const std::string serial = VMManager::GetDiscSerial();
  bool enabled = false;
  {
    auto& preferences = texture_boot_preferences();
    std::lock_guard lock(preferences.mutex);
    const auto found = preferences.games.find(serial);
    if (serial.empty() || found == preferences.games.end()) return;
    enabled = found->second;
  }
  @autoreleasepool {
    if (![ARMSX2Bridge perGameIdentityKeyForCurrentGame].length) return;
    NSNumber* current = [ARMSX2Bridge perGameINIBoolIfPresent:@"EmuCore/GS" key:@"LoadTextureReplacements" forISO:nil];
    NSNumber* precache = [ARMSX2Bridge perGameINIBoolIfPresent:@"EmuCore/GS" key:@"PrecacheTextureReplacements" forISO:nil];
    if (current && current.boolValue == enabled && (!enabled || (precache && !precache.boolValue))) return;
    write_texture_choice(enabled);
    VMManager::ReloadGameSettings();
    if (MTGS::IsOpen()) MTGS::ApplySettings();
  }
}

int get_texture_replacements_json(char* output, size_t capacity) {
  if (!output || capacity < 2 || !has_running_game()) return 0;
  NSData* encoded = nil;
  Host::RunOnCPUThread([&] {
    @autoreleasepool {
      const BOOL available = VMManager::HasValidVM() && runtime().kind == NEO_ARMSX2_BOOT_DISC &&
          [ARMSX2Bridge perGameIdentityKeyForCurrentGame].length > 0;
      NSMutableDictionary* state = [NSMutableDictionary dictionary];
      state[@"available"] = @(available);
      if (available) {
        NSNumber* game = [ARMSX2Bridge perGameINIBoolIfPresent:@"EmuCore/GS" key:@"LoadTextureReplacements" forISO:nil];
        state[@"serial"] = [NSString stringWithUTF8String:VMManager::GetDiscSerial().c_str()] ?: @"";
        state[@"crc"] = [NSString stringWithFormat:@"%08X", VMManager::GetDiscCRC()];
        state[@"version"] = [NSString stringWithUTF8String:VMManager::GetDiscVersion().c_str()] ?: @"";
        state[@"title"] = [NSString stringWithUTF8String:VMManager::GetTitle(true).c_str()] ?: @"";
        state[@"game"] = game ? @(game.boolValue ? 1 : 0) : @(-1);
        state[@"global"] = @([ARMSX2Bridge getINIBool:@"EmuCore/GS" key:@"LoadTextureReplacements" defaultValue:NO]);
        state[@"effective"] = @(EmuConfig.GS.LoadTextureReplacements ? YES : NO);
        state[@"async"] = @(EmuConfig.GS.LoadTextureReplacementsAsync ? YES : NO);
        state[@"precache"] = @(EmuConfig.GS.PrecacheTextureReplacements ? YES : NO);
        if (MTGS::IsOpen()) {
          bool hardware = false, dxt = false, bptc = false, astc = false, hit = false;
          u32 indexed = 0, loaded = 0;
          u64 bytes = 0, budget = 0;
          // The replacement map and the device belong to the GS thread.
          MTGS::RunOnGSThread([&] {
            hardware = GSIsHardwareRenderer();
            if (g_gs_device) {
              const GSDevice::FeatureSupport features = g_gs_device->Features();
              dxt = features.dxt_textures; bptc = features.bptc_textures; astc = features.astc_textures;
            }
            indexed = GSTextureReplacements::GetIndexedReplacementCount();
            loaded = GSTextureReplacements::GetLoadedTextureCount();
            GSTextureReplacements::GetReplacementCacheUsage(&bytes, &budget, &hit);
          });
          MTGS::WaitGS(false);
          state[@"hardware"] = @(hardware);
          state[@"indexed"] = @(indexed);
          state[@"loaded"] = @(loaded);
          state[@"cacheBytes"] = @(bytes);
          state[@"budgetBytes"] = @(budget);
          state[@"budgetReached"] = @(hit);
          state[@"bcTextures"] = @(dxt && bptc);
          state[@"astcTextures"] = @(astc);
        }
        state[@"availableMemory"] = @((unsigned long long)os_proc_available_memory());
      }
      // The core is MRC; retain bytes across the CPU thread's autorelease pool.
      encoded = [[NSJSONSerialization dataWithJSONObject:state options:0 error:nil] retain];
    }
  }, true);
  if (!encoded) return 0;
  const BOOL fits = encoded.length + 1 <= capacity;
  if (fits) { memcpy(output, encoded.bytes, encoded.length); output[encoded.length] = 0; }
  [encoded release];
  return fits ? 1 : 0;
}

int set_texture_replacements(int enabled, char* error, size_t capacity) {
  if (enabled != 0 && enabled != 1) return error_out("invalid", error, capacity);
  if (!has_running_game()) return error_out("noSession", error, capacity);
  BOOL success = NO;
  Host::RunOnCPUThread([&] {
    @autoreleasepool {
      if (!VMManager::HasValidVM() || runtime().kind != NEO_ARMSX2_BOOT_DISC ||
          ![ARMSX2Bridge perGameIdentityKeyForCurrentGame].length) return;
      write_texture_choice(enabled != 0);
      // Applied now on this thread (the writer's own reload follows and finds no
      // change): GSUpdateConfig starts or clears the replacements for the next frames.
      VMManager::ReloadGameSettings();
      if (MTGS::IsOpen()) MTGS::ApplySettings();
      NSNumber* stored = [ARMSX2Bridge perGameINIBoolIfPresent:@"EmuCore/GS" key:@"LoadTextureReplacements" forISO:nil];
      success = stored && stored.boolValue == (enabled != 0) && EmuConfig.GS.LoadTextureReplacements == (enabled != 0);
    }
  }, true);
  return success ? 1 : error_out("write", error, capacity);
}

// After NeoStation replaced or removed the files of the running game's pack.
int reload_texture_replacements(char* error, size_t capacity) {
  if (!has_running_game()) return error_out("noSession", error, capacity);
  BOOL reloaded = NO;
  Host::RunOnCPUThread([&] {
    if (!VMManager::HasValidVM() || !MTGS::IsOpen()) return;
    MTGS::RunOnGSThread([] {
      if (!g_gs_renderer) return;
      GSTextureReplacements::ReloadReplacementMap();
      g_gs_renderer->PurgeTextureCache(true, false, true);
    });
    MTGS::WaitGS(false);
    reloaded = YES;
  }, true);
  return reloaded ? 1 : error_out("noSession", error, capacity);
}

// The .tar.zst profile ARMSX2 packs ship in, decoded by the engine's own streaming
// reader (one decoder buffer at a time). Only texture entries are written, below
// [destination] under their archive path rebuilt from its checked parts, so the
// host can apply the same serial-folder rules as for any folder. error keys:
// unreadable, invalid, unsafe, entries, fileTooLarge, space, write, cancelled.
int expand_texture_archive(const char* archive_path, const char* destination, uint64_t available,
                           const volatile int* cancel, volatile uint64_t* consumed, char* error, size_t capacity) {
  if (!archive_path || !destination || archive_path[0] != '/' || destination[0] != '/')
    return error_out("invalid", error, capacity);
  constexpr uint64_t kMaxEntries = 100000, kMaxFile = 512ull * 1024 * 1024, kSpare = 512ull * 1024 * 1024;
  auto fp = FileSystem::OpenManagedCFile(archive_path, "rb");
  if (!fp) return error_out("unreadable", error, capacity);
  TexturePackZstd zstd(fp.get());
  if (!zstd.Valid()) return error_out("unreadable", error, capacity);
  std::string reason;
  uint64_t entries = 0, written = 0;
  std::vector<char> chunk(256 * 1024);
  const auto read = [&](void* buffer, size_t n) { return zstd.Read(buffer, n); };
  const bool ok = TexturePackTar::Read(read, [&](const std::string& name, uint64_t size) {
    if (++entries > kMaxEntries) { reason = "entries"; return false; }
    if (cancel && *cancel) { reason = "cancelled"; return false; }
    const TexturePackPaths::Entry entry = TexturePackPaths::Classify(name);
    if (entry.kind == TexturePackPaths::Kind::Unsafe) { reason = "unsafe"; return false; }
    std::FILE* file = nullptr;
    if (entry.kind == TexturePackPaths::Kind::Texture) {
      if (size > kMaxFile) { reason = "fileTooLarge"; return false; }
      std::string relative;
      for (const std::string& part : TexturePackPaths::Split(name)) relative += (relative.empty() ? "" : "/") + part;
      const std::string path = Path::Combine(destination, relative);
      if (!FileSystem::CreateDirectoryPath(std::string(Path::GetDirectory(path)).c_str(), true) ||
          FileSystem::FileExists(path.c_str()) || !(file = std::fopen(path.c_str(), "wb"))) {
        reason = "write"; return false;
      }
    }
    uint64_t left = size;
    bool wrote = true;
    while (left > 0) {
      const size_t n = static_cast<size_t>(std::min<uint64_t>(left, chunk.size()));
      if (!read(chunk.data(), n)) break;
      if (file) {
        written += n;
        if (written > available || available - written < kSpare) { reason = "space"; wrote = false; break; }
        wrote = wrote && std::fwrite(chunk.data(), 1, n, file) == n;
      }
      left -= n;
      if (consumed) *consumed = static_cast<uint64_t>(ftello(fp.get()));
      if (cancel && *cancel) { reason = "cancelled"; wrote = false; break; }
    }
    if (file && std::fclose(file) != 0) wrote = false;
    if (!wrote && reason.empty()) reason = "write";
    return wrote && left == 0;
  }, reason);
  if (ok) return 1;
  // The upstream reader reports damage in English sentences; the host needs a key.
  static const char* keys[] = {"entries", "cancelled", "unsafe", "fileTooLarge", "write", "space"};
  for (const char* key : keys) if (reason == key) return error_out(key, error, capacity);
  return error_out("invalid", error, capacity);
}
