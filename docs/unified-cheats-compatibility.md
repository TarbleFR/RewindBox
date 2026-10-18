# Adaptations de compatibilité du catalogue unifié

État au 18 octobre 2026 : seconde passe demandée par le mainteneur, après le
premier commit de code `2dec00b824bebd3dcf3f20df993c389f36a80d63`. Le principe
est de chercher une adaptation exécutable avant d'écarter une source. Une
conversion doit préserver l'édition, le programme entier, l'ordre des
instructions, les dépendances et la provenance. Les chiffres de ce document
décrivent les audits ciblés ; le total publié doit venir du manifeste final.
Aucune nouvelle IPA ni exécution sur appareil n'est attestée ici.

## Résultats concrets

| Famille | Adaptation ou correction | Résultat vérifiable | Limite conservée |
|---|---|---|---|
| RPCS3, collection Artemis déjà portée en YAML | Préserver les clés PPU et les noms de patch répétés au lieu de les écraser dans un dictionnaire YAML. | L'export intermédiaire passe de 662 à 1 884 enregistrements de programmes ; les variantes restent distinctes. | Ce sont des enregistrements source, avant filtrage final des paramètres et des éditions. |
| RPCS3, ancres YAML | Développer les `load` sans déplacement, dans leur ordre d'origine. | Le moteur source traite ces séquences récursivement avec un déplacement nul. Les sous-programmes restent complets. | Les déplacements non nuls ne sont pas remplacés par une approximation. |
| RPCS3, adresses | Réémettre les adresses numériques sous forme de chaînes `0x…` et les contrôler dans le bridge. | Le vrai parseur RPCS3 exige cette écriture pour les opcodes acceptés. Une adresse JSON décimale est refusée avant l'import. | Les valeurs, les tailles et les autres contraintes restent validées par le moteur natif. |
| Artemis NCL → RPCS3 | Retrouver une adaptation native déjà publiée par l'auteur, avec même nom, serial, APP_VER et séquence complète d'écritures `be32`, plus PPU explicite. | Premier audit : 1 083 blocs NCL associés à 713 documents natifs existants. | **Zéro nouveau programme unique** pour ces associations : elles apportent une provenance et une correspondance vérifiées. |
| Dolphin, Action Replay chiffré | Déchiffrer quatre blocs complets avec la vraie fonction Dolphin du cœur épinglé. | Les quatre blocs de `GTEP01` passent la parité et le CRC ; le résultat RAW est reproduit par un test portable. | Le dialecte reste Action Replay. Aucun remplacement par Gecko. |
| ARMSX2, RAW PS2 | Envelopper seulement les opérations RAW dont l'équivalence PNACH est démontrée ; permettre une source identifiée par serial exact sans inventer de CRC source. | Le bridge accepte une édition candidate confirmée et écrit au CRC exécutable réellement relu dans le moteur. | Un titre seul, un serial contraire ou un CRC source contraire ne permettent pas l'import. |
| mGBA, dialecte GBA indéterminé | Employer le vrai canal AUTO, sans inventer une version GS/AR. | Audit entier : 873 Delta, 6 XoEVOoX et 1 EventIslands passent ; 75 Delta et 4 EventIslands restent bloqués. | Décodage réel ; aucune édition ni efficacité Pokémon déduite. Un programme AUTO isolé ne se combine pas librement avec d'autres contextes crypto. |
| mGBA, routine Shiny RAW | Conserver la syntaxe VBA à deux-points et les 49 écritures ROM complètes. | Le parseur et la vraie entrée Libretro produisent 49 patches ROM. | Profil hôte borné, aucun renommage en GS/AR, aucune troncature. |
| FBNeo | Employer le fichier et les options natifs, associés au vrai driver. | Raccordement d'import complet avec choix désactivés et activation native volontaire. | Les callbacks Libretro du binaire livré sont sans effet ; le raccordement Apple doit être vérifié par la CI. |
| PicoDrive, notamment 32X | Employer le vrai décodeur MD Game Genie/RAW et les écritures natives, sans projection d'adresses SH2. | 523 des 658 programmes 32X examinés passent le profil borné ; les fonctions réelles et 2 475 patches en 99 appels passent les tests. | Adresses paires, portée ROM/main 68000 démontrée, valeur `FFFF` inutilisable dans ce callback ; RAM SMS/GG non implémentée. |

Les nombres ci-dessus ne doivent pas s'additionner au total du catalogue. Les
documents RPCS3 peuvent couvrir plusieurs éditions ; les associations NCL et
les miroirs peuvent désigner un même programme. La régénération finale et son
rapport doivent donner les nombres dédupliqués et les exclusions effectives.

## RPCS3 : correction de données et chemin natif réel

Le cœur livré expose déjà les quatre fonctions utilisées par le bridge :
`rpcs3_ios_install_patch_repository`, `rpcs3_ios_enumerate_runtime_patches`,
`rpcs3_ios_set_runtime_patch_enabled` et `rpcs3_ios_enumerate_games`. Leur
présence a été vérifiée dans la table des symboles Mach-O de l'artefact du run
`38178247609`, et non seulement recherchée comme texte dans le binaire.

| Élément épinglé | Valeur |
|---|---|
| Commit hôte du cœur RPCS3 | `dcf0df67b3edf923d5dd54071f5228e6cf6882b6` |
| Source du cœur RPCS3 | `22f1152783cef1f7e04af7b1c895173e28fd5b03` |
| SHA-256 du binaire contrôlé | `19718c30d3055dea049c5807e7ce0d5c7663fab4968362d2426562e9f85ba93d` |
| Collection YAML d'auteur | `chidreams/Artemis-Patch-Collection-RPCS3@21fc0ee86578f1452e42da01187eb852ab034b28` |
| Collection NCL | `bucanero/ArtemisPS3@d79b41e525e20251bd0d919100039ac0a6433956` |

La preuve reproductible est dans `test/unified_native_rpcs3_exports.json` et
`test/unified_native_exports_test.py`. La sémantique des ancres et des adresses
provient de `Utilities/bin_patch.cpp::add_patch_data` et de
`Utilities/bin_patch.h::patch_type_uses_hex_offset`, dans le
[commit exact du cœur](https://github.com/XITRIX/rpcs3/blob/22f1152783cef1f7e04af7b1c895173e28fd5b03/Utilities/bin_patch.cpp).
Une ancre `load` à deux éléments reçoit un déplacement nul. Le parseur ajoute
ses enfants dans l'ordre. Une conversion ciblée peut donc développer cette
séquence. Le bridge accepte les instructions natives ainsi développées et
refuse une adresse dépourvue de préfixe hexadécimal.

L'import conserve les programmes désactivés. L'activation demandée est
appliquée **au prochain lancement du jeu**. Le vrai patch engine vérifie alors
le PPU, le serial et APP_VER ; le bridge ne déduit pas un PPU du seul titre.
Un fichier personnel `<serial>_patch.yml` non géré par le catalogue produit un
conflit explicite et reste intact. Les fichiers globaux `patch.yml` et leur
sauvegarde sont restaurés après validation. Un catalogue invalide ou une API
optionnelle absente ne bloque pas le démarrage normal du jeu ; seule une
impossibilité matérielle de restaurer les fichiers globaux peut arrêter ce
chemin pour éviter un état incohérent.

## Artemis NCL : ce qui peut être relié, ce qui demande un interpréteur

`tools/cheats/unified_native_artemis.py` est un outil de correspondance en
lecture seule. Il n'installe aucun fichier et ne produit pas un faux PPU. Son
entrée est l'archive NCL épinglée et l'export structuré des documents YAML
d'auteur. Pour chaque association, il conserve le bloc NCL original, son
encodage, l'empreinte du fichier, les écritures ordonnées et le document natif
cible avec son empreinte. Les versions `av01.01` sont distinguées des versions
de disque `v01.00`. Une version `v` seule reste ambiguë pour cette passe.

La vérification exige un bloc mode `0`, des écritures simples de quatre octets,
un nom identique après normalisation des espaces et de la casse, un serial et
une APP_VER explicites, et un document d'auteur qui déclare lui-même ces
contraintes et un PPU. Elle refuse un bloc partiellement correspondant. Les
713 documents associés ne deviennent pas 713 nouveaux cheats : ils existaient
déjà dans la publication native. La fusion de provenance doit se faire sur le
document entier et les contraintes, avec déduplication.

Le reste du NCL ne peut pas être traduit en remplaçant son extension. Le
[moteur Artemis épinglé](https://github.com/bucanero/ArtemisPS3/tree/d79b41e525e20251bd0d919100039ac0a6433956/ArtemisPS3-PRX)
implémente notamment les écritures répétées, les opérations OR/AND/XOR, les
pointeurs, les conditions, les copies mémoire et les recherches de motifs.
Le mode d'écriture constante est traité dans sa boucle d'exécution. Les
[instructions d'utilisation](https://github.com/bucanero/ArtemisPS3/blob/d79b41e525e20251bd0d919100039ac0a6433956/docs/INSTALLATION.md)
décrivent aussi l'attachement en cours de jeu. Un patch statique au démarrage
ne reproduit pas une boucle de gel de données, un pointeur recalculé ou une
recherche mémoire exécutée après chargement d'un niveau.

L'audit des exports du cœur RPCS3 exact ne trouve aucune API NetCheat ni API
publique générique de lecture/écriture mémoire permettant d'implémenter ces
comportements depuis le bridge actuel. `enumerate_runtime_patches` renvoie
des métadonnées ; elle n'exporte pas les instructions complètes à fusionner.
Pour ouvrir davantage de NCL, il faut soit une adaptation native d'auteur
avec PPU/serial/APP_VER et opérations équivalentes, soit un vrai interpréteur
NetCheat raccordé au cycle mémoire du cœur, avec tests des pointeurs,
conditions et fréquences d'application. Ce prérequis n'est pas résolu par un
renommage, un hash inventé ou une promesse de compatibilité.

La piste indexée `chidreams/Artemis-to-RPCS3-Patch-Converter` a aussi été
examinée : la page annoncée décrivait un convertisseur alpha, sans
implémentation exécutable vérifiée dans les éléments observés. La nouvelle
vérification du dépôt et de son API le 18 octobre renvoie HTTP 404. Cette piste
ne sert donc pas de preuve d'un convertisseur disponible dans l'intégration.

## Dolphin : quatre petits apports préservés

Le `GTEP01.ini` de la collection Dolphin contient quatre programmes Action
Replay chiffrés : `Everything Unlocked`, `Infinite Lives`, `Downhill Boost
(Press X)` et `Time Trial: Found 5 Coin Pieces`. Les dix lignes d'origine sont
regroupées en leurs quatre programmes entiers. Leurs résultats RAW restent
des instructions Action Replay, avec conditions et ordre inchangés.

`test/unified_native_dolphin_ar_vectors.json` conserve les lignes chiffrées,
les sorties exactes, les pins des sources et les empreintes du décodeur.
`test/unified_native_dolphin_ar_test.py --fetch` ne récupère que
`ARDecrypt.cpp` et `ARDecrypt.h` du
[pin Dolphin iOS](https://github.com/OatmealDome/dolphin-ios/blob/7cac54161659421ed95c2cd1c0b0746539a4cd38/Source/Core/Core/ARDecrypt.cpp),
vérifie leur SHA-256 et exécute la vraie fonction. Les dépendances remplacées
dans ce test sont les types entiers, les messages, la conversion en majuscules
et le byte-swap ; la cryptographie, la parité et le CRC restent ceux du moteur.
Les quatre vecteurs passent. Une altération du bit de parité est rejetée.
Ce test ne reconstruit aucun cœur d'émulation.

Les formats Gecko et Action Replay existants restent séparés. Les conteneurs
TXT/INI/GCT servent à extraire un programme natif complet, sans conversion de
console. Le GameID et la révision restent des contraintes indépendantes : une
source sans révision demande une confirmation, une révision connue contraire
est refusée. Les mentions libres de révision dans une note ne sont pas
transformées automatiquement en portée valable pour toutes les versions.

## PS2 : RAW, serial et CRC sont trois questions distinctes

La [documentation PCSX2 sur les patches](https://github.com/PCSX2/pcsx2-net-www/blob/main/docs/advanced/writing-patches.md)
décrit le type `extended` comme l'interprétation de codes RAW. Cela autorise
une enveloppe PNACH pour les opérations revues ; cela ne démontre pas que
tous les codes de tous les dispositifs PS2 sont interchangeables. Les
programmes chiffrés demandent un décodeur réel et une preuve de leur format.
Les opcodes avancés et les sauts conditionnels demandent une vérification de
leur sémantique entière, pas seulement deux mots hexadécimaux bien formés.

Le nouveau chemin hôte accepte une source sans CRC uniquement si elle fournit
un serial `ps2-disc-serial` exactement égal au serial courant et que
l'utilisateur a confirmé l'édition candidate. Il exige un CRC moteur réel de
huit chiffres, différent du wildcard zéro. Tout CRC source contraire reste
bloquant. L'original n'est pas enrichi d'un faux CRC : le reçu conserve
`game` et, séparément, `mapped_target`, l'identité réelle utilisée pour le
fichier PNACH. Le CRC est relu dans la file du moteur avant écriture.

Les fichiers qui répètent un titre de section autour d'une condition et de
son corps restent un seul programme activable. Un test couvre le cas
`[L1+L2 For Max Gil]` répété : la condition et l'écriture suivante restent
ordonnées sous un seul interrupteur. Un catalogue CheatDevice dépourvu de
serial ne franchit pas cette règle par un titre ressemblant. Un éventuel
rapprochement avec PNACH doit prouver le programme entier pour l'édition
identifiée ; il ne donne pas l'identité du jeu à tous ses autres codes.

L'essai sur la publication officielle CheatDevice a porté sur 1 483 jeux et
156 977 programmes. Aucun titre ne fournit un serial. Parmi eux, 131 174
programmes RAW 0/1/2 sont techniquement convertibles mais restent non
importables faute d'édition attestée. Les 25 803 autres sont réservés :
25 369 pour des types, conditions ou hooks non convertis, 434 pour la largeur
ou l'alignement. Aucun CRC n'a été déduit d'un titre. Le parseur
`parse_cheatdevice_pnach` accepte des identités explicitement attestées pour
ouvrir ultérieurement ces programmes, sans étendre le CRC d'un PNACH à tous
les autres codes d'un jeu.

Un dernier essai a comparé ces titres au
[`GameIndex.yaml` du vrai pin ARMSX2](https://github.com/ARMSX2/ARMSX2/blob/9d989ca933a85bb2f1d111fd3b9e5742ac7d2fbe/bin/resources/GameIndex.yaml),
SHA-256 `61c77b789ccde856096f024e4a3eef6891e15ca59c127e0dd13e762a7d338a7e`,
qui contient 12 841 entrées. La normalisation conserve les mots et les
marqueurs d'édition ; elle ne change que NFKC, casse, ponctuation et espaces.
Sur 1 483 titres, 1 035 correspondent exactement à un titre du GameIndex :
806 ont plusieurs serials possibles et 229 un seul serial global. Toutefois,
aucun des 1 483 titres ne déclare une région ; ni l'en-tête de la base ni son
README n'attestent une région globale. Les mots `World Cup` ou `US Navy
Seals` font partie de titres, pas d'une preuve régionale. Le contrat
« titre exact + région explicite + édition/serial unique » produit donc
**zéro association éligible**. Aucune identité dérivée n'a été ajoutée.
Le blocage restant est l'identification de l'édition régionale, et non une
affirmation que le RAW PS2 serait techniquement inconvertible.

## GBA : le vrai décodeur et les vrais formats

Le binaire mGBA livré dans l'artefact `11928513314` du run `38638115521` porte
la version `0.11-212-7a12d6d` et le SHA-256
`c7026dc4d8a799be2d991faa3d4e2286011d97f9b11fb1e2ef6ba77ebca66218`.
Le commit primaire correspondant est
[`libretro/mgba@7a12d6d4b9acb14c0ae62c9166b6a2f3d08007f6`](https://github.com/libretro/mgba/tree/7a12d6d4b9acb14c0ae62c9166b6a2f3d08007f6).
`test/unified_native_mgba_test.py --fetch` compile seulement ses parseurs et
décodeurs GBA, listes et utilitaires nécessaires. Il ne construit pas
l'émulateur. Les messages et les callbacks de breakpoint non exécutés dans
l'audit sont remplacés ; le décodage et ses états restent ceux du cœur.

Le vrai `mCheatAddLine(..., 0)` accepte les paires CodeBreaker 8+4 et les
paires 8+8 via l'autodétection. Cette dernière compare plusieurs scores de
probabilité et conserve une version dans son état. Elle permet le dialecte
`gba-auto` sans affirmer une attribution historique v1 ou v3. Le rapport
versionné `tools/cheats/unified-gba-proof.json`, SHA-256
`401c9581a55d84df6849c733aa808340c0bd2d5f917ad1ee9b8e557e5073e2af`,
relie chaque programme et sa fermeture de dépendances aux traces réelles.
La promotion exige les empreintes exactes, toutes les lignes acceptées,
aucun état incomplet, aucun paramètre restant et aucune cellule source
invalide. Un master reste attaché au programme qu'il conditionne. Un mot de
neuf chiffres n'est pas réparé.

Les 873 programmes Delta acceptés proviennent des 948 examinés. Ce ne sont
pas 873 nouveaux effets uniques ni 873 essais de ROM. Les six programmes
XoEVOoX ont été vérifiés avec leurs masters USA/Japon. Le programme français
EventIslands sans template passe ; les quatre variantes paramétrées restent
bloquées. La région et la révision restent des contraintes indépendantes du
décodage.

La syntaxe RAW VBA est distincte : `GBACheatAddLine` détecte `:` avant les
états crypto GameShark/CodeBreaker. Elle crée une écriture RAM ou un patch ROM
de la largeur exprimée par la valeur. Le profil `gba-vba-raw` conserve cette
syntaxe. La RAM est bornée aux plages physiques EWRAM
`02000000..0203FFFF` et IWRAM `03000000..03007FFF`, avec contrôle de la largeur
et de la fin de plage ; les miroirs et registres d'entrée/sortie ne sont pas
ouverts. Shiny conserve ses 49 lignes ROM de quatre octets, dans leur ordre.

La vraie entrée `retro_cheat_set` transmet des lignes de 13 ou 17 caractères.
La ligne canonique `0200E924:96` de 11 caractères ne parvient donc pas seule
au parseur. Le formateur hôte conserve deux espaces après cette valeur de
deux chiffres, avant `+` **et à la fin du programme**. Les valeurs de quatre
ou huit chiffres occupent déjà 13 ou 17 caractères. Le test extrait et
compile la fonction `retro_cheat_set` exacte ; il vérifie les largeurs
1/2/4, Shiny entier et l'identité des écritures RAM après un seed CodeBreaker
préalable. Vecteurs et SHA des sources sont dans
`test/unified_native_mgba_vectors.json`.

AUTO garde une contrainte réelle : le cœur réutilise un même set et son état
crypto entre plusieurs appels. Les programmes promus par preuve individuelle
portent donc `mgba_auto_isolated:true`. Le raccordement refuse l'activation
avec un autre record GBA non VBA ; un programme avec ses masters reste un
seul record atomique. Les programmes VBA à deux-points peuvent coexister car
ils contournent cet état crypto. Le refus d'un second choix incompatible doit
rester explicite et préserver la sélection précédente.

## Libretro : autres voies examinées

L'audit MiSTer a examiné les 14 familles de la publication, soit 14 826
archives, 1 041 648 programmes natifs et 1 568 371 tuples. Il s'agit des
familles de systèmes, et non des 14 compléments de sources de la recherche
initiale. `tools/cheats/unified_adapt.py` conserve les tuples sources et
applique des conversions bornées par leur sémantique réelle.

| Familles MiSTer | Résultat de l'essai |
|---|---|
| NES | 27 283 programmes dans le profil revu avant déduplication : adresse CPU ROM et comparateur préservés dans la syntaxe native Nestopia. Les sélections ambiguës restent bloquées. |
| GBA | 148 072 programmes dans le profil RAM revu avant déduplication : écritures physiques EWRAM/IWRAM à la fréquence vidéo, via le chemin VBA sans contexte crypto. Les autres espaces mémoire, conditions et sélections ambiguës restent bloqués. |
| PSX | 381 392 programmes disponibles avant déduplication ; 63 756 sélections ambiguës et 7 086 hors profil restent bloqués. Conditions et répétitions utilisent un programme compact entier de 255 octets maximum ; les écritures 30/80 indépendantes peuvent être transmises en batches ordonnés sans troncature. |
| Game Boy, Mega Drive, Mega CD, SMS, SNES | Le matériel remplace la valeur lue sur un bus ; ce comportement ne se confond pas avec une écriture RAM périodique. Le mapping ROM/banc et les comparateurs doivent être démontrés avant une conversion supplémentaire. |
| N64 | Les champs d'opération, masques d'octets et règles d'endian ne sont pas des opcodes GameShark. Une conversion exige une équivalence explicite de ces opérations. |
| Atari Lynx, Jaguar, PC Engine/CD, Virtual Boy | Adaptateur d'activation natif absent dans le périmètre actuel. Les tuples ne deviennent pas des cheats d'un autre système. |

Ces quantités sont des apports examinés avant filtrage et déduplication,
pas des nombres à additionner au manifeste publié. Une restriction de
sélection conserve le programme entier en attente ; elle ne supprime pas
une partie de ses instructions pour le faire passer.

Le binaire FBNeo livré
`737bd97038db59e17d2ede4e68249be238c49bb31e3e93eced03a6e10e486625`
possède des callbacks cheats Libretro sans effet. Le raccordement utilise
donc les fichiers gérés sous `System/NeoStationFBNeo/fbneo/cheats`, le driver réel obtenu par
`BurnDrvGetTextA(DRV_NAME0)`, et les options natives de choix de cheats. Les
blocs et leurs choix restent complets, avec `default=0`, conflit explicite
pour les fichiers personnels modifiés, et activation volontaire après
rechargement du contenu. Un dossier temporaire isolé reçoit uniquement les
INI régénérés dont le reçu SHA-256 correspond ; les INI/DAT/VCT personnels
restent intacts. Le chemin natif exporté `szAppCheatsPath[260]` est raccordé
avant le premier chargement des cheats, avec contrôle à chaque callback
d'environnement. Les inclusions non résolues et les variantes matérielles
NES/FDS/SNES restent bloquées. Désactiver l'ensemble appelle aussi
`CheatUpdate`, car l'application native lit un état mis en cache. Les
sources du commit `1a03a1546cfa72f82fcba85267c1381a70437480` sont
`src/burner/libretro/libretro.cpp`, `src/burner/conc.cpp` et
`src/burn/cheat.cpp`. Le test spécifique est
`test/unified_identity_fbneo_native.py`, accompagné des tests de magasin et
de bridge ; leur exécution Apple doit être attestée par la CI.

Pour PS1, le vrai parseur Beetle au commit
`10e4b0c6ceae20daa65ddf436a4445dddd0982d2` permet d'étendre le sous-ensemble
revu aux conditions et répétitions dont la structure est complète.
`test/unified_identity_ps1_source_test.py` exécute les comportements visés
sous ASAN/UBSAN. Une condition isolée ne devient pas une écriture autonome.

MAME2003 Plus et Flycast ne figurent pas dans les 34 cœurs livrés examinés.
Un parseur de fichiers seul ne peut pas créer un moteur absent. Flycast
possède une table native d'adresses, tailles, types, répétitions et conditions ;
la réétiqueter GameShark ferait perdre ces informations. Il faut ajouter et
qualifier le bon cœur, son identité et son vrai importeur.

## PicoDrive : un raccordement 32X sans changement de cœur

Le PicoDrive livré porte la version `2.05-1890c29`, SHA-256
`3c5d6181904d4d644cad530008a202931237ab038ab6a064e4b4f68ecbc4592b`.
Le commit primaire
[`1890c2932234c9d30f4cd3851d02228baae8f09e`](https://github.com/libretro/picodrive/tree/1890c2932234c9d30f4cd3851d02228baae8f09e)
montre le vrai chemin : `retro_cheat_set` décode les tokens, puis
`PicoPatchApply` applique les patches ROM ou les écritures du bus 68000 à
chaque frame. Le décodeur MD est le même pour Mega Drive, 32X et Pico ; il
ne convertit pas une adresse SH2 en adresse 68000.

Le profil accepte uniquement les tokens MD Game Genie de neuf caractères ou
RAW `AAAAAA:VVVV`, avec adresse décodée paire, valeur différente de `FFFF`,
et portée limitée aux offsets ROM inférieurs à `400000` ou à la RAM
principale 68000 `FF0000..FFFFFE`. Pour Mega CD, seul ce dernier espace est
ouvert ; le sous-68000 et ses banques ne sont pas projetés sur la RAM
principale. La valeur `FFFF`, pourtant une valeur de mot valide, est rejetée
par le callback livré comme sentinelle d'erreur. La rendre applicable
demanderait de corriger ce test dans le cœur, pas de changer les octets du
cheat. Les adresses impaires ne sont pas transformées arbitrairement en
écritures d'octets.

Dans la publication Libretro épinglée, 29 fichiers 32X contiennent 658
programmes examinés : 523 passent, 121 ont des adresses de mot impaires,
12 sont vides ou paramétrés, et 2 rencontrent la sentinelle. La preuve
conserve les empreintes du programme entier, le membre source, son empreinte
et tous les mots décodés. Ces nombres précèdent la déduplication et ne sont
pas une mesure d'effets testés sur les jeux commerciaux.

Le buffer natif impose 255 octets maximum par appel et 11 par token.
Les callbacks ajoutent les patches à un tableau dynamique et n'appliquent
pas immédiatement les mutations ROM. Des lots d'un même programme restent
donc possibles si tous les appels se terminent avant la prochaine frame.
Les bornes hôtes existantes de 8 192 octets par programme et 99 appels
agrégés préservent cette exécution ; aucun quota artificiel de 1 024 patches
n'est ajouté. Le programme conserve un seul interrupteur et son ordre.

`test/unified_native_picodrive_test.py --fetch` récupère les trois fichiers
primaires épinglés, vérifie leurs empreintes et exécute les vraies fonctions
de décodage, import, application et reset. Le bus RAM est un double de test
borné ; les mutations ROM sont réelles dans le buffer du test. Le décodeur
pur réellement livré dans `LibretroPicoCheatDecoder.h` est comparé à
l'original sur 4 096 vecteurs Game Genie. Le maximum de 99 lots de 25 tokens
ajoute 2 475 patches, applique le dernier recouvrement ROM, puis restaure
l'original au reset. Un test séparé démontre qu'un code SH2 à huit chiffres
n'est pas accepté et que le chemin RAM SMS/GG livré ne réalise aucune
écriture. Le profil ne prétend donc pas ouvrir ces espaces.

## Autres réserves dont une conversion changerait le sens

L'audit des entrées RetroArch `handler=1` a trouvé 892 enregistrements :
715 SNES et 177 Mega Drive. Tous utilisent `cheat_type=0`, c'est-à-dire
`CHEAT_TYPE_DISABLED` dans le `cheat_manager.h` du RetroArch examiné. Ces
entrées décrivent des déclencheurs de vibration qui lisent la mémoire ; elles
n'écrivent pas une valeur de cheat. Les transformer en PAR inventerait donc
un effet sur le jeu. Les échantillons et l'analyse sont conservés dans
`analysis/handler1-audit/handler1-samples.json` pendant la préparation ; les
preuves pérennes de source doivent être reprises dans le rapport de génération.

Les formats Switch/Atmosphère ne sont pas des cheats des consoles RetroArch,
PS2, PS3, GameCube ou Wii. MelonX est un moteur externe dans le périmètre
actuel. Pour exploiter ces données, il faut un contrat d'import de ce moteur
et le couple TitleID/BuildID exact. Une conversion inter-console n'est pas
une adaptation valable. Les données Vita, Wii U/Cemu ou MAME qui nécessitent
leur interpréteur propre suivent la même distinction.

Azahar ne devient pas compatible parce qu'il expose `retro_cheat_set` : le
chemin examiné ne réalise pas l'application des cheats. Le support 3DS doit
venir d'une implémentation réelle du cœur et d'une preuve d'effet RAM.
Au commit `5f3306d13cab40bbd5cf38f2cf3ae8b6e6eedca6`, les deux callbacks
vides sont dans `src/citra_libretro/citra_libretro.cpp`. Les API internes
GatewayCheat et CheatEngine existent, mais le binaire livré n'expose pas
d'accès hôte sûr à son système actif ni à son moteur de cheats connecté.
Le correctif doit raccorder ces callbacks au moteur existant, ne gérer que
ses propres entrées et préserver les cheats personnels. Le workflow actuel
télécharge une collection de cœurs épinglée ; il ne prouve pas une chaîne de
compilation source Azahar iOS. Un build ciblé de ce seul cœur, sa toolchain
et un test mémoire GateShark sont les prérequis concrets supplémentaires.

## Vérifications et critères de publication

Les commandes ciblées suivantes ont passé en environnement Linux pour les
changements de cette seconde passe :

```sh
python3 test/unified_native_artemis_test.py
python3 test/unified_native_dolphin_ar_test.py --fetch
python3 test/unified_native_mgba_test.py --fetch
python3 test/unified_native_picodrive_test.py --fetch
python3 test/unified_native_ios_test.py
git diff --check
```

Le troisième test exécute ici le parseur C++ portable et signale explicitement
le saut des contrôles Apple. Les tests Foundation et la compilation des sept
sources Objective-C++ modifiées requièrent la CI macOS ; leurs résultats
doivent être ajoutés après le passage correspondant. Les tests du magasin
couvrent aussi les métadonnées de mauvais type, l'import désactivé, les
variantes homonymes, les dépendances indivisibles, la cible CRC séparée de la
source, et la préservation des fichiers RPCS3 personnels et globaux.

La publication du pack actif doit suivre la régénération finale, l'examen de
ses diagnostics et les validations Apple. Les programmes trop longs ou
incomplets sont refusés entiers ; aucune instruction n'est tronquée pour
gonfler un compteur. Le téléchargement global ne provoque aucune activation.
