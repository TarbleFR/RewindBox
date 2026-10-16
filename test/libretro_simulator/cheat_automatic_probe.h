// End-to-end: pre-existing indices -> renamed content -> automatic rows -> actual core RAM.
#import "LibretroCheatCatalog.h"
static void RunPSXCheatMenuProbe(NSMutableArray *checks,dispatch_block_t completion);
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
  _root=[_menu rootPage];[_root loadViewIfNeeded];
  // A user may leave a child catalogue page before async results arrive.
  [_menu setValue:nil forKey:@"visiblePage"];
  _page.builder=_root.builder;[_page rebuild];
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
    [self check:records.count==4 name:@"two installed sources automatically aggregate and deduplicate while retaining an unverified legacy choice"];
    [self check:[_root.tableView numberOfRowsInSection:1]==4 name:@"visible root table receives async results after the previous catalogue page has gone"];
    [self check:[self row:@"Automatic A"]!=nil && [self row:@"Complement"]!=nil && [self row:@"Wrong region"]==nil name:@"renamed exact content gets compatible codes and excludes mismatched regional hash"];
    [self check:[records.firstObject[@"origins"] count]==3 name:@"automatic duplicate keeps both source attributions and the recovered legacy choice"];
    BOOL disabled=YES;for(NSDictionary *r in records)disabled &= ![r[@"enabled"] boolValue];
    [self check:disabled name:@"automatic discovery never enables downloaded codes"];
    [self check:[records.firstObject[@"selected"] boolValue] && ![records.firstObject[@"uncertain"] boolValue] name:@"legacy CUE preference is retained and verified only by an exact matching current code"];
    LibretroMenuRow *restoreLegacy=[self row:@"cheatRestore"];if(restoreLegacy.action)restoreLegacy.action(_page);
    if(_page.confirmation){_page.confirmation();_page.confirmation=nil;}
    [self check:[self row:@"Automatic A"].toggleOn && ![self row:@"Unverified legacy choice"].toggleOn name:@"upgrade restoration enables a verified matching choice but refuses the selected uncertain variant"];
    LibretroMenuRow *clearLegacy=[self row:@"cheatDisableAll"];if(clearLegacy.action)clearLegacy.action(_page);
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
  NSString *cue=[probe.folder stringByAppendingPathComponent:@"renamed-by-user.cue"];
  if (![NSFileManager.defaultManager fileExistsAtPath:cue]) [@"FILE \"renamed-by-user.nes\" BINARY\n" writeToFile:cue atomically:YES encoding:NSUTF8StringEncoding error:nil];
  probe.content=cue;
  NSString *md5=[LibretroCheats identityAtPath:probe.content console:@"nes" core:@"nestopia"][@"md5"];
  BOOL restart=getenv("NEOSTATION_CHEAT_RESTART")!=NULL;
  if(!restart)probe.finish=^{RunPSXCheatMenuProbe(checks,completion);};
  if(restart)probe.stage=3;
  if(!restart) {
    NSString *oldHash=[LibretroCheats digest:[NSData dataWithContentsOfFile:cue]];
    NSString *key=[LibretroCheats digest:[[NSString stringWithFormat:@"nes|nestopia|%@",oldHash] dataUsingEncoding:NSUTF8StringEncoding]];
    NSString *folder=[probe.folder stringByAppendingPathComponent:@"Games"];
    [NSFileManager.defaultManager createDirectoryAtPath:folder withIntermediateDirectories:YES attributes:nil error:nil];
    NSDictionary *legacy=@{@"version":@2,@"remember":@YES,@"identity":@{@"sha256":oldHash},@"cheats":@[
      @{@"name":@"Old descriptor choice",@"code":@"0024:7F",@"handler":@0,@"selected":@YES,@"source":@"legacy",@"game":@"Synthetic (USA)"},
      @{@"name":@"Unverified legacy choice",@"code":@"0027:33",@"handler":@0,@"selected":@YES,@"source":@"legacy",@"game":@"Synthetic (Europe)"}]};
    [[NSJSONSerialization dataWithJSONObject:legacy options:0 error:nil] writeToFile:[folder stringByAppendingPathComponent:[key stringByAppendingPathExtension:@"json"]] atomically:YES];
  }
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

// Production catalogue + actual FFVII CHT -> UIKit switches -> native dispatch.
// Deliberately no PS1 emulation/BIOS: dispatch is observed, gameplay is not claimed.
@interface PSXCheatMenuProbe : NSObject
@property(nonatomic,strong) LibretroCheatMenu *menu;
@property(nonatomic,strong) LibretroMenuPage *root;
@property(nonatomic,strong) CheatConfirmationProbe *page;
@property(nonatomic,strong) NSMutableArray *checks,*applied;
@property(nonatomic,copy) dispatch_block_t finish;
@property(nonatomic,copy) NSString *folder,*content;
@property(nonatomic) NSUInteger attempts,stage;
@end
@implementation PSXCheatMenuProbe
- (void)check:(BOOL)value name:(NSString *)name { [_checks addObject:@{@"name":name,@"passed":@(value)}]; }
- (LibretroMenuRow *)row:(NSString *)title {
  for(LibretroMenuSection *s in _root.builder())for(LibretroMenuRow *r in s.rows)if([r.title isEqual:title])return r;return nil;
}
- (void)create:(NSString *)title {
  __weak PSXCheatMenuProbe *weakSelf=self;
  _menu=[[LibretroCheatMenu alloc] initWithDirectory:_folder console:@"psx" core:@"mednafen_psx_hw" contentPath:_content gameTitle:title legacy:@[] text:^NSString *(NSString *key){return key;} apply:^(NSArray *codes){[weakSelf.applied addObject:codes];}];
  LibretroCheatCatalog *catalog=[_menu valueForKey:@"catalog"];
  catalog.fetch=^NSData *(NSURL *url,NSUInteger limit,NSError **error){
    if([url.absoluteString containsString:@"Final%20Fantasy%20VII%20(USA).cht"])return [NSData dataWithContentsOfFile:[NSBundle.mainBundle.bundlePath stringByAppendingPathComponent:@"ff7-usa-original.cht"]];
    if(error)*error=[NSError errorWithDomain:NSURLErrorDomain code:NSURLErrorNotConnectedToInternet userInfo:nil];return nil;
  };
  _root=[_menu rootPage];[_root loadViewIfNeeded];_page.builder=_root.builder;[_page rebuild];
}
- (void)next {
  BOOL pending=![[_menu valueForKey:@"ready"] boolValue] || [[_menu valueForKey:@"discovering"] boolValue] || [[_menu valueForKey:@"pendingSources"] unsignedIntegerValue]>0;
  if(pending && _attempts++<600){dispatch_after(dispatch_time(DISPATCH_TIME_NOW,25*NSEC_PER_MSEC),dispatch_get_main_queue(),^{[self next];});return;}
  [self check:!pending name:@"PS1 production index/title resolution finishes"];if(pending){_finish();return;}_attempts=0;
  if(!_stage) {
    NSArray *records=[_menu valueForKey:@"records"];NSUInteger available=0;for(NSDictionary *r in records)if([self row:r[@"name"]].enabled)available++;
    [self check:records.count==19 && available==17 name:@"renamed CHD library title exposes actual 19 FFVII entries, 17 supported switches"];
    NSArray *sections=_root.builder();
    [self check:sections.count==3 && [sections[0] rows].count==2 && [sections[1] rows].count==19 name:@"phone menu places FFVII switches immediately after search and disable-all, before advanced tools"];
    [self check:[[self row:@"cheatFind"].detail containsString:@"libretro"] name:@"direct search identifies its available PS1 source"];
    [self check:_menu.enabledCount==0 && _applied.count==0 name:@"PS1 discovery leaves every code off"];
    VerifyCheatPresentation(_menu,_checks,@"Final Fantasy VII");
    [_page rebuild];
    NSUInteger unavailable=0;
    NSArray *visibleRows=((LibretroMenuSection *)_page.builder()[1]).rows;
    for(NSUInteger i=0;i<visibleRows.count;i++)if(!((LibretroMenuRow *)visibleRows[i]).enabled){
      [_page tableView:_page.tableView didSelectRowAtIndexPath:[NSIndexPath indexPathForRow:i inSection:1]];
      unavailable++;break;
    }
    [self check:unavailable && _page.pushedPage!=nil && _applied.count==0 name:@"disabled PS1 switch still opens read-only details through actual table selection without activation"];
    LibretroMenuRow *gil=[self row:@"Max Gil"];if(gil.toggle)gil.toggle(_page,YES);
    [self check:_page.confirmation!=nil && _applied.count==0 name:@"library title match requires version confirmation before native dispatch"];
    if(_page.confirmation){_page.confirmation();_page.confirmation=nil;}
    [self check:[_applied.lastObject isEqual:@[@"8009D260 967F+8009D262 0098"]] name:@"Max Gil switch dispatches complete real GameShark program"];
    LibretroMenuRow *phs=[self row:@"Save and use PHS Anywhere"];if(phs.toggle)phs.toggle(_page,YES);
    [self check:_menu.enabledCount==2 && [_applied.lastObject count]==2 name:@"PS1 switches allow simultaneous programs"];
    LibretroMenuRow *all=[self row:@"cheatDisableAll"];if(all.action)all.action(_page);
    [self check:_menu.enabledCount==0 && [_applied.lastObject count]==0 name:@"PS1 disable-all dispatches an empty program list"];
    NSData *digimon=[NSData dataWithContentsOfFile:[NSBundle.mainBundle.bundlePath stringByAppendingPathComponent:@"digimon-world-original.cht"]];
    NSError *parseError=nil;NSArray *parsed=[LibretroCheats parseCHT:digimon error:&parseError];
    [self check:parsed.count==56 && !parseError name:@"actual reviewed Digimon World fixture parses all 56 entries"];
    NSMutableArray *digimonRecords=[NSMutableArray array];
    for(NSDictionary *raw in parsed){NSMutableDictionary *r=[raw mutableCopy];r[@"game"]=@"Digimon World (USA, Europe) (GameShark)";r[@"uncertain"]=@YES;r[@"source"]=@"libretro";[digimonRecords addObject:r];}
    [_menu merge:digimonRecords];
    // Stress metadata and raw code size independently of the compact main cell.
    NSMutableString *longCode=[NSMutableString string];for(NSUInteger n=0;n<2000;n++)[longCode appendString:@"80000000 0001+"];
    [_menu merge:@[@{@"name":@"Long multi-line program with an intentionally long descriptive name that must wrap without colliding with its switch",@"code":longCode,@"handler":@0,@"game":@"Digimon World",@"source":@"libretro",@"revision":[@"a" stringByPaddingToLength:2048 withString:@"a" startingAtIndex:0]}]];
    VerifyCheatPresentation(_menu,_checks,@"Digimon World + FFVII + long program");
    _stage=1;dispatch_queue_t queue=[_menu valueForKey:@"queue"];
    dispatch_async(queue,^{dispatch_async(dispatch_get_main_queue(),^{
      self.folder=[self.folder stringByAppendingPathComponent:@"French"];
      [self create:@"Final Fantasy VII (France) (Disc 1)"];[self next];
    });});return;
  }
  [self check:[[_menu valueForKey:@"records"] count]==0 name:@"French FFVII does not automatically receive USA codes"];
  NSMutableDictionary *identity=[[_menu valueForKey:@"identity"] mutableCopy];
  identity[@"title"]=@"renamed-by-user";identity[@"serialTitles"]=@[@"Final Fantasy VII (France) (Disc 1)"];
  [_menu setValue:identity forKey:@"identity"];
  LibretroMenuRow *find=[self row:@"cheatFind"];if(find.action)find.action(_page);
  [self check:_page.pushedPage!=nil name:@"one search action opens results across sources when automatic match is empty"];
  NSArray *sections=_page.pushedPage.builder ? _page.pushedPage.builder() : @[];NSUInteger candidates=0;
  for(LibretroMenuSection *s in sections)for(LibretroMenuRow *r in s.rows)if([r.title isEqual:@"Final Fantasy VII (USA)"])candidates++;
  [self check:candidates==1 name:@"version picker reveals available USA catalogue instead of a blank source selector"];
  [self check:[[_menu valueForKey:@"gameSearch"] isEqual:@"final fantasy vii"] name:@"empty search uses the identified disc title instead of a renamed filename"];
  [[_menu valueForKey:@"installed"] removeAllObjects];
  [self check:[[self row:@"cheatFind"].detail isEqual:@"cheatNoSources"] name:@"a console with no usable source has an explicit explanation"];
  _finish();
}
@end
static void RunPSXCheatMenuProbe(NSMutableArray *checks,dispatch_block_t completion) {
  PSXCheatMenuProbe *probe=[PSXCheatMenuProbe new];probe.checks=checks;probe.applied=[NSMutableArray array];probe.finish=completion;
  probe.folder=DocumentsPath([@"PSXCheatMenuProbe/" stringByAppendingString:NSUUID.UUID.UUIDString]);
  [NSFileManager.defaultManager createDirectoryAtPath:probe.folder withIntermediateDirectories:YES attributes:nil error:nil];
  probe.content=[probe.folder stringByAppendingPathComponent:@"renamed.chd"];
  [@"Original synthetic container fixture, not a disc image" writeToFile:probe.content atomically:YES encoding:NSUTF8StringEncoding error:nil];
  probe.page=[[CheatConfirmationProbe alloc] initWithTitle:@"PS1 cheats" builder:^NSArray *{return @[];}];[probe.page loadViewIfNeeded];
  [probe create:@"Final Fantasy VII"];[probe next];
}
