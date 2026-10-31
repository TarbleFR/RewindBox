"""Execute the real Dolphin presentation callback implementation on the host."""
import argparse
import importlib.util
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--upstream', type=Path)
    args = parser.parse_args()
    spec = importlib.util.spec_from_file_location('dolphin_patch', ROOT / 'build-utils/patch_dolphin_internal_core_v2.py')
    patch = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(patch)
    if args.upstream:
        original = (args.upstream / 'Source/Core/Core/AchievementManager.cpp').read_bytes()
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder) / 'Source/Core/Core/AchievementManager.cpp'
            target.parent.mkdir(parents=True)
            target.write_bytes(original)
            patch.patch_achievement_presentation(Path(folder))
            first = target.read_bytes()
            patch.patch_achievement_presentation(Path(folder))
            assert target.read_bytes() == first, 'Patch is not idempotent'
            code = first.decode()
            assert code.count('neostation_dolphin_present_achievement(') == 4
            assert code.count('m_update_callback') == original.decode().count('m_update_callback')
            assert code.count('rc_client_set_hardcore_enabled') == original.decode().count('rc_client_set_hardcore_enabled')
            print('Pinned source patch: applied twice, callbacks and Hardcore configuration preserved')
    with tempfile.TemporaryDirectory() as folder:
        folder = Path(folder)
        source = folder / 'presenter.cpp'
        include = ROOT / 'packages/dolphin_internal_bridge/core/NeoStationAchievementPresentation.inc'
        source.write_text('#include "' + str(include) + '"\n' + r'''
#include <cassert>
#include <atomic>
#include <string>
#include <thread>
std::atomic<int> errors{0};
std::atomic<int> calls{0};
std::string copied;
static void capture(uint64_t session,uint32_t id,const char* title,const char* description,
                    uint32_t points,const char* progress,int kind) {
  assert(session==42 && id==17 && points==25 && kind==1);
  assert(std::string(description)=="requirements" && std::string(progress)=="3/5");
  copied=title; ++calls;
}
static void even(uint64_t session,uint32_t,const char*,const char*,uint32_t,const char*,int) {
  if (session % 2) ++errors;
  ++calls;
}
static void odd(uint64_t session,uint32_t,const char*,const char*,uint32_t,const char*,int) {
  if (!(session % 2)) ++errors;
  ++calls;
}
int main() {
  assert(!neostation_dolphin_present_achievement(17,"original","requirements",25,"3/5",1));
  neostation_dolphin_set_achievement_presenter(capture,42);
  char title[]="original";
  assert(neostation_dolphin_present_achievement(17,title,"requirements",25,"3/5",1));
  title[0]='X'; assert(copied=="original");
  neostation_dolphin_set_achievement_presenter(nullptr,0);
  assert(!neostation_dolphin_present_achievement(17,title,"requirements",25,"3/5",1));
  assert(calls==1);
  std::thread writer([] { for (uint64_t i=1;i<10000;++i)
      neostation_dolphin_set_achievement_presenter(i%2?odd:even,i); });
  std::thread reader([] { for(int i=0;i<10000;++i)
      neostation_dolphin_present_achievement(17,"t","d",25,"3/5",2); });
  writer.join(); reader.join(); assert(errors==0);
  neostation_dolphin_set_achievement_presenter(nullptr,0);
}
''')
        compiler = os.environ.get('CXX') or shutil.which('clang++') or shutil.which('g++')
        assert compiler, 'A real C++ compiler is required'
        output = folder / 'presenter'
        subprocess.run([compiler, '-std=c++17', '-Wall', '-Wextra', '-Werror', '-pthread', str(source), '-o', str(output)], check=True)
        subprocess.run([str(output)], check=True)
        print('Native presenter: real compile and runtime passed; copied payload, unregistration, concurrent callback/token pairing')

if __name__ == '__main__': main()
