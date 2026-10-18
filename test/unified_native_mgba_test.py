#!/usr/bin/env python3
"""Run the delivered mGBA revision's real GBA cheat decoders, not an emulator.

Pass a source checkout, or --fetch to obtain the pinned source temporarily.
Optional --audit <curated.json> <delta.xlsx> --output <report.json> records
whole-program acceptance without claiming a ROM edition or gameplay effect.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
PIN = '7a12d6d4b9acb14c0ae62c9166b6a2f3d08007f6'
BINARY_SHA = 'c7026dc4d8a799be2d991faa3d4e2286011d97f9b11fb1e2ef6ba77ebca66218'
FILES = ['src/gba/cheats.c', 'src/gba/cheats/gameshark.c', 'src/gba/cheats/parv3.c',
         'src/gba/cheats/codebreaker.c', 'src/core/cheats.c', 'src/util/string.c', 'src/util/vector.c']
LIBRETRO = 'src/platform/libretro/libretro.c'
VECTORS = json.loads((ROOT / 'test/unified_native_mgba_vectors.json').read_text())
DRIVER = r'''
#include <stdio.h>
#include "src/gba/cheats.c"
void GBASetBreakpoint(struct GBA* g,struct mCPUComponent* c,uint32_t a,enum ExecutionMode m,uint32_t* o){abort();}
void GBAClearBreakpoint(struct GBA* g,uint32_t a,enum ExecutionMode m,uint32_t o){abort();}
void mLog(int c,enum mLogLevel l,const char* f,...){}
int mLogGenerateCategory(const char* a,const char* b){return 0;}
int main(){
  struct mCheatSet* set=GBACheatSetCreate(NULL,"Audit");
  struct GBACheatSet* gba=(struct GBACheatSet*)set;
  char line[512];int n=0,good=0;printf("{\"lines\":[");
  while(fgets(line,sizeof(line),stdin)){
    line[strcspn(line,"\r\n")]=0;
    int scores[4]={0};unsigned op1,op2;
    int initial=gba->gsaVersion;
    if(strlen(line)==17&&sscanf(line,"%8X %8X",&op1,&op2)==2){
      unsigned a=op1,b=op2;GBACheatDecryptGameShark(&a,&b,GBACheatGameSharkSeeds);
      scores[0]=GBACheatGameSharkProbability(a,b);a=op1;b=op2;
      GBACheatDecryptGameShark(&a,&b,GBACheatProActionReplaySeeds);
      scores[1]=GBACheatProActionReplayProbability(a,b);
      scores[2]=GBACheatGameSharkProbability(op1,op2);scores[3]=GBACheatProActionReplayProbability(op1,op2);
    }
    bool ok=mCheatAddLine(set,line,0);
    printf("%s{\"accepted\":%s,\"initial_version\":%d,\"selected_version\":%d,\"scores\":[%d,%d,%d,%d]}",
      n?",":"",ok?"true":"false",initial,gba->gsaVersion,scores[0],scores[1],scores[2],scores[3]);n++;good+=ok;
  }
  printf("],\"accepted\":%d,\"total\":%d,\"instructions\":%zu,\"rom_patches\":%zu,\"hook\":%s,\"incomplete\":%s,\"remaining_addresses\":%d,\"operations\":[",
    good,n,mCheatListSize(&set->list),mCheatPatchListSize(&set->romPatches),gba->hook?"true":"false",
    (gba->incompleteCheat!=COMPLETE||gba->incompletePatch!=NULL||gba->currentBlock!=COMPLETE)?"true":"false",gba->remainingAddresses);
  for(size_t i=0;i<mCheatListSize(&set->list);i++){
    const struct mCheat* op=mCheatListGetPointer(&set->list,i);
    printf("%s{\"type\":%d,\"width\":%d,\"address\":%u,\"operand\":%u,\"repeat\":%u}",
      i?",":"",op->type,op->width,op->address,op->operand,op->repeat);
  }
  printf("]}\n");
  mCheatSetDeinit(set);return 0;
}
'''


def compile_decoder(source, work):
    for path, expected in VECTORS['source_sha256'].items():
        assert hashlib.sha256((source / path).read_bytes()).hexdigest() == expected, path
    compiler = shutil.which('gcc') or shutil.which('clang')
    assert compiler, 'A C compiler is required'
    (work / 'driver.c').write_text(DRIVER)
    executable = work / 'decoder'
    command = [compiler, '-std=gnu11', '-ffunction-sections', '-fdata-sections',
               '-DHAVE_STRDUP', '-DHAVE_STRNDUP', '-DM_CORE_GBA', '-I', str(source / 'include'),
               '-I', str(source / 'src'), '-I', str(source), str(work / 'driver.c')]
    command += [str(source / path) for path in FILES if path != 'src/gba/cheats.c']
    command += ['-Wl,-dead_strip' if sys.platform == 'darwin' else '-Wl,--gc-sections', '-o', str(executable)]
    subprocess.run(command, check=True)
    return executable


def probe(executable, code):
    return json.loads(subprocess.check_output([str(executable)], input=code, text=True))


def reviewed(trace):
    return trace['total'] > 0 and trace['accepted'] == trace['total'] and not trace['incomplete'] and not trace['remaining_addresses']


def compile_wrapper(source, work):
    """Compile the unchanged real entry point, with a core supplying only a set."""
    original = (source / LIBRETRO).read_text()
    start = original.index('void retro_cheat_set(')
    index = original.index('{', start) + 1
    nesting = 1
    while nesting:
        nesting += (original[index] == '{') - (original[index] == '}')
        index += 1
    prefix = DRIVER[:DRIVER.index('int main(){')]
    context = r'''
static struct mCheatDevice device;
static struct mCheatDevice* getDevice(struct mCore* c){return &device;}
static enum mPlatform platform(const struct mCore* c){return mPLATFORM_GBA;}
static struct mCore fakeCore={.cheatDevice=getDevice,.platform=platform};
static struct mCore* core=&fakeCore;
'''
    main = r'''
int main(int argc,char** argv){
  mCheatSetsInit(&device.cheats,1);device.createSet=GBACheatSetCreate;
  char input[8192]={0};fread(input,1,sizeof(input)-1,stdin);
  if(argc>1)retro_cheat_set(0,true,"9A0D7A0A 1F4D");
  retro_cheat_set(1,true,input);
  struct mCheatSet* set=*mCheatSetsGetPointer(&device.cheats,0);
  printf("{\"stored_lines\":%zu,\"rom_patches\":%zu,\"operations\":[",StringListSize(&set->lines),mCheatPatchListSize(&set->romPatches));
  for(size_t i=0;i<mCheatListSize(&set->list);i++){
    const struct mCheat* op=mCheatListGetPointer(&set->list,i);
    printf("%s{\"type\":%d,\"width\":%d,\"address\":%u,\"operand\":%u}",i?",":"",op->type,op->width,op->address,op->operand);
  }
  printf("]}\n");return 0;
}
'''
    driver = work / 'wrapper.c'
    driver.write_text(prefix + context + original[start:index] + main)
    compiler = shutil.which('gcc') or shutil.which('clang')
    executable = work / 'wrapper'
    subprocess.run([compiler, '-std=gnu11', '-ffunction-sections', '-fdata-sections',
                    '-DHAVE_STRDUP', '-DHAVE_STRNDUP', '-DM_CORE_GBA',
                    '-I', str(source / 'include'), '-I', str(source / 'src'), '-I', str(source),
                    str(driver), *[str(source / path) for path in FILES if path != 'src/gba/cheats.c'],
                    '-Wl,-dead_strip' if sys.platform == 'darwin' else '-Wl,--gc-sections',
                    '-o', str(executable)], check=True)
    return executable


def audit(executable, curated_path, delta_path):
    sys.path.insert(0, str(ROOT / 'tools/cheats'))
    import unified_curated
    curated = json.loads(curated_path.read_text())['games']
    games = [game for game in curated if game.get('source_id') in
             ('xoevoox_firered', 'gameshark_event_islands', 'tyler_shiny')]
    games += [{**game, 'source_id': 'delta_workbook'} for game in
              unified_curated.parse_delta_xlsx(delta_path.read_bytes(), {})]
    records = []
    for game in games:
        by_id = {row['id']: row for row in game['cheats'] if row.get('id')}
        for program in game['cheats']:
            ordered, seen = [], set()
            def visit(row):
                key = row.get('id', str(id(row)))
                if key in seen:
                    return
                seen.add(key)
                for dependency in row.get('dependencies', []):
                    visit(by_id[dependency])
                ordered.append(row)
            try:
                visit(program)
            except KeyError:
                records.append({'name': program['name'], 'source_id': game['source_id'],
                                'eligible': False, 'reason': 'missing-dependency'})
                continue
            code = '\n'.join(row['code'] for row in ordered)
            lines = code.splitlines()
            # Do not pass templates or malformed widths to the native parser
            # as a guessed repair. VBA colon syntax is examined separately.
            pair_shape = bool(lines) and all(re.fullmatch(r'[0-9a-fA-F]{8} (?:[0-9a-fA-F]{4}|[0-9a-fA-F]{8})', line) for line in lines)
            vba_shape = bool(lines) and all(re.fullmatch(r'[0-9a-fA-F]{8}:[0-9a-fA-F]{8}', line) for line in lines)
            parameters = any(row.get('parameters') for row in ordered)
            base = {'source_id': game['source_id'], 'title': game['title'], 'name': program['name'],
                    'program_sha256': hashlib.sha256(program['code'].encode()).hexdigest(),
                    'complete_program_sha256': hashlib.sha256(code.encode()).hexdigest(),
                    'program_code': program['code'], 'complete_program_code': code,
                    'dependency_ids': program.get('dependencies', []),
                    'source_status': program.get('status', ''), 'source_reason': program.get('reason', ''),
                    'parameters_present': parameters}
            if (not pair_shape and not vba_shape) or len(lines) > 128 or len('+'.join(lines)) > 4096:
                records.append({**base, 'eligible': False, 'reason': 'template-shape-or-existing-core-boundary'})
                continue
            trace = probe(executable, code)
            records.append({**base, 'trace': trace, 'eligible': reviewed(trace) and not parameters and
                            not any(row.get('status') == 'invalid' for row in ordered),
                            'native_channel': 'vba-colon' if vba_shape else 'gba-auto',
                            'gameplay_tested': False})
    return records


def check(source, work, args):
    executable = compile_decoder(source, work)
    master = '72BC6DFB E9CA5465\nA47FB2DC 1AF3CA86'
    encounter = master + '\n17543C48 E65E0B97\nAD86124F 2823D8DA'
    trace = probe(executable, encounter)
    assert reviewed(trace) and trace['hook'] and trace['rom_patches'] == 1
    assert not reviewed(probe(executable, 'BCDC8C406 2F2FD763'))
    assert not reviewed(probe(executable, '17543C48 ????????'))
    assert not reviewed(probe(executable, '42000010 00000001'))  # incomplete CodeBreaker fill
    # This is the VBA syntax's real ROM-patch path, not a guessed AR opcode.
    raw = probe(executable, '08067BF8:FC02F317')
    assert reviewed(raw) and raw['rom_patches'] == 1
    ram = probe(executable, '3200E924 0096\n8200E924 0096')
    assert reviewed(ram) and ram['operations'] == [
        {'type': 0, 'width': 1, 'address': 0x0200E924, 'operand': 0x96, 'repeat': 1},
        {'type': 0, 'width': 2, 'address': 0x0200E924, 'operand': 0x96, 'repeat': 1}]
    for vector in VECTORS['vectors']:
        if 'complete_program_code' in vector:
            actual = probe(executable, vector['complete_program_code'])
            assert actual == vector['trace'], vector['name']
    wrapper = compile_wrapper(source, work)
    assert probe(wrapper, '0200E924:96')['operations'] == []  # 11 chars never dispatched
    payload = '0200E924:96  +0200E924:0096+0200E924:00000096'
    clean = probe(wrapper, payload)
    seeded = json.loads(subprocess.check_output([str(wrapper), 'seed'], input=payload, text=True))
    expected = [{'type': 0, 'width': width, 'address': 0x0200E924, 'operand': 0x96} for width in (1, 2, 4)]
    assert clean['operations'] == seeded['operations'] == expected
    assert clean['stored_lines'] == 3 and seeded['stored_lines'] == 4
    for vector in VECTORS['vectors']:
        if vector['native_channel'] == 'vba-colon':
            actual = probe(wrapper, '+'.join(vector['complete_program_code'].splitlines()))
            assert actual['rom_patches'] == vector['trace']['rom_patches']
    report = {'schema_version': 1, 'engine_repository': 'https://github.com/libretro/mgba',
              'engine_revision': PIN, 'delivered_binary_sha256': BINARY_SHA,
              'source_sha256': {path: hashlib.sha256((source / path).read_bytes()).hexdigest() for path in [*FILES, LIBRETRO]},
              'limits': ['AUTO uses the real core heuristic; no v1/v3 attribution invented.',
                         'Syntax acceptance is not a ROM edition or gameplay-effect proof.',
                         'Logging and unreachable breakpoint callbacks only are stubbed.'],
              'example_trace': trace,
              'vba_wrapper_proof': {'payload': payload, 'clean': clean, 'after_cb9_seed': seeded,
                                    'byte_padding': 'Two spaces after a two-hex value, before + or end of the complete program.'}}
    if args.audit:
        report['programs'] = audit(executable, *[Path(path) for path in args.audit])
    if args.output:
        Path(args.output).write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    print('PASS: real pinned mGBA AUTO and VBA decoders, complete closure, malformed instruction rejection; no core rebuilt.')
    if report.get('programs'):
        from collections import Counter
        print(json.dumps(dict(Counter((row['source_id'] + (':accepted' if row['eligible'] else ':blocked')) for row in report['programs'])), sort_keys=True))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', nargs='?', type=Path)
    parser.add_argument('--fetch', action='store_true')
    parser.add_argument('--audit', nargs=2)
    parser.add_argument('--output')
    args = parser.parse_args()
    if bool(args.source) == args.fetch:
        parser.error('choose a source checkout or --fetch')
    with tempfile.TemporaryDirectory(prefix='unified-native-mgba-') as tmp:
        work = Path(tmp)
        if args.fetch:
            archive = work / 'source.tar.gz'
            with urllib.request.urlopen('https://codeload.github.com/libretro/mgba/tar.gz/' + PIN, timeout=30) as response:
                data = response.read(32 * 1024 * 1024 + 1)
            assert len(data) <= 32 * 1024 * 1024
            archive.write_bytes(data)
            source = work / 'source'
            with tarfile.open(archive) as package:
                for member in package:
                    if not member.isfile():
                        continue
                    parts = Path(member.name).parts
                    assert parts[0] == 'mgba-' + PIN and '..' not in parts
                    path = Path(*parts[1:])
                    if str(path).startswith('include/') or str(path) in [*FILES, LIBRETRO] or str(path).startswith('src/gba/cheats/'):
                        target = source / path; target.parent.mkdir(parents=True, exist_ok=True)
                        target.write_bytes(package.extractfile(member).read())
        else:
            source = args.source
        check(source, work, args)


if __name__ == '__main__':
    main()
