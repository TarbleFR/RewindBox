# Direct Switch playlist and compact main header — build 512

Scope: the maintainer requests a direct Switch playlist even when empty, a
single aligned top bar where the measured groups fit, and removal of the visual
LB/RB hints. Physical controller navigation, touch swipes, the complete Mau Ali
selection, Liquid Glass surfaces and other engines remain unchanged.
Baseline: delivered UI 511, assembly source
`12589d3fa7c3d5fd28537c456cde1b80a06cca98`, successful run `39894506630`,
plus its documentation receipt at `2ed9a18ca6b22a00675dcbbe3a44985e26ed04d5`.

Switch previously fell through to the generic empty-system panel with the
recursive scan preference. Its new quiet empty state keeps the playlist route,
normal import action and an optional small return control. Existing background
discovery and manual scan/import still use the same embedded library services
and canonical local files. No external MeloNX paths or launcher are added.
The two Switch UI platform guards now use Flutter's target platform, as does the
existing tab registry; native execution and filesystem services are unchanged.

The header removes only the decorative bumper glyphs and their space. It trims
the leading control's outer margin and excess status spacing. The adaptive
layout replaces an absolute 300-point navigation threshold with a measured
80%-of-natural-width floor; the old threshold unnecessarily wrapped the
852-point iPhone layout. Groups share their vertical centre on a single row.
Narrow/accessibility layouts can still adapt without overlap. Safe-area
padding, the shared same-frame header/body layout and all animation inputs
remain unchanged, so reclaiming the row also reclaims console-library space.

Targeted validation covers the actual Switch route, empty/reopened playlists,
real embedded files and discovery, menu-driven manual scan and import, touch
and translated controller events, twelve existing translations, and the complete
header at phone/tablet sizes with both batteries. Real Roboto font metrics are
loaded for layout assertions; fixed-width Ahem is not a valid width estimate.
Full portrait/landscape compositions use the existing renderer and neutral QA
artwork. Initial fixture errors (provider/schema/font/timing/platform input
setup) are retained as failed attempts, never represented as passing proofs.
Changed-file analysis retains four pre-existing informational brace-style
lints; errors and warnings remain fatal. No dependency/lockfile change is needed.

Only affected checks are run. The delivered 511 proof and exact unchanged
inputs cover all other native engines, services, repositories, startup,
Rewind Motion, catalogues, artwork, translations, animation tracks, tab identities,
AirPlay/Achievements routing and physical LB/RB owners. A new test IPA is
required; release/tag/main changes are not authorized. Successful CI and final
IPA identities will be recorded after completion. No physical-device or
performance/thermal validation is claimed.
