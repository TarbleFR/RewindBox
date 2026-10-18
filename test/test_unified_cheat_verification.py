import copy
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools" / "cheats"))
from unified_verification import apply_gba_proof, digest
from unified_catalogue import review_program


class NativeProofBinding(unittest.TestCase):
    def fixture(self):
        master = {"id":"master", "name":"Master", "code":"72BC6DFB E9CA5465\nA47FB2DC 1AF3CA86",
                  "dialect":"gba-unknown", "status":"unresolved", "reason":"gba-dialect-not-attested", "dependencies":[], "parameters":[]}
        child = {"name":"Encounter", "code":"17543C48 E65E0B97\nAD86124F 2823D8DA", "dialect":"gba-unknown",
                 "status":"unresolved", "reason":"gba-dialect-not-attested", "dependencies":["master"], "parameters":[]}
        game = {"title":"Game (USA)", "system":"gba", "identities":[], "status":"unresolved",
                "reason":"missing-explicit-identity", "cheats":[master,child]}
        proof = {"engine_revision":"a"*40, "engine_repository":"https://example.invalid/native", "programs":[]}
        for item, closure in ((master,master["code"]),(child,master["code"]+"\n"+child["code"])):
            proof["programs"].append({"source_id":"source", "title":game["title"], "name":item["name"],
                "program_code":item["code"], "program_sha256":digest(item["code"]), "complete_program_sha256":digest(closure),
                "dependency_ids":item["dependencies"], "eligible":True, "native_channel":"gba-auto", "parameters_present":False,
                "trace":{"accepted":len(closure.splitlines()), "total":len(closure.splitlines()), "incomplete":False,"remaining_addresses":0}})
        return game, proof

    def test_exact_bytes_and_whole_dependency_closure_bind_the_proof(self):
        game,proof=self.fixture();apply_gba_proof([game],"source",proof,"b"*64)
        self.assertEqual([p["status"] for p in game["cheats"]],["available","available"])
        self.assertTrue(all(p["mgba_auto_isolated"] for p in game["cheats"]))
        self.assertEqual(game["cheats"][1]["dependencies"],["master"])
        self.assertTrue(game["edition_confirmation_required"])
        for failure in ("changed-byte","changed-closure","missing-master","invalid-source","parameters"):
            game,proof=self.fixture()
            if failure=="changed-byte":game["cheats"][1]["code"]+="\n00000000 00000000"
            if failure=="changed-closure":proof["programs"][1]["complete_program_sha256"]="0"*64
            if failure=="missing-master":game["cheats"].pop(0)
            if failure=="invalid-source":game["cheats"][1]["status"]="invalid"
            if failure=="parameters":game["cheats"][1]["parameters"]=[{"name":"value"}]
            apply_gba_proof([game],"source",proof,"b"*64)
            self.assertNotEqual(game["cheats"][-1]["status"],"available",failure)

    def test_decoder_proof_does_not_override_a_separate_edition_ambiguity(self):
        game,proof=self.fixture();game["reason"]="source-region-not-established"
        apply_gba_proof([game],"source",proof,"b"*64)
        self.assertEqual(game["status"],"unresolved")
        self.assertEqual(game["cheats"][0]["dialect"],"gba-unknown")

    def test_decoder_proof_preserves_explicit_confirmation_for_an_opaque_hash(self):
        game,proof=self.fixture()
        game['identities']=[{'type':'md5','scheme':'openemu-md5-unspecified','value':'a'*32}]
        game['edition_confirmation_required']=True
        apply_gba_proof([game],'source',proof,'b'*64)
        self.assertTrue(game['edition_confirmation_required'])

    def test_vba_profile_preserves_rom_word_and_ram_byte_values(self):
        code="08067bf8:fc02f317\n0200e924:96\n03000000:0096"
        result=review_program({"name":"Native VBA", "code":code,"dialect":"gba-vba-raw"},"gba",{"gba"})
        self.assertEqual(result["status"],"available")
        self.assertEqual(result["code"],code.upper())
        for code in ("06000000:96","0203FFFF:0096"):
            self.assertEqual(review_program({"name":"Outside reviewed span","code":code,"dialect":"gba-vba-raw"},"gba",{"gba"})["status"],"requires_engine")


if __name__=="__main__":unittest.main()
