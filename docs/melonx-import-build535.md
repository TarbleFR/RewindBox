# MeloNX import completion — private Build 535

The supplied `app(8).log` shows a Switch game imported successfully (the next
playlist visit has two games instead of one), a 15,971,909,632-byte temporary
game copy removed, and subsequent `libraryBusy` warnings. The update picker
copies are also eventually removed. This establishes completed file work and
overlapping operations; the log alone does not establish a native deadlock.

The old menu awaited `MelonxLibraryScanner.refresh` after every successful
import before refreshing the playlist and showing success. The scanner reads
the entire contents of unindexed games for SHA-256 fingerprints, including
games already inserted by the importer. Updates and DLC unnecessarily paid
the same library-wide cost. The old NSP picker explicitly disabled multiple
selection.

## Changes

- Games update the playlist immediately after their file and database work.
  Updates and DLC report their installed configuration without rescanning all
  games. Keys, firmware and migration can request discovery independently.
- Selected files show validation, actual copied bytes, and installation phases.
  Copying uses bounded 1 MiB reads and awaited writes, verifies the final size,
  and renames a temporary file only after completion.
- DLC selection accepts multiple NSPs. Each is checked against the selected
  base title using the existing native inspector. Valid files are installed
  sequentially; rejected files are listed without discarding other successes.
  The final dialog remains until dismissed and lists imported/refused files.
- Library mutation state is visible to every menu, covers game imports too,
  and prevents automatic recovery during an active import. Native launch
  exclusion and finally-based release remain in force.
- New progress/report strings and the busy explanation cover all 12 locales.
  Import start, completion, file errors and stack traces go to the internal log.

## Evidence and limits

`test/melonx_import_completion_test.dart` exercises the real file/database
paths and widgets, with mocked native content inspection and picker boundaries.
It covers batch successes and rejection, retained update paths, rollback when
configuration writing cannot proceed, cancellation, refused gates, completed
game/update UI without post-import discovery, and app resume during a picker.
Existing key/scanner, transfer and menu-disposal tests cover shared code paths.
The delivery records successful check input hashes inside the signed IPA and
requires compiled import markers, the exact unchanged engine identities and
the existing packaging/signature validations.

No physical iPhone import or gameplay is claimed by these host tests. The
earlier save-folder report has no established root cause in this journal;
this delivery does not claim to fix every possible save format or access error.
Build 534's RPCS3 source and Build 533's MeloNX native engine are unchanged.
