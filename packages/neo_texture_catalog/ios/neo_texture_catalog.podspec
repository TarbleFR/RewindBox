Pod::Spec.new do |s|
  s.name = 'neo_texture_catalog'
  s.version = '0.1.0'
  s.summary = 'Unified HD texture pack catalogue for NeoStation embedded engines.'
  s.description = <<-DESC
One catalogue, download store and "HD textures" page for the textures the
embedded engines replace: ARMSX2 (through its own Build 485 store), Dolphin,
and the libretro PPSSPP, Azahar and Mupen64Plus-Next (GLideN64) cores. Packs
are fetched from their authors' own links when chosen; nothing is re-hosted.
Resources/ps2ktxpak-LICENSE.txt is the MIT notice of the ps2ktxpak catalogue
from which the manual PlayStation 2 entries are derived.
                  DESC
  s.homepage = 'https://github.com/TarbleFR/neostation-ios'
  s.license = { :type => 'GPL-3.0' }
  s.author = { 'NeoStation iOS' => 'TarbleFR' }
  s.source = { :path => '.' }
  # The LZMA SDK sources (public domain) are compiled once, through
  # Classes/NeoTextureLZMA.c, with hidden visibility.
  s.source_files = 'Classes/**/*.{h,m,mm,c}', 'ThirdParty/lzma/*.h'
  s.public_header_files = 'Classes/Public/*.h'
  s.private_header_files = 'Classes/*.h', 'ThirdParty/lzma/*.h'
  s.preserve_paths = 'ThirdParty/lzma/*'
  s.resource_bundles = { 'NeoTextureCatalog' => ['Resources/*.json', 'Resources/*.gz', 'Resources/*.txt'] }
  s.dependency 'Flutter'
  s.platform = :ios, '17.4'
  s.ios.deployment_target = '17.4'
  s.frameworks = 'Foundation', 'UIKit', 'UniformTypeIdentifiers', 'Metal'
  s.libraries = 'z', 'c++'
  s.pod_target_xcconfig = {
    'DEFINES_MODULE' => 'YES',
    'CLANG_ENABLE_OBJC_ARC' => 'YES',
    'CLANG_CXX_LANGUAGE_STANDARD' => 'c++20',
    'HEADER_SEARCH_PATHS' => '$(inherited) "${PODS_TARGET_SRCROOT}/ThirdParty/lzma"',
    'OTHER_LDFLAGS' => '$(inherited) -ObjC'
  }
end
