// SPDX-License-Identifier: GPL-3.0-or-later
#import "Public/NeoUnifiedCheatList.h"
#import "Public/NeoUnifiedCheatCatalog.h"
#import "NeoUnifiedCheatBrowser.h"
#import <UniformTypeIdentifiers/UniformTypeIdentifiers.h>
#import <CommonCrypto/CommonDigest.h>
#import <objc/runtime.h>

static NSString *NCLString(id value) { return [value isKindOfClass:NSString.class] ? value : @""; }
static NSArray *NCLArray(id value) { return [value isKindOfClass:NSArray.class] ? value : @[]; }
static char NCLSwitchRowKey;
static NSOperationQueue *NCLSelectionQueue(void) {
  static NSOperationQueue *queue;static dispatch_once_t once;dispatch_once(&once,^{
    queue=[NSOperationQueue new];queue.maxConcurrentOperationCount=2;queue.qualityOfService=NSQualityOfServiceUserInitiated;
  });return queue;
}
static NSString *NCLExecutionKey(NSArray *programs) {
  NSMutableArray *body=[NSMutableArray array];
  for(NSDictionary *program in programs) {
    NSString *dialect=NCLString(program[@"dialect"]),*code=NCLString(program[@"code"]);
    id instructions=code;
    if([dialect isEqual:@"pnach"]) {
      NSMutableArray *commands=[NSMutableArray array];
      for(NSString *line in [code componentsSeparatedByCharactersInSet:NSCharacterSet.newlineCharacterSet]) {
        NSString *text=[[line componentsSeparatedByString:@"//"] firstObject];
        text=[[text componentsSeparatedByCharactersInSet:NSCharacterSet.whitespaceCharacterSet] componentsJoinedByString:@""].lowercaseString;
        if([text hasPrefix:@"patch="])[commands addObject:text];
      }
      if(commands.count)instructions=commands;
    } else if([dialect isEqual:@"rpcs3-yaml"] && [program[@"native_document"] isKindOfClass:NSDictionary.class]) {
      NSMutableDictionary *document=[program[@"native_document"] mutableCopy];
      for(NSString *hash in [document.allKeys copy])if(![hash isEqual:@"Version"] && [document[hash] isKindOfClass:NSDictionary.class]) {
        NSMutableArray *patches=[NSMutableArray array];
        for(NSString *name in [document[hash] allKeys]) {
          NSMutableDictionary *patch=[document[hash][name] mutableCopy];
          // Names and attribution differ between mirrors. Execution scope,
          // instructions, order, groups and all other controls stay intact.
          [patch removeObjectsForKeys:@[@"Author",@"Notes",@"Patch Version"]];[patches addObject:patch];
        }
        document[hash]=patches;
      }
      instructions=document;
    }
    NSMutableDictionary *row=[NSMutableDictionary dictionaryWithDictionary:@{@"dialect":dialect,@"instructions":instructions}];
    for(NSString *key in @[@"handler",@"kind",@"exclusive_group",@"exclusive_groups",@"source_options"])
      if(program[key])row[key]=program[key];
    [body addObject:row];
  }
  NSData *data=[NSJSONSerialization dataWithJSONObject:body options:NSJSONWritingSortedKeys error:nil];
  if(!data)return @"";
  unsigned char hash[CC_SHA256_DIGEST_LENGTH];CC_SHA256(data.bytes,(CC_LONG)data.length,hash);
  NSMutableString *result=[NSMutableString string];for(NSUInteger i=0;i<sizeof(hash);i++)[result appendFormat:@"%02x",hash[i]];return result;
}
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
@property(nonatomic) BOOL downloading;
@property(nonatomic) BOOL catalogueInstalled;
@property(nonatomic) BOOL cataloguePartial;
@property(nonatomic) BOOL catalogueStateKnown;
@property(nonatomic, copy) NSString *downloadStatus;
@property(nonatomic, copy) NSString *catalogueStatus;
@property(nonatomic) NSTimeInterval lastDownloadDiscovery;
@property(nonatomic) NSTimeInterval lastDownloadStatusUpdate;
@property(nonatomic) BOOL closed;
@property(nonatomic, strong) id observer;
@property(nonatomic, strong) id progressObserver;
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
        @"name":NCLString(program[@"name"]),@"game":game,@"programs":ordered,@"execution_key":NCLExecutionKey(ordered)}];
  }
  return result;
}
+ (NSArray *)distinctSelections:(NSArray *)selections identity:(NSDictionary *)identity links:(NSDictionary *)links {
  NSMutableDictionary *groups=[NSMutableDictionary dictionary];
  BOOL identified=NCLArray(identity[@"identities"]).count>0;
  for(NSDictionary *selection in selections) {
    NSString *execution=NCLString(selection[@"execution_key"]);
    NSString *key=execution.length ? execution : selection[@"key"];
    if(!identified)key=[NSString stringWithFormat:@"%@|%@",selection[@"game"][@"identity_group"] ?: selection[@"game"][@"id"],key];
    NSMutableDictionary *previous=groups[key];
    NSMutableArray *equivalent=previous[@"equivalent_selections"] ?: [NSMutableArray array];
    NSMutableSet *aliases=previous[@"alias_keys"] ?: [NSMutableSet set];
    [equivalent addObject:selection];[aliases addObject:selection[@"key"]];
    BOOL linked=NCLString(links[selection[@"key"]]).length>0,oldLinked=previous && NCLString(links[previous[@"key"]]).length>0;
    BOOL exact=[selection[@"game"][@"match"] isEqual:@"exact"],oldExact=[previous[@"game"][@"match"] isEqual:@"exact"];
    BOOL prefer=!previous || (linked!=oldLinked ? linked : (exact!=oldExact ? exact : [selection[@"key"] compare:previous[@"key"]]==NSOrderedAscending));
    NSMutableDictionary *chosen=prefer ? [selection mutableCopy] : previous;
    chosen[@"equivalent_selections"]=equivalent;chosen[@"alias_keys"]=aliases;groups[key]=chosen;
  }
  NSMutableArray *result=[NSMutableArray array];
  for(NSMutableDictionary *row in groups.allValues) {
    NSMutableOrderedSet *notes=[NSMutableOrderedSet orderedSet];
    for(NSDictionary *source in row[@"equivalent_selections"]) {
      NSDictionary *program=NCLArray(source[@"programs"]).lastObject;
      if([program[@"feature"] isEqual:@"60fps"] && NCLString(program[@"notes"]).length)[notes addObject:program[@"notes"]];
    }
    row[@"source_notes"]=[notes.array componentsJoinedByString:@"\n"];
    [result addObject:row];
  }
  [result sortUsingComparator:^NSComparisonResult(NSDictionary *a,NSDictionary *b){NSComparisonResult name=[a[@"name"] localizedStandardCompare:b[@"name"]];return name!=NSOrderedSame ? name : [a[@"key"] compare:b[@"key"]];}];
  return result;
}
- (void)viewDidLoad {
  [super viewDidLoad]; self.title=[self text:@"programs"];
  self.overrideUserInterfaceStyle=UIUserInterfaceStyleDark;
  self.tableView.rowHeight=UITableViewAutomaticDimension; self.tableView.estimatedRowHeight=64;
  __weak typeof(self) weakSelf=self;
  self.observer=[NSNotificationCenter.defaultCenter addObserverForName:NeoUnifiedCheatCatalogDidInstallNotification
      object:NeoUnifiedCheatCatalog.sharedCatalog queue:NSOperationQueue.mainQueue usingBlock:^(NSNotification *note) { [weakSelf refreshDownloadState]; [weakSelf reloadCheats]; }];
  self.progressObserver=[NSNotificationCenter.defaultCenter addObserverForName:NeoUnifiedCheatCatalogProgressNotification
      object:NeoUnifiedCheatCatalog.sharedCatalog queue:NSOperationQueue.mainQueue usingBlock:^(NSNotification *note) {
    if(!weakSelf.closed)[weakSelf applyInstallationState:note.userInfo];
  }];
}
- (void)viewWillAppear:(BOOL)animated { [super viewWillAppear:animated]; self.closed=NO; [self refreshDownloadState]; [self reloadCheats]; }
- (void)viewDidDisappear:(BOOL)animated {
  [super viewDidDisappear:animated];
  if (self.isMovingFromParentViewController || self.navigationController.isBeingDismissed) { self.closed=YES; self.generation++; }
}
- (void)dealloc {
  if (_observer) [NSNotificationCenter.defaultCenter removeObserver:_observer];
  if (_progressObserver) [NSNotificationCenter.defaultCenter removeObserver:_progressObserver];
}
- (void)refreshDownloadState {
  __weak typeof(self) weakSelf=self;
  [NeoUnifiedCheatCatalog.sharedCatalog loadWithCompletion:^(NSDictionary *state,NSError *error) {
    NeoUnifiedCheatList *menu=weakSelf;if(!menu || menu.closed)return;
    if(state)[menu applyInstallationState:state];
    else {menu.catalogueStateKnown=YES;menu.downloadStatus=[menu text:@"loadFailed"];[menu.tableView reloadData];}
  }];
}
- (void)applyInstallationState:(NSDictionary *)state {
  NSString *phase=NCLString(state[@"installation_state"]);
  NSUInteger total=[state[@"total_packs"] unsignedIntegerValue],ready=[state[@"installed_packs"] unsignedIntegerValue];
  self.catalogueStateKnown=YES;
  self.downloading=[phase isEqual:@"installing"];
  self.catalogueInstalled=[phase isEqual:@"complete"] || (!phase.length && total && ready==total);
  self.cataloguePartial=[phase isEqual:@"partial"] || (!phase.length && ready && ready<total);
  NSDictionary *progress=[state[@"progress"] isKindOfClass:NSDictionary.class] ? state[@"progress"] : state;
  if(self.downloading) {
    NSString *status=[self text:[progress[@"phase"] isEqual:@"preparing"] ? @"loading" : @"progressPacks"];
    status=[status stringByReplacingOccurrencesOfString:@"{done}" withString:[progress[@"completed_packs"] description] ?: @"0"];
    self.downloadStatus=[status stringByReplacingOccurrencesOfString:@"{total}" withString:[progress[@"total_packs"] description] ?: @"0"];
  } else if(self.catalogueInstalled) self.downloadStatus=[self text:@"installedReady"];
  else if(self.cataloguePartial) self.downloadStatus=[self text:@"downloadExplanation"];
  NSTimeInterval now=NSDate.timeIntervalSinceReferenceDate;
  if(!self.downloading || now-self.lastDownloadStatusUpdate>=0.1) {
    self.lastDownloadStatusUpdate=now;
    [self.tableView reloadRowsAtIndexPaths:@[[NSIndexPath indexPathForRow:0 inSection:0]] withRowAnimation:UITableViewRowAnimationNone];
  }
  if(self.downloading && ready && !self.discovering && !self.busy && now-self.lastDownloadDiscovery>=1) {
    self.lastDownloadDiscovery=now;[self reloadCheats];
  }
}
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
      NSData *canonical=[NSJSONSerialization dataWithJSONObject:document options:NSJSONWritingSortedKeys error:nil];
      unsigned char digest[CC_SHA256_DIGEST_LENGTH];CC_SHA256(canonical.bytes,(CC_LONG)canonical.length,digest);
      NSMutableString *identifier=[NSMutableString string];for(NSUInteger i=0;i<sizeof(digest);i++)[identifier appendFormat:@"%02x",digest[i]];
      NSString *body=[[NSString alloc] initWithData:canonical encoding:NSUTF8StringEncoding];
      NSDictionary *program=@{@"id":identifier,@"name":name,@"code":body,@"dialect":@"rpcs3-yaml",@"status":@"available",@"enabled":@NO,@"native_document":document,@"parameters":@[],@"dependencies":@[]};
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
    if(!item)for(NSString *alias in selection[@"alias_keys"]){NSString *alternative=self.links[alias];if(alternative && native[alternative]){key=alternative;item=native[key];break;}}
    NSMutableDictionary *row=[selection mutableCopy];
    if (item) { row[@"native"]=item; [used addObject:key]; }
    [rows addObject:row];
  }
  for (NSDictionary *item in NCLArray(self.state[@"items"])) if (![used containsObject:NCLString(item[@"key"])])
    [rows addObject:@{@"key":NCLString(item[@"key"]),@"name":NCLString(item[@"name"]),@"native":item}];
  self.rows=rows; [self.tableView reloadData];
}
- (NSString *)detectedEdition {
  NSDictionary *identity=self.state[@"identity"];
  if (![identity[@"system"] isEqual:@"ps3"]) return @"";
  for (NSDictionary *identifier in NCLArray(identity[@"identities"])) if ([identifier[@"scheme"] isEqual:@"ps3-title-id"] && NCLString(identifier[@"value"]).length) {
    NSString *detail=[[self text:@"detectedEdition"] stringByReplacingOccurrencesOfString:@"{serial}" withString:identifier[@"value"]];
    NSString *revision=NCLString(identity[@"revision"]);
    return [detail stringByReplacingOccurrencesOfString:@"{revision}" withString:revision.length ? revision : [self text:@"unknown"]];
  }
  return @"";
}
- (void)explainMissingRevision:(NSDictionary *)identity generation:(NSUInteger)generation {
  if (![identity[@"system"] isEqual:@"ps3"] || !NCLString(identity[@"revision"]).length || ![self detectedEdition].length) return;
  NSMutableDictionary *withoutRevision=[identity mutableCopy]; [withoutRevision removeObjectForKey:@"revision"];
  __weak typeof(self) weakSelf=self;
  // Diagnostic lookup only: these rows never enter selections/imports. All
  // known serial/PPU/region/language conflicts remain enforced by the service.
  [NeoUnifiedCheatCatalog.sharedCatalog gamesForIdentity:withoutRevision completion:^(NSArray *games,NSError *error) {
    NeoUnifiedCheatList *menu=weakSelf; if (!menu || menu.closed || menu.generation!=generation || error) return;
    NSMutableSet *versions=[NSMutableSet set];
    for (NSDictionary *game in games) if (![game[@"archived"] boolValue] && NCLString(game[@"revision"]).length &&
        ![game[@"revision"] isEqual:identity[@"revision"]] && [NeoUnifiedCheatCatalog matchGame:game identity:withoutRevision])
      [versions addObject:game[@"revision"]];
    if (!versions.count) return;
    NSString *detail=[[menu text:@"otherRevisions"] stringByReplacingOccurrencesOfString:@"{versions}"
        withString:[[[versions allObjects] sortedArrayUsingSelector:@selector(compare:)] componentsJoinedByString:@", "]];
    menu.catalogueStatus=[NSString stringWithFormat:@"%@\n%@",[menu text:@"noMatches"],detail]; [menu rebuild];
  }];
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
      menu.selections=@[]; menu.catalogueStatus=nil; [menu rebuild];
      [NeoUnifiedCheatCatalog.sharedCatalog gamesForIdentity:state[@"identity"] ?: @{} completion:^(NSArray *games,NSError *error) {
        NeoUnifiedCheatList *owner=weakSelf; if (!owner || owner.closed || owner.generation!=generation) return;
        if (error) { owner.catalogueStatus=[owner text:@"lookupFailed"]; owner.discovering=NO; [owner rebuild]; return; }
        NSMutableArray *pending=[NSMutableArray array];
        BOOL needsDownload=NO;
        for (NSDictionary *game in games) if (![game[@"archived"] boolValue]) {
          if (([game[@"installed"] boolValue] || [game[@"cached_pack"] boolValue] || [game[@"download_requested"] boolValue]) && ![game[@"update_available"] boolValue]) {
            if (pending.count<64) [pending addObject:game];
          } else needsDownload=YES;
        }
        if (!pending.count) {
          owner.catalogueStatus=[owner text:needsDownload ? @"notInstalled" : @"noMatches"]; owner.discovering=NO; [owner rebuild];
          if (!needsDownload && !games.count) [owner explainMissingRevision:state[@"identity"] ?: @{} generation:generation];
          return;
        }
        NSMutableDictionary *context=[@{@"remaining":@(pending.count),@"choices":[NSMutableArray array]} mutableCopy];
        // Two bounded streams; show the first ready part immediately. Native
        // acceptance/closure hashing runs off main, without enabling anything.
        for(NSUInteger i=0;i<MIN((NSUInteger)2,pending.count);i++)[owner loadGames:pending context:context index:i generation:generation];
      }];
    });
  });
}
- (void)loadGames:(NSArray *)games context:(NSMutableDictionary *)context index:(NSUInteger)index generation:(NSUInteger)generation {
  if(index>=games.count || self.closed || self.generation!=generation)return;
  NSDictionary *game=games[index];__weak typeof(self) weakSelf=self;
  [NeoUnifiedCheatCatalog.sharedCatalog cheatsForGame:game completion:^(NSArray *programs,NSError *problem) {
    NeoUnifiedCheatList *menu=weakSelf;if(!menu || menu.closed || menu.generation!=generation)return;
    BOOL (^accepts)(NSDictionary *)=[menu.accepts copy];
    [NCLSelectionQueue() addOperationWithBlock:^{
      NSArray *additions=problem ? @[] : [NeoUnifiedCheatList selectionsForGame:game programs:programs accepts:accepts];
      dispatch_async(dispatch_get_main_queue(),^{
        NeoUnifiedCheatList *current=weakSelf;if(!current || current.closed || current.generation!=generation)return;
        if(problem)current.catalogueStatus=[current text:@"loadFailed"];
        NSMutableArray *choices=context[@"choices"];
        for(NSDictionary *selection in additions){if(choices.count>=4096)break;[choices addObject:selection];}
        context[@"remaining"]=@([context[@"remaining"] unsignedIntegerValue]-1);
        current.selections=[NeoUnifiedCheatList distinctSelections:choices identity:current.state[@"identity"] links:current.links];
        current.discovering=[context[@"remaining"] unsignedIntegerValue]>0;
        if(!current.discovering && !current.selections.count && !current.catalogueStatus)current.catalogueStatus=[current text:@"noCompatible"];
        [current rebuild];[current loadGames:games context:context index:index+2 generation:generation];
      });
    }];
  }];
}
- (NSInteger)numberOfSectionsInTableView:(UITableView *)tableView { return 2; }
- (NSInteger)tableView:(UITableView *)tableView numberOfRowsInSection:(NSInteger)section { return section==0 ? 1+(self.importAction ? 1 : 0) : self.rows.count; }
- (NSString *)tableView:(UITableView *)tableView titleForFooterInSection:(NSInteger)section {
  if (section==0) return nil;
  if (self.discovering && !self.rows.count) return [self text:@"loading"];
  NSString *help=NCLString(self.state[@"help"]);
  NSMutableArray *details=[NSMutableArray array];
  if (!self.rows.count) [details addObject:self.catalogueStatus ?: [self text:@"noMatches"]];
  NSString *edition=[self detectedEdition]; if (edition.length) [details addObject:edition];
  if (help.length) [details addObject:help];
  return [details componentsJoinedByString:@"\n"];
}
- (UITableViewCell *)tableView:(UITableView *)tableView cellForRowAtIndexPath:(NSIndexPath *)path {
  UITableViewCell *cell=[[UITableViewCell alloc] initWithStyle:UITableViewCellStyleSubtitle reuseIdentifier:nil];
  cell.textLabel.numberOfLines=0; cell.detailTextLabel.numberOfLines=0;
  if (path.section==0) {
    NSString *downloadKey=!self.catalogueStateKnown ? @"loading" : self.downloading ? @"downloading" : self.catalogueInstalled ? @"installedReady" : self.cataloguePartial ? @"resumeDownload" : @"downloadAll";
    cell.textLabel.text=[self text:path.row==0 ? downloadKey : @"directImport"];
    if (path.row==0) {
      cell.detailTextLabel.text=self.downloadStatus;
      if (self.downloading) { UIActivityIndicatorView *spinner=[[UIActivityIndicatorView alloc] initWithActivityIndicatorStyle:UIActivityIndicatorViewStyleMedium]; [spinner startAnimating]; cell.accessoryView=spinner; }
    }
    cell.accessibilityIdentifier=path.row==0 ? @"directCheats.downloadAll" : @"directCheats.import";
    if(path.row==1 && [self.engine isEqual:@"rpcs3"])cell.detailTextLabel.text=@"RPCS3 · JSON";
  } else {
    NSDictionary *row=self.rows[path.row],*item=row[@"native"];
    cell.textLabel.text=row[@"name"];
    cell.detailTextLabel.text=item ? NCLString(item[@"detail"]) : NCLString(row[@"game"][@"revision"]);
    NSDictionary *program=NCLArray(row[@"programs"]).lastObject;
    NSString *notes=NCLString(row[@"source_notes"]);
    if(!notes.length && [program[@"feature"] isEqual:@"60fps"])notes=NCLString(program[@"notes"]);
    if(notes.length)cell.detailTextLabel.text=[@[cell.detailTextLabel.text ?: @"",notes] componentsJoinedByString:@"\n"];
    UISwitch *toggle=[UISwitch new]; toggle.on=[item[@"enabled"] boolValue]; toggle.tag=path.row;
    toggle.enabled=!self.busy && [self.state[@"available"] boolValue] && ![self.state[@"hardcore"] boolValue] && ![item[@"readOnly"] boolValue];
    toggle.accessibilityLabel=row[@"name"]; toggle.accessibilityIdentifier=@"directCheats.toggle";
    objc_setAssociatedObject(toggle,&NCLSwitchRowKey,row[@"key"],OBJC_ASSOCIATION_COPY_NONATOMIC);
    [toggle addTarget:self action:@selector(toggle:) forControlEvents:UIControlEventValueChanged]; cell.accessoryView=toggle;
  }
  cell.userInteractionEnabled=!self.busy && !(path.section==0 && path.row==0 && (self.downloading || self.catalogueInstalled || !self.catalogueStateKnown)); return cell;
}
- (void)applyRow:(NSDictionary *)row enabled:(BOOL)enabled {
  if (self.busy || self.closed || !self.setEnabled || ![self.state[@"available"] boolValue] ||
      [self.state[@"hardcore"] boolValue] || [row[@"native"][@"readOnly"] boolValue]) return;
  self.busy=YES; [self.tableView reloadData];
  NSUInteger generation=self.generation; __weak typeof(self) weakSelf=self;
  void (^activate)(NSDictionary *,NSError *)=^(NSDictionary *item,NSError *error) {
    NeoUnifiedCheatList *menu=weakSelf; if (!menu || menu.closed || menu.generation!=generation || menu.navigationController.topViewController!=menu || !menu.viewIfLoaded.window || menu.navigationController.isBeingDismissed) return;
    if (!item || error) { menu.busy=NO; [menu showFailure]; [menu reloadCheats]; return; }
    if (row[@"game"]) { menu.links[row[@"key"]]=item[@"key"];for(NSString *alias in row[@"alias_keys"])menu.links[alias]=item[@"key"];
      [NSUserDefaults.standardUserDefaults setObject:menu.links forKey:menu.scope]; }
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
  if(self.busy)return;
  NSString *key=objc_getAssociatedObject(sender,&NCLSwitchRowKey);NSDictionary *row=nil;
  if(key.length){for(NSDictionary *candidate in self.rows)if([candidate[@"key"] isEqual:key] || [candidate[@"alias_keys"] containsObject:key]){row=candidate;break;}}
  else if(sender.tag>=0 && sender.tag<(NSInteger)self.rows.count)row=self.rows[sender.tag];
  if(!row)return;BOOL enabled=sender.on;
  if (!sender.enabled || self.closed || ![self.state[@"available"] boolValue] ||
      [self.state[@"hardcore"] boolValue] || [row[@"native"][@"readOnly"] boolValue]) {
    sender.on=[row[@"native"][@"enabled"] boolValue]; return;
  }
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
  if (self.downloading || self.catalogueInstalled || !self.catalogueStateKnown) return;
  self.downloading=YES; self.downloadStatus=[self text:@"downloading"]; [self.tableView reloadData]; __weak typeof(self) weakSelf=self;
  [NeoUnifiedCheatCatalog.sharedCatalog installAllForIdentity:self.state[@"identity"] ?: @{} progress:^(NSDictionary *progress) {
    NeoUnifiedCheatList *menu=weakSelf; if (!menu || menu.closed) return;
    NSMutableDictionary *state=[progress mutableCopy];state[@"installation_state"]=@"installing";[menu applyInstallationState:state];
  } completion:^(NSDictionary *result,NSError *error) {
    NeoUnifiedCheatList *menu=weakSelf; if (!menu || menu.closed) return;
    menu.downloading=NO;if(result)[menu applyInstallationState:result];
    menu.downloadStatus=[menu text:error ? @"downloadFailed" : @"installedReady"];[menu refreshDownloadState];[menu reloadCheats];
  }];
}
@end
