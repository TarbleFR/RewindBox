#!/usr/bin/env python3
"""Execute the pinned Dolphin AR decoder, without rebuilding an emulator.

Usage: python3 test/unified_native_dolphin_ar_test.py /path/to/dolphin/source
The argument may instead be a folder containing ARDecrypt.cpp and ARDecrypt.h.
Only logging, integer aliases, uppercase and byte-swap dependencies are stubbed.
The complete original decryption/parity/CRC implementation remains unchanged.
"""
from pathlib import Path
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
VECTORS = json.loads((ROOT / 'test/unified_native_dolphin_ar_vectors.json').read_text())


def check(source: Path):
    if (source / 'Source/Core/Core/ARDecrypt.cpp').is_file():
        source = source / 'Source/Core/Core'
    for name, expected in VECTORS['engine_source']['files'].items():
        assert hashlib.sha256((source / name).read_bytes()).hexdigest() == expected, name
    compiler = shutil.which('clang++') or shutil.which('g++')
    assert compiler, 'A C++20 compiler is required'
    with tempfile.TemporaryDirectory(prefix='unified-native-ar-') as tmp:
        work = Path(tmp)
        include = work / 'include'
        (include / 'Common').mkdir(parents=True)
        (include / 'Core').mkdir()
        shutil.copyfile(source / 'ARDecrypt.h', include / 'Core/ARDecrypt.h')
        stubs = {
            'Common/CommonTypes.h': '#include <cstdint>\nusing u8=uint8_t;using u16=uint16_t;using u32=uint32_t;using u64=uint64_t;\n',
            'Common/Swap.h': '#include "Common/CommonTypes.h"\nnamespace Common {inline u32 swap32(u32 n){return __builtin_bswap32(n);}}\n',
            'Common/StringUtil.h': '#include <string>\n#include <cctype>\nnamespace Common {inline void ToUpper(std::string* s){for(char& c:*s)c=std::toupper((unsigned char)c);}}\n',
            'Common/MsgHandler.h': '#include <stdexcept>\ntemplate<typename... T> void PanicAlertFmtT(const char*,T...){throw std::runtime_error("parity failure");}\n',
            'Core/ActionReplay.h': '#include "Common/CommonTypes.h"\nnamespace ActionReplay {struct AREntry{u32 cmd_addr,value; AREntry(u32 a,u32 v):cmd_addr(a),value(v){}};}\n',
        }
        for name, contents in stubs.items():
            (include / name).write_text('#pragma once\n' + contents)
        # Including the unchanged source makes its internal parity and CRC
        # functions directly testable in this translation unit.
        (work / 'driver.cpp').write_text('''#include <iostream>
#include <iomanip>
#include "ARDecrypt.cpp"
int main(){try{
  std::vector<std::string> codes; std::string line;
  while(std::getline(std::cin,line)) codes.push_back(line);
  std::array<u32,1200> binary{};
  auto parity=ActionReplay::alphatobin(binary.data(),codes,codes.size());
  bool crc=parity==0&&ActionReplay::batchdecrypt(binary.data(),codes.size()*2);
  std::cout<<"PARITY "<<parity<<" CRC "<<crc<<"\\n";
  std::vector<ActionReplay::AREntry> ops; ActionReplay::DecryptARCode(codes,&ops);
  for(auto op:ops) std::cout<<std::uppercase<<std::hex<<std::setw(8)<<std::setfill('0')
      <<op.cmd_addr<<" "<<std::setw(8)<<op.value<<"\\n";
}catch(...){return 2;}}
''')
        executable = work / 'ar-decrypt'
        subprocess.run([compiler, '-std=c++20', '-I', str(include), '-I', str(source),
                        str(work / 'driver.cpp'), '-o', str(executable)], check=True)
        for vector in VECTORS['vectors']:
            encrypted = '\n'.join(row.replace('-', '') for row in vector['encrypted'])
            actual = subprocess.check_output([str(executable)], input=encrypted, text=True).splitlines()
            assert actual == ['PARITY 0 CRC 1', *vector['decrypted']], (vector['name'], actual)
        # A one-bit parity error must never be accepted as the same program.
        corrupted = VECTORS['vectors'][0]['encrypted'][0].replace('-', '')
        corrupted = corrupted[:-1] + '2'  # original ends in 3: flip the parity bit.
        failed = subprocess.run([str(executable)], input=corrupted, text=True,
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        assert failed.returncode != 0
    print('PASS: four complete encrypted AR blocks, real pinned Dolphin parity+CRC+decryption; damaged block rejected.')


if __name__ == '__main__':
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    if sys.argv[1] == '--fetch':
        origin = VECTORS['engine_source']
        with tempfile.TemporaryDirectory(prefix='unified-native-ar-source-') as tmp:
            source = Path(tmp)
            for name in origin['files']:
                url = (origin['repository'].replace('github.com/', 'raw.githubusercontent.com/')
                       + '/' + origin['revision'] + '/Source/Core/Core/' + name)
                with urllib.request.urlopen(url, timeout=30) as response:
                    content = response.read(256 * 1024 + 1)
                assert len(content) <= 256 * 1024, 'Decoder source exceeds the expected bound'
                (source / name).write_bytes(content)
            check(source)
    else:
        check(Path(sys.argv[1]))
