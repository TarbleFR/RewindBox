#!/usr/bin/env python3
"""Compile and exercise the production RA settings adapter against a small
SettingsInterface boundary fixture. This is not an iOS/Core compilation or a
network authentication test. Native CI must also rebuild the pinned Core.
"""
from pathlib import Path
import os
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
CORE = ROOT/'packages/armsx2_internal_bridge/core'
ABI = ROOT/'packages/armsx2_internal_bridge/ios/Classes'

# Same virtual boundary as pinned pcsx2/common SettingsInterface. Backing INI I/O
# is replaced by a recording store so credentials cannot reach the filesystem.
INTERFACE = r'''
#pragma once
#include <string>
#include <vector>
#include <utility>
using uint = unsigned int;
class Error {};
struct SmallStringBase : std::string { using std::string::assign; };
class SettingsInterface {
public:
  virtual ~SettingsInterface() = default;
  virtual bool Save(Error* = nullptr) = 0;
  virtual void Clear() = 0;
  virtual bool IsEmpty() = 0;
#define GETSET(T, N) \
  virtual bool Get##N##Value(const char*,const char*,T*) const = 0; \
  virtual void Set##N##Value(const char*,const char*,T) = 0;
  GETSET(int,Int) GETSET(uint,UInt) GETSET(float,Float) GETSET(double,Double) GETSET(bool,Bool)
#undef GETSET
  virtual bool GetStringValue(const char*,const char*,std::string*) const = 0;
  virtual bool GetStringValue(const char*,const char*,SmallStringBase*) const = 0;
  virtual void SetStringValue(const char*,const char*,const char*) = 0;
  virtual bool ContainsValue(const char*,const char*) const = 0;
  virtual void DeleteValue(const char*,const char*) = 0;
  virtual void ClearSection(const char*) = 0;
  virtual void RemoveSection(const char*) = 0;
  virtual void RemoveEmptySections() = 0;
  virtual std::vector<std::string> GetStringList(const char*,const char*) const = 0;
  virtual void SetStringList(const char*,const char*,const std::vector<std::string>&) = 0;
  virtual bool RemoveFromStringList(const char*,const char*,const char*) = 0;
  virtual bool AddToStringList(const char*,const char*,const char*) = 0;
  virtual std::vector<std::pair<std::string,std::string>> GetKeyValueList(const char*) const = 0;
  virtual void SetKeyValueList(const char*,const std::vector<std::pair<std::string,std::string>>&) = 0;
};
'''
PROGRAM = r'''
#include "ARMSX2RALaunchSettings.h"
#include <cassert>
#include <map>
#include <iostream>
class Store final : public SettingsInterface {
public:
  using Map=std::map<std::pair<std::string,std::string>,std::string>;
  Map values, persisted;
  bool Save(Error* = nullptr) override { persisted=values;return true; }
  void Clear() override { values.clear(); }
  bool IsEmpty() override { return values.empty(); }
#define NUM(T,N) \
  bool Get##N##Value(const char* s,const char* k,T* out) const override { \
    auto i=values.find({s,k});if(i==values.end())return false;*out=static_cast<T>(std::stod(i->second));return true; \
  } \
  void Set##N##Value(const char* s,const char* k,T value) override { values[{s,k}]=std::to_string(value); }
  NUM(int,Int) NUM(uint,UInt) NUM(float,Float) NUM(double,Double) NUM(bool,Bool)
#undef NUM
  bool GetStringValue(const char* s,const char* k,std::string* out) const override {
    auto i=values.find({s,k});if(i==values.end())return false;*out=i->second;return true;
  }
  bool GetStringValue(const char* s,const char* k,SmallStringBase* out) const override {
    std::string value;if(!GetStringValue(s,k,&value))return false;out->assign(value);return true;
  }
  void SetStringValue(const char* s,const char* k,const char* value) override { values[{s,k}]=value; }
  bool ContainsValue(const char* s,const char* k) const override { return values.contains({s,k}); }
  void DeleteValue(const char* s,const char* k) override { values.erase({s,k}); }
  void ClearSection(const char* s) override { std::erase_if(values,[&](const auto& v){return v.first.first==s;}); }
  void RemoveSection(const char* s) override { ClearSection(s); }
  void RemoveEmptySections() override {}
  std::vector<std::string> GetStringList(const char*,const char*) const override { return {}; }
  void SetStringList(const char*,const char*,const std::vector<std::string>&) override {}
  bool RemoveFromStringList(const char*,const char*,const char*) override { return false; }
  bool AddToStringList(const char*,const char*,const char*) override { return false; }
  std::vector<std::pair<std::string,std::string>> GetKeyValueList(const char* s) const override {
    std::vector<std::pair<std::string,std::string>> result;
    for(const auto& [key,value]:values)if(key.first==s)result.push_back({key.second,value});
    return result;
  }
  void SetKeyValueList(const char* s,const std::vector<std::pair<std::string,std::string>>& list) override {
    ClearSection(s);for(const auto& [key,value]:list)values[{s,key}]=value;
  }
};
static std::string text(const SettingsInterface& settings,const char* key) {
  std::string value;assert(settings.GetStringValue("Achievements",key,&value));return value;
}
static bool flag(const SettingsInterface& settings,const char* key) {
  bool value=false;assert(settings.GetBoolValue("Achievements",key,&value));return value;
}
int main() {
  static_assert(NEO_ARMSX2_ABI_VERSION==9);
  using Scope=ARMSX2RALaunchSettings::Scope;
  Store disk;
  disk.SetStringValue("Achievements","Username","legacy-user");
  disk.SetStringValue("Achievements","Token","legacy-token");
  disk.SetStringValue("Achievements","Host","legacy.example.invalid");
  disk.SetBoolValue("Achievements","Enabled",true);
  disk.SetBoolValue("Achievements","ChallengeMode",true);
  disk.SetIntValue("EmuCore/GS","upscale_multiplier",2);
  disk.Save();const auto original=disk.persisted;
  auto missing=ARMSX2RALaunchPolicy::Copy(nullptr);
  ARMSX2RALaunchSettings disabled(&disk,missing,Scope::Base);
  ARMSX2RALaunchSettings disabledSecrets(&disk,missing,Scope::Secrets);
  assert(!flag(disabled,"Enabled") && !flag(disabled,"ChallengeMode"));
  assert(text(disabled,"Username").empty() && text(disabled,"Token").empty());
  assert(text(disabledSecrets,"Token").empty());
  assert(disabled.Save() && disk.persisted==original);
  char username[]="central-user",token[]="central-token";
  NeoARMSX2RALaunchConfiguration config={sizeof(config),1,1,1,username,token};
  auto policy=ARMSX2RALaunchPolicy::Copy(&config);
  username[0]='X';token[0]='Y';
  assert(policy.username=="central-user" && policy.token=="central-token");
  ARMSX2RALaunchSettings base(&disk,policy,Scope::Base);
  ARMSX2RALaunchSettings secrets(&disk,policy,Scope::Secrets);
  ARMSX2RALaunchSettings launch(nullptr,policy,Scope::Launch);
  assert(flag(base,"Enabled") && flag(base,"ChallengeMode"));
  assert(text(base,"Username")=="central-user" && text(base,"Token").empty());
  assert(text(base,"Host").empty() && text(launch,"Host").empty());
  assert(text(secrets,"Token")=="central-token" && text(launch,"Token")=="central-token");
  SmallStringBase small;
  assert(secrets.GetStringValue("Achievements","Token",&small) && small=="central-token");
  base.SetBoolValue("Achievements","Enabled",false);
  base.SetStringValue("Achievements","Username","other-user");
  secrets.SetStringValue("Achievements","Token","other-token");
  secrets.DeleteValue("Achievements","Token");
  assert(flag(base,"Enabled") && text(base,"Username")=="central-user");
  assert(text(secrets,"Token")=="central-token");
  base.Save();secrets.Save();assert(disk.persisted==original);
  for(const auto& [key,value]:secrets.GetKeyValueList("Achievements")) {
    assert(key!="Token");assert(value!="central-token" && value!="legacy-token");
  }
  base.SetIntValue("EmuCore/GS","upscale_multiplier",3);
  int scale=0;assert(base.GetIntValue("EmuCore/GS","upscale_multiplier",&scale) && scale==3);
  base.Save();assert((disk.persisted.at({"Achievements","Token"})=="legacy-token"));
  config.enabled=0;assert(!ARMSX2RALaunchPolicy::Copy(&config).enabled);
  config.enabled=1;config.size=0;assert(!ARMSX2RALaunchPolicy::Copy(&config).enabled);
  config.size=sizeof(config);config.hardcore=2;assert(!ARMSX2RALaunchPolicy::Copy(&config).enabled);
  config.hardcore=1;config.token="";assert(!ARMSX2RALaunchPolicy::Copy(&config).enabled);
  std::string oversized(4097,'x');config.token=oversized.c_str();assert(!ARMSX2RALaunchPolicy::Copy(&config).enabled);
  // Protections start before authentication: a late game layer cannot re-enable
  // cheats or slow motion, while allowed acceleration/overclock is retained.
  Store game;
  game.SetBoolValue("EmuCore","EnableCheats",true);
  game.SetBoolValue("EmuCore","EnableRecordingTools",true);
  game.SetBoolValue("PINE","Enabled",true);
  game.SetFloatValue("Framerate","NominalScalar",0.25f);
  game.SetFloatValue("Framerate","TurboScalar",3.0f);
  game.SetFloatValue("Framerate","SlomoScalar",0.5f);
  game.SetFloatValue("EmuCore/GS","FramerateNTSC",30.0f);
  game.SetFloatValue("EmuCore/GS","FrameratePAL",25.0f);
  game.SetIntValue("EmuCore/Speedhacks","EECycleRate",-2);
  game.SetUIntValue("EmuCore/Speedhacks","EECycleSkip",3);
  game.Save();const auto savedGame=game.persisted;
  SettingsInterface* currentGame=&game;
  ARMSX2RALaunchSettings guarded(nullptr,policy,Scope::Launch,[&]{
    return std::vector<SettingsInterface*>{currentGame,&base};
  });
  bool enabled=true;float speed=0;int rate=0;uint skip=1;
  assert(policy.HardcoreGuard());
  assert(guarded.GetBoolValue("EmuCore","EnableCheats",&enabled) && !enabled);
  assert(guarded.GetBoolValue("EmuCore","EnableRecordingTools",&enabled) && !enabled);
  assert(guarded.GetBoolValue("PINE","Enabled",&enabled) && !enabled);
  assert(guarded.GetFloatValue("Framerate","NominalScalar",&speed) && speed==1.0f);
  assert(guarded.GetFloatValue("Framerate","SlomoScalar",&speed) && speed==1.0f);
  assert(guarded.GetFloatValue("Framerate","TurboScalar",&speed) && speed==3.0f);
  assert(guarded.GetFloatValue("EmuCore/GS","FramerateNTSC",&speed) && speed==59.94f);
  assert(guarded.GetFloatValue("EmuCore/GS","FrameratePAL",&speed) && speed==50.0f);
  assert(guarded.GetIntValue("EmuCore/Speedhacks","EECycleRate",&rate) && rate==0);
  assert(guarded.GetUIntValue("EmuCore/Speedhacks","EECycleSkip",&skip) && skip==0);
  assert(game.persisted==savedGame && game.values==savedGame);
  Store replacedGame;
  replacedGame.SetFloatValue("Framerate","NominalScalar",2.5f);
  replacedGame.SetIntValue("EmuCore/Speedhacks","EECycleRate",2);
  currentGame=&replacedGame;
  assert(guarded.GetFloatValue("Framerate","NominalScalar",&speed) && speed==2.5f);
  assert(guarded.GetIntValue("EmuCore/Speedhacks","EECycleRate",&rate) && rate==2);
  auto softcore=policy;softcore.hardcore=false;
  ARMSX2RALaunchSettings unguarded(&game,softcore,Scope::Base);
  assert(!softcore.HardcoreGuard());
  assert(unguarded.GetBoolValue("EmuCore","EnableCheats",&enabled) && enabled);
  assert(unguarded.GetFloatValue("Framerate","NominalScalar",&speed) && speed==0.25f);
  assert(unguarded.GetIntValue("EmuCore/Speedhacks","EECycleRate",&rate) && rate==-2);
  policy.Clear();assert(policy.token.empty() && !policy.enabled && !policy.hardcore);
  assert(!flag(base,"Enabled") && text(secrets,"Token").empty());
  std::cout<<"PASS: launch-only RA policy; copied credentials; disabled/invalid fail closed; legacy storage preserved; non-RA settings forwarded\n";
}
'''

def main():
    compiler=os.environ.get('CXX') or shutil.which('clang++') or shutil.which('g++')
    if not compiler:
        raise SystemExit('C++ compiler required; no checks were executed')
    with tempfile.TemporaryDirectory(prefix='armsx2-ra-policy-') as directory:
        temp=Path(directory)
        (temp/'common').mkdir()
        (temp/'common/SettingsInterface.h').write_text(INTERFACE)
        (temp/'main.cpp').write_text(PROGRAM)
        executable=temp/'check'
        subprocess.run([compiler,'-std=c++20','-Wall','-Wextra','-Werror','-pedantic',
                        '-I'+str(temp),'-I'+str(CORE),'-I'+str(ABI),
                        str(temp/'main.cpp'),'-o',str(executable)],check=True)
        subprocess.run([str(executable)],check=True,timeout=15)
    core=(CORE/'ARMSX2Core.mm').read_text()
    host=(ABI/'Armsx2InternalBridgePlugin.mm').read_text()
    assert 'LAYER_CMDLINE, r.achievement_launch.get()' in core
    assert core.index('r.achievement_base =') < core.index('VMManager::Internal::LoadStartupSettings();')
    assert core.index('r.achievements = ARMSX2RALaunchPolicy::Copy') < core.index('pthread_create(')
    assert host.index('RBRATakeLaunchConfiguration(args, @"armsx2")') < host.index('self.api->prepare(&config')
    assert 'RBRAPublishSessionState(configuration' in host and 'state[@"hardcoreActive"]' in host
    assert 'RBRAEndSession(configuration)' in host
    assert 'hardcoreGuardActive' in host and 'gameLoaded && [state[@"hasAchievements"] boolValue]' in host
    assert 'runtime().achievements.HardcoreGuard() || Achievements::IsHardcoreModeActive()' in core
    print('PASS: adapter wired before engine initialization; effective-state publication and native-session end hooks present')

if __name__=='__main__':
    main()
