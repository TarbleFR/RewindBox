# IPA privée RewindBox 595 — derniers correctifs RPCS3 et MeloNX

Le mainteneur a demandé le 29 octobre 2026 une IPA privée contenant les derniers
correctifs des deux moteurs. La version `0.0.8 (595)` a été compilée sur `Claude`.
Le [run corrigé](https://github.com/TarbleFR/RewindBox/actions/runs/40928805790)
réussit sur la source `d2e5029f8d7ca33eec279546d64a7f908285e804`, job
`123641427943`, tentative 1. Aucun tag ni aucune release publique n'est créé.
La validation indépendante du fichier téléchargé a ensuite réussi. L'IPA a
été enregistrée pour une remise privée au mainteneur et la clé privée éphémère
de transport a été supprimée après cet enregistrement.

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
code de l'application hôte et a donc été compilé avec l'IPA, indépendamment du
dylib RPCS3 réutilisé.

Le fichier exact porte le SHA-256
`9a951454d7e5124bea4ca1ee5589b1e4429df637dc4377b6c7e3775fcb1c99e4`.
La recette a contrôlé sa copie effective de 27 077 octets dans les sources de
CocoaPods et sa présence dans la liste des sources avant la compilation. Les résultats Apple optimisé, ASan/UBSan et TSan déjà réussis restent
authentifiés sans nouvelle exécution.

## Résultat de compilation et contrôles Apple

L'artefact chiffré `12921794075` contient l'IPA et ses preuves de validation.
Son archive ZIP fait **188 666 269 octets**, SHA-256
`9bbda35701fe6da477d95e9a043935096270ecf5aaa9158b4c0af20532341a35`.
Après téléchargement et déchiffrement, l'IPA fait **188 331 345 octets**, SHA-256
`cfc1079249e4168349896a69f34a150ddbc68e318aafbb954a06cb019b00374e`.
Cette empreinte concorde avec `SHA256SUMS`, le reçu de signature et les deux
reçus de validation des cores.

Les vérifications du runner Apple confirment les identités compilées d'origine,
les structures, versions, signatures ad hoc, ABI, dépendances et notices. La
signature conserve le code et les données comparés des **85 images du reçu
`signed-payload-identity.json`**, qui sont des images ARM64 simples. La validation
structurelle recense séparément **88 entrées Mach-O** ; les trois autres sont des
conteneurs universels à une seule architecture ARM64 : `App.framework/App`,
`objective_c.framework/objective_c` et `sqlite3.framework/sqlite3`. Ces trois
conteneurs sont couverts par les contrôles de structure et de signature, sans
empreinte avant/après dans l'inventaire des 85 images. Le reçu de signature
contient **88 vérifications ad hoc** réussies. Ces nombres décrivent des périmètres
différents.

Le binaire RPCS3 signé correspond au vrai Core téléchargé, avec ses 88 exports,
son ABI30, les identités PPU/SPU conservées, les sections de code et de données,
les commandes de chargement et le contenu LINKEDIT préservés hors ajustements
de signature autorisés. La comparaison relève huit octets d'alignement
supplémentaires avant la signature.
Pour MeloNX, le payload et les 47 exports requis correspondent au Core85
original ; la comparaison tient compte du changement d'identifiant de dylib
nécessaire à l'encapsulation dans `MeloNXCore.framework`.

L'application et ses **sept extensions** portent toutes la version `0.0.8 (595)`.
L'artefact reste chiffré avec la nouvelle clé de destinataire ; la clé privée
n'est pas versionnée. Les résultats de signature sur le runner ne valident
ni le provisionnement Apple, ni l'installation, ni le chargement sur iPhone.
Une nouvelle signature avec SideStore ou un outil de sideload compatible reste
nécessaire. Le paquet déclare iOS18.0 minimum et l'architecture ARM64.

## Durées et réutilisation

| Mesure | Durée |
|---|---:|
| Job corrigé complet | 1 017 s — 16 min 57 s |
| Compilation Xcode du job corrigé | 427,782 s |
| Signature et export IPA du job corrigé | 58,788 s |
| Compilation Xcode de la première tentative | 378,903 s |
| Xcode cumulé sur les deux compilations de l'application | 806,685 s |

Le job corrigé s'est déroulé de **19 h 13 min 51 s à 19 h 30 min 48 s**, heure
de Paris, le 29 octobre 2026. Ses 69 étapes exécutées ont réussi ; la seule étape
ignorée est la reconstruction StikJIT, car ses interfaces vérifiées ont été
récupérées dans le cache.

Il y a eu **deux compilations de l'application** : la première a été arrêtée
après compilation par la garde des notices, et la seconde a produit l'IPA.
Aucun core RPCS3 ou MeloNX n'a été reconstruit pour ces assemblages, et aucune
suite native historique n'a été rejouée. Les sommes des tâches parallèles du
résumé Xcode ne sont pas utilisées comme durées écoulées du job.

## Première tentative et correction de recette

Le run `40926266201`, source `929b644327157e542d8043f4c2d7b038a7b8e697`,
a compilé l'application avec succès en 378,903 secondes. L'étape d'intégration
des notices a ensuite refusé une référence Dolphin incorrecte : une substitution
du numéro de build avait aussi changé `594` en `595` à l'intérieur de son SHA.
Le binaire Dolphin réutilisé était inchangé ; sa notice conservait sa vraie
référence. Le contrôle a donc correctement arrêté la livraison avant signature.

La recette rétablit `7cac54161659421ed95c2cd1c0b0746539a4cd38`. Son contrôle
initial authentifie désormais les neuf pins de sources et de runs des composants.
Le contrôle négatif reproduisant exactement la référence erronée est rejeté
avant compilation. Les sources produit et les deux cores ne changent pas.
Seuls les diagnostics ont été conservés après cette tentative ; l'application
a donc été assemblée à nouveau après la correction. L'échec reste documenté dans
`evidence/rewind595/failed-929b6443.json`.

## Portée et état de remise

Aucun gain de FPS, baisse de RAM en jeu, test sur appareil physique ou correction
visuelle constatée n'est établi par cet assemblage. Les tests de moteurs sur
simulateur ou dans des fixtures ciblées gardent leurs limites d'origine.

La vérification indépendante du fichier téléchargé réussit : 5 350 membres ZIP
et leurs CRC, 522 fichiers de sources authentifiés, deux validateurs signés
inchangés, égalité exacte des 85 empreintes de préservation, contrôle strict des
trois conteneurs universels et comparaison complète du rapport de structure à
88 images. Les signatures cryptographiques restent vérifiées par le runner
Apple ; elles ne sont pas revérifiées sur Linux. Aucun test natif ou build
supplémentaire n'est exécuté pour ce contrôle.

Le premier vérificateur local rejetait à tort les trois conteneurs universels.
Son script et son échec sont conservés avec le diff de correction. La prise en
charge exige les trois chemins, tailles et SHA-256 exacts, une seule tranche
ARM64, son alignement et son remplissage, sans diminuer les contrôles des cores.
Cette correction d'outillage ne modifie aucun octet de l'IPA.

La remise privée persistante du fichier `RewindBox-Build595.ipa` est confirmée.
La clé privée de transport a été supprimée après sauvegarde. Le fichier reste à
resigner avec SideStore avant installation ; aucune publication publique n'a été
effectuée.

Les preuves de compilation et de validation Apple sont conservées dans
`evidence/rewind595/apple-delivery/`. Le reçu principal de remise est conservé dans
`evidence/rewind595-delivery.json` ; la validation indépendante est conservée
séparément dans `evidence/rewind595/verification/` avec sa portée exacte.
