import 'package:flutter/material.dart';
import 'package:flutter/services.dart' show rootBundle;
import 'package:neostation/l10n/legal_credits_locale.dart';
import 'package:url_launcher/url_launcher.dart';

class LegalCreditsDialog {
  static const _fullRecordUrl =
      'https://github.com/TarbleFR/RewindBox/blob/Claude/docs/LEGAL_AND_CREDITS.md';

  static const List<_LegalEntry> _entries = [
    _LegalEntry(
      'Interactive iOS 26 Inspired Tab Menu',
      'Mau Ali; original dotLottie and adapted navigation motion',
      'Lottie Simple License FL 9.13.21',
      'https://lottiefiles.com/free-animation/free-interactive-ios-26-inspired-tab-menu-uTAhrmTC08',
      'assets/legal/Lottie-Simple-License.txt',
    ),
    _LegalEntry(
      'NeoStation',
      'Miguel Soto / misobadev, androosio, ItsRetroPup and contributors',
      'GPL-3.0-or-later',
      'https://github.com/misobadev/neostation-frontend',
      'assets/legal/NeoStation-GPL-3.0.txt',
    ),
    _LegalEntry(
      'RewindBox',
      'TarbleFR; iOS fork and native integrations',
      'GPL-3.0; upstream rights preserved',
      'https://github.com/TarbleFR/RewindBox',
      'assets/legal/NeoStation-GPL-3.0.txt',
    ),
    _LegalEntry(
      'Dolphin / DolphiniOS',
      'Dolphin Emulator, OatmealDome and contributors',
      'GPL-2.0-or-later for most Dolphin code; per-file SPDX applies',
      'https://github.com/OatmealDome/dolphin-ios',
      'assets/legal/Dolphin-COPYING.txt',
    ),
    _LegalEntry(
      'RPCS3 / XITRIX iOS fork',
      'RPCS3 contributors, XITRIX and credited ARM64/JIT contributors',
      'GPL-2.0-only for most RPCS3 files; per-file notices apply',
      'https://github.com/XITRIX/rpcs3',
      'assets/legal/RPCS3-GPL-2.0.txt',
    ),
    _LegalEntry(
      'ARMSX2 / PCSX2',
      'ARMSX2 and PCSX2 contributors',
      'GPLv3 / upstream component notices',
      'https://github.com/ARMSX2/ARMSX2',
      'assets/legal/ARMSX2-GPL-3.0.txt',
    ),
    _LegalEntry(
      'MeloNX / Ryujinx / LibHac',
      'MeloNX, Ryujinx, LibHac and Melo-Controller contributors',
      'Upstream MIT notice and GPLv3 README declaration preserved; component licenses apply',
      'https://starforgejo.dev/projects/MeloNX',
      'assets/legal/melonx/MeloNX-Ryujinx-LICENSE.txt',
    ),
    _LegalEntry(
      'XeniOS (Xenia for iOS)',
      'Ben Vanik, the Xenia project and XeniOS contributors',
      'BSD-3-Clause; component notices in Legal/XeniOS',
      'https://github.com/xenios-jp/XeniOS',
      'assets/legal/XeniOS-BSD-3-Clause.txt',
    ),
    _LegalEntry(
      'DXBC checksum (AMD), in XeniOS',
      'Advanced Micro Devices, Inc.; adapted by Xenia; derived from the RSA Data Security, Inc. MD5 Message Digest Algorithm',
      'MIT (AMD); RSA Data Security MD5 notice',
      'https://github.com/GPUOpen-Archive/common-src-ShaderUtils',
      'assets/legal/XeniOS-DXBC-notices.txt',
    ),
    _LegalEntry(
      'Apple Metal Shader Converter (runtime used by XeniOS)',
      'Apple Inc.',
      'Apple software license agreement EA1844; headers Apache-2.0; Apple acknowledgements',
      'https://developer.apple.com/metal/shader-converter/',
      'assets/legal/Apple-Metal-Shader-Converter-NOTICES.txt',
    ),
    _LegalEntry(
      'S2Arm (Switch 2)',
      'S2Arm contributors; .NET runtime and listed third parties',
      'Apache-2.0 with NOTICE; component notices in Legal/S2Arm',
      'https://github.com/jhaizhou-ops/S2Arm',
    ),
    _LegalEntry(
      'RewindBox modifications to the engines',
      'TarbleFR; changes made from August 2026',
      'Notice of modified engines, revisions and change locations',
      'https://github.com/TarbleFR/RewindBox',
      'assets/legal/RewindBox-MODIFICATIONS.md',
    ),
    _LegalEntry(
      'FFmpeg (in RPCS3, MeloNX and XeniOS)',
      'FFmpeg developers',
      'LGPL-2.1-or-later; GPL where configured, per engine',
      'https://ffmpeg.org/legal.html',
      'assets/legal/engines/RPCS3-FFmpeg-LICENSE-md.txt',
    ),
    _LegalEntry(
      'SDL3 (in MeloNX and XeniOS)',
      'Sam Lantinga and SDL contributors',
      'zlib',
      'https://github.com/libsdl-org/SDL',
      'assets/legal/melonx/SDL3-COPYING.txt',
    ),
    _LegalEntry(
      'MoltenVK',
      'The Brenwill Workshop Ltd. and MoltenVK contributors',
      'Apache-2.0',
      'https://github.com/KhronosGroup/MoltenVK',
      'assets/legal/libretro/MoltenVK-LICENSE',
    ),
    _LegalEntry(
      'librashader (in ARMSX2)',
      'librashader contributors (SnowflakePowered)',
      'MPL-2.0 or GPL-3.0',
      'https://github.com/SnowflakePowered/librashader',
      'assets/legal/engines/librashader-LICENSE.md',
    ),
    _LegalEntry(
      'rcheevos (RetroAchievements)',
      'RetroAchievements and rcheevos contributors',
      'MIT',
      'https://github.com/RetroAchievements/rcheevos',
      'assets/legal/libretro/rcheevos-LICENSE.txt',
    ),
    _LegalEntry(
      'libchdr, Zstandard, LZMA SDK (RetroAchievements disc reader)',
      'Romain Tisserand; Meta Platforms, Inc.; Igor Pavlov',
      'BSD-3-Clause · BSD · public domain',
      'https://github.com/rtissera/libchdr',
      'assets/legal/libretro/RA-disc-reader-NOTICES.txt',
    ),
    _LegalEntry(
      'Melo-Controller',
      'stossy11 and contributors; original controls and editor',
      'Original license retained',
      'https://github.com/stossy11/Melo-Controller',
      'assets/legal/melonx/Melo-Controller-LICENSE.txt',
    ),
    _LegalEntry(
      'StikJIT',
      'StikDebug and StikJIT contributors',
      'MPL-2.0',
      'https://github.com/StikDebug/StikJIT',
      'assets/legal/StikJIT-MPL-2.0.txt',
    ),
    _LegalEntry(
      'GameDB / GameDB-PS3',
      'Niema / niemasd; source datasets include MiSTer Addons and Redump',
      'GPL-3.0 for GameDB-PS3; dataset attribution preserved',
      'https://github.com/niemasd/GameDB-PS3',
      'assets/legal/GameDB-PS3-GPL-3.0.txt',
    ),
    _LegalEntry(
      'NeoAssets System Art catalogue',
      'NeoAssets and credited community pack creators (20 published packs inventoried)',
      'On-demand third-party artwork; individual creator rights and restrictions apply',
      'https://neoassets.dev/app/sap',
      'assets/legal/THIRD_PARTY_NOTICES.md',
    ),
    _LegalEntry(
      'NeoStation Assets',
      'NeoStation asset contributors; runtime-downloaded System Art catalog',
      'CC BY-NC-SA 4.0 for original creative assets; trademarks remain separate',
      'https://github.com/misobadev/neostation-assets',
      'assets/legal/NeoStation-Assets-CC-BY-NC-SA-4.0.txt',
    ),
    _LegalEntry(
      'RiiSU / iiSU System Art',
      'RiiSU by mult1v4c; icons credited to iiSU Interpreted / iiSU Network',
      'External on-demand artwork; no standalone RiiSU license was published when integrated',
      'https://github.com/mult1v4c/RiiSU',
      'assets/legal/RiiSU-ATTRIBUTION.md',
    ),
    _LegalEntry(
      'Canvas (ES-DE) System Art',
      'Canvas-Capsule custom edition by zenandiko; original Canvas theme by Siddy212',
      'External on-demand artwork; upstream terms: personal, non-commercial use',
      'https://github.com/zenandiko/canvas-es-de',
      'assets/legal/Canvas-ES-DE-ATTRIBUTION.md',
    ),
    _LegalEntry(
      'Once Upon a Time (loop)',
      'TAD; default ambient music of the menus',
      'CC0-1.0 (public domain dedication)',
      'https://opengameart.org/content/once-upon-a-time-loop',
      'assets/legal/OnceUponATime-CC0-1.0.txt',
    ),
    _LegalEntry(
      'glslang',
      'The Khronos Group Inc., Google Inc. and glslang contributors',
      'BSD-3-Clause, BSD-2-Clause, MIT, Apache-2.0, '
          'GPL-3.0-or-later WITH Bison-exception-2.2 · vulkan-sdk-1.4.350.1',
      'https://github.com/KhronosGroup/glslang',
      'assets/legal/glslang-LICENSE.txt',
    ),
    _LegalEntry(
      'SPIRV-Cross',
      'Arm Limited, The Brenwill Workshop Ltd., Hans-Kristian Arntzen, The Khronos Group Inc.',
      'Apache-2.0 · MIT · vulkan-sdk-1.4.350.1',
      'https://github.com/KhronosGroup/SPIRV-Cross',
      'assets/legal/SPIRV-Cross-Apache-2.0.txt',
    ),
    _LegalEntry(
      'RetroArch / libretro',
      'libretro and RetroArch contributors',
      null,
      'https://github.com/libretro/RetroArch',
      'assets/legal/libretro/LIBRETRO_CORES.md',
    ),
    _LegalEntry(
      'Azahar / Citra / Lime3DS',
      'Azahar, Citra, Lime3DS, PabloMK7; FastInterp: warmenhoven',
      'GPL-3.0-or-later',
      'https://github.com/azahar-emu/azahar',
      'assets/legal/libretro/azahar-LICENSE.txt',
    ),
  ];

  static Future<void> show(BuildContext context) {
    return showDialog<void>(
      context: context,
      builder: (dialogContext) {
        final theme = Theme.of(dialogContext);
        return AlertDialog(
          title: Text(LegalCreditsLocale.dialogTitle(dialogContext)),
          content: ConstrainedBox(
            constraints: BoxConstraints(
              // AlertDialog measures intrinsic width; the lazy list cannot.
              minWidth: 760,
              maxWidth: 760,
              maxHeight: MediaQuery.sizeOf(dialogContext).height * 0.72,
            ),
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                Text(
                  LegalCreditsLocale.intro(dialogContext),
                  style: theme.textTheme.bodyMedium,
                ),
                const SizedBox(height: 12),
                const Divider(height: 1),
                const SizedBox(height: 8),
                Flexible(
                  child: ListView.separated(
                    shrinkWrap: true,
                    // The free-software, trademark and no-content notice
                    // scrolls with the entries (a phone has no room above).
                    itemCount: _entries.length + 1,
                    separatorBuilder: (context, index) =>
                        const Divider(height: 1),
                    itemBuilder: (context, index) {
                      if (index == 0) {
                        return Padding(
                          padding: const EdgeInsets.symmetric(vertical: 8),
                          child: Text(
                            LegalCreditsLocale.disclaimer(context),
                            style: theme.textTheme.bodySmall,
                          ),
                        );
                      }
                      final entry = _entries[index - 1];
                      return ListTile(
                        contentPadding: EdgeInsets.zero,
                        title: Text(
                          entry.project,
                          style: theme.textTheme.titleSmall?.copyWith(
                            fontWeight: FontWeight.w700,
                          ),
                        ),
                        subtitle: Text(
                          '${entry.credit}\n'
                          '${entry.license ?? LegalCreditsLocale.embeddedCoreLicenses(context)}',
                        ),
                        isThreeLine: true,
                        trailing: Row(
                          mainAxisSize: MainAxisSize.min,
                          children: [
                            if (entry.licenseAsset != null)
                              const Icon(Icons.description_outlined),
                            IconButton(
                              tooltip: LegalCreditsLocale.source(context),
                              onPressed: () => _launch(entry.url),
                              icon: const Icon(Icons.open_in_new_rounded),
                            ),
                          ],
                        ),
                        onTap: () => entry.licenseAsset == null
                            ? _launch(entry.url)
                            : _showBundledDocument(context, entry),
                      );
                    },
                  ),
                ),
              ],
            ),
          ),
          actions: [
            TextButton.icon(
              onPressed: () => _launch(_fullRecordUrl),
              icon: const Icon(Icons.gavel_rounded),
              label: Text(LegalCreditsLocale.fullRecord(dialogContext)),
            ),
            TextButton(
              onPressed: () => Navigator.of(dialogContext).pop(),
              child: Text(LegalCreditsLocale.close(dialogContext)),
            ),
          ],
        );
      },
    );
  }

  static Future<void> _showBundledDocument(
    BuildContext context,
    _LegalEntry entry,
  ) async {
    final asset = entry.licenseAsset;
    if (asset == null) {
      await _launch(entry.url);
      return;
    }

    String contents;
    try {
      contents = await rootBundle.loadString(asset);
    } catch (_) {
      await _launch(entry.url);
      return;
    }
    if (!context.mounted) return;

    await showDialog<void>(
      context: context,
      builder: (documentContext) => AlertDialog(
        title: Text(
          '${entry.project} — '
          '${LegalCreditsLocale.licenseDocument(documentContext)}',
        ),
        content: ConstrainedBox(
          constraints: BoxConstraints(
            maxWidth: 820,
            maxHeight: MediaQuery.sizeOf(documentContext).height * 0.72,
          ),
          child: Scrollbar(
            child: SingleChildScrollView(
              child: SelectableText(
                contents,
                style: Theme.of(documentContext).textTheme.bodySmall?.copyWith(
                  fontFamily: 'monospace',
                  height: 1.35,
                ),
              ),
            ),
          ),
        ),
        actions: [
          TextButton.icon(
            onPressed: () => _launch(entry.url),
            icon: const Icon(Icons.open_in_new_rounded),
            label: Text(LegalCreditsLocale.source(documentContext)),
          ),
          TextButton(
            onPressed: () => Navigator.of(documentContext).pop(),
            child: Text(LegalCreditsLocale.close(documentContext)),
          ),
        ],
      ),
    );
  }

  static Future<void> _launch(String url) async {
    final uri = Uri.parse(url);
    if (await canLaunchUrl(uri)) {
      await launchUrl(uri, mode: LaunchMode.externalApplication);
    }
  }
}

class _LegalEntry {
  final String project;
  final String credit;
  final String? license;
  final String url;
  final String? licenseAsset;

  const _LegalEntry(
    this.project,
    this.credit,
    this.license,
    this.url, [
    this.licenseAsset,
  ]);
}
