// SPDX-License-Identifier: GPL-3.0-or-later
#pragma once
#include "ARMSX2CoreABI.h"
#include "common/SettingsInterface.h"
#include <algorithm>
#include <cstring>
#include <cmath>
#include <functional>
#include <utility>
#include <string>

// Owned by one prepare/boot/shutdown transaction. Never reload credentials from
// disk after this copy; the application owns account selection and migration.
struct ARMSX2RALaunchPolicy {
  bool enabled = false;
  bool hardcore = false;
  bool notifications = false;
  std::string username;
  std::string token;

  static ARMSX2RALaunchPolicy Copy(const NeoARMSX2RALaunchConfiguration* source) {
    ARMSX2RALaunchPolicy policy;
    if (!source || source->size < sizeof(*source) || source->enabled != 1 ||
        source->hardcore > 1 || source->notifications > 1 ||
        !source->username || !source->token) return policy;
    const size_t user_size = strnlen(source->username, 257);
    const size_t token_size = strnlen(source->token, 4097);
    if (user_size == 0 || user_size > 256 || token_size == 0 || token_size > 4096)
      return policy;
    policy.enabled = true;
    policy.hardcore = source->hardcore != 0;
    policy.notifications = source->notifications != 0;
    policy.username.assign(source->username, user_size);
    policy.token.assign(source->token, token_size);
    return policy;
  }

  bool HardcoreGuard() const { return enabled && hardcore; }

  void Clear() {
    std::fill(token.begin(), token.end(), '\0');
    token.clear(); username.clear();
    enabled = hardcore = notifications = false;
  }
};

// Adapt the engine's existing settings interfaces. Only the launch-owned RA
// keys are overlaid; unrelated reads/writes and persistence keep their original
// INI path. The base and secrets files retain their legacy bytes for migration.
// A separate top-priority instance prevents per-game INIs overriding the policy.
class ARMSX2RALaunchSettings final : public SettingsInterface {
public:
  enum class Scope { Base, Secrets, Launch };
  using LowerLayers = std::function<std::vector<SettingsInterface*>()>;
  ARMSX2RALaunchSettings(SettingsInterface* backing, const ARMSX2RALaunchPolicy& policy, Scope scope,
                        LowerLayers lower_layers = {})
      : m_backing(backing), m_policy(policy), m_scope(scope), m_lower_layers(std::move(lower_layers)) {}

  bool Save(Error* error = nullptr) override { return m_backing ? m_backing->Save(error) : true; }
  void Clear() override {
    if (!m_backing) return;
    const auto preserved = m_backing->GetKeyValueList("Achievements");
    m_backing->Clear();
    for (const auto& [key, value] : preserved)
      if (Owned("Achievements", key.c_str())) m_backing->SetStringValue("Achievements", key.c_str(), value.c_str());
  }
  bool IsEmpty() override { return false; }

  bool GetBoolValue(const char* section, const char* key, bool* value) const override {
    if (HardcoreSetting(section, key)) { *value = false; return true; }
    if (m_scope != Scope::Secrets && AchievementSection(section)) {
      if (std::strcmp(key, "Enabled") == 0) { *value = m_policy.enabled; return true; }
      if (std::strcmp(key, "ChallengeMode") == 0) { *value = m_policy.hardcore; return true; }
    }
    return !Owned(section, key) && m_backing && m_backing->GetBoolValue(section, key, value);
  }
  bool GetStringValue(const char* section, const char* key, std::string* value) const override {
    if (AchievementSection(section)) {
      if (std::strcmp(key, "Token") == 0) {
        // Suppress upstream's legacy base-INI token migration. Actual token
        // authentication reads the secrets/top-priority layer below.
        *value = m_scope == Scope::Base ? "" : m_policy.token;
        return true;
      }
      if (m_scope != Scope::Secrets && std::strcmp(key, "Username") == 0) {
        *value = m_policy.username; return true;
      }
      if (m_scope != Scope::Secrets && std::strcmp(key, "Host") == 0) {
        // A legacy custom endpoint must never receive the central RA token.
        // Empty selects the native client's official default service.
        value->clear(); return true;
      }
    }
    return !Owned(section, key) && m_backing && m_backing->GetStringValue(section, key, value);
  }
  bool GetStringValue(const char* section, const char* key, SmallStringBase* value) const override {
    if (Owned(section, key)) {
      std::string text;
      if (!GetStringValue(section, key, &text)) return false;
      value->assign(text); return true;
    }
    return m_backing && m_backing->GetStringValue(section, key, value);
  }

#define RBRA_FORWARD_VALUE(Type, Name) \
  bool Get##Name##Value(const char* s, const char* k, Type* value) const override { \
    return !Owned(s, k) && m_backing && m_backing->Get##Name##Value(s, k, value); \
  } \
  void Set##Name##Value(const char* s, const char* k, Type value) override { \
    if (!Owned(s, k) && m_backing) m_backing->Set##Name##Value(s, k, value); \
  }
  RBRA_FORWARD_VALUE(double, Double)
#undef RBRA_FORWARD_VALUE

  bool GetIntValue(const char* s, const char* k, int* value) const override {
    if (HardcoreSetting(s, k) && std::strcmp(s, "EmuCore/Speedhacks") == 0) {
      int configured = 0;
      ReadLower(s, k, &configured, &SettingsInterface::GetIntValue);
      *value = std::strcmp(k, "EECycleSkip") == 0 ? 0 : std::max(configured, 0);
      return true;
    }
    return !Owned(s, k) && m_backing && m_backing->GetIntValue(s, k, value);
  }
  bool GetUIntValue(const char* s, const char* k, uint* value) const override {
    if (HardcoreSetting(s, k) && std::strcmp(s, "EmuCore/Speedhacks") == 0) {
      int safe = 0; GetIntValue(s, k, &safe); *value = static_cast<uint>(safe); return true;
    }
    return !Owned(s, k) && m_backing && m_backing->GetUIntValue(s, k, value);
  }
  bool GetFloatValue(const char* s, const char* k, float* value) const override {
    if (HardcoreSetting(s, k)) {
      if (std::strcmp(s, "Framerate") == 0) {
        float configured = std::strcmp(k, "TurboScalar") == 0 ? 2.0f : 1.0f;
        ReadLower(s, k, &configured, &SettingsInterface::GetFloatValue);
        *value = std::isfinite(configured) ? std::max(configured, 1.0f) : 1.0f;
        return true;
      }
      if (std::strcmp(s, "EmuCore/GS") == 0) {
        // Pinned Pcsx2Config::GSOptions defaults, also used by native Hardcore.
        *value = std::strcmp(k, "FramerateNTSC") == 0 ? 59.94f : 50.0f; return true;
      }
    }
    return !Owned(s, k) && m_backing && m_backing->GetFloatValue(s, k, value);
  }
  void SetIntValue(const char* s, const char* k, int value) override {
    if (!Owned(s, k) && m_backing) m_backing->SetIntValue(s, k, value);
  }
  void SetUIntValue(const char* s, const char* k, uint value) override {
    if (!Owned(s, k) && m_backing) m_backing->SetUIntValue(s, k, value);
  }
  void SetFloatValue(const char* s, const char* k, float value) override {
    if (!Owned(s, k) && m_backing) m_backing->SetFloatValue(s, k, value);
  }

  void SetBoolValue(const char* s, const char* k, bool value) override {
    if (!Owned(s, k) && m_backing) m_backing->SetBoolValue(s, k, value);
  }
  void SetStringValue(const char* s, const char* k, const char* value) override {
    if (!Owned(s, k) && m_backing) m_backing->SetStringValue(s, k, value);
  }
  bool ContainsValue(const char* s, const char* k) const override {
    return Owned(s, k) || (m_backing && m_backing->ContainsValue(s, k));
  }
  void DeleteValue(const char* s, const char* k) override {
    if (!Owned(s, k) && m_backing) m_backing->DeleteValue(s, k);
  }
  void ClearSection(const char* section) override { ReplaceSection(section, {}); }
  void RemoveSection(const char* section) override {
    if (AchievementSection(section)) ReplaceSection(section, {});
    else if (m_backing) m_backing->RemoveSection(section);
  }
  void RemoveEmptySections() override { if (m_backing) m_backing->RemoveEmptySections(); }
  std::vector<std::string> GetStringList(const char* s, const char* k) const override {
    return !Owned(s, k) && m_backing ? m_backing->GetStringList(s, k) : std::vector<std::string>{};
  }
  void SetStringList(const char* s, const char* k, const std::vector<std::string>& items) override {
    if (!Owned(s, k) && m_backing) m_backing->SetStringList(s, k, items);
  }
  bool RemoveFromStringList(const char* s, const char* k, const char* item) override {
    return !Owned(s, k) && m_backing && m_backing->RemoveFromStringList(s, k, item);
  }
  bool AddToStringList(const char* s, const char* k, const char* item) override {
    return !Owned(s, k) && m_backing && m_backing->AddToStringList(s, k, item);
  }
  std::vector<std::pair<std::string, std::string>> GetKeyValueList(const char* section) const override {
    auto values = m_backing ? m_backing->GetKeyValueList(section) : std::vector<std::pair<std::string, std::string>>{};
    // This API is used for configuration editing, never authentication. Do not
    // reveal either the launch token or the legacy token through an enumeration.
    std::erase_if(values, [&](const auto& item) { return Owned(section, item.first.c_str()); });
    return values;
  }
  void SetKeyValueList(const char* section, const std::vector<std::pair<std::string, std::string>>& values) override {
    ReplaceSection(section, values);
  }

private:
  static bool AchievementSection(const char* section) { return std::strcmp(section, "Achievements") == 0; }
  bool HardcoreSetting(const char* s, const char* k) const {
    if (m_scope == Scope::Secrets || !m_policy.HardcoreGuard()) return false;
    if (std::strcmp(s, "EmuCore") == 0)
      return std::strcmp(k, "EnableCheats") == 0 || std::strcmp(k, "EnableRecordingTools") == 0;
    if (std::strcmp(s, "PINE") == 0) return std::strcmp(k, "Enabled") == 0;
    if (std::strcmp(s, "Framerate") == 0)
      return std::strcmp(k, "NominalScalar") == 0 || std::strcmp(k, "TurboScalar") == 0 ||
          std::strcmp(k, "SlomoScalar") == 0;
    if (std::strcmp(s, "EmuCore/GS") == 0)
      return std::strcmp(k, "FramerateNTSC") == 0 || std::strcmp(k, "FrameratePAL") == 0;
    if (std::strcmp(s, "EmuCore/Speedhacks") == 0)
      return std::strcmp(k, "EECycleRate") == 0 || std::strcmp(k, "EECycleSkip") == 0;
    return false;
  }
  template<typename T>
  bool ReadLower(const char* s, const char* k, T* value,
                 bool (SettingsInterface::*read)(const char*, const char*, T*) const) const {
    if (m_backing && (m_backing->*read)(s, k, value)) return true;
    if (m_lower_layers)
      for (SettingsInterface* layer : m_lower_layers())
        if (layer && (layer->*read)(s, k, value)) return true;
    return false;
  }
  bool Owned(const char* section, const char* key) const {
    if (HardcoreSetting(section, key)) return true;
    if (!AchievementSection(section)) return false;
    if (std::strcmp(key, "Token") == 0) return true;
    return m_scope != Scope::Secrets &&
        (std::strcmp(key, "Username") == 0 || std::strcmp(key, "Host") == 0 ||
         std::strcmp(key, "Enabled") == 0 || std::strcmp(key, "ChallengeMode") == 0);
  }
  void ReplaceSection(const char* section, const std::vector<std::pair<std::string, std::string>>& incoming) {
    if (!m_backing) return;
    auto values = incoming;
    std::erase_if(values, [&](const auto& item) { return Owned(section, item.first.c_str()); });
    for (const auto& item : m_backing->GetKeyValueList(section))
      if (Owned(section, item.first.c_str())) values.push_back(item);
    m_backing->SetKeyValueList(section, values);
  }
  SettingsInterface* const m_backing;
  const ARMSX2RALaunchPolicy& m_policy;
  const Scope m_scope;
  const LowerLayers m_lower_layers;
};
