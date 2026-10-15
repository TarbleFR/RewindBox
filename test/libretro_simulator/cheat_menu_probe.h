#import "LibretroCheatMenu.h"
#import "LibretroSessionMenu.h"
@interface LibretroCheatMenu (MenuProbePrivate)
- (void)merge:(NSArray *)records;
- (void)documentPicker:(UIDocumentPickerViewController *)controller didPickDocumentsAtURLs:(NSArray<NSURL *> *)urls;
@end
@interface CheatConfirmationProbe : LibretroMenuPage
@property(nonatomic, copy) dispatch_block_t confirmation;
@end
@implementation CheatConfirmationProbe
- (void)confirmWithTitle:(NSString *)title message:(NSString *)message action:(NSString *)action cancelTitle:(NSString *)cancel destructive:(BOOL)destructive handler:(dispatch_block_t)handler {
  self.confirmation = handler;
}
@end
@interface CheatMenuProbe : NSObject
@property(nonatomic, strong) LibretroCheatMenu *menu;
@property(nonatomic, strong) LibretroMenuPage *root;
@property(nonatomic, strong) CheatConfirmationProbe *page;
@property(nonatomic, strong) NSMutableArray *checks;
@property(nonatomic, strong) NSMutableArray *applied;
@property(nonatomic, copy) dispatch_block_t finish;
@property(nonatomic, copy) NSString *folder, *content;
@property(nonatomic) NSUInteger stage, attempts;
- (void)next;
@end
@implementation CheatMenuProbe
- (void)check:(BOOL)passed name:(NSString *)name { [_checks addObject:@{@"name":name,@"passed":@(passed)}]; }
- (LibretroMenuRow *)row:(NSString *)title {
  for (LibretroMenuSection *section in _root.builder()) for (LibretroMenuRow *row in section.rows)
    if ([row.title isEqual:title]) return row;
  return nil;
}
- (void)create {
  __weak CheatMenuProbe *weakSelf = self;
  _menu = [[LibretroCheatMenu alloc] initWithDirectory:_folder console:@"nes" core:@"nestopia" contentPath:_content
    legacy:@[] text:^NSString *(NSString *key) { return key; } apply:^(NSArray *codes) { [weakSelf.applied addObject:codes]; }];
  _root = [_menu rootPage];
}
- (void)next {
  BOOL pending = ![[_menu valueForKey:@"ready"] boolValue] || [[_menu valueForKey:@"busy"] boolValue];
  if (pending && _attempts++ < 200) {
    dispatch_after(dispatch_time(DISPATCH_TIME_NOW,50*NSEC_PER_MSEC),dispatch_get_main_queue(),^{[self next];}); return;
  }
  if (pending) { [self check:NO name:@"menu initialization/import deadline"]; self.finish(); return; }
  _attempts=0;
  if (_stage == 0) {
    [_menu merge:@[
      @{@"name":@"Counter",@"code":@"0024:7F",@"handler":@0,@"enabled":@YES,@"source":@"first",@"license":@"Unlicense"},
      @{@"name":@"Duplicate",@"code":@"0024:7f",@"handler":@0,@"source":@"second",@"license":@"CC BY-SA 4.0"},
      @{@"name":@"Memory 1",@"code":@"",@"handler":@1,@"raw":@{@"address":@"12",@"value":@"1"}},
      @{@"name":@"Memory 2",@"code":@"",@"handler":@1,@"raw":@{@"address":@"13",@"value":@"1"}},
      @{@"name":@"Invalid",@"code":@"not a code",@"handler":@0}]];
    NSArray *records=[_menu valueForKey:@"records"];
    [self check:records.count==4 name:@"native duplicates merge while distinct memory-engine entries remain separate"];
    [self check:[records.firstObject[@"origins"] count]==2 name:@"deduplication retains both source licences"];
    LibretroMenuRow *counter=[self row:@"Counter"];
    [self check:counter.enabled && !counter.toggleOn && _applied.count==0 name:@"imported enabled flag never activates a cheat"];
    [self check:![self row:@"Memory 1"].enabled && ![self row:@"Invalid"].enabled name:@"unsupported memory engine and invalid native codes have disabled switches"];
    counter.toggle(_page,YES);
    [self check:_page.confirmation!=nil && _applied.count==0 name:@"first activation waits for explicit save-risk confirmation"];
    if(_page.confirmation){_page.confirmation();_page.confirmation=nil;}
    [self check:[_applied.lastObject isEqual:@[@"0024:7F"]] name:@"confirmed menu activation sends the validated code"];
    [self row:@"Counter"].toggle(_page,NO);
    [self check:[_applied.lastObject count]==0 name:@"menu deactivation clears the host code list"];
    [self row:@"cheatRemember"].toggle(_page,YES);
    [self row:@"Counter"].toggle(_page,YES);
    _stage=1;
    // The same production picker delegate processes an actual .cht file.
    NSString *file=[_folder stringByAppendingPathComponent:@"import.cht"];
    [NSFileManager.defaultManager createDirectoryAtPath:_folder withIntermediateDirectories:YES attributes:nil error:nil];
    [@"cheats=1\ncheat0_desc=Imported\ncheat0_code=0010:44\ncheat0_enable=true" writeToFile:file atomically:YES encoding:NSUTF8StringEncoding error:nil];
    [_menu documentPicker:nil didPickDocumentsAtURLs:@[[NSURL fileURLWithPath:file]]];
  } else if (_stage == 1) {
    [self check:[self row:@"Imported"].enabled && ![self row:@"Imported"].toggleOn name:@"local file import creates an available but disabled cheat"];
    // save() uses a serial queue; wait behind every pending write before reload.
    dispatch_queue_t queue=[_menu valueForKey:@"queue"];
    dispatch_async(queue,^{dispatch_async(dispatch_get_main_queue(),^{
      self.stage=2; [self create]; [self.applied removeAllObjects]; [self next];
    });}); return;
  } else {
    [self check:![self row:@"Counter"].toggleOn && _applied.count==0 name:@"saved selections never activate when a game menu is recreated"];
    LibretroMenuRow *restore=[self row:@"cheatRestore"];
    [self check:restore!=nil && [self row:@"Imported"]!=nil name:@"per-content preferences retain imported entries and explicit restore action"];
    restore.action(_page);
    [self check:_applied.count==0 && _page.confirmation!=nil name:@"restoring preferences also requires explicit confirmation"];
    if(_page.confirmation){_page.confirmation();_page.confirmation=nil;}
    [self check:[_applied.lastObject isEqual:@[@"0024:7F"]] name:@"explicit restore only enables previously selected compatible cheats"];
    self.finish(); return;
  }
  dispatch_after(dispatch_time(DISPATCH_TIME_NOW,50*NSEC_PER_MSEC),dispatch_get_main_queue(),^{[self next];});
}
@end
static void RunCheatMenuProbe(NSMutableArray *checks, dispatch_block_t completion) {
  CheatMenuProbe *probe=[CheatMenuProbe new]; probe.checks=checks; probe.applied=[NSMutableArray array]; probe.finish=completion;
  probe.folder=DocumentsPath([@"CheatMenuProbe/" stringByAppendingString:NSUUID.UUID.UUIDString]);
  probe.content=[NSBundle.mainBundle.bundlePath stringByAppendingPathComponent:@"content/cheat-probe.nes"];
  probe.page=[[CheatConfirmationProbe alloc] initWithTitle:@"Cheat menu test" builder:^NSArray *{return @[];}];
  [probe create]; [probe next];
}
