#!/usr/bin/env python3
"""Execute the production CELL545 bodies ported from RPCS3 and ARMSX3 against the 543 baseline.

Usage: rpcs3_cell545_test.py <545 Core work tree> [--report out.json]

Every production body is copied verbatim from the 545 Core work tree, and the
543 baseline is reconstructed by reverse-applying the reviewed fixture. Adapters
replace logging, the VFS escape, the RPCS3 file object and the serializer's
writer. The harness runs under ASan+UBSan with libstdc++ assertions. Synthetic
names, programs and files only: no real PKG, SELF, savestate or iPhone.
The debug SELF decryption (RPCS3 b77d4a520, 8dc93f2e0, 4e078e07a) is verified by
the Core build only; this harness checks its SCE key-index bound.
"""
import argparse, hashlib, json, os, re, shlex, subprocess, tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / 'test/fixtures/rpcs3_cell545.diff'
sha = lambda b: hashlib.sha256(b).hexdigest()
MODIFIED = ['rpcs3/Crypto/unpkg.cpp', 'rpcs3/Crypto/unself.cpp', 'rpcs3/Crypto/unself.h',
            'rpcs3/Emu/CPU/JITCacheCompatibility.cmake', 'rpcs3/Emu/Cell/Modules/cellSaveData.cpp',
            'rpcs3/Emu/Cell/SPUCommonRecompiler.cpp', 'rpcs3/Emu/Cell/lv2/sys_fs.cpp',
            'rpcs3/util/logs.cpp', 'rpcs3/util/serialization.hpp']
PRELUDE = '''#include <algorithm>
#include <atomic>
#include <compare>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <deque>
#include <filesystem>
#include <memory>
#include <new>
#include <optional>
#include <random>
#include <span>
#include <string>
#include <string_view>
#include <thread>
#include <utility>
#include <vector>
using usz = std::size_t; using u8 = std::uint8_t; using u32 = std::uint32_t; using u64 = std::uint64_t;
constexpr usz umax = static_cast<usz>(-1);
struct log_stub { template <typename... A> void error(const char*, A&&...) {} template <typename... A> void notice(const char*, A&&...) {} };
template <typename C> auto& at32(C& container, usz index) { if (index >= container.size()) std::abort(); return container[index]; }
'''


def braced(text, start):
    a = text.index(start)
    b = text.index('{', a) + 1
    depth = 1
    while depth:
        depth += (text[b] == '{') - (text[b] == '}')
        b += 1
    return text[a:b]


def line_start(text, needle):
    """Start of the line containing needle (keeps the original indentation)."""
    return text.rindex('\n', 0, text.index(needle)) + 1


def baseline(source: Path, work: Path) -> Path:
    tree = work / 'before'
    for path in MODIFIED:
        dest = tree / path
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes((source / path).read_bytes())
    subprocess.run(['git', 'apply', '--reverse', str(FIXTURE)], cwd=tree, check=True)
    return tree


def static_checks(source: Path, before: Path) -> dict:
    added = [l[1:] for l in FIXTURE.read_text().splitlines() if l.startswith('+') and not l.startswith('+++')]
    # The iOS Core is built with -fno-exceptions.
    assert not [l for l in added if re.search(r'\b(try|catch|throw)\b', l)]
    manifest = json.loads((ROOT / 'build-utils/rpcs3/canonical-source.json').read_bytes())
    record = manifest.get('cell545')
    if record:
        for path, digest in record['before_sha256'].items():
            assert sha((before / path).read_bytes().replace(b'\r\n', b'\n')) == digest, path
        for path, digest in record['after_sha256'].items():
            assert sha((source / path).read_bytes().replace(b'\r\n', b'\n')) == digest, path
    # Codegen identity: the only modified file in either digest list is SPUCommonRecompiler.cpp, and the
    # compatibility table maps this exact 545 snapshot to the 543 hash, so SPU and PPU objects are reused.
    cmake = (source / 'rpcs3/Emu/CMakeLists.txt').read_text()
    listed = set()
    for block in re.findall(r'foreach\(NEOSTATION_(?:PPU|SPU)_CODEGEN_SOURCE IN ITEMS(.*?)\)', cmake, re.S):
        listed |= {('rpcs3/Emu/' + p).replace('rpcs3/Emu/../../', '').replace('rpcs3/Emu/../', 'rpcs3/') for p in block.split()}
    assert listed & set(MODIFIED) == {'rpcs3/Emu/Cell/SPUCommonRecompiler.cpp'}, listed & set(MODIFIED)
    table = (source / 'rpcs3/Emu/CPU/JITCacheCompatibility.cmake').read_text()
    alias = re.search(r'source STREQUAL "Cell/SPUCommonRecompiler\.cpp" AND\s+actual STREQUAL "([0-9a-f]{64})"\)\s+'
                      r'set\(\$\{output\} "([0-9a-f]{64})"', table)
    after_hash = sha((source / 'rpcs3/Emu/Cell/SPUCommonRecompiler.cpp').read_bytes())
    before_hash = sha((before / 'rpcs3/Emu/Cell/SPUCommonRecompiler.cpp').read_bytes())
    assert alias and alias.group(1) == after_hash and alias.group(2) == before_hash
    return dict(noExceptionsAdded=True, codegenFilesChanged=['rpcs3/Emu/Cell/SPUCommonRecompiler.cpp'],
                spuCommonRecompiler=dict(before=before_hash, after=after_hash, aliasedToBefore=True))


def pkg_namespace(name, text, after):
    code = f'namespace {name} {{\nlog_stub pkg_log;\nnamespace vfs {{ inline std::string escape(std::string_view s) {{ return std::string(s); }} }}\n'
    if not after:
        assert 'leaves_directory' not in text
        line = text[line_start(text, 'std::string path = m_install_path + vfs::escape(name);'):]
        line = line[:line.index('\n')]
        return code + f'inline std::string join(const std::string& m_install_path, std::string_view name)\n{{\n{line}\n\treturn path;\n}}\n}}\n'
    code += 'namespace rpcs3::utils { inline std::string get_hdd0_dir() { return "/sandbox/dev_hdd0/"; } }\n'
    code += braced(text, 'static bool leaves_directory(std::string_view name)') + '\n'
    code += braced(text, 'static std::optional<std::string> resolve_on_hdd0(') + '\n'
    check = braced(text, 'if (m_install_dir.empty() || leaves_directory(m_install_dir))')
    code += f'inline bool install_dir_valid(const std::string& m_install_dir)\n{{\n\t{check}\n\treturn true;\n}}\n'
    a = line_start(text, 'const std::string hdd0_dir = rpcs3::utils::get_hdd0_dir();')
    hdd0 = text[a:text.index(braced(text[a:], 'while (hdd0_trimmed.ends_with')) + len(braced(text[a:], 'while (hdd0_trimmed.ends_with'))]
    b = text.index('if (leaves_directory(name))')
    first = braced(text, 'if (leaves_directory(name))')
    rest = text[b + len(first):]
    assert rest.lstrip().startswith('else')
    second = braced(rest, 'else')
    path_block = text[line_start(text, 'std::string path;\n\n\t\tif (leaves_directory(name))'):b] + first + rest[:rest.index(second) + len(second)]
    code += ('struct outcome { bool ok; std::string path; };\n'
             'inline outcome select(const std::string& m_install_path, std::string_view name)\n{\n\tusz num_failures = 0;\n'
             f'{hdd0}\n\tfor (;;)\n\t{{\n{path_block}\n\t\treturn {{true, path}};\n\t}}\n\t(void)num_failures;\n\treturn {{false, {{}}}};\n}}\n'
             )
    return code + '}\n'


def spu_namespace(name, text, after):
    code = f'namespace {name} {{\nlog_stub spu_log;\n'
    span = text[line_start(text, 'struct span_less') - len('template<typename T>\n'):]
    assert span.startswith('template<typename T>\nstruct span_less')
    code += 'template<typename T>\n' + braced(span, 'struct span_less') + ';\n'
    code += ('struct spu_program { u32 entry_point; u32 lower_bound; std::vector<u32> data;\n'
             '\tbool operator==(const spu_program& rhs) const noexcept; bool operator<(const spu_program& rhs) const noexcept; };\n')
    code += braced(text, 'bool spu_program::operator==(const spu_program& rhs) const noexcept') + '\n'
    code += braced(text, 'bool spu_program::operator<(const spu_program& rhs) const noexcept') + '\n'
    marker = '// NEOSTATION_CELL545_SPU_WARMUP_ORDER'
    if after:
        a = line_start(text, marker)
        block = text[a:text.index(braced(text[a:], 'if (func_list.size() != cached_func_count)')) + len(braced(text[a:], 'if (func_list.size() != cached_func_count)'))]
        # Adapter of RPCS3's FN for the two-argument comparator.
        code += ('#define FN(...) [&]([[maybe_unused]] auto&& x, [[maybe_unused]] auto&& y) { return (__VA_ARGS__); }\n'
                 f'inline void order(std::deque<spu_program>& func_list)\n{{\n{block}\n}}\n#undef FN\n')
    else:
        assert marker not in text
        code += 'inline void order(std::deque<spu_program>&) {}\n'
    return code + '}\n'


def savedata_namespace(name, text, after):
    code = f'namespace {name} {{\ninline usz listed(u32 sdk, u32 max, usz count)\n{{\n'
    code += '\tstruct { u32 sdk_ver; } g_ps3_process_info{sdk};\n\tstruct { u32 fileListMax; } buf{max};\n\tauto* setBuf = &buf;\n\tstd::vector<int> files_sorted(count);\n'
    start = 'if ((g_ps3_process_info.sdk_ver <= 0x26FFFF || !setBuf->fileListMax) && files_sorted.size() > setBuf->fileListMax)'
    if after:
        code += '\t' + braced(text, start) + '\n'
    else:
        assert start not in text
        code += '\t(void)g_ps3_process_info; (void)setBuf;\n'
    return code + '\treturn files_sorted.size();\n}\n}\n'


def state_namespace(name, fs_text, serial_text, after):
    save = fs_text[fs_text.index('void lv2_file::save(utils::serial& ar)'):]
    block = braced(save, 'if (in_mem)')
    assert save[save.index(block) + len(block):].lstrip().startswith('ar(file.pos());')
    pad = 'u8* pad_from_end(usz forwards)' if after else 'usz pad_from_end(usz forwards)'
    methods = '\n'.join(braced(serial_text, s) for s in ['usz seek_end()', 'usz trunc(usz count)', pad,
                                                          'void patch_raw_data(usz pos, const void* data, usz size)'])
    return f'''namespace {name} {{
struct {{ template <typename... A> void error(const char*, A&&...) {{}} }} sys_fs;
template <typename T> T ensure(T v) {{ if (!v) std::abort(); return v; }}
namespace fs {{ struct stat_t {{ u64 size; u64 mtime; }}; inline bool is_file(const std::string&) {{ return false; }} }}
template <typename T, typename U> void write_to_ptr(U&& array, usz pos, const T& value)
{{ ensure((pos + sizeof(T)) <= std::size(array)); std::memcpy(static_cast<void*>(&array[pos]), &value, sizeof(value)); }}
struct file_handler_t {{ bool is_null() const {{ return false; }} }};
struct serial
{{
	std::vector<u8> data; usz data_offset = 0; usz pos = 0; std::unique_ptr<file_handler_t> m_file_handler;
	bool is_writing() const {{ return true; }}
{methods}
	// Adapter of raw_serialize's writing branch: insert at pos unless pos is the end.
	template <typename T> void operator()(const T& value)
	{{
		const u8* ptr = reinterpret_cast<const u8*>(&value);
		if (pos != data_offset + data.size()) data.insert(data.begin() + (pos - data_offset), ptr, ptr + sizeof(T));
		else data.insert(data.end(), ptr, ptr + sizeof(T));
		pos += sizeof(T);
	}}
}};
struct file_stub
{{
	static constexpr u64 position = 0x1122334455667788;
	std::vector<u8> content; usz available = 0;
	fs::stat_t get_stat() const {{ return {{content.size(), 7}}; }}
	usz read_at(u64 offset, void* dst, usz size) const {{ const usz n = std::min(size, available); std::memcpy(dst, content.data() + offset, n); return n; }}
	u64 pos() const {{ return position; }}
}};
inline void save(serial& ar, file_stub& file)
{{
	const bool in_mem = true; const std::string name = "tmp.dat"; const std::string real_path; const int type = 0; const u32 flags = 0;
	{block}
	ar(file.pos());
}}
struct tag
{{
	using serial = {name}::serial; using file_stub = {name}::file_stub; using stat_t = fs::stat_t;
	static void save(serial& ar, file_stub& file) {{ {name}::save(ar, file); }}
}};
}}
'''


def logs_namespace(name, text, after):
    body = braced(text, 'void logs::file_listener::log(u64 stamp, const logs::message& msg, std::string_view prefix, std::string_view _text)')
    if after:
        a = body.index('thread_local bool tls_destroyed = false;')
        b = body.index('text.clear();') + len('text.clear();')
    else:
        a = body.index('/*constinit thread_local*/ std::string text;')
        b = body.index('text.reserve(50000);') + len('text.reserve(50000);')
    return f'namespace {name} {{\ninline void format_once()\n{{\n\t{body[a:b]}\n\ttext += "message";\n}}\n}}\n'


def sce_namespace(name, text, after):
    body = text[text.index('bool SCEDecrypter::DecryptData()'):]
    m = re.search(r'if \(\(hdr\.key_idx < meta_hdr\.key_count\) && \(hdr\.iv_idx (<=?) meta_hdr\.key_count\)\)', body)
    assert m and m.group(1) == ('<' if after else '<=')
    condition = m.group(0)[len('if '):]
    return (f'namespace {name} {{\ninline bool accepts(u32 key_idx, u32 iv_idx, u32 key_count)\n{{\n'
            '\tstruct { u32 key_idx; u32 iv_idx; } hdr{key_idx, iv_idx};\n\tstruct { u32 key_count; } meta_hdr{key_count};\n'
            f'\treturn {condition};\n}}\n}}\n')


def assemble(source: Path, before: Path) -> str:
    read = lambda tree, p: (tree / p).read_text()
    code = PRELUDE
    for tree, after, suffix in ((source, True, 'after'), (before, False, 'before')):
        code += pkg_namespace('pkg_' + suffix, read(tree, 'rpcs3/Crypto/unpkg.cpp'), after)
        code += spu_namespace('spu_' + suffix, read(tree, 'rpcs3/Emu/Cell/SPUCommonRecompiler.cpp'), after)
        code += savedata_namespace('savedata_' + suffix, read(tree, 'rpcs3/Emu/Cell/Modules/cellSaveData.cpp'), after)
        code += state_namespace('state_' + suffix, read(tree, 'rpcs3/Emu/Cell/lv2/sys_fs.cpp'), read(tree, 'rpcs3/util/serialization.hpp'), after)
        code += logs_namespace('logs_' + suffix, read(tree, 'rpcs3/util/logs.cpp'), after)
        code += sce_namespace('sce_' + suffix, read(tree, 'rpcs3/Crypto/unself.cpp'), after)
    return code + (ROOT / 'test/native/rpcs3_cell545.inc').read_text()


def main():
    p = argparse.ArgumentParser()
    p.add_argument('source', type=Path)
    p.add_argument('--report', type=Path)
    a = p.parse_args()
    source = a.source.resolve()
    cxx = shlex.split(os.environ.get('CXX', 'c++'))
    if sdk := os.environ.get('HOST_MACOS_SDK'):
        cxx += ['-isysroot', sdk]
    with tempfile.TemporaryDirectory(prefix='cell545-') as td:
        work = Path(td)
        before = baseline(source, work)
        checks = static_checks(source, before)
        code = assemble(source, before)
        cpp = work / 'cell545.cpp'
        cpp.write_text(code)
        exe = work / 'cell545'
        flags = ['-std=c++20', '-O1', '-g', '-Wall', '-Wextra', '-Werror', '-Wno-unused-parameter', '-Wno-unused-function',
                 '-Wno-format-security', '-D_GLIBCXX_ASSERTIONS', '-D_LIBCPP_HARDENING_MODE=_LIBCPP_HARDENING_MODE_EXTENSIVE', '-pthread', '-fno-omit-frame-pointer',
                 '-fsanitize=address,undefined']
        subprocess.run(cxx + flags + [str(cpp), '-o', str(exe)], check=True)
        env = dict(os.environ, ASAN_OPTIONS='detect_leaks=0', UBSAN_OPTIONS='halt_on_error=1:print_stacktrace=1')
        run = subprocess.run([str(exe)], capture_output=True, text=True, timeout=600, env=env)
        if run.returncode:
            print(run.stdout, run.stderr)
            run.check_returncode()
        results = json.loads(run.stdout)
        # 543 body with data already flushed to the savestate file: it indexes ar.data by an absolute position.
        control = subprocess.run([str(exe), 'savestate-control-flushed'], capture_output=True, text=True, timeout=120, env=env)
        # libstdc++ and libc++ bounds assertions, ASan, or the hardening trap signal.
        reproduced = control.returncode != 0 and (control.returncode < 0 or any(m in control.stderr for m in
                                                  ('__n < this->size()', 'out of bounds', 'AddressSanitizer')))
        assert reproduced, (control.returncode, control.stderr[-2000:])
        results['savestate']['controlFlushedOutOfBounds'] = True
        harness = sha(code.encode())
    assert results['failures'] == 0
    inputs = ['test/rpcs3_cell545_test.py', 'test/native/rpcs3_cell545.inc', 'test/fixtures/rpcs3_cell545.diff']
    report = dict(result='passed', passed=True, static=checks, scenarios=results, harnessSHA256=harness, sanitizers='ASan+UBSan, standard library bounds assertions',
                  sourceSHA256={p: sha((source / p).read_bytes().replace(b'\r\n', b'\n')) for p in MODIFIED},
                  inputs={p: sha((ROOT / p).read_bytes()) for p in inputs},
                  debugSelfDecryptionExecuted=False, physicalDeviceTested=False)
    if a.report:
        a.report.parent.mkdir(parents=True, exist_ok=True)
        a.report.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))
    print('RPCS3 CELL545: PKG paths, SPU warmup order, savedata, savestate, log buffer and SCE key index passed; 543 controls reproduced.')


if __name__ == '__main__':
    main()
