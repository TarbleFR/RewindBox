#define _GNU_SOURCE
#include <stdio.h>
#include <stdint.h>
#include <stdlib.h>
#include <stdbool.h>
#include <string.h>
#include <dlfcn.h>
#include <signal.h>
#include <unistd.h>
#include <ucontext.h>
#include "libretro.h"
static const char *filter;
static unsigned frames;
static bool environment(unsigned cmd, void *data) {
 switch(cmd) {
  case RETRO_ENVIRONMENT_GET_SYSTEM_DIRECTORY:
  case RETRO_ENVIRONMENT_GET_SAVE_DIRECTORY: *(const char **)data="/tmp"; return true;
  case RETRO_ENVIRONMENT_GET_VARIABLE: {
   struct retro_variable *v=data;
   if(!strcmp(v->key,"nestopia_blargg_ntsc_filter")){v->value=filter;return true;}
   if(!strcmp(v->key,"nestopia_overscan_v_top") || !strcmp(v->key,"nestopia_overscan_v_bottom")){v->value="8";return true;}
   v->value=NULL; return false;
  }
  case RETRO_ENVIRONMENT_GET_VARIABLE_UPDATE: *(bool *)data=false;return true;
  case RETRO_ENVIRONMENT_GET_CAN_DUPE: *(bool *)data=true;return true;
  case RETRO_ENVIRONMENT_GET_CORE_OPTIONS_VERSION: *(unsigned *)data=2;return true;
  case RETRO_ENVIRONMENT_SET_PIXEL_FORMAT:return *(enum retro_pixel_format *)data==RETRO_PIXEL_FORMAT_XRGB8888;
  default: return false;
 }
}
static void video(const void *p,unsigned w,unsigned h,size_t pitch){if(!p||w!=(strcmp(filter,"disabled")?602u:256u)||h!=224||pitch!=w*4)exit(5);frames++;if(frames==1)printf("FIRST_FRAME %ux%u pitch=%zu\n",w,h,pitch);}
static void audio(int16_t a,int16_t b){}
static size_t audio_batch(const int16_t *p,size_t n){return n;}
static void poll(void){}
static int16_t input(unsigned p,unsigned d,unsigned i,unsigned id){return 0;}
#ifndef __APPLE__
static void fault(int sig,siginfo_t *info,void *ctx){
 uintptr_t pc=0;
#if defined(__linux__) && defined(__x86_64__)
 pc=((ucontext_t *)ctx)->uc_mcontext.gregs[REG_RIP];
#endif
 Dl_info d={0};dladdr((void*)pc,&d);
 dprintf(2,"FAULT signal=%d address=%p pc=%p image=%s offset=%#lx\n",sig,info->si_addr,(void*)pc,d.dli_fname?d.dli_fname:"?",(unsigned long)(pc-(uintptr_t)d.dli_fbase));
 _exit(128+sig);
}
#endif
#define LOAD(name) __typeof__(&name) f_##name=(__typeof__(&name))dlsym(handle,#name);if(!f_##name){fputs(#name " missing\n",stderr);return 3;}
int core_probe_main(int argc,char **argv){
 setbuf(stdout,NULL);filter=argc>2?argv[2]:"composite";
#ifndef __APPLE__
 struct sigaction a={0};a.sa_sigaction=fault;a.sa_flags=SA_SIGINFO;sigaction(SIGSEGV,&a,NULL);
#endif
 void *handle=dlopen(argv[1],RTLD_NOW|RTLD_LOCAL);if(!handle){puts(dlerror());return 2;}
 LOAD(retro_set_environment);LOAD(retro_set_video_refresh);LOAD(retro_set_audio_sample);LOAD(retro_set_audio_sample_batch);LOAD(retro_set_input_poll);LOAD(retro_set_input_state);LOAD(retro_init);LOAD(retro_load_game);LOAD(retro_run);LOAD(retro_reset);LOAD(retro_unload_game);LOAD(retro_deinit);
 Dl_info image={0};dladdr((void*)f_retro_run,&image);printf("CORE_BASE=%p\n",image.dli_fbase);
 f_retro_set_environment(environment);f_retro_set_video_refresh(video);f_retro_set_audio_sample(audio);f_retro_set_audio_sample_batch(audio_batch);f_retro_set_input_poll(poll);f_retro_set_input_state(input);f_retro_init();
 uint8_t rom[16+16384+8192]={0};memcpy(rom,"NES\032\001\001",6);memset(rom+16,0xea,16384);memcpy(rom+16,"\170\114\001\200",4);for(unsigned i=0;i<3;i++){rom[16+16384-6+i*2]=0;rom[16+16384-5+i*2]=0x80;}
 struct retro_game_info game={"probe.nes",rom,sizeof rom,NULL};
 if(!f_retro_load_game(&game)){puts("LOAD_FAILED");return 4;}
 puts("CONTENT_LOADED");for(unsigned i=0;i<60;i++)f_retro_run();f_retro_reset();for(unsigned i=0;i<60;i++)f_retro_run();
 f_retro_unload_game();f_retro_deinit();dlclose(handle);printf("PASS filter=%s frames=%u\n",filter,frames);return frames==120?0:6;
}

#ifndef __APPLE__
int main(int argc,char **argv){return core_probe_main(argc,argv);}
#endif
