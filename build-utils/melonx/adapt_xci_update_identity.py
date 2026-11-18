"""Use the launcher's application ID when identifying cartridge updates."""

import hashlib

from adapt_session import once


GAME_INFO = 'src/Ryujinx.Library/GameInfo.cs'
BASELINE = {GAME_INFO: '754dd993df600c3662224db08bccdfdb5a445043317168223617baba4a1bf74e'}


def apply(source):
    for name, expected in BASELINE.items():
        assert hashlib.sha256((source / name).read_bytes()).hexdigest() == expected, name
    path = source / GAME_INFO

    once(path, 'using LibHac.Ns;', 'using LibHac.Ns;\nusing LibHac.Ncm;')
    once(path, 'using Ryujinx.HLE.FileSystem;', '''using Ryujinx.HLE.FileSystem;
using Ryujinx.HLE.Loaders.Processes.Extensions;''')
    once(path, 'using System.IO;', 'using System.IO;\nusing System.Linq;')
    once(path, 'using System.Globalization;', 'using System.Globalization;\nusing ContentType = LibHac.Ncm.ContentType;')
    once(path, '''                            GetControlFsAndTitleId(virtualFileSystem, pfs, out IFileSystem? controlFs, out string? id);
                            gameInfo.TitleId = id;''', '''                            (Nca? program, _, Nca? control) = GetGameData(virtualFileSystem, pfs, 0);
                            string? id = (program ?? control)?.ProgramIdBase.ToString("x16");
                            IFileSystem? controlFs = control?.OpenFileSystem(NcaSectionType.Data, IntegrityCheckLevel.None);''')
    once(path, 'IsUpdateApplied(virtualFileSystem, gameInfo.TitleId, out IFileSystem? updatedControlFs)',
         'IsUpdateApplied(virtualFileSystem, program, id, out IFileSystem? updatedControlFs)')
    once(path, '''                            GetGameInformation(ref controlHolder.Value, out gameInfo.TitleName, out gameInfo.TitleId, out gameInfo.Developer, out gameInfo.Version);

                            try''', '''                            GetGameInformation(ref controlHolder.Value, out gameInfo.TitleName, out string controlTitleId, out gameInfo.Developer, out gameInfo.Version);
                            // A control's presence group or save owner can belong to a different title.
                            gameInfo.TitleId = id ?? controlTitleId;

                            try''')
    once(path, '''        private static void GetControlFsAndTitleId(VirtualFileSystem virtualFileSystem, IFileSystem pfs, out IFileSystem? controlFs, out string? titleId)
        {
            (_, _, Nca? controlNca) = GetGameData(virtualFileSystem, pfs, 0);

            if (controlNca == null)
                Logger.Warning?.Print(LogClass.Application, "Control NCA is null. Unable to load control FS.");

            controlFs = controlNca?.OpenFileSystem(NcaSectionType.Data, IntegrityCheckLevel.None);
            titleId = controlNca?.Header.TitleId.ToString("x16");
        }

''', '')
    once(path, '''            fileSystem.ImportTickets(pfs);

            foreach (DirectoryEntryEx fileEntry in pfs.EnumerateEntries("/", "*.nca"))
            {
                using var ncaFile = new UniqueRef<IFile>();
                pfs.OpenFile(ref ncaFile.Ref, fileEntry.FullPath.ToU8Span(), OpenMode.Read).ThrowIfFailure();

                Nca nca = new(fileSystem.KeySet, ncaFile.Release().AsStorage());
                int ncaProgramIndex = (int)(nca.Header.TitleId & 0xF);

                if (ncaProgramIndex != programIndex)
                    continue;

                if (nca.Header.ContentType == NcaContentType.Program)
                {
                    int dataIndex''', '''            // Match the same first application CNMT as the cartridge loader.
            var application = pfs.GetContentData(ContentMetaType.Application, fileSystem, IntegrityCheckLevel.None)
                .Values.FirstOrDefault();
            Nca? selectedProgram = application?.GetNcaByType(fileSystem.KeySet, ContentType.Program, programIndex);
            if (selectedProgram != null)
            {
                var bundled = pfs.GetContentData(ContentMetaType.Patch, fileSystem, IntegrityCheckLevel.None)
                    .Values.Where(content => (content.ApplicationId & ~0x1FFFUL) == selectedProgram.ProgramIdBase)
                    .OrderByDescending(content => content.Version.Version)
                    .FirstOrDefault();
                patchNca = bundled?.GetNcaByType(fileSystem.KeySet, ContentType.Program, programIndex);
                if (patchNca != null)
                {
                    controlNca = bundled?.GetNcaByType(fileSystem.KeySet, ContentType.Control, programIndex);
                }

                controlNca ??= application!.GetNcaByType(fileSystem.KeySet, ContentType.Control, programIndex);
                return (selectedProgram, patchNca, controlNca);
            }

            foreach (DirectoryEntryEx fileEntry in pfs.EnumerateEntries("/", "*.nca"))
            {
                using var ncaFile = new UniqueRef<IFile>();
                pfs.OpenFile(ref ncaFile.Ref, fileEntry.FullPath.ToU8Span(), OpenMode.Read).ThrowIfFailure();

                Nca nca = new(fileSystem.KeySet, ncaFile.Release().AsStorage());
                int ncaProgramIndex = (int)(nca.Header.TitleId & 0xF);

                if (ncaProgramIndex != programIndex)
                    continue;

                if (nca.Header.ContentType == NcaContentType.Program)
                {
                    int dataIndex''')
    once(path, 'private static bool IsUpdateApplied(VirtualFileSystem virtualFileSystem, string? titleId, out IFileSystem? updatedControlFs)',
         'private static bool IsUpdateApplied(VirtualFileSystem virtualFileSystem, Nca? program, string? titleId, out IFileSystem? updatedControlFs)')
    once(path, '''                (Nca? patchNca, Nca? controlNca) = GetGameUpdateData(virtualFileSystem, titleId, 0, out updatePath);''',
         '''                (Nca? patchNca, Nca? controlNca) = program != null
                    ? program.GetUpdateData(virtualFileSystem, IntegrityCheckLevel.None, 0, out updatePath)
                    : GetGameUpdateData(virtualFileSystem, titleId, 0, out updatePath);''')
    return [path]
