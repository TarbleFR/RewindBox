# RewindBox603 — Core MeloNX corrigé pour Hogwarts

Le mainteneur demande une nouvelle IPA privée avec le Core déjà compilé.
Cette autorisation remplace la portée « Core seul » du cycle précédent.
La dernière application livrée602, sourcef015b6cb, reste la base : ses cinq
racines produit hors `native` sont conservées exactement. La seule addition
dans `native` est `EmbeddedStartupTrace.cs`, incluse dans le Core1630bd02.
Le helper JIT corrigé602 reste inchangé. Aucun moteur ni ancien test natif
n’est recompilé/rejoué par la recette de livraison.

| Composant | Source et preuve conservée |
|---|---|
| MeloNX | `1630bd0230c9431de92faec9c5e2662262b1ede6`, run41097173966/job124205742820 |
| ZIP Core | artefact12995694624,87595452octets, SHA256 `7dd844774ff7991a406db8d37e35bba8f7b3b46284d1a8e05359b1d3ba135928` |
| Dylib iOS |37618024octets, SHA256 `423f2af029a5c1319d518a67114dc0b963ba5399747960cb6155b44014037ddc`|
| RPCS3 | `378509e82d360bc2cb2fcc9fb23d4d9d98787506`, artefact12968555534 |
| Application602 | SHA256 `ff99f2a72a5053b00543ef3efeeaf64423d8feaceb749fbe5069141c02b941f2` |

Le Core corrige les lectures littérales ARM64 de32bits traduites à tort
en64bits, les chargements S/D/Q31 omis et les véritables lectures vers ZR.
Les diagnostics ajoutent des mesures par étape de l’initialisation GPU et un
contexte à l’exception de page de garde. Ils conservent les erreurs natives et
l’étape du lancement. Les117 entrées de préparation,154 membres adaptés et
tous les lots antérieurs sont authentifiés. Les12167 contrôles de traduction,
8 contrôles de diagnostic,35 reçus historiques et deux sessions NativeAOT
simulateur gardent leur origine Apple. Ils ne sont pas présentés comme un test
physique de Hogwarts. Le crash précis et l’attente GPU restent à confirmer et
diagnostiquer sur l’iPhone ; aucune purge de cache ou promesse de FPS.

La livraison603 réutilise les3342 contrôles Swift,23 tests Flutter et
14 sessions JavaScriptCore du helper dont les entrées restent exactes. La
recette compile une fois l’application Release, vérifie les deux payloads
effectivement signés et tous les autres composants, puis chiffre l’artefact
privé. Seule la clé publique du destinataire est suivie dans Git. La clé privée
éphémère sera supprimée après vérification et remise du fichier final.

## Livraison vérifiée

La compilation privée a réussi depuis
`808b64e16bb0f5112a2a7b5a07b400c19bb9cfbd`,
[run 41102769156](https://github.com/TarbleFR/RewindBox/actions/runs/41102769156),
job `124223520172`, tentative 1. L’IPA téléchargée a été déchiffrée puis
vérifiée indépendamment avant son enregistrement.

| Élément final | Identité |
|---|---|
| Version | 0.0.8 (603), application et sept extensions |
| IPA | 189 835 284 octets |
| SHA-256 IPA | `4807cba308ec8fd0cf47a912afddaae8c0f781c20c42a8e14e7af61bfe44dddd` |
| Artefact chiffré | `13000847907`, 190 230 045 octets |
| SHA-256 archive | `3f8cfd963d67e63da8f4c166fa46fa9c17a2d7459aa6c77eaa98aaf95f2290b4` |
| Contrôles indépendants | CRC ZIP, 88 Mach-O iOS ARM64, 85 empreintes de préservation, trois conteneurs mono-ARM64, huit versions |
| Signatures | 88 vérifiées par Apple CI ; aucune vérification cryptographique codesign revendiquée sous Linux |
| Compilation de l’application | 385,015 s ; scellement et export 44,657 s |

[Télécharger RewindBox-Build603.ipa](https://chatgpt.com/library?file_id=libfile_3804daeef7a481919ad1f165d82e5ab3&account_id=personal).
Installation via SideStore, iOS 18 minimum. La clé privée éphémère a été
supprimée après vérification et enregistrement du fichier. Aucun tag ni
release publique.

La première tentative `41100584922` a échoué avant compilation : le contrôle
des étapes du producteur lisait une réponse API incomplète. La recette finale
interroge la collection des jobs du run exact et conserve les exigences de
source, identifiants, étapes réussies et empreintes du Core. Pour le job final,
les API ont aussi renvoyé `steps: []` après réussite. Les métadonnées originales
sont conservées telles quelles : le vérificateur indépendant utilise en plus
l’extrait du vrai journal, les reçus scellés des phases réussies et les octets
de l’IPA. Il ne reconstruit aucune liste d’étapes API fictive.

Preuves : `docs/evidence/rewind603-delivery.json` et dossier
`docs/evidence/rewind603/`. Aucun lancement physique de Hogwarts ni gain de
chargement GPU n’est établi ; ils restent à mesurer avec cette IPA. Aucun
correctif Super Smash Bros. Ultimate n’est revendiqué.
