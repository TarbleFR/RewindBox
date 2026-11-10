"""Do not retain completed IPC clients inside a server's reusable request pool.

All five existing return sites stay after their original completion/cleanup.
Only managed references are cleared; native reference counts, buffer unmapping,
reply values, descriptor-table storage and the request object itself are kept.
"""
from adapt_session import once


def apply(source):
    request = source / 'src/Ryujinx.HLE/HOS/Kernel/Ipc/KSessionRequest.cs'
    once(request, '''        public KSessionRequest Set(
''', '''        public KSessionRequest ClearReferences()
        {
            // Completion has finished before a request goes back to its pool.
            // Keep its reusable descriptor storage, not its former participants.
            ClientThread = null;
            ServerProcess = null;
            AsyncEvent = null;
            return this;
        }

        public KSessionRequest Set(
''')
    server = source / 'src/Ryujinx.HLE/HOS/Kernel/Ipc/KServerSession.cs'
    text = server.read_text(encoding='utf-8-sig')
    before = 'RequestPool.Release(request);'
    assert text.count(before) == 5, 'Unexpected IPC request-return sites'
    server.write_text(text.replace(before, 'RequestPool.Release(request.ClearReferences());'), encoding='utf-8')
    return [request, server]
