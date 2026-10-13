# Host build of the shader kit's portable core (Linux and macOS): the
# vendored glslang / SPIRV-Cross files, the core, the command-line tool used
# by the catalog generator and the core tests; on macOS also the Metal
# runtime (Classes/NeoSlangRenderer.mm) with its render tests. The iOS build
# compiles the same files through neo_shader_kit.podspec.
cmake_minimum_required(VERSION 3.16)
project(neo_shader_kit_host CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
if(NOT CMAKE_BUILD_TYPE)
  set(CMAKE_BUILD_TYPE Release)
endif()

set(KIT ${CMAKE_CURRENT_SOURCE_DIR}/../ios)
set(GLSLANG ${KIT}/ThirdParty/glslang)
set(SPIRV_CROSS ${KIT}/ThirdParty/SPIRV-Cross)

file(GLOB GLSLANG_SOURCES
  ${GLSLANG}/glslang/MachineIndependent/*.cpp
  ${GLSLANG}/glslang/MachineIndependent/preprocessor/*.cpp
  ${GLSLANG}/glslang/GenericCodeGen/*.cpp
  ${GLSLANG}/glslang/OSDependent/Unix/ossource.cpp
  ${GLSLANG}/glslang/ResourceLimits/ResourceLimits.cpp
  ${GLSLANG}/SPIRV/*.cpp)
file(GLOB SPIRV_CROSS_SOURCES ${SPIRV_CROSS}/*.cpp)
add_library(neoshader_thirdparty STATIC ${GLSLANG_SOURCES} ${SPIRV_CROSS_SOURCES})
target_include_directories(neoshader_thirdparty PUBLIC ${GLSLANG} ${SPIRV_CROSS})
# Third-party code: keep its own warnings out of the kit's -Werror build.
target_compile_options(neoshader_thirdparty PRIVATE -w)
find_package(Threads REQUIRED)
target_link_libraries(neoshader_thirdparty PUBLIC Threads::Threads)

file(GLOB CORE_SOURCES ${KIT}/Core/*.cpp)
add_library(neoshader_core STATIC ${CORE_SOURCES})
target_include_directories(neoshader_core PUBLIC ${KIT}/Core)
target_link_libraries(neoshader_core PUBLIC neoshader_thirdparty)
target_compile_options(neoshader_core PRIVATE -Wall -Wextra -Werror -Wno-unused-parameter)

add_executable(neoshader-tool neoshader_tool.cpp)
target_link_libraries(neoshader-tool PRIVATE neoshader_core)
target_compile_options(neoshader-tool PRIVATE -Wall -Wextra -Werror -Wno-unused-parameter)

if(EXISTS ${CMAKE_CURRENT_SOURCE_DIR}/../../../test/neo_shader_kit/core_test.cpp)
  add_executable(neoshader-core-tests ${CMAKE_CURRENT_SOURCE_DIR}/../../../test/neo_shader_kit/core_test.cpp)
  target_link_libraries(neoshader-core-tests PRIVATE neoshader_core)
  target_compile_options(neoshader-core-tests PRIVATE -Wall -Wextra -Werror -Wno-unused-parameter)
endif()

# macOS: the Metal runtime the application runs, with render tests reading
# back what the GPU drew (test/neo_shader_kit_test.py writes the fixtures).
if(APPLE AND EXISTS ${CMAKE_CURRENT_SOURCE_DIR}/../../../test/neo_shader_kit/slang_render_test.mm)
  enable_language(OBJCXX)
  add_executable(neoshader-render-tests
    ${KIT}/Classes/NeoSlangRenderer.mm
    ${CMAKE_CURRENT_SOURCE_DIR}/../../../test/neo_shader_kit/slang_render_test.mm)
  target_include_directories(neoshader-render-tests PRIVATE ${KIT}/Classes/Public)
  target_compile_options(neoshader-render-tests PRIVATE -fobjc-arc -Wall -Wextra -Wno-unused-parameter)
  target_link_libraries(neoshader-render-tests PRIVATE neoshader_core
    "-framework Foundation" "-framework Metal" "-framework CoreGraphics" "-framework ImageIO"
    "-framework QuartzCore")
endif()

# macOS: storage (verified downloads, removal, favourites, profiles) and
# catalog parsing, with a fake network; no Metal.
if(APPLE AND EXISTS ${CMAKE_CURRENT_SOURCE_DIR}/../../../test/neo_shader_kit/storage_test.m)
  enable_language(OBJC)
  enable_language(OBJCXX)
  add_executable(neoshader-kit-tests
    ${KIT}/Classes/NeoShaderStorage.m
    ${KIT}/Classes/NeoShaderCatalog.mm
    ${KIT}/Classes/NeoShaderEngine.m
    ${KIT}/Classes/NeoDolphinShader.mm
    ${CMAKE_CURRENT_SOURCE_DIR}/../../../test/neo_shader_kit/storage_test.m)
  target_include_directories(neoshader-kit-tests PRIVATE ${KIT}/Classes/Public)
  target_compile_options(neoshader-kit-tests PRIVATE -fobjc-arc -Wall -Wextra -Wno-unused-parameter)
  target_link_libraries(neoshader-kit-tests PRIVATE neoshader_core "-framework Foundation" "-framework Metal")
endif()

# macOS: Metal validation of the catalog presets (compile, render, visible
# effect), run by test/neo_shader_kit_catalog_test.py in CI.
if(APPLE)
  enable_language(OBJCXX)
  add_executable(neoshader-metal-validate ${KIT}/Classes/NeoSlangRenderer.mm neoshader_metal_validate.mm)
  target_include_directories(neoshader-metal-validate PRIVATE ${KIT}/Classes/Public)
  target_compile_options(neoshader-metal-validate PRIVATE -fobjc-arc -Wall -Wextra -Wno-unused-parameter)
  target_link_libraries(neoshader-metal-validate PRIVATE neoshader_core
    "-framework Foundation" "-framework Metal" "-framework CoreGraphics" "-framework ImageIO"
    "-framework QuartzCore")
  # Dolphin post-processing shaders drawn through a reproduction of
  # Dolphin's post-processing interface (test/neo_shader_kit_dolphin_test.py).
  add_executable(neoshader-dolphin-validate neoshader_dolphin_validate.mm)
  target_compile_options(neoshader-dolphin-validate PRIVATE -fobjc-arc -Wall -Wextra -Wno-unused-parameter)
  target_link_libraries(neoshader-dolphin-validate PRIVATE neoshader_core "-framework Foundation" "-framework Metal")
endif()
