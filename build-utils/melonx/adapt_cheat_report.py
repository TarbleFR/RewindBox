"""Which build a launch's cheats were for: the main executable's build id for the host, and one line per process.

The maintainer installed cheats from RewindBox's catalogue (Cheats & Enhancements) and "they do not work in game". The
host's side is consistent with the engine's (cheat folders, enabled.txt keys "{BUILDID16}-<{name} Cheat>"). What the
engine does with a catalogue made for another version of the game: ModLoader.LoadCheats installs a cheat only for an
executable whose build id starts with the file's 16 hex digits, and skips every other with a Warning that names the
64-digit build ids, which the journal's filter redacts (64 hex digits are above its 32-digit limit). So the device's
journal cannot say that nothing matched, nor which build was running.

Edits (journal and metadata only; what is installed, enabled or executed is unchanged):
  ModLoader.cs           LoadCheats counts the cheats found and those skipped for another build id, with their ids
                         (native/melonx/EmbeddedCheatReport.cs, copied into Ryujinx.HLE).
  TamperMachine.cs       CheatCounts: the programs installed for given build ids and how many are enabled (read only).
  ProcessLoaderHelper.cs after LoadCheats, one Warning line: title, main build id, found / installed / enabled /
                         skipped, the skipped files' build ids, each as 16 hex digits.
  EmbeddedContent.cs     (prepared copy, as adapt_nextendo_online leaves it) content operation 0 (metadata) also answers
                         "buildId", the main NSO's, in the cheat files' form; the update inspection (operation 4,
                         native EmbeddedAddons.cs) answers the update's the same way. Omitted when unreadable.

Fail closed on drift: each file is pinned to the bytes the preparation leaves before this adapter (ProcessLoaderHelper
after adapt_session, EmbeddedContent after adapt_nextendo_online); no later adapter edits them. Not run on an iPhone.
"""
import hashlib
from pathlib import Path

MOD_LOADER = 'src/Ryujinx.HLE/HOS/ModLoader.cs'
TAMPER = 'src/Ryujinx.HLE/HOS/TamperMachine.cs'
HELPER = 'src/Ryujinx.HLE/Loaders/Processes/ProcessLoaderHelper.cs'
CONTENT = 'src/Ryujinx.Library/EmbeddedContent.cs'

BASELINE = {
    MOD_LOADER: '251427773a6c8cfe0fc02114e7293379ba56f2928eb835012849ee336bdf5c1a',
    TAMPER: '0f2aca7ff295206b802d91476e0c69eaf48d15bd10fa1dee36dd8b58a874d448',
    HELPER: '2be96320b404be96e237b9354f57d91db9e69974ef21f4c8ab051c50ede19d36',
    CONTENT: '8c853590b8f6fef7c9a7a3a64b04df657107851f36799f3287ce4619b6d689d1',
}

BEGIN_OLD = '''            Logger.Info?.Print(LogClass.ModLoader, $"Build ids found for application {applicationId:X16}:\\n    {String.Join("\\n    ", tamperInfo.BuildIds)}");
'''
BEGIN_NEW = '''            Logger.Info?.Print(LogClass.ModLoader, $"Build ids found for application {applicationId:X16}:\\n    {String.Join("\\n    ", tamperInfo.BuildIds)}");
            Ryujinx.HLE.EmbeddedCheatReport.Begin(applicationId); // RewindBox (adapt_cheat_report)
'''
FOUND_OLD = '''            List<Cheat> cheats = mods.Cheats;
'''
FOUND_NEW = '''            List<Cheat> cheats = mods.Cheats;
            Ryujinx.HLE.EmbeddedCheatReport.Found(cheats.Count); // RewindBox (adapt_cheat_report)
'''
SKIP_OLD = '''                    Logger.Warning?.Print(LogClass.ModLoader, $"Skipping cheat '{cheat.Name}' because no executable matches its BuildId {cheatId} (check if the game title and version are correct)");
'''
SKIP_NEW = '''                    Logger.Warning?.Print(LogClass.ModLoader, $"Skipping cheat '{cheat.Name}' because no executable matches its BuildId {cheatId} (check if the game title and version are correct)");
                    Ryujinx.HLE.EmbeddedCheatReport.Skipped(cheatId); // RewindBox (adapt_cheat_report)
'''
COUNTS_OLD = '''        public void EnableAllCheats()
        {
            foreach (ITamperProgram program in _programDictionary.Values)
            {
                program.IsEnabled = true;
            }
        }
'''
COUNTS_NEW = '''        public void EnableAllCheats()
        {
            foreach (ITamperProgram program in _programDictionary.Values)
            {
                program.IsEnabled = true;
            }
        }

        // RewindBox (adapt_cheat_report): the programs installed for these build ids (keys "{build id}-{name}", the build
        // id in the cheat files' 16-digit form) and how many of them are enabled. Read only.
        internal (int Installed, int Enabled) CheatCounts(IEnumerable<string> buildIds)
        {
            HashSet<string> ids = new(buildIds, StringComparer.OrdinalIgnoreCase);
            int installed = 0, enabled = 0;
            foreach (KeyValuePair<string, ITamperProgram> pair in _programDictionary)
            {
                int dash = pair.Key.IndexOf('-');
                if (dash <= 0 || !ids.Contains(pair.Key[..dash])) continue;
                installed++;
                if (pair.Value.IsEnabled) enabled++;
            }

            return (installed, enabled);
        }
'''
WRITE_OLD = '''            device.Configuration.VirtualFileSystem.ModLoader.LoadCheats(programId, tamperInfo, device.TamperMachine);
'''
WRITE_NEW = '''            device.Configuration.VirtualFileSystem.ModLoader.LoadCheats(programId, tamperInfo, device.TamperMachine);

            // RewindBox (adapt_cheat_report): which build the cheats were for (title, main build id, found / installed /
            // enabled / skipped, the skipped files' build ids), one Warning line in the Core journal.
            Ryujinx.HLE.EmbeddedCheatReport.Write(programId, Ryujinx.HLE.EmbeddedCheatReport.MainOf(executables), buildIds, device.TamperMachine);
'''
METADATA_OLD = '''                                    json.WriteString("version", info.Version?.TrimEnd('\\0'));
'''
METADATA_NEW = '''                                    json.WriteString("version", info.Version?.TrimEnd('\\0'));
                                    // RewindBox (adapt_cheat_report): the main executable's build id in the cheat files' form.
                                    string mainBuildId = EmbeddedApplicationBuildId(path);
                                    if (mainBuildId != null) json.WriteString("buildId", mainBuildId);
'''

PAIRS = (
    (MOD_LOADER, BEGIN_OLD, BEGIN_NEW),
    (MOD_LOADER, FOUND_OLD, FOUND_NEW),
    (MOD_LOADER, SKIP_OLD, SKIP_NEW),
    (TAMPER, COUNTS_OLD, COUNTS_NEW),
    (HELPER, WRITE_OLD, WRITE_NEW),
    (CONTENT, METADATA_OLD, METADATA_NEW),
)


def once(path: Path, old: str, new: str):
    text = path.read_text(encoding='utf-8-sig')
    assert text.count(old) == 1, (str(path), old[:90], text.count(old))
    path.write_text(text.replace(old, new), encoding='utf-8')


def apply(source):
    """Edits the prepared tree; EmbeddedCheatReport.cs is copied there with the native files (prepare_embedded)."""
    source = Path(source)
    for name, expected in BASELINE.items():
        actual = hashlib.sha256((source / name).read_bytes()).hexdigest()
        assert actual == expected, 'Preparation drift, refusing to adapt: ' + name
    for name, old, new in PAIRS:
        once(source / name, old, new)
    return [source / name for name in BASELINE]


if __name__ == '__main__':
    import sys
    for path in apply(sys.argv[1]):
        print(path)
