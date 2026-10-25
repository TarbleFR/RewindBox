#!/usr/bin/env python3
"""Compare the changed production file restore constructor with Build525.

Real serial/endian, filesystem layouts and enums are used. Mount/open/FXO/log
adapters substitute host I/O only. Directory and generic trace tests are not
rerun because those production paths are unchanged. No game restore is claimed.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shlex
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
BASE = 'ed08da84f11a7182e133d80ecc9b2f602ce895ea'
FS_PATH = 'rpcs3/Emu/Cell/lv2/sys_fs.cpp'

def braced(text, start):
    a = text.index(start); b = text.index('{', a) + 1; depth = 1
    while depth:
        depth += (text[b] == '{') - (text[b] == '}'); b += 1
    return text[a:b]

def sha(data): return hashlib.sha256(data).hexdigest()

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('source', type=Path)
    p.add_argument('--repository', type=Path, default=ROOT)
    p.add_argument('--report', type=Path)
    a = p.parse_args(); source = a.source.resolve(); repo = a.repository.resolve()
    after = (source / FS_PATH).read_text()
    old = lambda path: subprocess.check_output(['git', 'show', BASE + ':' + path], cwd=repo)
    manifest = json.loads(old('build-utils/rpcs3/canonical-source.json'))
    header = (source / 'rpcs3/Emu/Cell/lv2/sys_fs.h').read_text()
    file_header = (source / 'Utilities/File.h').read_text()
    errors = (source / 'rpcs3/Emu/Cell/ErrorCodes.h').read_text()
    starts = ['lv2_fs_object::lv2_fs_object(utils::serial& ar, bool)',
              'lv2_file::lv2_file(utils::serial& ar)']
    with tempfile.TemporaryDirectory(prefix='fs-diagnostic526-') as tmp:
        w = Path(tmp); baseline = w / 'baseline'; target = baseline / FS_PATH
        target.parent.mkdir(parents=True)
        base_source = manifest['upstream_commit'] if 'upstream_commit' in manifest else '22f1152783cef1f7e04af7b1c895173e28fd5b03'
        target.write_bytes(subprocess.check_output(['git', 'show', base_source + ':' + FS_PATH], cwd=source))
        patch = w / 'baseline.patch'; patch.write_bytes(old('build-utils/rpcs3/embedded-core.patch'))
        subprocess.run(['git', 'apply', '--include', FS_PATH, str(patch)], cwd=baseline, check=True)
        before = target.read_text(); assert sha(before.encode()) == manifest['files_sha256'][FS_PATH]
        assert braced(before, 'static auto lv2_fs_restore_name(') == braced(after, 'static auto lv2_fs_restore_name(')
        assert braced(before, starts[0]) == braced(after, starts[0])
        # Ensure all inherited error handling remains byte-for-byte, except the
        # added diagnostics and the equivalent named boolean read.
        old_ctor = braced(before, starts[1]); new_ctor = braced(after, starts[1])
        reduced = new_ctor.replace('\n\tstx::serial_restore_fs_trace(ar, "file_path_class", idm::last_id(), static_cast<u32>(type), lv2_fs_restore_path_class(retrieve_real));', '')
        reduced = reduced.replace('\n\tstx::serial_restore_fs_trace(ar, "file_mount_read_only", idm::last_id(), static_cast<u32>(type), mp.read_only);', '')
        reduced = reduced.replace('\n\tif (!res.file)\n\t{\n\t\tstx::serial_restore_fs_trace(ar, "file_open_error", idm::last_id(), static_cast<u32>(type), static_cast<u32>(res.error));\n\t}', '')
        reduced = reduced.replace('const bool in_memory = ar.pop<bool>(); // see lv2_file::save in_mem\n#ifdef RPCS3_IOS\n\tstx::serial_restore_fs_trace(ar, "file_in_memory", idm::last_id(), static_cast<u32>(type), in_memory);\n#endif\n\tif (in_memory)', 'if (ar.pop<bool>()) // see lv2_file::save in_mem')
        reduced = reduced.replace('#ifdef RPCS3_IOS\n\t\tstx::serial_restore_fs_trace(ar, "file_unavailable", idm::last_id(), static_cast<u32>(type), static_cast<u32>(res.error));\n#endif\n', '')
        assert reduced == old_ctor, 'Non-diagnostic constructor change'
        (w / 'layout.inc').write_text(braced(file_header, '\tstruct stat_t\n') + ';\n')
        (w / 'enum.inc').write_text(braced(header, 'enum class lv2_file_type\n') + ';\n' + braced(errors, 'enum CellError : u32\n') + ';\n')
        (w / 'open-result.inc').write_text(braced(header, '\tstruct open_result_t\n') + ';\n')
        for name, text in [('before', before), ('after', after)]:
            helper = braced(text, 'static auto lv2_fs_restore_name(') + '\n'
            if name == 'after': helper += braced(text, 'static u64 lv2_fs_restore_path_class(') + '\n'
            (w / (name + '.inc')).write_text(helper + '\n'.join(braced(text, start) for start in starts))
        cxx = shlex.split(os.environ.get('CXX', 'c++'))
        if sdk := os.environ.get('HOST_MACOS_SDK'): cxx += ['-isysroot', sdk]
        common = cxx + ['-std=c++20','-O1','-g','-Wall','-Wextra','-Werror','-DRPCS3_IOS',
                        '-I'+str(w), '-I'+str(source/'rpcs3'), str(ROOT/'test/native/rpcs3_fs_diagnostic526.cpp')]
        runs = {}
        for name in ['before','after']:
            command = common + (['-DFS_BASELINE'] if name == 'before' else [])
            exe = w / name
            subprocess.run(command + ['-fsanitize=address,undefined','-fno-omit-frame-pointer','-o',str(exe)], check=True)
            env = dict(os.environ, ASAN_OPTIONS='detect_leaks=0', UBSAN_OPTIONS='halt_on_error=1')
            cases = [(None,0,None), ('unavailable-regular',91,'EXPECTED unchanged failed-file fatal path'),
                     ('unavailable-sdata',91,'EXPECTED unchanged failed-file fatal path'),
                     ('unavailable-edata',91,'EXPECTED unchanged failed-file fatal path'),
                     ('unterminated',88,'REJECT unchanged unterminated name'),
                     ('truncated-seek',92,'REJECT unchanged truncated archive'),
                     ('truncated-memory',92,'REJECT unchanged truncated archive')]
            records = {}
            for mode, code, message in cases:
                result = subprocess.run([str(exe)] + ([mode] if mode else []), capture_output=True, text=True, timeout=60, env=env)
                assert result.returncode == code, (name,mode,result.returncode,result.stdout,result.stderr)
                assert 'AddressSanitizer' not in result.stderr and 'runtime error:' not in result.stderr, result.stderr
                if message: assert message in result.stderr, (name,mode,result.stderr)
                else: records['valid'] = json.loads(result.stdout)
                records[mode or 'success'] = {'returncode':result.returncode,'stdout':result.stdout,'stderr':result.stderr}
            runs[name] = records
            subprocess.run(command + ['-fno-exceptions','-fsyntax-only'],check=True)
        assert runs['before']['valid']['fileCases'] == runs['after']['valid']['fileCases'] == 24
        assert runs['before']['valid']['stateFingerprint'] == runs['after']['valid']['stateFingerprint']
        assert runs['after']['valid']['pathClassCases'] == 15
        assert runs['after']['valid']['newDiagnosticEvents'] == 81
        for mode,_,message in cases[1:]:
            assert runs['before'][mode]['returncode'] == runs['after'][mode]['returncode']
    record = dict(passed=True,sanitized=True,base_commit=BASE,
                  baseline_file_sha256=manifest['files_sha256'][FS_PATH], candidate_file_sha256=sha(after.encode()),
                  valid=runs['after']['valid'],baseline_valid=runs['before']['valid'],
                  child_cases={key: runs['after'][key] for key in runs['after'] if key not in ('valid','success')},
                  constructor_semantics='Exact removal of five added diagnostics and equivalent named in-memory boolean reconstructs525 constructor bytes',
                  real_serialization_header=True,real_fs_layouts_and_enums=True,real_open_result_layout=True,
                  scope='extracted production file constructors/classifier; host file/mount/FXO/trace adapters; no directory test rerun, no device/game restore or performance claim',
                  limitation='Diagnostic improvement only. Failed host reopen retains existing fatal/inspection behavior; it does not repair missing files or prove the user save resumes.')
    if a.report:
        a.report.parent.mkdir(parents=True,exist_ok=True);a.report.write_text(json.dumps(record,indent=2)+'\n')
    print(json.dumps(record,indent=2))

if __name__=='__main__': main()
