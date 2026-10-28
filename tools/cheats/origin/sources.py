"""Where the app downloads each origin source, at the revision the catalogue
was built from. Every file is verified by the SHA-256 the manifest lists for
it, so a host that serves other bytes is refused, never trusted.

  raw:     URL template of one file, `{path}` being its path in the source.
  archive: optional single download holding every file (a GitHub tarball of
           the pinned commit, top folder stripped), used when a bulk install
           needs many files of the source.
  bundle:  the source is one archive (zip) whose members recipes read.
"""

GITHUB_RAW = 'https://raw.githubusercontent.com/{repo}/{commit}/{{path}}'
GITHUB_TARBALL = 'https://codeload.github.com/{repo}/tar.gz/{commit}'


def github(repo, commit, archive=False):
    origin = {'raw': GITHUB_RAW.format(repo=repo, commit=commit), 'revision': commit}
    if archive:
        origin['archive'] = GITHUB_TARBALL.format(repo=repo, commit=commit)
    return origin


ORIGINS = {
    'geckoarchive': github('SpaceXCheeseWheel/GeckoArchive', 'd465c2190d32f954056dd1e6ba68a2ec3fc588ff', True),
    'duckstation': github('duckstation/chtdb', '8b2f1dd257ab9130d16b72e0caeb5a07af8bcbdc', True),
    'cwcheat': github('Saramagrean/CWCheat-Database-Plus-', '40f6c429be63a4a3659284746b0d77d05caee837'),
    'lunamoo': github('LunaMoo/PPSSPP_workarounds', '1355bb338d4a1985aae043f674a070ef99c49524'),
    'shadow_pnach478': github('shadowninja826/pcsx2_pnach_cheats', '56d328be4c4f048896788f8203703b822656b768', True),
    'pal_pnach478': github('complicatiion/pcsx2_europe_cheats_collection', '9886a7a771e38d7ba65cf5826544ddc846d78b55'),
    'yuki_pnach478': github('YukiXXL/PS2-modding', 'bf079d98cc6a820643ab08598b1c3d3df6a9d960'),
    'weed_sheet': github('zzamizz/weed-sheet', '7dedab5f6ca43beff14a0f5fac6d353337d62b06'),
    'fbneo': github('finalburnneo/FBNeo-cheats', '084b13ed7a4d437614a2bf47664cc567ac9dcdef', True),
    'mister': github('MiSTer-devel/Cheats_MiSTer', '56eb5194c6a6c4a718ac0f67a93c498a7a7a4760', True),
    'dillonhafer_xml': {
        'raw': 'https://gist.githubusercontent.com/dillonhafer/8399eb1926e2af9164470ad45da67a57/raw/'
               '6bacdb08bb984bc6bc4d27727e89fdba4a926171/{path}',
        'revision': '6bacdb08bb984bc6bc4d27727e89fdba4a926171'},
    'psxdatacenter_v2_478': {
        'bundle': 'https://psxdatacenter.com/psx2/downloads2/PS2%20Cheats%20Pack%20New%20Pnach%20Format%20v.2.0%20for%20PCSX2.zip',
        'revision': 'v2.0-downloaded-2026-10-18'},
    'mighty_mo': {
        'bundle': 'https://github.com/mightymo77/MightyMos-Cheat-Code-Pack/releases/download/v2025-08-08/'
                  'Mighty.Mo.s.Cheat.Code.Pack.2025-08-08.zip',
        'revision': 'v2025-08-08'},
    'delta_workbook': {
        'bundle': 'https://drive.usercontent.google.com/uc?id=1B2QpnOlYr1ZS91lTS776NVrnUnHeUYIi&export=download',
        'revision': 'sha256:12f8cd5859570e3e8b03b9847ff0d32273f9ae912dca3d7b700b24e77cad5787'},
}
