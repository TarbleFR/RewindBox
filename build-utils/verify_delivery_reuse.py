"""Reject reuse if an input outside the reviewed library/RetroArch delta changed.

Historical results retain their real SHA; this is not new simulator evidence.
The closed tree comparison includes tests, lockfiles, native recipes and assets.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
REFERENCE = 'af0d539b4b8b3b95fe0434fc1f72c74d7c0b6eca'
REFERENCE_RUN = 37781416715
# Receiver-only evidence was added after the last complete NeoStation build.
# It is not a product change and has its own successful, pinned CI provenance.
RECEIVER_REFERENCE = '3c70b5f4adb80232d3c50d0b648520c7db5afe2c'
RECEIVER_RUN = 37857669052
RECEIVER_INPUT = 'test/fixtures/retroarch_handoff/SourceReceiverTests.swift'
DELTA = {
    'lib/data/datasources/sqlite_database_service.dart',
    'lib/data/datasources/sqlite_service.dart', 'lib/main.dart',
    'lib/providers/sqlite_config_provider.dart',
    'lib/providers/sqlite_config_provider/scanning.dart',
    'lib/repositories/system_repository.dart',
    'lib/screens/settings_screen/new_settings_options/directories_settings_content.dart',
    'lib/screens/systems_screen/system_content.dart', 'lib/services/config_service.dart',
    'lib/services/game/game_launch_service.dart',
    'lib/services/ios_rom_library_root_resolver.dart',
    'lib/services/retroarch_library_protocol.dart',
    'lib/services/retroarch_library_service.dart',
    'lib/services/retroarch_folder_recovery.dart',
    'lib/services/retroarch_library_importer.dart',
    'packages/external_folder_access/ios/Classes/ExternalFolderAccessPlugin.swift',
    'packages/external_folder_access/ios/Classes/RetroArchURLHandoff.swift',
    'packages/external_folder_access/lib/external_folder_access.dart',
    'test/armsx2_retroarch_routing_isolation_test.dart',
    'test/ios_selective_rollback_test.dart', 'test/retroarch_folder_recovery_test.dart',
    'test/retroarch_library_restoration_test.dart',
    'test/retroarch_library_cache_test.dart', 'test/retroarch_sync_locale_test.dart',
    'test/retroarch_url_handoff_test.swift', 'test/retroarch_launch_diagnostics_test.dart',
    'test/retroarch_baseline_scope_test.py', 'test/retroarch_real_export_test.dart',
    'test/retroarch_playlist_repair_test.py',
    'test/fixtures/retroarch_handoff/ConsentTests.swift',
    'test/fixtures/retroarch_handoff/LegacyRetroArchURLHandoff.swift',
    'test/fixtures/retroarch_handoff/Receiver.swift',
    'test/fixtures/retroarch_handoff/Sender.swift',
    'test/fixtures/retroarch_handoff/PatchedSceneSyntax.m',
    'test/retroarch_relaunch_cache_test.dart',
    'test/library_scan_restart_test.dart', 'test/delivery_pipeline_test.py',
    'test/rom_folder_registration_test.dart',
    'build-utils/verify_delivery_reuse.py', 'build-utils/delivery_metrics.py',
    'build-utils/sign_delivery.py', 'build-utils/delivery_benchmark.py',
    'build-utils/delivery_cipher.py', 'build-utils/delivery-422-recipient.pem',
    'build-utils/delivery-423-recipient.pem',
    'build-utils/delivery-424-recipient.pem',
}
# Embedded libretro engine requested by the maintainer on 9 October 2026:
# every new or changed validation input of that change, file by file.
LIBRETRO_DELTA = {
    'build-utils/libretro/build_cores.py',
    'build-utils/libretro/cores.json',
    'build-utils/validate_libretro_ipa.py',
    'lib/l10n/libretro_locale.dart',
    'lib/screens/game_screen/game_settings_dialog/game_settings_emulator_tab.dart',
    'lib/screens/game_screen/my_games_list.dart',
    'lib/services/embedded_ios_session_status.dart',
    'lib/services/game_launch_manager.dart',
    'lib/services/libretro_core_catalog.dart',
    'lib/services/libretro_internal_service.dart',
    'lib/widgets/libretro_internal_playlist_actions.dart',
    'packages/libretro_internal_bridge/ios/Classes/LibretroAchievements.h',
    'packages/libretro_internal_bridge/ios/Classes/LibretroAchievements.m',
    'packages/libretro_internal_bridge/ios/Classes/LibretroAudioOutput.h',
    'packages/libretro_internal_bridge/ios/Classes/LibretroAudioOutput.m',
    'packages/libretro_internal_bridge/ios/Classes/LibretroCoreHost.h',
    'packages/libretro_internal_bridge/ios/Classes/LibretroCoreHost.m',
    'packages/libretro_internal_bridge/ios/Classes/LibretroCoreOptions.h',
    'packages/libretro_internal_bridge/ios/Classes/LibretroCoreOptions.m',
    'packages/libretro_internal_bridge/ios/Classes/LibretroGLRenderer.h',
    'packages/libretro_internal_bridge/ios/Classes/LibretroGLRenderer.m',
    'packages/libretro_internal_bridge/ios/Classes/LibretroGameViewController.h',
    'packages/libretro_internal_bridge/ios/Classes/LibretroGameViewController.m',
    'packages/libretro_internal_bridge/ios/Classes/LibretroInputState.h',
    'packages/libretro_internal_bridge/ios/Classes/LibretroInputState.m',
    'packages/libretro_internal_bridge/ios/Classes/LibretroInternalBridgePlugin.h',
    'packages/libretro_internal_bridge/ios/Classes/LibretroInternalBridgePlugin.m',
    'packages/libretro_internal_bridge/ios/Classes/LibretroJit.h',
    'packages/libretro_internal_bridge/ios/Classes/LibretroJit.m',
    'packages/libretro_internal_bridge/ios/Classes/LibretroMetalPresenter.h',
    'packages/libretro_internal_bridge/ios/Classes/LibretroMetalPresenter.m',
    'packages/libretro_internal_bridge/ios/Classes/LibretroSession.h',
    'packages/libretro_internal_bridge/ios/Classes/LibretroSession.m',
    'packages/libretro_internal_bridge/ios/Classes/LibretroSessionMenu.h',
    'packages/libretro_internal_bridge/ios/Classes/LibretroSessionMenu.m',
    'packages/libretro_internal_bridge/ios/Classes/LibretroStateCodec.h',
    'packages/libretro_internal_bridge/ios/Classes/LibretroStateCodec.m',
    'packages/libretro_internal_bridge/ios/Classes/LibretroTouchOverlay.h',
    'packages/libretro_internal_bridge/ios/Classes/LibretroTouchOverlay.m',
    'packages/libretro_internal_bridge/ios/Classes/LibretroVulkanRenderer.h',
    'packages/libretro_internal_bridge/ios/Classes/LibretroVulkanRenderer.m',
    'packages/libretro_internal_bridge/ios/Classes/LibretroZipReader.h',
    'packages/libretro_internal_bridge/ios/Classes/LibretroZipReader.m',
    'packages/libretro_internal_bridge/ios/ThirdParty/include/libretro/SOURCE.txt',
    'packages/libretro_internal_bridge/ios/ThirdParty/include/libretro/libretro.h',
    'packages/libretro_internal_bridge/ios/ThirdParty/include/libretro/libretro_vulkan.h',
    'packages/libretro_internal_bridge/ios/ThirdParty/include/vk_video/vulkan_video_codec_av1std.h',
    'packages/libretro_internal_bridge/ios/ThirdParty/include/vk_video/vulkan_video_codec_av1std_decode.h',
    'packages/libretro_internal_bridge/ios/ThirdParty/include/vk_video/vulkan_video_codec_av1std_encode.h',
    'packages/libretro_internal_bridge/ios/ThirdParty/include/vk_video/vulkan_video_codec_h264std.h',
    'packages/libretro_internal_bridge/ios/ThirdParty/include/vk_video/vulkan_video_codec_h264std_decode.h',
    'packages/libretro_internal_bridge/ios/ThirdParty/include/vk_video/vulkan_video_codec_h264std_encode.h',
    'packages/libretro_internal_bridge/ios/ThirdParty/include/vk_video/vulkan_video_codec_h265std.h',
    'packages/libretro_internal_bridge/ios/ThirdParty/include/vk_video/vulkan_video_codec_h265std_decode.h',
    'packages/libretro_internal_bridge/ios/ThirdParty/include/vk_video/vulkan_video_codec_h265std_encode.h',
    'packages/libretro_internal_bridge/ios/ThirdParty/include/vk_video/vulkan_video_codec_vp9std.h',
    'packages/libretro_internal_bridge/ios/ThirdParty/include/vk_video/vulkan_video_codec_vp9std_decode.h',
    'packages/libretro_internal_bridge/ios/ThirdParty/include/vk_video/vulkan_video_codecs_common.h',
    'packages/libretro_internal_bridge/ios/ThirdParty/include/vulkan/LICENSE.md',
    'packages/libretro_internal_bridge/ios/ThirdParty/include/vulkan/SOURCE.txt',
    'packages/libretro_internal_bridge/ios/ThirdParty/include/vulkan/vk_platform.h',
    'packages/libretro_internal_bridge/ios/ThirdParty/include/vulkan/vulkan.h',
    'packages/libretro_internal_bridge/ios/ThirdParty/include/vulkan/vulkan_core.h',
    'packages/libretro_internal_bridge/ios/ThirdParty/include/vulkan/vulkan_metal.h',
    'packages/libretro_internal_bridge/ios/ThirdParty/rcheevos/LICENSE',
    'packages/libretro_internal_bridge/ios/ThirdParty/rcheevos/SOURCE.txt',
    'packages/libretro_internal_bridge/ios/ThirdParty/rcheevos/include/rc_api_editor.h',
    'packages/libretro_internal_bridge/ios/ThirdParty/rcheevos/include/rc_api_info.h',
    'packages/libretro_internal_bridge/ios/ThirdParty/rcheevos/include/rc_api_request.h',
    'packages/libretro_internal_bridge/ios/ThirdParty/rcheevos/include/rc_api_runtime.h',
    'packages/libretro_internal_bridge/ios/ThirdParty/rcheevos/include/rc_api_user.h',
    'packages/libretro_internal_bridge/ios/ThirdParty/rcheevos/include/rc_client.h',
    'packages/libretro_internal_bridge/ios/ThirdParty/rcheevos/include/rc_consoles.h',
    'packages/libretro_internal_bridge/ios/ThirdParty/rcheevos/include/rc_error.h',
    'packages/libretro_internal_bridge/ios/ThirdParty/rcheevos/include/rc_export.h',
    'packages/libretro_internal_bridge/ios/ThirdParty/rcheevos/include/rc_hash.h',
    'packages/libretro_internal_bridge/ios/ThirdParty/rcheevos/include/rc_runtime.h',
    'packages/libretro_internal_bridge/ios/ThirdParty/rcheevos/include/rc_runtime_types.h',
    'packages/libretro_internal_bridge/ios/ThirdParty/rcheevos/include/rc_util.h',
    'packages/libretro_internal_bridge/ios/ThirdParty/rcheevos/include/rcheevos.h',
    'packages/libretro_internal_bridge/ios/ThirdParty/rcheevos/src/rapi/rc_api_common.c',
    'packages/libretro_internal_bridge/ios/ThirdParty/rcheevos/src/rapi/rc_api_common.h',
    'packages/libretro_internal_bridge/ios/ThirdParty/rcheevos/src/rapi/rc_api_editor.c',
    'packages/libretro_internal_bridge/ios/ThirdParty/rcheevos/src/rapi/rc_api_info.c',
    'packages/libretro_internal_bridge/ios/ThirdParty/rcheevos/src/rapi/rc_api_runtime.c',
    'packages/libretro_internal_bridge/ios/ThirdParty/rcheevos/src/rapi/rc_api_user.c',
    'packages/libretro_internal_bridge/ios/ThirdParty/rcheevos/src/rc_client.c',
    'packages/libretro_internal_bridge/ios/ThirdParty/rcheevos/src/rc_client_external.c',
    'packages/libretro_internal_bridge/ios/ThirdParty/rcheevos/src/rc_client_external.h',
    'packages/libretro_internal_bridge/ios/ThirdParty/rcheevos/src/rc_client_external_versions.h',
    'packages/libretro_internal_bridge/ios/ThirdParty/rcheevos/src/rc_client_internal.h',
    'packages/libretro_internal_bridge/ios/ThirdParty/rcheevos/src/rc_compat.c',
    'packages/libretro_internal_bridge/ios/ThirdParty/rcheevos/src/rc_compat.h',
    'packages/libretro_internal_bridge/ios/ThirdParty/rcheevos/src/rc_libretro.c',
    'packages/libretro_internal_bridge/ios/ThirdParty/rcheevos/src/rc_libretro.h',
    'packages/libretro_internal_bridge/ios/ThirdParty/rcheevos/src/rc_util.c',
    'packages/libretro_internal_bridge/ios/ThirdParty/rcheevos/src/rc_version.c',
    'packages/libretro_internal_bridge/ios/ThirdParty/rcheevos/src/rc_version.h',
    'packages/libretro_internal_bridge/ios/ThirdParty/rcheevos/src/rcheevos/alloc.c',
    'packages/libretro_internal_bridge/ios/ThirdParty/rcheevos/src/rcheevos/condition.c',
    'packages/libretro_internal_bridge/ios/ThirdParty/rcheevos/src/rcheevos/condset.c',
    'packages/libretro_internal_bridge/ios/ThirdParty/rcheevos/src/rcheevos/consoleinfo.c',
    'packages/libretro_internal_bridge/ios/ThirdParty/rcheevos/src/rcheevos/format.c',
    'packages/libretro_internal_bridge/ios/ThirdParty/rcheevos/src/rcheevos/lboard.c',
    'packages/libretro_internal_bridge/ios/ThirdParty/rcheevos/src/rcheevos/memref.c',
    'packages/libretro_internal_bridge/ios/ThirdParty/rcheevos/src/rcheevos/operand.c',
    'packages/libretro_internal_bridge/ios/ThirdParty/rcheevos/src/rcheevos/rc_internal.h',
    'packages/libretro_internal_bridge/ios/ThirdParty/rcheevos/src/rcheevos/rc_validate.c',
    'packages/libretro_internal_bridge/ios/ThirdParty/rcheevos/src/rcheevos/rc_validate.h',
    'packages/libretro_internal_bridge/ios/ThirdParty/rcheevos/src/rcheevos/richpresence.c',
    'packages/libretro_internal_bridge/ios/ThirdParty/rcheevos/src/rcheevos/runtime.c',
    'packages/libretro_internal_bridge/ios/ThirdParty/rcheevos/src/rcheevos/runtime_progress.c',
    'packages/libretro_internal_bridge/ios/ThirdParty/rcheevos/src/rcheevos/trigger.c',
    'packages/libretro_internal_bridge/ios/ThirdParty/rcheevos/src/rcheevos/value.c',
    'packages/libretro_internal_bridge/ios/ThirdParty/rcheevos/src/rhash/aes.c',
    'packages/libretro_internal_bridge/ios/ThirdParty/rcheevos/src/rhash/aes.h',
    'packages/libretro_internal_bridge/ios/ThirdParty/rcheevos/src/rhash/cdreader.c',
    'packages/libretro_internal_bridge/ios/ThirdParty/rcheevos/src/rhash/hash.c',
    'packages/libretro_internal_bridge/ios/ThirdParty/rcheevos/src/rhash/hash_disc.c',
    'packages/libretro_internal_bridge/ios/ThirdParty/rcheevos/src/rhash/hash_encrypted.c',
    'packages/libretro_internal_bridge/ios/ThirdParty/rcheevos/src/rhash/hash_rom.c',
    'packages/libretro_internal_bridge/ios/ThirdParty/rcheevos/src/rhash/hash_zip.c',
    'packages/libretro_internal_bridge/ios/ThirdParty/rcheevos/src/rhash/md5.c',
    'packages/libretro_internal_bridge/ios/ThirdParty/rcheevos/src/rhash/md5.h',
    'packages/libretro_internal_bridge/ios/ThirdParty/rcheevos/src/rhash/rc_hash_internal.h',
    'packages/libretro_internal_bridge/ios/libretro_internal_bridge.podspec',
    'packages/libretro_internal_bridge/lib/libretro_internal_bridge.dart',
    'packages/libretro_internal_bridge/pubspec.yaml',
    'pubspec.yaml',
    'test/cheats_media_source_contract_test.py',
    'test/frontend_media_gate_test.dart',
    'test/integrated_import_tab_contract_test.py',
    'test/libretro_core_catalog_test.dart',
    'test/libretro_core_options_test.py',
    'test/libretro_host/host_test.m',
    'test/libretro_host/stubs/Flutter/Flutter.h',
    'test/libretro_host/test_core.c',
    'test/libretro_host_test.py',
    'test/libretro_ios_syntax_test.py',
    'test/libretro_locale_test.dart',
    'test/libretro_route_contract_test.py',
    'test/localization_12_locale_coverage_test.py',
}
DELTA |= LIBRETRO_DELTA
# Obsolete files removed on 9 October 2026 at the maintainer's request: Dart
# code unreachable from lib/main.dart, the tests of that dead code, and build
# files nothing references. dusklight_locale_test now checks the live Ports
# import menu instead of the removed Dusklight-only widget.
CLEANUP_DELTA = {
    'build-utils/canonical-host-285.json',
    'build-utils/generate_import_labels.py',
    'build-utils/materialize_dolphin_isolated_v2.py',
    'build-utils/migrations/candidate302/part0.b64',
    'build-utils/patches/grid_title_build243.patch',
    'build-utils/private-test-360-recipient.pem',
    'build-utils/private-test-361-recipient.pem',
    'build-utils/private-test-362-recipient.pem',
    'build-utils/private-test-363-recipient.pem',
    'build-utils/private-test-364-recipient.pem',
    'build-utils/private-test-366-recipient.pem',
    'build-utils/private-test-367-recipient.pem',
    'build-utils/verify_delivery_reuse.py',
    'lib/models/retroarch_config_model.dart',
    'lib/services/metadata_cleanup_service.dart',
    'lib/services/retroarch_config_service.dart',
    'lib/services/retroarch_playlist_service.dart',
    'lib/services/rom_folder_organizer_service.dart',
    'lib/services/scraped_media_migration_service.dart',
    'lib/utils/switch_save_detector.dart',
    'lib/widgets/dusklight_internal_playlist_actions.dart',
    'lib/widgets/info_dialog.dart',
    'lib/widgets/selection_grid/grid_navigation.dart',
    'lib/widgets/selection_grid/selection_grid.dart',
    'lib/widgets/selection_grid/selection_grid_geometry.dart',
    'test/dusklight_locale_test.dart',
    'test/metadata_cleanup_service_test.dart',
    'test/rom_folder_organizer_service_test.dart',
    'test/selection_grid_cache_test.dart',
    'test/selection_grid_test.dart',
}
DELTA |= CLEANUP_DELTA
# Second pass, same day: declarations nothing calls (found by reference
# counts over the whole repository, iterated to a fixed point), the
# RetroAchievements hash strategies left without caller, imports they used,
# and the unused Dart wrapper of the Dolphin plugin.
UNUSED_CODE_DELTA = {
    'lib/data/datasources/sqlite_config_service.dart',
    'lib/l10n/dusklight_locale.dart',
    'lib/l10n/fork_onboarding_locale.dart',
    'lib/models/database_game_model.dart',
    'lib/models/my_systems.dart',
    'lib/providers/file_provider.dart',
    'lib/providers/menu_app_provider.dart',
    'lib/providers/neo_assets_provider.dart',
    'lib/providers/retro_achievements_provider.dart',
    'lib/providers/retroachievements/console_lookup_hash_strategy.dart',
    'lib/providers/retroachievements/default_md5_hash_strategy.dart',
    'lib/providers/retroachievements/ds_hash_strategy.dart',
    'lib/providers/retroachievements/nes_hash_strategy.dart',
    'lib/providers/retroachievements/retro_achievements_hash_strategy.dart',
    'lib/providers/retroachievements/strategy_factory.dart',
    'lib/providers/scraping_provider.dart',
    'lib/providers/sqlite_config_provider/mutators.dart',
    'lib/providers/sqlite_database_provider.dart',
    'lib/responsive.dart',
    'lib/screens/app_screen.dart',
    'lib/services/audio_policy_service.dart',
    'lib/services/game_service.dart',
    'lib/services/game_session_persistence.dart',
    'lib/services/home_music_service.dart',
    'lib/services/library_addon_service.dart',
    'lib/services/library_metadata_provider_service.dart',
    'lib/services/melonx_library_service.dart',
    'lib/services/music_player_service.dart',
    'lib/services/neo_assets_service.dart',
    'lib/services/permission_service.dart',
    'lib/services/retro_achievements_service.dart',
    'lib/services/saf_directory_service.dart',
    'lib/services/screenscraper/media_resolver.dart',
    'lib/services/screenscraper_service.dart',
    'lib/services/systems_update_service.dart',
    'lib/services/user_data_location_service.dart',
    'lib/themes/app_themes.dart',
    'lib/themes/corner_radii.dart',
    'lib/utils/centered_scroll_controller.dart',
    'lib/utils/color.dart',
    'lib/utils/gamepad_mapping.dart',
    'lib/utils/gamepad_nav.dart',
    'lib/utils/gamepad_translator.dart',
    'lib/utils/login_form_selection.dart',
    'lib/utils/optimized_md5_utils.dart',
    'lib/widgets/custom_notification.dart',
    'lib/widgets/game_view_mode_dropdown.dart',
    'packages/dolphin_internal_bridge/lib/dolphin_internal_bridge.dart',
    'packages/dolphin_internal_bridge/ios/Classes/TouchController/TCWiiPad.swift',
    'lib/models/emulator_model.dart',
    'lib/models/system_model.dart',
    'lib/services/stikjit_melonx_service.dart',
}
DELTA |= UNUSED_CODE_DELTA
# Third pass, same day, after the maintainer allowed removing unusable
# RPCS3 code: the Build 260 action-sheet menus nothing presents, the
# recovery-core patch pipeline no workflow runs, the Dolphin touch-resource
# generator, the tests of those removed files, and the RPCS3 Dart
# declarations nothing calls.
RPCS3_UNUSED_DELTA = {
    'build-utils/.rpcs3_patch_chunk00',
    'build-utils/.rpcs3_patch_chunk01',
    'build-utils/.rpcs3_patch_chunk02',
    'build-utils/.rpcs3_patch_chunk02a',
    'build-utils/.rpcs3_patch_chunk02b',
    'build-utils/.rpcs3_patch_chunk02c',
    'build-utils/.rpcs3_patch_chunk03',
    'build-utils/.rpcs3_patch_chunk03a',
    'build-utils/.rpcs3_patch_chunk04',
    'build-utils/.rpcs3_patch_chunk05',
    'build-utils/benchmark_rpcs3_pipeline_scheduler.py',
    'build-utils/build_rpcs3_recovery_core.sh',
    'build-utils/compare_rpcs3_core_profiles.py',
    'build-utils/compare_rpcs3_telemetry.py',
    'build-utils/generate_rpcs3_ios_profiles.py',
    'build-utils/materialize_rpcs3_internal.py',
    'build-utils/patch_rpcs3_armsx3_performance.py',
    'build-utils/patch_rpcs3_build251_upscale.py',
    'build-utils/patch_rpcs3_build256_host.py',
    'build-utils/patch_rpcs3_build256_savestates.py',
    'build-utils/patch_rpcs3_build258_core_architecture.py',
    'build-utils/patch_rpcs3_build258_runtime_resilience.py',
    'build-utils/patch_rpcs3_build260_modern_menu.py',
    'build-utils/patch_rpcs3_build264_gow3_core.py',
    'build-utils/patch_rpcs3_build265_core.py',
    'build-utils/patch_rpcs3_build265_host.py',
    'build-utils/patch_rpcs3_build266_v09_core.py',
    'build-utils/patch_rpcs3_build283_host.py',
    'build-utils/patch_rpcs3_build295_fixed_reservation.py',
    'build-utils/patch_rpcs3_embedded_boot.py',
    'build-utils/patch_rpcs3_iso_integrity.py',
    'build-utils/patch_rpcs3_jit_memory.py',
    'build-utils/patch_rpcs3_neostation_session.py',
    'build-utils/patch_rpcs3_performance_telemetry.py',
    'build-utils/patch_rpcs3_savestate_stability.py',
    'build-utils/patch_rpcs3_savestate_ui.py',
    'build-utils/patch_rpcs3_serial_profiles.py',
    'build-utils/patch_rpcs3_stop_reply270.py',
    'build-utils/patches/rpcs3_build243_host.patch',
    'build-utils/patches/rpcs3_build243_menu_transition.patch',
    'build-utils/patches/rpcs3_build246_safe_controls.patch',
    'build-utils/patches/rpcs3_build247_localization.patch',
    'build-utils/patches/rpcs3_build251_upscale.patch',
    'build-utils/patches/rpcs3_build264_spu_arm64_lowering.patch',
    'build-utils/patches/rpcs3_build265_core.patch',
    'build-utils/rpcs3/build266-v09-manifest.json',
    'build-utils/rpcs3/jit_arena.cpp.inc',
    'build-utils/rpcs3/jit_write_scope.h.inc',
    'build-utils/validate_rpcs3_recovery_core.py',
    'lib/l10n/rpcs3_library_locale.dart',
    'lib/l10n/rpcs3_ui_locale.dart',
    'lib/services/rpcs3_internal_service.dart',
    'lib/services/rpcs3_launch_service.dart',
    'lib/services/rpcs3_library_service.dart',
    'lib/services/rpcs3_title_catalog_service.dart',
    'packages/dolphin_internal_bridge/ci/materialize_touch_resources.py',
    'packages/dolphin_internal_bridge/ci/touch_resources.json',
    'packages/rpcs3_internal_bridge/ios/Classes/Rpcs3InternalBridgePlugin.mm',
    'packages/rpcs3_internal_bridge/vendor/README.md',
    'test/neoplay_build397_integration_test.py',
    'test/rpcs3_build251_contract_test.py',
    'test/rpcs3_build256_host_patch_test.py',
    'test/rpcs3_build258_core_profile_comparison_test.py',
    'test/rpcs3_build258_pipeline_scheduler_benchmark_test.py',
    'test/rpcs3_build260_modern_menu_test.py',
    'test/rpcs3_build265_host_test.py',
    'test/rpcs3_build266_v09_core_test.py',
    'test/rpcs3_build295_fixed_reservation_test.py',
    'test/rpcs3_embedded_boot_test.py',
    'test/rpcs3_ingame_ui_contract_test.py',
    'test/rpcs3_jit_memory_test.py',
    'test/rpcs3_performance_snapshot_test.py',
    'test/rpcs3_recovery_core_contract_test.py',
    'test/rpcs3_savestate_ui_contract_test.py',
    'test/rpcs3_silent_mode_policy_test.dart',
    'test/rpcs3_stop_reply270_test.py',
    'test/rpcs3_telemetry_comparison_test.py',
}
DELTA |= RPCS3_UNUSED_DELTA
# Same day: the Armsx2 action builder left from the retired contextual
# UIMenu, and the command handler and overload only it invoked.
ARMSX2_UNUSED_DELTA = {
    'packages/armsx2_internal_bridge/ios/Classes/Armsx2InternalBridgePlugin.mm',
}
DELTA |= ARMSX2_UNUSED_DELTA
# Embedded libretro frontend (maintainer request of 9 October 2026): PSP and
# 3DS on the embedded cores, skins per console with Delta / Provenance
# import, Metal shader presets, screen format, controls customisation,
# portrait, twelve languages. New native modules, their macOS behaviour
# tests, the Dart services and screens, and the call sites switched to the
# canonical console key. Reviewed source changes; see
# docs/libretro-skins-shaders.md.
FRONTEND_DELTA = {
    'lib/screens/libretro/libretro_consoles_screen.dart',
    'lib/screens/libretro/libretro_skin_catalog_screen.dart',
    'lib/screens/libretro/libretro_skin_manager_screen.dart',
    'lib/services/libretro_skin_catalog_service.dart',
    'lib/services/libretro_skin_service.dart',
    'packages/libretro_internal_bridge/ios/Classes/LibretroDefaultSkins.h',
    'packages/libretro_internal_bridge/ios/Classes/LibretroDefaultSkins.m',
    'packages/libretro_internal_bridge/ios/Classes/LibretroFrontendMenu.h',
    'packages/libretro_internal_bridge/ios/Classes/LibretroFrontendMenu.m',
    'packages/libretro_internal_bridge/ios/Classes/LibretroFrontendStore.h',
    'packages/libretro_internal_bridge/ios/Classes/LibretroFrontendStore.m',
    'packages/libretro_internal_bridge/ios/Classes/LibretroGeometry.h',
    'packages/libretro_internal_bridge/ios/Classes/LibretroGeometry.m',
    'packages/libretro_internal_bridge/ios/Classes/LibretroInputMap.h',
    'packages/libretro_internal_bridge/ios/Classes/LibretroInputMap.m',
    'packages/libretro_internal_bridge/ios/Classes/LibretroOrientation.h',
    'packages/libretro_internal_bridge/ios/Classes/LibretroOrientation.m',
    'packages/libretro_internal_bridge/ios/Classes/LibretroShaderLibrary.h',
    'packages/libretro_internal_bridge/ios/Classes/LibretroShaderLibrary.m',
    'packages/libretro_internal_bridge/ios/Classes/LibretroSkin.h',
    'packages/libretro_internal_bridge/ios/Classes/LibretroSkin.m',
    'packages/libretro_internal_bridge/ios/Classes/LibretroSkinLayout.h',
    'packages/libretro_internal_bridge/ios/Classes/LibretroSkinLayout.m',
    'packages/libretro_internal_bridge/ios/Classes/LibretroSkinRenderer.h',
    'packages/libretro_internal_bridge/ios/Classes/LibretroSkinRenderer.m',
    'test/libretro_frontend_test.py',
    'test/libretro_frontend_ui_contract_test.py',
    'test/libretro_host/frontend/default_skins_test.m',
    'test/libretro_host/frontend/frontend_store_test.m',
    'test/libretro_host/frontend/geometry_test.m',
    'test/libretro_host/frontend/input_map_test.m',
    'test/libretro_host/frontend/skin_layout_test.m',
    'test/libretro_host/frontend/skin_test.m',
    'test/libretro_host/shader_test.m',
    'test/libretro_shader_catalog_test.py',
    'test/libretro_shader_test.py',
    'test/libretro_skin_catalog_test.dart',
    'test/libretro_skin_manager_test.dart',
    'test/libretro_skin_service_test.dart',
    'packages/libretro_internal_bridge/ios/Classes/LibretroChromeLayout.h',
    'packages/libretro_internal_bridge/ios/Classes/LibretroChromeLayout.m',
    'test/libretro_host/frontend/chrome_layout_test.m',
    'test/libretro_playlist_actions_test.dart',
}
DELTA |= FRONTEND_DELTA
# 3DS close and PSP start (maintainer report of 10 October 2026, video
# ScreenRecording_10-10-2026 01-04-54): RetroArch's teardown order (the
# hardware context outlives retro_unload_game and retro_deinit), core stops
# during startup reported as launch failures, the session journal, the
# PPSSPP memory window report, their macOS tests and the iOS Simulator probe
# with the real cores. See docs/libretro-3ds-psp-lifecycle.md.
LIFECYCLE_DELTA = {
    'packages/libretro_internal_bridge/ios/Classes/LibretroAddressSpace.h',
    'packages/libretro_internal_bridge/ios/Classes/LibretroAddressSpace.m',
    'packages/libretro_internal_bridge/ios/Classes/LibretroSessionJournal.h',
    'packages/libretro_internal_bridge/ios/Classes/LibretroSessionJournal.m',
    'test/libretro_host/frontend/address_space_test.m',
    'test/libretro_host/frontend/session_journal_test.m',
    'test/libretro_host/vulkan_test_core.c',
    'test/libretro_simulator/probe.m',
    'test/libretro_simulator_probe.py',
}
DELTA |= LIFECYCLE_DELTA
# Library folders (maintainer requests of 10 October 2026): saved folders
# found again after iOS moved an app container, imports into one of the
# user's own libraries without duplicates, NeoStation's console folders and
# moving a library into them, offered at first launch and in Settings.
LIBRARY_DELTA = {
    'lib/screens/libretro/libretro_library_actions.dart',
    'lib/services/ios_library_root_relocation.dart',
    'lib/services/neostation_rom_library.dart',
    'lib/widgets/setup_wizard.dart',
    'test/ios_library_root_relocation_test.dart',
    'test/neostation_rom_library_test.dart',
}
DELTA |= LIBRARY_DELTA
# NeoSwap Build434 (maintainer request of 10 October 2026, RPCS3 memory):
# the measured jetsam envelope of the host process in the budget policy, the
# demand-driven size-class shelves of relay host loans in the broker, the
# cold-storage prefetch planner, the plugin diagnostics that export them,
# their portable tests, and the hash manifest the NeoSwap scope gate reads
# (bookkeeping of those same files, not an engine). The pinned RPCS3 Core,
# the relay and donor extensions, the storage engine and every other native
# engine are byte-identical. See docs/neoswap-build434-7go-envelope.md.
NEOSWAP_434_DELTA = {
    'packages/neo_swap/ios/Classes/NeoSwap.cpp',
    'packages/neo_swap/ios/Classes/NeoSwapBudget.h',
    'packages/neo_swap/ios/Classes/NeoSwapColdPrefetch.h',
    'packages/neo_swap/ios/Classes/NeoSwapHost.h',
    'packages/neo_swap/ios/Classes/NeoSwapPlugin.mm',
    'test/neoswap_budget_test.cpp',
    'test/neoswap_cold_prefetch_test.cpp',
    'test/neoswap_relay_loans_test.cpp',
    'test/import_memory_candidate_scope_test.py',
    'test/neoplay_build397_integration_test.py',
    'native/import-memory-candidate.json',
}
DELTA |= NEOSWAP_434_DELTA
# RPCS3 Core Build435 (maintainer request of 10 October 2026): the three
# reviewed Core deltas of docs/neoswap-build435-core-delta.md inside the single
# canonical patch (measured memory allowance, deferred SPU compilation,
# writer-lock precheck), its hash manifest, the host-executed policy test,
# the Core build recipe and syntax gate that run it, the pinned-input test,
# the updated Build352 contract, the scope gates and the hash manifest they
# read. The delivery lane still reuses the Core artifact pinned by run id;
# a new Core run is pinned only after it succeeds.
NEOSWAP_435_DELTA = {
    'build-utils/rpcs3/embedded-core.patch',
    'build-utils/rpcs3/canonical-source.json',
    'build-utils/build_rpcs3_embedded_core.sh',
    'build-utils/rpcs3_core_syntax_gate.py',
    'test/neo_swap_core_pin_test.py',
    'test/rpcs3_build352_gow3_memory_test.py',
    'test/rpcs3_build435_core_delta_test.py',
    'test/native/rpcs3_build435_core_delta_test.cpp',
    'test/check_neo_swap_scope.py',
    'test/import_memory_candidate_scope_test.py',
    'test/delivery_pipeline_test.py',
    'test/neoplay_build397_integration_test.py',
    'native/import-memory-candidate.json',
}
DELTA |= NEOSWAP_435_DELTA
# Controller battery in the header (maintainer report of 10 October 2026: the
# indicator stayed at 100% with an Xbox Series X controller; it showed the
# phone's battery). The header now shows the connected controller's battery,
# read by NeoPlay's existing GameController monitor.
BATTERY_DELTA = {
    'lib/services/controller_battery_service.dart',
    'lib/widgets/header.dart',
    'lib/widgets/header_battery.dart',
    'packages/neoplay_bridge/ios/Classes/NPControllerBatteryMonitor.swift',
    'packages/neoplay_bridge/ios/Classes/NeoPlayBridgePlugin.swift',
    'packages/neoplay_bridge/lib/neoplay_bridge.dart',
    'test/header_battery_test.dart',
    'test/neoplay/companion_tests.swift',
}
DELTA |= BATTERY_DELTA
# Build 436 Core (10 October 2026): the Build 435 deferred SPU compilation is
# switched off after God of War III froze on the iPhone, and five RSX/Vulkan
# commits of XITRIX v0.11 are imported with their fixtures, which the new host
# test runs before the Core build. The third-party notices gained the skin
# catalog credits (08145438) and are bundled with the app.
BUILD436_DELTA = {
    'test/rpcs3_xitrix_v011_native_test.py',
    'assets/legal/THIRD_PARTY_NOTICES.md',
}
DELTA |= BUILD436_DELTA
# Build 437 reading Library (maintainer request of 10 October 2026): Aidoku
# catalogue preview and selective activation, native adapters re-verified
# against the live sites, local EPUB/PDF/CBZ/TXT library and iOS readers,
# shared Library network cache, 12-locale catalogs. The libretro bridge gains
# only the reader orientation method (listed in LIBRETRO_DELTA).
BUILD437_DELTA = {
    'lib/services/library_io_client.dart',
    'test/library_infra_io_client_test.dart',
    'test/library_ui_dates_test.dart',
    'test/library_ui_details_refresh_test.dart',
    'test/library_ui_hub_open_test.dart',
    'test/library_ui_l10n_terms_test.dart',
    'lib/l10n/library_date_format.dart',
    'test/library_date_format_test.dart',
    'lib/l10n/library_feature_locale.dart',
    'lib/l10n/library_local_locale.dart',
    'lib/l10n/library_reader_locale.dart',
    'lib/l10n/library_sources_locale.dart',
    'lib/screens/library_screen/library_catalog_preview_screen.dart',
    'lib/screens/library_screen/library_favorites_view.dart',
    'lib/screens/library_screen/library_gamepad_view_controller.dart',
    'lib/screens/library_screen/library_hub_dialog.dart',
    'lib/screens/library_screen/library_local_view.dart',
    'lib/screens/library_screen/library_manga_details_screen.dart',
    'lib/screens/library_screen/library_pdf_reader_screen.dart',
    'lib/screens/library_screen/library_reader_launcher.dart',
    'lib/screens/library_screen/library_reader_screen.dart',
    'lib/screens/library_screen/library_screen.dart',
    'lib/screens/library_screen/library_sources_view.dart',
    'lib/screens/library_screen/reader/library_book_reader_screen.dart',
    'lib/screens/library_screen/reader/library_page_reader_content.dart',
    'lib/screens/library_screen/reader/library_page_reader_controller.dart',
    'lib/screens/library_screen/reader/library_page_reader_screen.dart',
    'lib/screens/library_screen/reader/library_page_source.dart',
    'lib/screens/library_screen/reader/library_reader_chrome.dart',
    'lib/screens/library_screen/reader/library_reader_errors.dart',
    'lib/screens/library_screen/reader/library_reader_gamepad.dart',
    'lib/screens/library_screen/reader/library_reader_palette.dart',
    'lib/screens/library_screen/reader/library_reader_sheets.dart',
    'lib/screens/library_screen/reader/library_reader_system.dart',
    'lib/screens/library_screen/reader/library_reflow_source.dart',
    'lib/screens/library_screen/reader/library_reflow_view.dart',
    'lib/services/library_aidoku_engines.dart',
    'lib/services/library_aidoku_native_service.dart',
    'lib/services/library_aidoku_parsing.dart',
    'lib/services/library_archive_pages.dart',
    'lib/services/library_book_formats.dart',
    'lib/services/library_catalog_feed.dart',
    'lib/services/library_catalog_service.dart',
    'lib/services/library_epub.dart',
    'lib/services/library_http.dart',
    'lib/services/library_image_cache.dart',
    'lib/services/library_local_library_service.dart',
    'lib/services/library_local_models.dart',
    'lib/services/library_manga_models.dart',
    'lib/services/library_reader_orientation.dart',
    'lib/services/library_reading_store.dart',
    'lib/services/library_source_catalog_service.dart',
    'lib/services/library_source_health_store.dart',
    'lib/services/library_source_support.dart',
    'lib/services/library_text_document.dart',
    'lib/widgets/library_focus_gamepad_layer.dart',
    'test/fixtures/library_aidoku/README.md',
    'test/fixtures/library_aidoku/cloudflare_challenge_403.html',
    'test/fixtures/library_aidoku/lelscan_catalog_p1.html',
    'test/fixtures/library_aidoku/lelscan_catalog_p21.html',
    'test/fixtures/library_aidoku/lelscan_chapter_one_piece_1194.html',
    'test/fixtures/library_aidoku/lelscan_chapters_one_piece_p2.html',
    'test/fixtures/library_aidoku/lelscan_chapters_one_piece_p3.html',
    'test/fixtures/library_aidoku/lelscan_chapters_one_piece_p4.html',
    'test/fixtures/library_aidoku/lelscan_chapters_one_piece_p5.html',
    'test/fixtures/library_aidoku/lelscan_chapters_one_piece_p6.html',
    'test/fixtures/library_aidoku/lelscan_details_maria_no_danzai.html',
    'test/fixtures/library_aidoku/lelscan_details_one_piece.html',
    'test/fixtures/library_aidoku/lelscan_home_p1.html',
    'test/fixtures/library_aidoku/lelscan_search_one_piece.html',
    'test/fixtures/library_aidoku/mangascantrad_chapter_regressed_son_5.html',
    'test/fixtures/library_aidoku/mangascantrad_details_unknown_code.html',
    'test/fixtures/library_aidoku/mangascantrad_listing.html',
    'test/fixtures/library_aidoku/mangasorigines_ajax_chapters_solo_leveling.html',
    'test/fixtures/library_aidoku/mangasorigines_catalogue_solo_p1.json',
    'test/fixtures/library_aidoku/mangasorigines_catalogue_solo_p2.json',
    'test/fixtures/library_aidoku/mangasorigines_catalogue_the_p1.json',
    'test/fixtures/library_aidoku/mangasorigines_chapter_solo_leveling_200.html',
    'test/fixtures/library_aidoku/mangasorigines_details_solo_leveling.html',
    'test/fixtures/library_aidoku/mangasorigines_details_swordmaster.html',
    'test/fixtures/library_aidoku/mangasorigines_listing_latest_p0.html',
    'test/fixtures/library_aidoku/sushiscan_catalogue_update_p1.html',
    'test/fixtures/library_aidoku/sushiscan_catalogue_update_p145.html',
    'test/fixtures/library_aidoku/sushiscan_chapter_kagurabachi_119.html',
    'test/fixtures/library_aidoku/sushiscan_details_kagurabachi.html',
    'test/fixtures/library_aidoku/sushiscan_details_one_piece.html',
    'test/fixtures/library_aidoku/sushiscan_search_new_gotham.html',
    'test/fixtures/library_aidoku/sushiscan_search_the_p1.html',
    'test/fixtures/library_aidoku/sushiscans_catalog_p1.html',
    'test/fixtures/library_aidoku/sushiscans_chapter_one_piece_1179.html',
    'test/fixtures/library_aidoku/sushiscans_details_one_piece.html',
    'test/fixtures/library_catalog/aidoku_community_index_excerpt.json',
    'test/fixtures/library_catalog/aidoku_french_legacy_index.min.json',
    'test/fixtures/library_catalog/source_legacy_mangascantrad.json',
    'test/fixtures/library_catalog/source_new_bigsolo.json',
    'test/library_addon_service_test.dart',
    'test/library_aidoku_lelscan_test.dart',
    'test/library_aidoku_live_check_test.dart',
    'test/library_aidoku_madara_test.dart',
    'test/library_aidoku_native_service_test.dart',
    'test/library_aidoku_parsing_test.dart',
    'test/library_aidoku_test_support.dart',
    'test/library_aidoku_themesia_test.dart',
    'test/library_catalog_import_activation_test.dart',
    'test/library_catalog_import_catalog_service_test.dart',
    'test/library_catalog_import_fakes.dart',
    'test/library_catalog_import_preview_test.dart',
    'test/library_e2e_journeys_test.dart',
    'test/library_e2e_live_test.dart',
    'test/library_feed_catalog_test.dart',
    'test/library_feed_content_filter_test.dart',
    'test/library_feed_search_test.dart',
    'test/library_feed_test_fakes.dart',
    'test/library_infra_http_test.dart',
    'test/library_infra_image_cache_test.dart',
    'test/library_infra_reading_store_test.dart',
    'test/library_local_archive_pages_test.dart',
    'test/library_local_epub_test.dart',
    'test/library_local_fixtures.dart',
    'test/library_local_formats_test.dart',
    'test/library_local_library_service_test.dart',
    'test/library_local_text_document_test.dart',
    'test/library_no_native_sources_test.dart',
    'test/library_reader_book_test.dart',
    'test/library_reader_locale_test.dart',
    'test/library_reader_misc_test.dart',
    'test/library_reader_orientation_contract_test.py',
    'test/library_reader_orientation_test.dart',
    'test/library_reader_page_test.dart',
    'test/library_reader_test_support.dart',
    'test/library_reading_store_notify_test.dart',
    'test/library_ui_details_progressive_test.dart',
    'test/library_ui_details_screen_test.dart',
    'test/library_ui_hub_favorites_test.dart',
    'test/library_ui_hub_locale_test.dart',
    'test/library_ui_hub_test.dart',
    'test/library_ui_local_locale_test.dart',
    'test/library_ui_local_view_test.dart',
    'test/library_ui_sources_focus_layer_test.dart',
    'test/library_ui_sources_harness.dart',
    'test/library_ui_sources_health_store_test.dart',
    'test/library_ui_sources_locale_test.dart',
    'test/library_ui_sources_preview_test.dart',
    'test/library_ui_sources_view_test.dart',
}
DELTA |= BUILD437_DELTA
# Maintainer-requested MeloNX memory adaptation for RPCS3, 11 October 2026.
# These host allocator/control-plane inputs require the new NeoSwap native
# checks in retroarch-delivery.yml. Core recipes, Mach IPC, extension sources,
# entitlements and every other emulator stay outside this explicit delta.
NEOSWAP_MELONX_DELTA = {
    'native/neoswap-donation/Pool.cpp',
    'native/neoswap-relay/Backend.cpp',
    'packages/neo_swap/ios/Classes/NeoSwapDonationScheduler.h',
    'packages/neo_swap/ios/Classes/NeoSwapPlugin.mm',
    'test/neoswap_demand_test.cpp',
    'test/neoswap_pool_fragmentation_test.cpp',
    'test/neoswap_relay_loans_test.cpp',
    'test/relay_backend_test.cpp',
}
DELTA |= NEOSWAP_MELONX_DELTA
# RPCS3 NeoSwap donation accounting, 11 October 2026: active published guest
# backing plus active host relay/donor loans, truthful graph/settings labels,
# and their behavioral checks. No Core, allocation policy, IPC or extension
# capability changes are admitted by this list.
NEOSWAP_DONATED_DELTA = {
    'build-utils/validate_neoswap_donation_metrics.py',
    'lib/l10n/neoswap_locale.dart',
    'lib/screens/settings_screen/neoswap_dialog.dart',
    'native/neoswap-relay/Backend.cpp',
    'native/neoswap-relay/Backend.h',
    'native/neoswap/localizations.json',
    'packages/neo_swap/ios/Classes/NeoSwap.cpp',
    'packages/neo_swap/ios/Classes/NeoSwapDonationMetrics.h',
    'packages/neo_swap/ios/Classes/NeoSwapHost.h',
    'packages/neo_swap/ios/Classes/NeoSwapPlugin.mm',
    'packages/neo_swap/ios/Classes/NeoSwapRelayService.mm',
    'packages/neo_swap/ios/neo_swap.podspec',
    'packages/rpcs3_internal_bridge/ios/Classes/NeoSwapUsagePolicy.h',
    'packages/rpcs3_internal_bridge/ios/Classes/RPCS3InGameLocalization.mm',
    'packages/rpcs3_internal_bridge/ios/Classes/RPCS3PerformanceOverlay.h',
    'packages/rpcs3_internal_bridge/ios/Classes/RPCS3PerformanceOverlay.mm',
    'packages/rpcs3_internal_bridge/ios/Classes/Rpcs3InternalBridgePlugin.mm',
    'test/neo_swap_dialog_test.dart',
    'test/neoswap_donor_contract_test.py',
    'test/neoswap_usage_policy_test.cpp',
    'test/neoswap_relay_loans_test.cpp',
    'test/relay_backend_test.cpp',
    'test/rpcs3_neoswap_localizations_test.py',
}
DELTA |= NEOSWAP_DONATED_DELTA
# Build 440 (maintainer requests of 11 October 2026, built on top of the
# NeoSwap Builds 438 and 439): Dolphin Wii touch Shake and its controller row,
# RAP licence import, main-bar consoles tab, 120 Hz interface plugin, BIOS
# checker, Embedded RetroArch settings, reader Back button and Library source
# files. See docs/build440-plan.md.
BUILD440_DELTA = {
    'assets/data/libretro_bios_requirements.json',
    'lib/l10n/app_locale_de.dart',
    'lib/l10n/app_locale_en.dart',
    'lib/l10n/app_locale_es.dart',
    'lib/l10n/app_locale_fr.dart',
    'lib/l10n/app_locale_id.dart',
    'lib/l10n/app_locale_it.dart',
    'lib/l10n/app_locale_ja.dart',
    'lib/l10n/app_locale_ko.dart',
    'lib/l10n/app_locale_pt.dart',
    'lib/l10n/app_locale_ru.dart',
    'lib/l10n/app_locale_zh.dart',
    'lib/l10n/app_locale_zh_hant.dart',
    'lib/l10n/dolphin_import_locale.dart',
    'lib/l10n/dolphin_shake_locale.dart',
    'lib/l10n/ios_setup_locale.dart',
    'lib/l10n/rpcs3_rap_locale.dart',
    'lib/l10n/ui_refresh_rate_locale.dart',
    'lib/screens/libretro/libretro_bios_checker_screen.dart',
    'lib/screens/settings_screen/new_settings_options/general_settings_content.dart',
    'lib/screens/settings_screen/new_settings_options/tools_settings_content.dart',
    'lib/screens/settings_screen/new_settings_options/widgets/ui_refresh_rate_setting_row.dart',
    'lib/services/library_source_files.dart',
    'lib/services/libretro_bios_catalog.dart',
    'lib/services/libretro_bios_check_service.dart',
    'lib/services/libretro_engine_choices.dart',
    'lib/services/libretro_main_menu.dart',
    'lib/services/rpcs3_rap_licence_service.dart',
    'lib/services/ui_refresh_rate_service.dart',
    'lib/utils/frame_cadence_estimator.dart',
    'lib/utils/nav_tabs.dart',
    'lib/widgets/libretro_engine_panel.dart',
    'lib/widgets/main_menu_tab_strip.dart',
    'lib/widgets/notification_bell.dart',
    'lib/widgets/rpcs3_internal_playlist_actions.dart',
    'lib/widgets/rpcs3_rap_import_report_dialog.dart',
    'lib/widgets/system_emulator_settings_dialog.dart',
    'lib/widgets/system_emulator_settings_dialog/gamepad_nav.dart',
    'lib/widgets/system_emulator_settings_dialog/tabs.dart',
    'packages/dolphin_internal_bridge/ios/Classes/DolphinInternalBridgePlugin.mm',
    'packages/dolphin_internal_bridge/ios/Classes/DolphinSessionMenu.mm',
    'packages/dolphin_internal_bridge/ios/Classes/TouchController/DolphinShakeAssignment.h',
    'packages/dolphin_internal_bridge/ios/Classes/TouchController/DolphinShakeAssignment.mm',
    'packages/dolphin_internal_bridge/ios/Classes/TouchController/DolphinShakeButton.swift',
    'packages/dolphin_internal_bridge/ios/Classes/TouchController/DolphinShakeInput.swift',
    'packages/dolphin_internal_bridge/ios/Classes/TouchController/DolphinTouchOverlay.swift',
    'packages/dolphin_internal_bridge/ios/dolphin_internal_bridge.podspec',
    'packages/ui_refresh_rate/ios/Classes/UiRefreshRateEngineHook.h',
    'packages/ui_refresh_rate/ios/Classes/UiRefreshRateEngineHook.m',
    'packages/ui_refresh_rate/ios/Classes/UiRefreshRatePlugin.h',
    'packages/ui_refresh_rate/ios/Classes/UiRefreshRatePlugin.m',
    'packages/ui_refresh_rate/ios/ui_refresh_rate.podspec',
    'packages/ui_refresh_rate/lib/ui_refresh_rate.dart',
    'packages/ui_refresh_rate/pubspec.yaml',
    'test/dolphin_shake_assignment_test.cpp',
    'test/dolphin_shake_assignment_test.mm',
    'test/dolphin_shake_assignment_test.py',
    'test/dolphin_shake_locale_test.dart',
    'test/dolphin_shake_wiring_test.py',
    'test/dolphin_touch_shake_test.py',
    'test/dolphin_touch_shake_ui_test.py',
    'test/fixtures/libretro_bios/core_info_5a74858a.json',
    'test/frame_cadence_estimator_test.dart',
    'test/general_settings_ui_refresh_rate_test.dart',
    'test/jit_backend_preference_service_test.dart',
    'test/library_reader_back_button_test.dart',
    'test/library_source_files_app_test.dart',
    'test/library_source_files_test.dart',
    'test/libretro_bios_catalog_test.dart',
    'test/libretro_bios_check_service_test.dart',
    'test/libretro_bios_checker_screen_test.dart',
    'test/libretro_bios_launch_test.dart',
    'test/libretro_bios_requirements_test.py',
    'test/libretro_consoles_tab_test.dart',
    'test/libretro_engine_settings_test.dart',
    'test/libretro_main_menu_test.dart',
    'test/main_menu_tab_strip_test.dart',
    'test/nav_tabs_test.dart',
    'test/notification_bell_idle_test.dart',
    'test/rpcs3_firmware_library_test.dart',
    'test/rpcs3_internal_integration_test.dart',
    'test/rpcs3_rap_core_contract_test.py',
    'test/rpcs3_rap_import_menu_test.dart',
    'test/rpcs3_rap_licence_service_test.dart',
    'test/rpcs3_rap_locale_test.dart',
    'test/ui_refresh_rate_hook_test.py',
    'test/ui_refresh_rate_locale_test.dart',
    'test/ui_refresh_rate_scope_test.py',
    'test/ui_refresh_rate_service_test.dart',
}
DELTA |= BUILD440_DELTA

# Build 442 (11 October 2026, evening): Wii phone-shake sensitivity and hold,
# Dolphin external display (AirPlay) Fit/Fill, 60 Hz pacing default with
# frame-time counters, RPCS3 game-save ZIP exchange. Dolphin Core and RPCS3
# Core untouched.
BUILD442_DELTA = {
    'build-utils/verify_delivery_reuse.py',
    'lib/l10n/dolphin_display_locale.dart',
    'lib/l10n/dolphin_import_locale.dart',
    'lib/l10n/dolphin_shake_locale.dart',
    'lib/l10n/rpcs3_saves_locale.dart',
    'lib/l10n/rpcs3_ui_locale.dart',
    'lib/models/dolphin_phone_shake_settings.dart',
    'lib/screens/rpcs3_manager_screen.dart',
    'lib/services/dolphin_internal_v2_service.dart',
    'lib/services/rpcs3_internal_service.dart',
    'lib/services/rpcs3_param_sfo.dart',
    'lib/services/rpcs3_save_exchange_service.dart',
    'lib/widgets/dolphin_wii_motion_panel.dart',
    'lib/widgets/rpcs3_save_exchange_dialogs.dart',
    'lib/widgets/system_emulator_settings_dialog.dart',
    'lib/widgets/system_emulator_settings_dialog/tabs.dart',
    'packages/dolphin_internal_bridge/ci/test_session_ui.rb',
    'packages/dolphin_internal_bridge/ios/Classes/DolphinExternalDisplay.h',
    'packages/dolphin_internal_bridge/ios/Classes/DolphinExternalDisplay.mm',
    'packages/dolphin_internal_bridge/ios/Classes/DolphinExternalDisplayLayout.h',
    'packages/dolphin_internal_bridge/ios/Classes/DolphinFramePacing.h',
    'packages/dolphin_internal_bridge/ios/Classes/DolphinFramePacing.mm',
    'packages/dolphin_internal_bridge/ios/Classes/DolphinInternalBridgePlugin.mm',
    'packages/dolphin_internal_bridge/ios/Classes/DolphinPacingLabels.h',
    'packages/dolphin_internal_bridge/ios/Classes/DolphinPerformanceOverlay.mm',
    'packages/dolphin_internal_bridge/ios/Classes/DolphinPhoneShakePreferences.h',
    'packages/dolphin_internal_bridge/ios/Classes/DolphinSessionMenu.mm',
    'packages/dolphin_internal_bridge/ios/Classes/TouchController/DolphinPhoneShake.swift',
    'packages/dolphin_internal_bridge/ios/Classes/TouchController/DolphinShakeDetector.swift',
    'packages/dolphin_internal_bridge/ios/Classes/TouchController/DolphinTouchOverlay.swift',
    'packages/dolphin_internal_bridge/ios/dolphin_internal_bridge.podspec',
    'test/armsx2_graphics_ui_test.py',
    'test/diagnostics_files_workspace_test.py',
    'test/dolphin_account_267_test.py',
    'test/dolphin_external_display_test.mm',
    'test/dolphin_external_display_test.py',
    'test/dolphin_external_display_ui_test.py',
    'test/dolphin_pacing362_ui_test.py',
    'test/dolphin_phone_shake_test.py',
    'test/dolphin_shake_locale_test.dart',
    'test/dolphin_shake_wiring_test.py',
    'test/dolphin_touch_shake_ui_test.py',
    'test/dolphin_wii_motion_panel_test.dart',
    'test/localization_12_locale_coverage_test.py',
    'test/rpcs3_save_exchange_service_test.dart',
    'test/rpcs3_save_export_contract_test.dart',
    'test/rpcs3_saves_locale_test.dart',
    'test/rpcs3_ui_status_cleanup_test.py',
}
DELTA |= BUILD442_DELTA
BUILD444_DELTA = {
    'build-utils/build_rpcs3_embedded_core.sh',
    'build-utils/rpcs3/canonical-source.json',
    'build-utils/rpcs3/embedded-core.patch',
    'build-utils/verify_delivery_reuse.py',
    'native/import-memory-candidate.json',
    'native/neoswap-relay/Backend.cpp',
    'native/neoswap-relay/Backend.h',
    'packages/neo_swap/ios/Classes/NeoSwapBudget.h',
    'packages/neo_swap/ios/Classes/NeoSwapPlugin.mm',
    'packages/neo_swap/ios/Classes/NeoSwapRelay.h',
    'packages/neo_swap/ios/Classes/NeoSwapRelayService.mm',
    'packages/rpcs3_internal_bridge/ios/Classes/Rpcs3CoreABI.h',
    'packages/rpcs3_internal_bridge/ios/Classes/Rpcs3InternalBridgePlugin.mm',
    'test/native/rpcs3_build444_core_delta_test.cpp',
    'test/native/rpcs3_neoswap_relay_test.cpp',
    'test/neo_swap_core_pin_test.py',
    'test/neoswap_budget_test.cpp',
    'test/relay_backend_test.cpp',
    'test/rpcs3_build444_core_delta_test.py',
    'test/rpcs3_neoswap_build_comparison_test.py',
    'test/rpcs3_neoswap_relay_test.py',
}
DELTA |= BUILD444_DELTA
# Build 481 (18 October 2026): persistent ARM64 SPU object cache of the RPCS3 Core;
# host evidence files of the Core delta.
BUILD481_DELTA = {
    'test/native/rpcs3_build481_spu_object_cache_test.cpp',
    'test/native/rpcs3_spu_object_relocation_test.cpp',
    'test/rpcs3_build481_spu_object_cache_test.py',
}
DELTA |= BUILD481_DELTA
# Build 483 (18 October 2026): selectable LLVM pipelines of the RPCS3 recompilers;
# host evidence files of the Core delta.
BUILD483_DELTA = {
    'test/native/rpcs3_llvm_pipeline_harness.cpp',
    'test/rpcs3_build483_llvm_pipeline_test.py',
}
DELTA |= BUILD483_DELTA
# Build 487 (19 October 2026): diagnostics and levers of the RPCS3 bottleneck audit;
# host evidence files of the Core delta and of the bridge diagnostics.
BUILD487_DELTA = {
    'test/rpcs3_build487_core_diagnostics_test.py',
    'test/rpcs3_build487_host_diagnostics_test.py',
    'test/native/rpcs3_build487_profiler_helpers_test.cpp',
    'test/native/rpcs3_build487_boot_diagnostics_test.cpp',
    'test/native/rpcs3_build487_lever_helpers_test.cpp',
    'test/native/rpcs3_build487_retention_sequence_test.cpp',
    'test/rpcs3_build258_core_architecture_test.py',
    'test/native/rpcs3_diagnostics_test.mm',
    'build-utils/rpcs3/regenerate_canonical_delta.py',
}
DELTA |= BUILD487_DELTA
# Build 482 (18 October 2026): ARMSX2 blending accuracy (Core ABI 7, in-game menu)
# and the Get More RAM information before a PS3 firmware installation.
BUILD482_DELTA = {
    'packages/armsx2_internal_bridge/core/ARMSX2BlendingAccuracy.h',
    'packages/armsx2_internal_bridge/core/ARMSX2BlendingAccuracy.inc',
    'lib/l10n/rpcs3_firmware_locale.dart',
    'lib/widgets/rpcs3_firmware_preflight_dialog.dart',
    'test/armsx2_blending_accuracy_test.mm',
    'test/rpcs3_firmware_preflight_test.dart',
    'test/build482_targeted_test.py',
}
DELTA |= BUILD482_DELTA
# New inputs of the libretro skin/touch commits 4da31544..f28525fd (other session,
# 11-12 October 2026) present on Claude when Build 444 was delivered; listed so the
# closed-tree check names them instead of refusing every later delivery.
LIBRETRO_SKINS_INPUTS_DELTA = {
    'assets/data/libretro_skin_overlays.json',
    'lib/services/libretro_overlay_converter.dart',
    'lib/services/libretro_skin_catalogs.dart',
    'lib/services/libretro_skin_compatibility.dart',
    'lib/services/libretro_skin_remote_inspector.dart',
    'packages/libretro_internal_bridge/ios/Classes/LibretroInputLatch.h',
    'packages/libretro_internal_bridge/ios/Classes/LibretroInputLatch.m',
    'packages/libretro_internal_bridge/ios/Classes/LibretroSkinCompatibility.h',
    'packages/libretro_internal_bridge/ios/Classes/LibretroSkinCompatibility.m',
    'packages/libretro_internal_bridge/ios/Classes/LibretroTouchDiagnosticsView.h',
    'packages/libretro_internal_bridge/ios/Classes/LibretroTouchDiagnosticsView.m',
    'packages/libretro_internal_bridge/ios/Classes/LibretroTouchTracker.h',
    'packages/libretro_internal_bridge/ios/Classes/LibretroTouchTracker.m',
    'test/libretro_host/frontend/input_latch_test.m',
    'test/libretro_host/frontend/skin_compatibility_test.m',
    'test/libretro_host/frontend/touch_tracker_test.m',
    'test/libretro_skin_catalogs_test.dart',
}
DELTA |= LIBRETRO_SKINS_INPUTS_DELTA
# Build 445 (12 October 2026), built on the delivered Build 444 (a221ae0c): the
# public key the encrypted artifact of this session is addressed to (its private
# key stays outside the repository). The skin catalog test the delivery now runs is
# declared above; the delivery workflow is outside the input roots.
BUILD445_DELTA = {
    'build-utils/delivery-445-recipient.pem',
}
DELTA |= BUILD445_DELTA
# Build 447 chantier 1 (12 October 2026): universal AirPlay/external display.
# One host infrastructure (packages/external_display, dynamic framework) owns
# the window of the external scene and places the TV menu (second Flutter
# engine) or the running engine's render view on it; Dolphin, libretro, RPCS3
# and ARMSX2 bridges adopt NeoExternalRenderHost, Dusklight suspends it and
# KartPad through Flutter (its bridge stays pinned with its Core, delivery run
# 38207626900 stopped at that guard before any IPA);
# global setting in Settings > General; generated host role via
# configure_external_display_ios.py. Every created or modified input, file by
# file (docs/external-display-universal.md).
BUILD447_EXTERNAL_DISPLAY_DELTA = {
    # CI harnesses that compile bridge sources: the headers the pod publishes
    # are staged as <external_display/...> and its Flutter-free sources linked
    # (test/libretro_ios_syntax_test.py stage_external_display).
    '.github/workflows/armsx2-core.yml',
    '.github/workflows/dolphin-motion-check.yml',
    '.github/workflows/dolphin-pacing-check.yml',
    '.github/workflows/external-display-check.yml',
    '.github/workflows/ios-ci.yml',
    '.github/workflows/neoswap-ipa.yml',
    '.github/workflows/retroarch-delivery.yml',
    'build-utils/configure_external_display_ios.py',
    'build-utils/verify_delivery_reuse.py',
    'lib/external_display/external_display_entrypoint.dart',
    'lib/external_display/external_display_state_channel.dart',
    'lib/external_display/external_menu_screen.dart',
    'lib/l10n/external_display_locale.dart',
    'lib/l10n/neoplay_companion_locale.dart',
    'lib/screens/app_screen.dart',
    'lib/screens/game_screen/my_games_list.dart',
    'lib/screens/game_screen/my_games_list/secondary_display.dart',
    'lib/screens/secondary_screen/secondary_screen.dart',
    'lib/screens/settings_screen/new_settings_options/general_settings_content.dart',
    'lib/screens/settings_screen/new_settings_options/widgets/external_display_setting_rows.dart',
    'lib/screens/systems_screen/my_systems_section/my_systems_carousel.dart',
    'lib/screens/systems_screen/my_systems_section/my_systems_grid.dart',
    'lib/screens/systems_screen/my_systems_section/my_systems_grid/theme_background.dart',
    'lib/services/external_display_service.dart',
    'lib/services/kartpad_internal_service.dart',
    'lib/services/secondary_display_bridge.dart',
    'lib/widgets/neoplay_apple_tv_card.dart',
    'packages/armsx2_internal_bridge/ios/Classes/Armsx2InternalBridgePlugin.mm',
    'packages/armsx2_internal_bridge/ios/armsx2_internal_bridge.podspec',
    'packages/dolphin_internal_bridge/ios/Classes/DolphinExternalDisplay.h',
    'packages/dolphin_internal_bridge/ios/Classes/DolphinExternalDisplay.mm',
    'packages/dolphin_internal_bridge/ios/Classes/DolphinExternalDisplayLayout.h',
    'packages/dolphin_internal_bridge/ios/Classes/DolphinFramePacing.h',
    'packages/dolphin_internal_bridge/ios/Classes/DolphinFramePacing.mm',
    'packages/dolphin_internal_bridge/ios/Classes/DolphinInternalBridgePlugin.mm',
    'packages/dolphin_internal_bridge/ios/Classes/DolphinPacingLabels.h',
    'packages/dolphin_internal_bridge/ios/dolphin_internal_bridge.podspec',
    'packages/dusklight_internal_bridge/ios/Classes/DusklightInternalBridgePlugin.mm',
    'packages/dusklight_internal_bridge/ios/dusklight_internal_bridge.podspec',
    'packages/external_display/ios/Classes/ExternalDisplayPlugin.h',
    'packages/external_display/ios/Classes/ExternalDisplayPlugin.m',
    'packages/external_display/ios/Classes/NeoExternalDisplayCoordinator.h',
    'packages/external_display/ios/Classes/NeoExternalDisplayCoordinator.m',
    'packages/external_display/ios/Classes/NeoExternalDisplayLabels.h',
    'packages/external_display/ios/Classes/NeoExternalDisplayLayout.h',
    'packages/external_display/ios/Classes/NeoExternalDisplayMenuEngine.h',
    'packages/external_display/ios/Classes/NeoExternalDisplayMenuEngine.m',
    'packages/external_display/ios/Classes/NeoExternalDisplayPreferences.h',
    'packages/external_display/ios/Classes/NeoExternalDisplayPreferences.m',
    'packages/external_display/ios/Classes/NeoExternalDisplaySceneDelegate.h',
    'packages/external_display/ios/Classes/NeoExternalDisplaySceneDelegate.m',
    'packages/external_display/ios/Classes/NeoExternalRenderHost.h',
    'packages/external_display/ios/external_display.podspec',
    'packages/external_display/lib/external_display.dart',
    'packages/external_display/pubspec.yaml',
    'packages/libretro_internal_bridge/ios/Classes/LibretroGameViewController.h',
    'packages/libretro_internal_bridge/ios/Classes/LibretroGameViewController.m',
    'packages/libretro_internal_bridge/ios/Classes/LibretroInternalBridgePlugin.m',
    'packages/libretro_internal_bridge/ios/Classes/LibretroRenderSurface.h',
    'packages/libretro_internal_bridge/ios/Classes/LibretroSession.h',
    'packages/libretro_internal_bridge/ios/Classes/LibretroSession.m',
    'packages/libretro_internal_bridge/ios/libretro_internal_bridge.podspec',
    'packages/neoplay_bridge/ios/Classes/NPController.swift',
    'packages/rpcs3_internal_bridge/ios/Classes/Rpcs3InternalBridgePlugin.mm',
    'packages/rpcs3_internal_bridge/ios/rpcs3_internal_bridge.podspec',
    'packages/ui_refresh_rate/ios/Classes/UiRefreshRatePlugin.m',
    'pubspec.lock',
    'pubspec.yaml',
    'test/armsx2_external_display_test.py',
    'test/delivery_pipeline_test.py',
    'test/dolphin_account_267_test.py',
    'test/dolphin_external_display_test.mm',
    'test/dolphin_external_display_test.py',
    'test/dolphin_external_display_ui_test.py',
    'test/dolphin_touch_shake_ui_test.py',
    'test/external_display_host_plist_test.py',
    'test/external_display_labels_test.py',
    'test/external_display_games_list_test.dart',
    'test/external_display_layout_test.mm',
    'test/external_display_locale_test.dart',
    'test/external_display_scope_test.py',
    'test/external_display_service_test.dart',
    'test/external_display_test.py',
    'test/external_display_ui_test.py',
    'test/external_display_unsupported_engine_test.dart',
    'test/external_menu_screen_test.dart',
    'test/general_settings_external_display_test.dart',
    'test/general_settings_ui_refresh_rate_test.dart',
    'test/libretro_external_surface_test.py',
    'test/libretro_host/frontend/render_surface_test.m',
    'test/libretro_ios_syntax_test.py',
    'test/libretro_simulator_probe.py',
    'test/localization_12_locale_coverage_test.py',
    'test/neoplay_locale_test.dart',
    'test/ports_external_display_test.py',
    'test/rpcs3_external_display_test.py',
}
DELTA |= BUILD447_EXTERNAL_DISPLAY_DELTA
# Build 447, Nintendo 3DS system settings and data (12 October 2026,
# docs/libretro-3ds-system-settings.md): language/region/model of the
# azahar core through the Dart option store, launch-time language default,
# Emulators-tab page with system data inventory, import and restore, and
# the CI lists that run their tests. Dart only: no native or core change.
BUILD447_3DS_DELTA = {
    '.github/workflows/libretro-checks.yml',
    '.github/workflows/retroarch-delivery.yml',
    'build-utils/verify_delivery_reuse.py',
    'lib/l10n/libretro_locale.dart',
    'lib/screens/libretro/libretro_3ds_system_screen.dart',
    'lib/services/libretro_3ds_language.dart',
    'lib/services/libretro_3ds_system_data_service.dart',
    'lib/services/libretro_core_catalog.dart',
    'lib/services/libretro_core_option_store.dart',
    'lib/services/libretro_internal_service.dart',
    'lib/widgets/libretro_engine_panel.dart',
    'test/libretro_3ds_language_test.dart',
    'test/libretro_3ds_launch_default_test.dart',
    'test/libretro_3ds_system_data_service_test.dart',
    'test/libretro_3ds_system_screen_test.dart',
    'test/libretro_core_catalog_test.dart',
    'test/libretro_core_option_store_test.dart',
    'test/libretro_core_options_test.py',
    'test/libretro_engine_settings_test.dart',
    'test/libretro_locale_test.dart',
}
DELTA |= BUILD447_3DS_DELTA
# Build 447 chantier 3, books and mangas in 3D (12 October 2026,
# docs/library-books-3d-plan.md): every created or modified input, file by
# file, added as each phase lands (reader catalog first).
BUILD447_BOOKS_DELTA = {
    'assets/shaders/page_curl.frag',
    'build-utils/verify_delivery_reuse.py',
    'lib/l10n/library_reader_locale.dart',
    'lib/screens/library_screen/library_favorites_view.dart',
    'lib/screens/library_screen/library_local_view.dart',
    'lib/screens/library_screen/library_pdf_reader_screen.dart',
    'lib/screens/library_screen/library_reader_launcher.dart',
    'lib/screens/library_screen/library_screen.dart',
    'lib/screens/library_screen/reader/library_book_pages_view.dart',
    'lib/screens/library_screen/reader/library_book_reader_screen.dart',
    'lib/screens/library_screen/reader/library_page_curl.dart',
    'lib/screens/library_screen/reader/library_page_reader_controller.dart',
    'lib/screens/library_screen/reader/library_page_reader_screen.dart',
    'lib/screens/library_screen/reader/library_page_spreads.dart',
    'lib/screens/library_screen/reader/library_page_textures.dart',
    'lib/screens/library_screen/reader/library_pdf_pages_view.dart',
    'lib/screens/library_screen/reader/library_reader_bookmarks.dart',
    'lib/screens/library_screen/reader/library_reader_chrome.dart',
    'lib/screens/library_screen/reader/library_reader_effective_settings.dart',
    'lib/screens/library_screen/reader/library_reader_gamepad.dart',
    'lib/screens/library_screen/reader/library_reader_sheets.dart',
    'lib/screens/library_screen/reader/library_reader_toolbar.dart',
    'lib/screens/library_screen/reader/library_reader_trace.dart',
    'lib/screens/library_screen/reader/library_reflow_paginator.dart',
    'lib/screens/library_screen/reader/library_reflow_view.dart',
    'lib/services/library_reading_store.dart',
    'lib/widgets/library_book_cover.dart',
    'lib/widgets/library_book_open_transition.dart',
    'lib/widgets/library_book_volume.dart',
    'lib/widgets/library_reduce_motion.dart',
    'pubspec.yaml',
    'test/library_book_cover_test.dart',
    'test/library_book_open_transition_test.dart',
    'test/library_book_volume_test.dart',
    'test/library_books_3d_contract_test.py',
    'test/library_e2e_journeys_test.dart',
    'test/library_infra_reading_store_test.dart',
    'test/library_page_curl_test.dart',
    'test/library_page_spreads_test.dart',
    'test/library_page_textures_test.dart',
    'test/library_reader_accessibility_test.dart',
    'test/library_reader_back_button_test.dart',
    'test/library_reader_book_pages_test.dart',
    'test/library_reader_book_test.dart',
    'test/library_reader_bookmarks_test.dart',
    'test/library_reader_effective_settings_test.dart',
    'test/library_reader_gamepad_test.dart',
    'test/library_reader_locale_test.dart',
    'test/library_reader_misc_test.dart',
    'test/library_reader_page_precedence_test.dart',
    'test/library_reader_page_spreads_test.dart',
    'test/library_reader_page_test.dart',
    'test/library_reader_page_turns_test.dart',
    'test/library_reader_pdf_modes_test.dart',
    'test/library_reader_settings_sections_test.dart',
    'test/library_reader_toolbar_test.dart',
    'test/library_reading_store_bookmarks_test.dart',
    'test/library_reflow_paginator_test.dart',
    'test/library_ui_details_refresh_test.dart',
    'test/library_ui_hub_favorites_test.dart',
    'test/library_ui_hub_test.dart',
    'test/library_ui_local_view_test.dart',
}
DELTA |= BUILD447_BOOKS_DELTA
# Build 447 chantier 5, storage analysis and cleanup (12 October 2026,
# docs/storage-audit-cleanup.md): every created or modified input, file by
# file, added as each phase lands (translation catalog first).
BUILD447_STORAGE_DELTA = {
    'build-utils/verify_delivery_reuse.py',
    'lib/l10n/storage_locale.dart',
    'lib/repositories/storage_maintenance_repository.dart',
    'lib/screens/game_screen/game_settings_dialog/game_settings_scrapping_tab.dart',
    'lib/screens/libretro/libretro_3ds_system_screen.dart',
    'lib/screens/libretro/libretro_library_actions.dart',
    'lib/screens/settings_screen/new_settings_options/themes_settings_content.dart',
    'lib/screens/settings_screen/new_settings_options/tools_settings_content.dart',
    'lib/screens/storage/storage_audit_screen.dart',
    'lib/screens/storage/storage_cleanup_preview_screen.dart',
    'lib/screens/storage/storage_screen_widgets.dart',
    'lib/services/armsx2_internal_service.dart',
    'lib/services/dolphin_internal_v2_service.dart',
    'lib/services/dolphin_smart_import_service.dart',
    'lib/services/dusklight_internal_service.dart',
    'lib/services/home_music_service.dart',
    'lib/services/kartpad_internal_service.dart',
    'lib/services/library_local_library_service.dart',
    'lib/services/libretro_internal_service.dart',
    'lib/services/libretro_skin_service.dart',
    'lib/services/pairing_file_service.dart',
    'lib/services/rpcs3_content_import_service.dart',
    'lib/services/rpcs3_internal_service.dart',
    'lib/services/rpcs3_rap_licence_service.dart',
    'lib/services/rpcs3_save_exchange_service.dart',
    'lib/services/storage/storage_categorizer.dart',
    'lib/services/storage/storage_cleanup_planner.dart',
    'lib/services/storage/storage_deletion_manager.dart',
    'lib/services/storage/storage_import_activity.dart',
    'lib/services/storage/storage_orphan_detector.dart',
    'lib/services/storage/storage_picker_copies.dart',
    'lib/services/storage/storage_report.dart',
    'lib/services/storage/storage_roots.dart',
    'lib/services/storage/storage_scanner.dart',
    'lib/services/storage/storage_stat_ffi.dart',
    'lib/widgets/system_emulator_settings_dialog.dart',
    'lib/widgets/system_emulator_settings_dialog/tabs.dart',
    'test/jit_backend_preference_service_test.dart',
    'test/libretro_bios_checker_screen_test.dart',
    'test/localization_12_locale_coverage_test.py',
    'test/neoplay_build397_integration_test.py',
    'test/storage_audit_screen_test.dart',
    'test/storage_categorizer_test.dart',
    'test/storage_cleanup_planner_test.dart',
    'test/storage_contract_test.py',
    'test/storage_deletion_manager_test.dart',
    'test/storage_import_activity_test.dart',
    'test/storage_locale_test.dart',
    'test/storage_log_rotation_test.dart',
    'test/storage_maintenance_repository_test.dart',
    'test/storage_orphan_detector_test.dart',
    'test/storage_picker_copies_test.dart',
    'test/storage_report_test.dart',
    'test/storage_roots_test.dart',
    'test/storage_scanner_test.dart',
    'test/storage_stat_ffi_test.dart',
    'test/storage_tools_row_test.dart',
}
DELTA |= BUILD447_STORAGE_DELTA
# Build 448 (12 October 2026, docs/build448-plan.md): ambient music « Once
# Upon a Time » (single manager, CC0 asset and notice), universal Consoles
# tab with the built-in engine switches and Settings › General « Use the
# built-in emulators », adaptive skin catalog and manager, confirmed touch
# defects of the libretro bridge, 3DS essential.exefs and encrypted-game
# check, and this session's delivery recipient key. Every created, modified
# or deleted input since the Build 447 source af3cec8a, file by file.
BUILD448_DELTA = {
    'assets/legal/OnceUponATime-CC0-1.0.txt',
    'assets/legal/THIRD_PARTY_NOTICES.md',
    'assets/sounds/once_upon_a_time_loop.ogg',
    'build-utils/delivery-448-recipient.pem',
    'build-utils/embed_legal_bundle.py',
    'build-utils/verify_delivery_reuse.py',
    'lib/l10n/ambient_music_locale.dart',
    'lib/l10n/console_manager_locale.dart',
    'lib/l10n/home_music_locale.dart',
    'lib/l10n/libretro_locale.dart',
    'lib/l10n/skin_browser_locale.dart',
    'lib/screens/app_screen.dart',
    'lib/screens/libretro/libretro_3ds_system_screen.dart',
    'lib/screens/libretro/libretro_consoles_screen.dart',
    'lib/screens/libretro/libretro_skin_catalog_screen.dart',
    'lib/screens/libretro/libretro_skin_manager_screen.dart',
    'lib/screens/settings_screen/legal_credits_dialog.dart',
    'lib/screens/settings_screen/new_settings_options/general_settings_content.dart',
    'lib/screens/settings_screen/new_settings_options/themes_settings_content.dart',
    'lib/screens/settings_screen/new_settings_options/widgets/ambient_music_setting_rows.dart',
    'lib/screens/settings_screen/new_settings_options/widgets/embedded_engines_setting_row.dart',
    'lib/services/console_catalog.dart',
    'lib/services/embedded_engine_policy.dart',
    'lib/services/game/game_launch_service.dart',
    'lib/services/game/game_session_manager.dart',
    'lib/services/home_music_service.dart',
    'lib/services/libretro_3ds_containers.dart',
    'lib/services/libretro_3ds_system_data_service.dart',
    'lib/services/libretro_internal_service.dart',
    'lib/services/libretro_main_menu.dart',
    'lib/services/music_player_service.dart',
    'lib/widgets/armsx2_internal_playlist_actions.dart',
    'lib/widgets/dolphin_internal_playlist_actions.dart',
    'packages/libretro_internal_bridge/ios/Classes/LibretroInputLatch.h',
    'packages/libretro_internal_bridge/ios/Classes/LibretroInputLatch.m',
    'packages/libretro_internal_bridge/ios/Classes/LibretroInputState.m',
    'packages/libretro_internal_bridge/ios/Classes/LibretroSkinLayout.m',
    'packages/libretro_internal_bridge/ios/Classes/LibretroTouchTracker.m',
    'test/ambient_music_locale_test.dart',
    'test/ambient_music_loop_test.py',
    'test/ambient_music_service_test.dart',
    'test/armsx2_retroarch_routing_isolation_test.dart',
    'test/console_manager_test.dart',
    'test/embedded_engine_route_contract_test.py',
    'test/game_audio_handoff_test.py',
    'test/general_settings_external_display_test.dart',
    'test/general_settings_ui_refresh_rate_test.dart',
    'test/home_music_silent_mode_test.dart',
    'test/libretro_3ds_encrypted_launch_test.dart',
    'test/libretro_3ds_system_data_service_test.dart',
    'test/libretro_3ds_system_screen_test.dart',
    'test/libretro_consoles_tab_test.dart',
    'test/libretro_frontend_ui_contract_test.py',
    'test/libretro_host/frontend/input_latch_test.m',
    'test/libretro_host/frontend/skin_layout_test.m',
    'test/libretro_host/frontend/touch_tracker_test.m',
    'test/libretro_skin_manager_test.dart',
    'test/localization_12_locale_coverage_test.py',
    'test/native/ambient_music_loop_harness.cpp',
    'test/skin_browser_locale_test.dart',
}
DELTA |= BUILD448_DELTA
# Build 449 (12-13 October 2026), on top of the Build 448 source 36567551:
# the Apple TV mirrors the NeoStation interface outside a game (the external
# window leaves its scene; no second-engine TV menu), version 0.0.7 read from
# pubspec.yaml by the IPA gates, 3DS system files still in iCloud Drive said
# instead of "not recognized". Every created, modified or deleted input since
# that source, file by file.
BUILD449_DELTA = {
    'build-utils/validate_cheat_bulk_ipa.py',
    'build-utils/validate_release002_ipa.py',
    'build-utils/verify_delivery_reuse.py',
    'lib/l10n/external_display_locale.dart',
    'lib/l10n/libretro_locale.dart',
    'lib/l10n/neoplay_companion_locale.dart',
    'lib/screens/libretro/libretro_3ds_system_screen.dart',
    'lib/screens/settings_screen/new_settings_options/general_settings_content.dart',
    'lib/screens/settings_screen/new_settings_options/widgets/external_display_setting_rows.dart',
    'lib/services/libretro_3ds_system_data_service.dart',
    'packages/external_display/ios/Classes/NeoExternalDisplayCoordinator.h',
    'packages/external_display/ios/Classes/NeoExternalDisplayCoordinator.m',
    'packages/external_display/ios/Classes/NeoExternalDisplaySceneDelegate.m',
    'pubspec.yaml',
    'test/external_display_locale_test.dart',
    'test/external_display_test.py',
    'test/external_display_ui_test.py',
    'test/general_settings_external_display_test.dart',
    'test/general_settings_ui_refresh_rate_test.dart',
    'test/libretro_3ds_system_data_service_test.dart',
    'test/neoplay_locale_test.dart',
    'test/validate_cheat_bulk_ipa_test.py',
}
DELTA |= BUILD449_DELTA
# Build 450 (13 October 2026), on top of the Build 449 source ff2a491c: the
# shared shader kit (neo_shader_kit: portable C++ core, glslang and SPIRV-Cross
# vendored at vulkan-sdk-1.4.350.1, Metal runtime of RetroArch slang presets,
# verified downloads, catalogs of libretro/slang-shaders and of Dolphin's
# Sys/Shaders), the libretro in-game Shaders pages, the Dolphin post-processing
# page staged at the next launch, their texts in twelve languages and the
# legal notices of the two compilers. Every created, modified or deleted input
# since that source, file by file.
BUILD450_DELTA = {
    'assets/legal/SPIRV-Cross-Apache-2.0.txt',
    'assets/legal/THIRD_PARTY_NOTICES.md',
    'assets/legal/glslang-LICENSE.txt',
    'build-utils/embed_legal_bundle.py',
    'build-utils/validate_legal_bundle_ipa.py',
    'build-utils/verify_delivery_reuse.py',
    'lib/l10n/libretro_locale.dart',
    'lib/screens/settings_screen/legal_credits_dialog.dart',
    'native/dolphin_shaders/labels.json',
    'packages/dolphin_internal_bridge/ios/Classes/DOLShaderLabels.h',
    'packages/dolphin_internal_bridge/ios/Classes/DOLShaderSettings.h',
    'packages/dolphin_internal_bridge/ios/Classes/DOLShaderSettings.mm',
    'packages/dolphin_internal_bridge/ios/Classes/DOLShaderStore.h',
    'packages/dolphin_internal_bridge/ios/Classes/DolphinFramePacing.h',
    'packages/dolphin_internal_bridge/ios/Classes/DolphinFramePacing.mm',
    'packages/dolphin_internal_bridge/ios/Classes/DolphinInternalBridgePlugin.mm',
    'packages/dolphin_internal_bridge/ios/dolphin_internal_bridge.podspec',
    'packages/libretro_internal_bridge/ios/Classes/LibretroFrontendMenu.h',
    'packages/libretro_internal_bridge/ios/Classes/LibretroFrontendMenu.m',
    'packages/libretro_internal_bridge/ios/Classes/LibretroInternalBridgePlugin.m',
    'packages/libretro_internal_bridge/ios/Classes/LibretroMetalPresenter.h',
    'packages/libretro_internal_bridge/ios/Classes/LibretroMetalPresenter.m',
    'packages/libretro_internal_bridge/ios/Classes/LibretroSession.m',
    'packages/libretro_internal_bridge/ios/Classes/LibretroSlangShaders.h',
    'packages/libretro_internal_bridge/ios/Classes/LibretroSlangShaders.m',
    'packages/libretro_internal_bridge/ios/libretro_internal_bridge.podspec',
    'packages/neo_shader_kit/ios/Classes/NeoDolphinShader.mm',
    'packages/neo_shader_kit/ios/Classes/NeoShaderCatalog.mm',
    'packages/neo_shader_kit/ios/Classes/NeoShaderEngine.m',
    'packages/neo_shader_kit/ios/Classes/NeoShaderKitPlugin.m',
    'packages/neo_shader_kit/ios/Classes/NeoShaderStorage.m',
    'packages/neo_shader_kit/ios/Classes/NeoSlangRenderer.mm',
    'packages/neo_shader_kit/ios/Classes/Public/NeoDolphinShader.h',
    'packages/neo_shader_kit/ios/Classes/Public/NeoShaderCatalog.h',
    'packages/neo_shader_kit/ios/Classes/Public/NeoShaderEngine.h',
    'packages/neo_shader_kit/ios/Classes/Public/NeoShaderKitPlugin.h',
    'packages/neo_shader_kit/ios/Classes/Public/NeoShaderStorage.h',
    'packages/neo_shader_kit/ios/Classes/Public/NeoSlangRenderer.h',
    'packages/neo_shader_kit/ios/Core/NeoDolphinPostProcess.cpp',
    'packages/neo_shader_kit/ios/Core/NeoDolphinPostProcess.hpp',
    'packages/neo_shader_kit/ios/Core/NeoShaderConfig.cpp',
    'packages/neo_shader_kit/ios/Core/NeoShaderConfig.hpp',
    'packages/neo_shader_kit/ios/Core/NeoShaderFiles.cpp',
    'packages/neo_shader_kit/ios/Core/NeoShaderFiles.hpp',
    'packages/neo_shader_kit/ios/Core/NeoShaderPaths.cpp',
    'packages/neo_shader_kit/ios/Core/NeoShaderPaths.hpp',
    'packages/neo_shader_kit/ios/Core/NeoSlangCompiler.cpp',
    'packages/neo_shader_kit/ios/Core/NeoSlangCompiler.hpp',
    'packages/neo_shader_kit/ios/Core/NeoSlangPreset.cpp',
    'packages/neo_shader_kit/ios/Core/NeoSlangPreset.hpp',
    'packages/neo_shader_kit/ios/Core/NeoSlangSource.cpp',
    'packages/neo_shader_kit/ios/Core/NeoSlangSource.hpp',
    'packages/neo_shader_kit/ios/Resources/dolphin-catalog-diagnostics.json',
    'packages/neo_shader_kit/ios/Resources/dolphin-catalog.json',
    'packages/neo_shader_kit/ios/Resources/slang-catalog-diagnostics.json',
    'packages/neo_shader_kit/ios/Resources/slang-catalog.json',
    'packages/neo_shader_kit/ios/ThirdParty/SPIRV-Cross/GLSL.std.450.h',
    'packages/neo_shader_kit/ios/ThirdParty/SPIRV-Cross/LICENSE',
    'packages/neo_shader_kit/ios/ThirdParty/SPIRV-Cross/NonSemanticShaderDebugInfo100.h',
    'packages/neo_shader_kit/ios/ThirdParty/SPIRV-Cross/SOURCE.txt',
    'packages/neo_shader_kit/ios/ThirdParty/SPIRV-Cross/spirv.hpp',
    'packages/neo_shader_kit/ios/ThirdParty/SPIRV-Cross/spirv_cfg.cpp',
    'packages/neo_shader_kit/ios/ThirdParty/SPIRV-Cross/spirv_cfg.hpp',
    'packages/neo_shader_kit/ios/ThirdParty/SPIRV-Cross/spirv_common.hpp',
    'packages/neo_shader_kit/ios/ThirdParty/SPIRV-Cross/spirv_cross.cpp',
    'packages/neo_shader_kit/ios/ThirdParty/SPIRV-Cross/spirv_cross.hpp',
    'packages/neo_shader_kit/ios/ThirdParty/SPIRV-Cross/spirv_cross_containers.hpp',
    'packages/neo_shader_kit/ios/ThirdParty/SPIRV-Cross/spirv_cross_error_handling.hpp',
    'packages/neo_shader_kit/ios/ThirdParty/SPIRV-Cross/spirv_cross_parsed_ir.cpp',
    'packages/neo_shader_kit/ios/ThirdParty/SPIRV-Cross/spirv_cross_parsed_ir.hpp',
    'packages/neo_shader_kit/ios/ThirdParty/SPIRV-Cross/spirv_glsl.cpp',
    'packages/neo_shader_kit/ios/ThirdParty/SPIRV-Cross/spirv_glsl.hpp',
    'packages/neo_shader_kit/ios/ThirdParty/SPIRV-Cross/spirv_msl.cpp',
    'packages/neo_shader_kit/ios/ThirdParty/SPIRV-Cross/spirv_msl.hpp',
    'packages/neo_shader_kit/ios/ThirdParty/SPIRV-Cross/spirv_parser.cpp',
    'packages/neo_shader_kit/ios/ThirdParty/SPIRV-Cross/spirv_parser.hpp',
    'packages/neo_shader_kit/ios/ThirdParty/glslang/LICENSE.txt',
    'packages/neo_shader_kit/ios/ThirdParty/glslang/SOURCE.txt',
    'packages/neo_shader_kit/ios/ThirdParty/glslang/SPIRV/GLSL.ext.AMD.h',
    'packages/neo_shader_kit/ios/ThirdParty/glslang/SPIRV/GLSL.ext.ARM.h',
    'packages/neo_shader_kit/ios/ThirdParty/glslang/SPIRV/GLSL.ext.EXT.h',
    'packages/neo_shader_kit/ios/ThirdParty/glslang/SPIRV/GLSL.ext.KHR.h',
    'packages/neo_shader_kit/ios/ThirdParty/glslang/SPIRV/GLSL.ext.NV.h',
    'packages/neo_shader_kit/ios/ThirdParty/glslang/SPIRV/GLSL.ext.QCOM.h',
    'packages/neo_shader_kit/ios/ThirdParty/glslang/SPIRV/GLSL.std.450.h',
    'packages/neo_shader_kit/ios/ThirdParty/glslang/SPIRV/GlslangToSpv.cpp',
    'packages/neo_shader_kit/ios/ThirdParty/glslang/SPIRV/GlslangToSpv.h',
    'packages/neo_shader_kit/ios/ThirdParty/glslang/SPIRV/InReadableOrder.cpp',
    'packages/neo_shader_kit/ios/ThirdParty/glslang/SPIRV/Logger.cpp',
    'packages/neo_shader_kit/ios/ThirdParty/glslang/SPIRV/Logger.h',
    'packages/neo_shader_kit/ios/ThirdParty/glslang/SPIRV/NonSemanticDebugPrintf.h',
    'packages/neo_shader_kit/ios/ThirdParty/glslang/SPIRV/NonSemanticShaderDebugInfo.h',
    'packages/neo_shader_kit/ios/ThirdParty/glslang/SPIRV/SpvBuilder.cpp',
    'packages/neo_shader_kit/ios/ThirdParty/glslang/SPIRV/SpvBuilder.h',
    'packages/neo_shader_kit/ios/ThirdParty/glslang/SPIRV/SpvPostProcess.cpp',
    'packages/neo_shader_kit/ios/ThirdParty/glslang/SPIRV/SpvTools.cpp',
    'packages/neo_shader_kit/ios/ThirdParty/glslang/SPIRV/SpvTools.h',
    'packages/neo_shader_kit/ios/ThirdParty/glslang/SPIRV/bitutils.h',
    'packages/neo_shader_kit/ios/ThirdParty/glslang/SPIRV/disassemble.cpp',
    'packages/neo_shader_kit/ios/ThirdParty/glslang/SPIRV/disassemble.h',
    'packages/neo_shader_kit/ios/ThirdParty/glslang/SPIRV/doc.cpp',
    'packages/neo_shader_kit/ios/ThirdParty/glslang/SPIRV/doc.h',
    'packages/neo_shader_kit/ios/ThirdParty/glslang/SPIRV/hex_float.h',
    'packages/neo_shader_kit/ios/ThirdParty/glslang/SPIRV/spirv.hpp11',
    'packages/neo_shader_kit/ios/ThirdParty/glslang/SPIRV/spvIR.h',
    'packages/neo_shader_kit/ios/ThirdParty/glslang/SPIRV/spvUtil.h',
    'packages/neo_shader_kit/ios/ThirdParty/glslang/glslang/GenericCodeGen/CodeGen.cpp',
    'packages/neo_shader_kit/ios/ThirdParty/glslang/glslang/GenericCodeGen/Link.cpp',
    'packages/neo_shader_kit/ios/ThirdParty/glslang/glslang/Include/BaseTypes.h',
    'packages/neo_shader_kit/ios/ThirdParty/glslang/glslang/Include/Common.h',
    'packages/neo_shader_kit/ios/ThirdParty/glslang/glslang/Include/ConstantUnion.h',
    'packages/neo_shader_kit/ios/ThirdParty/glslang/glslang/Include/InfoSink.h',
    'packages/neo_shader_kit/ios/ThirdParty/glslang/glslang/Include/InitializeGlobals.h',
    'packages/neo_shader_kit/ios/ThirdParty/glslang/glslang/Include/PoolAlloc.h',
    'packages/neo_shader_kit/ios/ThirdParty/glslang/glslang/Include/ResourceLimits.h',
    'packages/neo_shader_kit/ios/ThirdParty/glslang/glslang/Include/ShHandle.h',
    'packages/neo_shader_kit/ios/ThirdParty/glslang/glslang/Include/SpirvIntrinsics.h',
    'packages/neo_shader_kit/ios/ThirdParty/glslang/glslang/Include/Types.h',
    'packages/neo_shader_kit/ios/ThirdParty/glslang/glslang/Include/arrays.h',
    'packages/neo_shader_kit/ios/ThirdParty/glslang/glslang/Include/defer.h',
    'packages/neo_shader_kit/ios/ThirdParty/glslang/glslang/Include/glslang_c_interface.h',
    'packages/neo_shader_kit/ios/ThirdParty/glslang/glslang/Include/glslang_c_shader_types.h',
    'packages/neo_shader_kit/ios/ThirdParty/glslang/glslang/Include/intermediate.h',
    'packages/neo_shader_kit/ios/ThirdParty/glslang/glslang/Include/visibility.h',
    'packages/neo_shader_kit/ios/ThirdParty/glslang/glslang/MachineIndependent/Constant.cpp',
    'packages/neo_shader_kit/ios/ThirdParty/glslang/glslang/MachineIndependent/InfoSink.cpp',
    'packages/neo_shader_kit/ios/ThirdParty/glslang/glslang/MachineIndependent/Initialize.cpp',
    'packages/neo_shader_kit/ios/ThirdParty/glslang/glslang/MachineIndependent/Initialize.h',
    'packages/neo_shader_kit/ios/ThirdParty/glslang/glslang/MachineIndependent/IntermTraverse.cpp',
    'packages/neo_shader_kit/ios/ThirdParty/glslang/glslang/MachineIndependent/Intermediate.cpp',
    'packages/neo_shader_kit/ios/ThirdParty/glslang/glslang/MachineIndependent/LiveTraverser.h',
    'packages/neo_shader_kit/ios/ThirdParty/glslang/glslang/MachineIndependent/ParseContextBase.cpp',
    'packages/neo_shader_kit/ios/ThirdParty/glslang/glslang/MachineIndependent/ParseHelper.cpp',
    'packages/neo_shader_kit/ios/ThirdParty/glslang/glslang/MachineIndependent/ParseHelper.h',
    'packages/neo_shader_kit/ios/ThirdParty/glslang/glslang/MachineIndependent/PoolAlloc.cpp',
    'packages/neo_shader_kit/ios/ThirdParty/glslang/glslang/MachineIndependent/RemoveTree.cpp',
    'packages/neo_shader_kit/ios/ThirdParty/glslang/glslang/MachineIndependent/RemoveTree.h',
    'packages/neo_shader_kit/ios/ThirdParty/glslang/glslang/MachineIndependent/Scan.cpp',
    'packages/neo_shader_kit/ios/ThirdParty/glslang/glslang/MachineIndependent/Scan.h',
    'packages/neo_shader_kit/ios/ThirdParty/glslang/glslang/MachineIndependent/ScanContext.h',
    'packages/neo_shader_kit/ios/ThirdParty/glslang/glslang/MachineIndependent/ShaderLang.cpp',
    'packages/neo_shader_kit/ios/ThirdParty/glslang/glslang/MachineIndependent/SpirvIntrinsics.cpp',
    'packages/neo_shader_kit/ios/ThirdParty/glslang/glslang/MachineIndependent/SymbolTable.cpp',
    'packages/neo_shader_kit/ios/ThirdParty/glslang/glslang/MachineIndependent/SymbolTable.h',
    'packages/neo_shader_kit/ios/ThirdParty/glslang/glslang/MachineIndependent/Versions.cpp',
    'packages/neo_shader_kit/ios/ThirdParty/glslang/glslang/MachineIndependent/Versions.h',
    'packages/neo_shader_kit/ios/ThirdParty/glslang/glslang/MachineIndependent/attribute.cpp',
    'packages/neo_shader_kit/ios/ThirdParty/glslang/glslang/MachineIndependent/attribute.h',
    'packages/neo_shader_kit/ios/ThirdParty/glslang/glslang/MachineIndependent/gl_types.h',
    'packages/neo_shader_kit/ios/ThirdParty/glslang/glslang/MachineIndependent/glslang_tab.cpp',
    'packages/neo_shader_kit/ios/ThirdParty/glslang/glslang/MachineIndependent/glslang_tab.cpp.h',
    'packages/neo_shader_kit/ios/ThirdParty/glslang/glslang/MachineIndependent/intermOut.cpp',
    'packages/neo_shader_kit/ios/ThirdParty/glslang/glslang/MachineIndependent/iomapper.cpp',
    'packages/neo_shader_kit/ios/ThirdParty/glslang/glslang/MachineIndependent/iomapper.h',
    'packages/neo_shader_kit/ios/ThirdParty/glslang/glslang/MachineIndependent/limits.cpp',
    'packages/neo_shader_kit/ios/ThirdParty/glslang/glslang/MachineIndependent/linkValidate.cpp',
    'packages/neo_shader_kit/ios/ThirdParty/glslang/glslang/MachineIndependent/localintermediate.h',
    'packages/neo_shader_kit/ios/ThirdParty/glslang/glslang/MachineIndependent/parseConst.cpp',
    'packages/neo_shader_kit/ios/ThirdParty/glslang/glslang/MachineIndependent/parseVersions.h',
    'packages/neo_shader_kit/ios/ThirdParty/glslang/glslang/MachineIndependent/pch.h',
    'packages/neo_shader_kit/ios/ThirdParty/glslang/glslang/MachineIndependent/preprocessor/Pp.cpp',
    'packages/neo_shader_kit/ios/ThirdParty/glslang/glslang/MachineIndependent/preprocessor/PpAtom.cpp',
    'packages/neo_shader_kit/ios/ThirdParty/glslang/glslang/MachineIndependent/preprocessor/PpContext.cpp',
    'packages/neo_shader_kit/ios/ThirdParty/glslang/glslang/MachineIndependent/preprocessor/PpContext.h',
    'packages/neo_shader_kit/ios/ThirdParty/glslang/glslang/MachineIndependent/preprocessor/PpScanner.cpp',
    'packages/neo_shader_kit/ios/ThirdParty/glslang/glslang/MachineIndependent/preprocessor/PpTokens.cpp',
    'packages/neo_shader_kit/ios/ThirdParty/glslang/glslang/MachineIndependent/preprocessor/PpTokens.h',
    'packages/neo_shader_kit/ios/ThirdParty/glslang/glslang/MachineIndependent/propagateNoContraction.cpp',
    'packages/neo_shader_kit/ios/ThirdParty/glslang/glslang/MachineIndependent/propagateNoContraction.h',
    'packages/neo_shader_kit/ios/ThirdParty/glslang/glslang/MachineIndependent/reflection.cpp',
    'packages/neo_shader_kit/ios/ThirdParty/glslang/glslang/MachineIndependent/reflection.h',
    'packages/neo_shader_kit/ios/ThirdParty/glslang/glslang/MachineIndependent/span.h',
    'packages/neo_shader_kit/ios/ThirdParty/glslang/glslang/OSDependent/Unix/ossource.cpp',
    'packages/neo_shader_kit/ios/ThirdParty/glslang/glslang/OSDependent/osinclude.h',
    'packages/neo_shader_kit/ios/ThirdParty/glslang/glslang/Public/ResourceLimits.h',
    'packages/neo_shader_kit/ios/ThirdParty/glslang/glslang/Public/ShaderLang.h',
    'packages/neo_shader_kit/ios/ThirdParty/glslang/glslang/Public/resource_limits_c.h',
    'packages/neo_shader_kit/ios/ThirdParty/glslang/glslang/ResourceLimits/ResourceLimits.cpp',
    'packages/neo_shader_kit/ios/ThirdParty/glslang/glslang/build_info.h',
    'packages/neo_shader_kit/ios/neo_shader_kit.podspec',
    'packages/neo_shader_kit/lib/neo_shader_kit.dart',
    'packages/neo_shader_kit/pubspec.yaml',
    'packages/neo_shader_kit/tools/CMakeLists.txt',
    'packages/neo_shader_kit/tools/neoshader_dolphin_validate.mm',
    'packages/neo_shader_kit/tools/neoshader_metal_validate.mm',
    'packages/neo_shader_kit/tools/neoshader_tool.cpp',
    'pubspec.yaml',
    'test/delivery_pipeline_test.py',
    'test/dolphin_shader_localizations_test.py',
    'test/dolphin_shader_store_test.mm',
    'test/dolphin_shader_store_test.py',
    'test/libretro_external_surface_test.py',
    'test/libretro_ios_syntax_test.py',
    'test/libretro_simulator/probe.m',
    'test/libretro_simulator_probe.py',
    'test/neo_shader_kit/core_test.cpp',
    'test/neo_shader_kit/slang_render_test.mm',
    'test/neo_shader_kit/storage_test.m',
    'test/neo_shader_kit_catalog_test.py',
    'test/neo_shader_kit_dolphin_test.py',
    'test/neo_shader_kit_ios_build.py',
    'test/neo_shader_kit_test.py',
}
DELTA |= BUILD450_DELTA
# Build 451 (13 October 2026), on top of the Build 450 source e7f22336: the
# 3DS system data import keeps the title contents Azahar encrypted for their
# console in its legacy form (whole file in AES-CTR, no AZCR header) once
# other contents confirm one console key, and installs them only with that
# console's otp.bin; one text in twelve languages; version 0.0.7+451. Every
# created, modified or deleted input since that source, file by file.
BUILD451_DELTA = {
    'build-utils/verify_delivery_reuse.py',
    'lib/l10n/libretro_locale.dart',
    'lib/screens/libretro/libretro_3ds_system_screen.dart',
    'lib/services/libretro_3ds_system_data_service.dart',
    'pubspec.yaml',
    'test/libretro_3ds_system_data_service_test.dart',
    'test/libretro_3ds_system_screen_test.dart',
}
DELTA |= BUILD451_DELTA
# Build 452 (13 October 2026), on top of the Build 451 source c65efd42: the
# Nintendo 3DS import menu of the library offers the 3DS BIOS and system
# files import (its page opens with the assistant started), and the
# RetroArch copy recognizes an Azahar, Citra or Lime3DS folder and points
# to that import; two texts in twelve languages; version 0.0.7+452. Every
# created, modified or deleted input since that source, file by file.
BUILD452_DELTA = {
    'build-utils/verify_delivery_reuse.py',
    'lib/l10n/libretro_locale.dart',
    'lib/screens/libretro/libretro_3ds_system_screen.dart',
    'lib/screens/libretro/libretro_bios_checker_screen.dart',
    'lib/services/libretro_internal_service.dart',
    'lib/widgets/libretro_3ds_import_route.dart',
    'lib/widgets/libretro_internal_playlist_actions.dart',
    'pubspec.yaml',
    'test/libretro_3ds_system_screen_test.dart',
    'test/libretro_bios_checker_screen_test.dart',
    'test/libretro_playlist_actions_test.dart',
}
DELTA |= BUILD452_DELTA
# Build 453: the requested official Azahar FastInterp replacement, translated
# native option menu, pinned package and behavioral/package delivery checks.
BUILD453_DELTA = {
    'test/libretro_3ds_launch_default_test.dart',
    'build-utils/libretro/cores.json',
    'build-utils/libretro/Azahar-LICENSE.txt',
    'build-utils/libretro/upgrade_azahar.py',
    '.github/workflows/libretro-cores.yml',
    'test/libretro_azahar_package_test.py',
    'lib/services/libretro_core_catalog.dart',
    'lib/l10n/libretro_locale.dart',
    'test/libretro_core_catalog_test.dart',
    'test/libretro_core_options_test.py',
    'test/libretro_host/host_test.m',
    '.github/workflows/retroarch-delivery.yml',
    '.github/workflows/libretro-checks.yml',
    '.github/workflows/libretro-simulator.yml',
    'build-utils/validate_libretro_ipa.py',
    'pubspec.yaml',
    'NOTICE.md',
    'assets/legal/THIRD_PARTY_NOTICES.md',
    'build-utils/verify_delivery_reuse.py',
}
DELTA |= BUILD453_DELTA
# Build 454 (13 October 2026), on top of the Build 453 source 81efc210: the
# libretro bridge answers isSessionActive with @YES or @NO (an int32 before,
# which Dart could not cast to bool: the 3DS system data import refused to
# run), Dart takes only a boolean for a session state, a ZIP inside the
# chosen folder or ZIP is listed apart instead of refused as an unsupported
# archive (one text in twelve languages), the channel codec test in the iOS
# Simulator; version 0.0.7+454. Every created, modified or deleted input
# since that source, file by file.
BUILD454_DELTA = {
    '.github/workflows/libretro-checks.yml',
    '.github/workflows/retroarch-delivery.yml',
    'build-utils/verify_delivery_reuse.py',
    'lib/l10n/libretro_locale.dart',
    'lib/screens/libretro/libretro_3ds_system_screen.dart',
    'lib/services/embedded_ios_session_status.dart',
    'lib/services/libretro_3ds_system_data_service.dart',
    'packages/libretro_internal_bridge/ios/Classes/LibretroInternalBridgePlugin.m',
    'packages/libretro_internal_bridge/lib/libretro_internal_bridge.dart',
    'pubspec.yaml',
    'test/external_display_host_plist_test.py',
    'test/libretro_3ds_system_data_service_test.dart',
    'test/libretro_3ds_system_screen_test.dart',
    'test/libretro_channel_codec/main.m',
    'test/libretro_channel_codec_test.py',
    'test/libretro_session_envelopes.dart',
    'test/libretro_session_probe_codec_test.dart',
}
DELTA |= BUILD454_DELTA
# Build 455 (13 October 2026), on top of the Build 454 source 6dcdfd1a: the
# internal resolution of the embedded libretro cores (docs/libretro-
# resolution.md) - LibretroResolution recognizes a core's resolution option
# (profiles of known names sent by Dart, else its name or description),
# values kept for one game (Config/Games/<core>.json), native by default,
# the in-game "Resolution and picture" page and the console settings page,
# 31 texts in twelve languages, the host, simulator and binary checks;
# version 0.0.7+455. Every created, modified or deleted input since that
# source, file by file.
BUILD455_DELTA = {
    '.github/workflows/libretro-checks.yml',
    '.github/workflows/retroarch-delivery.yml',
    'build-utils/verify_delivery_reuse.py',
    'lib/l10n/libretro_locale.dart',
    'lib/screens/libretro/libretro_consoles_screen.dart',
    'lib/screens/libretro/libretro_resolution_screen.dart',
    'lib/services/libretro_core_catalog.dart',
    'lib/services/libretro_internal_service.dart',
    'lib/services/libretro_resolution.dart',
    'lib/services/libretro_resolution_service.dart',
    'lib/widgets/libretro_engine_panel.dart',
    'packages/libretro_internal_bridge/ios/Classes/LibretroCoreHost.h',
    'packages/libretro_internal_bridge/ios/Classes/LibretroCoreHost.m',
    'packages/libretro_internal_bridge/ios/Classes/LibretroCoreOptions.h',
    'packages/libretro_internal_bridge/ios/Classes/LibretroCoreOptions.m',
    'packages/libretro_internal_bridge/ios/Classes/LibretroFrontendMenu.h',
    'packages/libretro_internal_bridge/ios/Classes/LibretroFrontendMenu.m',
    'packages/libretro_internal_bridge/ios/Classes/LibretroInternalBridgePlugin.m',
    'packages/libretro_internal_bridge/ios/Classes/LibretroResolution.h',
    'packages/libretro_internal_bridge/ios/Classes/LibretroResolution.m',
    'packages/libretro_internal_bridge/ios/Classes/LibretroSession.h',
    'packages/libretro_internal_bridge/ios/Classes/LibretroSession.m',
    'pubspec.yaml',
    'test/fixtures/libretro_resolution/native_rules.json',
    'test/fixtures/libretro_resolution/value_cases.json',
    'test/libretro_3ds_launch_default_test.dart',
    'test/libretro_consoles_tab_test.dart',
    'test/libretro_core_options_test.py',
    'test/libretro_engine_settings_test.dart',
    'test/libretro_host/host_test.m',
    'test/libretro_host/test_core.c',
    'test/libretro_host_test.py',
    'test/libretro_resolution_screen_test.dart',
    'test/libretro_resolution_test.dart',
    'test/libretro_simulator/probe.m',
    'test/libretro_simulator_probe.py',
}
DELTA |= BUILD455_DELTA
# The Build 456 delivery closes omissions in the historical inventory without
# granting those paths an open-ended exception. The 39 earlier legal/UI inputs
# are exactly the shader investigation's starting tree; the six shader inputs
# are exactly the completed shader candidate. Changed bytes, modes, deletions
# and symlinks require a new reviewed reference before another delivery.
DELIVERY456_HISTORICAL_REFERENCE = '29b24945b2e7041f08e02d7d70e8c90ffe8a1c24'
DELIVERY456_HISTORICAL_INPUTS = {
    'assets/legal/libretro/LIBRETRO_CORES.md',
    'assets/legal/libretro/MoltenVK-LICENSE',
    'assets/legal/libretro/MoltenVK-README.md',
    'assets/legal/libretro/Vulkan-Headers-LICENSE.md',
    'assets/legal/libretro/azahar-LICENSE.txt',
    'assets/legal/libretro/beetle_psx-COPYING',
    'assets/legal/libretro/desmume-license.txt',
    'assets/legal/libretro/fbneo-LICENSE.md',
    'assets/legal/libretro/fbneo-src-license.txt',
    'assets/legal/libretro/gambatte-COPYING',
    'assets/legal/libretro/genesis_plus_gx-LICENSE.txt',
    'assets/legal/libretro/genesis_plus_gx_wide-LICENSE.txt',
    'assets/legal/libretro/libretro-api-MIT.txt',
    'assets/legal/libretro/license-sources.json',
    'assets/legal/libretro/mgba-LICENSE',
    'assets/legal/libretro/mupen64plus_next-LICENSE',
    'assets/legal/libretro/nestopia-COPYING',
    'assets/legal/libretro/nestopia-README',
    'assets/legal/libretro/picodrive-AUTHORS',
    'assets/legal/libretro/picodrive-COPYING',
    'assets/legal/libretro/ppsspp-LICENSE.TXT',
    'assets/legal/libretro/rcheevos-LICENSE.txt',
    'assets/legal/libretro/snes9x-LICENSE',
    'lib/l10n/armsx2_ui_locale.dart',
    'lib/l10n/legal_credits_locale.dart',
    'lib/l10n/secondary_ui_locale.dart',
    'lib/screens/scraper_screen/new_scraper_options_screen.dart',
    'lib/services/dolphin_system_files.dart',
    'lib/services/dusklight_game_identity.dart',
    'lib/services/rpcs3_game_deletion.dart',
    'lib/widgets/rpcs3_multi_delete_dialog.dart',
    'packages/armsx2_internal_bridge/lib/armsx2_internal_bridge.dart',
    'packages/rpcs3_internal_bridge/lib/rpcs3_internal_bridge.dart',
    'test/armsx2_in_game_localization_test.dart',
    'test/ios_gamepad_navigation_test.dart',
    'test/legal_bundle_preflight_test.py',
    'test/legal_credits_dialog_test.dart',
    'test/neoswap_shader_storage_test.dart',
    'test/retro_achievements_layout_test.dart',
}
DELIVERY456_SHADER_REFERENCE = '5d90ea223d0dc1894b0763f3ea77a70be844b2ba'
DELIVERY456_SHADER_INPUTS = {
    'packages/dolphin_internal_bridge/ios/Classes/DolphinSessionMenu.h',
    'packages/libretro_internal_bridge/ios/Classes/LibretroShaderRecovery.h',
    'packages/libretro_internal_bridge/ios/Classes/LibretroShaderRecovery.m',
    'test/armsx2_embedded_library_contract_test.dart',
    'test/libretro_host/frontend/shader_recovery_test.m',
    'test/neo_shader_kit/libretro_presenter_test.mm',
}
DELIVERY456_PINNED_INPUTS = {
    **dict.fromkeys(DELIVERY456_HISTORICAL_INPUTS, DELIVERY456_HISTORICAL_REFERENCE),
    **dict.fromkeys(DELIVERY456_SHADER_INPUTS, DELIVERY456_SHADER_REFERENCE),
}
DELTA |= set(DELIVERY456_PINNED_INPUTS)
DELIVERY456_RECIPIENT_PATH = 'build-utils/delivery-456-recipient.pem'
DELIVERY456_RECIPIENT_SHA256 = '49764c811fc0dd73213b5c93835d24766cbeda98e4989885ae9733f60e43af12'
DELTA.add(DELIVERY456_RECIPIENT_PATH)
# Build 457: the kit's link-time public API boundary and the reproduction
# with Dolphin's unmodified pinned compiler. Existing shader recipes and
# podspec are already inventoried; no unrelated runtime exemption is added.
DELTA |= {
    'packages/neo_shader_kit/ios/neo_shader_kit.exports',
    'test/neo_shader_compiler_coexistence.py',
    'build-utils/validate_shader_compiler_ipa.py',
}
# Lot 1 of the Consoles tab (docs/libretro-consoles-lot1.md): sixteen cores
# added to the pinned LibretroCores package (df0124b8, run 38627332377) and
# the 21 hidden consoles they run. The legal inputs, existing and new, are
# pinned to the reviewed lot 1 commit: any later byte, mode or deletion needs
# a new reviewed reference.
LIBRETRO_LOT1_REFERENCE = 'ed61c9e4659c45e66de969230d7d6e560ec7574d'
LIBRETRO_LOT1_LEGAL_INPUTS = {
    'assets/legal/libretro/LIBRETRO_CORES.md',
    'assets/legal/libretro/license-sources.json',
    'assets/legal/libretro/a5200-License.txt',
    'assets/legal/libretro/ardens-LICENSE.txt',
    'assets/legal/libretro/beetle_ngp-COPYING',
    'assets/legal/libretro/beetle_pce_fast-COPYING',
    'assets/legal/libretro/beetle_vb-COPYING',
    'assets/legal/libretro/beetle_wswan-COPYING',
    'assets/legal/libretro/gearcoleco-LICENSE',
    'assets/legal/libretro/gw-LICENSE',
    'assets/legal/libretro/handy-license.txt',
    'assets/legal/libretro/pokemini-LICENSE',
    'assets/legal/libretro/potator-LICENSE',
    'assets/legal/libretro/prosystem-License.txt',
    'assets/legal/libretro/sameduck-LICENSE',
    'assets/legal/libretro/stella-Copyright.txt',
    'assets/legal/libretro/stella-License.txt',
    'assets/legal/libretro/uzem-MIT-notice.h',
    'assets/legal/libretro/wasm4-LICENSE.txt',
    'test/legal_credits_dialog_test.dart',
}
DELIVERY456_PINNED_INPUTS.update(dict.fromkeys(LIBRETRO_LOT1_LEGAL_INPUTS, LIBRETRO_LOT1_REFERENCE))
LIBRETRO_LOT1_DELTA = LIBRETRO_LOT1_LEGAL_INPUTS | {
    'assets/data/libretro_bios_requirements.json',
    'build-utils/libretro/add_cores.py',
    'build-utils/libretro/build_cores.py',
    'build-utils/libretro/cores.json',
    'lib/l10n/libretro_locale.dart',
    'lib/services/console_catalog.dart',
    'lib/services/libretro_core_catalog.dart',
    'lib/services/libretro_internal_service.dart',
    'lib/services/neostation_rom_library.dart',
    'packages/libretro_internal_bridge/ios/Classes/LibretroDefaultSkins.m',
    'packages/libretro_internal_bridge/ios/Classes/LibretroInputMap.h',
    'packages/libretro_internal_bridge/ios/Classes/LibretroInputMap.m',
    'packages/libretro_internal_bridge/ios/Classes/LibretroInternalBridgePlugin.m',
    'packages/libretro_internal_bridge/ios/Classes/LibretroSkin.h',
    'packages/libretro_internal_bridge/ios/Classes/LibretroSkin.m',
    'packages/libretro_internal_bridge/ios/Classes/LibretroSkinCompatibility.h',
    'packages/libretro_internal_bridge/ios/Classes/LibretroSkinCompatibility.m',
    'test/console_manager_test.dart',
    'test/fixtures/libretro_bios/core_info_5a74858a.json',
    'test/libretro_add_cores_test.py',
    'test/libretro_azahar_package_test.py',
    'test/libretro_bios_catalog_test.dart',
    'test/libretro_bios_check_service_test.dart',
    'test/libretro_bios_checker_screen_test.dart',
    'test/libretro_consoles_tab_test.dart',
    'test/libretro_core_catalog_test.dart',
    'test/libretro_core_options_test.py',
    'test/libretro_host/frontend/chrome_layout_test.m',
    'test/libretro_host/frontend/default_skins_test.m',
    'test/libretro_host/frontend/input_map_test.m',
    'test/libretro_host/frontend/skin_test.m',
    'test/libretro_simulator_probe.py',
}
DELTA |= LIBRETRO_LOT1_DELTA
# Lot 2 (docs/libretro-consoles-lot2.md): FreeChaF, FreeIntv, O2EM and
# Beetle PC-FX (package fdeaef56, run 38638115521) for four more consoles of
# the Consoles tab. The legal inputs it changes or adds are pinned to the
# reviewed lot 2 commit, which replaces the lot 1 pin of the three shared
# ones.
LIBRETRO_LOT2_REFERENCE = '6e88e7844c8004838dc264c2839c8bd4c8c8e8e9'
LIBRETRO_LOT2_LEGAL_INPUTS = {
    'assets/legal/libretro/LIBRETRO_CORES.md',
    'assets/legal/libretro/license-sources.json',
    'assets/legal/libretro/beetle_pcfx-COPYING',
    'assets/legal/libretro/freechaf-LICENSE',
    'assets/legal/libretro/freeintv-LICENSE',
    'assets/legal/libretro/o2em-COPYING',
    'test/legal_credits_dialog_test.dart',
}
DELIVERY456_PINNED_INPUTS.update(dict.fromkeys(LIBRETRO_LOT2_LEGAL_INPUTS, LIBRETRO_LOT2_REFERENCE))
LIBRETRO_LOT2_DELTA = LIBRETRO_LOT2_LEGAL_INPUTS | {
    'assets/data/libretro_bios_requirements.json',
    'build-utils/libretro/cores.json',
    'lib/l10n/libretro_locale.dart',
    'lib/services/console_catalog.dart',
    'lib/services/game/game_launch_service.dart',
    'lib/services/libretro_core_catalog.dart',
    'lib/services/libretro_internal_service.dart',
    'packages/libretro_internal_bridge/ios/Classes/LibretroDefaultSkins.m',
    'packages/libretro_internal_bridge/ios/Classes/LibretroInputMap.h',
    'packages/libretro_internal_bridge/ios/Classes/LibretroInputMap.m',
    'packages/libretro_internal_bridge/ios/Classes/LibretroSkin.h',
    'packages/libretro_internal_bridge/ios/Classes/LibretroSkin.m',
    'packages/libretro_internal_bridge/ios/Classes/LibretroSkinCompatibility.h',
    'packages/libretro_internal_bridge/ios/Classes/LibretroSkinCompatibility.m',
    'test/console_manager_test.dart',
    'test/fixtures/libretro_bios/core_info_5a74858a.json',
    'test/libretro_bios_catalog_test.dart',
    'test/libretro_bios_check_service_test.dart',
    'test/libretro_bios_checker_screen_test.dart',
    'test/libretro_bios_launch_test.dart',
    'test/libretro_core_catalog_test.dart',
    'test/libretro_core_options_test.py',
    'test/libretro_host/frontend/chrome_layout_test.m',
    'test/libretro_host/frontend/default_skins_test.m',
    'test/libretro_host/frontend/input_map_test.m',
    'test/libretro_host/frontend/skin_test.m',
    'test/libretro_locale_test.dart',
    'test/libretro_route_contract_test.py',
    'test/libretro_simulator_probe.py',
}
DELTA |= LIBRETRO_LOT2_DELTA
# Maintainer rule of 14 October 2026, never ship a BIOS: the notices that
# state it and the MIT notice of the Arduboy bootloaders Ardens embeds,
# pinned to the reviewed commit.
LIBRETRO_NO_BIOS_REFERENCE = '3b0a5b1837c8c7ff159d51759abc2f6a041cd0c0'
LIBRETRO_NO_BIOS_LEGAL_INPUTS = {
    'assets/legal/libretro/LIBRETRO_CORES.md',
    'assets/legal/libretro/license-sources.json',
    'assets/legal/libretro/ardens-cathy3k-LICENSE',
}
DELIVERY456_PINNED_INPUTS.update(dict.fromkeys(LIBRETRO_NO_BIOS_LEGAL_INPUTS, LIBRETRO_NO_BIOS_REFERENCE))
DELTA |= LIBRETRO_NO_BIOS_LEGAL_INPUTS
# Build 460: pressable skin artwork and touch lifecycle, validated at this
# exact source by libretro-checks run 38661616452. New crop sources and all
# changed inputs are pinned, rather than admitted as open-ended exceptions.
LIBRETRO_SKIN_PRESS_REFERENCE = '6a7ddb54568e9048a7b66682c6fcdd9889f9f9ef'
LIBRETRO_SKIN_PRESS_RUN = 38887228314
LIBRETRO_SKIN_PRESS_INPUTS = {
    '.github/workflows/libretro-checks.yml',
    'lib/l10n/libretro_locale.dart',
    'lib/services/libretro_skin_service.dart',
    'packages/libretro_internal_bridge/ios/Classes/LibretroGameViewController.m',
    'packages/libretro_internal_bridge/ios/Classes/LibretroSkin.h',
    'packages/libretro_internal_bridge/ios/Classes/LibretroSkin.m',
    'packages/libretro_internal_bridge/ios/Classes/LibretroSkinButtonCrop.h',
    'packages/libretro_internal_bridge/ios/Classes/LibretroSkinButtonCrop.m',
    'packages/libretro_internal_bridge/ios/Classes/LibretroSkinRenderer.h',
    'packages/libretro_internal_bridge/ios/Classes/LibretroSkinRenderer.m',
    'packages/libretro_internal_bridge/ios/Classes/LibretroTouchOverlay.h',
    'packages/libretro_internal_bridge/ios/Classes/LibretroTouchOverlay.m',
    'packages/libretro_internal_bridge/ios/Classes/LibretroTouchTracker.h',
    'packages/libretro_internal_bridge/ios/Classes/LibretroTouchTracker.m',
    'test/libretro_frontend_test.py',
    'test/libretro_host/frontend/skin_button_crop_test.m',
    'test/libretro_host/frontend/skin_test.m',
    'test/libretro_host/frontend/touch_tracker_test.m',
    'test/libretro_simulator/probe.m',
    'test/libretro_simulator/skin_press_probe.h',
    'test/libretro_simulator_probe.py',
    'test/libretro_skin_press_probe.py',
    'test/libretro_skin_service_test.dart',
}
DELIVERY456_PINNED_INPUTS.update(dict.fromkeys(LIBRETRO_SKIN_PRESS_INPUTS, LIBRETRO_SKIN_PRESS_REFERENCE))
DELTA |= LIBRETRO_SKIN_PRESS_INPUTS
DELIVERY460_RECIPIENT_PATH = 'build-utils/delivery-460-recipient.pem'
DELIVERY456_PINNED_INPUTS[DELIVERY460_RECIPIENT_PATH] = '24dca74cc09be795da67494380b7fb6a8cef0960'
DELTA.add(DELIVERY460_RECIPIENT_PATH)
# Build 461: directional deformation, asymmetric/overlapping artwork, Atomic
# Pink regression inputs, and the exact successful iPhone-phase reuse gate.
# These are closed byte/mode pins. The portable tests still run in delivery;
# the earlier failed portable step is never treated as successful evidence.
LIBRETRO_DIRECTIONAL_REFERENCE = 'a5aaac2e13a0d44564a847613fb89cc990674698'
LIBRETRO_DIRECTIONAL_INPUTS = {
    '.github/workflows/libretro-skin-checks.yml',
    'packages/libretro_internal_bridge/ios/Classes/LibretroSkin.h',
    'packages/libretro_internal_bridge/ios/Classes/LibretroSkin.m',
    'packages/libretro_internal_bridge/ios/Classes/LibretroSkinPressure.h',
    'packages/libretro_internal_bridge/ios/Classes/LibretroSkinPressure.m',
    'packages/libretro_internal_bridge/ios/Classes/LibretroSkinRenderer.m',
    'test/libretro_frontend_test.py',
    'test/libretro_host/frontend/skin_pressure_test.m',
    'test/libretro_host/frontend/skin_test.m',
    'test/libretro_simulator/probe.m',
    'test/libretro_simulator/skin_press_probe.h',
    'test/libretro_skin_press_probe.py',
    'build-utils/reuse_skin_frontend.py',
    'test/skin_frontend_reuse_test.py',
    'test/external_display_host_plist_test.py',
    'build-utils/delivery-461-recipient.pem',
}
DELIVERY456_PINNED_INPUTS.update(dict.fromkeys(LIBRETRO_DIRECTIONAL_INPUTS, LIBRETRO_DIRECTIONAL_REFERENCE))
DELTA |= LIBRETRO_DIRECTIONAL_INPUTS
# Build 462: reviewed pressure profiles, intensity preference and regression
# fixtures. Bind all changed source bytes to the actual tested candidate.
LIBRETRO_PRESSURE462_REFERENCE = '06143ac80815c5f125b20e18c47c2d6291eeb117'
LIBRETRO_PRESSURE462_INPUTS = {
    'lib/l10n/libretro_locale.dart',
    'packages/libretro_internal_bridge/ios/Classes/LibretroFrontendMenu.m',
    'packages/libretro_internal_bridge/ios/Classes/LibretroFrontendStore.h',
    'packages/libretro_internal_bridge/ios/Classes/LibretroFrontendStore.m',
    'packages/libretro_internal_bridge/ios/Classes/LibretroInternalBridgePlugin.m',
    'packages/libretro_internal_bridge/ios/Classes/LibretroSession.m',
    'packages/libretro_internal_bridge/ios/Classes/LibretroSkinPressure.h',
    'packages/libretro_internal_bridge/ios/Classes/LibretroSkinPressure.m',
    'packages/libretro_internal_bridge/ios/Classes/LibretroSkinRenderer.h',
    'packages/libretro_internal_bridge/ios/Classes/LibretroSkinRenderer.m',
    'test/libretro_host/frontend/frontend_store_test.m',
    'test/libretro_host/frontend/skin_pressure_test.m',
    'test/libretro_locale_test.dart',
    'test/libretro_simulator/skin_press_probe.h',
    'test/libretro_skin_press_probe.py',
}
DELIVERY456_PINNED_INPUTS.update(dict.fromkeys(LIBRETRO_PRESSURE462_INPUTS, LIBRETRO_PRESSURE462_REFERENCE))
DELTA |= LIBRETRO_PRESSURE462_INPUTS
DELIVERY456_PINNED_INPUTS['build-utils/reuse_skin_frontend.py'] = 'ca856f875ab937e515bc43a107496bb4a1db3f2a'
# Build 463: reviewed overlay reconstruction, bounded skin loading and opt-in
# multi-source cheats. Native sources and fixtures are pinned, not excluded.
LIBRETRO_CATALOG463_REFERENCE = 'c93f493aa17caafce820ce126e37ec090cb4e8a5'
LIBRETRO_CATALOG463_INPUTS = {
    ".github/workflows/libretro-skin-checks.yml",
    "packages/libretro_internal_bridge/ios/Classes/LibretroSessionMenu.m",
    '.github/workflows/libretro-cheats-checks.yml',
    'lib/l10n/libretro_locale.dart',
    'lib/screens/libretro/libretro_skin_catalog_screen.dart',
    'lib/services/libretro_overlay_converter.dart',
    'lib/services/libretro_skin_catalogs.dart',
    'lib/services/libretro_skin_service.dart',
    'packages/libretro_internal_bridge/ios/Classes/LibretroCheatCatalog.h',
    'packages/libretro_internal_bridge/ios/Classes/LibretroCheatCatalog.m',
    'packages/libretro_internal_bridge/ios/Classes/LibretroCheatMenu.h',
    'packages/libretro_internal_bridge/ios/Classes/LibretroCheatMenu.m',
    'packages/libretro_internal_bridge/ios/Classes/LibretroCheats.h',
    'packages/libretro_internal_bridge/ios/Classes/LibretroCheats.m',
    'packages/libretro_internal_bridge/ios/Classes/LibretroCoreHost.m',
    'packages/libretro_internal_bridge/ios/Classes/LibretroInternalBridgePlugin.m',
    'packages/libretro_internal_bridge/ios/Classes/LibretroSession.m',
    'packages/libretro_internal_bridge/ios/Classes/LibretroSkin.m',
    'packages/libretro_internal_bridge/ios/Classes/LibretroSkinRenderer.h',
    'packages/libretro_internal_bridge/ios/Classes/LibretroSkinRenderer.m',
    'packages/libretro_internal_bridge/ios/libretro_internal_bridge.podspec',
    'packages/libretro_internal_bridge/lib/libretro_internal_bridge.dart',
    'test/fixtures/libretro_cheats/README.md',
    'test/fixtures/libretro_cheats/libretro-LICENSE',
    'test/fixtures/libretro_cheats/openemu-LICENSE',
    'test/fixtures/libretro_cheats/openemu-original.xml',
    'test/fixtures/libretro_overlays/COPYING',
    'test/fixtures/libretro_overlays/README.md',
    'test/fixtures/libretro_overlays/psx.cfg',
    'test/fixtures/libretro_overlays/rgpad_modern.cfg',
    'test/libretro_cheat_probe.py',
    'test/libretro_frontend_test.py',
    'test/libretro_host/frontend/cheat_catalog_live_probe.m',
    'test/libretro_host/frontend/cheat_catalog_test.m',
    'test/libretro_host/frontend/cheats_test.m',
    'test/libretro_host/host_test.m',
    'test/libretro_ios_syntax_test.py',
    'test/libretro_overlay_fixture_test.dart',
    'test/libretro_simulator/cheat_menu_probe.h',
    'test/libretro_simulator/cheat_probe.h',
    'test/libretro_simulator/overlay_preview_probe.h',
    'test/libretro_simulator/probe.m',
    'test/libretro_simulator/skin_failure_probe.h',
    'test/libretro_simulator/skin_press_probe.h',
    'test/libretro_simulator_probe.py',
    'test/libretro_skin_catalogs_test.dart',
}
DELIVERY456_PINNED_INPUTS.update(dict.fromkeys(LIBRETRO_CATALOG463_INPUTS, LIBRETRO_CATALOG463_REFERENCE))
DELTA |= LIBRETRO_CATALOG463_INPUTS
# Build 464 keeps the 463 features and repairs layout-scoped activation.
# New and changed source/test inputs are pinned, never excluded from evidence.
SKIN_LOADING_REFERENCE = 'ed45df2e97cefb63b455037f72390455a3309692'
SKIN_LOADING_RUN = 39072237930
SKIN_LOADING_INPUTS = {
    '.github/workflows/libretro-skin-loading-checks.yml',
    '.github/workflows/libretro-skin-checks.yml',
    '.github/workflows/libretro-cheats-checks.yml',
    'packages/libretro_internal_bridge/ios/Classes/LibretroSession.m',
    'packages/libretro_internal_bridge/ios/Classes/LibretroSkin.h',
    'packages/libretro_internal_bridge/ios/Classes/LibretroSkin.m',
    'packages/libretro_internal_bridge/ios/Classes/LibretroSkinRenderer.h',
    'packages/libretro_internal_bridge/ios/Classes/LibretroSkinRenderer.m',
    'test/libretro_host/frontend/skin_test.m',
    'test/libretro_simulator/overlay_preview_probe.h',
    'test/libretro_simulator/probe.m',
    'test/libretro_simulator/skin_failure_probe.h',
    'test/libretro_simulator/skin_loading_probe.h',
    'test/libretro_simulator/skin_resource_legacy.m',
    'test/libretro_simulator_probe.py',
    'test/libretro_skin_loading_probe.py',
    'test/libretro_skin_press_probe.py',
    'test/libretro_simulator/skin_press_probe.h',
}
DELIVERY456_PINNED_INPUTS.update(dict.fromkeys(SKIN_LOADING_INPUTS, SKIN_LOADING_REFERENCE))
DELTA |= SKIN_LOADING_INPUTS

# Build 465: catalogue-only product corrections and original-source audit.
CATALOG_AUDIT_REFERENCE = '2e877872a919c119fb3d10f47699218cc1a34e96'
CATALOG_AUDIT_RUN = 39071418361
CATALOG_AUDIT_INPUTS = {
    '.github/workflows/libretro-catalog-checks.yml',
    'assets/data/libretro_skin_overlays.json',
    'lib/screens/libretro/libretro_skin_catalog_screen.dart',
    'lib/services/libretro_skin_catalog_service.dart',
    'lib/services/libretro_skin_catalogs.dart',
    'test/fixtures/libretro_overlays/pocketarch/LICENSE',
    'test/fixtures/libretro_overlays/pocketarch/README.md',
    'test/fixtures/libretro_overlays/pocketarch/manifest.json',
    'test/libretro_catalog_probe.py',
    'test/libretro_simulator/overlay_preview_probe.h',
    'test/libretro_simulator_probe.py',
    'test/libretro_skin_catalog_audit_test.dart',
    'test/libretro_skin_catalogs_test.dart',
    'test/libretro_skin_manager_test.dart',
}
DELIVERY456_PINNED_INPUTS.update(dict.fromkeys(CATALOG_AUDIT_INPUTS, CATALOG_AUDIT_REFERENCE))
DELTA |= CATALOG_AUDIT_INPUTS
# Build 466: exact reviewed automatic-cheat product, data, test and recipe inputs.
# New bytes are pinned, never hidden from the reuse boundary. Successful native,
# UIKit, loading, catalogue and cheat jobs are checked independently below.
AUTOMATIC_CHEATS466_REFERENCE = 'cc594d40a751be462dad0e3ef437c4ade5e2fc80'
AUTOMATIC_CHEATS466_INPUTS = {
    '.gitattributes',
    '.github/workflows/libretro-cheats-checks.yml',
    '.github/workflows/retroarch-delivery.yml',
    'build-utils/validate_cheat_bootstrap_ipa.py',
    'lib/l10n/libretro_locale.dart',
    'packages/libretro_internal_bridge/ios/Classes/LibretroCheatCatalog.h',
    'packages/libretro_internal_bridge/ios/Classes/LibretroCheatCatalog.m',
    'packages/libretro_internal_bridge/ios/Classes/LibretroCheatMenu.h',
    'packages/libretro_internal_bridge/ios/Classes/LibretroCheatMenu.m',
    'packages/libretro_internal_bridge/ios/Classes/LibretroCheats.h',
    'packages/libretro_internal_bridge/ios/Classes/LibretroCheats.m',
    'packages/libretro_internal_bridge/ios/Classes/LibretroInternalBridgePlugin.m',
    'packages/libretro_internal_bridge/ios/Classes/LibretroSession.m',
    'packages/libretro_internal_bridge/ios/Resources/Cheats/NOTICE.txt',
    'packages/libretro_internal_bridge/ios/Resources/Cheats/libretro-2600.json',
    'packages/libretro_internal_bridge/ios/Resources/Cheats/libretro-32x.json',
    'packages/libretro_internal_bridge/ios/Resources/Cheats/libretro-5200.json',
    'packages/libretro_internal_bridge/ios/Resources/Cheats/libretro-7800.json',
    'packages/libretro_internal_bridge/ios/Resources/Cheats/libretro-LICENSE',
    'packages/libretro_internal_bridge/ios/Resources/Cheats/libretro-arcade.json',
    'packages/libretro_internal_bridge/ios/Resources/Cheats/libretro-cv.json',
    'packages/libretro_internal_bridge/ios/Resources/Cheats/libretro-gb.json',
    'packages/libretro_internal_bridge/ios/Resources/Cheats/libretro-gba.json',
    'packages/libretro_internal_bridge/ios/Resources/Cheats/libretro-gbc.json',
    'packages/libretro_internal_bridge/ios/Resources/Cheats/libretro-gg.json',
    'packages/libretro_internal_bridge/ios/Resources/Cheats/libretro-intv.json',
    'packages/libretro_internal_bridge/ios/Resources/Cheats/libretro-lynx.json',
    'packages/libretro_internal_bridge/ios/Resources/Cheats/libretro-mcd.json',
    'packages/libretro_internal_bridge/ios/Resources/Cheats/libretro-md.json',
    'packages/libretro_internal_bridge/ios/Resources/Cheats/libretro-n64.json',
    'packages/libretro_internal_bridge/ios/Resources/Cheats/libretro-nds.json',
    'packages/libretro_internal_bridge/ios/Resources/Cheats/libretro-nes.json',
    'packages/libretro_internal_bridge/ios/Resources/Cheats/libretro-ngp.json',
    'packages/libretro_internal_bridge/ios/Resources/Cheats/libretro-ngpc.json',
    'packages/libretro_internal_bridge/ios/Resources/Cheats/libretro-pccd.json',
    'packages/libretro_internal_bridge/ios/Resources/Cheats/libretro-pce.json',
    'packages/libretro_internal_bridge/ios/Resources/Cheats/libretro-pcfx.json',
    'packages/libretro_internal_bridge/ios/Resources/Cheats/libretro-psp.json',
    'packages/libretro_internal_bridge/ios/Resources/Cheats/libretro-psx.json',
    'packages/libretro_internal_bridge/ios/Resources/Cheats/libretro-sg1000.json',
    'packages/libretro_internal_bridge/ios/Resources/Cheats/libretro-sms.json',
    'packages/libretro_internal_bridge/ios/Resources/Cheats/libretro-snes.json',
    'packages/libretro_internal_bridge/ios/Resources/Cheats/libretro-vb.json',
    'packages/libretro_internal_bridge/ios/Resources/Cheats/libretro-ws.json',
    'packages/libretro_internal_bridge/ios/Resources/Cheats/libretro-wsc.json',
    'packages/libretro_internal_bridge/ios/Resources/Cheats/manifest.json',
    'packages/libretro_internal_bridge/ios/Resources/Cheats/openemu-LICENSE',
    'packages/libretro_internal_bridge/ios/Resources/Cheats/openemu.xml',
    'packages/libretro_internal_bridge/ios/libretro_internal_bridge.podspec',
    'test/cheat_bootstrap_ipa_test.py',
    'test/cheat_bootstrap_test.py',
    'test/libretro_cheat_probe.py',
    'test/libretro_frontend_test.py',
    'test/libretro_host/frontend/cheat_automatic_test.m',
    'test/libretro_host/frontend/cheats_test.m',
    'test/libretro_simulator/cheat_automatic_probe.h',
    'test/libretro_simulator/cheat_probe.h',
    'test/libretro_simulator/probe.m',
    'test/libretro_simulator_probe.py',
    'tools/cheats/NOTICE.txt',
    'tools/cheats/build_bootstrap.py',
}
DELIVERY456_PINNED_INPUTS.update(dict.fromkeys(AUTOMATIC_CHEATS466_INPUTS, AUTOMATIC_CHEATS466_REFERENCE))
DELTA |= AUTOMATIC_CHEATS466_INPUTS

# Build 467: pin the reviewed PS1 cheat flow AND the subsequent native
# readable-cell layout to the same immutable product/test snapshot. The
# delivery-only verification edit does not modify that snapshot.
PS1_CHEATS467_REFERENCE = '8e94231e0ea0879dead658c6c66b0d46f13ab2ed'
PS1_CHEATS467_INPUTS = AUTOMATIC_CHEATS466_INPUTS | {
    'packages/libretro_internal_bridge/ios/Classes/LibretroSessionMenu.h',
    'packages/libretro_internal_bridge/ios/Classes/LibretroSessionMenu.m',
    'test/fixtures/libretro_cheats/README.md',
    'test/fixtures/libretro_cheats/ff7-usa-original.cht',
    'test/fixtures/libretro_cheats/digimon-world-original.cht',
    'test/libretro_host/frontend/cheat_catalog_live_probe.m',
    'test/libretro_simulator/cheat_menu_probe.h',
}
DELIVERY456_PINNED_INPUTS.update(dict.fromkeys(PS1_CHEATS467_INPUTS, PS1_CHEATS467_REFERENCE))
DELTA |= PS1_CHEATS467_INPUTS

# The corrected Build 467 IPA is encrypted to a new, locally held private
# key. Pin its public certificate to the immutable reviewed commit that added
# it; it must never be mistaken for a source/input exemption.
DELIVERY467_RECIPIENT_PATH = 'build-utils/delivery-467-recipient.pem'
DELIVERY456_PINNED_INPUTS[DELIVERY467_RECIPIENT_PATH] = '5077a9384dcf5b603b42073d619579ffbb06b0b9'
DELTA.add(DELIVERY467_RECIPIENT_PATH)


# Build 468: crash-hardening product + reproducible 37-session Nestopia test.
# Pin only changed source/test bytes to the immutable candidate. The previous
# 467 cheat, catalogue and notice pins remain untouched.
SKIN_STABILITY468_REFERENCE = '9ee313d96b79550406c62c5b862c0f859b01ad00'
SKIN_STABILITY468_RUN = 38963540654
SKIN_STABILITY468_INPUTS = {
    'packages/libretro_internal_bridge/ios/Classes/LibretroSkinRenderer.h',
    'packages/libretro_internal_bridge/ios/Classes/LibretroSkinRenderer.m',
    'packages/libretro_internal_bridge/ios/Classes/LibretroGameViewController.m',
    'packages/libretro_internal_bridge/ios/Classes/LibretroMetalPresenter.m',
    'test/libretro_simulator/probe.m',
    'test/libretro_nestopia_skin_stability_probe.py',
}
DELIVERY456_PINNED_INPUTS.update(dict.fromkeys(SKIN_STABILITY468_INPUTS, SKIN_STABILITY468_REFERENCE))
DELTA |= SKIN_STABILITY468_INPUTS
# This workflow/CI recipe is a delivery-only update over the source above;
# it cannot modify the already-validated native inputs.
SKIN_STABILITY468_DELIVERY_RECIPE = 'e634c98b49776db219b5a8cb8b15d433e55c6b6b'
DELIVERY456_PINNED_INPUTS['.github/workflows/retroarch-delivery.yml'] = SKIN_STABILITY468_DELIVERY_RECIPE
SKIN_STABILITY468_RECIPIENT = 'docs/delivery/recipients/neostation-468-chatgpt-recipient.pem'
SKIN_STABILITY468_RECIPIENT_SHA256 = '503232ab14e40879949584b809fc36fa081cc2634ba1b8c993bb12b56aebaa73'

# Build 470: terminal lifetime repair and native fault diagnostics. Every
# changed runtime/test input is pinned to the reviewed product, not exempted.
SKIN_STABILITY470_REFERENCE = '2e877872a919c119fb3d10f47699218cc1a34e96'
SKIN_STABILITY470_RUN = 39071406998
SKIN_STABILITY470_RECIPIENT = 'docs/delivery/recipients/neostation-470-skins-recipient.pem'
SKIN_STABILITY470_RECIPIENT_SHA256 = '77d32cd61a7a2c3e91bd44e4f949c8382d19c0ee2910bf413564a36a3bdcf9b7'
SKIN_STABILITY470_INPUTS = {
    'packages/libretro_internal_bridge/ios/Classes/LibretroCrashCapture.h',
    'packages/libretro_internal_bridge/ios/Classes/LibretroGameViewController.m',
    'packages/libretro_internal_bridge/ios/Classes/LibretroMetalPresenter.h',
    'packages/libretro_internal_bridge/ios/Classes/LibretroMetalPresenter.m',
    'packages/libretro_internal_bridge/ios/Classes/LibretroSession.m',
    'packages/libretro_internal_bridge/ios/Classes/LibretroSessionJournal.h',
    'packages/libretro_internal_bridge/ios/Classes/LibretroSessionJournal.m',
    'packages/libretro_internal_bridge/ios/Classes/LibretroSkinRenderer.h',
    'packages/libretro_internal_bridge/ios/Classes/LibretroSkinRenderer.m',
    'test/libretro_crash_capture_test.c',
    'test/libretro_crash_capture_test.py',
    'test/libretro_nestopia_skin_stability_probe.py',
    'test/libretro_simulator/probe.m',
    'test/libretro_simulator/skin_lifetime_probe.h',
    'test/libretro_simulator_probe.py',
}
DELIVERY456_PINNED_INPUTS.update(dict.fromkeys(SKIN_STABILITY470_INPUTS, SKIN_STABILITY470_REFERENCE))
DELTA |= SKIN_STABILITY470_INPUTS
DELIVERY456_PINNED_INPUTS['.github/workflows/retroarch-delivery.yml'] = '18968851c52095aa2c94d57a60c3eed9a3301075'

# Build 443 changes only the book/manga cover widget and its catalogue wiring.
# Unlike the broad historical delta, this scope closes the entire tracked tree.
LIBRARY_COVERS_REFERENCE = 'e8808dd32301f71fdd421a70c0ac6be2ed6fba47'
LIBRARY_COVERS_RUN = 38170927050
LIBRARY_COVERS_DELTA = {
    'build-utils/delivery-443-recipient.pem',
    'lib/screens/library_screen/library_screen.dart',
    'lib/widgets/library_book_cover.dart',
    'test/library_book_cover_test.dart',
    'test/library_ui_hub_test.dart',
    'test/library_cover_delivery_test.py',
    'test/delivery_pipeline_test.py',
    'build-utils/verify_delivery_reuse.py',
    '.github/workflows/retroarch-delivery.yml',
    'docs/build442-plan.md',
    'docs/build443-plan.md',
    'docs/library-book-cover-3d.md',
}
DELTA |= LIBRARY_COVERS_DELTA
INPUT_ROOTS =('lib/', 'packages/', 'native/', 'build-utils/', 'assets/', 'test/')

# Build 441 changes RPCS3/NeoSwap only. The targeted lane retains the actual
# Build 440 evidence and rejects every other runtime, dependency or recipe delta.
NEOSWAP_441_REFERENCE = '0913f260beb71874ac4aea48ac3ac8014232f119'
NEOSWAP_441_EVIDENCE = (
    (38161126590, 'cbd0ff0124a4af7a34d1b10b3e22e0991d7d5e64', '.github/workflows/retroarch-delivery.yml', ('checks', 'native', 'Release device build • cold')),
    (38161934907, NEOSWAP_441_REFERENCE, '.github/workflows/dolphin-motion-check.yml', ()),
    (38161174475, '1bc0edf8396c913c4c7d6d0d2665decdaa09c23a', '.github/workflows/ui-refresh-rate-check.yml', ()),
)
NEOSWAP_441_DELTA = {
    'build-utils/rpcs3/embedded-core.patch',
    'build-utils/rpcs3/canonical-source.json',
    'build-utils/build_rpcs3_embedded_core.sh',
    'build-utils/verify_delivery_reuse.py',
    'native/neoswap-relay/Backend.cpp',
    'native/neoswap-relay/Backend.h',
    'packages/neo_swap/ios/Classes/NeoSwapRelay.h',
    'packages/neo_swap/ios/Classes/NeoSwapRelayService.mm',
    'packages/neo_swap/ios/Classes/NeoSwapBudget.h',
    'packages/neo_swap/ios/Classes/NeoSwap.cpp',
    'packages/neo_swap/ios/Classes/NeoSwapHost.h',
    'packages/neo_swap/ios/Classes/NeoSwapPlugin.mm',
    'packages/rpcs3_internal_bridge/ios/Classes/Rpcs3CoreABI.h',
    'packages/rpcs3_internal_bridge/ios/Classes/Rpcs3InternalBridgePlugin.mm',
    'test/neo_swap_core_pin_test.py',
    'test/rpcs3_neoswap_relay_test.py',
    'test/native/rpcs3_neoswap_relay_test.cpp',
    'test/relay_backend_test.cpp',
    'test/neoswap_budget_test.cpp',
    'test/delivery_pipeline_test.py',
    'test/retroarch_baseline_scope_test.py',
    'test/rpcs3_neoswap_build_comparison_test.py',
    'test/neoswap_donor_contract_test.py',
    'tools/compare_rpcs3_neoswap_builds.py',
    '.github/workflows/rpcs3-core.yml',
    '.github/workflows/retroarch-delivery.yml',
    '.github/workflows/neoswap-ipa.yml',
}
DELTA |= NEOSWAP_441_DELTA


def verify_neoswap_tree(reference=NEOSWAP_441_REFERENCE):
    """Closed Build440 inputs; only reviewed RPCS3/NeoSwap paths may differ."""
    roots = INPUT_ROOTS + ('tools/', '.github/workflows/')
    tracked = lambda path: path.startswith(roots) or path in ('pubspec.yaml', 'pubspec.lock')
    old = {}
    for line in subprocess.check_output(['git', 'ls-tree', '-r', reference], cwd=ROOT, text=True).splitlines():
        metadata, path = line.split('\t', 1)
        if tracked(path):
            old[path] = metadata.split()
    current = {p for p in subprocess.check_output(['git', 'ls-files'], cwd=ROOT, text=True).splitlines() if tracked(p)}
    changed, unchanged = [], {}
    for path in sorted(set(old) | current):
        file = ROOT / path
        data = file.read_bytes() if file.is_file() and not file.is_symlink() else None
        oid = hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest() if data is not None else None
        if path in old and data is not None:
            mode = '100755' if file.stat().st_mode & 0o111 else '100644'
            if mode != old[path][0]:
                raise ValueError('NeoSwap delivery input mode changed: ' + path)
        if path in old and old[path][2] == oid:
            unchanged[path] = sha(data)
            continue
        if path == 'pubspec.yaml' and data is not None:
            before = subprocess.check_output(['git', 'show', reference + ':' + path], cwd=ROOT)
            strip_version = lambda payload: b'\n'.join(line for line in payload.splitlines() if not line.startswith(b'version: '))
            if strip_version(before) != strip_version(data):
                raise ValueError('NeoSwap delivery changed dependencies instead of only the build version')
        elif path not in NEOSWAP_441_DELTA:
            raise ValueError('Unreviewed NeoSwap delivery input changed: ' + path)
        if data is None:
            raise ValueError('NeoSwap delivery input is missing or symlinked: ' + path)
        changed.append(path)
    return changed, unchanged


def verify_neoswap_evidence():
    records = []
    for run_id, commit, workflow, required_jobs in NEOSWAP_441_EVIDENCE:
        run = json.loads(subprocess.check_output(['gh', 'api', f'repos/TarbleFR/neostation-ios/actions/runs/{run_id}']))
        if run['head_sha'] != commit or run['conclusion'] != 'success' or run['path'] != workflow:
            raise ValueError('Build440 evidence is not successful at its exact reference: ' + str(run_id))
        jobs = json.loads(subprocess.check_output(['gh', 'api', f'repos/TarbleFR/neostation-ios/actions/runs/{run_id}/jobs']))['jobs']
        if required_jobs:
            for name in required_jobs:
                if not any(job['name'] == name and job['conclusion'] == 'success' for job in jobs):
                    raise ValueError('Build440 evidence lacks successful job ' + name)
        elif not jobs or any(job['conclusion'] != 'success' for job in jobs):
            raise ValueError('Build440 follow-up includes an unsuccessful job: ' + str(run_id))
        records.append({'run': run_id, 'testedSHA': commit, 'workflow': workflow,
                        'successfulJobs': [job['name'] for job in jobs if job['conclusion'] == 'success']})
    return records


def verify_library_covers_tree(reference=LIBRARY_COVERS_REFERENCE):
    """Reuse Build442 only when every other tracked input remains identical."""
    old = {}
    for entry in subprocess.check_output(
            ['git', 'ls-tree', '-rz', reference], cwd=ROOT).split(b'\0'):
        if entry:
            metadata, raw_path = entry.split(b'\t', 1)
            old[raw_path.decode()] = metadata.decode().split()
    # Include nonignored untracked inputs during local review, too. In CI every
    # source is tracked by the checkout; a newly added input cannot hide here.
    current = {p.decode() for p in subprocess.check_output(
        ['git', 'ls-files', '-z', '--cached', '--others', '--exclude-standard'],
        cwd=ROOT).split(b'\0') if p}
    changed, unchanged = [], {}
    for path in sorted(set(old) | current):
        file = ROOT / path
        if file.is_symlink() or not file.is_file():
            raise ValueError('Library covers input is missing or symlinked: ' + path)
        data = file.read_bytes()
        mode = '100755' if file.stat().st_mode & 0o111 else '100644'
        if path in old and mode != old[path][0]:
            raise ValueError('Library covers input mode changed: ' + path)
        oid = hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest()
        if path in old and oid == old[path][2]:
            unchanged[path] = sha(data)
        elif path in LIBRARY_COVERS_DELTA:
            if path not in old and mode != '100644':
                raise ValueError('Library covers added input must be nonexecutable: ' + path)
            changed.append(path)
        else:
            raise ValueError('Unreviewed library covers input changed: ' + path)
    # The only workflow edits permitted by this lane concern validation, never
    # donor pins, compilation, packaging, signature checks or encryption.
    workflow = '.github/workflows/retroarch-delivery.yml'
    if workflow in old:
        before = subprocess.check_output(['git', 'show', reference + ':' + workflow], cwd=ROOT, text=True)
        after = (ROOT / workflow).read_text()
        # A fresh public recipient is necessary to decrypt this authorized IPA.
        # This exact key-path rotation is the sole packaging change allowed.
        after = after.replace('DELIVERY_RECIPIENT: build-utils/delivery-443-recipient.pem',
                              'DELIVERY_RECIPIENT: build-utils/delivery-424-recipient.pem')
        before = before.replace('DELIVERY_RECIPIENT: build-utils/delivery-443-recipient.pem',
                                'DELIVERY_RECIPIENT: build-utils/delivery-424-recipient.pem')
        marker = '  cold:\n'
        if marker not in before or marker not in after or before.split(marker, 1)[1] != after.split(marker, 1)[1]:
            raise ValueError('Library covers delivery changed the pinned packaging recipe')
        native_start = '    - name: Validate changed RPCS3 NeoSwap allocators and iPhone control plane\n'
        native_end = '    - name: Preserve exact NeoSwap native validation\n'
        before_native = before.split(native_start, 1)[1].split(native_end, 1)[0].split('      run: |\n', 1)[1]
        after_native = after.split(native_start, 1)[1].split(native_end, 1)[0].split('      run: |\n', 1)[1]
        if before_native != after_native:
            raise ValueError('Library covers delivery changed the pinned native test recipe')
    return changed, unchanged


def verify_library_covers_evidence():
    """Require the successful exact Build442 jobs, including reused evidence."""
    endpoint = f'repos/TarbleFR/neostation-ios/actions/runs/{LIBRARY_COVERS_RUN}'
    run = json.loads(subprocess.check_output(['gh', 'api', endpoint]))
    if (run.get('head_sha') != LIBRARY_COVERS_REFERENCE
            or run.get('status') != 'completed' or run.get('conclusion') != 'success'
            or run.get('path') != '.github/workflows/retroarch-delivery.yml'):
        raise ValueError('Build442 evidence is not successful at its exact reference')
    jobs = json.loads(subprocess.check_output(['gh', 'api', endpoint + '/jobs?per_page=100']))['jobs']
    required = {
        'checks': ('Verify closed validation input tree and previous CI success',
                   'Verify reused Dart evidence and changed pipeline guards'),
        'native': ('Select Xcode 26.3 for NeoPlay and Google Cast',
                   'Validate changed RPCS3 NeoSwap allocators and iPhone control plane',
                   'Verify prior Swift success for identical transport inputs',
                   'Run the embedded libretro host against a test core',
                   'Run the portable libretro frontend modules (geometry, controls, settings, skins)',
                   'Compile and render every libretro shader preset with Metal',
                   'Compile and link every libretro bridge source for iPhone'),
        'Release device build • cold': ('Compile Release device binary with measured AOT and Xcode phases',
                                        'Package and validate NeoStation IPA',
                                        'Seal every executable, framework and extension for SideStore'),
    }
    for name, steps in required.items():
        matching = [j for j in jobs if j.get('name') == name]
        if len(matching) != 1 or matching[0].get('conclusion') != 'success':
            raise ValueError('Build442 evidence lacks successful job ' + name)
        job = matching[0]
        if job.get('head_sha') != LIBRARY_COVERS_REFERENCE or job.get('run_id') != LIBRARY_COVERS_RUN:
            raise ValueError('Build442 job identity differs: ' + name)
        for step in steps:
            if not any(s.get('name') == step and s.get('conclusion') == 'success' for s in job.get('steps', ())):
                raise ValueError('Build442 evidence lacks successful step ' + step)
    return {'run': LIBRARY_COVERS_RUN, 'testedSHA': LIBRARY_COVERS_REFERENCE,
            'workflow': run['path'], 'successfulJobs': list(required),
            'validationWasReused': True, 'deviceGameplayValidated': False}


def sha(data):
    return hashlib.sha256(data).hexdigest()

TARGETED470_SOURCE = '6b1aaba9dd8b6e7cdb50de5730fbd6f51dd0a9eb'
TARGETED470_REFERENCE = '2ca52ba233e5acaf3b8848dc3a21b78719a74e87'
TARGETED470_RUN = 39077361583
TARGETED470_MENU_PATH = 'packages/libretro_internal_bridge/ios/Classes/LibretroCheatMenu.m'
TARGETED470_RECIPES = {'.github/workflows/libretro-memory-ownership470.yml',
    '.github/diagnostics/libretro_memory_probe.py', '.github/diagnostics/libretro_simulator_device.py'}
TARGETED470_REVIEWED_SOURCE_REFS = dict.fromkeys(SKIN_STABILITY470_INPUTS, SKIN_STABILITY470_REFERENCE)
TARGETED470_REVIEWED_SOURCE_REFS[TARGETED470_MENU_PATH] = TARGETED470_SOURCE
DELIVERY456_PINNED_INPUTS[TARGETED470_MENU_PATH] = TARGETED470_SOURCE
DELIVERY456_PINNED_INPUTS.update(dict.fromkeys(TARGETED470_RECIPES, TARGETED470_REFERENCE))
DELTA |= TARGETED470_RECIPES


def verify_libretro_reuse_tree(reference=LIBRETRO_SKIN_PRESS_REFERENCE, *, ignored=(), exact_inputs=(), reviewed_overrides=()):
    """Close all source/dependency inputs of the already successful native job."""
    roots = INPUT_ROOTS + ('tools/',)
    exact = {'pubspec.yaml', 'pubspec.lock', '.github/workflows/libretro-checks.yml'} | set(exact_inputs)
    # Delivery-only guards have new tests; none is imported by these harnesses.
    guards = {'build-utils/verify_delivery_reuse.py', 'test/delivery_pipeline_test.py',
              'test/external_display_host_plist_test.py', DELIVERY460_RECIPIENT_PATH,
              # The public envelope is pinned byte-for-byte above and never
              # linked into or read by the libretro runtime/test harness.
              DELIVERY467_RECIPIENT_PATH} | set(ignored)
    selected = lambda p: (p.startswith(roots) or p in exact) and p not in guards
    old = {}
    for line in subprocess.check_output(['git', 'ls-tree', '-r', reference], cwd=ROOT, text=True).splitlines():
        metadata, path = line.split('\t', 1)
        if selected(path):
            old[path] = metadata.split()
    for path, reviewed in dict(reviewed_overrides).items():
        if TARGETED470_REVIEWED_SOURCE_REFS.get(path) != reviewed or not selected(path):
            raise ValueError('Unreviewed source override: ' + path)
        entry = subprocess.check_output(['git','ls-tree',reviewed,'--',path],cwd=ROOT,text=True).strip()
        metadata, actual_path = entry.split('\t',1)
        if actual_path != path:
            raise ValueError('Missing reviewed source override: ' + path)
        old[path] = metadata.split()
    current = {p for p in subprocess.check_output(
        ['git', 'ls-files', '--cached', '--others', '--exclude-standard'], cwd=ROOT, text=True).splitlines() if selected(p)}
    hashes = {}
    for path in sorted(set(old) | current):
        file = ROOT / path
        if path not in old or file.is_symlink() or not file.is_file():
            raise ValueError('Libretro reuse input added, missing or symlinked: ' + path)
        data = file.read_bytes()
        mode = '100755' if file.stat().st_mode & 0o111 else '100644'
        oid = hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest()
        if old[path] != [mode, 'blob', oid]:
            raise ValueError('Libretro reuse input changed: ' + path)
        hashes[path] = sha(data)
    return hashes

def verify_470_reuse_tree(reference, *, exact_inputs=()):
    # Only the ARC ownership declaration differs from the successful common
    # runtime. Its new bytes require separate successful targeted evidence.
    return verify_libretro_reuse_tree(reference, exact_inputs=exact_inputs,
        reviewed_overrides={TARGETED470_MENU_PATH: TARGETED470_SOURCE})


SKIN_SESSION_REFERENCE = '2e877872a919c119fb3d10f47699218cc1a34e96'
SKIN_SESSION_RUN = 39071406958

CHEAT_CATALOG_REFERENCE = '6a7ddb54568e9048a7b66682c6fcdd9889f9f9ef'
CHEAT_CATALOG_RUN = 38887218980
CHEAT_RECIPE_REFERENCE = 'd11c92bcf50abe9cf55280238011f9828359e188'
CHEAT_RECIPE_INPUTS = {'.github/workflows/libretro-cheats-checks.yml',
                       '.github/diagnostics/libretro_simulator_device.py'}
DELIVERY456_PINNED_INPUTS.update(dict.fromkeys(CHEAT_RECIPE_INPUTS, CHEAT_RECIPE_REFERENCE))
DELTA |= CHEAT_RECIPE_INPUTS

def verify_skin_loading_evidence():
    """Require the historical negative reproduction and current installed-skin tests."""
    endpoint = f'repos/TarbleFR/neostation-ios/actions/runs/{SKIN_LOADING_RUN}'
    run = json.loads(subprocess.check_output(['gh', 'api', endpoint]))
    if (run.get('head_sha') != SKIN_LOADING_REFERENCE or run.get('status') != 'completed'
            or run.get('conclusion') != 'success'
            or run.get('path') != '.github/workflows/libretro-skin-loading-checks.yml'):
        raise ValueError('Installed-skin loading evidence is different or incomplete')
    jobs = json.loads(subprocess.check_output(['gh', 'api', endpoint + '/jobs?per_page=100']))['jobs']
    matches = [job for job in jobs if job.get('name') == 'existing-install']
    if (len(matches) != 1 or matches[0].get('head_sha') != SKIN_LOADING_REFERENCE
            or matches[0].get('run_id') != SKIN_LOADING_RUN or matches[0].get('conclusion') != 'success'
            or not matches[0].get('steps')
            or any(step.get('conclusion') != 'success' for step in matches[0]['steps'])):
        raise ValueError('Installed-skin loading checks did not all pass')
    required = 'Reproduce exact 463 rejection then test already installed skins in the candidate'
    if not any(step.get('name') == required and step.get('conclusion') == 'success' for step in matches[0]['steps']):
        raise ValueError('Installed-skin loading proof step is missing')
    return {'run':SKIN_LOADING_RUN, 'testedSHA':SKIN_LOADING_REFERENCE,
            'successfulJob':'existing-install', 'physicalDeviceValidated':False}

def verify_catalog_audit_evidence():
    """Require actual transport/filter tests and original-image native compositions."""
    endpoint = f'repos/TarbleFR/neostation-ios/actions/runs/{CATALOG_AUDIT_RUN}'
    run = json.loads(subprocess.check_output(['gh', 'api', endpoint]))
    if (run.get('head_sha') != CATALOG_AUDIT_REFERENCE or run.get('status') != 'completed'
            or run.get('conclusion') != 'success'
            or run.get('path') != '.github/workflows/libretro-catalog-checks.yml'):
        raise ValueError('Catalogue audit evidence is different or incomplete')
    jobs = json.loads(subprocess.check_output(['gh', 'api', endpoint + '/jobs?per_page=100']))['jobs']
    matches = [job for job in jobs if job.get('name') == 'catalogues']
    required = {'Original configurations, transport, platform matrix and source filters',
                'Actual native compatibility and full previews from original PocketArch images'}
    if (len(matches) != 1 or matches[0].get('head_sha') != CATALOG_AUDIT_REFERENCE
            or matches[0].get('run_id') != CATALOG_AUDIT_RUN
            or matches[0].get('conclusion') != 'success' or not matches[0].get('steps')
            or any(step.get('conclusion') != 'success' for step in matches[0]['steps'])
            or not required.issubset({step.get('name') for step in matches[0]['steps']})):
        raise ValueError('Catalogue transport/filter/native audit did not all pass')
    return {'run': CATALOG_AUDIT_RUN, 'testedSHA': CATALOG_AUDIT_REFERENCE,
            'successfulJob': 'catalogues', 'physicalDeviceValidated': False}


def verify_cheat_catalog_evidence():
    endpoint = f'repos/TarbleFR/neostation-ios/actions/runs/{CHEAT_CATALOG_RUN}'
    run = json.loads(subprocess.check_output(['gh', 'api', endpoint]))
    if (run.get('head_sha') != CHEAT_CATALOG_REFERENCE or run.get('status') != 'completed'
            or run.get('conclusion') != 'success'
            or run.get('path') != '.github/workflows/libretro-cheats-checks.yml'):
        raise ValueError('Cheat catalogue/core evidence is different or incomplete')
    jobs = json.loads(subprocess.check_output(['gh', 'api', endpoint + '/jobs?per_page=100']))['jobs']
    matches = [job for job in jobs if job.get('name') == 'catalogues-and-cores']
    if (len(matches) != 1 or matches[0].get('head_sha') != CHEAT_CATALOG_REFERENCE
            or matches[0].get('conclusion') != 'success' or not matches[0].get('steps')
            or any(step.get('conclusion') != 'success' for step in matches[0]['steps'])):
        raise ValueError('Cheat catalogue/core checks did not all pass')
    return {'run': CHEAT_CATALOG_RUN, 'testedSHA': CHEAT_CATALOG_REFERENCE,
            'successfulJob': 'catalogues-and-cores', 'physicalDeviceValidated': False}

# The corrected menu and its Dynamic Type assertions are independently
# exercised on the exact reviewed product snapshot (not claimed as covered by
# the older successful 6a7d reference).
CHEAT_LAYOUT467_REFERENCE = '14e66cf20ca9c38154d2a26d39ca7705f95c1b4d'
CHEAT_LAYOUT467_RUN = 38907359293

def verify_cheat_layout467_evidence():
    endpoint = f'repos/TarbleFR/neostation-ios/actions/runs/{CHEAT_LAYOUT467_RUN}'
    run = json.loads(subprocess.check_output(['gh', 'api', endpoint]))
    if (run.get('head_sha') != CHEAT_LAYOUT467_REFERENCE
            or run.get('status') != 'completed' or run.get('conclusion') != 'success'
            or run.get('path') != '.github/workflows/libretro-cheats-checks.yml'):
        raise ValueError('Corrected native cheat layout was not validated by the exact Simulator run')
    jobs = json.loads(subprocess.check_output(['gh', 'api', endpoint + '/jobs?per_page=100']))['jobs']
    matching = [job for job in jobs if job.get('name') == 'catalogues-and-cores']
    if (len(matching) != 1 or matching[0].get('head_sha') != CHEAT_LAYOUT467_REFERENCE
            or matching[0].get('conclusion') != 'success'):
        raise ValueError('Corrected native cheat layout job is not successful')
    required = {
        'Bounded parsers, adapters, two sources and offline storage',
        'Bundled index integrity and complete translations',
        'Convert the actual Libretro overlay configurations used in the reported previews',
        'Real Nestopia and Snes9x cheat effects, original Ignited on Nestopia',
    }
    successful = {step.get('name') for step in matching[0].get('steps', [])
                  if step.get('conclusion') == 'success'}
    if not required.issubset(successful):
        raise ValueError('Corrected native cheat layout did not pass all source and Simulator checks')
    return {'testedSHA': CHEAT_LAYOUT467_REFERENCE, 'run': CHEAT_LAYOUT467_RUN,
            'successfulSteps': sorted(required), 'physicalDeviceValidated': False}


def verify_nestopia_skin_stability468_evidence():
    """Require the complete real Nestopia + original author skin CI results."""
    endpoint = f'repos/TarbleFR/neostation-ios/actions/runs/{SKIN_STABILITY468_RUN}'
    run = json.loads(subprocess.check_output(['gh', 'api', endpoint]))
    if (run.get('head_sha') != SKIN_STABILITY468_REFERENCE
            or run.get('status') != 'completed' or run.get('conclusion') != 'success'
            or run.get('path') != '.github/workflows/libretro-nestopia-skin-stability.yml'):
        raise ValueError('37-session NESThumbstick proof did not pass at exact source')
    jobs = json.loads(subprocess.check_output(['gh','api',endpoint + '/jobs?per_page=100']))['jobs']
    relevant = [j for j in jobs if j.get('name') == 'original-skin-on-real-nestopia']
    if (len(relevant) != 1 or relevant[0].get('head_sha') != SKIN_STABILITY468_REFERENCE
            or relevant[0].get('conclusion') != 'success' or not relevant[0].get('steps')
            or any(s.get('conclusion') != 'success' for s in relevant[0]['steps'])):
        raise ValueError('37-session Nestopia job or its required steps failed')
    name = 'Real Nestopia — original NESThumbstick and 37 game sessions'
    if not any(s.get('name') == name and s.get('conclusion') == 'success'
               for s in relevant[0]['steps']):
        raise ValueError('Original author skin was not run through real Nestopia')
    return {'run':SKIN_STABILITY468_RUN,'testedSHA':SKIN_STABILITY468_REFERENCE,
            'realNestopiaSessions':37, 'originalSkinSessions':31,
            'physicalDeviceValidated':False}


def validate_nestopia470_verdict(record, *, baseline=False, asan=False):
    expected = (1, 0, 0, 3) if baseline else ((6, 3, 3, 38) if asan else (82, 10, 8, 38))
    cold_count = 0 if baseline or asan else 10
    cold = record.get('coldProcessEvidence', [])
    if (record.get('coldProcesses') != cold_count or len(cold) != cold_count
            or len({e.get('session') for e in cold}) != cold_count
            or any(e.get('launch') != i+1 or not e.get('pid') or not e.get('session')
                   or e.get('finished') is not True or e.get('failures') != [] for i, e in enumerate(cold))):
        raise ValueError('Incomplete independent-process Nestopia 470 verdict')
    actual = tuple(record.get(k) for k in ('attemptsOriginal', 'attemptsWithoutSkin',
                                         'attemptsOtherCatalogue', 'checks'))
    if (record.get('source') != SKIN_STABILITY470_REFERENCE or actual != expected
            or record.get('failures') != [] or record.get('allSessionsClosed') is not True
            or record.get('physicalDeviceValidated') is not False
            or record.get('commercialROMUsed') is not False
            or record.get('baseline469Bodies') is not baseline
            or record.get('addressSanitizer') is not asan
            or record.get('prebuiltCoreInstrumented') is not False):
        raise ValueError('Incomplete, different-source or misclassified Nestopia 470 verdict')
    return record


def verify_nestopia_skin_stability470_evidence():
    """Require both successful jobs AND their actual bounded verdict files."""
    endpoint = f'repos/TarbleFR/neostation-ios/actions/runs/{SKIN_STABILITY470_RUN}'
    run = json.loads(subprocess.check_output(['gh', 'api', endpoint]))
    if (run.get('head_sha') != SKIN_STABILITY470_REFERENCE or run.get('status') != 'completed'
            or run.get('conclusion') != 'success'
            or run.get('path') != '.github/workflows/libretro-nestopia-skin-stability.yml'):
        raise ValueError('100-session Nestopia and sanitizer workflow is not successful at exact source')
    jobs = json.loads(subprocess.check_output(['gh', 'api', endpoint + '/jobs?per_page=100']))['jobs']
    required = {
        'original-skin-on-real-nestopia': (
            'Native fatal-signal capture behaviour',
            'Reproduce 469 terminal-lifetime defects with unchanged renderer and view bodies',
            'Real Nestopia — original NESThumbstick and 100 game sessions'),
        'memory-sanitizers': (
            'Concurrent journal writes under ThreadSanitizer',
            'Real Nestopia — 12 bridge AddressSanitizer sessions'),
    }
    for name, steps in required.items():
        matches = [job for job in jobs if job.get('name') == name]
        if (len(matches) != 1 or matches[0].get('head_sha') != SKIN_STABILITY470_REFERENCE
                or matches[0].get('conclusion') != 'success'
                or any(s.get('conclusion') != 'success' for s in matches[0].get('steps', []))
                or any(not any(s.get('name') == step and s.get('conclusion') == 'success'
                               for s in matches[0].get('steps', [])) for step in steps)):
            raise ValueError('Incomplete Nestopia proof job: ' + name)
    import tempfile
    with tempfile.TemporaryDirectory(prefix='nestopia-470-proof-') as temporary:
        folder = Path(temporary)
        for artifact, subfolder in (('nestopia-skin-stability-', 'normal'),
                                   ('nestopia-memory-sanitizers-', 'asan')):
            subprocess.run(['gh', 'run', 'download', str(SKIN_STABILITY470_RUN),
                            '--repo', 'TarbleFR/neostation-ios', '--name', artifact + SKIN_STABILITY470_REFERENCE,
                            '--dir', str(folder / subfolder)], check=True)
        normal = validate_nestopia470_verdict(json.loads(
            (folder / 'normal/skin-stability-verdict.json').read_text()))
        baseline = validate_nestopia470_verdict(json.loads(
            (folder / 'normal/baseline469/skin-stability-verdict.json').read_text()), baseline=True)
        asan = validate_nestopia470_verdict(json.loads(
            (folder / 'asan/skin-stability-verdict.json').read_text()), asan=True)
    return {'run': SKIN_STABILITY470_RUN, 'testedSHA': SKIN_STABILITY470_REFERENCE,
            'realNestopiaSessions': 100, 'originalSkinSessions': 82,
            'independentProcessRestarts': 10,
            'addressSanitizerSessions': 12, 'baseline469': baseline,
            'normal': normal, 'asan': asan, 'physicalDeviceValidated': False}


def verify_skin_session_evidence():
    """Require the complete shared session suite from the engine workflow."""
    endpoint = f'repos/TarbleFR/neostation-ios/actions/runs/{SKIN_SESSION_RUN}'
    run = json.loads(subprocess.check_output(['gh', 'api', endpoint]))
    if (run.get('head_sha') != SKIN_SESSION_REFERENCE or run.get('status') != 'completed'
            or run.get('path') != '.github/workflows/libretro-checks.yml'):
        raise ValueError('Directional skin session evidence is different or incomplete')
    jobs = json.loads(subprocess.check_output(['gh', 'api', endpoint + '/jobs?per_page=100']))['jobs']
    matches = [job for job in jobs if job.get('name') == 'skin-press']
    if (len(matches) != 1 or matches[0].get('head_sha') != SKIN_SESSION_REFERENCE
            or matches[0].get('conclusion') != 'success'
            or not matches[0].get('steps')
            or not any(step.get('name') == 'Skin artwork and delivered inputs in actual embedded sessions'
                       for step in matches[0]['steps'])
            or any(step.get('conclusion') != 'success' for step in matches[0]['steps'])):
        raise ValueError('Directional skin sessions did not all pass')
    return {'run': SKIN_SESSION_RUN, 'testedSHA': SKIN_SESSION_REFERENCE,
            'successfulJob': 'skin-press', 'overallRunConclusion': run.get('conclusion'),
            'nativePortableTestsRequireSeparateSuccess': True}

LIBRETRO_SKIN_PRESS_REFERENCE = SKIN_STABILITY470_REFERENCE
LIBRETRO_SKIN_PRESS_RUN = 39071406958

def verify_libretro_reuse_evidence():
    endpoint = f'repos/TarbleFR/neostation-ios/actions/runs/{LIBRETRO_SKIN_PRESS_RUN}'
    run = json.loads(subprocess.check_output(['gh', 'api', endpoint]))
    if (run.get('head_sha') != LIBRETRO_SKIN_PRESS_REFERENCE or run.get('status') != 'completed'
            or run.get('conclusion') != 'success' or run.get('path') != '.github/workflows/libretro-checks.yml'):
        raise ValueError('Skin press evidence is not successful at the exact reference')
    jobs = json.loads(subprocess.check_output(['gh', 'api', endpoint + '/jobs?per_page=100']))['jobs']
    for name in ('native', 'dart', 'skin-press'):
        matches = [j for j in jobs if j.get('name') == name]
        if (len(matches) != 1 or matches[0].get('conclusion') != 'success'
                or matches[0].get('head_sha') != LIBRETRO_SKIN_PRESS_REFERENCE
                or any(s.get('conclusion') != 'success' for s in matches[0].get('steps', []))):
            raise ValueError('Skin press evidence has an unsuccessful or different job: ' + name)
    return {'run': LIBRETRO_SKIN_PRESS_RUN, 'testedSHA': LIBRETRO_SKIN_PRESS_REFERENCE,
            'workflow': run['path'], 'successfulJobs': ['native', 'dart', 'skin-press']}

DELIVERY460_DART_REFERENCE = '2f7a09608d7587f8522e2323433c7d31b15565df'
DELIVERY460_DART_RUN = 38707150124

def verify_delivery460_dart_evidence():
    """The Dart phases passed; a later, separate Python contract failed."""
    endpoint = f'repos/TarbleFR/neostation-ios/actions/runs/{DELIVERY460_DART_RUN}'
    run = json.loads(subprocess.check_output(['gh', 'api', endpoint]))
    if (run.get('head_sha') != DELIVERY460_DART_REFERENCE or run.get('status') != 'completed'
            or run.get('path') != '.github/workflows/retroarch-delivery.yml'):
        raise ValueError('Dart phase evidence has a different or incomplete source')
    jobs = json.loads(subprocess.check_output(['gh', 'api', endpoint + '/jobs?per_page=100']))['jobs']
    matches = [j for j in jobs if j.get('name') == 'checks']
    if len(matches) != 1 or matches[0].get('head_sha') != DELIVERY460_DART_REFERENCE:
        raise ValueError('Dart phase job differs')
    steps = matches[0].get('steps', [])
    required = ('Run subosito/flutter-action@v2',
                'Verify closed validation input tree and previous CI success',
                'Analyze the changed integration and its restored dependencies',
                'Reproduce the seven-root registration defect on the unchanged 422 code',
                'Validate changed library, callback, launch and restart behavior')
    for name in required:
        hits = [s for s in steps if s.get('name') == name]
        if len(hits) != 1 or hits[0].get('conclusion') != 'success':
            raise ValueError('Dart phase did not pass: ' + name)
    failed = [s['name'] for s in steps if s.get('conclusion') == 'failure']
    if failed != ['Verify reused Dart evidence and changed pipeline guards']:
        raise ValueError('Dart evidence has an unexpected failure')
    return {'run': DELIVERY460_DART_RUN, 'testedSHA': DELIVERY460_DART_REFERENCE,
            'successfulSteps': list(required), 'overallJobConclusion': matches[0]['conclusion'],
            'laterFailedStepRequiringNewValidation': failed[0]}

def verify_reviewed_delivery_inputs():
    for reference in sorted(set(DELIVERY456_PINNED_INPUTS.values())):
        paths = sorted(path for path, pinned in DELIVERY456_PINNED_INPUTS.items()
                       if pinned == reference)
        entries = subprocess.check_output(
            ['git', 'ls-tree', '-r', reference, '--', *paths], cwd=ROOT, text=True)
        expected = {}
        for line in entries.splitlines():
            metadata, path = line.split('\t', 1)
            expected[path] = metadata.split()
        for path in paths:
            file = ROOT / path
            if path not in expected or not file.is_file() or file.is_symlink():
                raise ValueError('Reviewed delivery input is missing or symlinked: ' + path)
            mode, kind, oid = expected[path]
            if kind != 'blob' or mode not in ('100644', '100755'):
                raise ValueError('Reviewed delivery reference is not a regular input: ' + path)
            actual_mode = '100755' if file.stat().st_mode & 0o111 else '100644'
            if actual_mode != mode:
                raise ValueError('Reviewed delivery input mode changed: ' + path)
            data = file.read_bytes()
            actual_oid = hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest()
            if actual_oid != oid:
                raise ValueError('Reviewed delivery input differs from ' + reference + ': ' + path)
    recipient = ROOT / DELIVERY456_RECIPIENT_PATH
    if not recipient.is_file() or recipient.is_symlink():
        raise ValueError('Private delivery recipient is missing or symlinked')
    if recipient.stat().st_mode & 0o111:
        raise ValueError('Private delivery recipient must be nonexecutable')
    public_key = recipient.read_bytes()
    if (sha(public_key) != DELIVERY456_RECIPIENT_SHA256
            or not public_key.startswith(b'-----BEGIN PUBLIC KEY-----\n')
            or not public_key.rstrip().endswith(b'-----END PUBLIC KEY-----')):
        raise ValueError('Private delivery recipient differs from the reviewed public key')

def verify_tree():
    verify_reviewed_delivery_inputs()
    old = {}
    tree = subprocess.check_output(['git', 'ls-tree', '-r', REFERENCE], cwd=ROOT, text=True)
    for line in tree.splitlines():
        metadata, path = line.split('\t', 1)
        if path.startswith(INPUT_ROOTS) or path in ('pubspec.yaml', 'pubspec.lock'):
            old[path] = metadata.split()
    receiver_entry = subprocess.check_output(
        ['git', 'ls-tree', RECEIVER_REFERENCE, '--', RECEIVER_INPUT], cwd=ROOT, text=True)
    metadata, receiver_path = receiver_entry.strip().split('\t', 1)
    if receiver_path != RECEIVER_INPUT:
        raise ValueError('Missing pinned receiver validation input')
    old[receiver_path] = metadata.split()
    current = set(subprocess.check_output(['git', 'ls-files'], cwd=ROOT, text=True).splitlines())
    current = {p for p in current if p.startswith(INPUT_ROOTS) or p in ('pubspec.yaml', 'pubspec.lock')}
    changed = []
    unchanged = {}
    for path in sorted(set(old) | current):
        file = ROOT / path
        data = file.read_bytes() if file.is_file() else None
        oid = hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest() if data is not None else None
        if path not in old or old[path][2] != oid:
            if path not in DELTA:
                raise ValueError('Unreviewed validation input changed: ' + path)
            changed.append(path)
        else:
            mode = '100755' if file.stat().st_mode & 0o111 else '100644'
            if mode != old[path][0]:
                raise ValueError('Validation input mode changed: ' + path)
            unchanged[path] = sha(data)
    return changed, unchanged

def validate_targeted470_verdict(record, ownership):
    if (record.get('source') != TARGETED470_REFERENCE or record.get('productionSource') != TARGETED470_SOURCE
            or record.get('problems') != [] or record.get('physicalDeviceValidated') is not False
            or record.get('outcome',{}).get('finished') is not True
            or record.get('restartOutcome',{}).get('finished') is not True
            or record.get('functionalCheatChecks') != 99 or record.get('persistenceCheatChecks') != 4):
        raise ValueError('Incomplete or different targeted 470 verdict')
    records = record.get('records',[])
    owners = ('session','controller','presenter','audio','host','input','skinRenderer','overlay',
              'cheatMenu','cheatCatalog','catalogDocument','cheatRootPage')
    if (len(records) != 20 or [row.get('name') for row in records] != [f'memory-{i:02d}' for i in range(1,21)]
            or any(row.get('taskInfoStatus') != 0 or row.get('footprint',0) <= 0
                   or any(row.get('owners',{}).get(key) != 0 for key in owners) for row in records)):
        raise ValueError('Retained or unmeasured targeted 470 owner')
    if (ownership.get('baselineRootOwnership') != 'strong' or ownership.get('candidateRootOwnership') != 'weak'
            or ownership.get('visibleOwnership') != ['weak','weak']
            or ownership.get('actualSourcePath') != TARGETED470_MENU_PATH
            or ownership.get('changedIPhoneSourceCompiled') is not True):
        raise ValueError('Targeted 470 ARC/iPhone proof missing')
    return record


def verify_targeted470_evidence():
    # Never reinterpret the older successful runs as coverage of new Menu bytes.
    endpoint = f'repos/TarbleFR/neostation-ios/actions/runs/{TARGETED470_RUN}'
    run = json.loads(subprocess.check_output(['gh','api',endpoint]))
    if (run.get('head_sha') != TARGETED470_REFERENCE or run.get('status') != 'completed'
            or run.get('conclusion') != 'success' or run.get('path') != '.github/workflows/libretro-memory-ownership470.yml'):
        raise ValueError('Targeted 470 ownership and cheat evidence is different or incomplete')
    jobs = json.loads(subprocess.check_output(['gh','api',endpoint+'/jobs?per_page=100']))['jobs']
    required = {'Prove production and existing test source identity',
                'Prove ARC ownership and compile only the changed iPhone file',
                'Verify 20 closed-session owners and actual cheat activation and persistence'}
    matches = [j for j in jobs if j.get('name') == 'targeted-cheat-lifetime']
    if (len(matches) != 1 or matches[0].get('head_sha') != TARGETED470_REFERENCE
            or matches[0].get('run_id') != TARGETED470_RUN or matches[0].get('conclusion') != 'success'
            or not matches[0].get('steps') or any(step.get('conclusion') != 'success' for step in matches[0]['steps'])
            or not required.issubset({step.get('name') for step in matches[0]['steps']})):
        raise ValueError('Targeted 470 checks did not all pass')
    # Close the ENTIRE actual product/test tree and the three diagnostic recipe
    # files against this successful witness; no product input is excluded here.
    closed = verify_libretro_reuse_tree(TARGETED470_REFERENCE, exact_inputs=TARGETED470_RECIPES)
    import tempfile
    with tempfile.TemporaryDirectory(prefix='targeted-470-proof-') as temporary:
        folder = Path(temporary)
        subprocess.run(['gh','run','download',str(TARGETED470_RUN),'--repo','TarbleFR/neostation-ios',
                        '--name','libretro-targeted-lifetime-'+TARGETED470_REFERENCE,'--dir',str(folder)],check=True)
        verdict = validate_targeted470_verdict(json.loads((folder/'memory-verdict.json').read_text()),
                                               json.loads((folder/'ownership-proof.json').read_text()))
        injection = json.loads((folder/'instrumentation.json').read_text())
        if injection != {'compiledInstrumentedProbeCount':1,'weakOwnersAndMallocSnapshots':True}:
            raise ValueError('Targeted ownership instrumentation was not compiled exactly once')
    return {'run':TARGETED470_RUN,'testedSHA':TARGETED470_REFERENCE,'productFixSHA':TARGETED470_SOURCE,
            'actualVerdict':verdict,'closedInputsSHA256':closed,'physicalDeviceValidated':False}


def verify_unchanged_cheat_modules470():
    paths = ['packages/libretro_internal_bridge/ios/Classes/'+name for name in
             ('LibretroCheatCatalog.h','LibretroCheatCatalog.m','LibretroCheats.h','LibretroCheats.m','LibretroCheatMenu.h')]
    paths += [p.relative_to(ROOT).as_posix() for p in
              (ROOT/'packages/libretro_internal_bridge/ios/Resources/Cheats').rglob('*') if p.is_file()]
    hashes = {}
    for path in paths:
        old = subprocess.check_output(['git','show',CHEAT_CATALOG_REFERENCE+':'+path],cwd=ROOT)
        current = (ROOT/path).read_bytes()
        if old != current:
            raise ValueError('Previously validated cheat module changed: '+path)
        hashes[path] = sha(current)
    return hashes


def verify_delivery470_dart_evidence():
    # This is the original full Dart execution behind the accepted 469 cache.
    # Its checks job passed completely before unrelated native/device jobs
    # were cancelled. Never require those jobs to execute unchanged Dart again.
    ref = 'fc1ef43a66b23a5e4c8be2cf790ba63b46e312a1'
    endpoint = 'repos/TarbleFR/neostation-ios/actions/runs/38962439914'
    run = json.loads(subprocess.check_output(['gh','api',endpoint]))
    if (run.get('head_sha') != ref or run.get('status') != 'completed'
            or run.get('path') != '.github/workflows/retroarch-delivery.yml'):
        raise ValueError('Original successful Dart phase provenance differs')
    jobs = json.loads(subprocess.check_output(['gh','api',endpoint+'/jobs?per_page=100']))['jobs']
    checks = [j for j in jobs if j.get('name') == 'checks']
    required = {'Analyze the changed integration and its restored dependencies',
                'Reproduce the seven-root registration defect on the unchanged 422 code',
                'Validate changed library, callback, launch and restart behavior',
                'Verify reused Dart evidence and changed pipeline guards'}
    if (len(checks) != 1 or checks[0].get('head_sha') != ref or checks[0].get('conclusion') != 'success'
            or any(not any(s.get('name') == name and s.get('conclusion') == 'success'
                           for s in checks[0].get('steps',[])) for name in required)):
        raise ValueError('Original full Dart checks did not pass')
    engine = verify_libretro_reuse_evidence()
    return {'originalDartRun':38962439914,'originalDartSHA':ref,'successfulJob':'checks',
            'wholeRunConclusion':run.get('conclusion'),'currentEngineEvidence':engine,
            'validationWasReused':True,'note':'Dart recipes and inputs unchanged; changed native bytes have independent exact witnesses.'}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--offline', action='store_true')
    parser.add_argument('--libretro-evidence', action='store_true')
    parser.add_argument('--dart-evidence', action='store_true')
    parser.add_argument('--skin-session-evidence', action='store_true')
    parser.add_argument('--scope', choices=('full', 'rpcs3_neoswap', 'library_covers'), default='full')
    parser.add_argument('--output', default='build/delivery/reused-validation.json')
    args = parser.parse_args()
    if args.skin_session_evidence:
        if args.offline:
            raise ValueError('Skin session verification requires online CI evidence')
        # The old successful skin/catalogue runs prove their historical
        # baselines. They do not claim coverage of the corrected menu.
        # Freeze EVERY current libretro dependency, test and recipe to the
        # reviewed post-layout product commit. Delivery-only source/recipient
        # records have separate pinned checks and cannot change this product.
        closed = verify_470_reuse_tree(SKIN_STABILITY470_REFERENCE, exact_inputs={
            '.github/workflows/libretro-nestopia-skin-stability.yml',
            '.github/workflows/libretro-skin-checks.yml',
            '.github/workflows/libretro-catalog-checks.yml'})
        # This retry adds only an external process sampler to the installed-
        # skin recipe. Close its recipe AND the entire product/test dependency
        # tree against its own successful revision; no runtime input exemption.
        loading_closed = verify_470_reuse_tree(SKIN_LOADING_REFERENCE, exact_inputs={
            '.github/workflows/libretro-skin-loading-checks.yml'})
        cheat_closed = verify_470_reuse_tree(CHEAT_RECIPE_REFERENCE, exact_inputs=CHEAT_RECIPE_INPUTS)
        evidence = verify_skin_session_evidence()
        cheats = verify_cheat_catalog_evidence()
        loading = verify_skin_loading_evidence()
        catalog = verify_catalog_audit_evidence()
        current_layout = verify_cheat_layout467_evidence()
        targeted = verify_targeted470_evidence()
        unchanged_cheats = verify_unchanged_cheat_modules470()
        stability = verify_nestopia_skin_stability470_evidence()
        recipient = ROOT / SKIN_STABILITY470_RECIPIENT
        if (not recipient.is_file() or recipient.is_symlink()
                or sha(recipient.read_bytes()) != SKIN_STABILITY470_RECIPIENT_SHA256):
            raise ValueError('Build 470 public delivery recipient differs from reviewed bytes')
        out = ROOT / args.output
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps({'result':'passed', 'reviewedProductSHA':SKIN_STABILITY470_REFERENCE,
            'closedSourceInputsSHA256':closed, 'currentLayoutEvidence':current_layout,
            'targetedCheatOwnershipEvidence':targeted, 'unchangedCheatModulesSHA256':unchanged_cheats,
            'nestopiaSkinStabilityEvidence':stability, 'deliveryPublicRecipientSha256':SKIN_STABILITY470_RECIPIENT_SHA256,
            'skinSessionEvidence':evidence, 'cheatEvidence':cheats, 'cheatClosedInputsSHA256':cheat_closed,
            'installedSkinEvidence':loading, 'installedSkinClosedInputsSHA256':loading_closed,
            'catalogueEvidence':catalog,
            'deviceGameplayValidated':False}, indent=2) + '\n')
        print('Verified complete corrected libretro product input closure:', len(closed),
              '; successful real-core Simulator evidence:', current_layout)
        return
    if args.dart_evidence:
        import os
        if args.offline:
            raise ValueError('Dart reuse requires online success of every named phase')
        verify_tree()
        hashes = verify_libretro_reuse_tree('fc1ef43a66b23a5e4c8be2cf790ba63b46e312a1',
            reviewed_overrides=TARGETED470_REVIEWED_SOURCE_REFS)
        path = '.github/workflows/retroarch-delivery.yml'
        old = subprocess.check_output(['git','show','fc1ef43a66b23a5e4c8be2cf790ba63b46e312a1:' + path],cwd=ROOT,text=True)
        current = (ROOT/path).read_text()
        start = '    - name: Analyze the changed integration and its restored dependencies\n'
        end = '    - name: Verify reused Dart evidence and changed pipeline guards\n'
        if old.split(start,1)[1].split(end,1)[0] != current.split(start,1)[1].split(end,1)[0]:
            raise ValueError('Dart validation recipe differs from delivered 469')
        report = {'result':'passed','testedSHA':'fc1ef43a66b23a5e4c8be2cf790ba63b46e312a1',
                  'key':os.environ['DART_VALIDATION_KEY'],'tool':'Flutter 3.47.2, Ubuntu 24.04',
                  'validationWasReused':True, 'evidence':verify_delivery470_dart_evidence(),
                  'targetedCheatOwnershipEvidence':verify_targeted470_evidence(),
                  'unchangedInputsSHA256':hashes,'deviceGameplayValidated':False}
        out = ROOT / args.output
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(report, indent=2) + '\n')
        print('Reused accepted 469 Dart phases and fresh 470 engine checks from', LIBRETRO_SKIN_PRESS_RUN,
              '; later Python contracts still require validation in this run')
        return
    if args.libretro_evidence:
        if args.offline:
            raise ValueError('Native reuse requires online CI success and the real Xcode toolchain')
        verify_tree()
        hashes = verify_470_reuse_tree(LIBRETRO_SKIN_PRESS_REFERENCE)
        cheat_hashes = verify_470_reuse_tree(CHEAT_RECIPE_REFERENCE, exact_inputs=CHEAT_RECIPE_INPUTS)
        cheats = verify_cheat_catalog_evidence()
        targeted = verify_targeted470_evidence()
        unchanged_cheats = verify_unchanged_cheat_modules470()
        xcode = subprocess.check_output(['xcodebuild', '-version'], text=True).strip()
        sdk = subprocess.check_output(['xcrun', '--sdk', 'iphoneos', '--show-sdk-version'], text=True).strip()
        if xcode != 'Xcode 26.3\nBuild version 17C529' or sdk != '26.2':
            raise ValueError('Libretro reuse toolchain differs from the successful native job')
        report = {'result': 'passed', 'validationWasReused': True,
                  'evidence': verify_libretro_reuse_evidence(), 'targetedCheatOwnershipEvidence':targeted,
                  'unchangedCheatModulesSHA256':unchanged_cheats, 'xcode': xcode, 'iphoneSDK': sdk,
                  'unchangedInputsSHA256': hashes, 'deviceGameplayValidated': False}
        out = ROOT / args.output
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(report, indent=2) + '\n')
        print('Reused successful native libretro checks from', LIBRETRO_SKIN_PRESS_REFERENCE,
              'run', LIBRETRO_SKIN_PRESS_RUN, '; identical source/dependency files:', len(hashes))
        return
    if args.scope == 'library_covers':
        changed, unchanged = verify_library_covers_tree()
        report = {'scope': args.scope, 'referenceSHA': LIBRARY_COVERS_REFERENCE,
                  'referenceRun': LIBRARY_COVERS_RUN,
                  'onlineSuccessVerified': not args.offline,
                  'unchangedInputCount': len(unchanged),
                  'unchangedInputsSha256': sha(json.dumps(unchanged, sort_keys=True).encode()),
                  'changedInputsRequiringNewTests': changed,
                  'evidence': None if args.offline else verify_library_covers_evidence(),
                  'deviceGameplayValidated': False}
        out = ROOT / args.output
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(report, indent=2) + '\n')
        print(json.dumps(report, indent=2))
        return
    changed, unchanged = verify_tree()
    scoped = None
    if args.scope == 'rpcs3_neoswap':
        scoped_changed, scoped_unchanged = verify_neoswap_tree()
        scoped = {'referenceSHA': NEOSWAP_441_REFERENCE,
                  'changedInputsRequiringNewTests': scoped_changed,
                  'unchangedInputCount': len(scoped_unchanged),
                  'unchangedInputsSha256': sha(json.dumps(scoped_unchanged, sort_keys=True).encode()),
                  'evidence': [] if args.offline else verify_neoswap_evidence(),
                  'onlineSuccessVerified': not args.offline}
    run = None
    if not args.offline:
        run = json.loads(subprocess.check_output(['gh', 'api', f'repos/TarbleFR/neostation-ios/actions/runs/{REFERENCE_RUN}']))
        if run['head_sha'] != REFERENCE or run['conclusion'] != 'success' or run['path'] != '.github/workflows/neoswap-ipa.yml':
            raise ValueError('Historical complete build was not successful at the exact reference')
        jobs = json.loads(subprocess.check_output(['gh', 'api', f'repos/TarbleFR/neostation-ios/actions/runs/{REFERENCE_RUN}/jobs']))['jobs']
        build = next(j for j in jobs if 'private IPA' in j['name'])
        if build['conclusion'] != 'success' or any(s['conclusion'] != 'success' for s in build['steps']):
            raise ValueError('Historical build contains failed or skipped checks')
        receiver_run = json.loads(subprocess.check_output(['gh', 'api', f'repos/TarbleFR/neostation-ios/actions/runs/{RECEIVER_RUN}']))
        if (receiver_run['head_sha'] != RECEIVER_REFERENCE or receiver_run['conclusion'] != 'success'
                or receiver_run['path'] != '.github/workflows/retroarch-source-proof.yml'):
            raise ValueError('Pinned receiver validation was not successful')
    report = {'scope': args.scope, 'build440Reuse': scoped, 'referenceSHA': REFERENCE, 'referenceRun': REFERENCE_RUN,
              'onlineSuccessVerified': run is not None,
              'receiverReferenceSHA': RECEIVER_REFERENCE, 'receiverReferenceRun': RECEIVER_RUN,
              'reviewedInputReferences': DELIVERY456_PINNED_INPUTS,
              'privateDeliveryRecipient': {'path': DELIVERY456_RECIPIENT_PATH,
                                          'sha256': DELIVERY456_RECIPIENT_SHA256},
              'unchangedInputCount': len(unchanged),
              'unchangedInputsSha256': sha(json.dumps(unchanged, sort_keys=True).encode()),
              'changedInputsRequiringNewTests': changed,
              'deviceGameplayValidated': False}
    out = ROOT / args.output
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))

if __name__ == '__main__':
    main()
