# NeoAssets System Art — published source register

_Checked 21 October 2026. RewindBox iOS (independent NeoStation fork)._

Official community catalogue: https://neoassets.dev/app/sap

Source API (public, no account required):
- Published catalogue: `GET https://api.neoassets.dev/api/v1/packs?sort=downloads&limit=100&offset=0` (paginate using `total`).
- Full per-pack file list: `GET https://api.neoassets.dev/api/v1/packs/{folder}`.
- Record a **real successful installation only**: `GET https://api.neoassets.dev/api/v1/packs/{folder}/download`.
- Artwork is served at the published per-file `url` on `https://cdn.neoassets.dev/`. Do not invent filenames from `file_name`; use `system_id` and the `url` supplied by the API.

## All published System Art packs

| Pack (NeoAssets page) | Folder slug | Credited author(s) | Backgrounds |
| --- | --- | --- | ---: |
| [RiiSU](https://neoassets.dev/app/sap/riisu) | `riisu` | mult1v4c (iiSU Interpreted also credited in the pack description) | 107 |
| [NeoStation](https://neoassets.dev/app/sap/neostation) | `neostation` | NeoStation Team | 101 |
| [Aura (ES-DE Version)](https://neoassets.dev/app/sap/aura-es-de-version) | `aura-es-de-version` | Siddy212 | 104 |
| [canvas-es-de](https://neoassets.dev/app/sap/canvas-es-de) | `canvas-es-de` | Siddy212 & Kim Visnes | 105 |
| [Canvas [ES-DE] System Logo](https://neoassets.dev/app/sap/canvas-es-de-system-logo) | `canvas-es-de-system-logo` | Siddy212 | 104 |
| [Modern for ES-DE Frontend](https://neoassets.dev/app/sap/modern-for-es-de-frontend) | `modern-for-es-de-frontend` | Leon Styhre | 103 |
| [Colorfully](https://neoassets.dev/app/sap/colorfully) | `colorfully` | viking & Jamesinorbit | 100 |
| [iiSU-Dark](https://neoassets.dev/app/sap/iisu-dark) | `iisu-dark` | VJB | 107 |
| [compendium-es-de](https://neoassets.dev/app/sap/compendium-es-de) | `compendium-es-de` | RobZombie9043 | 102 |
| [Inked Gel](https://neoassets.dev/app/sap/inked-gel) | `inked-gel` | Destron5683 | 73 |
| [Canvas (carousel-icons-capsule)](https://neoassets.dev/app/sap/canvas-carousel-icons-capsule) | `canvas-carousel-icons-capsule` | Kim Visnes, Siddy212 | 110 |
| [COLORFUL Hardware PNG media (1x1)](https://neoassets.dev/app/sap/colorful-hardware-png-media-1x1) | `colorful-hardware-png-media-1x1` | viking | 108 |
| [WIIRD](https://neoassets.dev/app/sap/wiird) | `wiird` | Mistery | 59 |
| [Pixel UI - Smart Folders](https://neoassets.dev/app/sap/pixel-ui-smart-folders) | `pixel-ui-smart-folders` | w0rm; pack description also credits YOjeremyRaps and BenJelter | 52 |
| [colorful-pop-es-de](https://neoassets.dev/app/sap/colorful-pop-es-de) | `colorful-pop-es-de` | RobZombie9043 (adaptation credits in pack description) | 106 |
| [Controller](https://neoassets.dev/app/sap/controller) | `controller` | axiomaticWave (Pinapple Graphics credited in description) | 42 |
| [Gradient Mesh](https://neoassets.dev/app/sap/gradient-mesh) | `gradient-mesh` | melo23 | 65 |
| [Analog](https://neoassets.dev/app/sap/analog) | `analog` | axiomaticWave (seanfletchr credited as inspiration) | 32 |
| [Simply Basic Dark](https://neoassets.dev/app/sap/simply-basic-dark) | `simply-basic-dark` | Destron5683 | 66 |
| [Simply Basic Light](https://neoassets.dev/app/sap/simply-basic-light) | `simply-basic-light` | Destron5683 | 64 |

**Total at inventory time:** 20 approved packs; 1,710 published background-file records. Pixel UI publishes **51 GIF and 1 WebP**; all 19 other packs published WebP. These totals are not a promise of future availability. The iOS app refreshes the public catalogue dynamically and can discover later additions without an app update.

The NeoAssets site identifies Controller, Gradient Mesh and Analog as **AI-assisted/generated**; RewindBox preserves that flag.

## Integration and interoperability

- RewindBox downloads selected image files directly from the official CDN into its existing local System Art cache. No third-party artwork is bundled with the IPA, mirrored or committed to the repository.
- The original pack name, author and AI flag are retained in the selector. The existing installed IDs `NeoStation` and `RiiSU` remain stable even though the API slugs are lowercase.
- The pre-existing, separately curated `CanvasESDE` pack still uses zenandiko's pinned GitHub revision and is **not** the same as NeoAssets' `canvas-es-de` or `canvas-carousel-icons-capsule` packs.
- Every published file is selected by the API's `system_id` and real `url` (not a guessed filename). Unsupported system cards retain the app's default art. GIF/WebP are installed with their true extensions.
- The service consults the official detail for the selected pack only, not all packs on every refresh. Cached metadata and images survive offline launches.
- The upstream `/download` counter is used only for a genuine new installation after at least one asset is present, not for browsing, previewing or reapplying an already installed pack.

## Rights and provenance

**Listing a pack is not a license to redistribute its illustrations.** NeoAssets identifies submitters and authors but does not establish one uniform content license for all these third-party designs. Credits remain with the individual artists and projects named above; logos, console marks and underlying game imagery retain their respective ownership and terms.

RewindBox only references the original official API and lets the user retrieve the artwork on demand. RewindBox does not claim ownership, endorsement, affiliation with NeoAssets, or permission to redistribute the content independently. For permission to mirror, bundle or adapt a particular pack, check the applicable original creator's terms or request permission directly. Upstream credits/usage conditions may change: the per-pack public page and creator declarations take precedence over this inventory.

Existing rights records remain applicable to historical NeoStation Assets, RiiSU/iiSU and Canvas-Capsule; see `assets/legal/THIRD_PARTY_NOTICES.md`.
