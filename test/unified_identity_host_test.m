#import <Foundation/Foundation.h>
#import "LibretroCoreHost.h"
#import "LibretroCoreOptions.h"
static unsigned checks,failures;
#define CHECK(c,m) do{checks++;if(!(c)){failures++;fprintf(stderr,"FAIL %d %s\n",__LINE__,m);}}while(0)
static void WriteJSON(NSString *path,id object) { [NSFileManager.defaultManager createDirectoryAtPath:path.stringByDeletingLastPathComponent withIntermediateDirectories:YES attributes:nil error:nil];[[NSJSONSerialization dataWithJSONObject:object options:0 error:nil] writeToFile:path atomically:YES]; }
static NSDictionary *ReadJSON(NSString *path) { NSData *d=[NSData dataWithContentsOfFile:path];return d?[NSJSONSerialization JSONObjectWithData:d options:0 error:nil]:nil; }
static LibretroCoreHost *Host(NSString *core,NSString *folder) { return [[LibretroCoreHost alloc] initWithCorePath:core systemDirectory:[folder stringByAppendingPathComponent:@"System"] saveDirectory:[folder stringByAppendingPathComponent:@"Saves"] stateDirectory:[folder stringByAppendingPathComponent:@"States"] optionsDirectory:[folder stringByAppendingPathComponent:@"Config"] cacheDirectory:[folder stringByAppendingPathComponent:@"Cache"] language:RETRO_LANGUAGE_FRENCH jitCapable:NO]; }
int main(int argc,const char **argv) { @autoreleasepool {
 if(argc!=3)return 2;NSString *core=@(argv[1]),*folder=@(argv[2]);NSString *config=[folder stringByAppendingPathComponent:@"Config/UnifiedIdentityHost.json"],*games=[folder stringByAppendingPathComponent:@"Config/Games/UnifiedIdentityHost.json"];
 NSString *content=[folder stringByAppendingPathComponent:@"test.ntc"];[NSFileManager.defaultManager createDirectoryAtPath:folder withIntermediateDirectories:YES attributes:nil error:nil];[[@"content" dataUsingEncoding:NSASCIIStringEncoding] writeToFile:content atomically:YES];
 WriteJSON(config,@{@"values":@{@"ppsspp_cheats":@"enabled",@"other":@"one"}});WriteJSON(games,@{@"games":@{@"game":@{@"ppsspp_cheats":@"enabled"}}});
 LibretroCoreHost *host=Host(core,folder);host.optionsGameKey=@"game";host.initialSessionOverrides=@{@"ppsspp_cheats":@"enabled"};host.optionsDeclared=^(LibretroCoreOptions *options){[options applySessionOverrides:@{@"ppsspp_cheats":@"enabled"}];};NSError *error=nil;
 CHECK([host loadCore:&error],"measurement core loads");CHECK([host loadContentAtPath:content error:&error],"measurement content loads");size_t size=0;uint8_t *ram=[host memoryDataForIdentifier:RETRO_MEMORY_SYSTEM_RAM size:&size];CHECK(ram&&size==256&&ram[0]&&ram[1],"stored core/game/session enabled cannot activate at init or content load");
 [host runFrame];CHECK(ram[2]==0&&ram[3]==0,"session starts off without calling a cheat activation");CHECK(![host.options setValue:@"enabled" forKey:@"ppsspp_cheats" persist:YES],"raw core option cannot bypass explicit cheat consent");
 [host applyCheats:@[@"000F0024 0000007F"]];[host runFrame];CHECK(ram[2]==1&&ram[3]==1,"explicit valid program enables only this session");[host applyCheats:@[]];[host runFrame];CHECK(ram[2]==0,"disable-all disables PSP interpreter");
 [host unloadWithContextDestroy:nil contextRelease:nil];host=nil;
 // A persisted disabled value must survive explicit activation followed by a
 // save of an unrelated option. persist:NO used to leak enabled into this file.
 WriteJSON(config,@{@"values":@{@"ppsspp_cheats":@"disabled",@"other":@"one"}});host=Host(core,folder);CHECK([host loadCore:&error]&&[host loadContentAtPath:content error:&error],"second session loads");
 [host applyCheats:@[@"000F0024 0000007F"]];[host.options setValue:@"two" forKey:@"other" persist:YES];CHECK([ReadJSON(config)[@"values"][@"ppsspp_cheats"] isEqual:@"disabled"],"saving another option cannot persist cheat activation");
 NSString *oversized=[@"A" stringByPaddingToLength:5000 withString:@"A" startingAtIndex:0];[host applyCheats:@[oversized]];[host runFrame];ram=[host memoryDataForIdentifier:RETRO_MEMORY_SYSTEM_RAM size:&size];CHECK(ram[2]==0,"rejected oversized input cannot turn on PSP cheats");
 [host unloadWithContextDestroy:nil contextRelease:nil];host=nil;host=Host(core,folder);CHECK([host loadCore:&error]&&[host loadContentAtPath:content error:&error],"fresh third session loads");ram=[host memoryDataForIdentifier:RETRO_MEMORY_SYSTEM_RAM size:&size];[host runFrame];CHECK(ram[0]&&ram[1]&&ram[2]==0&&ram[3]==0,"later launch remains disabled after earlier explicit activation");[host unloadWithContextDestroy:nil contextRelease:nil];
}printf("Unified host: %u checks, %u failures\n",checks,failures);return failures?1:0;}
