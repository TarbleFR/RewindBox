// SPDX-License-Identifier: GPL-2.0-or-later
#import <Foundation/Foundation.h>
#include <dlfcn.h>

// Optional owned C ABI keeps the UI safe with the currently retained Core.
static inline bool DOLWiimmfiSupported() {
  auto abi = reinterpret_cast<int32_t (*)()>(dlsym(RTLD_DEFAULT, "neostation_dolphin_wiimmfi_abi"));
  return abi && abi() == 1 &&
      dlsym(RTLD_DEFAULT, "neostation_dolphin_wiimmfi_import") &&
      dlsym(RTLD_DEFAULT, "neostation_dolphin_wiimmfi_nand_ready") &&
      dlsym(RTLD_DEFAULT, "neostation_dolphin_wiimmfi_configure");
}
static inline int32_t DOLWiimmfiConfigure(bool enabled) {
  auto fn = reinterpret_cast<int32_t (*)(int32_t)>(dlsym(RTLD_DEFAULT, "neostation_dolphin_wiimmfi_configure"));
  return fn ? fn(enabled ? 1 : 0) : (enabled ? 0 : 1);
}
static inline bool DOLWiimmfiPrivateDirectory(NSString* path, bool empty) {
  if (!path.length) return false;
  NSString* home = NSHomeDirectory().stringByResolvingSymlinksInPath;
  NSString* normalized = path.stringByStandardizingPath;
  // Follows only the platform's /var -> /private/var alias, not player links.
  if (![normalized.stringByResolvingSymlinksInPath hasPrefix:[home stringByAppendingString:@"/Library/"]]) return false;
  for (NSString* cursor = normalized; cursor.length > 1; cursor = cursor.stringByDeletingLastPathComponent) {
    NSDictionary* attrs = [NSFileManager.defaultManager attributesOfItemAtPath:cursor error:nil];
    if (![attrs[NSFileType] isEqual:NSFileTypeDirectory]) return false;
    if ([cursor.stringByResolvingSymlinksInPath isEqual:home]) break;
  }
  NSError* error = nil;
  NSArray* contents = [NSFileManager.defaultManager contentsOfDirectoryAtPath:normalized error:&error];
  return contents && !error && (!empty || contents.count == 0);
}
static inline bool DOLWiimmfiProtectDirectory(NSString* root) {
  if (!DOLWiimmfiPrivateDirectory(root, false)) return false;
  NSFileManager* manager = NSFileManager.defaultManager;
  NSDictionary* protection = @{NSFileProtectionKey: NSFileProtectionCompleteUntilFirstUserAuthentication};
  if (![manager setAttributes:protection ofItemAtPath:root error:nil]) return false;
  NSDirectoryEnumerator* items = [manager enumeratorAtPath:root];
  for (NSString* relative in items) {
    NSString* file = [root stringByAppendingPathComponent:relative];
    NSDictionary* attrs = [manager attributesOfItemAtPath:file error:nil];
    if (![attrs[NSFileType] isEqual:NSFileTypeDirectory] && ![attrs[NSFileType] isEqual:NSFileTypeRegular]) return false;
    if (![manager setAttributes:protection ofItemAtPath:file error:nil]) return false;
  }
  NSURL* url = [NSURL fileURLWithPath:root isDirectory:YES];
  return [url setResourceValue:@YES forKey:NSURLIsExcludedFromBackupKey error:nil];
}
