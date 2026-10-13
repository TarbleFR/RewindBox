// SPDX-License-Identifier: GPL-3.0-or-later
// Post-processing effect of the embedded Dolphin core (Build 450).
//
// The in-game page writes only NeoStation's choice (Config/
// NeoStationShaders.json in Dolphin's user folder) and the shaders the
// player imports (Shaders/<name>.glsl, Dolphin's own folder for them). The
// choice reaches Dolphin's files right before the core initializes, at the
// next launch (DOLApplyShaderSelection): GFX.ini [Enhancements]
// PostProcessingShader and Dolphin.ini "<shader>-options". The retained core
// reads them at boot and exposes no call to change the effect during a game,
// and it saves its in-memory settings when the game stops, so a value
// written into GFX.ini during a game would be overwritten.
//
// Dolphin looks for a shader in User/Shaders first, then in Sys/Shaders
// (VideoCommon/PostProcessing.cpp, LoadShaderFromFile): an imported shader
// may not take the name of an official one, which it would hide.
//
// Foundation only: the launch path includes it without the shader kit.
#pragma once
#import <Foundation/Foundation.h>
#include <math.h>
#include <stdio.h>

#include "DolphinDisplayTrial.h"

static NSString* const DOLShaderSelectionPath = @"Config/NeoStationShaders.json";
/// Largest shader file accepted (NeoDolphinPostProcess.hpp kMaxDolphinShaderBytes).
static const unsigned long long DOLShaderMaxBytes = 512 * 1024;
/// Dolphin's default pass (s_default_pixel_shader_name), never offered.
static NSString* const DOLShaderDefaultName = @"default_pre_post_process";

/// A name Dolphin and NeoStation both handle: 1 to 64 characters, letters,
/// digits, spaces and ._()+-, not starting with a dot, no outer space.
static BOOL DOLShaderValidName(NSString* name) {
  if(![name isKindOfClass:NSString.class] || name.length<1 || name.length>64)return NO;
  if([name hasPrefix:@"."] || [name hasPrefix:@" "] || [name hasSuffix:@" "])return NO;
  if([name isEqualToString:DOLShaderDefaultName])return NO;
  return [name rangeOfString:@"^[A-Za-z0-9 _.()+-]+$" options:NSRegularExpressionSearch].location!=NSNotFound;
}

static BOOL DOLShaderValidGame(NSString* gameId) {
  return [gameId isKindOfClass:NSString.class] &&
    [gameId rangeOfString:@"^[A-Z0-9]{4,6}$" options:NSRegularExpressionSearch].location!=NSNotFound;
}

static NSString* DOLShaderFolder(NSString* root) {
  return root.length?[root stringByAppendingPathComponent:@"Shaders"]:nil;
}

/// Top-level .glsl names of a Shaders folder (sub-folders hold Dolphin's
/// stereoscopic shaders, which NeoStation does not offer).
static NSArray<NSString*>* DOLShaderNames(NSString* folder) {
  NSMutableArray<NSString*>* names=[NSMutableArray array];
  if(!folder.length)return names;
  NSFileManager* fm=NSFileManager.defaultManager;
  for(NSString* file in [fm contentsOfDirectoryAtPath:folder error:nil]) {
    if(![file.pathExtension isEqualToString:@"glsl"])continue;
    NSString* name=file.stringByDeletingPathExtension;
    NSDictionary* attributes=[fm attributesOfItemAtPath:[folder stringByAppendingPathComponent:file] error:nil];
    if(![attributes[NSFileType] isEqual:NSFileTypeRegular] || !DOLShaderValidName(name))continue;
    [names addObject:name];
  }
  [names sortUsingSelector:@selector(localizedStandardCompare:)];
  return names;
}

/// The file Dolphin would load for `name` (user folder first), nil if none.
static NSString* DOLShaderFile(NSString* user,NSString* system,NSString* name,BOOL* imported) {
  if(imported)*imported=NO;
  if(!DOLShaderValidName(name))return nil;
  NSFileManager* fm=NSFileManager.defaultManager;
  NSString* file=[DOLShaderFolder(user) stringByAppendingPathComponent:[name stringByAppendingPathExtension:@"glsl"]];
  if(file && [fm fileExistsAtPath:file]) {
    if(imported)*imported=YES;
    return file;
  }
  file=[DOLShaderFolder(system) stringByAppendingPathComponent:[name stringByAppendingPathExtension:@"glsl"]];
  return file && [fm fileExistsAtPath:file]?file:nil;
}

static BOOL DOLShaderValidOption(NSString* option,id record) {
  if(![option isKindOfClass:NSString.class] ||
     [option rangeOfString:@"^[A-Za-z_][A-Za-z0-9_]{0,63}$" options:NSRegularExpressionSearch].location==NSNotFound)return NO;
  if(![record isKindOfClass:NSDictionary.class] || ![@[@"bool",@"float",@"integer"] containsObject:record[@"type"]])return NO;
  NSArray* values=record[@"values"];
  if(![values isKindOfClass:NSArray.class] || values.count<1 || values.count>4)return NO;
  for(id number in values)if(![number isKindOfClass:NSNumber.class] || !isfinite([number doubleValue]))return NO;
  return YES;
}

/// {"schema":1, "global": name or "", "games": {gameId: name or ""},
///  "options": {name: {option: {"type": "bool"|"float"|"integer",
///  "values": [1 to 4 numbers]}}}, "checked": {name: SHA-256 of the file
///  compiled on this device}}; defaults when missing or invalid.
static NSMutableDictionary* DOLShaderReadSelection(NSString* user) {
  NSMutableDictionary* selection=[@{@"schema":@1,@"global":@"",@"games":[NSMutableDictionary dictionary],
    @"options":[NSMutableDictionary dictionary],@"checked":[NSMutableDictionary dictionary]} mutableCopy];
  if(!user.length)return selection;
  NSData* bytes=[NSData dataWithContentsOfFile:[user stringByAppendingPathComponent:DOLShaderSelectionPath]];
  id json=bytes.length && bytes.length<1048576?[NSJSONSerialization JSONObjectWithData:bytes options:0 error:nil]:nil;
  if(![json isKindOfClass:NSDictionary.class] || ![json[@"schema"] isEqual:@1])return selection;
  id global=json[@"global"];
  if([global isKindOfClass:NSString.class] && ([global length]==0 || DOLShaderValidName(global)))selection[@"global"]=global;
  if([json[@"games"] isKindOfClass:NSDictionary.class])
    for(id game in json[@"games"]) {
      id name=json[@"games"][game];
      if(DOLShaderValidGame(game) && [name isKindOfClass:NSString.class] && ([name length]==0 || DOLShaderValidName(name)))
        selection[@"games"][game]=name;
    }
  if([json[@"options"] isKindOfClass:NSDictionary.class])
    for(id name in json[@"options"]) {
      id options=json[@"options"][name];
      if(!DOLShaderValidName(name) || ![options isKindOfClass:NSDictionary.class])continue;
      NSMutableDictionary* kept=[NSMutableDictionary dictionary];
      for(id option in options)if(DOLShaderValidOption(option,options[option]))kept[option]=options[option];
      if(kept.count)selection[@"options"][name]=kept;
    }
  if([json[@"checked"] isKindOfClass:NSDictionary.class])
    for(id name in json[@"checked"]) {
      id hash=json[@"checked"][name];
      if(DOLShaderValidName(name) && [hash isKindOfClass:NSString.class] &&
         [hash rangeOfString:@"^[0-9a-f]{64}$" options:NSRegularExpressionSearch].location!=NSNotFound)
        selection[@"checked"][name]=hash;
    }
  return selection;
}

static BOOL DOLShaderWriteSelection(NSString* user,NSDictionary* selection) {
  if(!user.length)return NO;
  NSString* file=[user stringByAppendingPathComponent:DOLShaderSelectionPath];
  if(![NSFileManager.defaultManager createDirectoryAtPath:file.stringByDeletingLastPathComponent withIntermediateDirectories:YES attributes:nil error:nil])return NO;
  NSData* bytes=[NSJSONSerialization dataWithJSONObject:selection options:NSJSONWritingSortedKeys error:nil];
  return bytes && [bytes writeToFile:file options:NSDataWritingAtomic error:nil];
}

/// The game's own choice when it has one, else the choice for every game
/// ("" = no effect).
static NSString* DOLShaderEffective(NSDictionary* selection,NSString* gameId) {
  NSString* own=gameId.length?selection[@"games"][gameId]:nil;
  if([own isKindOfClass:NSString.class])return own;
  return [selection[@"global"] isKindOfClass:NSString.class]?selection[@"global"]:@"";
}

/// gameId nil: the choice for every game. name "" switches the effect off;
/// for a game, nil removes its own choice (it follows every game's).
static BOOL DOLShaderSetChoice(NSString* user,NSString* gameId,NSString* name) {
  if(name.length && !DOLShaderValidName(name))return NO;
  NSMutableDictionary* selection=DOLShaderReadSelection(user);
  if(gameId.length) {
    if(!DOLShaderValidGame(gameId))return NO;
    if(name)selection[@"games"][gameId]=name;else [selection[@"games"] removeObjectForKey:gameId];
  } else {
    selection[@"global"]=name?:@"";
  }
  return DOLShaderWriteSelection(user,selection);
}

/// Every option of a shader with its value ({option: {"type", "values"}});
/// nil forgets them (the shader's own defaults apply).
static BOOL DOLShaderSetOptionValues(NSString* user,NSString* name,NSDictionary* options) {
  if(!DOLShaderValidName(name))return NO;
  NSMutableDictionary* kept=[NSMutableDictionary dictionary];
  for(id option in options)if(DOLShaderValidOption(option,options[option]))kept[option]=options[option];
  NSMutableDictionary* selection=DOLShaderReadSelection(user);
  if(kept.count)selection[@"options"][name]=kept;else [selection[@"options"] removeObjectForKey:name];
  return DOLShaderWriteSelection(user,selection);
}

/// Remembers that the file of `name` with this SHA-256 compiled for Metal on
/// this device (nil forgets it).
static BOOL DOLShaderSetChecked(NSString* user,NSString* name,NSString* sha256) {
  if(!DOLShaderValidName(name))return NO;
  NSMutableDictionary* selection=DOLShaderReadSelection(user);
  if(sha256.length==64)selection[@"checked"][name]=sha256;else [selection[@"checked"] removeObjectForKey:name];
  return DOLShaderWriteSelection(user,selection);
}

/// One option value as Dolphin.ini holds it: "True"/"False" for a bool
/// (IniFile Set(bool)), numbers separated by ", " in the C locale otherwise
/// (TryParseVector).
static NSString* DOLShaderIniValue(NSDictionary* record) {
  NSArray<NSNumber*>* values=record[@"values"];
  if([record[@"type"] isEqual:@"bool"])return [values.firstObject boolValue]?@"True":@"False";
  NSMutableArray<NSString*>* parts=[NSMutableArray array];
  for(NSNumber* value in values) {
    if([record[@"type"] isEqual:@"integer"])[parts addObject:[NSString stringWithFormat:@"%lld",llround(value.doubleValue)]];
    else {
      char buffer[32];
      snprintf(buffer,sizeof(buffer),"%.9g",value.doubleValue);
      [parts addObject:@(buffer)];
    }
  }
  return [parts componentsJoinedByString:@", "];
}

/// `text` without the lines of `section` (header included).
static NSString* DOLIniRemoveSection(NSString* text,NSString* section) {
  NSMutableArray* kept=[NSMutableArray array];NSString* current=@"";
  for(NSString* line in [text componentsSeparatedByString:@"\n"]) {
    NSString* next=DOLSection(line);if(next)current=next;
    if([current caseInsensitiveCompare:section]==NSOrderedSame)continue;
    [kept addObject:line];
  }
  return [kept componentsJoinedByString:@"\n"];
}

static BOOL DOLShaderPatchIni(NSString* file,NSString* (^patch)(NSString* text)) {
  NSFileManager* fm=NSFileManager.defaultManager;
  NSDictionary* attributes=[fm attributesOfItemAtPath:file error:nil];
  if([attributes[NSFileType] isEqual:NSFileTypeSymbolicLink] || [attributes[NSFileSize] unsignedLongLongValue]>4194304)return NO;
  NSString* before=attributes?[NSString stringWithContentsOfFile:file encoding:NSUTF8StringEncoding error:nil]:@"";
  if(!before || ![fm createDirectoryAtPath:file.stringByDeletingLastPathComponent withIntermediateDirectories:YES attributes:nil error:nil])return NO;
  NSString* after=patch(before);
  return [after isEqualToString:before] || [after writeToFile:file atomically:YES encoding:NSUTF8StringEncoding error:nil];
}

/// Right before the core initializes: the effect of this game (or of every
/// game) and its option values go to Dolphin's files. A shader that is no
/// longer there is switched off rather than failing in the core. The
/// "<shader>-options" section is rewritten from NeoStation's values only
/// (none: the shader's own defaults). `applied` gets the shader written
/// ("" for none).
static BOOL DOLApplyShaderSelection(NSString* user,NSString* system,NSString* gameId,NSString** applied) {
  if(applied)*applied=@"";
  if(!user.length)return NO;
  NSDictionary* selection=DOLShaderReadSelection(user);
  NSString* name=DOLShaderEffective(selection,DOLShaderValidGame(gameId)?gameId:nil);
  NSString* file=name.length?DOLShaderFile(user,system,name,NULL):nil;
  NSDictionary* attributes=file?[NSFileManager.defaultManager attributesOfItemAtPath:file error:nil]:nil;
  if(!file || ![attributes[NSFileType] isEqual:NSFileTypeRegular] ||
     [attributes[NSFileSize] unsignedLongLongValue]>DOLShaderMaxBytes)name=@"";
  // An explicit empty value: the pinned loader does not clear a key that
  // is missing from the file, so a removal would keep the last effect.
  if(!DOLShaderPatchIni([user stringByAppendingPathComponent:@"Config/GFX.ini"],^NSString*(NSString* text){
    return DOLIniSet(text,@"Enhancements",@"PostProcessingShader",name);
  }))return NO;
  if(name.length) {
    NSDictionary* options=selection[@"options"][name];
    NSString* section=[name stringByAppendingString:@"-options"];
    if(!DOLShaderPatchIni([user stringByAppendingPathComponent:@"Config/Dolphin.ini"],^NSString*(NSString* text){
      NSString* patched=DOLIniRemoveSection(text,section);
      for(NSString* option in [[options allKeys] sortedArrayUsingSelector:@selector(compare:)])
        patched=DOLIniSet(patched,section,option,DOLShaderIniValue(options[option]));
      return patched;
    }))return NO;
  }
  if(applied)*applied=name;
  return YES;
}

/// Writes an imported shader (already validated) as User/Shaders/<name>.glsl.
static BOOL DOLShaderStoreImport(NSString* user,NSString* name,NSData* code,BOOL* replaced) {
  if(replaced)*replaced=NO;
  if(!DOLShaderValidName(name) || !code.length || code.length>DOLShaderMaxBytes)return NO;
  NSString* folder=DOLShaderFolder(user);
  NSFileManager* fm=NSFileManager.defaultManager;
  if(!folder || ![fm createDirectoryAtPath:folder withIntermediateDirectories:YES attributes:nil error:nil])return NO;
  NSString* file=[folder stringByAppendingPathComponent:[name stringByAppendingPathExtension:@"glsl"]];
  NSDictionary* attributes=[fm attributesOfItemAtPath:file error:nil];
  if([attributes[NSFileType] isEqual:NSFileTypeSymbolicLink])return NO;
  if(replaced)*replaced=attributes!=nil;
  return [code writeToFile:file options:NSDataWritingAtomic error:nil];
}

/// Deletes an imported shader; the choices that named it switch the effect
/// off and what NeoStation kept about it is forgotten.
static BOOL DOLShaderRemoveImport(NSString* user,NSString* name) {
  if(!DOLShaderValidName(name))return NO;
  NSString* file=[DOLShaderFolder(user) stringByAppendingPathComponent:[name stringByAppendingPathExtension:@"glsl"]];
  NSFileManager* fm=NSFileManager.defaultManager;
  if(file && [fm fileExistsAtPath:file] && ![fm removeItemAtPath:file error:nil])return NO;
  NSMutableDictionary* selection=DOLShaderReadSelection(user);
  if([selection[@"global"] isEqual:name])selection[@"global"]=@"";
  for(NSString* game in [selection[@"games"] allKeys])
    if([selection[@"games"][game] isEqual:name])selection[@"games"][game]=@"";
  [selection[@"options"] removeObjectForKey:name];
  [selection[@"checked"] removeObjectForKey:name];
  return DOLShaderWriteSelection(user,selection);
}
