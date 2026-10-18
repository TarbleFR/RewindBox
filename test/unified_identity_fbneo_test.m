#import <Foundation/Foundation.h>
#import "LibretroCheats.h"
#import "LibretroCoreHost.h"
#import "LibretroCoreOptions.h"
static unsigned checks,failures;
#define CHECK(c,m) do{checks++;if(!(c)){failures++;fprintf(stderr,"FAIL %d %s\n",__LINE__,m);}}while(0)
static NSDictionary *Game(void) { return @{@"system":@"arcade",@"identities":@[@{@"type":@"romset",@"scheme":@"fbneo-driver-name",@"value":@"neotest"}]}; }
static NSDictionary *Program(NSString *code) { return @{@"name":@"Synthetic",@"dialect":@"fbneo-ini",@"status":@"available",@"dependencies":@[],@"parameters":@[],@"code":code}; }
static NSString *Block(NSString *name) { return [NSString stringWithFormat:@"cheat \"%@\"\ndefault 1\n0 \"Disabled\"\n1 \"Enabled\", 0, 0x24, 0x7F\n2 \"Alternate\", 0, 0x24, 0x33",name]; }
static void WriteJSON(NSString *path,id object) { [NSFileManager.defaultManager createDirectoryAtPath:path.stringByDeletingLastPathComponent withIntermediateDirectories:YES attributes:nil error:nil];[[NSJSONSerialization dataWithJSONObject:object options:0 error:nil] writeToFile:path atomically:YES]; }
static NSDictionary *ReadJSON(NSString *path) { NSData *data=[NSData dataWithContentsOfFile:path];return data?[NSJSONSerialization JSONObjectWithData:data options:0 error:nil]:nil; }
static LibretroCoreHost *Host(NSString *core,NSString *folder) { return [[LibretroCoreHost alloc] initWithCorePath:core systemDirectory:[folder stringByAppendingPathComponent:@"System"] saveDirectory:[folder stringByAppendingPathComponent:@"Saves"] stateDirectory:[folder stringByAppendingPathComponent:@"States"] optionsDirectory:[folder stringByAppendingPathComponent:@"Config"] cacheDirectory:[folder stringByAppendingPathComponent:@"Cache"] language:RETRO_LANGUAGE_FRENCH jitCapable:NO]; }
int main(int argc,const char **argv) { @autoreleasepool {
 if(argc!=3)return 2;NSString *core=@(argv[1]),*folder=@(argv[2]);NSFileManager *files=NSFileManager.defaultManager;NSError *error=nil;
 NSDictionary *program=Program(Block(@"Jinrei's move \"A+down\""));
 CHECK(([LibretroCheats canInstallFBNeoPrograms:@[program] game:Game()]),"native choices and inner quotes preserved");
 CHECK((![[LibretroCheats supportedCoreIDs] containsObject:@"fbneo"]),"FBNeo native channel does not pretend retro_cheat_set support");
 CHECK((![LibretroCheats canInstallFBNeoPrograms:@[program,program] game:Game()]),"multi-program dependency closure cannot create independent toggles");
 for(id malformed in @[@{@"parameters":NSNull.null},@{@"dependencies":@[@"master"]},@{@"parameters":@[@{@"name":@"choice"}]}]) {
  NSMutableDictionary *bad=[program mutableCopy];[bad addEntriesFromDictionary:malformed];CHECK((![LibretroCheats canInstallFBNeoPrograms:@[bad] game:Game()]),"malformed parameters or dependencies rejected without exception");
 }
 for(NSString *bad in @[@"cheat \"x\"\ndefault 0\n0 \"Off\"\n1 \"On\",8,0x24,1",@"cheat \"x\"\ndefault 0\n0 \"Off\"\n1 \"On\",0,0x24,256",@"cheat \"x\"\ndefault 0\n0 \"Off\"\n2 \"On\",0,0x24,1",@"cheat \"x\"\ndefault 0\n0 \"Off\"\n1 \"On\",0,0,1",@"cheat \"x\"\ndefault 0\n0 \"Off\"\n1 \"On\",0,0x24,08",@"cheat \"x\"\ndefault 08\n0 \"Off\"\n1 \"On\",0,0x24,1",@"cheat \"x\"\ndefault 0\n0 \"Off\"\n08 \"On\",0,0x24,1",@"cheat \"x\"\ndefault 0\n0 \"Off\"\n1 \"On\",0,0x24,1\ninclude \"other\""]) {
  CHECK((![LibretroCheats canInstallFBNeoPrograms:@[Program(bad)] game:Game()]),"unsafe native block refused at device boundary");
 }
 CHECK(([LibretroCheats canInstallFBNeoPrograms:@[Program(@"cheat \"Octal\"\ndefault 01\n0 \"Off\"\n01 \"On\",0,044,0377")] game:Game()]),"native base0 octal preserved");
 NSString *system=[folder stringByAppendingPathComponent:@"Files"];
 NSDictionary *installed=[LibretroCheats installFBNeoPrograms:@[program] game:Game() systemDirectory:system error:&error];
 NSString *path=installed[@"imported_path"],*text=[NSString stringWithContentsOfFile:path encoding:NSUTF8StringEncoding error:nil];
 CHECK((installed&&[installed[@"changed"] boolValue]&&[text containsString:@"default 0"]&&![text containsString:@"default 1"]),"first import writes source choices with explicit disabled default");
 CHECK(([text containsString:@"Jinrei's move \"A+down\""]),"name and choices survive native installation");
 NSString *stage=[folder stringByAppendingPathComponent:@"Isolated"];[files createDirectoryAtPath:stage withIntermediateDirectories:YES attributes:nil error:nil];
 CHECK(([LibretroCheats stageManagedFBNeoDriver:@"neotest" systemDirectory:system destination:stage error:&error]!=nil),"intact receipt and regenerated disabled blocks may enter isolated directory");
 installed=[LibretroCheats installFBNeoPrograms:@[program] game:Game() systemDirectory:system error:&error];CHECK((installed&&![installed[@"changed"] boolValue]),"same managed import is idempotent");
 installed=[LibretroCheats installFBNeoPrograms:@[Program(Block(@"Second"))] game:Game() systemDirectory:system error:&error];text=[NSString stringWithContentsOfFile:path encoding:NSUTF8StringEncoding error:nil];CHECK((installed&&[text containsString:@"Second"]&&[text containsString:@"Jinrei"]),"later independent import retains existing managed program");
 NSData *personal=[@"// User edited native cheats\n" dataUsingEncoding:NSUTF8StringEncoding];[personal writeToFile:path atomically:YES];
 CHECK(([LibretroCheats installFBNeoPrograms:@[program] game:Game() systemDirectory:system error:&error]==nil&&[[NSData dataWithContentsOfFile:path] isEqual:personal]),"personally modified file preserved byte for byte");
 CHECK(([LibretroCheats stageManagedFBNeoDriver:@"neotest" systemDirectory:system destination:stage error:&error]==nil),"modified native bytes cannot enter a subsequent game session");
 NSString *config=[folder stringByAppendingPathComponent:@"Config/UnifiedIdentityHost.json"],*games=[folder stringByAppendingPathComponent:@"Config/Games/UnifiedIdentityHost.json"];
 NSString *key=@"fbneo-cheat-0-neotest-Synthetic",*on=@"1 - Enabled";
 WriteJSON(config,@{@"values":@{key:on,@"other":@"one"}});WriteJSON(games,@{@"games":@{@"game":@{key:on}}});
 NSString *content=[folder stringByAppendingPathComponent:@"test.ntc"];[[NSData dataWithBytes:"x" length:1] writeToFile:content atomically:YES];
 NSString *hostSystem=[folder stringByAppendingPathComponent:@"System"];
 CHECK(([LibretroCheats installFBNeoPrograms:@[Program(Block(@"Seed"))] game:Game() systemDirectory:hostSystem error:&error]!=nil),"managed source seeded for next clean game launch");
 LibretroCoreHost *host=Host(core,folder);host.optionsGameKey=@"game";host.initialSessionOverrides=@{key:on};
 CHECK(([host loadCore:&error]&&[host loadContentAtPath:content error:&error]),"FBNeo measurement core/content load");size_t size=0;uint8_t *ram=[host memoryDataForIdentifier:RETRO_MEMORY_SYSTEM_RAM size:&size];
 CHECK((ram&&size==256&&ram[0]&&ram[1]&&ram[5]),"stored defaults stay off and native path overwrite is restored before cheat parsing");
 NSDictionary *snapshot=[host performFBNeoCheatCommand:@{@"action":@"snapshot"} error:&error];
 CHECK(([snapshot[@"driver"] isEqual:@"neotest"]&&[snapshot[@"options"] count]==1&&[snapshot[@"enabled_count"] integerValue]==0),"snapshot uses exported actual driver and filters foreign-driver options");
 CHECK((![host.options setValue:on forKey:key persist:YES]),"generic option cannot bypass explicit native cheat channel");
 snapshot=[host performFBNeoCheatCommand:@{@"action":@"set",@"key":key,@"value":on} error:&error];[host runFrame];CHECK((snapshot&&ram[2]==1&&ram[3]==0),"explicit native option enables session without retro_cheat_set");
 [host.options setValue:@"two" forKey:@"other" persist:YES];CHECK(([ReadJSON(config)[@"values"][key] isEqual:on]),"unrelated option save does not rewrite stored native cheat preference");
 snapshot=[host performFBNeoCheatCommand:@{@"action":@"disableAll"} error:&error];[host runFrame];CHECK((snapshot&&ram[2]==0),"disableAll reaches native option session override");
 CHECK(([host performFBNeoCheatCommand:@{@"action":@"set",@"key":key,@"value":@"arbitrary"} error:&error]==nil),"only currently declared native choices accepted");
 NSMutableDictionary *wrong=[Game() mutableCopy];wrong[@"identities"]=@[@{@"type":@"romset",@"scheme":@"fbneo-driver-name",@"value":@"another"}];
 CHECK(([host performFBNeoCheatCommand:@{@"action":@"import",@"game":wrong,@"programs":@[program]} error:&error]==nil),"wrong source driver cannot write native INI");
 snapshot=[host performFBNeoCheatCommand:@{@"action":@"import",@"game":Game(),@"programs":@[program]} error:&error];CHECK((snapshot&&[snapshot[@"restart_required"] boolValue]&&[snapshot[@"enabled_count"] integerValue]==0),"import stays off and explicitly requires relaunch");
 CHECK(([host performFBNeoCheatCommand:@{@"action":@"set",@"key":key,@"value":on} error:&error]==nil),"stale option indices cannot activate after pending import");
 [host unloadWithContextDestroy:nil contextRelease:nil];WriteJSON(config,@{@"values":@{key:@"0 - Disabled",@"other":@"one"}});CHECK(([host loadCore:&error]&&[host loadContentAtPath:content error:&error]),"same host object can start another clean session");snapshot=[host performFBNeoCheatCommand:@{@"action":@"snapshot"} error:&error];CHECK((snapshot&&![snapshot[@"restart_required"] boolValue]&&[snapshot[@"enabled_count"] integerValue]==0),"next launch clears pending import and starts native choices off");
 [host performFBNeoCheatCommand:@{@"action":@"set",@"key":key,@"value":on} error:&error];[host.options setValue:@"two" forKey:@"other" persist:YES];CHECK(([ReadJSON(config)[@"values"][key] isEqual:@"0 - Disabled"]),"explicit native activation cannot leak into a later preference save");
 [host unloadWithContextDestroy:nil contextRelease:nil];
}printf("Unified FBNeo: %u checks, %u failures\n",checks,failures);return failures?1:0;}
