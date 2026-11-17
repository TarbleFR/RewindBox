# Private test IPA 772: verified and handed over, not a base

- Run 44103379791 (`[ipa-delivery:772]`, a023167f): every job green.
- IPA `RewindBox-Build772-a023167ff5f0fc59c5947095fc92fc62bcc25386-cold.ipa`, 331,834,247 bytes, SHA-256
  `64646e7a8c326bc75fc7f631639104d2f0bba91b5bb7e7977cb28767411a4770`.
- The IPA was checked offline by `build-utils/verify_downloaded_delivery.py` (`download772-verification.json`,
  result `passed-offline-checks`):
  - the four encrypted transport parts matched the API digests (`api/`);
  - SHA256SUMS and the signer receipt matched;
  - the 97 native images and their fingerprints matched;
  - all six validators returned 0.
- It was handed over privately to the maintainer on 17 November 2026 (no IPA in Git).

## Why there is no `delivery.json`

The eight decrypted receipts were copied from the wrong place: `find` in the verifier's work folder first met the
ones of IPA 616, which live in the exported effective tree. `signed-payload-identity.json` and the seven others
in this folder were therefore build 616's.

The recipient key had already been deleted. `standard_delivery.py record 772` refused the folder ("The signed
payload identity in the evidence folder is not the one of the verified IPA"). The wrong files were removed.

The real receipts existed only in the encrypted delivery and cannot be decrypted again. They are not rebuilt here:
a locally computed inventory would not be the signed one.

Under recipe § 3.8, IPA 772 is therefore not a base. The next build starts again from IPA 771, the last complete
base, and takes the 772 lots again as reviewed commits:

- the S2Arm engine pin 9a9ca3a8 (0001-0081) and the bridge fixes e59eb698 / f0e572de;
- MeloNX Core 9546deb7 and the journal fix e58154cd.

For later deliveries, copy each receipt from the decrypted `delivery/` folder of the work directory, not from a
search of the whole work directory.
