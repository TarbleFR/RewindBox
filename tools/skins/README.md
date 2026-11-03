# RewindBox Pocket skins

These two packs were reconstructed after workspace maintenance removed the
prepared sources. They retain the recovered v1 input bindings and hit rectangles,
adapt the four game viewports to the approved raw body images, and use newly
rendered original controls. Their hashes do not identify the lost prepared commit.

Install the pinned requirements and run from the repository root:

```sh
python3 tools/skins/build_pocket_skins.py --output build/pocket-review
python3 tools/skins/verify_pocket_skins.py --assets-dir build/pocket-review
```

`--output` selects a different destination. `--body-textures` selects a directory
containing `body-portrait.png` and `body-landscape.png`; these files are embedded
byte-for-byte. No crop, recoloring, or retouching of the source body images occurs.

`pocket_art.py` renders transparent control PNGs using signed-distance surface
heights, material shading and separate contact shadows. Each button and stick
base has distinct normal/pressed artwork. Knobs are separate sprites moved by
the native overlay; no stationary knob is baked into a base or body image.

Portrait and landscape installed-manager previews are composed from the actual
layout and sprite files, included in the archive, and copied to catalog previews.
Standard-phone previews and pressed-state examples are also produced for review.
Only the catalog, two archives and four normal portrait/landscape previews are
copied to `assets/skins/pocket/`; the other review files are not app resources.
ZIP metadata and image rendering are deterministic with the pinned dependencies
and bundled DejaVu fonts (see `fonts/DejaVu-notices.txt`).

Only original RewindBox artwork is bundled. Console names and marks remain the
property of their owners; no third-party rights or public-domain waiver is given.
Generation and geometry checks do not establish physical iPhone gameplay.
