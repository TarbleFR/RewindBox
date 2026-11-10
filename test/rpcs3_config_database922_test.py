#!/usr/bin/env python3
"""REWINDBOX_CONFIG_DATABASE_RULE_922, executed: the RPCS3 database config wins over a legacy full custom config.

Maintainer's rule (10 Nov): every game uses the RPCS3 database (api.rpcs3.net/config, bundled as
assets/data/rpcs3_ios_profiles.json), the applied settings are compared with it and a setting that disagrees is corrected.
God of War III (build 723, PID 48627) boots on a full custom file written by an earlier build (CONFIG_LAYERS legacy_custom=1)
whose own values outranked the database (inherit_database: a value the file changed stays). The driver compiles the real
rpcs3/ios/RPCS3IOSConfigInheritance.h with RPCS3's yaml-cpp and yaml_load copied from rpcs3/util/yaml.cpp, and checks
apply_database on the God of War III database entry of the shipped profile file: a file value that disagrees with the
database is corrected (and reported with its path), one that agrees is left, a setting the database does not name (the
resolution) keeps the file's value, nested sections and malformed documents behave; inherit_database keeps its old answer
(the control). Static: the loader calls apply_database for a legacy file and reports CONFIG_DB922.

    python3 test/rpcs3_config_database922_test.py --source CORE --yaml-cpp YAML_CPP_DIR [--cxx g++]
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]

HARNESS = r'''
#include <cstdio>
#include <string>
@INCLUDES@
using namespace rpcs3::ios::config_inheritance;
static int failures = 0, checks = 0;
static void check(bool ok, const char* what) { checks++; if (!ok) { failures++; std::printf("FAILED: %s\n", what); } }
static const std::string kDb = R"rbx(@DB@)rbx";
static const std::string kGlobal = "Video:\n  Vulkan:\n    Asynchronous Texture Streaming: false\n  Shader Precision: High\n  Write Color Buffers: false\n  Resolution Scale: 100\n  Multithreaded RSX: false\nCore:\n  SPU Block Size: Safe\n";
int main()
{
	// The God of War III file of build 723: async off (global), precision Ultra, WCB on, 75 %, MT RSX on, SPU Giga.
	const std::string file = "Video:\n  Vulkan:\n    Asynchronous Texture Streaming: false\n  Shader Precision: Ultra\n  Write Color Buffers: true\n  Resolution Scale: 75\n  Multithreaded RSX: true\nCore:\n  SPU Block Size: Giga\n";
	const auto r = apply_database(kDb, file, kGlobal);
	check(r.ok, "the documents parse");
	check(r.corrected == 1 && r.corrections == "Core/SPU Block Size:Giga->Mega", "the file's SPU Block Size that disagrees is corrected and reported");
	check(r.inherited == 1, "a database setting the file left at the global value is applied");
	check(r.agreed == 2, "settings that already agree are left alone");
	check(r.yaml.find("SPU Block Size: Mega") != std::string::npos && r.yaml.find("Asynchronous Texture Streaming: true") != std::string::npos, "both are in the applied document");
	check(r.yaml.find("Resolution Scale") == std::string::npos && r.yaml.find("Multithreaded RSX") == std::string::npos, "settings the database does not name keep the file's value");
	const auto old = inherit_database(kDb, file, kGlobal);
	check(old.ok && old.kept == 3 && old.yaml.find("SPU Block Size") == std::string::npos, "control: the old rule kept the three file values, the disagreeing one included");
	const auto same = apply_database(kDb, kDb, kGlobal);
	check(same.ok && same.corrected == 0 && same.inherited == 0 && same.yaml.empty(), "a file equal to the database changes nothing");
	check(!apply_database("Core: [", file, kGlobal).ok && !apply_database("just a scalar", file, kGlobal).ok, "malformed database refused");
	std::printf("{\"checks\": %d, \"failures\": %d}\n", checks, failures);
	return failures != 0;
}
'''


def require(condition, message):
    if not condition:
        raise SystemExit('FAIL: ' + message)


def braced(text, start):
    a = text.index(start)
    b = text.index('{', a) + 1
    depth = 1
    while depth:
        depth += {'{': 1, '}': -1}.get(text[b], 0)
        b += 1
    return text[a:b]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--yaml-cpp', type=Path)
    parser.add_argument('--cxx', default='g++')
    parser.add_argument('--no-sanitizers', action='store_true')
    parser.add_argument('--report', type=Path)
    args = parser.parse_args()
    source = args.source.resolve()
    yaml_dir = (args.yaml_cpp or source / '3rdparty/yaml-cpp/yaml-cpp').resolve()
    require((yaml_dir / 'include/yaml-cpp/yaml.h').exists(), 'yaml-cpp not found: ' + str(yaml_dir))
    system = (source / 'rpcs3/Emu/System.cpp').read_text('utf-8', 'surrogateescape')
    require('rpcs3::ios::config_inheritance::apply_database(*m_db_config, ios_full_config, ios_global_config)' in system, 'the loader applies the database rule')
    require('CONFIG_DB922' in system, 'the loader reports the corrections')
    require('CONFIG_DB922 title=%s legacy_custom_ignored=1 path=%s' in system and
            system.index('legacy_custom_ignored=1') < system.index('sys_log.notice("Applying custom config: %s", config_path);'),
            'a legacy full custom config is no longer applied')
    require('resolve_mode(g_cfg.ios_experimental.gow3_mlaa_bypass, is_god_of_war_iii_title(title_id))' in
            (source / 'rpcs3/ios/RPCS3IOSExperimentalPolicy.cpp').read_text('utf-8', 'surrogateescape'), 'the MLAA bypass is on by default for God of War III')
    require('if (!ios_has_legacy_custom_config && !m_title_id.empty())' not in system and
            'REWINDBOX_CONFIG_DATABASE_RULE_922: also after a legacy full custom config' in system, 'the user sparse overrides apply after a legacy file')
    profiles = json.loads((ROOT / 'assets/data/rpcs3_ios_profiles.json').read_text())
    require(profiles.get('source_url') == 'https://api.rpcs3.net/config/?api=v1', 'the profile file is the RPCS3 database')
    db = profiles['games']['BCES00510']['config']
    yaml_load = braced((source / 'rpcs3/util/yaml.cpp').read_text(), 'std::pair<YAML::Node, std::string> yaml_load(const std::string& from)')
    includes = '#include <cstdint>\nusing u64 = std::uint64_t;\n#define RPCS3_IOS 1\n#include "ios/RPCS3IOSConfigInheritance.h"\n' + yaml_load
    code = HARNESS.replace('@INCLUDES@', includes).replace('@DB@', db)
    with tempfile.TemporaryDirectory(prefix='db922-') as temporary:
        work = Path(temporary)
        (work / 'h.cpp').write_text(code)
        sanitize = not args.no_sanitizers and Path(args.cxx).name.startswith('g++') and sys.platform.startswith('linux')
        flags = ['-O1', '-g', '-fsanitize=address,undefined'] if sanitize else ['-O1']
        objects = []
        for index, unit in enumerate(sorted((yaml_dir / 'src').rglob('*.cpp'))):
            obj = work / f'y{index}.o'
            subprocess.run([args.cxx, '-std=c++20', '-w', *flags, '-c', '-I', str(yaml_dir / 'include'), str(unit), '-o', str(obj)], check=True)
            objects.append(str(obj))
        build = subprocess.run([args.cxx, '-std=c++20', '-Wall', '-Wextra', *flags, '-I', str(source / 'rpcs3'), '-isystem', str(yaml_dir / 'include'),
                                str(work / 'h.cpp'), *objects, '-o', str(work / 'h')], capture_output=True, text=True)
        require(build.returncode == 0, 'harness does not build:\n' + build.stderr[-3000:])
        run = subprocess.run([str(work / 'h')], capture_output=True, text=True, timeout=120)
        require(run.returncode == 0 and run.stdout.strip().endswith('"failures": 0}'), run.stdout[-2000:])
    result = run.stdout.strip().splitlines()[-1]
    if args.report:
        args.report.write_text(json.dumps({'passed': True, 'result': result}) + '\n')
    print('PASS: RPCS3 database rule over legacy custom configs (%s)' % result)
    return 0


if __name__ == '__main__':
    sys.exit(main())
