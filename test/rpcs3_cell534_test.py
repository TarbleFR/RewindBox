#!/usr/bin/env python3
"""Run production mount fragments, shader counters and actual temporary file I/O.

The VFS/ISO fixtures are adapters, not a real ISO parser or a guest savestate.
The native iPhone Core build separately compiles the full translation units.
"""
import argparse, hashlib, json, os, platform, shlex, subprocess, tempfile
from pathlib import Path
from rpcs3_memory523_test import braced
ROOT = Path(__file__).resolve().parents[1]
BASE = 'a1c7ab9bebf763b034c522363c29ce6dee6c4594'

def mount_harness(text):
    anchor = text.index('sys_log.notice("Load: is iso archive')
    normalize = braced(text[anchor:], '\t\tif (launching_from_disc_archive)')
    final = braced(text, '\t\telse\n\t\t{\n\t\t\t// Disc game\n')
    final = final[final.index('{') + 1:final.rindex('}')]
    return r'''
#include <cassert>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <map>
#include <string>
using namespace std::string_view_literals;
namespace iso_device { std::string virtual_device_name; }
namespace vfs {
std::map<std::string, std::string> mounts;
void mount(const std::string& guest, const std::string& host) { mounts[guest] = host; }
std::string get(const std::string& guest) {
    std::string match, host;
    for (const auto& [g,h] : mounts) if ((guest == g || guest.starts_with(g + "/")) && g.size() > match.size()) { match = g; host = h; }
    if (match.empty()) return {};
    if (guest.size() == match.size()) return host;
    if (!host.ends_with('/')) host += '/';
    return host + guest.substr(match.size() + 1);
}
}
struct Logger { template<class... T> void notice(const char*, T&&...) {} } sys_log;
struct Boot {
    bool launching_from_disc_archive = false, m_ar = true;
    std::string m_dir, m_cat = "DG", disc, bdvd_dir, m_game_dir = "PS3_GAME", m_title_id = "BCES00510";
    void normalize() {
''' + normalize + r'''
    }
    void final_mount() {
''' + final + r'''
    }
};
int main(int argc, char** argv) {
    assert(argc == 2); std::string root = argv[1];
    iso_device::virtual_device_name = root + "/mounted_iso";
    for (const auto& game : {"PS3_GAME", "PS3_GM01"}) {
        auto path = iso_device::virtual_device_name + "/" + game + "/USRDIR";
        std::filesystem::create_directories(path);
        std::ofstream(path + "/GAME.PSARC") << "exact fixture bytes";
    }
    const auto archive = root + "/current-container/disc.iso";
    std::filesystem::create_directories(root + "/current-container");
    std::ofstream(archive) << "ISO adapter";
    // State title ID resolves to the current ISO. load_iso has already mounted
    // the archive, before the two production fragments below execute.
    Boot restored; restored.launching_from_disc_archive = true; restored.disc = archive;
    vfs::mount("/dev_bdvd", iso_device::virtual_device_name + "/");
    restored.normalize(); restored.final_mount();
    std::ifstream file(vfs::get("/dev_bdvd/PS3_GAME/USRDIR/GAME.PSARC"));
    std::string value; std::getline(file, value);
    if (value != "exact fixture bytes") { std::cout << "REPRODUCED: final mount replaced valid ISO root with host ISO filename\n"; return 17; }
    restored.m_game_dir = "PS3_GM01"; restored.final_mount();
    assert(std::filesystem::exists(vfs::get("/dev_bdvd/PS3_GAME/USRDIR/GAME.PSARC")));
    // Fresh ISO and absolute-path states keep the existing empty-disc branch,
    // including its SFB/title validation; no forced generic mount is introduced.
    Boot fresh; fresh.launching_from_disc_archive = true; fresh.m_ar = false; fresh.normalize(); assert(fresh.disc.empty());
    // Directory and PSN path selection remain untouched.
    Boot folder; folder.disc = iso_device::virtual_device_name + "/"; folder.normalize(); folder.final_mount();
    assert(std::filesystem::exists(vfs::get("/dev_bdvd/PS3_GAME/USRDIR/GAME.PSARC")));
    Boot psn; psn.m_cat = "HG"; psn.disc = root + "/dev_hdd0/game/NPUB12345/"; auto saved = psn.disc; psn.normalize(); assert(psn.disc == saved && psn.m_cat == "HG");
    std::filesystem::remove(iso_device::virtual_device_name + "/PS3_GAME/USRDIR/GAME.PSARC");
    restored.m_game_dir = "PS3_GAME"; restored.final_mount();
    assert(!std::filesystem::exists(vfs::get("/dev_bdvd/PS3_GAME/USRDIR/GAME.PSARC")));
    std::ifstream original(archive); std::getline(original, value); assert(value == "ISO adapter");
    std::cout << "PASS restored/current-container ISO, multi-game, fresh ISO branch, folder/PSN, actual missing file, original bytes preserved\n";
}
'''

def main():
    p = argparse.ArgumentParser(); p.add_argument('source', type=Path); p.add_argument('--report', type=Path); a = p.parse_args()
    src = a.source.resolve(); native = ROOT / 'native/neoswap-storage'
    cxx = shlex.split(os.environ.get('CXX', 'c++'))
    if sdk := os.environ.get('HOST_MACOS_SDK'): cxx += ['-isysroot', sdk]
    common = cxx + ['-std=c++20', '-O1', '-g', '-pthread', '-Wall', '-Wextra', '-Werror', '-fsanitize=address,undefined', '-fno-omit-frame-pointer']
    env = dict(os.environ, ASAN_OPTIONS='detect_leaks=0', UBSAN_OPTIONS='halt_on_error=1')
    results = {}
    with tempfile.TemporaryDirectory(prefix='cell534-') as temp:
        work = Path(temp); (work/'files').mkdir()
        upstream = json.loads((ROOT/'build-utils/rpcs3/canonical-source.json').read_text())['upstream_commit']
        path = 'rpcs3/Emu/System.cpp'; old = work/'baseline'/path; old.parent.mkdir(parents=True)
        old.write_bytes(subprocess.check_output(['git', 'show', upstream+':'+path], cwd=src))
        patch = work/'baseline.patch'; patch.write_bytes(subprocess.check_output(['git', 'show', BASE+':build-utils/rpcs3/embedded-core.patch'], cwd=ROOT))
        subprocess.run(['git', 'apply', '--include', path, str(patch)], cwd=work/'baseline', check=True)
        before = json.loads(subprocess.check_output(['git', 'show', BASE+':build-utils/rpcs3/canonical-source.json'], cwd=ROOT))
        assert hashlib.sha256(old.read_bytes()).hexdigest() == before['files_sha256'][path]
        for name, text, expected in [('before', old.read_text(), 17), ('after', (src/path).read_text(), 0)]:
            file = work/(name+'.cpp'); file.write_text(mount_harness(text)); exe = work/name
            subprocess.run(common+['-DRPCS3_IOS', str(file), '-o', str(exe)], check=True)
            run = subprocess.run([str(exe), str(work/'files')], capture_output=True, text=True, env=env, timeout=30)
            assert run.returncode == expected, (name, run.returncode, run.stdout, run.stderr)
            assert 'AddressSanitizer' not in run.stderr and 'runtime error:' not in run.stderr
            results[name] = dict(exit=run.returncode, output=run.stdout)
        exe = work/'shader'; subprocess.run(common+['-I'+str(src/'rpcs3'), str(ROOT/'test/native/rpcs3_shader_timing534.cpp'), '-o', str(exe)], check=True)
        results['shader'] = subprocess.check_output([str(exe)], text=True, env=env, timeout=30)
        pipeline = (src/'rpcs3/Emu/RSX/VK/VKProgramPipeline.cpp').read_text()
        assert all(pipeline.count('shader_timing::Stage::'+stage+')') == 1 for stage in ('source', 'module', 'graphics', 'compute', 'debug_source'))
        libs = ['-lcompression','-lz'] if platform.system() == 'Darwin' else ['-llz4','-lz']
        legacy = [] if 'clang' in subprocess.check_output(cxx[:1]+['--version'], text=True).lower() else ['-Wno-error=misleading-indentation', '-Wno-error=unused-result']
        exe = work/'storage'; subprocess.run(common+legacy+['-I'+str(native)]+[str(native/s) for s in ('Metrics.cpp','Store.cpp','ManagedSwap.cpp','SourceArchive.cpp')]+[str(ROOT/'test/native/neoswap_persistence534.cpp')]+libs+['-o',str(exe)],check=True)
        output = subprocess.check_output([str(exe), str(work/'files')], text=True, env=env, timeout=120)
        results['storage'] = [json.loads(line) for line in output.splitlines() if line.startswith('{')]
        assert len(results['storage']) == 2
    report = dict(passed=True, physicalDeviceTested=False, realGameRestored=False, sanitized=True, baseline=BASE,
                  scope='Production mount fragments with VFS adapter; actual atomic counters and real POSIX archive reads/writes. Timings are host-only, no FPS inference.', results=results)
    if a.report: a.report.parent.mkdir(parents=True, exist_ok=True); a.report.write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps(report, indent=2))
if __name__ == '__main__': main()
