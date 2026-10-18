// SPDX-License-Identifier: GPL-3.0-or-later
#import "Public/NeoUnifiedCheatList.h"
#import "Public/NeoUnifiedCheatCatalog.h"
#import "NeoUnifiedCheatBrowser.h"
#import <UniformTypeIdentifiers/UniformTypeIdentifiers.h>

static NSString *NCLString(id value) { return [value isKindOfClass:NSString.class] ? value : @""; }
static NSArray *NCLArray(id value) { return [value isKindOfClass:NSArray.class] ? value : @[]; }
static BOOL NCLAppend(NSDictionary *program, NSDictionary *index, NSMutableSet *visiting,
                      NSMutableSet *seen, NSMutableArray *ordered, BOOL (^accepts)(NSDictionary *), NSUInteger depth) {
  NSString *key=NCLString(program[@"id"]);
  if (!key.length || depth>128 || ordered.count>=512 || [visiting containsObject:key]) return NO;
  if ([seen containsObject:key]) return YES;
  if (![program[@"status"] isEqual:@"available"] || NCLArray(program[@"parameters"]).count || !accepts(program)) return NO;
  [visiting addObject:key];
  for (id dependency in NCLArray(program[@"dependencies"]))
    if (![dependency isKindOfClass:NSString.class] || !index[dependency] ||
        !NCLAppend(index[dependency],index,visiting,seen,ordered,accepts,depth+1)) return NO;
  NSMutableDictionary *disabled=[program mutableCopy]; disabled[@"enabled"]=@NO;
  [visiting removeObject:key]; [seen addObject:key]; [ordered addObject:disabled]; return YES;
}

@interface NeoUnifiedCheatList () <UIDocumentPickerDelegate>
@property(nonatomic, copy) NSDictionary *state;
@property(nonatomic, copy) NSArray *selections;
@property(nonatomic, copy) NSArray *rows;
@property(nonatomic, copy) NSString *scope;
@property(nonatomic, strong) NSMutableDictionary *links;
@property(nonatomic) NSUInteger generation;
@property(nonatomic) BOOL busy;
@property(nonatomic) BOOL discovering;
@property(nonatomic) BOOL closed;
@property(nonatomic, strong) id observer;
@end

@implementation NeoUnifiedCheatList
- (instancetype)init { return [super initWithStyle:UITableViewStyleInsetGrouped]; }
- (NSString *)text:(NSString *)key { return [NeoUnifiedCheatBrowser localizedText:key locale:self.locale ?: @"en"]; }
+ (NSArray *)selectionsForGame:(NSDictionary *)game programs:(NSArray *)programs accepts:(BOOL (^)(NSDictionary *))accepts {
  NSMutableDictionary *index=[NSMutableDictionary dictionary];
  for (NSDictionary *program in programs) if ([program isKindOfClass:NSDictionary.class] && NCLString(program[@"id"]).length) index[program[@"id"]]=program;
  NSMutableArray *result=[NSMutableArray array];
  for (NSDictionary *program in programs) {
    NSMutableArray *ordered=[NSMutableArray array];
    if (!NCLAppend(program,index,[NSMutableSet set],[NSMutableSet set],ordered,accepts,0)) continue;
    NSMutableSet *groups=[NSMutableSet set]; BOOL conflict=NO;
    for (NSDictionary *part in ordered) {
      NSMutableSet *this=[NSMutableSet setWithArray:NCLArray(part[@"exclusive_groups"])];
      if (NCLString(part[@"exclusive_group"]).length) [this addObject:part[@"exclusive_group"]];
      if ([groups intersectsSet:this]) conflict=YES; [groups unionSet:this];
    }
    if (!conflict) [result addObject:@{@"key":[NSString stringWithFormat:@"%@|%@",game[@"identity_group"] ?: game[@"id"],program[@"id"]],
        @"name":NCLString(program[@"name"]),@"game":game,@"programs":ordered}];
  }
  return result;
}
- (void)viewDidLoad {
  [super viewDidLoad]; self.title=[self text:@"programs"];
  self.overrideUserInterfaceStyle=UIUserInterfaceStyleDark;
  self.tableView.rowHeight=UITableViewAutomaticDimension; self.tableView.estimatedRowHeight=64;
  __weak typeof(self) weakSelf=self;
  self.observer=[NSNotificationCenter.defaultCenter addObserverForName:NeoUnifiedCheatCatalogDidInstallNotification
      object:NeoUnifiedCheatCatalog.sharedCatalog queue:NSOperationQueue.mainQueue usingBlock:^(NSNotification *note) { [weakSelf reloadCheats]; }];
}
- (void)viewWillAppear:(BOOL)animated { [super viewWillAppear:animated]; self.closed=NO; [self reloadCheats]; }
- (void)viewDidDisappear:(BOOL)animated {
  [super viewDidDisappear:animated];
  if (self.isMovingFromParentViewController || self.navigationController.isBeingDismissed) { self.closed=YES; self.generation++; }
}
- (void)dealloc { if (_observer) [NSNotificationCenter.defaultCenter removeObserver:_observer]; }
- (void)openRPCS3Import {
  if (self.busy || ![self.state[@"available"] boolValue]) return;
  UIDocumentPickerViewController *picker=[[UIDocumentPickerViewController alloc] initForOpeningContentTypes:@[UTTypeJSON] asCopy:YES];
  picker.delegate=self; picker.allowsMultipleSelection=NO; [self presentViewController:picker animated:YES completion:nil];
}
- (void)documentPicker:(UIDocumentPickerViewController *)picker didPickDocumentsAtURLs:(NSArray<NSURL *> *)urls {
  if (self.busy || self.closed || urls.count!=1) return;
  NSURL *url=urls.firstObject; BOOL access=[url startAccessingSecurityScopedResource];
  NSDictionary *attributes=[NSFileManager.defaultManager attributesOfItemAtPath:url.path error:nil];
  NSData *data=attributes && attributes.fileSize<=2*1024*1024 ? [NSData dataWithContentsOfURL:url] : nil;
  if (access) [url stopAccessingSecurityScopedResource];
  id parsed=data ? [NSJSONSerialization JSONObjectWithData:data options:0 error:nil] : nil;
  if (![parsed isKindOfClass:NSDictionary.class] || ![[parsed[@"Version"] description] isEqual:@"1.2"]) { [self showFailure]; return; }
  NSString *serial=@"",*version=NCLString(self.state[@"identity"][@"revision"]);
  for (NSDictionary *identifier in self.state[@"identity"][@"identities"])
    if ([identifier[@"scheme"] isEqual:@"ps3-title-id"]) serial=NCLString(identifier[@"value"]);
  NSMutableArray *imports=[NSMutableArray array];
  for (NSString *hash in parsed) {
    if ([hash isEqual:@"Version"]) continue;
    if (![hash isKindOfClass:NSString.class] || ![hash hasPrefix:@"PPU-"] || hash.length!=44 || ![parsed[hash] isKindOfClass:NSDictionary.class]) { [self showFailure]; return; }
    for (NSString *name in parsed[hash]) {
      NSDictionary *patch=parsed[hash][name]; if (![patch isKindOfClass:NSDictionary.class] || ![patch[@"Games"] isKindOfClass:NSDictionary.class]) { [self showFailure]; return; }
      NSString *title=nil; BOOL all=NO;
      for (NSString *candidate in patch[@"Games"]) {
        id serials=patch[@"Games"][candidate]; if (![serials isKindOfClass:NSDictionary.class]) continue;
        NSArray *versions=NCLArray(serials[serial]);
        if ([versions containsObject:version] || [versions containsObject:@"All"]) { title=candidate; all=[versions containsObject:@"All"]; break; }
      }
      if (!title) continue; // a multi-game document never targets other titles.
      NSDictionary *document=@{@"Version":@"1.2",hash:@{name:patch}};
      NSDictionary *program=@{@"id":NSUUID.UUID.UUIDString,@"name":name,@"code":@"JSON",@"dialect":@"rpcs3-yaml",@"status":@"available",@"enabled":@NO,@"native_document":document,@"parameters":@[],@"dependencies":@[]};
      if (!self.accepts(program) || imports.count>=512) { [self showFailure]; return; }
      NSDictionary *game=@{@"system":@"ps3",@"title":title,@"revision":all?@"":version,@"version_scope":all?@"all":@"",@"edition_confirmed":@YES,
          @"identities":@[@{@"type":@"serial",@"value":serial,@"scheme":@"ps3-title-id"},@{@"type":@"ppu_hash",@"value":[hash substringFromIndex:4],@"scheme":@"rpcs3-ppu-hash"}]};
      [imports addObject:@{@"game":game,@"programs":@[program]}];
    }
  }
  if (!imports.count) { [self showFailure]; return; }
  self.busy=YES; [self importDisabled:imports index:0 generation:self.generation];
}
- (void)importDisabled:(NSArray *)imports index:(NSUInteger)index generation:(NSUInteger)generation {
  if (self.closed || self.generation!=generation) return;
  if (index>=imports.count) { self.busy=NO; [self reloadCheats]; return; }
  __weak typeof(self) weakSelf=self;
  self.install(imports[index][@"game"],imports[index][@"programs"],^(NSDictionary *item,NSError *error) {
    dispatch_async(dispatch_get_main_queue(),^{
      NeoUnifiedCheatList *menu=weakSelf; if (!menu || menu.closed || menu.generation!=generation) return;
      if (!item || error) { menu.busy=NO; [menu showFailure]; [menu reloadCheats]; return; }
      [menu importDisabled:imports index:index+1 generation:generation];
    });
  });
}
- (void)showFailure { self.navigationItem.prompt=[self text:@"importFailed"]; [self.tableView reloadData]; }
- (void)rebuild {
  NSMutableDictionary *native=[NSMutableDictionary dictionary];
  for (NSDictionary *item in NCLArray(self.state[@"items"])) if (NCLString(item[@"key"]).length) native[item[@"key"]]=item;
  NSMutableSet *used=[NSMutableSet set]; NSMutableArray *rows=[NSMutableArray array];
  for (NSDictionary *selection in self.selections) {
    NSString *key=self.links[selection[@"key"]]; NSDictionary *item=key ? native[key] : nil;
    NSMutableDictionary *row=[selection mutableCopy];
    if (item) { row[@"native"]=item; [used addObject:key]; }
    [rows addObject:row];
  }
  for (NSDictionary *item in NCLArray(self.state[@"items"])) if (![used containsObject:NCLString(item[@"key"])])
    [rows addObject:@{@"key":NCLString(item[@"key"]),@"name":NCLString(item[@"name"]),@"native":item}];
  self.rows=rows; [self.tableView reloadData];
}
- (void)reloadCheats {
  if (!self.readState || self.busy || self.closed) return;
  NSUInteger generation=++self.generation; self.discovering=YES;
  __weak typeof(self) weakSelf=self;
  self.readState(^(NSDictionary *state) {
    dispatch_async(dispatch_get_main_queue(),^{
      NeoUnifiedCheatList *menu=weakSelf; if (!menu || menu.closed || menu.generation!=generation) return;
      menu.state=state ?: @{};
      NSData *scope=[NSJSONSerialization dataWithJSONObject:@{@"engine":menu.engine ?: @"",@"identity":state[@"identity"] ?: @{}}
          options:NSJSONWritingSortedKeys error:nil];
      menu.scope=[@"NeoStation.DirectCheats." stringByAppendingString:[scope base64EncodedStringWithOptions:0] ?: @""];
      menu.links=[[NSUserDefaults.standardUserDefaults dictionaryForKey:menu.scope] mutableCopy] ?: [NSMutableDictionary dictionary];
      menu.selections=@[]; [menu rebuild];
      if (![state[@"available"] boolValue]) { menu.discovering=NO; return; }
      [NeoUnifiedCheatCatalog.sharedCatalog gamesForIdentity:state[@"identity"] ?: @{} completion:^(NSArray *games,NSError *error) {
        NeoUnifiedCheatList *owner=weakSelf; if (!owner || owner.closed || owner.generation!=generation) return;
        NSMutableArray *pending=[NSMutableArray array];
        for (NSDictionary *game in games) if ([game[@"installed"] boolValue] && ![game[@"archived"] boolValue] && ![game[@"update_available"] boolValue] && pending.count<64) [pending addObject:game];
        if (!pending.count) { owner.discovering=NO; [owner rebuild]; return; }
        __block NSUInteger remaining=pending.count; NSMutableArray *choices=[NSMutableArray array];
        // Serial catalogue queue/worker bounds remain owned by the service.
        for (NSDictionary *game in pending) [NeoUnifiedCheatCatalog.sharedCatalog cheatsForGame:game completion:^(NSArray *programs,NSError *problem) {
          NeoUnifiedCheatList *current=weakSelf; if (!current || current.closed || current.generation!=generation) return;
          if (!problem) for (NSDictionary *selection in [NeoUnifiedCheatList selectionsForGame:game programs:programs accepts:current.accepts]) {
            if (choices.count>=4096) break; [choices addObject:selection];
          }
          if (--remaining==0) {
            [choices sortUsingComparator:^NSComparisonResult(NSDictionary *a,NSDictionary *b) { return [a[@"name"] localizedStandardCompare:b[@"name"]]; }];
            current.selections=choices; current.discovering=NO; [current rebuild];
          }
        }];
      }];
    });
  });
}
- (NSInteger)numberOfSectionsInTableView:(UITableView *)tableView { return 2; }
- (NSInteger)tableView:(UITableView *)tableView numberOfRowsInSection:(NSInteger)section { return section==0 ? 1+(self.importAction ? 1 : 0) : self.rows.count; }
- (NSString *)tableView:(UITableView *)tableView titleForFooterInSection:(NSInteger)section {
  if (section==0) return nil;
  if (self.discovering) return [self text:@"loading"];
  NSString *help=NCLString(self.state[@"help"]);
  return self.rows.count ? help : [NSString stringWithFormat:@"%@%@%@",[self text:@"noMatches"],help.length ? @"\n" : @"",help];
}
- (UITableViewCell *)tableView:(UITableView *)tableView cellForRowAtIndexPath:(NSIndexPath *)path {
  UITableViewCell *cell=[[UITableViewCell alloc] initWithStyle:UITableViewCellStyleSubtitle reuseIdentifier:nil];
  cell.textLabel.numberOfLines=0; cell.detailTextLabel.numberOfLines=0;
  if (path.section==0) {
    cell.textLabel.text=[self text:path.row==0 ? @"downloadAll" : @"directImport"];
    cell.accessibilityIdentifier=path.row==0 ? @"directCheats.downloadAll" : @"directCheats.import";
    if(path.row==1 && [self.engine isEqual:@"rpcs3"])cell.detailTextLabel.text=@"RPCS3 · JSON";
  } else {
    NSDictionary *row=self.rows[path.row],*item=row[@"native"];
    cell.textLabel.text=row[@"name"];
    cell.detailTextLabel.text=item ? NCLString(item[@"detail"]) : NCLString(row[@"game"][@"revision"]);
    UISwitch *toggle=[UISwitch new]; toggle.on=[item[@"enabled"] boolValue]; toggle.tag=path.row;
    toggle.enabled=!self.busy && [self.state[@"available"] boolValue] && ![self.state[@"hardcore"] boolValue] && ![item[@"readOnly"] boolValue];
    toggle.accessibilityLabel=row[@"name"]; toggle.accessibilityIdentifier=@"directCheats.toggle";
    [toggle addTarget:self action:@selector(toggle:) forControlEvents:UIControlEventValueChanged]; cell.accessoryView=toggle;
  }
  cell.userInteractionEnabled=!self.busy; return cell;
}
- (void)applyRow:(NSDictionary *)row enabled:(BOOL)enabled {
  if (self.busy || !self.setEnabled) return; self.busy=YES; [self.tableView reloadData];
  NSUInteger generation=self.generation; __weak typeof(self) weakSelf=self;
  void (^activate)(NSDictionary *,NSError *)=^(NSDictionary *item,NSError *error) {
    NeoUnifiedCheatList *menu=weakSelf; if (!menu || menu.closed || menu.generation!=generation || menu.navigationController.topViewController!=menu || !menu.viewIfLoaded.window || menu.navigationController.isBeingDismissed) return;
    if (!item || error) { menu.busy=NO; [menu showFailure]; [menu reloadCheats]; return; }
    if (row[@"game"]) { menu.links[row[@"key"]]=item[@"key"]; [NSUserDefaults.standardUserDefaults setObject:menu.links forKey:menu.scope]; }
    menu.setEnabled(item,enabled,^(BOOL success) { dispatch_async(dispatch_get_main_queue(),^{
      NeoUnifiedCheatList *current=weakSelf; if (!current || current.closed || current.generation!=generation) return;
      current.busy=NO; if (!success) [current showFailure]; [current reloadCheats];
    }); });
  };
  if (row[@"native"]) activate(row[@"native"],nil);
  else if (self.install) {
    NSMutableDictionary *game=[row[@"game"] mutableCopy]; game[@"edition_confirmed"]=@YES;
    self.install(game,row[@"programs"],activate);
  } else { self.busy=NO; [self showFailure]; }
}
- (void)toggle:(UISwitch *)sender {
  if (sender.tag<0 || sender.tag>=(NSInteger)self.rows.count || self.busy) return;
  NSDictionary *row=self.rows[sender.tag]; BOOL enabled=sender.on;
  NSString *editionKey=[@"edition|" stringByAppendingString:NCLString(row[@"game"][@"identity_group"] ?: row[@"game"][@"id"])];
  if (!row[@"native"] && ![row[@"game"][@"match"] isEqual:@"exact"] && ![self.links[editionKey] isEqual:@"confirmed"]) {
    sender.on=NO;
    UIAlertController *alert=[UIAlertController alertControllerWithTitle:[self text:@"editionConfirmTitle"]
        message:[NSString stringWithFormat:@"%@\n%@",NCLString(row[@"game"][@"title"]),NCLString(row[@"game"][@"revision"])] preferredStyle:UIAlertControllerStyleAlert];
    __weak typeof(self) weakSelf=self;
    [alert addAction:[UIAlertAction actionWithTitle:[self text:@"cancel"] style:UIAlertActionStyleCancel handler:nil]];
    [alert addAction:[UIAlertAction actionWithTitle:[self text:@"chooseEdition"] style:UIAlertActionStyleDefault handler:^(UIAlertAction *a) { weakSelf.links[editionKey]=@"confirmed"; [weakSelf applyRow:row enabled:enabled]; }]];
    [self presentViewController:alert animated:YES completion:nil];
  } else [self applyRow:row enabled:enabled];
}
- (void)tableView:(UITableView *)tableView didSelectRowAtIndexPath:(NSIndexPath *)path {
  [tableView deselectRowAtIndexPath:path animated:YES]; if (self.busy || path.section!=0) return;
  if (path.row==1) { if (self.importAction) self.importAction(self); return; }
  self.busy=YES; [self.tableView reloadData]; __weak typeof(self) weakSelf=self;
  [NeoUnifiedCheatCatalog.sharedCatalog installAllWithProgress:^(NSDictionary *progress) {
    NeoUnifiedCheatList *menu=weakSelf; if (!menu || menu.closed) return;
    menu.navigationItem.prompt=[NSString stringWithFormat:@"%@ / %@",progress[@"completed_packs"],progress[@"total_packs"]];
  } completion:^(NSDictionary *result,NSError *error) {
    NeoUnifiedCheatList *menu=weakSelf; if (!menu || menu.closed) return;
    menu.busy=NO; menu.navigationItem.prompt=[menu text:error ? @"downloadFailed" : @"ready"]; [menu reloadCheats];
  }];
}
@end
