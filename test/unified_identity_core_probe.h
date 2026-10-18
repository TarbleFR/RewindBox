// Test-only memory effects against the already delivered PSP/N64 cores.
// Observations require real core frames; they never wait for an expected value
// alone and cannot pass merely because the frontend accepted a code string.
#import "LibretroCoreHost.h"
#import "LibretroCheats.h"
@interface LibretroSession (UnifiedIdentityProbePrivate)
- (void)enqueue:(dispatch_block_t)command;
@end
@interface UnifiedIdentityCoreProbe : NSObject
@property(nonatomic,strong) LibretroSession *session;
@property(nonatomic,strong) NSMutableArray *checks;
@property(nonatomic,copy) dispatch_block_t finish;
@property(nonatomic,copy) NSArray<NSString *> *codes;
@property(nonatomic) NSUInteger offset;
@end
@implementation UnifiedIdentityCoreProbe
- (void)check:(BOOL)passed name:(NSString *)name {
  [self.checks addObject:@{@"name":name,@"passed":@(passed)}];
}
- (void)observeAfter:(uint64_t)serial expected:(uint8_t)value attempts:(NSUInteger)attempts then:(dispatch_block_t)then {
  [self.session enqueue:^{
    LibretroCoreHost *host=[self.session valueForKey:@"host"];size_t size=0;
    uint8_t *ram=[host memoryDataForIdentifier:RETRO_MEMORY_SYSTEM_RAM size:&size];
    BOOL advanced=host.frameSerial>=serial+4;BOOL passed=advanced&&ram&&size>self.offset&&ram[self.offset]==value;
    dispatch_async(dispatch_get_main_queue(),^{
      if(passed||!attempts){[self check:passed name:[NSString stringWithFormat:@"real core advanced four frames and RAM[%lu]=%02X",(unsigned long)self.offset,value]];then();}
      else dispatch_after(dispatch_time(DISPATCH_TIME_NOW,20*NSEC_PER_MSEC),dispatch_get_main_queue(),^{[self observeAfter:serial expected:value attempts:attempts-1 then:then];});
    });
  }];
}
- (void)start {
  [self.session enqueue:^{
    LibretroCoreHost *host=[self.session valueForKey:@"host"];size_t size=0;uint8_t *ram=[host memoryDataForIdentifier:RETRO_MEMORY_SYSTEM_RAM size:&size];
    BOOL valid=ram&&size>self.offset;uint64_t frame=host.frameSerial;
    if(valid){ram[self.offset]=0x11;[host applyCheats:self.codes];}
    dispatch_async(dispatch_get_main_queue(),^{
      [self check:valid name:@"delivered core exposes the expected real RAM address"];
      if(!valid){self.finish();return;}
      [self observeAfter:frame expected:0x7f attempts:200 then:^{
        // Destroy the first observed result: a second overwrite proves a
        // running cheat engine rather than ApplyCheatSet's one-off write.
        [self.session enqueue:^{
          LibretroCoreHost *held=[self.session valueForKey:@"host"];size_t heldSize=0;uint8_t *memory=[held memoryDataForIdentifier:RETRO_MEMORY_SYSTEM_RAM size:&heldSize];
          if(memory&&heldSize>self.offset)memory[self.offset]=0x33;uint64_t active=held.frameSerial;
          dispatch_async(dispatch_get_main_queue(),^{[self observeAfter:active expected:0x7f attempts:200 then:^{
            [self.session enqueue:^{
              LibretroCoreHost *released=[self.session valueForKey:@"host"];[released applyCheats:@[]];size_t releasedSize=0;uint8_t *memory=[released memoryDataForIdentifier:RETRO_MEMORY_SYSTEM_RAM size:&releasedSize];
              if(memory&&releasedSize>self.offset)memory[self.offset]=0x22;uint64_t disabled=released.frameSerial;
              dispatch_async(dispatch_get_main_queue(),^{[self observeAfter:disabled expected:0x22 attempts:200 then:self.finish];});
            }];
          }];});
        }];
      }];
    });
  }];
}
@end
static void RunUnifiedIdentityCoreProbe(LibretroSession *session,NSDictionary *scenario,NSMutableDictionary *result,dispatch_block_t completion) {
  UnifiedIdentityCoreProbe *probe=[UnifiedIdentityCoreProbe new];probe.session=session;probe.checks=[NSMutableArray array];result[@"cheatChecks"]=probe.checks;probe.finish=completion;
  BOOL psp=[scenario[@"console"] isEqual:@"psp"];
  // PSP CWCheat GetAddress adds0x08800000; core RAM starts0x08000000.
  // Mupen RDRAM is little-endian word storage, so an N64 byte uses address^3.
  probe.offset=psp?0x008f0024:(0x000f0024^3);
  NSString *raw=psp?@"000F0024 0000007F":@"800F0024 007F";
  probe.codes=[LibretroCheats codesForCheat:@{@"name":@"Original synthetic effect",@"code":raw,@"handler":@0} core:scenario[@"core"] console:scenario[@"console"]];
  [probe check:probe.codes.count==1 name:@"audited adapter preserves one complete native program"];
  [probe start];
}
