import gzip
import io
import json
import sys
import tarfile
import unittest
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'/'cheats'))
from unified_reserve import parse_vita, parse_atmosphere, parse_switch_json, parse_cemu_archive


class ReservedFormats(unittest.TestCase):
    def test_vita_native_opcodes_not_renamed_action_replay(self):
        g=parse_vita(b'# Title: Game\n# Version: 1.00\n_V0 Money\n$0200 81000000 00000063\n',{'path':'db/PCSB00041.psv'})[0]
        self.assertEqual(g['identities'][0]['value'],'PCSB00041')
        self.assertEqual(g['cheats'][0]['dialect'],'vitacheat')
        self.assertEqual(g['cheats'][0]['status'],'requires_engine')
        self.assertTrue(g['cheats'][0]['code'].startswith('$0200'))

    def test_switch_build_id_and_no_activation(self):
        g=parse_atmosphere(b'[Money]\n04000000 01234567 00000063\n',{'path':'titles/0100000000010000/cheats/1234567890ABCDEF.txt'})[0]
        self.assertEqual([i['value'] for i in g['identities']],['0100000000010000','1234567890ABCDEF'])
        self.assertEqual(g['cheats'][0]['status'],'requires_engine')

    def test_switch_json_attribution_not_build_or_program(self):
        payload={'attribution':{'Author':'Someone'},'1234567890ABCDEF':{'Money':['04000000 01234567 00000063']}}
        records=parse_switch_json(json.dumps(payload).encode(),{'path':'0100000000010000.json'})
        self.assertEqual(len(records),1)
        self.assertEqual(len(records[0]['cheats']),1)
        self.assertEqual(records[0]['cheats'][0]['attribution'],payload['attribution'])

    def test_cemu_keeps_rules_and_patches_and_excludes_graphics(self):
        stream=io.BytesIO()
        files={'root/src/Game/Cheats/Stamina/rules.txt':'[Definition]\nname = Stamina\ntitleIds = 00050000101C9300\nversion = 6\n',
               'root/src/Game/Cheats/Stamina/patches.txt':'[Build]\nmoduleMatches = 0x12345678\n0x1234 = nop\n',
               'root/src/Game/Graphics/Resolution/rules.txt':'name = Resolution\ntitleIds = 00050000101C9300'}
        with tarfile.open(fileobj=stream,mode='w:gz') as archive:
            for name,body in files.items():
                b=body.encode();entry=tarfile.TarInfo(name);entry.size=len(b);archive.addfile(entry,io.BytesIO(b))
        records=parse_cemu_archive(stream.getvalue(),{})
        self.assertEqual(len(records),1)
        self.assertEqual(records[0]['revision'],'')
        self.assertEqual(set(records[0]['cheats'][0]['native_document']['files']),{'rules.txt','patches.txt'})
        self.assertEqual(records[0]['cheats'][0]['status'],'requires_engine')


if __name__=='__main__':unittest.main()
