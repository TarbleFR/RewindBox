#import "LibretroShaderRecovery.h"

#include <fcntl.h>
#include <unistd.h>

static BOOL IsAttempt(NSDictionary *record) {
  if (![record isKindOfClass:NSDictionary.class]) return NO;
  for (NSString *key in @[ @"preset", @"core", @"game", @"token" ]) {
    if (![record[key] isKindOfClass:NSString.class]) return NO;
  }
  return [record[@"preset"] length] > 0 && [record[@"token"] length] > 0;
}

static BOOL Matches(NSDictionary *record, NSString *preset, NSString *core, NSString *game) {
  return IsAttempt(record) && [record[@"preset"] isEqualToString:preset] &&
         [record[@"core"] isEqualToString:core] && [record[@"game"] isEqualToString:game];
}

@implementation LibretroShaderRecovery {
  NSString *_path;
  NSMutableArray<NSDictionary *> *_interrupted;
  NSDictionary *_pending;
  NSDictionary *_active;
  BOOL _usable;
}

- (instancetype)initWithDirectory:(NSString *)directory {
  self = [super init];
  if (self) {
    _interrupted = [NSMutableArray array];
    _path = directory.length > 0 ? [directory stringByAppendingPathComponent:@"shader-attempts.json"] : nil;
    _usable = _path != nil;
    if (_path != nil && [NSFileManager.defaultManager fileExistsAtPath:_path]) {
      NSData *data = [NSData dataWithContentsOfFile:_path];
      id decoded = data != nil ? [NSJSONSerialization JSONObjectWithData:data options:0 error:nil] : nil;
      if (![decoded isKindOfClass:NSDictionary.class] || ![decoded[@"version"] isEqual:@1] ||
          ![decoded[@"interrupted"] isKindOfClass:NSArray.class]) {
        _usable = NO;
      } else {
        for (id record in decoded[@"interrupted"]) {
          if (!IsAttempt(record)) { _usable = NO; break; }
          [_interrupted addObject:record];
        }
        id pending = decoded[@"pending"];
        id active = decoded[@"active"];
        if (pending != nil && !IsAttempt(pending)) _usable = NO;
        if (active != nil && !IsAttempt(active)) _usable = NO;
        if (_usable && (pending != nil || active != nil)) {
          // Keep the skipped preset blocked until the user explicitly retries
          // successfully or gets a handled error; starting another game does
          // not silently re-enable an interrupted activation.
          if (pending != nil) [_interrupted addObject:pending];
          if (active != nil) [_interrupted addObject:active];
          _usable = [self writeState];
        }
      }
    }
  }
  return self;
}

- (BOOL)writeState {
  if (_path == nil) return NO;
  NSMutableDictionary *state = [@{ @"version" : @1, @"interrupted" : _interrupted } mutableCopy];
  if (_pending != nil) state[@"pending"] = _pending;
  if (_active != nil) state[@"active"] = _active;
  NSData *data = [NSJSONSerialization dataWithJSONObject:state options:0 error:nil];
  if (data == nil || ![NSFileManager.defaultManager createDirectoryAtPath:_path.stringByDeletingLastPathComponent
                                            withIntermediateDirectories:YES attributes:nil error:nil] ||
      ![data writeToFile:_path options:NSDataWritingAtomic error:nil]) return NO;
  int descriptor = open(_path.fileSystemRepresentation, O_RDONLY | O_CLOEXEC);
  if (descriptor < 0) return NO;
  BOOL synced = fsync(descriptor) == 0;
  close(descriptor);
  return synced;
}

- (BOOL)blocksAutomaticPreset:(NSString *)preset core:(NSString *)core game:(NSString *)game {
  @synchronized(self) {
    if (!_usable) return YES;
    for (NSDictionary *record in _interrupted) {
      if (Matches(record, preset, core, game)) return YES;
    }
    return NO;
  }
}

- (BOOL)canProtect {
  @synchronized(self) { return _usable; }
}

- (NSString *)beginPreset:(NSString *)preset core:(NSString *)core game:(NSString *)game {
  @synchronized(self) {
    if (!_usable || preset.length == 0) return nil;
    NSDictionary *before = _pending;
    NSString *token = NSUUID.UUID.UUIDString;
    _pending = @{ @"preset" : preset, @"core" : core ?: @"", @"game" : game ?: @"", @"token" : token };
    if (![self writeState]) { _pending = before; return nil; }
    return token;
  }
}

- (void)finishToken:(NSString *)token confirmed:(BOOL)confirmed {
  @synchronized(self) {
    if (![_pending[@"token"] isEqualToString:token]) return;
    NSDictionary *finished = _pending;
    NSDictionary *activeBefore = _active;
    NSMutableArray *before = [_interrupted mutableCopy];
    if (confirmed) {
      NSIndexSet *same = [_interrupted indexesOfObjectsPassingTest:^BOOL(NSDictionary *record, NSUInteger index,
                                                                        BOOL *stop) {
        return Matches(record, finished[@"preset"], finished[@"core"], finished[@"game"]);
      }];
      [_interrupted removeObjectsAtIndexes:same];
      _active = finished;
    }
    _pending = nil;
    if (![self writeState]) { _pending = finished; _active = activeBefore; _interrupted = before; }
  }
}

- (void)finishSession {
  @synchronized(self) {
    if (_pending == nil && _active == nil) return;
    NSDictionary *before = _pending;
    NSDictionary *activeBefore = _active;
    _pending = nil;
    _active = nil;
    if (![self writeState]) { _pending = before; _active = activeBefore; }
  }
}

- (void)deactivatePreset {
  @synchronized(self) {
    if (_active == nil) return;
    NSDictionary *before = _active;
    _active = nil;
    if (![self writeState]) _active = before;
  }
}

@end

NSString *LibretroShaderFailureTextKey(NSString *code) {
  if ([code isEqualToString:@"SHADER_INTERRUPTED"]) return @"shaderInterrupted";
  if ([code isEqualToString:@"SHADER_RECOVERY_WRITE"]) return @"shaderProtectionFailed";
  if ([code isEqualToString:@"SHADER_NOT_INSTALLED"]) return @"shaderNotInstalled";
  if ([code isEqualToString:@"DOWNLOAD_SIZE"] || [code isEqualToString:@"DOWNLOAD_HASH"]) {
    return @"shaderErrorVerification";
  }
  if ([code isEqualToString:@"CHAIN_MEMORY"] || [code isEqualToString:@"CHAIN_PASS_SIZE"] ||
      [code isEqualToString:@"CHAIN_ALLOCATION"]) return @"shaderTooHeavy";
  if ([code hasPrefix:@"PRESET_"] || [code hasPrefix:@"SOURCE_"] || [code hasPrefix:@"PATH_"] ||
      [code isEqualToString:@"ENTRY_INVALID"] || [code isEqualToString:@"CHAIN_FILE"] ||
      [code isEqualToString:@"LUT_UNREADABLE"]) return @"shaderInvalid";
  if ([code isEqualToString:@"CHAIN_GPU"] || [code isEqualToString:@"SHADER_GPU_FAILED"]) return @"shaderGpuFailed";
  if ([code isEqualToString:@"CHAIN_INPUT_FORMAT"] || [code isEqualToString:@"CHAIN_INPUT_TEXTURE"] ||
      [code isEqualToString:@"CHAIN_FORMAT"] || [code isEqualToString:@"CHAIN_UNSUPPORTED"]) {
    return @"shaderIncompatible";
  }
  if ([code hasPrefix:@"SHADER_COMPILE"] || [code hasPrefix:@"COMPILER_"] ||
      [code hasPrefix:@"METAL_"] || [code hasPrefix:@"GLSL_STAGE"]) return @"shaderCompileFailed";
  return @"shaderFailed";
}
