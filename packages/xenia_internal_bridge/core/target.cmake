# SPDX-License-Identifier: BSD-3-Clause
# RewindBox's embedded XeniOS Core. Included at the end of XeniOS's
# cmake/ios/App.cmake by build-utils/xenia/rewindbox-core.patch, so every
# upstream target, data repository and helper of xenia-app already exists.
# Builds XeniaCore.framework from the same sources and libraries as the
# XeniOS app, minus its main(), with XE_NEO_EMBEDDED_CORE=1 and RewindBox's
# facade (core/XeniaCore.mm). Only NeoXenia_GetAPI is exported.
if(NOT NEO_XENIA_SOURCE_REVISION MATCHES "^[0-9a-f]+$")
  message(FATAL_ERROR "NEO_XENIA_SOURCE_REVISION (the pinned XeniOS commit) is required")
endif()
if(NOT TARGET xenia-third-party-metal-shader-converter)
  message(FATAL_ERROR "XeniaCore needs the iPhoneOS Metal Shader Converter "
                      "(XENIA_IOS_SHADER_CONVERTER_LIBRARY), validated by "
                      "build-utils/xenia/validate_shader_converter.py")
endif()

add_library(XeniaCore SHARED
  ${CMAKE_CURRENT_SOURCE_DIR}/xenia_main_ios.mm
  ${CMAKE_CURRENT_SOURCE_DIR}/game_title_db.cc
  "${NEO_XENIA_ADAPTER_DIR}/core/XeniaCore.mm"
)
# Upstream Objective-C is manual retain/release; only the facade uses ARC.
set_property(SOURCE "${NEO_XENIA_ADAPTER_DIR}/core/XeniaCore.mm"
  APPEND PROPERTY COMPILE_OPTIONS "-fobjc-arc")
target_compile_definitions(XeniaCore PRIVATE
  XE_NEO_EMBEDDED_CORE=1
  NEO_XENIA_SOURCE_REVISION="${NEO_XENIA_SOURCE_REVISION}"
  XBYAK_NO_OP_NAMES
  XBYAK_ENABLE_OMITTED_OPERAND
)
target_include_directories(XeniaCore PRIVATE
  "${NEO_XENIA_ADAPTER_DIR}/core"
  "${NEO_XENIA_ADAPTER_DIR}/ios/Classes"
  "${PROJECT_SOURCE_DIR}/third_party/rapidjson/include"
)
# The data xenia-app embeds, which xenia-ui-ios's launcher code references.
xe_embed_compressed_bundle(XeniaCore "${XENIA_DATA_REPOS_DIR}/x360db/games.json" game_db)
xe_embed_compressed_bundle(XeniaCore "${PROJECT_SOURCE_DIR}/assets/xdb/games.json" xbox_db)
xe_embed_binary_assets(XeniaCore "${PROJECT_SOURCE_DIR}/assets/icons" icons)
xe_embed_compressed_bundle(XeniaCore "${XENIA_IOS_COMPATIBILITY_DATA_DIR}" game_compat)

target_link_libraries(XeniaCore PRIVATE
  xenia-apu xenia-apu-nop xenia-apu-phase xenia-apu-sdl xenia-apu-voice-apple
  xenia-base xenia-core xenia-cpu xenia-cpu-backend-a64
  xenia-gpu xenia-gpu-metal
  xenia-helper-sdl xenia-hid xenia-hid-nop xenia-hid-sdl xenia-hid-touch
  xenia-kernel xenia-patcher xenia-ui xenia-ui-ios xenia-ui-metal xenia-vfs
  xenia-third-party-metal-shader-converter
  capstone dxbc fmt imgui libavcodec libavformat libavutil mspack snappy xxhash
  "-framework AVFoundation" "-framework AudioToolbox" "-framework CoreFoundation"
  "-framework Foundation" "-framework GameController" "-framework Metal"
  "-framework MetalKit" "-framework MetricKit" "-framework QuartzCore"
  "-framework Security" "-framework UIKit" "-framework UniformTypeIdentifiers"
)
target_link_options(XeniaCore PRIVATE
  "-Wl,-u,___clear_cache"
  # Only the versioned C boundary: FFmpeg, fmt, SDL3, imgui, capstone and
  # mbedtls linked here stay invisible to RewindBox's other engines.
  "-Wl,-exported_symbols_list,${NEO_XENIA_ADAPTER_DIR}/core/exports.txt"
  # App/Frameworks/libmetalirconverter.dylib, beside XeniaCore.framework.
  "-Wl,-rpath,@executable_path/Frameworks"
  "-Wl,-rpath,@loader_path/.."
)
set_target_properties(XeniaCore PROPERTIES
  FRAMEWORK TRUE
  FRAMEWORK_VERSION A
  OUTPUT_NAME XeniaCore
  MACOSX_FRAMEWORK_IDENTIFIER com.neogamelab.neostation.XeniaCore
  MACOSX_FRAMEWORK_SHORT_VERSION_STRING "1.0"
  MACOSX_FRAMEWORK_BUNDLE_VERSION "1"
  XCODE_ATTRIBUTE_PRODUCT_BUNDLE_IDENTIFIER com.neogamelab.neostation.XeniaCore
  XCODE_ATTRIBUTE_CODE_SIGNING_ALLOWED NO
  XCODE_ATTRIBUTE_CODE_SIGNING_REQUIRED NO
  BUILD_WITH_INSTALL_NAME_DIR TRUE
  INSTALL_NAME_DIR "@rpath"
)
# Credits travel with the binary (Xenia BSD license, XeniOS acknowledgements).
add_custom_command(TARGET XeniaCore POST_BUILD
  COMMAND "${CMAKE_COMMAND}" -E copy_if_different
          "${PROJECT_SOURCE_DIR}/LICENSE" "$<TARGET_BUNDLE_DIR:XeniaCore>/LICENSE.txt"
  COMMAND "${CMAKE_COMMAND}" -E copy_if_different
          "${PROJECT_SOURCE_DIR}/assets/apple/Acknowledgements.json"
          "$<TARGET_BUNDLE_DIR:XeniaCore>/Acknowledgements.json"
  VERBATIM)
xe_target_defaults(XeniaCore)
