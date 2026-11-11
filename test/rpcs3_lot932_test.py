#!/usr/bin/env python3
"""Host test of RPCS3 Core 932 (maintainer, 11 Nov 2026: the ARMSX3 lot, « intègre tout ce qui peut être utile », « Je ne
veux pas de plafonds de FPS », and the urgent audit of the same day: thermal evidence, shared corrections, variants).

Source and data checks on the Core tree (--source), and a harness built from the Core's own headers and functions:
- REWINDBOX_CANARY_PATCHES_932: the embedded ARMSX3 file is byte for byte the recorded one (SHA-256), parses as patch
  engine 1.2 with the engine's own rules (raw scalars, serials, versions, patch types), the default list is the file
  minus the seven entries left off (the official Killzone 3 MLAA entries stay off), no entry tied to a frame limit is on;
  the engine loads it third, keeps the user's saved choice, saves a turned-off fix as Enabled: false, and the iOS list
  loads it in the same order;
- REWINDBOX_PATCH_RELIEF_932: the decision table, the rules' patches exist in the file, and the database entries hold
  the settings the rules relieve (GT6: both color buffers; GTA IV: XFloat Accurate);
- REWINDBOX_TITLE_VARIANTS_932: the six Black Ops II serials share the database entry of BLES01717;
- REWINDBOX_ENERGY_VALIDITY_932, REWINDBOX_DISK_IO_932, REWINDBOX_THERMAL_LEDGER_932, REWINDBOX_EVENT_WAIT_LATENCY_932,
  REWINDBOX_BACKGROUND_PAUSE_TRANSITION_932, REWINDBOX_PREHASH_THERMAL_932, REWINDBOX_JIT_STEP_932 (the real
  reserve_capacity_layout against the previous 64 MiB step on 1,035 gap and capacity cases), REWINDBOX_METAL_CONCURRENT_
  COMPILATION_932;
- the analyzer's thermal comparison at equal conditions (mixed windows and invalid energy left out, strata of the other
  levers, order of the trials).
Controls, always run: eight mutations (a counter that goes back printed as 0, a mixed window not flagged, the user's
choice ignored by the relief, no thermal reduction of the speculative hashing, the 64 MiB step, a transition pause
asked in the foreground, the bundled fixes not loaded, a turned-off fix not saved) must each be caught.
Not an iPhone: energy, heat, wake latency and frame rate are read from the device journals."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
HARNESS = ROOT / 'test/rpcs3_lot932/harness.cpp'
CANARY_SHA256 = '1955e1d860c5d416a1b8889d54aa78b984c0ba38436fbc47c3081d5191d77376'
HEADERS = ('IOSEnergy931.h', 'IOSThermalPolicy931.h', 'IOSEventWait931.h', 'IOSBackgroundPause931.h', 'IOSTexturePrehash.h',
           'IOSPatchRelief932.h', 'IOSCanaryPatches932.h', 'IOSShardedCounter931.h', 'IOSWriterParkSpin917.h')
FILES = ('Utilities/bin_patch.cpp', 'Utilities/bin_patch.h', 'Utilities/JITIOS.cpp', 'Utilities/JITIOSLayoutPolicy.h', 'rpcs3/Emu/System.cpp',
         'rpcs3/ios/RPCS3IOSRuntimePatches.cpp', 'rpcs3/ios/RPCS3IOSPerformance.cpp', 'rpcs3/ios/RPCS3IOSPlatform.mm',
         'rpcs3/ios/IOSTitleLevers.h', 'rpcs3/ios/IOSCanaryPatches932.h', 'rpcs3/Emu/RSX/VK/vkutils/instance.cpp',
         'rpcs3/Emu/RSX/Common/texture_cache.cpp', 'rpcs3/ios/IOSEventWait931.h', 'rpcs3/Emu/Memory/vm.cpp', 'rpcs3/Emu/RSX/RSXFIFO.cpp')
OFF = {('PPU-602e58994456e14dfd80a6e0f376729b53c3109a', 'Private matches start with fewer players'),
       ('PPU-3e9032a3f7857057ef783810bd8f34a439baaa59', 'Field at 30 fps with a 60 fps limit')}
# The two official Killzone 3 MLAA entries ARMSX3 turns on stay at the database default (off): no documented failure.
KILLZONE3 = {('PPU-ae204e2198c9a051a44a69913c48f6591b811082', 'Disable MLAA(Post-processing On SPU)'),
             ('PPU-4836b8e74c47919f50b030ee6b47d96bc7305387', 'Disable MLAA (Post-processing on SPU)')}
BO2 = ('BLES01717', 'BLES01718', 'BLES01719', 'BLES01720', 'BLUS31011', 'BLUS31140')
PATCH_TYPES = {'be32', 'be16', 'byte', 'bef32', 'calloc', 'jump', 'jumpf', 'jumpl'}


def read(source: Path, rel: str) -> str:
    return (source / rel).read_text(encoding='utf-8', errors='replace')


def embedded_yaml(header: str) -> str:
    start = header.index('R"RBCANARY932(') + len('R"RBCANARY932(')
    return header[start:header.index(')RBCANARY932"', start)]


def table(header: str, name: str) -> list[tuple[str, str]]:
    body = header[header.index(f'inline constexpr entry {name}[] = {{'):]
    body = body[:body.index('};')]
    return re.findall(r'\{"([^"]+)", "([^"]+)"\}', body)


def canary_errors(header: str) -> list[str]:
    errors = []
    text = embedded_yaml(header)
    raw = text.encode('ascii')
    if hashlib.sha256(raw).hexdigest() != CANARY_SHA256:
        errors.append('canary: the embedded file is not the recorded ARMSX3 21863 file')
    if f'yaml_sha256 = "{CANARY_SHA256}"' not in header or f'yaml_bytes = {len(raw)};' not in header:
        errors.append('canary: recorded identity constants differ')
    root = yaml.compose(text)  # raw scalars, as yaml-cpp's Scalar() reads them
    entries = []
    for key, value in root.value:
        if key.value == 'Version':
            if value.value != '1.2':
                errors.append('canary: not patch engine 1.2')
            continue
        if not re.fullmatch(r'(PPU|SPU)-[0-9a-f]{40}', key.value):
            errors.append('canary: bad hash key ' + key.value)
        for description, patch in value.value:
            entries.append((key.value, description.value))
            fields = {k.value: v for k, v in patch.value}
            games = fields.get('Games')
            if games is None or not isinstance(games, yaml.MappingNode):
                errors.append(f'canary: {description.value}: no Games map')
                continue
            for title, serials in games.value:
                for serial, versions in serials.value:
                    if not re.fullmatch(r'[A-Z0-9]{9}', serial.value):
                        errors.append(f'canary: {description.value}: serial {serial.value}')
                    for version in versions.value:
                        if version.value != 'All' and not re.fullmatch(r'[0-9]{2}\.[0-9]{2}', version.value):
                            errors.append(f'canary: {description.value}: version {version.value}')
            for item in fields['Patch'].value:
                kind = item.value[0].value
                if kind not in PATCH_TYPES:
                    errors.append(f'canary: {description.value}: patch type {kind}')
    on, left = set(table(header, 'default_on_entries')), set(table(header, 'left_off_entries'))
    expected_left = OFF | {e for e in entries if e[0] == 'PPU-5af0f0d7824157a0aace48f5d0b06f6efe02fe4e'}
    if left != expected_left or len(left) != 7:
        errors.append('canary: the entries left off are not the seven of the record')
    if on != set(entries) - expected_left or len(on) != 42 or on & KILLZONE3:
        errors.append('canary: the default list is not the file minus the seven entries left off')
    if any(re.search(r'fps|frame limit', d, re.I) for _, d in on):
        errors.append('canary: an entry tied to a frame limit is on by default')
    return errors


def source_errors(texts: dict[str, str]) -> list[str]:
    errors: list[str] = []
    patch = texts['Utilities/bin_patch.cpp']
    glob = patch[patch.index('void patch_engine::append_global_patches()'):patch.index('void patch_engine::append_title_patches(')]
    if glob.find('load(m_map, get_imported_patch_path());') > glob.find(
            'load(m_map, std::string{rpcs3::ios::canary932::source_name}, std::string{rpcs3::ios::canary932::yaml});') or \
            'canary932::yaml' not in glob:
        errors.append('engine: the bundled fixes are not loaded after the two global files')
    if 'app_versions[app_version] = canary932_config_values(patch_config, importing, main_key, description, title, serial, app_version);' not in patch:
        errors.append('engine: the configuration lookup does not use the saved choice and the default')
    helper = patch[patch.index('static patch_engine::patch_config_values canary932_config_values('):]
    helper = helper[:helper.index('\n}\n')]
    if 'patch_config[' in helper or '.find(' not in helper or 'values.enabled = !importing && rpcs3::ios::canary932::default_on(main_key, description);' not in helper:
        errors.append('engine: the lookup inserts entries or the default is not the bundled list')
    save = patch[patch.index('bool patch_engine::save_config(const patch_map& patches_map)'):patch.index('static void append_patches(')]
    if save.count('config_values.enabled != default_enabled || config_values_dirty') != 2 or \
            'if (config_values.enabled || default_enabled)\n\t\t\t\t\t\t\t\t{\n\t\t\t\t\t\t\t\t\tout << patch_key::enabled << config_values.enabled;' not in save:
        errors.append('engine: a turned-off bundled fix is not saved with Enabled: false')
    if 'relief::is_gt6_mlaa_patch(patch->hash, patch->description) && relief::boot_state::instance().armed()' not in patch or \
            'const bool complete = applied_total.size() - old_size == patch->data_list.size();' not in patch:
        errors.append('engine: GT6 relief missing or not tied to a complete application')
    if 'backup.set(false);' not in patch or 'g_backup_cfg.core.spu_xfloat_accuracy.set(xfloat_accuracy::approximate);' not in texts['rpcs3/Emu/System.cpp']:
        errors.append('relief: the boot backup does not follow (the home menu would restore the database value)')
    if 'bool is_enabled(std::string_view hash, std::string_view description, std::string_view serial, std::string_view app_version) const;' not in texts['Utilities/bin_patch.h']:
        errors.append('engine: is_enabled not declared')
    runtime = texts['rpcs3/ios/RPCS3IOSRuntimePatches.cpp']
    if 'if (index == 1)' not in runtime or 'patch_engine::load(patches, std::string{canary932::source_name}, std::string{canary932::yaml}, false, &canary_messages)' not in runtime:
        errors.append('runtime list: the bundled fixes are not in the map that save_config writes')
    system = texts['rpcs3/Emu/System.cpp']
    for needle, what in (('const bool ios_global_wcb = g_cfg.video.write_color_buffers.get();', 'global values before the database'),
                         ('relief::boot_state::instance().begin(!m_ar, ios_config_path_applied, !m_title_id.empty() && ios_overrides_read && keys_known, origins);', 'boot state'),
                         ('g_fxo->get<patch_engine>().is_enabled(relief::gta4_hash, relief::gta4_description, m_title_id, m_app_version)', 'GTA IV rule'),
                         ('rpcs3::ios::patch_relief932::boot_state::instance().end_loading();', 'end of the loading phase'),
                         ('rpcs3::ios::background_pause::on_emulation_running();', 'transition pause')):
        if needle not in system:
            errors.append('System.cpp: ' + what)
    begin_at = system.find('relief::boot_state::instance().begin(')
    overrides_at = system.find('if (!rpcs3::ios::apply_game_setting_overrides(m_title_id))')
    patches_at = system.find('g_fxo->get<patch_engine>().append_title_patches(m_title_id);')
    gta_at = system.find('relief::is_gta4_serial(m_title_id)')
    exec_at = system.find('const bool loaded_ppu = ppu_load_exec(ppu_exec, false, m_path, DeserialManager());')
    if not (0 <= overrides_at < begin_at < patches_at < gta_at < exec_at):
        errors.append('System.cpp: order (user layer, origins, patches, boot rule, executable)')
    levers = texts['rpcs3/ios/IOSTitleLevers.h']
    body = levers[levers.index('constexpr bool is_black_ops_ii_title(std::string_view title_id) noexcept'):]
    body = body[:body.index('}')]
    if sorted(re.findall(r'"([A-Z0-9]{9})"', body)) != sorted(BO2):
        errors.append('levers: Black Ops II serials are not the six of the compatibility list')
    if 'capacity = std::max(arena_min_capacity, capacity - arena_capacity_step / 4);' not in texts['Utilities/JITIOS.cpp']:
        errors.append('JIT: 16 MiB step missing')
    if '"MVK_CONFIG_SHOULD_MAXIMIZE_CONCURRENT_COMPILATION", VK_LAYER_SETTING_TYPE_BOOL32_EXT, 1, &setting_true' not in texts['rpcs3/Emu/RSX/VK/vkutils/instance.cpp']:
        errors.append('MoltenVK: concurrent compilation not asked')
    cache = texts['rpcs3/Emu/RSX/Common/texture_cache.cpp']
    if 'g_lookahead = next_lookahead(g_lookahead, hashes_now - g_frame_worker_hashes, hits_now - g_frame_hits);\n\t\t\t// REWINDBOX_PREHASH_THERMAL_932' not in cache or \
            'g_lookahead = thermal_lookahead(g_lookahead, depth_before, hashes_now - g_frame_worker_hashes, hits_now - g_frame_hits,' not in cache:
        errors.append('prehash: the thermal bound does not follow the usage rule')
    perf = texts['rpcs3/ios/RPCS3IOSPerformance.cpp']
    for needle in ('sample.disk_write_bytes = usage.ri_diskio_byteswritten;', 'sample.logical_write_bytes = usage.ri_logical_writes;',
                   'window_state_begin=%s window_changes=%llu', 'window_mixed=%s event_waits_window=%s', 'wfe_latency_us=%llu:%llu:%llu:%llu:%llu',
                   'background_transition_requests=%llu', 'const thermal::ledger_snapshot ledger_now = thermal::state_ledger.snapshot(thermal::steady_now_ns());'):
        if needle not in perf:
            errors.append('report: ' + needle[:60])
    if 'state::instance().ask_on_running([] { request_pause(); });' not in texts['rpcs3/ios/RPCS3IOSPlatform.mm']:
        errors.append('platform: the transition does not ask through the state')
    for rel in ('rpcs3/Emu/Memory/vm.cpp', 'rpcs3/Emu/RSX/RSXFIFO.cpp'):
        if 'within about 1 us' in texts[rel]:
            errors.append(rel + ': a WFE latency is still stated as a fact')
    return errors


def database_errors(header: str) -> list[str]:
    """The premises of the relief rules and of the variants, read in the database the Core receives."""
    errors = []
    games = json.loads((ROOT / 'assets/data/rpcs3_ios_profiles.json').read_text())['games']
    root = yaml.safe_load(embedded_yaml(header).replace('\t', '  '))
    gt6_serials = set()
    for hash_, patches in root.items():
        if not isinstance(patches, dict):
            continue
        for description, patch in patches.items():
            if description == 'Disable MLAA' and any('Gran Turismo 6' in t for t in patch['Games']):
                for serials in patch['Games'].values():
                    gt6_serials |= set(serials)
                # apply_modification records one applied entry per be32 write: the relief's completeness test
                # (applied == data_list.size()) holds only for plain writes.
                if not patch['Patch'] or any(entry[0] != 'be32' for entry in patch['Patch']):
                    errors.append(f'relief: {hash_} Disable MLAA is not made of be32 writes only')
    if len(gt6_serials) < 7:
        errors.append('relief: the GT6 serials of the file are not found')
    for serial in sorted(gt6_serials):
        config = (games.get(serial) or {}).get('config', '')
        if 'Write Color Buffers: true' not in config or 'Read Color Buffers: true' not in config:
            errors.append(f'relief: the database does not turn both color buffers on for {serial}')
    gta = root['SPU-d0a1508208613e2184fbd64906d34d5f07890033']['ARMSX3 Approximate collision fix']['Games']
    gta_serials = {s for serials in gta.values() for s in serials}
    if gta_serials != {'BLUS30682', 'BLUS30127', 'NPUB30702'}:
        errors.append('relief: GTA IV serials differ from the rule')
    for serial in sorted(gta_serials):
        if 'SPU XFloat Accuracy: Accurate' not in (games.get(serial) or {}).get('config', ''):
            errors.append(f'relief: the database does not pin {serial} to Accurate')
    reference = games['BLES01717']
    for serial in BO2:
        if games.get(serial) != reference:
            errors.append(f'variants: {serial} does not share the database entry of BLES01717')
    return errors



def jit_include(source: Path, work: Path, step_text: str | None = None) -> None:
    policy = read(source, 'Utilities/JITIOSLayoutPolicy.h')
    jit = read(source, 'Utilities/JITIOS.cpp')
    constants = []
    for name in ('mib', 'arena_min_capacity', 'arena_default_capacity', 'arena_standard_max_capacity', 'arena_max_capacity', 'arena_capacity_step'):
        match = re.search(rf'^inline constexpr usz {name} = [^;]+;', policy, re.M)
        constants.append(match.group(0))
    start = jit.index('u8* reserve_capacity_layout(usz& capacity, bool expanded, u8*& data, usz& data_capacity) noexcept')
    depth, cursor = 0, jit.index('{', start)
    while True:
        depth += {'{': 1, '}': -1}.get(jit[cursor], 0)
        cursor += 1
        if depth == 0:
            break
    function = jit[start:cursor]
    new_line = 'capacity = std::max(arena_min_capacity, capacity - arena_capacity_step / 4);'
    old_line = 'capacity = std::max(arena_min_capacity, capacity - arena_capacity_step);'
    variants = {'jit_step_new': function if step_text is None else function.replace(new_line, step_text),
                'jit_step_old': function.replace(new_line, old_line)}
    parts = ['#include <algorithm>\n#include <cstddef>\n#include <cstdint>\n#include <string>\n#include <utility>\n']
    for name, body in variants.items():
        parts.append(f'''namespace {name}
{{
using u8 = std::uint8_t;
using usz = std::size_t;
namespace rpcs3::ios::jit
{{
{chr(10).join(constants)}
}}
inline usz g_gap = 0;
inline void emit_diagnostic(const std::string&) {{}}
inline u8* reserve_code_data_layout(usz code_capacity, u8*& data, usz& data_capacity) noexcept
{{
	if (code_capacity <= g_gap)
	{{
		data = reinterpret_cast<u8*>(0x200000000ull);
		data_capacity = code_capacity;
		return reinterpret_cast<u8*>(0x100000000ull);
	}}
	data = nullptr;
	data_capacity = 0;
	return nullptr;
}}
{body}
inline std::pair<bool, usz> run(usz initial, usz gap, bool expanded)
{{
	g_gap = gap;
	usz capacity = initial, data_capacity = 0;
	u8* data = nullptr;
	const bool ok = reserve_capacity_layout(capacity, expanded, data, data_capacity) != nullptr;
	return {{ok, capacity}};
}}
}}
''')
    (work / 'jit_step_under_test.inc').write_text('\n'.join(parts))


def build_and_run(cxx: str, includes: list[Path], work: Path, name: str, sanitize: bool) -> tuple[int, str]:
    binary = work / name
    flags = ['-std=c++20', '-O1', '-g', '-Wall', '-Wextra', '-pthread']
    if sanitize:
        flags += ['-fsanitize=address,undefined', '-fno-omit-frame-pointer']
    args = [cxx, *flags]
    for include in includes:
        args += ['-I', str(include)]
    build = subprocess.run([*args, str(HARNESS), '-o', str(binary)], capture_output=True, text=True)
    if build.returncode:
        return build.returncode, 'BUILD FAILED\n' + build.stderr[-3000:]
    run = subprocess.run([str(binary)], capture_output=True, text=True, timeout=900)
    return run.returncode, run.stdout + run.stderr[-2000:]


HEADER_MUTATIONS = (
    ('a counter that goes back printed as 0', 'IOSEnergy931.h',
     'return now >= before ? difference{now - before, true} : difference{0, false};', 'return difference{now >= before ? now - before : 0, true};'),
    ('a mixed window not flagged', 'IOSThermalPolicy931.h',
     'out.mixed = out.changes != 0 || out.states_with_time() > 1 || out.begin_state != out.end_state;', 'out.mixed = false;'),
    ("the user's choice ignored by the relief", 'IOSPatchRelief932.h',
     '\tif (in.origin.user_key)\n\t{\n\t\treturn refusal::user_choice;\n\t}\n', ''),
    ('no thermal reduction of the speculative hashing', 'IOSTexturePrehash.h',
     'if (thermal_state >= 1 && after == before', 'if (thermal_state >= 9 && after == before'),
    ('a transition pause asked in the foreground', 'IOSBackgroundPause931.h',
     '\t\tif (!background() || ours())\n\t\t{\n\t\t\treturn false;\n\t\t}\n\t\tm_transition_requests', '\t\tif (ours())\n\t\t{\n\t\t\treturn false;\n\t\t}\n\t\tm_transition_requests'),
)


def source_mutations(texts: dict[str, str]) -> list[tuple[str, dict[str, str]]]:
    out = []
    patch = texts['Utilities/bin_patch.cpp']
    loaded = '\tload(m_map, std::string{rpcs3::ios::canary932::source_name}, std::string{rpcs3::ios::canary932::yaml});\n'
    out.append(('the bundled fixes not loaded', dict(texts, **{'Utilities/bin_patch.cpp': patch.replace(loaded, '')})))
    explicit = 'if (config_values.enabled || default_enabled)\n\t\t\t\t\t\t\t\t{\n\t\t\t\t\t\t\t\t\tout << patch_key::enabled'
    out.append(('a turned-off fix not saved', dict(texts, **{'Utilities/bin_patch.cpp': patch.replace(explicit, explicit.replace(' || default_enabled', ''))})))
    return out


ANALYZER_WINDOWS = (
    # window, waits, park_spin, mixed, discontinuities, mj per frame
    (1, 'off', '1', '0', 0, 80.0), (2, 'on', '1', '0', 0, 70.0), (3, 'on', '1', '1', 0, 10.0), (4, 'off', '1', '0', 0, 79.0),
    (5, 'on', '1', '0', 0, 69.0), (6, 'off', '1', '0', 1, 5.0), (7, 'on', '0', '0', 0, 60.0), (8, 'off', '0', '0', 0, 66.0))


def analyzer_errors(work: Path) -> list[str]:
    lines = []
    clock = 1794384000.0

    def line(message: str) -> None:
        nonlocal clock
        clock += 0.001
        lines.append(json.dumps({'build': '932', 'message': 'TID: 1: ' + message, 'timestamp': clock, 'stage': 'core_log', 'pid': 4343}))
    for window, waits, spin, mixed, discontinuities, mj in ANALYZER_WINDOWS:
        clock += 5.0
        line(f'COREPROF FRAMEPROF527 session=2 window={window} wall_guest_fps=30.0 p95_ms=40.0')
        line(f'COREPROF SCHED918 session=2 window={window} task_events=available context_switches=1000 mach_traps=10 unix_syscalls=10 busy_wait_scale=1')
        line(f'COREPROF RANGELOCKPROF session=2 window={window} park_spin={spin} wl_putllc=10:1.0:1.0')
        energy = 'invalid' if discontinuities else f'{mj * 150:.1f}'
        per_frame = 'invalid' if discontinuities else f'{mj:.3f}'
        line(f'COREPROF ENERGY931 session=2 window={window} energy=available frames=150 cpu_energy_mj={energy} p_energy_mj=1.0 mj_per_frame={per_frame} '
             f'cpu_ms=100.0 p_cpu_ms=50.0 p_share=0.500 disk_write_mib=1.25 timer_wakeups_2ms=10 timer_wakeups_5ms=1 discontinuities={discontinuities}')
        line(f'COREPROF THERMAL931 session=2 window={window} thermal_state=serious state_changes=3 event_waits={waits} mode=automatic compared=no '
             f'window_state_begin=serious window_changes={1 if mixed == "1" else 0} window_mixed={mixed} event_waits_window={"mixed" if mixed == "1" else waits}')
    journal = work / 'RPCS3-performance.log'
    journal.write_text('\n'.join(lines) + '\n')
    run = subprocess.run([sys.executable, str(ROOT / 'tools/rpcs3/capture_analyzer.py'), str(journal)], capture_output=True, text=True)
    out = run.stdout
    errors = []
    if run.returncode:
        errors.append('analyzer failed: ' + run.stderr[-800:])
    expectations = (
        (r'left out: 1 mixed window\(s\) .*, 1 with an invalid energy counter', 'mixed and invalid windows counted'),
        (r'other levers park_spin=1 busy_wait_scale=1:\n\s+event_waits=off: windows 2 \(1,4\) fps 30\.00 mj_per_frame 79\.500', 'stratum park_spin=1, off side'),
        (r'event_waits=on: windows 2 \(2,5\) fps 30\.00 mj_per_frame 69\.500 .* disk_write_mib 1\.25\n\s+order: interleaved', 'stratum park_spin=1, on side, interleaved'),
        (r'other levers park_spin=0 busy_wait_scale=1:\n\s+event_waits=off: windows 1 \(8\)', 'stratum park_spin=0'),
        (r'order: every event_waits=on window comes first: not counterbalanced', 'order not counterbalanced flagged'),
        (r'scope: the CPU energy the system attributes to the process, not the battery', 'energy scope stated'),
    )
    for pattern, what in expectations:
        if not re.search(pattern, out):
            errors.append('analyzer: ' + what + '\n' + out[out.find('energy per frame'):][:1800])
    if 'no transition recorded inside a window' in out:
        errors.append('analyzer: a Core 932 journal was treated as one without transitions')
    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--cxx', default='g++')
    parser.add_argument('--no-sanitizers', action='store_true')
    parser.add_argument('--report', type=Path)
    args = parser.parse_args()
    source = args.source.resolve()
    texts = {rel: read(source, rel) for rel in FILES}
    header = texts['rpcs3/ios/IOSCanaryPatches932.h']
    errors = canary_errors(header) + source_errors(texts) + database_errors(header)
    for name, mutated in source_mutations(texts):
        if not source_errors(mutated):
            errors.append('control not caught: ' + name)
    work = Path(tempfile.mkdtemp(prefix='lot932-'))
    result, latency, jit = {}, {}, {}
    try:
        jit_include(source, work)
        code, out = build_and_run(args.cxx, [source / 'rpcs3/ios', work], work, 'harness', not args.no_sanitizers)
        jsons = [json.loads(l) for l in out.splitlines() if l.startswith('{')]
        result = jsons[-1] if jsons else {}
        latency = next((j for j in jsons if 'wfe_measured' in j), {})
        jit = next((j for j in jsons if 'jit_step_cases' in j), {})
        if code or result.get('failures') != 0:
            errors.append('harness: ' + out[-3000:])
        errors.extend(analyzer_errors(work))
        # Header mutations: each must make the harness fail (a build failure counts: a static_assert caught it).
        for index, (name, rel, old, new) in enumerate(HEADER_MUTATIONS):
            mutant = work / f'mutant{index}'
            mutant.mkdir()
            for h in HEADERS:
                shutil.copy(source / 'rpcs3/ios' / h, mutant / h)
            text = (mutant / rel).read_text()
            if text.count(old) != 1:
                errors.append(f'control {name}: mutation site not found')
                continue
            (mutant / rel).write_text(text.replace(old, new))
            mcode, _ = build_and_run(args.cxx, [mutant, work], work, f'harness_m{index}', False)
            if mcode == 0:
                errors.append('control not caught: ' + name)
        # The JIT step reverted: the documented 380 MiB case must fail.
        reverted = work / 'jit_reverted'
        reverted.mkdir()
        jit_include(source, reverted, 'capacity = std::max(arena_min_capacity, capacity - arena_capacity_step);')
        mcode, _ = build_and_run(args.cxx, [source / 'rpcs3/ios', reverted], work, 'harness_jit', False)
        if mcode == 0:
            errors.append('control not caught: the 64 MiB step')
    finally:
        shutil.rmtree(work, ignore_errors=True)
    controls = [m[0] for m in HEADER_MUTATIONS] + ['the 64 MiB step', 'the bundled fixes not loaded', 'a turned-off fix not saved']
    report = {'result': 'failed' if errors else 'passed', 'checks': result.get('checks'), 'eventWaitLatency': latency, 'jit': jit,
              'errors': errors, 'controls': controls, 'physicalDeviceTested': False}
    if args.report:
        args.report.write_text(json.dumps(report, indent=1) + '\n')
    if errors:
        print('\n'.join(errors))
        return 1
    print('PASS: Core 932 lot (%s); the %d controls are caught' % (json.dumps({'checks': result.get('checks'), 'latency': latency, 'jit': jit}), len(controls)))
    return 0


if __name__ == '__main__':
    sys.exit(main())
