"""Drain disk-cache translation workers before a failed load can release memory.

A backend error can escape LoadShaders while eight translators still use its
GPU context. Complete the existing queue and join every successfully started
thread in finally. Preserve the three recoverable cache errors, queued work,
translation policy, cache rebuilds and the original exception on failure.
"""
import hashlib
from adapt_session import once


RELATIVE = 'src/Ryujinx.Graphics.Gpu/Shader/DiskCache/ParallelDiskCacheLoader.cs'
BASELINE = '477fe022ac61f0acddeaa2c3becff3f7d1ff153209f3a63b88e0ce6b0e3b4fc2'


def apply(source):
    path = source / RELATIVE
    assert hashlib.sha256(path.read_bytes()).hexdigest() == BASELINE, str(path)

    load = '''            for (int index = 0; index < ThreadCount; index++)
            {
                workThreads[index].Start(_cancellationToken);
            }

            try
            {
                _hostStorage.LoadShaders(_context, this);
            }
            catch (DiskCacheLoadException diskCacheLoadException)
            {
                Logger.Warning?.Print(LogClass.Gpu, $"Error loading the shader cache. {diskCacheLoadException.Message}");

                // If we can't even access the file, then we also can't rebuild.
                if (diskCacheLoadException.Result != DiskCacheLoadResult.NoAccess)
                {
                    _needsHostRegen = true;
                }
            }
            catch (InvalidDataException invalidDataException)
            {
                Logger.Warning?.Print(LogClass.Gpu, $"Error decompressing the shader cache file. {invalidDataException.Message}");
                _needsHostRegen = true;
            }
            catch (IOException ioException)
            {
                Logger.Warning?.Print(LogClass.Gpu, $"Error reading the shader cache file. {ioException.Message}");
                _needsHostRegen = true;
            }'''
    drain = '''            _asyncTranslationQueue.CompleteAdding();

            for (int index = 0; index < ThreadCount; index++)
            {
                workThreads[index].Join();
            }'''
    started = load.replace('                workThreads[index].Start(_cancellationToken);',
                           '                workThreads[index].Start(_cancellationToken);\n                startedThreads++;')
    guarded = '\n'.join('    ' + line if line else '' for line in started.split('\n'))
    once(path, load + '\n\n' + drain,
         '''            int startedThreads = 0;

            try
            {
''' + guarded + '''
            }
            finally
            {
                // A failed load must not outlive translations that still use
                // this context. Drain submitted work before publishing failure.
                _asyncTranslationQueue.CompleteAdding();

                for (int index = 0; index < startedThreads; index++)
                {
                    workThreads[index].Join();
                }
            }''')
    return [path]
