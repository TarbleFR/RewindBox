#!/usr/bin/env python3
"""Execute the production CELL546 bodies (JIT object deflate level, restore trace scope) against the 545 baseline.

Usage: rpcs3_cell546_test.py <546 Core work tree> [--corpus FILE] [--report out.json]

The zip() body, the deflate level line of the compressed serialization handler
and the restore trace bodies are copied verbatim from the 546 Core work tree;
the 545 baseline is reconstructed by reverse-applying the reviewed fixture.
Adapters replace the file object, the threaded serializer and the logger. The
compressed objects are read back by the production jit_object_buffer reader
(Utilities/JITObjectBuffer.h, unchanged). The corpus is host machine code (an
installed binary), not a PS3 module: the timings are host timings, not iPhone
ones. ASan+UBSan with standard library assertions.
"""
import argparse, hashlib, json, os, re, shlex, shutil, subprocess, sys, tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / 'test/fixtures/rpcs3_cell546.diff'
sha = lambda b: hashlib.sha256(b).hexdigest()
MODIFIED = ['rpcs3/Crypto/unzip.cpp', 'rpcs3/Emu/savestate_utils.cpp',
            'rpcs3/util/serialization_ext.cpp', 'rpcs3/util/serialization_ext.hpp']
# Size of the PPU object whose level 9 compression took 3.58 s on the iPhone (build 541, session 4).
OBJECT_BYTES = 6665088
PRELUDE = '''#include <algorithm>
#include <chrono>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <fstream>
#include <memory>
#include <string>
#include <string_view>
#include <thread>
#include <type_traits>
#include <utility>
#include <vector>
#include <zlib.h>
using usz = std::size_t; using u8 = std::uint8_t; using u16 = std::uint16_t; using u32 = std::uint32_t; using u64 = std::uint64_t;
template <typename T> T ensure(T v) { if (!v) std::abort(); return v; }
static int g_deflate_level = -100;
static int harness_deflate_init(z_streamp strm, int level, int method, int bits, int mem, int strategy)
{
	g_deflate_level = level;
	return deflateInit2_(strm, level, method, bits, mem, strategy, ZLIB_VERSION, static_cast<int>(sizeof(z_stream)));
}
#undef deflateInit2
#define deflateInit2(strm, level, method, bits, mem, strategy) harness_deflate_init((strm), (level), (method), (bits), (mem), (strategy))
static u64 g_now = 0;
static u64 get_system_time() { return g_now; }
// Adapter of RPCS3's fmt for the three conversions used by the trace bodies.
struct log_stub
{
	std::vector<std::string> lines;
	static std::string text(std::string_view v) { return std::string(v); }
	static std::string text(const char* v) { return v; }
	template <typename T> requires std::is_integral_v<T> static std::string text(T v) { return std::to_string(v); }
	template <typename... A> void notice(const char* fmt, A&&... args)
	{
		const std::vector<std::string> values{text(args)...};
		std::string out; usz next = 0;
		for (const char* p = fmt; *p; ++p)
		{
			if (*p != '%') { out += *p; continue; }
			while (*p && !std::strchr("sud", *p)) ++p;
			if (!*p || next >= values.size()) std::abort();
			out += values[next++];
		}
		if (next != values.size()) std::abort();
		lines.push_back(std::move(out));
	}
};
'''


def braced(text, start):
    a = text.index(start)
    b = text.index('{', a) + 1
    depth = 1
    while depth:
        depth += (text[b] == '{') - (text[b] == '}')
        b += 1
    return text[a:b]


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
    record = manifest.get('cell546')
    if record:
        for path, digest in record['before_sha256'].items():
            assert sha((before / path).read_bytes().replace(b'\r\n', b'\n')) == digest, path
        for path, digest in record['after_sha256'].items():
            assert sha((source / path).read_bytes().replace(b'\r\n', b'\n')) == digest, path
    # No modified file shapes PPU or SPU objects: both codegen identities are those of 545.
    cmake = (source / 'rpcs3/Emu/CMakeLists.txt').read_text()
    listed = set()
    for block in re.findall(r'foreach\(NEOSTATION_(?:PPU|SPU)_CODEGEN_SOURCE IN ITEMS(.*?)\)', cmake, re.S):
        listed |= {('rpcs3/Emu/' + p).replace('rpcs3/Emu/../../', '').replace('rpcs3/Emu/../', 'rpcs3/') for p in block.split()}
    assert not listed & set(MODIFIED), listed & set(MODIFIED)
    # Every other compressed stream keeps the upstream level: only zip() selects one, and only on iOS.
    callers = []
    for path in source.joinpath('rpcs3').rglob('*.cpp'):
        if 'set_deflate_level(' in path.read_text(errors='replace'):
            callers.append(path.relative_to(source).as_posix())
    assert callers == ['rpcs3/Crypto/unzip.cpp'], callers
    return dict(noExceptionsAdded=True, codegenFilesChanged=[], deflateLevelCallers=callers)


def zip_namespace(name, unzip, header, serial_cpp, serial_hpp, after):
    # The production declaration carries the default argument used by the JIT object writer.
    declaration = re.search(r'\nbool zip\(const void\* src, usz size, fs::file& out, bool multi_thread_it = false\);', header).group(0).strip()
    init = braced(serial_cpp, 'void compressed_serialization_file_handler::initialize(utils::serial& ar)')
    call = re.search(r'\n([^\n]*ensure\(deflateInit2\(&m_zs,[^\n]*)\n', init).group(1).strip()
    level = re.search(r'\n([^\n]*const int level = [^\n]*)\n', init)
    assert bool(level) == after
    level_line = level.group(1).strip() if level else ''
    handler = serial_hpp[serial_hpp.index('struct compressed_serialization_file_handler :'):]
    handler = handler[:handler.index('make_compressed_serialization_file_handler(File&& file)')]
    setter = braced(handler, 'void set_deflate_level(int level) noexcept') if after else ''
    assert ('set_deflate_level' in handler) == after
    member = 'int m_deflate_level = -1;' if after else ''
    if after:
        assert member in handler
    body = braced(unzip, 'bool zip(const void* src, usz size, fs::file& out, bool multi_thread_it)')
    return f'''namespace {name} {{
namespace fs {{ struct file {{ std::string bytes; explicit operator bool() const {{ return true; }} usz size() const {{ return bytes.size(); }} }}; }}
namespace utils {{
struct serial;
struct serialization_file_handler {{ virtual ~serialization_file_handler() = default; virtual bool is_valid() const = 0; virtual void finalize(serial&) = 0; virtual void write(serial&, std::string_view) = 0; }};
struct serial
{{
	bool m_expect_little_data = false;
	std::unique_ptr<serialization_file_handler> m_file_handler;
	void set_expect_little_data(bool value) {{ m_expect_little_data = value; }}
	bool expect_little_data() const {{ return m_expect_little_data; }}
	void operator()(std::string_view data) {{ m_file_handler->write(*this, data); }}
	void breathe() {{}}
}};
}}
// Adapter of the handler's write side: the production level line and deflateInit2 call, deflate inline.
struct compressed_serialization_file_handler : utils::serialization_file_handler
{{
	explicit compressed_serialization_file_handler(fs::file& file) : m_file(&file) {{}}
	{setter}
	bool is_valid() const override {{ return !m_errored; }}
	void initialize(utils::serial& ar)
	{{
		if (m_write_inited) return;
		z_stream& m_zs = m_stream;
		m_zs = {{}};
		{level_line}
		{call}
		m_write_inited = true;
	}}
	void pump(int flush)
	{{
		u8 out[0x10000];
		do
		{{
			m_stream.next_out = out;
			m_stream.avail_out = sizeof(out);
			const int status = deflate(&m_stream, flush);
			if (status != Z_OK && status != Z_STREAM_END && status != Z_BUF_ERROR) m_errored = true;
			m_file->bytes.append(reinterpret_cast<const char*>(out), sizeof(out) - m_stream.avail_out);
		}}
		while (m_stream.avail_out == 0);
	}}
	void write(utils::serial& ar, std::string_view data) override
	{{
		initialize(ar);
		m_stream.next_in = reinterpret_cast<Bytef*>(const_cast<char*>(data.data()));
		m_stream.avail_in = static_cast<uInt>(data.size());
		pump(Z_NO_FLUSH);
	}}
	void finalize(utils::serial&) override
	{{
		if (!m_write_inited) return;
		pump(Z_FINISH);
		deflateEnd(&m_stream);
		m_write_inited = false;
	}}
	fs::file* m_file;
	z_stream m_stream{{}};
	bool m_write_inited = false;
	bool m_errored = false;
	{member}
}};
inline std::unique_ptr<compressed_serialization_file_handler> make_compressed_serialization_file_handler(fs::file& file)
{{
	return std::make_unique<compressed_serialization_file_handler>(file);
}}
{declaration}
{body}
}}
'''


def trace_namespace(name, text, after):
    a = text.index('\tstruct restore_trace_state')
    b = text.index('#endif\n\textern u16 serial_breathe_and_tag')
    block = text[a:b]
    assert ('REWINDBOX_RESTORE_TRACE_SCOPE_V1' in block) == after
    return f'''namespace {name} {{
log_stub sys_log;
struct handler_stub {{ bool is_valid() const {{ return true; }} }};
namespace utils {{
struct serial
{{
	bool writing = false; usz pos = 0; std::vector<u8> data; std::unique_ptr<handler_stub> m_file_handler;
	bool is_writing() const {{ return writing; }}
}};
}}
{block}
}}
'''


def assemble(source: Path, before: Path) -> str:
    read = lambda tree, p: (tree / p).read_text()
    code = PRELUDE
    code += f'#include "{source / "Utilities/JITObjectBuffer.h"}"\n#include "{source / "rpcs3/ios/IOSRestoreFailure.h"}"\n'
    for tree, after, suffix in ((source, True, 'after'), (before, False, 'before')):
        code += zip_namespace('zip_' + suffix, read(tree, 'rpcs3/Crypto/unzip.cpp'), read(source, 'rpcs3/Crypto/unzip.h'), read(tree, 'rpcs3/util/serialization_ext.cpp'),
                              read(tree, 'rpcs3/util/serialization_ext.hpp'), after)
        code += trace_namespace('trace_' + suffix, read(tree, 'rpcs3/Emu/savestate_utils.cpp'), after)
    return code + (ROOT / 'test/native/rpcs3_cell546.inc').read_text()


def default_corpus(cxx) -> Path:
    candidates = []
    for tool in (cxx[0], 'clang++', 'g++', 'c++'):
        if found := shutil.which(tool):
            candidates.append(Path(found).resolve())
    probe = subprocess.run(cxx + ['-print-prog-name=cc1plus'], capture_output=True, text=True)
    if probe.returncode == 0 and Path(probe.stdout.strip()).is_file():
        candidates.append(Path(probe.stdout.strip()).resolve())
    candidates.append(Path(sys.executable).resolve())
    return max((c for c in candidates if c.is_file()), key=lambda c: c.stat().st_size)


def main():
    p = argparse.ArgumentParser()
    p.add_argument('source', type=Path)
    p.add_argument('--corpus', type=Path)
    p.add_argument('--report', type=Path)
    a = p.parse_args()
    source = a.source.resolve()
    cxx = shlex.split(os.environ.get('CXX', 'c++'))
    corpus = (a.corpus or default_corpus(cxx)).resolve()
    if sdk := os.environ.get('HOST_MACOS_SDK'):
        cxx += ['-isysroot', sdk]
    data = corpus.read_bytes()
    offset = max(0, min(len(data) // 4, len(data) - OBJECT_BYTES))
    sample = data[offset:offset + OBJECT_BYTES]
    assert len(sample) >= 1 << 20, (corpus, len(data))
    with tempfile.TemporaryDirectory(prefix='cell546-') as td:
        work = Path(td)
        before = baseline(source, work)
        checks = static_checks(source, before)
        code = assemble(source, before)
        cpp = work / 'cell546.cpp'
        cpp.write_text(code)
        (work / 'sample.bin').write_bytes(sample)
        flags = ['-std=c++20', '-O2', '-g', '-Wall', '-Wextra', '-Werror', '-Wno-unused-parameter', '-Wno-unused-function',
                 '-D_GLIBCXX_ASSERTIONS', '-D_LIBCPP_HARDENING_MODE=_LIBCPP_HARDENING_MODE_EXTENSIVE', '-pthread',
                 '-fno-omit-frame-pointer', '-fsanitize=address,undefined']
        env = dict(os.environ, ASAN_OPTIONS='detect_leaks=0', UBSAN_OPTIONS='halt_on_error=1:print_stacktrace=1')
        results = {}
        # The iOS Core defines RPCS3_IOS globally; another platform's build must keep the upstream level.
        for platform, defines in (('ios', ['-DRPCS3_IOS=1']), ('other', [])):
            exe = work / ('cell546-' + platform)
            subprocess.run(cxx + flags + defines + [str(cpp), '-lz', '-o', str(exe)], check=True)
            run = subprocess.run([str(exe), platform, str(work / 'sample.bin')], capture_output=True, text=True, timeout=900, env=env)
            if run.returncode:
                print(run.stdout, run.stderr)
                run.check_returncode()
            results[platform] = json.loads(run.stdout)
        harness = sha(code.encode())
    assert results['ios']['failures'] == 0 and results['other']['failures'] == 0
    inputs = ['test/rpcs3_cell546_test.py', 'test/native/rpcs3_cell546.inc', 'test/fixtures/rpcs3_cell546.diff']
    report = dict(result='passed', passed=True, static=checks, scenarios=results, harnessSHA256=harness,
                  sanitizers='ASan+UBSan, standard library bounds assertions',
                  corpus=dict(path=str(corpus), bytes=len(data), sampleOffset=offset, sampleBytes=len(sample), sampleSHA256=sha(sample),
                              kind='host machine code; timings are host timings, not iPhone ones'),
                  sourceSHA256={p: sha((source / p).read_bytes().replace(b'\r\n', b'\n')) for p in MODIFIED},
                  inputs={p: sha((ROOT / p).read_bytes()) for p in inputs}, physicalDeviceTested=False)
    if a.report:
        a.report.parent.mkdir(parents=True, exist_ok=True)
        a.report.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))
    print('RPCS3 CELL546: JIT object deflate level, production reader round trip and restore trace scope passed; 545 controls reproduced.')


if __name__ == '__main__':
    main()
