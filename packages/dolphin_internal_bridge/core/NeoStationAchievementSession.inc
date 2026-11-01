// SPDX-License-Identifier: GPL-2.0-or-later
// This configuration belongs to one launch. Only the host's consumed central
// snapshot may populate it; disk preferences are never an account authority.
namespace
{
struct DOLAchievementConfiguration
{
  bool enabled = false;
  bool hardcore = false;
  bool notifications = false;
  std::string username;
  std::string token;
};

struct DOLAchievementRuntimeState
{
  bool active = false;
  bool game_loaded = false;
  bool hardcore_active = false;
  int login_error = 0;
};

DOLAchievementConfiguration g_achievement_configuration;
std::atomic<int> g_achievement_login_error{0};

bool DOLHardcoreModeActive()
{
#ifdef USE_RETRO_ACHIEVEMENTS
  auto& achievements = AchievementManager::GetInstance();
  std::lock_guard lock(achievements.GetLock());
  return achievements.GetClient() && achievements.IsHardcoreModeActive();
#else
  return false;
#endif
}

bool DOLHardcorePolicyBlocksUnsafeActions()
{
  // Keep restrictions from launch through login/game identification failures.
  // This is policy enforcement, never a claim that Hardcore awards are active.
  return (g_achievement_configuration.enabled && g_achievement_configuration.hardcore) ||
      DOLHardcoreModeActive();
}

void DOLApplyAchievementConfiguration()
{
#ifdef USE_RETRO_ACHIEVEMENTS
  const auto& session = g_achievement_configuration;
  DOLSetAchievementNotifications(session.enabled && session.notifications);
  // CurrentRun outranks the base/game INIs and has no persistent loader. The
  // upstream login callback also writes only to CurrentRun in this build.
  Config::ConfigChangeCallbackGuard guard;
  Config::SetCurrent(Config::RA_ENABLED, session.enabled);
  // Never send the central token to a host inherited from a legacy/imported INI.
  // Nonempty makes Init explicitly reset rcheevos' host even after a prior client.
  Config::SetCurrent(Config::RA_HOST_URL, std::string("https://retroachievements.org"));
  Config::SetCurrent(Config::RA_USERNAME, session.username);
  Config::SetCurrent(Config::RA_API_TOKEN, session.token);
  Config::SetCurrent(Config::RA_HARDCORE_ENABLED, session.hardcore);
  Config::SetCurrent(Config::RA_PROGRESS_ENABLED, session.notifications);
  if (session.enabled)
  {
    // RA's Dolphin support requires single-core execution in both modes.
    // This override is temporary and cannot be undone by the game's INI.
    Config::SetCurrent(Config::MAIN_CPU_THREAD, false);
  }
  if (session.hardcore)
  {
    const float speed = Config::Get(Config::MAIN_EMULATION_SPEED);
    Config::SetCurrent(Config::MAIN_EMULATION_SPEED, speed < 1.0f ? 1.0f : speed);
    Config::SetCurrent(Config::FREE_LOOK_ENABLED, false);
    Config::SetCurrent(Config::MAIN_ENABLE_CHEATS, false);
  }
#else
  DOLSetAchievementNotifications(false);
#endif
}

void DOLClearAchievementOverrides()
{
#ifdef USE_RETRO_ACHIEVEMENTS
  Config::ConfigChangeCallbackGuard guard;
  // BootManager normally clears these. A launch rejected before BootCore must
  // also release only our policy overrides, preserving the user's base values.
  if (g_achievement_configuration.enabled)
    Config::DeleteKey(Config::LayerType::CurrentRun, Config::MAIN_CPU_THREAD);
  if (g_achievement_configuration.hardcore)
  {
    Config::DeleteKey(Config::LayerType::CurrentRun, Config::MAIN_EMULATION_SPEED);
    Config::DeleteKey(Config::LayerType::CurrentRun, Config::FREE_LOOK_ENABLED);
    Config::DeleteKey(Config::LayerType::CurrentRun, Config::MAIN_ENABLE_CHEATS);
  }
#endif
}

void DOLConfigureAchievementSession(int32_t enabled, int32_t hardcore, int32_t notifications,
                                    const char* username, const char* token)
{
#ifdef USE_RETRO_ACHIEVEMENTS
  auto& achievements = AchievementManager::GetInstance();
  // A fresh launch cannot inherit a previous user's client or in-flight login.
  // Stop/restart ownership is enforced by the public C entry point's guards.
  achievements.SetUpdateCallback({});
  achievements.Shutdown();
#endif
  DOLClearAchievementOverrides();
  DOLAchievementConfiguration session;
  const std::string user = username ? username : "";
  const std::string api_token = token ? token : "";
  const bool valid_flags = (enabled == 0 || enabled == 1) &&
      (hardcore == 0 || hardcore == 1) && (notifications == 0 || notifications == 1);
  session.enabled = valid_flags && enabled == 1 && !user.empty() && user.size() <= 256 &&
      !api_token.empty() && api_token.size() <= 4096;
  if (session.enabled)
  {
    session.username = user;
    session.token = api_token;
    session.hardcore = hardcore == 1;
    session.notifications = notifications == 1;
  }
  g_achievement_configuration = std::move(session);
  g_achievement_login_error = 0;
  DOLApplyAchievementConfiguration();
#ifdef USE_RETRO_ACHIEVEMENTS
  if (g_achievement_configuration.enabled)
  {
    achievements.SetUpdateCallback([](const AchievementManager::UpdatedItems& update) {
      if (update.failed_login_code)
        g_achievement_login_error = update.failed_login_code;
    });
    // Keep Dolphin's native token login, hashing and award implementation.
    achievements.Init(nullptr);
  }
#endif
}

void DOLClearAchievementSession()
{
#ifdef USE_RETRO_ACHIEVEMENTS
  auto& achievements = AchievementManager::GetInstance();
  achievements.SetUpdateCallback({});
  achievements.Shutdown();
#endif
  DOLClearAchievementOverrides();
  g_achievement_configuration = {};
  g_achievement_login_error = 0;
  DOLApplyAchievementConfiguration();
}

DOLAchievementRuntimeState DOLReadAchievementRuntimeState()
{
  DOLAchievementRuntimeState state;
#ifdef USE_RETRO_ACHIEVEMENTS
  auto& achievements = AchievementManager::GetInstance();
  std::lock_guard lock(achievements.GetLock());
  auto* client = achievements.GetClient();
  const bool authenticated = g_achievement_configuration.enabled && client &&
      rc_client_get_user_info(client) != nullptr;
  state.game_loaded = authenticated && achievements.IsGameLoaded();
  // A signed-in account is not a recognized/usable achievement set.
  state.active = state.game_loaded && rc_client_is_processing_required(client);
  state.hardcore_active = state.active && achievements.IsHardcoreModeActive();
  state.login_error = authenticated ? 0 : g_achievement_login_error.load();
#endif
  return state;
}
}  // namespace
