/* Original test-only libretro core: observes the managed PSP cheat option at
 * init/load/frame and counts actual calls. Never used as a production core. */
#include "libretro.h"
#include <stdbool.h>
#include <stdint.h>
#include <string.h>
#include <stdio.h>
static retro_environment_t environment;
static retro_video_refresh_t video;
static uint8_t report[256];
#ifdef FBNEO
#define CHEAT_KEY "fbneo-cheat-0-neotest-Synthetic"
RETRO_API char szAppCheatsPath[260];
RETRO_API bool bCheatsAllowed;
RETRO_API uint32_t nBurnDrvActive=0,nBurnDrvCount=1;
RETRO_API int CheatUpdate(void) { return 0; }
RETRO_API uint32_t BurnDrvGetHardwareCode(void) { return 0x01000000; }
static bool enabled(void) { struct retro_variable v={CHEAT_KEY,NULL};return environment(RETRO_ENVIRONMENT_GET_VARIABLE,&v)&&v.value&&strcmp(v.value,"0 - Disabled")!=0; }
RETRO_API char *BurnDrvGetTextA(uint32_t type) { return type==0?"neotest":NULL; }
#else
static bool enabled(void) { struct retro_variable v={"ppsspp_cheats",NULL};return environment(RETRO_ENVIRONMENT_GET_VARIABLE,&v)&&v.value&&strcmp(v.value,"enabled")==0; }
#endif
RETRO_API void retro_set_environment(retro_environment_t cb) {
 environment=cb;
 static const struct retro_variable vars[]={
#ifndef FBNEO
 {"ppsspp_cheats","Cheats; disabled|enabled"},
#endif
 {"other","Other; one|two"},{NULL,NULL}};
 cb(RETRO_ENVIRONMENT_SET_VARIABLES,(void*)vars);
}
RETRO_API void retro_set_video_refresh(retro_video_refresh_t cb) { video=cb; }
RETRO_API void retro_set_audio_sample(retro_audio_sample_t cb) {(void)cb;}
RETRO_API void retro_set_audio_sample_batch(retro_audio_sample_batch_t cb) {(void)cb;}
RETRO_API void retro_set_input_poll(retro_input_poll_t cb) {(void)cb;}
RETRO_API void retro_set_input_state(retro_input_state_t cb) {(void)cb;}
RETRO_API void retro_init(void) { memset(report,0,sizeof(report));report[0]=!enabled(); }
RETRO_API void retro_deinit(void) {}
RETRO_API unsigned retro_api_version(void) { return RETRO_API_VERSION; }
RETRO_API void retro_get_system_info(struct retro_system_info *i) { memset(i,0,sizeof(*i));i->library_name="UnifiedIdentityHost";i->library_version="1";i->valid_extensions="ntc"; }
RETRO_API void retro_get_system_av_info(struct retro_system_av_info *i) { memset(i,0,sizeof(*i));i->geometry.base_width=1;i->geometry.base_height=1;i->geometry.max_width=1;i->geometry.max_height=1;i->geometry.aspect_ratio=1;i->timing.fps=60;i->timing.sample_rate=48000; }
RETRO_API bool retro_load_game(const struct retro_game_info *i) {
#ifdef FBNEO
 const char *system=NULL;
 environment(RETRO_ENVIRONMENT_GET_SYSTEM_DIRECTORY,&system);
 if(system)snprintf(szAppCheatsPath,sizeof(szAppCheatsPath),"%s/fbneo/cheats/",system);
 static const struct retro_controller_info controllers[]={{NULL,0}};
 environment(RETRO_ENVIRONMENT_SET_CONTROLLER_INFO,(void*)controllers);
 report[5]=strstr(szAppCheatsPath,"/NFC-")!=NULL;
 // Real FBNeo creates driver-specific v2 options during load_game. An INI
 // default may request Enabled even though index zero is the first value.
 static struct retro_core_option_v2_definition defs[]={
  {.key=CHEAT_KEY,.desc="Synthetic",.values={{"0 - Disabled",NULL},{"1 - Enabled",NULL},{"2 - Alternate",NULL},{NULL,NULL}},.default_value="0 - Disabled"},
  {.key="fbneo-cheat-1-otherdriver-Foreign",.desc="Foreign",.values={{"0 - Disabled",NULL},{"1 - Enabled",NULL},{NULL,NULL}},.default_value="1 - Enabled"},
  {.key="other",.desc="Other",.values={{"one",NULL},{"two",NULL},{NULL,NULL}},.default_value="one"},
  {0}};
 static const struct retro_core_options_v2 options={NULL,defs};
 environment(RETRO_ENVIRONMENT_SET_CORE_OPTIONS_V2,(void*)&options);
#endif
 report[1]=!enabled();return i&&i->data&&i->size;
}
RETRO_API void retro_unload_game(void) {}
RETRO_API void retro_reset(void) {}
RETRO_API void retro_run(void) { static uint32_t pixel;report[2]=enabled()
#ifdef FBNEO
 &&bCheatsAllowed
#endif
 ;if(video)video(&pixel,1,1,4); }
RETRO_API size_t retro_serialize_size(void) { return sizeof(report); }
RETRO_API bool retro_serialize(void *d,size_t n) { if(n<sizeof(report))return false;memcpy(d,report,sizeof(report));return true; }
RETRO_API bool retro_unserialize(const void *d,size_t n) { if(n!=sizeof(report))return false;memcpy(report,d,sizeof(report));return true; }
RETRO_API void retro_cheat_reset(void) { report[4]++; }
RETRO_API void retro_cheat_set(unsigned i,bool active,const char *code) {(void)i;if(active&&code&&*code)report[3]++;}
RETRO_API void *retro_get_memory_data(unsigned id) { return id==RETRO_MEMORY_SYSTEM_RAM?report:NULL; }
RETRO_API size_t retro_get_memory_size(unsigned id) { return id==RETRO_MEMORY_SYSTEM_RAM?sizeof(report):0; }
