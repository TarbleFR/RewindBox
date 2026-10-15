// Real core effect probe. Own synthetic ROMs never write $24 after reset.
#import "LibretroCoreHost.h"
#import "LibretroCheats.h"
@interface LibretroSession (CheatProbePrivate)
- (void)enqueue:(dispatch_block_t)command;
@end
static void RunCheatProbe(LibretroSession *session, NSDictionary *scenario, NSMutableDictionary *result,
                          dispatch_block_t completion) {
  NSMutableArray *checks = [NSMutableArray array]; result[@"cheatChecks"] = checks;
  NSString *console = scenario[@"console"], *core = scenario[@"core"];
  NSString *raw = [console isEqual:@"snes"] ? @"7E0024:7F" : @"0024:7F";
  NSArray *codes = [LibretroCheats codesForCheat:@{@"name":@"Synthetic counter", @"code":raw, @"handler":@0} core:core console:console];
  [checks addObject:@{@"name":@"core adapter accepts the synthetic native code", @"passed":@(codes.count == 1)}];
  dispatch_after(dispatch_time(DISPATCH_TIME_NOW, 600 * NSEC_PER_MSEC), dispatch_get_main_queue(), ^{
    [session enqueue:^{
      LibretroCoreHost *host = [session valueForKey:@"host"];
      size_t size = 0; uint8_t *ram = [host memoryDataForIdentifier:RETRO_MEMORY_SYSTEM_RAM size:&size];
      BOOL hasRAM = ram != NULL && size > 0x24;
      dispatch_async(dispatch_get_main_queue(), ^{ [checks addObject:@{@"name":@"actual core exposes system RAM", @"passed":@(hasRAM)}]; });
      if (!hasRAM) { dispatch_async(dispatch_get_main_queue(), completion); return; }
      ram[0x24] = 0x11; [host applyCheats:codes];
      dispatch_after(dispatch_time(DISPATCH_TIME_NOW, 400 * NSEC_PER_MSEC), dispatch_get_main_queue(), ^{
        [session enqueue:^{
          size_t heldSize = 0; uint8_t *held = [host memoryDataForIdentifier:RETRO_MEMORY_SYSTEM_RAM size:&heldSize];
          BOOL active = held && heldSize > 0x24 && held[0x24] == 0x7f;
          [host applyCheats:@[]]; if (held && heldSize > 0x24) held[0x24] = 0x22;
          dispatch_async(dispatch_get_main_queue(), ^{ [checks addObject:@{@"name":@"enabled code changes real emulated memory without restart", @"passed":@(active)}]; });
          dispatch_after(dispatch_time(DISPATCH_TIME_NOW, 400 * NSEC_PER_MSEC), dispatch_get_main_queue(), ^{
            [session enqueue:^{
              size_t releasedSize = 0; uint8_t *released = [host memoryDataForIdentifier:RETRO_MEMORY_SYSTEM_RAM size:&releasedSize];
              BOOL inactive = released && releasedSize > 0x24 && released[0x24] == 0x22;
              dispatch_async(dispatch_get_main_queue(), ^{
                [checks addObject:@{@"name":@"disabled code stops modifying emulated memory without restart", @"passed":@(inactive)}];
                completion();
              });
            }];
          });
        }];
      });
    }];
  });
}
