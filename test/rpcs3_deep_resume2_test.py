#!/usr/bin/env python3
"""Run the actual chained 24-mode checkpoint through the existing corruption controls."""
import functools
import shutil
import unittest
import rpcs3_deep_resume_test as original
import rpcs3deep_resume as first
import rpcs3deep_resume2 as second

# Commit-qualified immutable reads can be shared by these metadata-only tests.
original.gate.at=functools.lru_cache(maxsize=None)(original.gate.at)
original.resume=second


class Resume2Tests(original.ResumeTests):
    def setUp(self):
        super().setUp()
        shutil.copytree(original.ROOT/first.DIRECTORY,self.root/first.DIRECTORY)

    def test_real_eighteen_modes_are_reusable(self):
        proof=self.check()
        self.assertEqual(len(proof['tests']),24)
        self.assertEqual(sum('reused_from'in s for s in proof['tests'].values()),18)


if __name__=='__main__':unittest.main()
