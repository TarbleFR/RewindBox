# Build 489 — catalogue HD étendu (GameCube, Wii, 3DS) et Beetle PSX HW en Vulkan, 19 octobre 2026

Demande du mainteneur (19 octobre 2026) : étendre massivement le catalogue unifié de textures HD (priorités GameCube, Wii et 3DS, puis PSP et PS2) à partir des 386 références fournies (S001–S386), des autres projets de leurs auteurs et des annuaires ; mesurer et figer N0 (packs distincts installables) au départ, viser au moins 3 × N0 au total et séparément pour le GameCube, la Wii et la 3DS, et publier l'écart honnêtement ; ne compter comme « installable » qu'une archive vérifiée en CI, distincte du « rendu vérifié en jeu » ; implémenter réellement Beetle PSX HW avec son rendu Vulkan (MoltenVK) pour la PS1, avec l'état réel affiché et sans fausse conversion de packs DuckStation ; une IPA de test une fois stabilisé. Branche `Claude` seule, rien sur `main`, aucune release, pas de contournement de CAPTCHA, d'authentification, de paiement ni de limite d'accès, pas de réhébergement.

Inventaire généré : [`HD_TEXTURE_CATALOG_SOURCES.md`](HD_TEXTURE_CATALOG_SOURCES.md). Expansion 488 : [`hd-textures-expansion-2026-10-19.md`](hd-textures-expansion-2026-10-19.md). Architecture 486 : [`build486-hd-textures-catalogue.md`](build486-hd-textures-catalogue.md).

## 1. Règle de comptage et N0

- **Installable** : pack en un geste (fichier de l'auteur vérifié) ou pack manuel portant le fichier de l'auteur vérifié en CI (`download.verified`, § 3). Un lien manuel sans fichier vérifié n'est pas installable.
- **Une famille par pack** : résolutions, formats (PNG/DDS), éditions de plateforme (bureau/mobile), régions, styles de boutons, mises à jour, miroirs et dépendances d'un même pack comptent une fois (`family` des sources, sinon règles de `tools/textures/count_packs.py`). Les champs `family` et `scope` restent dans les sources ; l'index ne les porte pas.
- **Portée** : `complete`, `partial` (travail en cours, sélection, correctifs), `ui` (interface, polices, boutons).
- **N0 figé** sur l'index livré de la Build 488 (`2026-10-19.72e26f767470`, `python3 tools/textures/count_packs.py --git 2bdca0d4`) :

⟪tableau N0 / objectif / Nfinal⟫

## 2. Exploration des références

⟪statistiques des 386 références, sondes, hôtes, exclusions⟫

## 3. Packs manuels à fichier vérifié

Un auteur qui publie sur MEGA, Google Drive, Dropbox, MediaFire, GameBanana ou archive.org garde un lien manuel (règle de la Build 486 : NeoStation ne télécharge jamais lui-même ces fichiers). Depuis la 489, le job `hosts` de `hd-textures.yml` récupère une fois sur les runners le fichier exact de l'auteur (`tools/textures/hosts.py` : liens publics seulement ; quota, connexion, CAPTCHA ou protection anti-robot → statut `protected`/`quota`, jamais contournés) et l'installe avec le code de l'application (`verify_packs.py --kind host`). L'index porte alors `download.verified` (format, nom, taille, SHA-256, hôte) : la page du pack propose « Importer le fichier téléchargé », et le magasin n'accepte que ce fichier exact (taille puis SHA-256 pendant la copie), installé comme un pack en un geste ; tout autre fichier est refusé sans rien toucher. Les applications 486–488 ignorent ces clés (lien manuel).

Les enregistrements de ces runs sont recopiés depuis leurs journaux (le conteneur de travail ne peut pas télécharger les artefacts) et `tools/textures/check_ci_records.py` (partie host) exige qu'ils soient identiques aux artefacts `hdtex-hosts-<console>-<run>`.

## 4. Beetle PSX HW en Vulkan (PS1)

⟪état exact⟫

## 5. Vérifications

⟪CI⟫

## 6. Limites

⟪limites⟫

## 7. Livraison Build 489

⟪livraison⟫
