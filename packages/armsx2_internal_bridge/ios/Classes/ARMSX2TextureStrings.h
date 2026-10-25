// SPDX-License-Identifier: GPL-3.0-or-later
// Texts of the ARMSX2 HD texture packs (Build 485) in NeoStation's twelve
// locales, generated from tools/armsx2_textures/strings.json.
#import <Foundation/Foundation.h>

NS_ASSUME_NONNULL_BEGIN

FOUNDATION_EXPORT NSString* ARMSX2TextureText(NSString* key, NSString* _Nullable locale);
/// Replaces each {name} of the text by values[name].
FOUNDATION_EXPORT NSString* ARMSX2TextureFormat(NSString* key, NSString* _Nullable locale,
                                                NSDictionary<NSString*, id>* values);

NS_ASSUME_NONNULL_END
