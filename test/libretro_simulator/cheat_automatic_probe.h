// End-to-end: pre-existing indices -> renamed content -> automatic rows -> actual core RAM.
#import "LibretroCheatCatalog.h"
@interface LibretroCheatMenu (AutomaticProbePrivate)
- (void)discover;
@end
@interface AutomaticCheatProbe : NSObject
@property(nonatomic,strong) LibretroSession *session;
@property(nonatomic,strong) LibretroCheatMenu *menu;
@property(nonatomic,strong) LibretroMenuPage *root;
@property(nonatomic,strong) CheatConfirmationProbe *page;
@property(nonatomic,strong) NSMutableArray *checks;
@property(nonatomic,copy) dispatch_block_t finish;
@property(nonatomic,copy) NSString *folder,*content;
@property(nonatomic) NSUInteger attempts,stage;
- (void)next;
@end
@implementation AutomaticCheatProbe
- (void)check:(BOOL)value name:(NSString *)name { [_checks addObject:@{@"name":name,@"passed":@(value)}]; }
- (LibretroMenuRow *)row:(NSString *)name {
  for(LibretroMenuSection *section in _root.builder()) for(LibretroMenuRow *row in section.rows) if([row.title isEqual:name])return row;
  return nil;
}
- (void)create:(NSString *)core {
  __weak AutomaticCheatProbe *weakSelf=self;
  _menu=[[LibretroCheatMenu alloc] initWithDirectory:_folder console:@"nes" core:core contentPath:_content legacy:@[]
    text:^NSString *(NSString *key){return key;} apply:^(NSArray *codes){
      AutomaticCheatProbe *probe=weakSelf;if(!probe)return;
      [probe.session enqueue:^{[[probe.session valueForKey:@"host"] applyCheats:codes];}];
    }];
  _root=[_menu rootPage];_page.builder=_root.builder;[_page rebuild];
}
- (void)memoryAfter:(uint64_t)serial expected:(uint8_t)expected remaining:(NSUInteger)remaining then:(dispatch_block_t)then {
  [_session enqueue:^{
    LibretroCoreHost *host=[self.session valueForKey:@"host"];
    BOOL elapsed=host.frameSerial>=serial+4;
    size_t size=0;uint8_t *ram=[host memoryDataForIdentifier:RETRO_MEMORY_SYSTEM_RAM size:&size];
    BOOL correct=ram && size>0x24 && ram[0x24]==expected;
    dispatch_async(dispatch_get_main_queue(),^{
      if(elapsed || remaining==0){[self check:elapsed && correct name:expected==0x7f ? @"automatic menu activation changes actual Nestopia RAM after observed frames" : @"disable-all stops actual Nestopia RAM modification after observed frames"];then();}
      else dispatch_after(dispatch_time(DISPATCH_TIME_NOW,25*NSEC_PER_MSEC),dispatch_get_main_queue(),^{[self memoryAfter:serial expected:expected remaining:remaining-1 then:then];});
    });
  }];
}
- (void)next {
  BOOL pending=![[_menu valueForKey:@"ready"] boolValue] || [[_menu valueForKey:@"discovering"] boolValue] || [[_menu valueForKey:@"pendingSources"] unsignedIntegerValue]>0;
  if(pending && _attempts++<400){dispatch_after(dispatch_time(DISPATCH_TIME_NOW,25*NSEC_PER_MSEC),dispatch_get_main_queue(),^{[self next];});return;}
  if(pending){[self check:NO name:@"automatic catalogue resolution deadline"];_finish();return;}_attempts=0;
  if(_stage==0){
    NSArray *records=[_menu valueForKey:@"records"];
    [self check:records.count==3 name:@"two installed sources automatically aggregate and deduplicate without catalogue selection"];
    [self check:[self row:@"Automatic A"]!=nil && [self row:@"Complement"]!=nil && [self row:@"Wrong region"]==nil name:@"renamed exact content gets compatible codes and excludes mismatched regional hash"];
    [self check:[records.firstObject[@"origins"] count]==2 name:@"automatic duplicate keeps both source attributions"];
    BOOL disabled=YES;for(NSDictionary *r in records)disabled &= ![r[@"enabled"] boolValue];
    [self check:disabled name:@"automatic discovery never enables downloaded codes"];
    LibretroMenuRow *row=[self row:@"Automatic A"];if(row.toggle)row.toggle(_page,YES);
    if(_page.confirmation){_page.confirmation();_page.confirmation=nil;}
    [self check:[self row:@"Automatic A"].toggleOn name:@"discovered code has a working individual switch"];
    [_session enqueue:^{
      LibretroCoreHost *host=[self.session valueForKey:@"host"];uint64_t serial=host.frameSerial;
      dispatch_async(dispatch_get_main_queue(),^{[self memoryAfter:serial expected:0x7f remaining:100 then:^{
        LibretroMenuRow *all=[self row:@"cheatDisableAll"];if(all.action)all.action(self.page);
        [self check:self.menu.enabledCount==0 name:@"disable-all clears all individual selections"];
        [self.session enqueue:^{
          LibretroCoreHost *held=[self.session valueForKey:@"host"];size_t size=0;uint8_t *ram=[held memoryDataForIdentifier:RETRO_MEMORY_SYSTEM_RAM size:&size];if(ram && size>0x24)ram[0x24]=0x22;uint64_t after=held.frameSerial;
          dispatch_async(dispatch_get_main_queue(),^{[self memoryAfter:after expected:0x22 remaining:100 then:^{
            LibretroMenuRow *again=[self row:@"Automatic A"];if(again.toggle)again.toggle(self.page,YES);
            self.stage=1;dispatch_queue_t queue=[self.menu valueForKey:@"queue"];
            dispatch_async(queue,^{dispatch_async(dispatch_get_main_queue(),^{[self create:@"nestopia"];[self next];});});
          }];});
        }];
      }];});
    }];return;
  }
  if(_stage==1){
    [self check:[self row:@"Automatic A"]!=nil && ![self row:@"Automatic A"].toggleOn name:@"relaunch restores available cheats with activation off"];
    LibretroMenuRow *restore=[self row:@"cheatRestore"];if(restore.action)restore.action(_page);
    if(_page.confirmation){_page.confirmation();_page.confirmation=nil;}
    [self check:[self row:@"Automatic A"].toggleOn name:@"content-specific explicit restore remembers automatic selections"];
    // Keep the explicit selection on disk; clear only the live core before the
    // next object. The second process must load it disabled and restore it itself.
    [_session enqueue:^{[[self.session valueForKey:@"host"] applyCheats:@[]];}];
    _stage=2;dispatch_queue_t queue=[_menu valueForKey:@"queue"];
    dispatch_async(queue,^{dispatch_async(dispatch_get_main_queue(),^{[self create:@"future_core"];[self next];});});return;
  }
  if (_stage==3) {
    [self check:[NSFileManager.defaultManager fileExistsAtPath:[_folder stringByAppendingPathComponent:@"process-restart-ready"]] name:@"second process reads the first process receipt without reinstalling or erasing data"];
    [self check:[self row:@"Automatic A"]!=nil && ![self row:@"Automatic A"].toggleOn name:@"process restart automatically rediscovers codes without activating remembered selections"];
    LibretroMenuRow *restore=[self row:@"cheatRestore"];if(restore.action)restore.action(_page);
    if(_page.confirmation){_page.confirmation();_page.confirmation=nil;}
    [self check:[self row:@"Automatic A"].toggleOn name:@"second process restores the first process saved selection explicitly"];
    [_session enqueue:^{
      LibretroCoreHost *host=[self.session valueForKey:@"host"];uint64_t serial=host.frameSerial;
      dispatch_async(dispatch_get_main_queue(),^{[self memoryAfter:serial expected:0x7f remaining:100 then:^{self.finish();}];});
    }];return;
  }
  [self check:[self row:@"Automatic A"]!=nil && ![self row:@"Automatic A"].enabled name:@"unknown core can browse the common catalogue but cannot activate unreviewed formats"];
  [[NSData data] writeToFile:[_folder stringByAppendingPathComponent:@"process-restart-ready"] atomically:YES];
  _finish();
}
@end
static void RunAutomaticCheatProbe(LibretroSession *session,NSMutableArray *checks,dispatch_block_t completion) {
  AutomaticCheatProbe *probe=[AutomaticCheatProbe new];probe.session=session;probe.checks=checks;probe.finish=completion;
  probe.folder=DocumentsPath(@"AutomaticCheatProbe/Persistent");
  [NSFileManager.defaultManager createDirectoryAtPath:probe.folder withIntermediateDirectories:YES attributes:nil error:nil];
  probe.content=[probe.folder stringByAppendingPathComponent:@"renamed-by-user.nes"];
  if (![NSFileManager.defaultManager fileExistsAtPath:probe.content]) [NSFileManager.defaultManager copyItemAtPath:[NSBundle.mainBundle.bundlePath stringByAppendingPathComponent:@"content/cheat-probe.nes"] toPath:probe.content error:nil];
  NSString *md5=[LibretroCheats identityAtPath:probe.content console:@"nes" core:@"nestopia"][@"md5"];
  BOOL restart=getenv("NEOSTATION_CHEAT_RESTART")!=NULL;
  if(restart)probe.stage=3;
  NSArray *sources=restart ? @[] : LibretroCheatCatalog.sources;
  for(NSUInteger i=0;i<sources.count;i++){
    NSDictionary *source=sources[i];NSString *identifier=source[@"id"];
    NSArray *cheats=i==0 ? @[@{@"name":@"Automatic A",@"code":@"0024:7F",@"handler":@0},@{@"name":@"Automatic B",@"code":@"0010:44",@"handler":@0}]
      : @[@{@"name":@"Duplicate",@"code":@"0024:7F",@"handler":@0},@{@"name":@"Complement",@"code":@"0025:66",@"handler":@0}];
    NSMutableDictionary *game=[@{@"title":@"Synthetic (USA)",@"console":@"nes",@"source":identifier,@"revision":source[@"revision"],@"md5s":@[md5 ?: @""],@"cheats":cheats} mutableCopy];
    if(i==0) {
      NSData *cht=[@"cheats=2\ncheat0_desc=Automatic A\ncheat0_code=0024:7F\ncheat1_desc=Automatic B\ncheat1_code=0010:44\n" dataUsingEncoding:NSUTF8StringEncoding];
      NSString *sha=[LibretroCheats gitBlobSHA:cht];
      [game removeObjectForKey:@"cheats"];game[@"sha"]=sha;game[@"path"]=@"cht/Nintendo - Nintendo Entertainment System/Synthetic (USA).cht";
      NSString *cache=[probe.folder stringByAppendingPathComponent:@"Catalogs/libretro/nes/Files"];
      [NSFileManager.defaultManager createDirectoryAtPath:cache withIntermediateDirectories:YES attributes:nil error:nil];
      [cht writeToFile:[cache stringByAppendingPathComponent:[sha stringByAppendingPathExtension:@"cht"]] atomically:YES];
    }
    NSMutableDictionary *wrong=[game mutableCopy];wrong[@"title"]=@"Synthetic (Europe)";wrong[@"md5s"]=@[@"11111111111111111111111111111111"];
    wrong[@"cheats"]=@[@{@"name":@"Wrong region",@"code":@"0024:01",@"handler":@0}];
    NSDictionary *index=@{@"source":identifier,@"console":@"nes",@"revision":source[@"revision"],@"games":@[game,wrong]};
    NSString *folder=[probe.folder stringByAppendingPathComponent:[NSString stringWithFormat:@"Catalogs/%@/nes",identifier]];
    [NSFileManager.defaultManager createDirectoryAtPath:folder withIntermediateDirectories:YES attributes:nil error:nil];
    [[NSJSONSerialization dataWithJSONObject:index options:0 error:nil] writeToFile:[folder stringByAppendingPathComponent:@"index.json"] atomically:YES];
  }
  probe.page=[[CheatConfirmationProbe alloc] initWithTitle:@"Automatic" builder:^NSArray *{return @[];}];
  [probe.page loadViewIfNeeded];[probe create:@"nestopia"];[probe next];
}
