#!/usr/bin/env python3
"""REWINDBOX_RETIRED_OVERRIDES_906: a retired game setting left in a title's sparse
override file no longer drops every user value of the title nor refuses every
later change.

Device input (IPA 676, 7 Nov, private logs): Black Ops II (BLES01717) kept
`experimental.thread_orchestrator: Enabled` from a Core 665 test; Core 668 removed
that setting. apply_game_setting_overrides() then failed for the whole file:
CONFIG_LAYERS sparse_overrides=0 at every boot, and rpcs3_ios_set_game_setting
returned RPCS3_IOS_SETTINGS_SAVE_FAILED (21) for the Metal 4 switch
("experimental.metal_renderer=Enabled test=1 refused=21").

Executed against the real bodies extracted from rpcs3/ios/RPCS3IOSSettings.cpp
(retired key table, apply_game_setting_overrides, save_game_setting_override),
compiled with explicit storage and catalogue stubs:
  1. a file holding a retired key and a valid key applies the valid key and succeeds;
  2. an unknown (not retired) key or an invalid value still fails the file;
  3. saving a new value rewrites the file without the retired key and keeps the others;
  4. the retired key is reported (one warning per skipped entry).
Static: System.cpp's sparse-override call is unchanged.

    python3 test/rpcs3_retired_overrides906_test.py --source CORE [--cxx g++] [--report OUT.json]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile


def require(condition, message):
    if not condition:
        raise SystemExit(f'FAIL: {message}')


def extract(text: str, start: str) -> str:
    begin = text.find(start)
    require(begin >= 0, f'missing {start!r}')
    brace = text.find('{', begin + len(start) - 1)
    depth = 0
    for index in range(brace, len(text)):
        if text[index] == '{':
            depth += 1
        elif text[index] == '}':
            depth -= 1
            if depth == 0:
                end = index + 1
                if text[end:end + 1] == ';':
                    end += 1
                return text[begin:end]
    raise SystemExit(f'FAIL: unbalanced {start!r}')


STUBS = r'''
#include <algorithm>
#include <array>
#include <cstdio>
#include <map>
#include <optional>
#include <string>
#include <string_view>
#include <utility>
#include <vector>

static int g_warnings = 0, g_errors = 0;
struct log_stub
{
	template <typename... A> void warning(const char*, const A&...) { ++g_warnings; }
	template <typename... A> void error(const char*, const A&...) { ++g_errors; }
} ios_overrides_log;

struct entry_stub
{
	std::string value;
	bool from_string(std::string_view v) { if (v != "Enabled" && v != "Disabled" && v != "true" && v != "false") return false; value = std::string{v}; return true; }
};
struct cfg_stub { struct { entry_stub precise_zpass_count, relaxed_zcull_sync; } video; } g_cfg;

enum class setting_context { game };
struct setting_record { entry_stub* entry; };
static std::map<std::string, entry_stub> g_entries{{"experimental.metal_renderer", {}}, {"advanced.disable_msl_fast_math", {}}};
static std::map<std::string, setting_record> g_records;
const setting_record* find_setting(std::string_view key, setting_context)
{
	auto found = g_entries.find(std::string{key});
	if (found == g_entries.end()) return nullptr;
	g_records[found->first] = setting_record{&found->second};
	return &g_records[found->first];
}
struct zcull_state { bool precise, relaxed; };
std::optional<zcull_state> parse_zcull_accuracy(std::string_view) { return std::nullopt; }

static std::vector<std::pair<std::string, std::string>> g_file;
static bool g_written = false;
bool read_game_setting_overrides(std::string_view, std::vector<std::pair<std::string, std::string>>& values) { values = g_file; return true; }
bool write_game_setting_overrides(std::string_view, const std::vector<std::pair<std::string, std::string>>& values) { g_file = values; g_written = true; return true; }
'''

DRIVER = r'''
#define CHECK(c) do { if (!(c)) { std::printf("FAIL line %d: %s\n", __LINE__, #c); return 1; } } while (0)
static bool has(std::string_view key) { return std::ranges::any_of(g_file, [&](const auto& i) { return i.first == key; }); }
int main()
{
	using namespace std::string_literals;
	// 1. The BO2 file: retired orchestrator value plus a real user value.
	g_file = {{"experimental.thread_orchestrator"s, "Enabled"s}, {"advanced.disable_msl_fast_math"s, "true"s}};
	CHECK(apply_game_setting_overrides("BLES01717"));
	CHECK(g_entries["advanced.disable_msl_fast_math"].value == "true");
	CHECK(g_warnings == 1 && g_errors == 0);
	// 3. Saving the Metal switch writes it and leaves the retired key out.
	CHECK(save_game_setting_override("BLES01717", "experimental.metal_renderer", "Enabled"));
	CHECK(g_written && !has("experimental.thread_orchestrator") && has("advanced.disable_msl_fast_math") && has("experimental.metal_renderer"));
	g_warnings = 0;
	CHECK(apply_game_setting_overrides("BLES01717"));
	CHECK(g_entries["experimental.metal_renderer"].value == "Enabled" && g_warnings == 0);
	// 2. Unknown and invalid entries keep failing the file.
	g_file = {{"experimental.not_a_setting"s, "Enabled"s}};
	CHECK(!apply_game_setting_overrides("BLES01717") && g_errors == 1);
	g_file = {{"experimental.metal_renderer"s, "Sideways"s}};
	CHECK(!apply_game_setting_overrides("BLES01717") && g_errors == 2);
	g_file = {{"gpu.zcull_accuracy"s, "nonsense"s}};
	CHECK(!apply_game_setting_overrides("BLES01717") && g_errors == 3);
	// A retired key is never accepted as a new value.
	CHECK(!save_game_setting_override("BLES01717", "experimental.thread_orchestrator", "Enabled"));
	std::printf("PASS: retired override keys skipped, pruned on save; unknown and invalid entries still fail\n");
	return 0;
}
'''


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--source', required=True, type=Path)
    parser.add_argument('--cxx', default=os.environ.get('CXX') or shutil.which('g++') or shutil.which('clang++'))
    parser.add_argument('--report', type=Path)
    args = parser.parse_args()

    settings = (args.source / 'rpcs3/ios/RPCS3IOSSettings.cpp').read_text()
    system = (args.source / 'rpcs3/Emu/System.cpp').read_text()
    require('REWINDBOX_RETIRED_OVERRIDES_906' in settings, 'marker missing in RPCS3IOSSettings.cpp')
    require('if (!rpcs3::ios::apply_game_setting_overrides(m_title_id))' in system,
            'System.cpp sparse-override call changed')
    require('"experimental.thread_orchestrator"' not in settings.split('const std::array catalog{', 1)[1].split('};', 1)[0],
            'the retired key is back in the catalogue')

    bodies = [
        extract(settings, 'constexpr std::array<std::string_view, 1> retired_game_setting_keys{'),
        extract(settings, 'bool is_retired_game_setting_key(std::string_view key) noexcept\n{'),
        extract(settings, 'bool apply_game_setting_overrides(std::string_view title_id) noexcept\n{'),
        extract(settings, 'bool save_game_setting_override(\n\tstd::string_view title_id,'),
    ]
    with tempfile.TemporaryDirectory() as work:
        unit = Path(work) / 'retired906.cpp'
        unit.write_text(STUBS + '\n'.join(bodies) + DRIVER)
        binary = Path(work) / 'retired906'
        subprocess.run([args.cxx, '-std=c++20', '-Wall', '-Werror', '-Wno-unused-function', str(unit), '-o', str(binary)], check=True)
        result = subprocess.run([str(binary)], capture_output=True, text=True)
        sys.stdout.write(result.stdout)
        require(result.returncode == 0, 'executed check failed')
    report = {'result': 'passed', 'compiler': args.cxx,
              'extracted_bodies_sha256': hashlib.sha256('\n'.join(bodies).encode()).hexdigest()}
    if args.report:
        args.report.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
