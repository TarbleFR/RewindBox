#!/usr/bin/env python3
"""Binding extraction for REWINDBOX_SPU_DIRECT_OBJECT_HIT_660 (shared by the audit and the table emitter).

extract(text) returns every symbol the block translator of SPULLVMRecompiler.cpp maps on the engine
under a literal name, outside compile_interpreter():
- call("name", EXPR, ...) and call<T>("name", EXPR, ...): CPUTranslator.h call() maps name -> EXPR;
- m_engine->updateGlobalMapping("name", CAST(EXPR)): the direct mappings (spu_dispatcher,
  spu_timebase_offs, spu_segment_base).
Comments are blanked first (the commented-out notify_all copy of putllc0_pattern is not a site).
Each site records its preprocessor condition, evaluated for the iOS ARM64 build.

`python3 spu_bindings_extract.py <SPULLVMRecompiler.cpp>` prints the generated C++ table.
"""
from __future__ import annotations

import re
import sys
from dataclasses import dataclass
from pathlib import Path

ARM64_IOS = {'ARCH_ARM64': True, 'ARCH_X64': False, 'RPCS3_IOS': True, 'LLVM_AVAILABLE': True, '_WIN32': False,
             '_MSC_VER': False, '__APPLE__': True, '__GNUC__': True, '__clang__': True}
TABLE_BEGIN = '\t// REWINDBOX_SPU_DIRECT_OBJECT_HIT_660 BINDINGS BEGIN'
TABLE_END = '\t// REWINDBOX_SPU_DIRECT_OBJECT_HIT_660 BINDINGS END\n'


@dataclass
class Site:
    name: str
    expr: str          # the function argument of call(), or the address argument of updateGlobalMapping()
    kind: str          # 'call' or 'mapping'
    line: int
    active: bool       # compiled in the iOS ARM64 build
    condition: str


def blank_comments(text: str) -> str:
    """Comments replaced by spaces (newlines kept), string literals untouched."""
    out, i, n = [], 0, len(text)
    while i < n:
        c = text[i]
        if c == '"' or c == "'":
            j = i + 1
            while j < n and text[j] != c:
                j += 2 if text[j] == '\\' else 1
            out.append(text[i:j + 1])
            i = j + 1
        elif text.startswith('//', i):
            j = text.find('\n', i)
            j = n if j < 0 else j
            out.append(' ' * (j - i))
            i = j
        elif text.startswith('/*', i):
            j = text.index('*/', i) + 2
            out.append(''.join(ch if ch == '\n' else ' ' for ch in text[i:j]))
            i = j
        else:
            out.append(c)
            i += 1
    return ''.join(out)


def braced(text: str, start: int) -> tuple[int, int]:
    """[start of signature, end after the matching brace] of the body that opens after start."""
    pos = text.index('{', start)
    depth = 0
    for end in range(pos, len(text)):
        depth += (text[end] == '{') - (text[end] == '}')
        if depth == 0:
            return start, end + 1
    raise AssertionError('unbalanced')


def condition_value(expr: str) -> bool:
    expr = expr.strip()
    py = re.sub(r'defined\s*\(\s*(\w+)\s*\)', lambda m: str(ARM64_IOS.get(m.group(1), None)), expr)
    py = re.sub(r'defined\s+(\w+)', lambda m: str(ARM64_IOS.get(m.group(1), None)), py)
    py = py.replace('&&', ' and ').replace('||', ' or ')
    py = re.sub(r'!(?!=)', ' not ', py)
    assert 'None' not in py, ('unknown macro in #if', expr)
    assert re.fullmatch(r'(?:\s|\bTrue\b|\bFalse\b|\band\b|\bor\b|\bnot\b|[()01])*', py), ('unsupported #if', expr)
    return bool(eval(py, {}, {}))  # noqa: S307 - reduced to True/False/and/or/not/0/1 above


def conditions(text: str) -> list[tuple[bool, str]]:
    """Per line (1-based index): whether it is compiled for iOS ARM64, and the enclosing conditions."""
    stack: list[tuple[bool, bool, str]] = []  # (this branch active, some branch taken, label)
    result = [(True, '')]
    for line in text.split('\n'):
        stripped = line.strip()
        directive = re.match(r'#\s*(ifdef|ifndef|if|elif|else|endif)\b(.*)', stripped)
        if directive:
            kind, rest = directive.group(1), directive.group(2).strip()
            if kind in ('ifdef', 'ifndef'):
                macro = rest.split()[0]
                value = ARM64_IOS.get(macro)
                assert value is not None, ('unknown macro', macro)
                value = value if kind == 'ifdef' else not value
                stack.append((value, value, f'{kind} {macro}'))
            elif kind == 'if':
                value = condition_value(rest)
                stack.append((value, value, f'if {rest}'))
            elif kind == 'elif':
                active, taken, label = stack.pop()
                value = not taken and condition_value(rest)
                stack.append((value, taken or value, label + f' / elif {rest}'))
            elif kind == 'else':
                active, taken, label = stack.pop()
                stack.append((not taken, True, label + ' / else'))
            else:
                stack.pop()
        live = all(entry[0] for entry in stack)
        result.append((live, ' & '.join(entry[2] for entry in stack)))
    return result


def split_args(text: str, start: int) -> tuple[list[str], int]:
    """Top-level arguments of the call whose '(' is at start; returns them and the index after ')'."""
    assert text[start] == '('
    depth, args, current, i = 0, [], [], start
    while True:
        c = text[i]
        if c in '([{':
            depth += 1
            if depth > 1:
                current.append(c)
        elif c in ')]}':
            depth -= 1
            if depth == 0:
                args.append(''.join(current).strip())
                return args, i + 1
            current.append(c)
        elif c == '"':
            j = i + 1
            while text[j] != '"':
                j += 2 if text[j] == '\\' else 1
            current.append(text[i:j + 1])
            i = j
        elif c == ',' and depth == 1:
            args.append(''.join(current).strip())
            current = []
        else:
            current.append(c)
        i += 1


def interpreter_span(code: str) -> tuple[int, int]:
    begin = code.index('\tspu_function_t compile_interpreter()\n')
    return braced(code, begin)


def generated_span(code: str) -> tuple[int, int] | None:
    if TABLE_BEGIN not in code:
        return None
    begin = code.index(TABLE_BEGIN)
    return begin, code.index(TABLE_END, begin) + len(TABLE_END)


CALL = re.compile(r'(?<![\w>.:])call\s*(<[^;{}]*?>)?\s*\(')
MAPPING = re.compile(r'm_engine->updateGlobalMapping\s*\(')


def extract(text: str) -> tuple[list[Site], list[int]]:
    """Literal-name sites outside compile_interpreter and the generated table, and the lines of
    calls whose name is not a literal (outside compile_interpreter)."""
    code = blank_comments(text)
    cond = conditions(text)
    skip = [interpreter_span(code)]
    if (gen := generated_span(code)) is not None:
        skip.append(gen)
    sites, dynamic = [], []

    def skipped(at: int) -> bool:
        return any(a <= at < b for a, b in skip)

    for kind, pattern in (('call', CALL), ('mapping', MAPPING)):
        for match in pattern.finditer(code):
            if skipped(match.start()):
                continue
            line = code.count('\n', 0, match.start()) + 1
            args, _ = split_args(code, match.end() - 1)
            first = args[0]
            if not (first.startswith('"') and first.endswith('"')):
                dynamic.append(line)
                continue
            name = first[1:-1]
            assert len(args) >= 2, (line, args)
            sites.append(Site(name, re.sub(r'\s+', ' ', args[1]), kind, line, cond[line][0], cond[line][1]))
    return sites, dynamic


def table(text: str) -> dict[str, tuple[str, str]]:
    """name -> (kind, expression) for the iOS ARM64 build; every name has exactly one expression."""
    sites, _ = extract(text)
    result: dict[str, tuple[str, str]] = {}
    for site in sites:
        if not site.active:
            continue
        previous = result.setdefault(site.name, (site.kind, site.expr))
        assert previous == (site.kind, site.expr), ('one name, two bindings', site.name, previous, site)
    return result


def cast(kind: str, expr: str) -> str:
    # call() maps reinterpret_cast<uptr>(_func); a mapping site already holds its cast.
    return f'reinterpret_cast<uptr>({expr})' if kind == 'call' else expr


def emit(text: str) -> str:
    entries = table(text)
    names = sorted(entries)
    rows = ''.join(f'\t\t\t{{"{name}", {cast(*entries[name])}}},\n' for name in names)
    return (f'{TABLE_BEGIN}: generated from every call("name", function) and\n'
            '\t// updateGlobalMapping("name", address) of the block translator outside compile_interpreter(),\n'
            '\t// for this build (ARCH_X64-only sites are not compiled here). Each row is the exact expression\n'
            '\t// that site maps under that name; the host audit regenerates this block from the sites.\n'
            '\tstruct direct_binding\n'
            '\t{\n'
            '\t\tstd::string_view name;\n'
            '\t\tu64 address;\n'
            '\t};\n'
            '\n'
            '\t// Evaluated once per process (thread-safe static initialization), on the first hit: every row is\n'
            '\t// constant by then. spu_runtime::initialize_static_trampolines() (SPUCommonRecompiler.cpp) sets\n'
            '\t// tr_dispatch, tr_all and g_escape once per process (its state 2 never resets), at Core init\n'
            '\t// (rpcs3/ios/RPCS3IOS.cpp), before any SPU compile; jit_runtime::alloc(0, 0) returns the base of\n'
            '\t// the code subrange, fixed once the JIT arena is prepared, and on Apple takes the process-wide\n'
            '\t// s_alloc_lock (JITASM.cpp), which a hit therefore no longer takes.\n'
            f'\tstatic const std::array<direct_binding, {len(names)}>& direct_bindings() noexcept\n'
            '\t{\n'
            f'\t\tstatic const std::array<direct_binding, {len(names)}> table\n'
            '\t\t{{\n'
            f'{rows}'
            '\t\t}};\n'
            '\t\treturn table;\n'
            '\t}\n'
            f'{TABLE_END}')


if __name__ == '__main__':
    sys.stdout.write(emit(Path(sys.argv[1]).read_text()))
