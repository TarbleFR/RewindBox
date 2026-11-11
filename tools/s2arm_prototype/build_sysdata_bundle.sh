#!/bin/bash
# CI only. Builds the game-independent system data tree that S2Arm's runtime reads from a resource
# pack (systemdata/), with S2Arm's own generators at the pinned commit, as pack/stages/sysdata.sh
# assembles it for a game without the player's real system data:
#   systemdata/fonts/*.bfttf        the 7 open replacement shared fonts (pack/fonts/make_open_fonts.py,
#                                   SIL OFL sources pinned by version and SHA-256 there)
#   systemdata/010000000000080E/    time zone data generated from the pinned IANA release
#                                   (services/systemdata/make_tzdata.sh, SHA-512 checked sources)
#   systemdata/<id>/ + <id>.synth   the "empty but well-formed" system data of pack/sysdata_synth.py for
#                                   every id pack/sysdata_need.py asks for when nothing real is there
# beside it licenses/ (the font licence texts and manifest, the tz licence), SOURCES.tsv (where each
# part comes from) and SHA256SUMS (every file). The host ships this tree once and links or copies it
# into each game's resource pack (rb_s2arm_resource_request.systemdata_dir). Nothing of it is stored
# in this repository: the workflow uploads it as an artifact.
# Usage: build_sysdata_bundle.sh <s2arm checkout> <output dir>
set -euo pipefail
s2arm=$(cd "$1" && pwd)
out=$2
py=${PYTHON:-python3}
rm -rf "$out"
mkdir -p "$out/systemdata/fonts" "$out/licenses/fonts" "$out/licenses/tzdata"
out=$(cd "$out" && pwd)
work=$(mktemp -d "${RUNNER_TEMP:-${TMPDIR:-/tmp}}/sysdata.XXXXXX")
trap 'rm -rf "$work"' EXIT

# 1. Shared fonts, with the generator's pinned dependencies in a private environment.
"$py" -m venv "$work/venv"
"$work/venv/bin/python" -m pip install -q -r "$s2arm/pack/fonts/requirements.txt"
S2A_OPENFONTS_CACHE="$work/font-cache" "$work/venv/bin/python" "$s2arm/pack/fonts/make_open_fonts.py" "$work/fonts" > "$work/fonts.log"
test "$(ls "$work/fonts"/*.bfttf | wc -l | tr -d ' ')" = 7
cp "$work/fonts"/*.bfttf "$out/systemdata/fonts/"
cp "$work/fonts"/OFL-*.txt "$work/fonts/MANIFEST.tsv" "$s2arm/pack/fonts/LICENSES.md" "$out/licenses/fonts/"

# 2. Time zone data (the sources are downloaded once at the pinned release, then generated offline).
export S2A_TZDATA_CACHE="$work/tz-cache"
bash "$s2arm/services/systemdata/make_tzdata.sh" --prepare-sources
S2A_PYTHON="$py" bash "$s2arm/services/systemdata/make_tzdata.sh" "$out/systemdata/010000000000080E" > "$work/tz.log"
tz_id=$(bash "$s2arm/services/systemdata/make_tzdata.sh" --source-id)
tz_version=${tz_id%% *}
mkdir -p "$work/tzcode"
tar -xzf "$S2A_TZDATA_CACHE/tzcode$tz_version.tar.gz" -C "$work/tzcode"
cp "$work/tzcode/LICENSE" "$out/licenses/tzdata/LICENSE"

# 3. The synthesised system data: every SYNTH id of sysdata_need.py for an empty product root.
mkdir -p "$work/root"
"$py" "$s2arm/pack/sysdata_need.py" "$work/root" "" > "$work/need.txt"
ids=$(awk -F'\t' '$1 == "SYNTH" { print $2 }' "$work/need.txt")
test -n "$ids"
for id in $ids; do
  "$py" "$s2arm/pack/sysdata_synth.py" "$id" "$out/systemdata/$id"
  # the marker pack/stages/sysdata.sh writes beside it ("合成：pack/sysdata_synth.py <id>")
  printf '\xe5\x90\x88\xe6\x88\x90\xef\xbc\x9apack/sysdata_synth.py %s\n' "$id" > "$out/systemdata/$id.synth"
done

# 4. Provenance and checksums.
commit=$(git -C "$s2arm" rev-parse HEAD 2> /dev/null || echo unknown)
generator=$("$py" -c 'import hashlib,sys; print(hashlib.sha256(open(sys.argv[1], "rb").read()).hexdigest())' "$s2arm/pack/fonts/make_open_fonts.py")
{
  printf 'part\tsource\n'
  printf 's2arm\t%s\n' "$commit"
  printf 'fonts\tpack/fonts/make_open_fonts.py sha256 %s; %s\n' "$generator" "$(grep -v '^#' "$s2arm/pack/fonts/requirements.txt" | tr '\n' ' ' | sed 's/ *$//')"
  printf 'tzdata\tservices/systemdata/make_tzdata.sh, IANA %s\n' "$tz_id"
  printf 'synthesised\t%s\n' "$(echo $ids)"
} > "$out/SOURCES.tsv"
"$py" - "$out" << 'PY'
import hashlib, os, sys
root = sys.argv[1]
rows = []
for top in ('systemdata', 'licenses', 'SOURCES.tsv'):
    path = os.path.join(root, top)
    walk = [(path, [], [''])] if os.path.isfile(path) else os.walk(path)
    for directory, dirs, files in walk:
        dirs.sort()
        for name in sorted(files):
            p = os.path.join(directory, name) if name else directory
            if os.path.islink(p):
                sys.exit(f'unexpected link {p}')
            with open(p, 'rb') as f:
                rows.append(f'{hashlib.sha256(f.read()).hexdigest()}  {os.path.relpath(p, root)}\n')
with open(os.path.join(root, 'SHA256SUMS'), 'w', encoding='utf-8', newline='\n') as f:
    f.writelines(rows)
print(f'{len(rows)} files')
PY
du -sh "$out/systemdata" | sed 's/^/systemdata: /'
cat "$out/SOURCES.tsv"
