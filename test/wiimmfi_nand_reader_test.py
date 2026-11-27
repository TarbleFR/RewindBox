"""Execute the patched reader's actual filesystem validator with hostile fixtures.

No game, key, console identity, NAND dump or network is used.
"""
import argparse
import shutil
import subprocess
import tempfile
from pathlib import Path


def function(source, signature):
    start = source.index(signature)
    return source[start:source.index('\n}', start) + 2]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--upstream', type=Path, required=True)
    args = parser.parse_args()
    source = (args.upstream / 'Source/Core/DiscIO/NANDImporter.cpp').read_text()
    assert 'RewindBox bounded BootMii import' in source
    harness = r'''
#include <algorithm>
#include <array>
#include <cassert>
#include <cctype>
#include <cstdint>
#include <cstring>
#include <functional>
#include <memory>
#include <set>
#include <stdexcept>
#include <string>
using u16 = uint16_t;
namespace DiscIO {
class NANDImporter {
public:
  struct NANDFSTEntry { char name[12]{}; uint8_t mode=2; u16 sub=0xffff,sib=0xffff; uint32_t size=0; };
  struct Super { std::array<NANDFSTEntry,0x17ff> fst; std::array<u16,0x8000> fat{}; };
  std::unique_ptr<Super> m_superblock = std::make_unique<Super>();
  std::array<bool,0x17ff> m_seen{};
  std::array<bool,0x8000> m_clusters{};
  size_t m_entry_count=0, m_extracted_bytes=0;
  std::function<void()> m_update_callback=[]{};
  std::string GetPath(const NANDFSTEntry&, const std::string&);
  void ValidateEntries(u16,const std::string&,size_t);
  NANDImporter() { std::strcpy(m_superblock->fst[0].name,"/"); }
  void add(int index,const char* name,int type=2,u16 sub=0xffff,uint32_t size=0) {
    auto& e=m_superblock->fst[index]; std::strncpy(e.name,name,12); e.mode=type; e.sub=sub; e.size=size;
  }
};
'''
    harness += function(source, 'std::string NANDImporter::GetPath(') + '\n'
    harness += function(source, 'void NANDImporter::ValidateEntries(') + '\n}\n'
    harness += r'''
using DiscIO::NANDImporter;
template<class F> void rejects(F mutate) {
  NANDImporter n; mutate(n); bool refused=false;
  try { n.ValidateEntries(0,"",0); } catch(const std::runtime_error&) {refused=true;}
  assert(refused);
}
int main() {
  { NANDImporter n; n.m_superblock->fst[0].sub=1; n.add(1,"title",2,2);
    n.add(2,"save.bin",1,5,0x4001); n.m_superblock->fat[5]=6;
    n.ValidateEntries(0,"",0); assert(n.m_entry_count==3 && n.m_extracted_bytes==0x4001); }
  rejects([](auto& n){n.add(0,"");});
  rejects([](auto& n){n.add(0,"notroot");});
  rejects([](auto& n){n.m_superblock->fst[0].sub=0x17ff;});
  rejects([](auto& n){n.m_superblock->fst[0].sub=0;});
  rejects([](auto& n){n.m_superblock->fst[0].sub=1;n.add(1,"../escape");});
  rejects([](auto& n){n.m_superblock->fst[0].sub=1;n.add(1,"..");});
  rejects([](auto& n){n.m_superblock->fst[0].sub=1;n.add(1,"a\\b");});
  rejects([](auto& n){n.m_superblock->fst[0].sub=1;n.add(1,"a:b");});
  rejects([](auto& n){n.m_superblock->fst[0].sub=1;n.add(1,"SAVE");n.m_superblock->fst[1].sib=2;n.add(2,"save");});
  rejects([](auto& n){n.m_superblock->fst[0].sub=1;n.add(1,"x",0);});
  rejects([](auto& n){n.m_superblock->fst[0].sub=1;n.add(1,"x",1,0x7f00,1);});
  rejects([](auto& n){n.m_superblock->fst[0].sub=1;n.add(1,"x",1,5,0x4001);n.m_superblock->fat[5]=5;});
  rejects([](auto& n){n.m_superblock->fst[0].sub=1;n.add(1,"x",1,5,1);n.m_superblock->fst[1].sib=2;n.add(2,"y",1,5,1);});
  rejects([](auto& n){n.m_superblock->fst[0].sub=1;n.add(1,"x",1,5,0x20000001);});
  rejects([](auto& n){for(int i=0;i<66;++i)n.m_superblock->fst[i].sub=i+1;for(int i=1;i<67;++i)n.add(i,"dir",2,i<66?i+1:0xffff);});
  rejects([](auto& n){n.m_update_callback=[]{throw std::runtime_error("cancelled");};});
}
'''
    with tempfile.TemporaryDirectory() as temp:
        cpp = Path(temp) / 'nand.cpp'
        binary = Path(temp) / 'nand'
        cpp.write_text(harness)
        compiler = shutil.which('clang++') or shutil.which('c++')
        if not compiler:
            raise SystemExit('C++ compiler required for the BootMii validator')
        subprocess.run([compiler, '-std=c++20', '-fsanitize=address,undefined',
                        '-fno-omit-frame-pointer', str(cpp), '-o', str(binary)], check=True)
        subprocess.run([str(binary)], check=True)
    print('PASS: actual BootMii validator, 1 valid + 16 hostile/cancel fixtures, ASan/UBSan')


if __name__ == '__main__':
    main()
