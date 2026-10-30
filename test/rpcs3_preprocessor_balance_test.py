#!/usr/bin/env python3
"""Reject malformed conditional directives in modified RPCS3 Core sources."""
from bisect import bisect_left
import json
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DIRECTIVE = re.compile(r'^\s*#\s*(if|ifdef|ifndef|elif|else|endif)\b')
INLINE = re.compile(r'\S\s*#\s*(?:if|ifdef|ifndef|elif|else|endif)\b')
RAW_STRING = re.compile(r'(?:u8|u|U|L)?R"([^\s()\\]{0,16})\(')
NORMAL_LITERAL = re.compile(r'''(?:u8|u|U|L)?(['"])''')


def mask_non_code(source: str) -> str:
    """Hide comments/literal contents while preserving physical line numbers.

    C++ removes backslash-newline pairs before recognizing comments and normal
    literals. Keep a position map so that scanning that logical view does not
    remove physical newlines from the result. Raw literal bodies instead use
    their original bytes: line splicing is reverted inside those literals.
    Literal endpoints retain a token marker; a real #else after a literal must
    still be rejected as code followed by an inline directive.
    """
    logical, positions = [], []
    i = 0
    while i < len(source):
        if source.startswith('\\\n', i):
            i += 2
        elif source.startswith('\\\r\n', i):
            i += 3
        else:
            logical.append(source[i])
            positions.append(i)
            i += 1
    text = ''.join(logical)
    result = list(source)

    def hide(begin, end, literal=False):
        for position in range(begin, end):
            if source[position] not in '\r\n':
                result[position] = ' '
        if literal:
            result[begin] = 'x'
            last = end - 1
            while source[last] in '\r\n':
                last -= 1
            result[last] = 'x'

    i = 0
    while i < len(text):
        begin = i
        literal = False
        if text.startswith('//', i):
            end = text.find('\n', i + 2)
            i = len(text) if end < 0 else end
        elif text.startswith('/*', i):
            end = text.find('*/', i + 2)
            i = len(text) if end < 0 else end + 2
        elif raw := RAW_STRING.match(text, i):
            # Search the unspliced source, so a raw payload containing a
            # closing-looking delimiter split by a newline cannot end it.
            close = ')' + raw.group(1) + '"'
            end = source.find(close, positions[raw.end() - 1] + 1)
            end = len(source) if end < 0 else end + len(close)
            hide(positions[i], end, literal=True)
            i = bisect_left(positions, end, lo=raw.end())
            continue
        elif normal := NORMAL_LITERAL.match(text, i):
            literal = True
            quote = normal.group(1)
            i = normal.end()
            while i < len(text):
                if text[i] == '\\':
                    i = min(i + 2, len(text))
                elif text[i] == quote:
                    i += 1
                    break
                else:
                    i += 1
        elif text[i].isdigit() or (text[i] == '.' and i + 1 < len(text) and text[i + 1].isdigit()):
            # Apostrophes in preprocessing numbers (1'000, 0xAB'CD) are digit
            # separators, not the start of character literals.
            i += 1
            while i < len(text):
                if text[i].isalnum() or text[i] in '_.':
                    i += 1
                elif text[i] == "'" and i + 1 < len(text) and (text[i + 1].isalnum() or text[i + 1] == '_'):
                    i += 2
                elif text[i] in '+-' and text[i - 1] in 'eEpP':
                    i += 1
                else:
                    break
            continue
        else:
            i += 1
            continue
        hide(positions[begin], positions[i - 1] + 1, literal)
    return ''.join(result)


def check_directives(path: str, source: str) -> None:
    stack = []
    for number, line in enumerate(mask_non_code(source).splitlines(), 1):
        if not line.lstrip().startswith('#') and INLINE.search(line):
            raise ValueError(f'{path}:{number}: conditional directive is not on its own line')
        match = DIRECTIVE.match(line)
        if not match:
            continue
        kind = match.group(1)
        if kind in ('if', 'ifdef', 'ifndef'):
            stack.append((number, False))
        elif kind == 'endif':
            if not stack:
                raise ValueError(f'{path}:{number}: unmatched #endif')
            stack.pop()
        elif not stack:
            raise ValueError(f'{path}:{number}: unmatched #{kind}')
        elif kind == 'else':
            if stack[-1][1]:
                raise ValueError(f'{path}:{number}: repeated #else')
            stack[-1] = (stack[-1][0], True)
        elif stack[-1][1]:
            raise ValueError(f'{path}:{number}: #elif after #else')
    if stack:
        raise ValueError(f'{path}:{stack[-1][0]}: unterminated conditional')


class BalanceTests(unittest.TestCase):
    def test_rejects_inline_and_unterminated_directives(self):
        for source in ('#if ARM\nx();#else\n#endif\n', '#if ARM\nx();\n',
                       '#if ARM\n#else\n#elif IOS\n#endif\n'):
            with self.assertRaises(ValueError):
                check_directives('fixture.cpp', source)

    def test_accepts_nested_directives(self):
        check_directives('fixture.cpp', '#ifdef ARM\n#if IOS\n#else\n#endif\n#endif\n')

    def test_accepts_emitted_glsl_directives(self):
        # FragmentProgramDecompiler.cpp emits these GLSL lines as C++ data.
        check_directives('fixture.cpp', r'''
OS << "#if 0\n";
OS << main << "\n";
OS << "#endif\n";
#ifdef RPCS3_IOS
OS << "escaped quote: \" #else /* text */";
auto hash = '#';
auto quote = '\'';
auto slash = '\\';
#endif
''')

    def test_accepts_raw_strings_with_delimiters_and_prefixes(self):
        for prefix in ('', 'u8', 'u', 'U', 'L'):
            with self.subTest(prefix=prefix):
                check_directives('fixture.cpp', prefix + '''R"shader(
#else
" // /* not C++ comments or directives
)" is not the custom closing delimiter
#endif
)shader";
#if REAL
#endif
''')
        check_directives('fixture.cpp', 'auto s = R"(\n#if GLSL\n#endif\n)";\n')

    def test_raw_string_closing_delimiter_is_not_line_spliced(self):
        check_directives('fixture.cpp', 'auto s = R"tag(\n)tag\\\n" #else\n#endif\n)tag";\n')

    def test_comments_and_spliced_line_comments(self):
        check_directives('fixture.cpp', '''// x();#else
/* #if IGNORE
#endif
*/ #if REAL
// Continue comment \\
#else
/\\
/ A second spliced comment \\
#endif
/* More #if text */ #endif
''')

    def test_digit_separators_do_not_hide_real_directives(self):
        check_directives('fixture.cpp', "auto a = 1'000; auto b = 0xAB'CD;\n#if REAL\n#endif\n")
        with self.assertRaisesRegex(ValueError, r'fixture.cpp:2: unmatched #endif'):
            check_directives('fixture.cpp', "auto a = 1'000;\n#endif\n")

    def test_prefixed_literals_do_not_hide_following_directives(self):
        for prefix in ('', 'u8', 'u', 'U', 'L'):
            for literal in ("'a'", r"'\''", r"'\\'", '"#else"'):
                source = 'auto value = ' + prefix + literal + ';\n'
                with self.subTest(prefix=prefix, literal=literal):
                    check_directives('fixture.cpp', source + '#if REAL\n#endif\n')
                    with self.assertRaisesRegex(ValueError, r'fixture.cpp:2: unmatched #endif'):
                        check_directives('fixture.cpp', source + '#endif\n')

    def test_rejects_real_directives_after_literal_or_code(self):
        for source in ('#if X\nx(); /* comment */ #else\n#endif\n',
                       '#if X\n"text" #else\n#endif\n',
                       '#if X\n\'#\' #else\n#endif\n',
                       '#if X\nR"(payload\n)" #else\n#endif\n',
                       '#if X\n#else\n#else\n#endif\n'):
            with self.subTest(source=source), self.assertRaises(ValueError):
                check_directives('fixture.cpp', source)

    def test_preserves_physical_line_numbers(self):
        source = 'auto s = R"tag(\r\n#if text\r\n)tag";\r\n/* comment\r\n*/\r\nx();#else\r\n'
        masked = mask_non_code(source)
        self.assertEqual(len(masked), len(source))
        self.assertEqual([i for i, char in enumerate(masked) if char in '\r\n'],
                         [i for i, char in enumerate(source) if char in '\r\n'])
        with self.assertRaisesRegex(ValueError, r'fixture.cpp:6: conditional directive'):
            check_directives('fixture.cpp', source)


if __name__ == '__main__':
    if len(sys.argv) == 1:
        unittest.main()
    elif len(sys.argv) == 2:
        source = Path(sys.argv[1])
        manifest = json.loads((ROOT / 'build-utils/rpcs3/canonical-source.json').read_text())
        checked = 0
        for relative in manifest['files_sha256']:
            if Path(relative).suffix in ('.cpp', '.h', '.hpp'):
                check_directives(relative, (source / relative).read_text())
                checked += 1
        print(f'PASS: conditional directives in {checked} materialized Core files')
    else:
        raise SystemExit('usage: rpcs3_preprocessor_balance_test.py [rpcs3-source-root]')
