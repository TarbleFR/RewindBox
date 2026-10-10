# Aidoku source fixtures

Minimized copies of pages captured on 2026-10-10 by the Build 437 source
research (Manga Scantrad: Wayback captures of 2025-03/04, the live site being
behind a Cloudflare challenge; Sushi Scans chapter: Wayback capture of
2026-04-23, the origin answering 504 that day).

Minimization keeps the markup the parsers rely on and removes the rest:
scripts (except `wp-manga-js-extra` and `ts_reader.run`), styles, SVG,
comments sections, avatars, share links and ads; text longer than about
60 characters is replaced by a placeholder; repeated rows are limited to a
few representative entries (first rows, decimals, volumes, last row). No
image is stored.

`cloudflare_challenge_403.html` is the `<title>` of the live challenge page.
The Manga Scantrad chapter list used by the tests is synthetic (inline in
`library_aidoku_madara_test.dart`): the endpoint could not be observed.
