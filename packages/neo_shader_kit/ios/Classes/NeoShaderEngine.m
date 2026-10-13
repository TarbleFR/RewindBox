// SPDX-License-Identifier: GPL-3.0-or-later
#import "NeoShaderEngine.h"

NeoShaderFormat const NeoShaderFormatBuiltinMetal = @"neostation-metal";
NeoShaderFormat const NeoShaderFormatSlang = @"slang";
NeoShaderFormat const NeoShaderFormatDolphinGLSL = @"dolphin-glsl";

@implementation NeoShaderEngineCapabilities

- (instancetype)init {
  self = [super init];
  if (self) {
    _engineIdentifier = @"";
    _formats = @[];
    _renderBackend = @"Metal";
    _profileScopes = @[];
    _limits = @{};
  }
  return self;
}

@end

@implementation NeoShaderResult

- (instancetype)initWithSuccess:(BOOL)success code:(NSString *)code detail:(NSString *)detail {
  self = [super init];
  if (self) {
    _success = success;
    _code = [code copy];
    _detail = [detail copy];
  }
  return self;
}

+ (instancetype)success {
  return [[self alloc] initWithSuccess:YES code:nil detail:nil];
}

+ (instancetype)failureWithCode:(NSString *)code detail:(NSString *)detail {
  return [[self alloc] initWithSuccess:NO code:code.length > 0 ? code : @"UNKNOWN" detail:detail];
}

@end
