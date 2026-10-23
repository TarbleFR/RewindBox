#!/usr/bin/env python3
"""Apply the audited bootstrap and session boundaries to the pinned engine."""
import hashlib
import json
from pathlib import Path
import shutil
import sys
import zipfile
from adapt_session import apply as adapt_session
from adapt_input import apply as adapt_input
from adapt_runtime import apply as adapt_runtime
from adapt_firmware import apply as adapt_firmware
from adapt_memory import apply as adapt_memory


def replace_once(path, old, new):
    text = path.read_text(encoding='utf-8-sig')
    assert text.count(old) == 1, str(path)
    path.write_text(text.replace(old, new), encoding='utf-8')


def main():
    root = Path(__file__).resolve().parents[2]
    source = Path(sys.argv[1]).resolve()
    library = source / 'src/Ryujinx.Library/Library.cs'
    replace_once(library, '    class Library\n', '    partial class Library\n')
    replace_once(library, '''        public static unsafe void Initialize()
        {
            AppDataManager.Initialize(Environment.GetFolderPath(Environment.SpecialFolder.MyDocuments));''', '''        public static unsafe void Initialize()
        {
            InitializeCore(Environment.GetFolderPath(Environment.SpecialFolder.MyDocuments));
        }

        private static unsafe void InitializeCore(string rootDirectory)
        {
            AppDataManager.Initialize(rootDirectory);''')
    replace_once(source / 'src/Ryujinx.Common/Configuration/AppDataManager.cs',
                 'BaseDirPath = Path.GetFullPath(Environment.GetFolderPath(Environment.SpecialFolder.MyDocuments));',
                 'BaseDirPath = Path.GetFullPath(baseDirPath ?? Environment.GetFolderPath(Environment.SpecialFolder.MyDocuments));')
    adapted = adapt_session(source)
    adapted += adapt_input(source)
    adapted += adapt_runtime(source)
    adapted += adapt_firmware(source)
    adapted += adapt_memory(source)
    inputs = {}
    copied = []
    for path in sorted((root / 'native/melonx').glob('*.cs')):
        project = {'EmbeddedHomebrewAssets.cs': 'Ryujinx.HLE',
                   'EmbeddedDarwinSignals.cs': 'Ryujinx.Cpu',
                   'EmbeddedNativeGamepadLease.cs': 'Ryujinx.Input.Native',
                   'EmbeddedNativeLibraries.cs': 'Ryujinx.Common',
                   'EmbeddedLaunchDiagnostics.cs': 'Ryujinx.Common',
                   'EmbeddedFirmwareStore.cs': 'Ryujinx.HLE',
                   'EmbeddedFirmwareArchive.cs': 'Ryujinx.HLE'}.get(path.name, 'Ryujinx.Library')
        target = source / 'src' / project / path.name
        shutil.copyfile(path, target)
        copied.append(target)
        inputs[str(path.relative_to(root))] = hashlib.sha256(path.read_bytes()).hexdigest()
    inputs['build-utils/melonx/prepare_embedded.py'] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    adapter = Path(__file__).with_name('adapt_session.py')
    inputs['build-utils/melonx/adapt_session.py'] = hashlib.sha256(adapter.read_bytes()).hexdigest()
    adapter = Path(__file__).with_name('adapt_input.py')
    inputs['build-utils/melonx/adapt_input.py'] = hashlib.sha256(adapter.read_bytes()).hexdigest()
    adapter = Path(__file__).with_name('adapt_runtime.py')
    inputs['build-utils/melonx/adapt_runtime.py'] = hashlib.sha256(adapter.read_bytes()).hexdigest()
    adapter = Path(__file__).with_name('adapt_firmware.py')
    inputs['build-utils/melonx/adapt_firmware.py'] = hashlib.sha256(adapter.read_bytes()).hexdigest()
    adapter = Path(__file__).with_name('adapt_memory.py')
    inputs['build-utils/melonx/adapt_memory.py'] = hashlib.sha256(adapter.read_bytes()).hexdigest()
    output = root / 'dist/melonx'
    output.mkdir(parents=True, exist_ok=True)
    (output / 'embedded-inputs.json').write_text(json.dumps(inputs, indent=2) + '\n')
    with zipfile.ZipFile(output / 'embedded-adapted-source.zip', 'w', zipfile.ZIP_DEFLATED) as archive:
        for path in dict.fromkeys([*adapted, source / 'src/Ryujinx.Common/Configuration/AppDataManager.cs',
                                  *copied]):
            archive.write(path, str(path.relative_to(source)))


if __name__ == '__main__':
    main()
