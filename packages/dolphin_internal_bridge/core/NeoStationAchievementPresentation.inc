// SPDX-License-Identifier: GPL-2.0-or-later
// Presentation only. The callback copies its inputs synchronously and never
// waits for translation or changes rc_client award/authentication state.
#include <cstdint>
#include <mutex>
using DOLAchievementPresenter = void (*)(uint64_t, uint32_t, const char*, const char*,
                                        uint32_t, const char*, int);
namespace {
std::mutex g_achievement_presenter_mutex;
DOLAchievementPresenter g_achievement_presenter = nullptr;
uint64_t g_achievement_presenter_session = 0;
}
extern "C" __attribute__((visibility("default")))
void neostation_dolphin_set_achievement_presenter(DOLAchievementPresenter presenter, uint64_t session)
{
  std::lock_guard<std::mutex> lock(g_achievement_presenter_mutex);
  g_achievement_presenter = presenter;
  g_achievement_presenter_session = session;
}
extern "C" __attribute__((visibility("default")))
bool neostation_dolphin_present_achievement(uint32_t id, const char* title, const char* description,
                                           uint32_t points, const char* progress, int kind)
{
  DOLAchievementPresenter presenter;
  uint64_t session;
  {
    std::lock_guard<std::mutex> lock(g_achievement_presenter_mutex);
    presenter = g_achievement_presenter;
    session = g_achievement_presenter_session;
  }
  if (!presenter) return false;
  presenter(session, id, title, description, points, progress, kind);
  return true;
}
