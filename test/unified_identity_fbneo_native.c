/* Original fixture: execute the delivered FBNeo INI parser and cheat engine
 * against a test CPU's memory callbacks. No game ROM or CPU implementation is
 * rebuilt or included. This does not claim physical-device/game validation.
 * cpu_core_config matches upstream src/burn/burnint.h; the actual binary
 * calling the callbacks and changing RAM is the authoritative ABI check. */
#include <dlfcn.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include "libretro.h"
typedef struct cpu_core_config {
 char cpu_name[32];void(*open)(int);void(*close)(void);
 uint8_t(*read)(uint32_t);void(*write)(uint32_t,uint8_t);
 int(*active)(void);int(*totalcycles)(void);void(*newframe)(void);
 int(*idle)(int);void(*irq)(int,int,int);int(*run)(int);
 void(*runend)(void);void(*reset)(void);int(*scan)(int);void(*exit)(void);
 uint64_t memory_size;uint32_t address_flags;
} cpu_core_config;
static uint8_t memory[256];static unsigned writes,checks,failures;
static const char *phase="entry";
#define PHASE(name) do{phase=(name);fprintf(stderr,"FBNeo phase: %s\n",phase);}while(0)
static void cpu_open(int n){if(n!=0){fprintf(stderr,"FBNeo %s: unexpected CPU index %d\n",phase,n);abort();}}static void noop(void){}
static uint8_t cpu_read(uint32_t a){if(a>=sizeof(memory)){fprintf(stderr,"FBNeo %s: CPU read outside fixture RAM: 0x%08X\n",phase,a);abort();}return memory[a];}
static void cpu_write(uint32_t a,uint8_t v){if(a>=sizeof(memory)){fprintf(stderr,"FBNeo %s: CPU write outside fixture RAM: 0x%08X=0x%02X\n",phase,a,v);abort();}memory[a]=v;writes++;}
static int zero(void){return 0;}static int one_arg(int n){return n;}
static void irq(int a,int b,int c){(void)a;(void)b;(void)c;}
static char *path_export,private_path[260],personal_system[260];
static bool *master_export;static int(*update_export)(void);
static unsigned controller_callbacks,private_options,personal_options;
static void input_poll(void){}
static int16_t input_state(unsigned p,unsigned d,unsigned i,unsigned k){(void)p;(void)d;(void)i;(void)k;return 0;}
static void video(const void *p,unsigned w,unsigned h,size_t n){(void)p;(void)w;(void)h;(void)n;}
static void audio(int16_t l,int16_t r){(void)l;(void)r;}
static size_t audio_batch(const int16_t *p,size_t n){(void)p;return n;}
static void inspect_option(const char *key,const char *desc){
 if(key&&!strncmp(key,"fbneo-cheat-",12)&&desc){
  if(strstr(desc,"NS_PRIVATE"))private_options++;
  if(strstr(desc,"NS_PERSONAL"))personal_options++;
 }
}
static bool isolation_environment(unsigned command,void *data){
 // Same public-export guard as the production Host, including the cached
 // engine enable flag. No offset patch or instruction change is involved.
 snprintf(path_export,260,"%s/",private_path);*master_export=false;update_export();
 if(!data)return false;
 switch(command&0xffff){
  case RETRO_ENVIRONMENT_GET_SYSTEM_DIRECTORY:case RETRO_ENVIRONMENT_GET_SAVE_DIRECTORY:
   *(const char**)data=personal_system;return true;
  case RETRO_ENVIRONMENT_GET_CORE_OPTIONS_VERSION:*(unsigned*)data=2;return true;
  case RETRO_ENVIRONMENT_GET_LANGUAGE:*(unsigned*)data=RETRO_LANGUAGE_ENGLISH;return true;
  case RETRO_ENVIRONMENT_GET_CAN_DUPE:*(bool*)data=true;return true;
  case RETRO_ENVIRONMENT_GET_VARIABLE_UPDATE:*(bool*)data=false;return true;
  case RETRO_ENVIRONMENT_GET_VARIABLE:{struct retro_variable *v=data;if(v&&v->key&&!strncmp(v->key,"fbneo-cheat-",12)){v->value="0 - Disabled";return true;}return false;}
  case RETRO_ENVIRONMENT_SET_CONTROLLER_INFO:{
   controller_callbacks++;char name[300];snprintf(name,sizeof(name),"%s/1942.ini",private_path);
   FILE *f=fopen(name,"wb");if(f){fputs("cheat \"NS_PRIVATE\"\ndefault 0\n0 \"Disabled\"\n1 \"Enabled\",0,0x24,0x7F\n",f);fclose(f);}return true;
  }
  case RETRO_ENVIRONMENT_SET_CORE_OPTIONS_V2:{const struct retro_core_options_v2 *v=data;for(const struct retro_core_option_v2_definition *d=v?v->definitions:NULL;d&&d->key;d++)inspect_option(d->key,d->desc);return true;}
  case RETRO_ENVIRONMENT_SET_CORE_OPTIONS_V2_INTL:{const struct retro_core_options_v2_intl *v=data;for(const struct retro_core_option_v2_definition *d=v&&v->us?v->us->definitions:NULL;d&&d->key;d++)inspect_option(d->key,d->desc);return true;}
  case RETRO_ENVIRONMENT_SET_VARIABLES:{for(const struct retro_variable *v=data;v&&v->key;v++)inspect_option(v->key,v->value);return true;}
  case RETRO_ENVIRONMENT_SET_PIXEL_FORMAT:case RETRO_ENVIRONMENT_SET_INPUT_DESCRIPTORS:return true;
  default:return false;
 }
}
#define CHECK(c,m) do{checks++;if(!(c)){failures++;fprintf(stderr,"FAIL %s\n",m);}}while(0)
#define SYMBOL(type,name,symbol) type name=(type)dlsym(library,symbol);if(!name){fprintf(stderr,"Missing actual core export %s\n",symbol);return 2;}
int main(int argc,char **argv){
 setvbuf(stderr,NULL,_IONBF,0);PHASE("before dlopen");
 bool isolation_only=argc==4&&!strcmp(argv[3],"--isolation");
 if(argc!=3&&!isolation_only)return 2;
 void *library=dlopen(argv[1],RTLD_NOW|RTLD_LOCAL);if(!library){fprintf(stderr,"%s\n",dlerror());return 2;}
 PHASE("resolving native exports");
 typedef int(*int_fn)(void);typedef void(*void_fn)(void);typedef int(*enable_fn)(int,int);
 typedef char*(*text_fn)(uint32_t);typedef void(*register_fn)(int,cpu_core_config*);
 typedef cpu_core_config*(*config_fn)(int);
 SYMBOL(int_fn,burn_init,"BurnLibInit");SYMBOL(int_fn,burn_exit,"BurnLibExit");
 SYMBOL(int_fn,cheat_init,"CheatInit");SYMBOL(void_fn,cheat_exit,"CheatExit");
 SYMBOL(int_fn,load,"_Z15ConfigCheatLoadv");SYMBOL(enable_fn,enable,"CheatEnable");SYMBOL(int_fn,apply,"CheatApply");
 SYMBOL(int_fn,update,"CheatUpdate");
 SYMBOL(text_fn,driver_name,"BurnDrvGetTextA");SYMBOL(register_fn,register_cpu,"_Z16CpuCheatRegisteriP15cpu_core_config");
 SYMBOL(config_fn,cpu_config,"_Z16GetCpuCoreConfigi");
 SYMBOL(uint32_t*,driver,"nBurnDrvActive");SYMBOL(uint32_t*,count,"nBurnDrvCount");
 SYMBOL(bool*,allowed,"bCheatsAllowed");SYMBOL(char*,cheats_path,"szAppCheatsPath");
 // BurnLibInit itself calls BurnLibExit. The delivered Exit leaves its freed
 // table pointers non-null, so an explicit Exit followed by retro_init would
 // double-free them. Each independent fixture runs in a fresh process.
 FILE *file;
 if(!isolation_only){
 PHASE("BurnLibInit");CHECK(burn_init()==0,"native driver database initialises");
 PHASE("selecting 1942 metadata");
 for(*driver=0;*driver<*count;(*driver)++){const char *name=driver_name(0);if(name&&!strcmp(name,"1942"))break;}
 if(*driver>=*count){fprintf(stderr,"Pinned core has no1942 driver metadata\n");return 2;}
 // argv2 is a deliberately short test-only /tmp directory.
 if(strlen(argv[2])>64)return 2;
 strcpy(cheats_path,argv[2]);strcat(cheats_path,"/");
 char filename[128];snprintf(filename,sizeof(filename),"%s/1942.ini",argv[2]);file=fopen(filename,"wb");if(!file)return 2;
 fputs("cheat \"Original CPU callback fixture\"\ndefault 0\n0 \"Disabled\"\n1 \"Enabled\", 0, 0x24, 0x7F\n2 \"Alternate\", 0, 0x24, 0x33\n",file);fclose(file);
 cpu_core_config cpu={"Original test CPU",cpu_open,noop,cpu_read,cpu_write,zero,zero,noop,one_arg,irq,one_arg,noop,noop,one_arg,noop,sizeof(memory),0};
 PHASE("registering fixture CPU");CHECK(cheat_init()==0,"native CPU cheat registry initialises");register_cpu(0,&cpu);CHECK(cpu_config(0)==&cpu,"actual exported CPU registry retains callback configuration");*allowed=true;
 PHASE("parsing default0 INI");CHECK(load()==0,"actual pinned parser reads native INI");memory[0x24]=0x11;apply();CHECK(memory[0x24]==0x11&&writes==0,"native INI starts disabled");
 PHASE("enabling native choice");CHECK(enable(0,1)==0,"actual native choice enables");apply();CHECK(memory[0x24]==0x7f&&writes>0,"actual delivered engine writes CPU memory");
 memory[0x24]=0x22;unsigned before=writes;apply();CHECK(memory[0x24]==0x7f&&writes>before,"native engine repeats the write after overwrite");
 *allowed=false;update();memory[0x24]=0x55;before=writes;apply();CHECK(memory[0x24]==0x55&&writes==before,"master Off plus native CheatUpdate immediately stops cached active writes");*allowed=true;update();
 CHECK(enable(0,2)==0,"actual second native choice selected");apply();CHECK(memory[0x24]==0x33,"native choice values are preserved");
 CHECK(enable(0,0)==0,"actual native Off selected");memory[0x24]=0x44;before=writes;apply();CHECK(memory[0x24]==0x44&&writes==before,"disabled native engine leaves memory untouched");
 PHASE("exiting default0 fixture");cheat_exit();
 // Diagnose the personal-INI case separately. Production imports always use
 // default0; do not silently rewrite a user's existing nonzero default.
 file=fopen(filename,"wb");if(!file)return 2;
 fputs("cheat \"Nonzero default diagnostic\"\ndefault 1\n0 \"Disabled\"\n1 \"Enabled\", 0, 0x24, 0x7F\n",file);fclose(file);
 memset(memory,0,sizeof(memory));memory[0x24]=0x11;unsigned initial_writes=writes;
 PHASE("parsing nonzero default diagnostic");cheat_init();register_cpu(0,&cpu);*allowed=true;load();apply();
 bool nonzero_loaded_off=memory[0x24]==0x11&&writes==initial_writes;
 CHECK(nonzero_loaded_off,"native ConfigCheatLoad does not activate a nonzero default before explicit selection");
 enable(0,1);apply();CHECK(memory[0x24]==0x7f,"nonzero default diagnostic can activate its default choice");
 enable(0,0);memory[0x24]=0x44;initial_writes=writes;apply();
 bool nonzero_can_disable=memory[0x24]==0x44&&writes==initial_writes;
 PHASE("exiting native CPU fixture");cheat_exit();burn_exit();
 dlclose(library);
 printf("{\"checks\":%u,\"failures\":%u,\"writes\":%u,\"nonzeroDefaultLoadedOff\":%s,\"nonzeroDefaultCanDisable\":%s,\"rebuiltCore\":false,\"gameROMUsed\":false,\"physicalDeviceValidated\":false}\n",checks,failures,writes,nonzero_loaded_off?"true":"false",nonzero_can_disable?"true":"false");return failures?1:0;
 }
 // Execute the actual load_game path up to early native options with an empty
 // ZIP. Missing game ROMs are expected; no CPU game execution is claimed.
 typedef void(*environment_fn)(retro_environment_t);typedef bool(*load_game_fn)(const struct retro_game_info*);
 SYMBOL(environment_fn,set_environment,"retro_set_environment");SYMBOL(void_fn,init,"retro_init");SYMBOL(void_fn,deinit,"retro_deinit");SYMBOL(load_game_fn,load_game,"retro_load_game");
 snprintf(private_path,sizeof(private_path),"%s/private",argv[2]);mkdir(private_path,0700);
 snprintf(personal_system,sizeof(personal_system),"%s/personal",argv[2]);mkdir(personal_system,0700);
 char personal_fbneo[300],personal_cheats[300],personal_ini[320],zip[300];
 snprintf(personal_fbneo,sizeof(personal_fbneo),"%s/fbneo",personal_system);mkdir(personal_fbneo,0700);
 snprintf(personal_cheats,sizeof(personal_cheats),"%s/fbneo/cheats",personal_system);mkdir(personal_cheats,0700);
 snprintf(personal_ini,sizeof(personal_ini),"%s/1942.ini",personal_cheats);file=fopen(personal_ini,"wb");if(!file)return 2;
 const char *personal="cheat \"NS_PERSONAL\"\ndefault 1\n0 \"Disabled\"\n1 \"Enabled\",0,0x24,0x66\n";fputs(personal,file);fclose(file);
 snprintf(zip,sizeof(zip),"%s/1942.zip",argv[2]);file=fopen(zip,"wb");if(!file)return 2;unsigned char empty_zip[22]={0x50,0x4b,0x05,0x06};fwrite(empty_zip,1,sizeof(empty_zip),file);fclose(file);
 path_export=cheats_path;master_export=allowed;update_export=update;
 PHASE("setting real libretro environment");set_environment(isolation_environment);
 typedef void(*set_poll_fn)(retro_input_poll_t);typedef void(*set_state_fn)(retro_input_state_t);
 typedef void(*set_video_fn)(retro_video_refresh_t);typedef void(*set_audio_fn)(retro_audio_sample_t);typedef void(*set_batch_fn)(retro_audio_sample_batch_t);
 SYMBOL(set_poll_fn,set_poll,"retro_set_input_poll");SYMBOL(set_state_fn,set_state,"retro_set_input_state");
 SYMBOL(set_video_fn,set_video,"retro_set_video_refresh");SYMBOL(set_audio_fn,set_audio,"retro_set_audio_sample");SYMBOL(set_batch_fn,set_batch,"retro_set_audio_sample_batch");
 set_poll(input_poll);set_state(input_state);set_video(video);set_audio(audio);set_batch(audio_batch);PHASE("real retro_init");init();
 PHASE("real retro_load_game early native parser");struct retro_game_info info={zip,NULL,0,NULL};(void)load_game(&info);
 CHECK(controller_callbacks>0&&private_options>0,"actual early load parser sees command35 staged private INI");
 CHECK(personal_options==0,"actual early load parser excludes personal nonzero-default INI");
 file=fopen(personal_ini,"rb");char preserved[256]={0};if(file){fread(preserved,1,sizeof(preserved)-1,file);fclose(file);}CHECK(!strcmp(preserved,personal),"personal INI remains byte for byte unchanged");
 PHASE("real retro_deinit");cheat_exit();deinit();dlclose(library);
 printf("{\"checks\":%u,\"failures\":%u,\"privateOptions\":%u,\"personalOptions\":%u,\"rebuiltCore\":false,\"gameROMUsed\":false,\"physicalDeviceValidated\":false}\n",checks,failures,private_options,personal_options);return failures?1:0;
}
