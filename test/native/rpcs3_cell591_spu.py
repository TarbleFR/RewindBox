"""Execute real try_add bodies with a recoverable-codegen outcome adapter.

No LLVM fatal is induced: the real worker outcome is represented by false,
so the ownership contract is tested without using a corrupted MCJIT engine.
The next uncached operation must never see a pointer to the old stack cache.
"""
from pathlib import Path
import ctypes.util
import hashlib
import json
import os
import shlex
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
NATIVE = Path(__file__).resolve().parent

def sha(value):
    return hashlib.sha256(value).hexdigest()

def compiler():
    result = shlex.split(os.environ.get('CXX', 'c++'))
    if sdk := os.environ.get('HOST_MACOS_SDK'):
        result += ['-isysroot', sdk]
    return result

def checked_run(command, work, **kwargs):
    return subprocess.run(command, cwd=work, capture_output=True, text=True,
                          env=dict(os.environ, ASAN_OPTIONS='detect_leaks=0', UBSAN_OPTIONS='halt_on_error=1'),
                          timeout=180, **kwargs)

def cleanup_checks(before, after, work):
    reports = {}
    signatures = (
        'bool jit_compiler::try_add(std::unique_ptr<llvm::Module> _module, const std::string& path, std::string& error)',
        'bool jit_compiler::try_add(std::unique_ptr<llvm::Module> _module, std::string& error)',
    )
    for mode, flags in [('plain', []), ('addressUndefined', ['-fsanitize=address,undefined'])]:
        reports[mode] = {}
        for label, source_root in [('before', before), ('after', after)]:
            text = (source_root / 'Utilities/JITLLVM.cpp').read_text()
            bodies = '\n'.join(body(text, name) for name in signatures)
            code = prefix + '\n' + bodies + suffix
            cpp, exe = work / f'cleanup-{label}-{mode}.cpp', work / f'cleanup-{label}-{mode}'
            cpp.write_text(code)
            command = compiler() + ['-std=c++20', '-DRPCS3_IOS=1', '-O1', '-g', '-fno-omit-frame-pointer'] + flags + [str(cpp), '-o', str(exe)]
            build = checked_run(command, work)
            assert build.returncode == 0, build.stderr
            result = checked_run([str(exe)], work)
            if label == 'before':
                assert result.returncode != 0 and 'dangling ObjectCache' in result.stderr, result.stderr
            else:
                assert result.returncode == 0, result.stderr
            reports[mode][label] = {
                'sourceBodiesSHA256': sha(bodies.encode()), 'harnessSHA256': sha(code.encode()),
                'returncode': result.returncode, 'expectedFailure': label == 'before',
                'stderr': result.stderr.strip()[:500],
            }
    return {'passed': True, 'cases': reports,
            'scope': 'Real try_add bodies; worker false is an outcome adapter, not a real LLVM fatal. The following uncached operation must see no stack cache.'}

def release_block(source):
    text = (source / 'rpcs3/Emu/Cell/SPULLVMRecompiler.cpp').read_text()
    marker = '\t\t// CELL591_RELEASE_SPU_IR:'
    assert text.count(marker) == 1
    start = text.index(marker)
    block = text[start:text.index('\n#endif', start)]
    assert 'm_ir->ClearInsertionPoint();' in block
    assert 'm_engine->removeModule(m_module)' in block and 'delete m_module;' in block
    for field in ('m_module', 'm_function', 'm_test_state', 'm_dispatch'):
        assert field + ' = nullptr;' in block
    return block

def native_checks(source, work):
    block = release_block(source)
    template = (NATIVE / 'rpcs3_cell591_mcjit.cpp').read_text()
    assert template.count('// PRODUCTION_RELEASE_BLOCK') == 1
    code = template.replace('// PRODUCTION_RELEASE_BLOCK', block)
    cpp = work / 'mcjit591.cpp'
    cpp.write_text(code)
    configured = os.environ.get('LLVM_CONFIG')
    config = configured or shutil.which('llvm-config-22') or shutil.which('llvm-config')
    ci = os.environ.get('CI', '').lower() not in ('', '0', 'false')
    if config:
        config_command = [config] if Path(config).is_file() else shlex.split(config)
        version = subprocess.check_output(config_command + ['--version'], text=True).strip()
        if not version.startswith('22.'):
            if ci or configured:
                raise AssertionError('Pinned LLVM22 required for the native gate, got ' + version)
            config = None
    if not config:
        assert not ci and not configured, 'CI requires LLVM_CONFIG pointing to the pinned LLVM22; the LLVM20 smoke is not a substitute'
        library = ctypes.util.find_library('LLVM-20') or '/usr/lib/x86_64-linux-gnu/libLLVM.so.20.1'
        smoke = work / 'mcjit20-smoke.py'
        smoke.write_text(CAPI_SMOKE.replace("'/usr/lib/x86_64-linux-gnu/libLLVM.so.20.1'", repr(library)))
        result = checked_run([sys.executable, str(smoke)], work)
        assert result.returncode == 0, result.stderr
        payload = json.loads(result.stdout)
        assert payload['passed'] and payload['reusedIRFunctionAddresses'] >= 1
        return {'passed': True, 'nativeCppRan': False, 'pinnedLLVMRequired': True,
                'releaseBlockSHA256': sha(block.encode()), 'nativeHarnessSHA256': sha(code.encode()),
                'localLLVM20Smoke': payload,
                'scope': 'Pinned LLVM22 C++ gate NOT RUN locally; actual LLVM20.1 C API smoke only. CI fails without LLVM22.'}
    cxxflags = shlex.split(subprocess.check_output(config_command + ['--cxxflags'], text=True))
    ldflags = shlex.split(subprocess.check_output(config_command + ['--ldflags', '--system-libs', '--libs', 'core', 'executionengine', 'mcjit', 'native', 'irreader'], text=True))
    results = {}
    for mode, flags in [('plain', []), ('addressUndefined', ['-fsanitize=address,undefined'])]:
        exe = work / ('mcjit591-' + mode)
        command = compiler() + cxxflags + ['-std=c++20', '-UNDEBUG', '-O1', '-g', '-fno-omit-frame-pointer', '-pthread'] + flags + [str(cpp), '-o', str(exe)] + ldflags
        build = checked_run(command, work)
        assert build.returncode == 0, build.stderr
        result = checked_run([str(exe)], work)
        assert result.returncode == 0, result.stderr
        payload = json.loads(result.stdout)
        assert payload['passed'] and payload['modulesReleased'] == 66
        assert payload['crossModuleCallers'] == 64 and payload['cachedObjectHits'] == 1
        results[mode] = payload
    return {'passed': True, 'nativeCppRan': True, 'llvmVersion': version, 'pinnedLLVMRequired': True,
            'releaseBlockSHA256': sha(block.encode()), 'nativeHarnessSHA256': sha(code.encode()),
            'cases': results, 'scope': 'Exact production release block against real pinned LLVM22 MCJIT; native objects, globals, cached relocations and later modules remain usable.'}

def run(before: Path, after: Path, source: Path, work: Path) -> dict:
    before, after, source, work = (Path(p).resolve() for p in (before, after, source, work))
    work.mkdir(parents=True, exist_ok=True)
    assert (after / 'rpcs3/Emu/Cell/SPULLVMRecompiler.cpp').read_bytes() == (source / 'rpcs3/Emu/Cell/SPULLVMRecompiler.cpp').read_bytes()
    result = {'passed': False, 'cleanup': cleanup_checks(before, after, work),
              'mcjitLifetime': native_checks(source, work),
              'inputs': {p: sha((ROOT / p).read_bytes()) for p in (
                  'test/native/rpcs3_cell591_spu.py', 'test/native/rpcs3_cell591_mcjit.cpp')},
              'physicalDeviceTested': False, 'gameplayMeasured': False,
              'scope': 'Host resource lifetime and recovered-error cleanup only; no iPhone memory, FPS or crash result inferred.'}
    result['passed'] = True
    result['pinnedLLVM22Tested'] = result['mcjitLifetime']['nativeCppRan']
    return result

def body(text, start):
    a = text.index(start)
    b = text.index('{', a)
    n, i = 1, b + 1
    while n:
        n += (text[i] == '{') - (text[i] == '}')
        i += 1
    return text[a:i]

prefix = r'''
#include <cassert>
#include <cstdint>
#include <memory>
#include <string>
#include <utility>
#include <vector>
namespace llvm {
struct Function { void deleteBody() {} };
struct Module { std::vector<Function> fs{1}; auto& functions() { return fs; } };
}
namespace utils { std::uint64_t get_tsc() { return 0; } }
namespace jit_phase { constexpr int ppu_codegen = 0; struct scope { template<class F> scope(int,F) {} }; }
struct jit_compiler;
struct ObjectCache { ObjectCache(const std::string&,jit_compiler*) {} };
struct Engine {
    ObjectCache* cache = nullptr;
    std::vector<std::unique_ptr<llvm::Module>> modules;
    unsigned codegens = 0;
    void setObjectCache(ObjectCache* value) { cache = value; }
    void addModule(std::unique_ptr<llvm::Module> module) { modules.push_back(std::move(module)); }
    void generateCodeForModule(llvm::Module*) { ++codegens; }
};
struct Announcer { void finalized(bool) {} };
bool fail_next = true;
template<class F> bool run_recoverable_llvm(F&& fn,std::string&) {
    std::forward<F>(fn)();
    return !std::exchange(fail_next, false);
}
struct jit_compiler {
    std::unique_ptr<Engine> m_engine = std::make_unique<Engine>();
    Announcer* m_announcer = nullptr;
    bool try_add(std::unique_ptr<llvm::Module>,const std::string&,std::string&);
    bool try_add(std::unique_ptr<llvm::Module>,std::string&);
};
'''

suffix = r'''
int main() {
    jit_compiler compiler;
    std::string error;
    assert(!compiler.try_add(std::make_unique<llvm::Module>(), "cache/", error));
    assert(compiler.m_engine->cache == nullptr && "recoverable path leaves dangling ObjectCache");
    assert(compiler.try_add(std::make_unique<llvm::Module>(), error));
    assert(compiler.m_engine->cache == nullptr);
    assert(compiler.m_engine->codegens == 2);
}
'''

CAPI_SMOKE = "import ctypes as C\nimport json\n\nlib = C.CDLL('/usr/lib/x86_64-linux-gnu/libLLVM.so.20.1')\nptr = C.c_void_p\ndef bind(name, result, *args):\n    fn = getattr(lib, name)\n    fn.restype, fn.argtypes = result, args\n    return fn\n\nfor n in ('LLVMLinkInMCJIT', 'LLVMInitializeX86TargetInfo', 'LLVMInitializeX86Target', 'LLVMInitializeX86TargetMC', 'LLVMInitializeX86AsmPrinter'):\n    bind(n, None)()\nctx_create = bind('LLVMContextCreate', ptr)\nctx_dispose = bind('LLVMContextDispose', None, ptr)\nbuf = bind('LLVMCreateMemoryBufferWithMemoryRangeCopy', ptr, C.c_char_p, C.c_size_t, C.c_char_p)\nparse = bind('LLVMParseIRInContext', C.c_int, ptr, ptr, C.POINTER(ptr), C.POINTER(C.c_char_p))\ncreate = bind('LLVMCreateExecutionEngineForModule', C.c_int, C.POINTER(ptr), ptr, C.POINTER(C.c_char_p))\nadd = bind('LLVMAddModule', None, ptr, ptr)\nremove = bind('LLVMRemoveModule', C.c_int, ptr, ptr, C.POINTER(ptr), C.POINTER(C.c_char_p))\ndispose = bind('LLVMDisposeModule', None, ptr)\ndispose_ee = bind('LLVMDisposeExecutionEngine', None, ptr)\nget_fn = bind('LLVMGetFunctionAddress', C.c_uint64, ptr, C.c_char_p)\nget_named_fn = bind('LLVMGetNamedFunction', ptr, ptr, C.c_char_p)\nget_pointer = bind('LLVMGetPointerToGlobal', ptr, ptr, ptr)\nget_global = bind('LLVMGetGlobalValueAddress', C.c_uint64, ptr, C.c_char_p)\nfind_fn = bind('LLVMFindFunction', C.c_int, ptr, C.c_char_p, C.POINTER(ptr))\nerror = C.c_char_p()\nctx = ctx_create()\ndef mod(name, text):\n    m = ptr()\n    raw = text.encode()\n    assert parse(ctx, buf(raw, len(raw), name.encode()), C.byref(m), C.byref(error)) == 0, error.value\n    return m\nbase = mod('base', '''\n@table = global [4 x i64] [i64 5, i64 7, i64 11, i64 13]\ndefine i64 @base(i64 %x) {\n  %i = and i64 %x, 3\n  %p = getelementptr [4 x i64], ptr @table, i64 0, i64 %i\n  %v = load i64, ptr %p\n  %r = add i64 %v, %x\n  ret i64 %r\n}\n''')\nengine = ptr()\nassert create(C.byref(engine), base, C.byref(error)) == 0, error.value\nbase_ir_pointer = get_named_fn(base, b'base')\nbase_addr = get_pointer(engine, base_ir_pointer)\ntable_addr = get_global(engine, b'table')\nassert base_addr and table_addr\nf = C.CFUNCTYPE(C.c_int64, C.c_int64)(base_addr)\nassert [f(i) for i in range(4)] == [5, 8, 13, 16]\nout = ptr()\nassert remove(engine, base, C.byref(out), C.byref(error)) == 0, error.value\nassert out.value == base.value\ndispose(out)\nir_lookup = ptr()\nassert find_fn(engine, b'base', C.byref(ir_lookup)) != 0, 'removed module remains in IR lookup'\nassert get_fn(engine, b'base') == base_addr\nassert get_global(engine, b'table') == table_addr\nassert f(3) == 16\ncallers = []\nfunction_ir_addresses = [base_ir_pointer]\nfor i in range(64):\n    name = f'caller{i}'\n    m = mod(name, f'''\ndeclare i64 @base(i64)\n@table = external global [4 x i64]\ndefine i64 @{name}(i64 %x) {{\n  %v = call i64 @base(i64 %x)\n  %p = getelementptr [4 x i64], ptr @table, i64 0, i64 1\n  %g = load i64, ptr %p\n  %s = add i64 %v, %g\n  %r = add i64 %s, {i}\n  ret i64 %r\n}}\n''')\n    add(engine, m)\n    ir_pointer = get_named_fn(m, name.encode())\n    function_ir_addresses.append(ir_pointer)\n    address = get_pointer(engine, ir_pointer)\n    assert address\n    function = C.CFUNCTYPE(C.c_int64, C.c_int64)(address)\n    assert function(3) == 23 + i\n    detached = ptr()\n    assert remove(engine, m, C.byref(detached), C.byref(error)) == 0, error.value\n    dispose(detached)\n    assert find_fn(engine, name.encode(), C.byref(ir_lookup)) != 0\n    assert get_fn(engine, name.encode()) == address\n    callers.append((function, i))\nfor function, i in callers:\n    assert function(3) == 23 + i\nassert f(2) == 13\ndispose_ee(engine)\nctx_dispose(ctx)\nprint(json.dumps({'passed': True, 'llvm': '20.1 system shared library', 'modulesRemovedAndDestroyed': 65,\n                  'nativeCodeAfterIRRemoval': True, 'nativeGlobalAfterIRRemoval': True,\n                  'subsequentCrossModuleRelocationsToRemovedIR': True,\n                  'pointerLookupUsesGlobalValueAPI': True,\n                  'reusedIRFunctionAddresses': len(function_ir_addresses) - len(set(function_ir_addresses)),\n                  'irLookupsAbsentAfterRemoval': True, 'objectCachePathTested': False,\n                  'scope': 'C API smoke test; pinned LLVM22 needs native source-bound cached-object test in CI; no iPhone or memory gain claim'}))\n"
