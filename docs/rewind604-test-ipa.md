# RewindBox 604 — correctifs MeloNX et lancement plus direct

L’IPA a été compilée, téléchargée, déchiffrée et vérifiée indépendamment,
puis enregistrée pour remise privée.

La source d’assemblage est `60add3d79b3e4d9d76b68ef154cb5d3f8772c323`,
sur `Claude`. La base produit reste la dernière IPA livrée, Build 603,
source `808b64e16bb0f5112a2a7b5a07b400c19bb9cfbd`. Aucun composant retiré,
notamment Mario Kart Pad, n’est réintroduit. Les identifiants internes
NeoStation restent compatibles ; le nom public demeure RewindBox.

## Modifications de l’application

Le delta produit par rapport à 603 comprend exactement quatre chemins :

- `lib/l10n/melonx_unreal_profile_locale.dart` : catalogue des 12 langues ;
- `lib/widgets/melonx_unreal_profile_dialog.dart` : traductions complètes,
  explications d’erreur localisées et détails techniques dépliables ;
- `lib/widgets/melonx_internal_playlist_actions.dart` : libellé traduit ;
- `packages/melonx_internal_bridge/ios/Classes/MeloNXInternalBridgePlugin.swift` :
  présentation du jeu sans animation.

Les autres racines produit restent identiques à 603. Le profil Unreal conserve
son consentement, son état désactivé par défaut et sa désinstallation réversible.
Aucune sauvegarde, donnée de jeu, clé, association JIT ou cache n’est effacé.

## Moteurs retenus et preuves

| Composant | Source et validation |
|---|---|
| MeloNX compilé | `ada4058f5738465ac882934bb87224b637bcd0a1` ; run `41118873328`, job `124280125758` |
| Validation séparée des mêmes binaires | `510e683a149e811e68ea6ab5e766e85c44ab1057` ; run `41121572662`, job `124288787086`, réussi |
| Archive MeloNX retenue | artefact `13009521221`, 87 656 173 octets ; SHA-256 `ed70ba31b1b52fc0fbd55e695b25cc4254d5f90c4f86b930d8bf2958235ac278` |
| Bibliothèque MeloNX iOS originale | SHA-256 `7620fa3009e6df971665e7b8adec1a0bac654e6efa4bc3fceb292daefa6adb55` |
| Dernier RPCS3 compilé avec succès | `a4d0c9a5e00ace8d2036c62ef1a653e50bb79a3a` ; run `41117115264`, job `124274114161` |
| Archive RPCS3 retenue | artefact `13007148559`, 29 263 531 octets ; SHA-256 `b260bb4fa48b72ff889d6e9c4eb061591676b18e12427c0160a44974c9ff2b07` |
| Bibliothèque RPCS3 iOS originale | SHA-256 `f2f167af5cfa7889e76af150b6c9f02e6a19b7f3e881de0397bcafe185dbe19a` |

Le premier run MeloNX reste en échec : compilation et trois contrôles Apple
réussis, mais délai du test de démarrage trop court et diagnostic secondaire
ayant masqué son rapport. La validation séparée réutilise les mêmes octets,
préserve les 393 membres originaux et démontre deux sessions distinctes avec
exécution du code invité et libération de leur mémoire. Elle ne requalifie pas
le premier run. Aucun moteur ni contrôle historique inchangé n’est reconstruit
ou rejoué pour la livraison.

Le nouveau Core préserve V31 dans les masques de registres vectoriels, rétablit
le bouclage modulo 32 des listes et la lecture de destination de TBX. Il termine
la publication différée des rapports d’occlusion aux deux chemins de syncpoint,
transmet le vrai résultat du backend conditionnel et lui laisse ses réservations.
Le contexte ajouté au défaut mémoire décrit le dernier dispatch connu ; il
ne prétend pas fournir l’instruction fautive et n’atténue pas la page de garde.

Le traitement par lots des requêtes, le repli JIT sur refus d’allocation explicite,
la lecture de profondeur et les corrections de petits mipmaps de 603 restent.
Les contrôles ciblés de l’hôte ont réussi : 19 tests Flutter, analyse sans erreur
ni avertissement et 14 vérifications UIKit. Leur run original reste en échec au
parseur de reçu ; la récupération stricte authentifie ses sorties originales.

## Chargement et limites physiques

Le journal 603 mesure 12,441 s entre sélection et première présentation de
Hogwarts. Cinq lancements consacrent 0,510–0,513 s à l’animation UIKit désormais
supprimée. Le moteur démarre toujours dans `viewDidAppear`, après attachement
de sa vue, avec les contrôles JIT, génération et audio conservés. Cette mesure
décrit l’ancien coût ; le gain réel de 604 sur iPhone reste à mesurer.

L’attente GPU intermittente d’environ une minute n’est pas démontrée corrigée.
La disparition du crash de Hogwarts, l’application effective des CVar Unreal,
la récupération des textures noires et un gain de FPS restent non établis sur
appareil. Les tests simulateur et la compilation ne remplacent pas cette preuve.

## Livraison vérifiée

| Élément final | Valeur vérifiée |
|---|---|
| Version vérifiée | `0.0.8 (604), application et sept extensions` |
| Run / job / tentative | `41122746325` / `124293077616` / `1` |
| IPA | `RewindBox-Build604-60add3d79b3e4d9d76b68ef154cb5d3f8772c323-cold.ipa` ; `189 410 630` octets |
| SHA-256 IPA | `50a248491142fdee7148f0d695d6716a385e780a621506367b78b4308326c095` |
| Contrôles indépendants des octets téléchargés | `CRC ZIP ; 88 images ARM64 iOS ; 85 empreintes ; trois conteneurs mono-ARM64 ; moteurs, hôte et notices` |
| Signatures vérifiées dans Apple CI | `88 ; structure vérifiée séparément sous Linux, sans revendiquer codesign Apple local` |
| Compilation / scellement et export | `372,707 s / 49,942 s` |

Téléchargement : [Télécharger RewindBox-604.ipa](https://chatgpt.com/library?file_id=libfile_4913b71897348191ad559a63dc9f8f3d&account_id=personal).
Installation via SideStore, iOS 18 minimum, après re-signature.
État de la clé privée éphémère après remise : `supprimée après vérification et enregistrement`.
Aucun tag ni release publique.

Preuves finales : `docs/evidence/rewind604-delivery.json` et reçus
de validation. Analyse : `docs/melonx-build603-guard-crash-2026-10-30.md`.
