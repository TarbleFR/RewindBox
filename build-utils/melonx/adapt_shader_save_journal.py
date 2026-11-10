"""Durable counters of the shader disk-cache saves (does the cache learn the shaders compiled in play?).

IPA 666 (MeloNX Core 663), private journals, not in the repository: Hogwarts Legacy loads "759 shaders from the cache"
in every session from 2026-11-05 15:24 to 20:55 UTC (Super Smash Bros. Ultimate: 3322), while the 21-minute session
pid 15186 ended with 1238 programs: about 450 programs were translated, converted and compiled in play. The render
thread spent 199 s of that session's 1259 s creating pipelines (114.6 s graphics, 84.7 s compute; 40 five-second
windows with more than 2 s of it), the stutter the maintainer reports in fights and animations. A program saved to
the disk cache is loaded and warmed in the background at the next launch instead.

Every Hogwarts session between those two loads ended within 30 s of its start (IPA 662 deaths, the IPA 666 JIT arena
abort), and a review of the save path in the Core 663 preparation found it correct (ShaderCache.EnqueueProgramToSave
for every program made in play, ProcessShaderCacheQueue on every GPU loop pass, one append per program to the shared,
guest and host files) apart from the save queue left unwritten at teardown. Whether in-play programs reach the disk is
therefore undecided from the journals: the next launch's count and these counters decide it.

Change (ShaderCache.cs, every title, no behaviour change): counts of programs queued for saving in play, written,
dropped after a failed link, and the longest time a program waited at the head of the queue for its link status.
One durable core-journal line "shaderCache saves" at each 64th written program and at disposal (with the queue left
unwritten). The save order, the link checks and the writer are unchanged.
Fail closed on drift: the file must be the Core 663 preparation's.
"""
import hashlib
from adapt_session import once

BASELINE = {
    'src/Ryujinx.Graphics.Gpu/Shader/ShaderCache.cs': '913fe78c3ec15eed86940d39d2502c89ee1f440a84bbe310b580ce30274d2668',
}

FIELDS_OLD = '''        private readonly Queue<ProgramToSave> _programsToSaveQueue;
'''
FIELDS_NEW = '''        private readonly Queue<ProgramToSave> _programsToSaveQueue;

        // RewindBox (adapt_shader_save_journal): saves of programs made in play (GPU thread only).
        private int _savesQueued;
        private int _savesWritten;
        private int _savesFailed;
        private long _headWaitStart;
        private long _longestHeadWaitTicks;
'''

PROCESS_OLD = '''                if (result != ProgramLinkStatus.Incomplete)
                {
                    if (result == ProgramLinkStatus.Success)
                    {
                        _cacheWriter.AddShader(programToSave.CachedProgram, programToSave.BinaryCode ?? programToSave.HostProgram.GetBinary());
                    }

                    _programsToSaveQueue.Dequeue();
                }
                else
                {
                    break;
                }
'''
PROCESS_NEW = '''                if (result != ProgramLinkStatus.Incomplete)
                {
                    if (result == ProgramLinkStatus.Success)
                    {
                        _cacheWriter.AddShader(programToSave.CachedProgram, programToSave.BinaryCode ?? programToSave.HostProgram.GetBinary());
                        _savesWritten++;
                    }
                    else
                    {
                        _savesFailed++;
                    }

                    _programsToSaveQueue.Dequeue();
                    NoteHeadWait(System.Diagnostics.Stopwatch.GetTimestamp());
                    _headWaitStart = 0;

                    if (result == ProgramLinkStatus.Success && _savesWritten % 64 == 0)
                    {
                        RecordSaves("written");
                    }
                }
                else
                {
                    long now = System.Diagnostics.Stopwatch.GetTimestamp();

                    if (_headWaitStart == 0)
                    {
                        _headWaitStart = now;
                    }

                    NoteHeadWait(now);
                    break;
                }
'''

ENQUEUE_OLD = '''                _programsToSaveQueue.Enqueue(programToSave);
'''
ENQUEUE_NEW = '''                _programsToSaveQueue.Enqueue(programToSave);
                _savesQueued++;
'''

DISPOSE_OLD = '''            _cacheWriter?.Dispose();
        }
'''
DISPOSE_NEW = '''            if (_cacheWriter != null)
            {
                RecordSaves("disposed");
            }

            _cacheWriter?.Dispose();
        }

        // RewindBox (adapt_shader_save_journal): the longest wait at the head of the save queue so far.
        private void NoteHeadWait(long now)
        {
            if (_headWaitStart != 0 && now - _headWaitStart > _longestHeadWaitTicks)
            {
                _longestHeadWaitTicks = now - _headWaitStart;
            }
        }

        private void RecordSaves(string when)
        {
            Ryujinx.Common.EmbeddedLaunchDiagnostics.Record("shaderCache", "saves", detail: when + ": programs made in play queued " + _savesQueued +
                ", written " + _savesWritten + ", dropped after a failed link " + _savesFailed + ", still queued " + _programsToSaveQueue.Count +
                "; longest wait at the head " + (_longestHeadWaitTicks * 1000 / System.Diagnostics.Stopwatch.Frequency) + " ms");
        }
'''


def apply(source):
    paths = {name: source / name for name in BASELINE}
    for name, expected in BASELINE.items():
        assert hashlib.sha256(paths[name].read_bytes()).hexdigest() == expected, name

    cache = paths['src/Ryujinx.Graphics.Gpu/Shader/ShaderCache.cs']
    once(cache, FIELDS_OLD, FIELDS_NEW)
    once(cache, PROCESS_OLD, PROCESS_NEW)
    once(cache, ENQUEUE_OLD, ENQUEUE_NEW)
    once(cache, DISPOSE_OLD, DISPOSE_NEW)
    return list(paths.values())
