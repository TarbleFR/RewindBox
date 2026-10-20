#!/usr/bin/env python3
"""Reconstruct the missing dependency from pinned, corresponding upstream source.

This is a source build, not a claim to have recovered the original NuGet bytes.
Only LibHac uses this private, local feed; all other package mapping is retained.
"""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import xml.etree.ElementTree as ET
import zipfile


def run(*args, cwd=None, timeout=600):
    subprocess.run(args, cwd=cwd, check=True, timeout=timeout)


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    root = Path(__file__).resolve().parents[2]
    engine = Path(sys.argv[1]).resolve()
    source = Path(sys.argv[2]).resolve()
    lock = json.loads((root / 'build-utils/melonx/source.json').read_text())['libHac']
    actual = subprocess.check_output(['git', '-C', str(source), 'rev-parse', 'HEAD'], text=True).strip()
    assert actual == lock['revision'], (actual, lock['revision'])
    assert not subprocess.check_output(['git', '-C', str(source), 'status', '--porcelain'], text=True).strip()
    project = ET.parse(source / 'src/LibHac/LibHac.csproj').getroot()
    assert project.findtext('.//PackageId') == lock['package']
    assert project.findtext('.//PackageLicenseExpression') == 'MIT'
    assert project.findtext('.//VersionPrefix') == '0.21.0'
    # The NACP fix is the source change which introduced the consumer's exact
    # dependency; fail if a different revision no longer exposes that ABI.
    nacp = (source / 'src/LibHac/Ns/ApplicationControlProperty.cs').read_text(encoding='utf-8-sig')
    assert 'TitleBlock' in nacp and 'readonly ApplicationTitle[] Title' in nacp
    output = root / 'dist/melonx'
    feed = output / 'libhac-feed'
    feed.mkdir(parents=True, exist_ok=True)
    with (output / 'libhac-upstream-source.tar').open('wb') as target:
        subprocess.run(['git', '-C', str(source), 'archive', 'HEAD'], stdout=target, check=True)
    # Run the upstream generators. Its Stage2 wrapper catches failures, so run
    # Stage2 explicitly as well; a swallowed failure must not yield a package.
    run('dotnet', 'run', '--project', 'build/_build.csproj', '--', '--target', 'Codegen', cwd=source)
    run('dotnet', 'run', '--project', 'build/CodeGen/_buildCodeGen.csproj', cwd=source)
    generated = sorted(source.glob('src/LibHac/**/*.Generated.cs'))
    assert any(p.name == 'DefaultKeySet.Generated.cs' for p in generated)
    assert any(p.name == 'ResultNameResolver.Generated.cs' for p in generated)
    run('dotnet', 'test', 'tests/LibHac.Tests/LibHac.Tests.csproj', '-c', 'Release',
        '--filter', 'FullyQualifiedName~LibHac.Tests.Ns.TypeLayoutTests', cwd=source)
    run('dotnet', 'pack', 'src/LibHac/LibHac.csproj', '-c', 'Release', '-o', str(feed),
        '-p:PackageVersion=' + lock['version'], '-p:Version=' + lock['version'],
        '-p:InformationalVersion=' + lock['version'] + '+neostation-source.' + actual,
        '-p:RepositoryUrl=' + lock['repository'], '-p:RepositoryCommit=' + actual, cwd=source)
    package = feed / (lock['package'] + '.' + lock['version'] + '.nupkg')
    with zipfile.ZipFile(package) as archive:
        nuspec = ET.fromstring(archive.read(next(p for p in archive.namelist() if p.endswith('.nuspec'))))
        ns = {'n': nuspec.tag.split('}')[0].strip('{')}
        assert nuspec.findtext('n:metadata/n:id', namespaces=ns) == lock['package']
        assert nuspec.findtext('n:metadata/n:version', namespaces=ns) == lock['version']
        assert 'lib/net8.0/LibHac.dll' in archive.namelist()
    # Preserve the full generated build inputs, not just the original archive.
    with zipfile.ZipFile(output / 'libhac-generated-source.zip', 'w', zipfile.ZIP_DEFLATED) as archive:
        for path in generated:
            archive.write(path, str(path.relative_to(source)))
    nuget = engine / 'nuget.config'
    config = ET.parse(nuget)
    sources = config.getroot().findall('./packageSources/add')
    selected = [item for item in sources if item.get('key') == 'LibHacAlpha']
    assert len(selected) == 1
    selected[0].set('value', str(feed))
    mapping = config.getroot().find("./packageSourceMapping/packageSource[@key='LibHacAlpha']")
    assert [p.get('pattern') for p in mapping] == [lock['package']]
    config.write(nuget, encoding='utf-8', xml_declaration=True)
    receipt = dict(source=lock, reconstructed=True, originalPackageRecovered=False,
                   packageSha256=sha256(package), packageBytes=package.stat().st_size,
                   generatedInputs={str(p.relative_to(source)): sha256(p) for p in generated},
                   layoutTests='LibHac.Tests.Ns.TypeLayoutTests',
                   upstreamSourceSha256=sha256(output / 'libhac-upstream-source.tar'))
    (output / 'libhac-identity.json').write_text(json.dumps(receipt, indent=2) + '\n')
    print('Reconstructed pinned LibHac source:', actual, receipt['packageSha256'])


if __name__ == '__main__':
    main()
