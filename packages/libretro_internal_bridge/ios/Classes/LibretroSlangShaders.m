#import "LibretroSlangShaders.h"

#import <neo_shader_kit/NeoShaderCatalog.h>
#import <neo_shader_kit/NeoShaderStorage.h>
#import <neo_shader_kit/NeoSlangRenderer.h>

NSString *const LibretroSlangPrefix = @"slang:";
NSString *const LibretroSlangNotInstalled = @"SHADER_NOT_INSTALLED";

BOOL LibretroIsSlangShader(NSString *identifier) {
  return [identifier isKindOfClass:NSString.class] && identifier.length > LibretroSlangPrefix.length &&
         [identifier hasPrefix:LibretroSlangPrefix];
}

NSString *LibretroSlangCatalogIdentifier(NSString *identifier) {
  return LibretroIsSlangShader(identifier) ? [identifier substringFromIndex:LibretroSlangPrefix.length] : nil;
}

NSString *LibretroSlangShaderIdentifier(NSString *catalogIdentifier) {
  return [LibretroSlangPrefix stringByAppendingString:catalogIdentifier ?: @""];
}

NSString *LibretroSlangStorageRoot(void) {
  NSString *support = NSSearchPathForDirectoriesInDomains(NSApplicationSupportDirectory, NSUserDomainMask, YES).firstObject;
  return [[[support stringByAppendingPathComponent:@"NeoStation"] stringByAppendingPathComponent:@"Shaders"]
      stringByAppendingPathComponent:@"libretro"];
}

NeoShaderStorage *LibretroSlangStorage(void) {
  return [NeoShaderStorage sharedStorageWithRoot:LibretroSlangStorageRoot() engine:@"libretro"];
}

NeoShaderCatalog *LibretroSlangCatalog(void) {
  return [[NeoShaderCatalogManager sharedManager] catalogForEngine:@"libretro"];
}

NeoSlangProgram *LibretroCompileSlangShader(NSString *identifier, id<MTLDevice> device, NSString **code,
                                           NSString **detail) {
  NSString *catalogIdentifier = LibretroSlangCatalogIdentifier(identifier);
  NeoShaderStorage *storage = LibretroSlangStorage();
  NeoShaderInstallation *installation =
      catalogIdentifier != nil ? [storage installationWithIdentifier:catalogIdentifier] : nil;
  if (installation == nil || ![storage installationIsComplete:installation] || device == nil) {
    if (code != NULL) *code = LibretroSlangNotInstalled;
    if (detail != NULL) *detail = identifier;
    return nil;
  }
  NSError *error = nil;
  NeoSlangProgram *program = [NeoSlangProgram programWithRoot:[storage filesDirectoryForRevision:installation.revision]
                                                       preset:catalogIdentifier
                                                       device:device
                                                  iosPlatform:YES
                                                        error:&error];
  if (program == nil) {
    if (code != NULL) *code = error.userInfo[NeoSlangErrorCodeKey] ?: @"SHADER_COMPILE_FAILED";
    if (detail != NULL) *detail = error.userInfo[NSDebugDescriptionErrorKey] ?: @"";
    return nil;
  }
  NSLog(@"[Libretro] slang %@: %lu passes, %lu parameters, translation %.2f s, Metal %.2f s", catalogIdentifier,
        (unsigned long)program.passCount, (unsigned long)program.parameters.count, program.translationSeconds,
        program.metalSeconds);
  return program;
}
