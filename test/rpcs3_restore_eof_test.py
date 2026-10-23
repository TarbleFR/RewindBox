#!/usr/bin/env python3
"""Production TAR + serial methods + pinned ZSTD; portable thread/file adapters.

Reproduces the Build 513 zero-byte end probe with prefetched next-member data.
No game, save-state content, device or physical-memory measurement is mocked as
evidence. The adapters replace host I/O only; compressed bytes are real ZSTD.
"""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import shlex
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def braced(text, signature):
    start = text.index(signature)
    end = text.index('{', start)
    depth = 1
    end += 1
    while depth:
        depth += (text[end] == '{') - (text[end] == '}')
        end += 1
    return text[start:end]


def program(core, before):
    harness = (ROOT / 'test/native/rpcs3_savestate_harness.cpp').read_text()
    preamble = harness.split('// INSERT_PRODUCTION_SERIALIZATION')[0]
    preamble = preamble.replace('virtual ~serialization_file_handler() = default;', 'virtual ~serialization_file_handler() = default;\n  virtual bool is_null() const { return false; }')
    preamble = preamble.replace('#include <algorithm>', '#include <algorithm>\n#include <span>')
    preamble = preamble.replace('template<class T> T sub_saturate',
        'template<class T> T aligned_div(T a,T b){return a/b+(a%b!=0);}\ntemplate<class T> T sub_saturate')
    hpp = (core / 'rpcs3/util/serialization_ext.hpp').read_text()
    cpp = (core / 'rpcs3/util/serialization_ext.cpp').read_text()
    declaration = braced(hpp, 'struct compressed_zstd_serialization_file_handler :') + ';'
    methods = cpp[cpp.index('struct compressed_zstd_stream_data :'):cpp.index('\nbool null_serialization_file_handler::')]
    serial = (core / 'rpcs3/util/serialization.hpp').read_text()
    breathe = braced(serial, 'void breathe(bool forced = false)')
    get_size = braced(serial, 'usz get_size(usz recommended = umax) const')
    raw = braced(serial, 'bool raw_serialize(Func&& memory_provider, usz size)')
    read = braced(serial, 'usz try_read(T&& obj)')
    tar = (core / 'rpcs3/Loader/TAR.cpp').read_text()
    if before:
        tar = tar.replace('while (filedata_read_pos < utils::aligned_div<usz>(filesize, chunk_size))', 'while (true)')
    start = tar.index('std::unique_ptr<named_thread<std::function<void()>>> async_reader;')
    loop = tar[start:tar.index('\n\t\t\t\tfile.close();', start)]
    return preamble + '\nstruct compressed_zstd_stream_data;\n' + declaration + '\n' + methods + r'''
struct reader : utils::serial {
    compressed_zstd_serialization_file_handler codec;
    utils::serialization_file_handler* m_file_handler = &codec;
    reader(const fs::file& file, usz prefix, usz size, usz prefetch) : codec(file) {
        writing = false;
        data.reserve(prefetch);
        ensure(codec.handle_file_op(*this, 0, prefix, nullptr));
        pos = prefix;
        m_max_data = prefix + size;
    }
    static usz predict_object_size(std::span<u8> out) { return out.size(); }
    bool serialize(std::span<u8> out) {
        return raw_serialize([&]() -> const void* { return out.data(); }, out.size());
    }
''' + breathe + '\n' + get_size + '\ntemplate<class Func>\n' + raw + '\ntemplate<class T>\n' + read + r'''
};
struct sink {
    usz pos = 0, prefix;
    const std::vector<u8>& expected;
    void write(const u8* data, usz size) {
        ensure(prefix + pos + size <= expected.size());
        ensure(std::memcmp(data, expected.data() + prefix + pos, size) == 0);
        pos += size;
    }
};
void run(usz filesize, usz prefetch) {
    constexpr usz chunk_size = 0x100000, chunk_count = 4, prefix = 512;
    const usz suffix_start = prefix + utils::aligned_div<usz>(filesize, 512) * 512;
    std::vector<u8> expected(suffix_start + 3 * chunk_size);
    for(usz i=0;i<expected.size();++i) expected[i]=static_cast<u8>((i*13+(i>>12)*7)%251);
    fs::file archive;
    archive.bytes.resize(ZSTD_compressBound(expected.size()));
    const usz compressed = ZSTD_compress(archive.bytes.data(),archive.bytes.size(),expected.data(),expected.size(),1);
    ensure(!ZSTD_isError(compressed)); archive.bytes.resize(compressed);
    auto file_data = std::make_unique<reader>(archive,prefix,filesize,prefetch);
    void* m_ar = reinterpret_cast<void*>(1);
    bool should_ignore = false;
    std::vector<std::vector<u8>> filedata_buffers;
    for(usz i=0;i<std::min<usz>(utils::aligned_div<usz>(filesize,chunk_size),chunk_count);++i)
        filedata_buffers.emplace_back(std::min<usz>(filesize-i*chunk_size,chunk_size));
    sink file{0,prefix,expected};
''' + loop + r'''
    ensure(file.pos==filesize && file_data->pos==prefix+filesize);
    // Production forward seek/padding before the next TAR member, with the
    // enclosing archive's limit restored. Do not lose prefetched suffix bytes.
    file_data->pos = suffix_start;
    file_data->codec.skip_until(*file_data);
    file_data->breathe();
    file_data->m_max_data = umax;
    std::vector<u8> tail(3 * chunk_size);
    ensure(file_data->try_read(std::span<u8>(tail))==0);
    ensure(std::equal(tail.begin(),tail.end(),expected.begin()+suffix_start));
}
int main() {
    for(auto size : {usz{2*1048576},usz{3*1048576},usz{1048576},usz{1048575},usz{1048577},usz{0},usz{1},usz{5*1048576},usz{5*1048576+123},usz{33*1048576+17}})
        for(auto prefetch : {usz{3*1048576},usz{8*1048576}}) run(size,prefetch);
    ensure(live_decoders==0);
    std::cout << "PASS 20 compressed TAR boundaries; all payload/padding/next-member bytes preserved\n";
}
'''


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('source', type=Path)
    ap.add_argument('--report', type=Path)
    ap.add_argument('--sanitize', action='store_true')
    args = ap.parse_args()
    core = args.source.resolve()
    zstd = core / '3rdparty/zstd/zstd/lib'
    assert (zstd / 'zstd.h').is_file(), 'Initialize pinned ZSTD submodule'
    cc = shlex.split(os.environ.get('HOST_CC', 'cc'))
    cxx = shlex.split(os.environ.get('CXX', 'c++'))
    sdk = ['-isysroot',os.environ['HOST_MACOS_SDK']] if os.environ.get('HOST_MACOS_SDK') else []
    sanitizer = ['-fsanitize=address,undefined','-fno-omit-frame-pointer'] if args.sanitize else []
    results = []
    with tempfile.TemporaryDirectory(prefix='rpcs3-restore-eof-') as directory:
        work = Path(directory)
        objects = []
        for src in sorted(zstd.glob('*/*.c')):
            if src.parent.name not in ('common','compress','decompress'): continue
            obj = work / (src.stem+'.o')
            subprocess.run(cc+['-O1','-g','-DZSTD_DISABLE_ASM','-I'+str(zstd),'-c',str(src),'-o',str(obj)]+sdk+sanitizer,check=True)
            objects.append(str(obj))
        for before in (True,False):
            label = '513-negative-control' if before else 'candidate'
            source = work/(label+'.cpp'); binary=source.with_suffix('')
            source.write_text(program(core,before))
            subprocess.run(cxx+['-std=c++20','-O1','-g','-pthread','-DRPCS3_IOS','-I'+str(zstd),
                '-I'+str(core/'rpcs3/ios'),str(source),*objects,'-o',str(binary)]+sdk+sanitizer,check=True)
            r = subprocess.run([str(binary)],capture_output=True,text=True,timeout=60)
            if before:
                assert r.returncode != 0 and 'ar.pos >= ar.data_offset' in r.stderr, r.stderr
            else:
                assert r.returncode == 0, r.stderr
            results.append({'variant':label,'exit':r.returncode,'stdout':r.stdout.strip(),'stderr':r.stderr.strip()})
    report={'passed':True,'realZstd':True,'boundaryCases':20,'sanitizers':args.sanitize,'cases':results,
        'scope':'production methods with portable host I/O/thread adapters; no device run'}
    if args.report: args.report.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))


if __name__ == '__main__': main()
