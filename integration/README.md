# Liquid glass / AirPlay — isolated integration

Base: `654263ac09ad192360064f92dedcb4f9442bde38` (delivered Build 503).
Work branch: `work/liquid-glass-airplay-20261022`.

The maintainer explicitly requested an isolated checkout for this work and
integration **after** the separate startup-animation chantier. Do not merge or
push this work to `Claude` until that chantier has completed its integration.
Do not create a tag or release. `main` is outside the scope.

## Implementation

- Neutral convex glass rims, inner optical depth, a surface glint and a clear
  center over existing artwork. This is a lightweight optical illustration,
  not a claim of physically accurate background refraction.
- Only the selected card animates its existing light controller. Light changes
  repaint the shell without rebuilding the artwork or text. Dense cards still
  have no backdrop filters; the moving navigation lens retains its small blur.
- The navigation lens stretches along its direction of travel and retargets
  from its actual position during quick reversals. Presses gently compress the
  surface in two axes. Reduced motion, lifecycle and the existing frontend
  media barrier stop movement.
- Playlist opening/closing uses the same lens material and a small transient
  stretch. The real page keeps its stable element path, final viewport, input
  lifetime lock and source focus/scroll position. The temporary source image
  preserves aspect ratio and retains the previous bounded GPU allocation.
- AirPlay has an appended canonical identity (`7`); existing indices `0–6`
  remain unchanged. The shared visible-tab order places it after Search and
  before Achievements, including when optional tabs are hidden. Its page reuses
  receiver selection; merely visiting it does not discover or start capture.
  The existing app input owner is reused instead of creating another gamepad
  subscription. Existing translated labels are used in all twelve languages.

## Reserved startup file

`lib/screens/app_screen.dart` contains both startup sequencing and tab dispatch.
It is deliberately **unchanged** in this work branch. The small, deferred
`liquid-airplay-app-screen.patch` contains only the tab identity, content
dispatch, secondary-display name and input delegation. It does not change the
startup sequencing. The isolated CI applies it in a disposable checkout for
analysis and tests; this is an integration rehearsal, not an integrated build.

After the startup owner has integrated and stopped writing:

1. Fetch `Claude` and record the completed startup commit. Review its actual
   changed paths; do not infer completion from an unrelated commit or build.
2. Integrate these commits on top of that state, preserving all startup edits.
3. Run `git apply --check integration/liquid-airplay-app-screen.patch`, inspect
   each hunk and apply it. If startup changed the surrounding file, port only
   the tab-dispatch hunks. Never replace the whole file from this old base.
4. Commit the integrated dispatch. Update the existing UI evidence/build gate
   to cover the exact combined startup and liquid-glass source inputs. Remove
   the temporary rehearsal workflow/patch only after the integration is stored.
5. Run only checks affected by the merge and its transitive inputs; reuse
   unchanged engine/native evidence by identity. Produce one new test IPA from
   `Claude` with the existing packaging/signature gates. Do not reuse 503.
6. Delete this temporary remote/local branch after integration, leaving only
   `Claude` and `main` as requested. Never delete another chantier's work.

## Evidence and limits

The rehearsal workflow uploads the tested commit, exact applied dispatch patch,
formatting review and production console/navigation render. Tests exercise
slow/fast touch, raw controller translation, keyboard, hidden-tab order,
receiver focus, reverse transitions, source-state retention, interruption,
accessibility and the original receiver-dialog behavior.

CI results are not physical iPhone/Bluetooth verification or measured 60/120 FPS.
The final combined IPA is intentionally deferred until the startup integration
condition is met. No emulator, import, database, language catalogue, dependency
or asset is changed by this work.
