#pragma once
// What a launch does with one environment variable of a game's settings profile (S2ArmSettings.m), in plain C so that
// test/s2arm_engine_bridge_test.py compiles and runs it. The engine reads these variables before their NSUserDefaults keys
// (S2Arm ios/settings.m s2a_ios_apply_graphics_settings: a variable already set is used as it is), so a game's profile
// reaches it while the global keys stay as stored. A value this bridge did not set (the launch environment, Documents/env.txt,
// the engine's own reading of the global keys at an earlier start) is never replaced; a value it set itself at an earlier
// start of this process (a parked game that resumes, patch 0010) is its own to change or remove.

typedef enum {
  S2ARM_GAME_ENV_KEEP = 0,      // left as it is
  S2ARM_GAME_ENV_SET = 1,       // not set: setenv(name, wanted, 0)
  S2ARM_GAME_ENV_REPLACE = 2,   // still the value this bridge set: setenv(name, wanted, 1)
  S2ARM_GAME_ENV_UNSET = 3,     // still the value this bridge set, and the game has no profile now: unsetenv(name)
} s2arm_game_env_action;

// current: the variable's value now (NULL: not set). mine: the value this bridge set for it earlier in this process (NULL:
// none). wanted: the game's value (NULL: the game has no profile, the engine reads its global key).
s2arm_game_env_action s2arm_game_env_decide(const char *current, const char *mine, const char *wanted);
