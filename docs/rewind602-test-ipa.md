# RewindBox602 — correction du helper JIT de Hogwarts

La build privée **0.0.8(602)** est compilée et vérifiée depuis
[f015b6cb](https://github.com/TarbleFR/RewindBox/commit/f015b6cba870147b4ee1f2a2deb9bae72eae743b),
[run41085116632](https://github.com/TarbleFR/RewindBox/actions/runs/41085116632),
job124164117275, tentative1. Le fichier est remis au mainteneur après
vérification indépendante; la clé privée éphémère est supprimée.

| Identité | Valeur |
|---|---|
| IPA | RewindBox-Build602.ipa |
| Octets | 189828656 |
| SHA256 | `ff99f2a72a5053b00543ef3efeeaf64423d8feaceb749fbe5069141c02b941f2` |
| Artefact chiffré | 12990819802,190223261octets |
| SHA256 ZIP chiffré | `1cc7f4f1d3e0c433bcdc7b5deefed64aaf0cb7f0b7c0d3c151b5a9876a31f165` |
| Core MeloNX conservé | 827f4653, payload original `b4beb50452ab3a36ad71e0415c4a775249bddf92c7db222899f3da2fc43521c4` |
| Core RPCS3 conservé | 378509e8, payload original `973f59bf02a1c51989dc880aefb8d4be8c4df6c27c2f1f1a63c240b7341d2bf8` |

Le seul changement produit par rapport à601 est le déplacement exact du bloc
initialisant le protocole JIT avant la boucle de traitement du helper. Les
améliorations cumulées des deux cores, les sources hôtes, les options et les
composants natifs sont conservés. Ni moteur ni suite native inchangée n’est
recompilé/rejoué. La préparation binaire MeloNX(114entrées,151membres) reste
exacte; le digest historique du helper dans le reçu du producteur reste préservé,
avec une exception strictement limitée à cette relocation de ressource hôte.

La régression est reproduite sur le script601 entier, puis corrigée:99contrôles
du script complet,101contrôles du protocole et14sessions Apple JavaScriptCore.
Les3342contrôles Swift de politique et23tests Flutter sont authentifiés à leurs
sources originales. Tous gardent leur origine; la livraison ne les présente pas
comme de nouvelles exécutions. Détails:
[diagnostic et correction](melonx-jit-helper-initialization-2026-10-30.md).

Le véritable ZIP téléchargé passe SHA256, taille et CRC; l’IPA déchiffrée passe
ses deux sommes de contrôle internes. Le script effectivement empaqueté a le
SHA256 `fe162e0bd44471aa930db8582203b85ed135baf51712b57249dfcbfc6fe112fc`.
Les88images Mach-O iOSARM64,85empreintes de sections et trois conteneurs
fat mono-ARM64 sont inspectés; huit bundles affichent0.0.8(602). Les deux
payloads compilés, leurs interfaces et les reçus originaux sont vérifiés
contre les archives réelles de leurs producteurs. Apple CI vérifie88signatures
ad hoc, y compris le ZIP final; le contrôle Linux ne réexécute pas codesign.
Xcode prend363.512s et signature/export50.050s: une compilation de l’application.

Reçu: [rewind602-delivery.json](evidence/rewind602-delivery.json).
Vérificateur: [verify_download602.py](evidence/melonx-jit-helper-init-20261030/verify_download602.py).
Pour reproduire ce contrôle, utiliser le checkout figéf015b6cb, les ZIP Core
originaux, le ZIP chiffré602, les métadonnées GitHub et le dossier déchiffré;
le script peut être exécuté depuis un checkout documentaire plus récent en
passant le checkout figé à `--repo`. Aucun programme natif n’y est rejoué.

Réinstaller avec SideStore, iOS18minimum. Aucun lancement physique TXM,
gameplay, gain FPS ou correction des autres symptômes Hogwarts n’est établi
par cette compilation. Le mainteneur réserve Smash à un nouveau journal; aucun
correctif de sa nouvelle latence n’est revendiqué. Aucune release publique,
tag ou suppression des données du joueur. **Ne pas réutiliser le numéro602.**
