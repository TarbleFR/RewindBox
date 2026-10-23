"""The Core provenance gate accepts both observed YAML scalar representations."""
import json
from pathlib import Path
import re
import subprocess
import unittest
from neo_swap_core_pin_test import CORE_INPUTS, workflow_source_text

ROOT=Path(__file__).resolve().parents[1]
BASE='555603e541dc586b60d27cac28b38e62f7df12a0'

def paths(text):
    block=workflow_source_text(text).split('# RPCS3_CORE_INPUTS_BEGIN',1)[1].split('# RPCS3_CORE_INPUTS_END',1)[0]
    return re.findall(r'(?:build-utils|test|packages|native|\.github)/[^\s\\]+',block)

class WorkflowFormatTests(unittest.TestCase):
    def test_real_literal_and_real_quoted_workflows_keep_exact_input_sequence(self):
        old=subprocess.check_output(['git','show',BASE+':.github/workflows/retroarch-delivery.yml'],cwd=ROOT,text=True)
        current=(ROOT/'.github/workflows/retroarch-delivery.yml').read_text()
        self.assertEqual(paths(old),list(CORE_INPUTS))
        self.assertEqual(paths(current),list(CORE_INPUTS))
        self.assertEqual(paths(json.dumps(old)),list(CORE_INPUTS))

    def test_escaped_assertion_wrap_keeps_the_required_abi_value(self):
        assertion="assert identity['neoswap_relay_client_stats_abi'] == 1"
        quoted=assertion.replace(' ==','\\\n        \\ ==')
        self.assertEqual(workflow_source_text(quoted),assertion)
        self.assertNotIn(assertion,workflow_source_text(quoted.replace('== 1','== 0')))

    def test_missing_marker_or_path_is_not_reconstructed(self):
        body='# RPCS3_CORE_INPUTS_BEGIN\ntest/a.py\n# RPCS3_CORE_INPUTS_END'
        self.assertEqual(paths(body),['test/a.py'])
        with self.assertRaises(IndexError):paths(body.replace('RPCS3_CORE_INPUTS_BEGIN','REMOVED'))
        self.assertEqual(paths(body.replace('test/a.py','')),[])

if __name__=='__main__':unittest.main()
