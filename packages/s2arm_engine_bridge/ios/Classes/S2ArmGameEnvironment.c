// What a launch does with one environment variable of a game's settings profile. See S2ArmGameEnvironment.h.
#include "S2ArmGameEnvironment.h"

#include <string.h>

s2arm_game_env_action s2arm_game_env_decide(const char *current, const char *mine, const char *wanted) {
  int ours = current && mine && strcmp(current, mine) == 0;
  if (!wanted) return ours ? S2ARM_GAME_ENV_UNSET : S2ARM_GAME_ENV_KEEP;
  if (!current) return S2ARM_GAME_ENV_SET;
  return ours ? S2ARM_GAME_ENV_REPLACE : S2ARM_GAME_ENV_KEEP;
}
