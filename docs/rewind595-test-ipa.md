# IPA privée RewindBox 595 — derniers correctifs RPCS3 et MeloNX

Le mainteneur a demandé le 29 octobre 2026 une IPA privée contenant les derniers
correctifs des deux moteurs. La livraison prépare la version `0.0.8 (595)` sur
`Claude`, sans release ni tag public. Le résultat de compilation et les contrôles
du fichier livré seront ajoutés après leur exécution.

## Composants sélectionnés

| Composant | Source compilée | Run réussi | Artefact |
|---|---|---|---|
| RPCS3, correctifs globaux et affinements runtime | `f42573afc25842ca9a0068f4ad505bbfe5342623` | `40917423708` | `12917652510` |
| MeloNX Core85, mémoire, timers et synchronisation GPU | `3c0997d91ebfb5554656076a93a1f167ec948c67` | `40906908049` | `12912462226` |

Le Core RPCS3 iOS ARM64 de 77 268 488 octets porte le SHA-256
`05459149444fe5be32ffb8218ada79dd6a3b531377bd3d19e1bf34294dd0fbb8`.
Son archive de 29 118 830 octets porte le SHA-256
`4956f76388cbe2da7eeb87f45980a91391d05e3f71af16fdb163668efe3e2cad`.
Ses 349 entrées de validation, 92 entrées de fabrication, ABI 30, 88 exports,
313 sources natives préparées et 97 suppléments correspondent au dépôt actuel.
Les onze résultats Apple du candidat et les résultats historiques inchangés
conservent leurs origines distinctes. Aucun test natif n'est rejoué pour assembler
l'application.

Le Core MeloNX iPhone de 37 585 128 octets porte le SHA-256
`68fe61ddd412788d7dadc12e5e6226421f91c7354a3f61bfc0738b6635508588`.
Son archive de 87 451 078 octets porte le SHA-256
`defa8224442ccd455c7fa0542702abd2711294461818664ef168711f4baff912`.
Elle contient les douze correctifs du Core84 et les nouveaux traitements des
annulations de timers, des callbacks de flush, de la file de synchronisation et
des bornes des bitmaps. Les 87 entrées de préparation correspondent au dépôt ;
les 129 membres des sources préparées contiennent les trois différences revues
depuis Core84 et 126 membres inchangés. Deux tests Apple affectés ont été exécutés
et douze résultats inchangés ont été réutilisés. Les deux sessions de homebrew
sur simulateur utilisent le nouveau binaire, exécutent un SVC distinct puis
libèrent leur mémoire. Cela ne constitue pas une mesure de jeu sur iPhone.

## Application et NeoSwap

Les sources de l'application, ses ressources et ses dépendances correspondent
à l'IPA594 livrée, sauf `native/neoswap-storage/Store.cpp`. Ce correctif évite de
balayer les entrées à retirer lorsqu'aucun retrait n'est en attente. Il est du
code de l'application hôte et sera donc compilé avec l'IPA, indépendamment du
dylib RPCS3 réutilisé.

Le fichier exact porte le SHA-256
`9a951454d7e5124bea4ca1ee5589b1e4429df637dc4377b6c7e3775fcb1c99e4`.
La recette contrôle sa copie effective dans les sources de CocoaPods avant la
compilation. Les résultats Apple optimisé, ASan/UBSan et TSan déjà réussis restent
authentifiés sans nouvelle exécution.

## Livraison et vérification prévues

La recette conserve les identités d'origine des cores, vérifie les sources et
les artefacts, compile l'application Release, puis compare les binaires de l'IPA
signée avec les véritables bibliothèques téléchargées. Les contrôles de structure,
versions, signatures, ABI, contenus et notices de la livraison précédente restent
actifs. Les artefacts contenant l'IPA sont chiffrés pour une nouvelle clé de
destinataire ; la clé privée n'est pas versionnée.

L'installation nécessite une nouvelle signature avec SideStore ou un outil de
sideload compatible. Aucun gain de FPS, baisse de RAM en jeu, test sur appareil
physique ou correction visuelle constatée n'est établi par cet assemblage.
