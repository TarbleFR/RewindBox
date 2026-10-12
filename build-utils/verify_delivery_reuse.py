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
    'build-utils/verify_delivery_reuse.py',
    'lib/l10n/library_reader_locale.dart',
    'lib/screens/library_screen/reader/library_book_reader_screen.dart',
    'lib/screens/library_screen/reader/library_reader_bookmarks.dart',
    'lib/screens/library_screen/reader/library_reader_effective_settings.dart',
    'lib/screens/library_screen/reader/library_reflow_paginator.dart',
    'lib/services/library_reading_store.dart',
    'test/library_infra_reading_store_test.dart',
    'test/library_reader_effective_settings_test.dart',
    'test/library_reader_locale_test.dart',
    'test/library_reading_store_bookmarks_test.dart',
    'test/library_reflow_paginator_test.dart',
}
DELTA |= BUILD447_BOOKS_DELTA
# Build 447 chantier 5, storage analysis and cleanup (12 October 2026,
# docs/storage-audit-cleanup.md): every created or modified input, file by
# file, added as each phase lands (translation catalog first).
BUILD447_STORAGE_DELTA = {
    'build-utils/verify_delivery_reuse.py',
    'lib/l10n/storage_locale.dart',
    'lib/repositories/storage_maintenance_repository.dart',
    'lib/services/armsx2_internal_service.dart',
    'lib/services/dolphin_internal_v2_service.dart',
    'lib/services/dolphin_smart_import_service.dart',
    'lib/services/dusklight_internal_service.dart',
    'lib/services/kartpad_internal_service.dart',
    'lib/services/libretro_internal_service.dart',
    'lib/services/rpcs3_internal_service.dart',
    'lib/services/rpcs3_save_exchange_service.dart',
    'lib/services/storage/storage_categorizer.dart',
    'lib/services/storage/storage_orphan_detector.dart',
    'lib/services/storage/storage_picker_copies.dart',
    'lib/services/storage/storage_roots.dart',
    'lib/services/storage/storage_scanner.dart',
    'lib/services/storage/storage_stat_ffi.dart',
    'test/localization_12_locale_coverage_test.py',
    'test/storage_categorizer_test.dart',
    'test/storage_contract_test.py',
    'test/storage_locale_test.dart',
    'test/storage_log_rotation_test.dart',
    'test/storage_maintenance_repository_test.dart',
    'test/storage_orphan_detector_test.dart',
    'test/storage_picker_copies_test.dart',
    'test/storage_roots_test.dart',
    'test/storage_scanner_test.dart',
    'test/storage_stat_ffi_test.dart',
}
DELTA |= BUILD447_STORAGE_DELTA
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

def verify_tree():
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

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--offline', action='store_true')
    parser.add_argument('--scope', choices=('full', 'rpcs3_neoswap', 'library_covers'), default='full')
    parser.add_argument('--output', default='build/delivery/reused-validation.json')
    args = parser.parse_args()
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
