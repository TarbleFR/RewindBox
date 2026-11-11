# Private IPA delivery

Public users receive installable IPAs through approved GitHub Releases. Test
IPAs are encrypted before being uploaded to public Actions artifacts. The
recipient's private decryption key stays outside the repository and artifacts.
The public repository and its development sources remain public.

Every workflow artifact upload uses the immutable
`TarbleFR/RewindBox/.github/actions/upload-protected-artifact` action. It keeps the
original artifact names, paths, retention, compression and output IDs/digests.
Before uploading, it inspects files and nested ZIP/tar/compressed archives,
including renamed packages, and rejects plaintext `.ipa`, `Payload/*.app` and
device `.xcarchive` application packages. An incomplete inspection blocks upload.
Core/framework archives, source archives and ordinary test evidence remain
allowed. Existing encrypted delivery and legacy CMS envelopes remain supported.

The scan is conservative: it also checks hidden and excluded files within
included directories. Archives are never extracted using their member paths;
temporary storage, depth, member count, decompressed bytes and time are bounded.
Unsupported archive formats must be converted or explicitly supported and
reviewed; they must not be uploaded through an unguarded replacement action.
Python 3.11+ is required. The boundary is exercised on Ubuntu, macOS and Windows.

`private-ipa-policy.yml` checks workflow coverage and the real upload boundary.
Its harmless `.ipa` fixture must be rejected, while its JSON receipt must upload
and return the original artifact outputs. Tests cover archive camouflage, nested
archives, limits, directory aliases and normal component/encrypted payloads.

The old NeoSwap Build421 workflow now requires an explicitly selected public
recipient key and encrypts its staging directory before upload. New private
deliveries should use the standard delivery workflow and its frozen manifest.

The artifact inventory uses read-only Actions permissions. Any removal of an
existing exposed artifact requires a separately reviewed list with identities
and retained evidence. Release assets, tags, public source history and component
pins are not cleanup targets. Repository administrators and recipients of a
decrypted IPA can still redistribute files; this mechanism is not DRM.
