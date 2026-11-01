"""Run the actual Dolphin session policy with a fake engine/config boundary.

This compiles portable C++ helpers, not UIKit or the complete iOS Core. Optional
--upstream validates the storage patch against the pinned AchievementManager.
"""
import argparse
import importlib.util
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def native_policy():
    fixture = r'''
#include <atomic>
#include <cassert>
#include <cstdint>
#include <functional>
#include <mutex>
#include <optional>
#include <string>
#include <utility>
#define USE_RETRO_ACHIEVEMENTS 1
namespace Config {
enum class LayerType { CurrentRun };
template<class T> struct Info { T base; mutable std::optional<T> current; };
Info<bool> RA_ENABLED{true, {}}, RA_HARDCORE_ENABLED{false, {}}, RA_PROGRESS_ENABLED{true, {}};
Info<bool> MAIN_CPU_THREAD{true, {}}, FREE_LOOK_ENABLED{true, {}}, MAIN_ENABLE_CHEATS{true, {}};
Info<float> MAIN_EMULATION_SPEED{1.5f, {}};
Info<std::string> RA_USERNAME{"legacy-user", {}}, RA_API_TOKEN{"legacy-token", {}};
Info<std::string> RA_HOST_URL{"https://custom.example.invalid", {}};
struct ConfigChangeCallbackGuard { ~ConfigChangeCallbackGuard() {} };
template<class T> T Get(const Info<T>& info) { return info.current.value_or(info.base); }
template<class T, class V> void SetCurrent(const Info<T>& info, const V& value) { info.current = value; }
template<class T> void DeleteKey(LayerType, const Info<T>& info) { info.current.reset(); }
}
struct Client { bool logged_in=false, game_loaded=false, hardcore=false, processing=false; };
const void* rc_client_get_user_info(Client* client) {
  return client && client->logged_in ? client : nullptr;
}
bool rc_client_is_processing_required(Client* client) { return client && client->processing; }
class AchievementManager {
public:
  struct UpdatedItems { int failed_login_code=0; };
  using Update = std::function<void(const UpdatedItems&)>;
  static AchievementManager& GetInstance() { static AchievementManager instance; return instance; }
  void SetUpdateCallback(Update callback) { update=std::move(callback); }
  void Shutdown() { client=nullptr; }
  void Init(void*) {
    assert(Config::Get(Config::RA_HOST_URL)=="https://retroachievements.org");
    ++login_attempts; storage={}; client=&storage;
  }
  Client* GetClient() { return client; }
  std::recursive_mutex& GetLock() { return mutex; }
  bool IsGameLoaded() { return client && client->game_loaded; }
  bool IsHardcoreModeActive() { return client && client->hardcore; }
  int login_attempts=0;
  Update update;
  Client storage;
private:
  Client* client=nullptr;
  std::recursive_mutex mutex;
};
PRESENTATION_INCLUDE
SESSION_INCLUDE
int main() {
  auto& manager=AchievementManager::GetInstance();
  // Credentials never enable a disabled session, including a stale disk account.
  DOLConfigureAchievementSession(0,1,1,"player","token");
  assert(!Config::Get(Config::RA_ENABLED) && manager.login_attempts==0);
  assert(Config::Get(Config::RA_USERNAME).empty() && Config::Get(Config::RA_API_TOKEN).empty());
  assert(!DOLReadAchievementRuntimeState().active);
  for (int invalid : {-1,2,17}) {
    DOLConfigureAchievementSession(invalid,1,1,"player","token");
    assert(!Config::Get(Config::RA_ENABLED) && manager.login_attempts==0);
  }
  DOLConfigureAchievementSession(1,1,1,nullptr,"token");
  assert(!Config::Get(Config::RA_ENABLED) && manager.login_attempts==0);
  DOLConfigureAchievementSession(1,1,1,"player",nullptr);
  assert(!Config::Get(Config::RA_ENABLED) && manager.login_attempts==0);

  DOLConfigureAchievementSession(1,1,1,"player","token");
  assert(manager.login_attempts==1);
  assert(Config::RA_HOST_URL.base=="https://custom.example.invalid");
  assert(Config::Get(Config::RA_ENABLED) && Config::Get(Config::RA_HARDCORE_ENABLED));
  assert(!Config::Get(Config::MAIN_CPU_THREAD) && !Config::Get(Config::MAIN_ENABLE_CHEATS));
  assert(!Config::Get(Config::FREE_LOOK_ENABLED));
  assert(Config::Get(Config::MAIN_EMULATION_SPEED)==1.5f); // fast-forward preserved
  assert(!DOLReadAchievementRuntimeState().active); // preference is not login success
  assert(DOLHardcorePolicyBlocksUnsafeActions()); // block load/cheats while login is pending
  manager.update({-7});
  assert(DOLReadAchievementRuntimeState().login_error==-7);
  assert(DOLHardcorePolicyBlocksUnsafeActions()); // failed login does not lift requested restrictions
  assert(!DOLReadAchievementRuntimeState().hardcore_active);
  manager.storage.logged_in=true;
  assert(!DOLReadAchievementRuntimeState().active); // logged-in alone is not a usable set
  assert(!DOLReadAchievementRuntimeState().game_loaded);
  manager.storage.game_loaded=true;
  assert(!DOLReadAchievementRuntimeState().active); // recognized game, no processing set yet
  manager.storage.processing=true;
  assert(DOLReadAchievementRuntimeState().active);
  assert(!DOLReadAchievementRuntimeState().hardcore_active); // native mode still false
  manager.storage.hardcore=true;
  assert(DOLReadAchievementRuntimeState().hardcore_active && DOLHardcoreModeActive());
  assert(DOLReadAchievementRuntimeState().login_error==0);

  // BootManager clears CurrentRun on restart. Reapply only this session's data.
  Config::RA_USERNAME.current.reset(); Config::RA_API_TOKEN.current.reset();
  Config::RA_ENABLED.current.reset(); Config::RA_HARDCORE_ENABLED.current.reset();
  Config::MAIN_CPU_THREAD.current.reset();
  Config::MAIN_EMULATION_SPEED.current=0.5f;
  DOLApplyAchievementConfiguration();
  assert(Config::Get(Config::RA_USERNAME)=="player" && Config::Get(Config::RA_API_TOKEN)=="token");
  assert(Config::Get(Config::RA_HARDCORE_ENABLED) && !Config::Get(Config::MAIN_CPU_THREAD));
  assert(Config::Get(Config::MAIN_EMULATION_SPEED)==1.0f);
  assert(manager.login_attempts==1); // reset does not reconnect the account
  assert(Config::RA_USERNAME.base=="legacy-user" && Config::RA_API_TOKEN.base=="legacy-token");
  assert(Config::MAIN_CPU_THREAD.base && Config::MAIN_ENABLE_CHEATS.base);

  DOLClearAchievementSession();
  assert(!manager.GetClient() && !DOLReadAchievementRuntimeState().active);
  assert(!DOLHardcorePolicyBlocksUnsafeActions());
  assert(Config::Get(Config::RA_API_TOKEN).empty() && !Config::Get(Config::RA_ENABLED));
  assert(Config::Get(Config::MAIN_CPU_THREAD) && Config::Get(Config::MAIN_ENABLE_CHEATS));
  assert(Config::Get(Config::FREE_LOOK_ENABLED) && Config::Get(Config::MAIN_EMULATION_SPEED)==1.5f);
  DOLConfigureAchievementSession(1,0,1,"second","second-token");
  assert(manager.login_attempts==2 && !Config::Get(Config::RA_HARDCORE_ENABLED));
  assert(Config::Get(Config::RA_USERNAME)=="second");
  assert(!DOLReadAchievementRuntimeState().active); // old user cannot leak into next session
  DOLClearAchievementSession();
}
'''
    include = ROOT / 'packages/dolphin_internal_bridge/core/NeoStationAchievementSession.inc'
    fixture = fixture.replace('SESSION_INCLUDE', '#include "' + str(include) + '"')
    presenter = ROOT / 'packages/dolphin_internal_bridge/core/NeoStationAchievementPresentation.inc'
    fixture = fixture.replace('PRESENTATION_INCLUDE', '#include "' + str(presenter) + '"')
    with tempfile.TemporaryDirectory(prefix='dolphin-session-') as folder:
        source = Path(folder) / 'policy.cpp'
        source.write_text(fixture)
        binary = Path(folder) / 'policy'
        compiler = os.environ.get('CXX') or shutil.which('clang++') or shutil.which('g++')
        assert compiler, 'A real C++ compiler is required'
        subprocess.run([compiler, '-std=c++17', '-Wall', '-Wextra', '-Werror',
                        '-pthread', str(source), '-o', str(binary)], check=True)
        subprocess.run([str(binary)], check=True)
    print('Dolphin session C++ policy: disabled/invalid/Hardcore/actual state/restart/account isolation passed')


def source_contracts(upstream):
    path = ROOT / 'build-utils/patch_dolphin_internal_core_v2.py'
    spec = importlib.util.spec_from_file_location('dolphin_patch', path)
    patch = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(patch)
    host = (ROOT / 'packages/dolphin_internal_bridge/ios/Classes/DolphinInternalBridgePlugin.mm').read_text()
    assert host.count('RBRATakeLaunchConfiguration(arguments, @"dolphin")') == 1
    assert '[DolphinRetroAchievementsAccount credentials]' not in host
    assert 'RBRAPublishSessionState(configuration, state)' in host
    assert 'RBRAEndSession(configuration)' in host
    assert host.count('[self endAchievementSession]') == 2
    assert host.index('neostation_dolphin_configure_achievements_session(', host.index('- (NSDictionary*)launchWithArguments:')) < host.index('int32_t launchFlags =')
    assert 'DOLReadAchievementState()[@"hardcoreEnforced"]' in host
    assert 'neostation_dolphin_configure_achievements(const char* username, const char* api_token)' in patch.BRIDGE_SOURCE
    assert 'return neostation_dolphin_configure_achievements_session(0, 0, 0, nullptr, nullptr);' in patch.BRIDGE_SOURCE
    assert 'char* neostation_dolphin_achievements_snapshot(void)' in patch.BRIDGE_SOURCE
    assert 'if (DOLHardcorePolicyBlocksUnsafeActions()) return;' in patch.BRIDGE_SOURCE
    assert patch.BRIDGE_SOURCE.count('if (requested && DOLHardcorePolicyBlocksUnsafeActions()) return;') == 2
    assert 'State::SaveAs(system, path, true)' in patch.BRIDGE_SOURCE
    assert "s.dependency 'retro_achievements_session'" in (ROOT / 'packages/dolphin_internal_bridge/ios/dolphin_internal_bridge.podspec').read_text()
    if upstream:
        original = (upstream / 'Source/Core/Core/AchievementManager.cpp').read_text()
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder) / 'Source/Core/Core/AchievementManager.cpp'
            target.parent.mkdir(parents=True)
            target.write_text(original)
            patch.patch_achievement_session_storage(Path(folder))
            first = target.read_text()
            patch.patch_achievement_session_storage(Path(folder))
            assert target.read_text() == first, 'Storage patch must be idempotent'
            expected = original.replace('Config::SetBaseOrCurrent(Config::RA_API_TOKEN,',
                                        'Config::SetCurrent(Config::RA_API_TOKEN,')
            expected = expected.replace('Config::SetBaseOrCurrent(Config::RA_USERNAME,',
                                        'Config::SetCurrent(Config::RA_USERNAME,')
            assert first == expected, 'Token login, hashes and award logic must be byte-for-byte preserved'
        print('Pinned native storage patch: applied twice; only the 3 credential destinations changed')
    print('Dolphin central launch and native guards: source contracts passed')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--upstream', type=Path)
    args = parser.parse_args()
    native_policy()
    source_contracts(args.upstream)
