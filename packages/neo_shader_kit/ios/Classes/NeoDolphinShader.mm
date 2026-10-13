// SPDX-License-Identifier: GPL-3.0-or-later
#import "NeoDolphinShader.h"

#include <cstring>
#include <string>
#include <vector>

#include "NeoDolphinPostProcess.hpp"

NSString *const NeoDolphinShaderErrorDomain = @"NeoDolphinShaderErrorDomain";
NSString *const NeoDolphinShaderErrorCodeKey = @"NeoDolphinShaderErrorCode";

static NSError *DolphinError(NSString *code, NSString *detail) {
  return [NSError errorWithDomain:NeoDolphinShaderErrorDomain
                             code:1
                         userInfo:@{NeoDolphinShaderErrorCodeKey : code, NSDebugDescriptionErrorKey : detail ?: @""}];
}

static NSArray<NSNumber *> *Numbers(const std::vector<double> &values) {
  NSMutableArray<NSNumber *> *numbers = [NSMutableArray arrayWithCapacity:values.size()];
  for (double value : values) [numbers addObject:@(value)];
  return numbers;
}

static NSString *String(const std::string &text) {
  return [[NSString alloc] initWithBytes:text.data() length:text.size() encoding:NSUTF8StringEncoding] ?: @"";
}

@interface NeoDolphinShaderOption ()
@property(nonatomic, readwrite) NeoDolphinOptionType type;
@property(nonatomic, copy, readwrite) NSString *guiName;
@property(nonatomic, copy, readwrite) NSString *name;
@property(nonatomic, copy, readwrite) NSString *dependentOption;
@property(nonatomic, copy, readwrite) NSArray<NSNumber *> *defaultValues;
@property(nonatomic, copy, readwrite) NSArray<NSNumber *> *minimums;
@property(nonatomic, copy, readwrite) NSArray<NSNumber *> *maximums;
@property(nonatomic, copy, readwrite) NSArray<NSNumber *> *steps;
@end

@implementation NeoDolphinShaderOption
@end

static NSArray<NeoDolphinShaderOption *> *Options(const std::vector<neoshader::DolphinOption> &parsed) {
  NSMutableArray<NeoDolphinShaderOption *> *options = [NSMutableArray arrayWithCapacity:parsed.size()];
  for (const neoshader::DolphinOption &item : parsed) {
    NeoDolphinShaderOption *option = [NeoDolphinShaderOption new];
    switch (item.type) {
      case neoshader::DolphinOptionType::Bool: option.type = NeoDolphinOptionTypeBool; break;
      case neoshader::DolphinOptionType::Float: option.type = NeoDolphinOptionTypeFloat; break;
      case neoshader::DolphinOptionType::Integer: option.type = NeoDolphinOptionTypeInteger; break;
    }
    option.guiName = String(item.guiName);
    option.name = String(item.name);
    option.dependentOption = String(item.dependentOption);
    option.defaultValues = Numbers(item.values);
    option.minimums = Numbers(item.minimums);
    option.maximums = Numbers(item.maximums);
    option.steps = Numbers(item.steps);
    if (option.name.length > 0) [options addObject:option];
  }
  return options;
}

@interface NeoDolphinShader ()
@property(nonatomic, copy, readwrite) NSArray<NeoDolphinShaderOption *> *options;
@property(nonatomic, copy, readwrite) NSString *fragmentMSL;
@property(nonatomic, copy, readwrite) NSString *vertexMSL;
@property(nonatomic, copy) NSString *fragmentEntry;
@property(nonatomic, copy) NSString *vertexEntry;
@property(nonatomic, readwrite) NSUInteger sampleInstructions;
@end

@implementation NeoDolphinShader

+ (NSArray<NeoDolphinShaderOption *> *)optionsOfCode:(NSString *)code {
  if (![code isKindOfClass:NSString.class]) return @[];
  const char *bytes = code.UTF8String;
  if (bytes == nullptr || std::strlen(bytes) > neoshader::kMaxDolphinShaderBytes) return @[];
  return Options(neoshader::parseDolphinOptions(bytes));
}

+ (NSArray<NSString *> *)creditLinesOfCode:(NSString *)code {
  NSMutableArray<NSString *> *lines = [NSMutableArray array];
  if (![code isKindOfClass:NSString.class]) return lines;
  NSRegularExpression *author = [NSRegularExpression
      regularExpressionWithPattern:@"^(by\\s+\\S.{0,60}|.*\\b(?:copyright|author|ported|adapted|written)\\b.{0,80}|"
                                   @"https?://(?:www\\.)?shadertoy\\.com/\\S+)$"
                           options:NSRegularExpressionCaseInsensitive
                             error:nil];
  NSUInteger read = 0;
  for (NSString *raw in [code componentsSeparatedByCharactersInSet:NSCharacterSet.newlineCharacterSet]) {
    if (++read > 80 || lines.count >= 4) break;
    NSString *line = [raw stringByTrimmingCharactersInSet:NSCharacterSet.whitespaceCharacterSet];
    if (![line hasPrefix:@"//"] && ![line hasPrefix:@"/*"] && ![line hasPrefix:@"*"]) continue;
    NSString *text = [line stringByTrimmingCharactersInSet:[NSCharacterSet characterSetWithCharactersInString:@"/* \t"]];
    if (text.length < 3 || text.length > 140) continue;
    if ([author firstMatchInString:text options:0 range:NSMakeRange(0, text.length)] != nil && ![lines containsObject:text]) {
      [lines addObject:text];
    }
  }
  return lines;
}

+ (instancetype)shaderWithCode:(NSString *)code error:(NSError **)error {
  const char *bytes = [code isKindOfClass:NSString.class] ? code.UTF8String : nullptr;
  if (bytes == nullptr) {
    if (error != NULL) *error = DolphinError(@"DOLPHIN_NOT_TEXT", @"");
    return nil;
  }
  neoshader::DolphinPostProcessShader translated;
  neoshader::ShaderError failure;
  neoshader::DolphinTranslateOptions options;
  options.iosPlatform = true;
  if (!neoshader::translateDolphinPostProcess(bytes, options, &translated, &failure)) {
    if (error != NULL) *error = DolphinError(String(failure.code), String(failure.detail));
    return nil;
  }
  NeoDolphinShader *shader = [NeoDolphinShader new];
  shader.options = Options(translated.options);
  shader.fragmentMSL = String(translated.fragmentMSL);
  shader.vertexMSL = String(translated.vertexMSL);
  shader.fragmentEntry = String(translated.fragmentEntry);
  shader.vertexEntry = String(translated.vertexEntry);
  shader.sampleInstructions = translated.sampleInstructions;
  return shader;
}

- (BOOL)compileWithDevice:(id<MTLDevice>)device error:(NSError **)error {
  if (device == nil) {
    if (error != NULL) *error = DolphinError(@"METAL_LIBRARY_FAILED", @"no Metal device");
    return NO;
  }
  NSArray *stages = @[ @[ self.fragmentMSL, self.fragmentEntry ], @[ self.vertexMSL, self.vertexEntry ] ];
  for (NSArray<NSString *> *stage in stages) {
    NSError *metalError = nil;
    id<MTLLibrary> library = [device newLibraryWithSource:stage[0] options:nil error:&metalError];
    if ([library newFunctionWithName:stage[1]] == nil) {
      if (error != NULL) {
        *error = DolphinError(@"METAL_LIBRARY_FAILED", metalError.localizedDescription ?: @"entry point missing");
      }
      return NO;
    }
  }
  return YES;
}

@end
