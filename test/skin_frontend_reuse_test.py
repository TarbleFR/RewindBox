import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location('reuse', Path(__file__).resolve().parents[1] / 'build-utils/reuse_skin_frontend.py')
reuse = importlib.util.module_from_spec(spec)
spec.loader.exec_module(reuse)


class ReuseTest(unittest.TestCase):
    def test_closed_tree_rejects_changes_additions_deletions_and_modes(self):
        original = {'packages/test.h': '100644 blob abc', 'test/fixture': '100644 blob def'}
        for changed in ({'packages/test.h': '100644 blob bad', 'test/fixture': '100644 blob def'},
                        {**original, 'new-input': '100644 blob def'},
                        {'packages/test.h': original['packages/test.h']},
                        {**original, 'test/fixture': '120000 blob def'}):
            self.assertFalse(reuse.same_inputs(original, changed))
        self.assertTrue(reuse.same_inputs(original, {**original,
            'packages/libretro_internal_bridge/ios/Classes/LibretroSkinRenderer.m': '100644 blob new'}))

    def test_only_the_exact_successful_phase_can_be_reused(self):
        run = {'head_sha': reuse.REFERENCE, 'status': 'completed', 'conclusion': 'failure'}
        steps = [{'name': n, 'status': 'completed', 'conclusion': 'success'} for n in
                 ['Frontend behaviour and pressure pixel tests', 'Run maxim-lobanov/setup-xcode@v1']]
        jobs = {'jobs': [{'name': 'native', 'conclusion': 'failure', 'steps': steps}]}
        self.assertTrue(reuse.phase_passed(run, jobs))
        for state in ['failure', 'skipped', 'cancelled', None]:
            steps[0]['conclusion'] = state
            self.assertFalse(reuse.phase_passed(run, jobs))
        steps[0]['conclusion'] = 'success'
        self.assertFalse(reuse.phase_passed({**run, 'head_sha': 'another'}, jobs))
        self.assertFalse(reuse.phase_passed({**run, 'status': 'in_progress'}, jobs))


if __name__ == '__main__':
    unittest.main()
