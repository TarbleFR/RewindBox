# Catalogue de cheats unifié — intégration sur Claude

État de ce document : implémentation candidate du 18 octobre 2026. Le mainteneur
a autorisé l'intégration du catalogue commun pour les consoles Libretro,
ARMSX2, RPCS3 et Dolphin iOS. Aucune nouvelle IPA n'a été générée ou publiée
pour ce chantier. Les résultats Apple doivent être complétés après le
passage de la CI ciblée ; les vérifications Linux ne les remplacent pas.

## Résultat proposé dans l'application

Le même catalogue NeoStation est accessible depuis les menus Cheats des quatre
familles de moteurs. Une action **Télécharger tous les catalogues** installe
tous les packs importables en une opération, avec progression globale, taille
annoncée et reprise des téléchargements manquants. Les packs déjà vérifiés sont
conservés lorsqu'une autre source échoue. L'opération suivante permet de mettre
à jour ou de réessayer les éléments absents. Après téléchargement, l'index et
les codes vérifiés sont consultables hors ligne.

Le téléchargement n'active aucun code. L'utilisateur choisit un jeu ou une
édition, puis un programme ; ses dépendances complètes sont importées avec lui.
Le menu natif du moteur sert ensuite à activer ou désactiver ce programme.
Une variante régionale explicitement incompatible n'est jamais remplacée par
la version USA ou une autre langue. Une correspondance incertaine exige une
confirmation de l'édition.

Le service partagé conserve les données et leur provenance. Les adaptateurs
des moteurs valident les formats et écrivent leurs fichiers natifs. Ces deux
responsabilités sont distinctes : un code peut être présent dans le catalogue
sans être activable par le cœur actuellement sélectionné.

Le 18 octobre, le mainteneur a précisé de retirer les catalogues indisponibles
ou incompatibles, puis de tenter leur adaptation avant d'écarter les formats
incompatibles. Le téléchargement actif est donc filtré sur le contenu
exploitable par les moteurs actuels ; les parties valides des sources partielles
sont conservées. L'inventaire historique de recherche et les exclusions restent
séparés de cette publication active. Les données sont figées à la révision
`bf10b1c3314e951c810a2e786c67a10bc388fe34530badb45ebfe3565881bcb4` :
34 attributions de sources figurent dans le manifeste, dont ArtemisPS3 comme
provenance seule de programmes RPCS3 existants. L'inventaire complet est dans
[Sources de cheats NeoStation](unified-cheats-sources.md).

## Adaptations avant exclusion

La vérification ne se limite pas aux extensions de fichiers. Les travaux
supplémentaires portent sur les INI natifs FBNeo et leurs options de session,
la possibilité de conversion PS2 RAW vers PNACH et son blocage sur l'identité
des éditions, les lectures ROM MiSTer NES comparables au mécanisme de patch
du cœur, les écritures RAM MiSTer PS1/GBA, les blocs Action Replay chiffrés
Dolphin vérifiés par son décodeur, les limites réelles DeSmuME/PS1 et les voies
PicoDrive/PCE Fast/WonderSwan. Les programmes retenus dans les packs sont ceux
qui passent les contraintes de format, de dépendances et d'adaptation ; les
autres restent des diagnostics d'audit.

Pour PS3, un rapprochement strict associe les programmes Artemis NCL aux
patchs YAML existants seulement lorsque le serial, la version explicite, le
PPU, le nom et toutes les écritures ordonnées correspondent. Une seconde
provenance ne crée pas un programme unique supplémentaire. Les adresses YAML
sont conservées sous la forme hexadécimale attendue par le véritable parseur.

L'audit ciblé des familles GB/GBC/GBA/N64/SNES/Mega Drive a trouvé 892 entrées
handler 1, toutes dans SNES et Mega Drive : ce sont des observateurs mémoire
de vibrations avec un type de cheat désactivé, sans écriture de triche à
transposer. Ce nombre ne couvre pas tous les handlers mémoire des autres
familles. Une conversion arbitraire en GameShark ou PAR changerait leur sens.
Les autres exclusions indiquent elles aussi l'essai effectué et le blocage
concret dans l'audit final.

La liste exacte des drivers du binaire FBNeo livré a également été comparée
aux INI : 107 romsets absents et leurs 1 344 programmes sont retirés ;
59 087 programmes restent publiés dans cette source. Aucun alias de driver
n'est inventé à partir du titre ou du nom d'un parent.

## Les 70 références et les 14 compléments

`tools/cheats/unified-sources.json` contient les 70 références de la recherche.
Ce nombre est celui des sources ou pistes, pas celui des publications
indépendantes intégralement aspirées. Le champ `import_scope` de chaque source
précise son apport réel : publication complète épinglée, extrait de programmes
complets vérifiés, publication historique, ou référence conditionnelle sans
programme importable. Les reprises d'une même collection conservent leur
provenance ; elles ne deviennent pas automatiquement des codes supplémentaires.

Les 14 compléments documentés, ajoutés aux 52 références initiales, sont :

| Référence | Complément | Portée déclarée dans l'inventaire |
|---:|---|---|
| 53 | Mighty Mo's Cheat Code Pack | Publication machine complète épinglée ; XML/CHT représentent la même famille de données. |
| 54 | dillonhafer OpenEmu XML | Publication XML complète épinglée. |
| 55 | FF7.fr | Extraits de programmes complets pour Final Fantasy VII français ; le site entier n'est pas déclaré importé. |
| 56 | Ethereal Games | Extraits complets vérifiés, avec distinction des éditions lorsque la source l'indique. |
| 57 | PSX Data Center | Extraits Action Replay associés à une édition ou un serial. |
| 58 | Contributions Pokébip | Programmes français vérifiés ; pas d'aspiration exhaustive de la communauté. |
| 59 | Square Palace | Complément spécialisé Secret of Mana ; région non inventée. |
| 60 | Weed Sheet | Publication Sly Cooper épinglée, avec PNACH et documentation. |
| 61 | XoEVOoX FireRed | Extraits complets ; une adaptation française ne se déduit pas de codes USA/Japon. |
| 62 | The Shiny Pokémon Code Repository | Programmes spécialisés ; contraintes de moteur et longueur conservées. |
| 63 | Cemu Community Graphic Packs | Publication épinglée ; les instructions Wii U requièrent leur moteur propre. |
| 64 | Kodewerx | Extraits d'auteurs ; mastercodes et routines restent des programmes complets. |
| 65 | r/Gameshark — îles événementielles d'Émeraude | Complément ciblé ; dialectes et éditions réellement documentés seulement. |
| 66 | Tableur référencé par DeltaCore | Classeur complet ; cellules ambiguës mises en réserve sans réparation numérique supposée. |

Les références 67 à 70 — ShadeTrees, KH-Vids, StrategyWiki et Zelda Central —
restent des pistes conditionnelles tant que leurs données ne sont pas
récupérées et interprétées avec une preuve suffisante. Les autres références
conditionnelles de l'inventaire initial suivent le même principe. Une fiche de
source ne crée pas de faux programme téléchargeable.

## Identification du jeu

Le contrat commun est `{system, title, regions, languages, revision,
identities:[{type,value,scheme}]}`. Le titre sert à proposer une recherche, jamais
à affirmer seul une correspondance exacte. Les empreintes ne sont comparées
qu'avec le même type et le même schéma : le CRC d'un en-tête R4, le CRC d'une ROM
complète et le CRC exécutable PCSX2 ne désignent pas les mêmes octets.

| Moteur | Identité utilisée | Conditions d'import |
|---|---|---|
| Libretro | Empreinte du contenu, schéma explicite et identifiants natifs disponibles. DS : GameCode + CRC R4 de l'en-tête. PS1 : serial/édition ou empreinte pertinente. | Nom seul = candidat. Archives et conteneurs ne sont pas confondus avec leur contenu. Le cœur sélectionné doit accepter le programme entier. |
| ARMSX2 | `ps2_crc / pcsx2-executable-crc` issu du moteur, avec serial courant et refus d'un serial source contradictoire. | Le CRC est relu avant l'import ; il ne provient pas d'un CRC calculé arbitrairement sur l'ISO. |
| Dolphin | `game_id / dolphin-disc-game-id` et révision du disque. | GameID identique mais révision source inconnue = candidat confirmé ; une révision explicitement différente est refusée. |
| RPCS3 | Serial et APP_VER réels énumérés avant le boot ; PPU déclaré par la source. | Tant que le PPU courant n'est pas exposé par le bridge, l'édition reste un candidat confirmé. Le vrai patch engine vérifie ensuite le PPU, le serial et la version lors du boot. |

Le schéma DS conserve l'inversion et la portée exacte du CRC R4. Les ROM NES à
en-tête, les ordres d'octets N64 et les identifiants PSP/3DS sont traités par les
adaptateurs d'identité ; la langue de l'interface n'est pas utilisée comme
preuve de la langue du jeu. Le complément d'identité Pokémon Rouge français
est documenté dans `tools/cheats/unified_pokered_fr_identity.py`.

Pour chacune des empreintes SHA1 originales Rouge et Bleu FR, la publication
contient cinq programmes : quatre programmes Pokémon France nouvellement
attestés pour ces éditions, plus un programme Libretro déjà existant. Ce sont
cinq programmes par édition, pas cinq nouveautés. Une ROM modifiée ou une
autre révision ne reçoit pas une correspondance exacte par son titre seul.

Les MD5 des XML OpenEmu dont le domaine n'est pas attesté restent dans le
schéma `openemu-md5-unspecified` : ils ne sont pas rebaptisés empreintes de
ROM complète. Ces fiches restent des candidats à confirmer ; les
contradictions explicites d'identité, de région ou de révision restent bloquées.

## Formats et activation des quatre moteurs

### Libretro

L'adaptateur est explicitement borné par cœur dans
`LibretroCheats.supportedCoreIDs` et `codesForCheat`. La présence du symbole
obligatoire `retro_cheat_set` n'établit pas à elle seule une implémentation
fonctionnelle : le cœur Azahar examiné possède notamment un chemin de cheats
sans effet. Aucun support 3DS n'est déclaré sur cette seule base.

Le lot comprend 14 profils ABI explicites : Nestopia, Snes9x, Gambatte,
mGBA, Genesis Plus GX, Genesis Plus GX Wide, DeSmuME, Beetle PSX HW,
Beetle PSX, PPSSPP, Mupen64Plus Next, PicoDrive, Beetle PCE Fast et
Beetle WonderSwan. FBNeo utilise une quinzième voie distincte, son import
INI natif désactivé ; il n'est pas présenté comme un callback ABI fonctionnel.
Cela ne constitue pas un support cheats des 34 cores livrés. Les variantes
de console et les opcodes réellement pris en charge sont indiqués dans
[la matrice de compatibilité](unified-cheats-compatibility.md).

Les limites sont celles des vrais buffers et des adaptateurs revus : notamment
DeSmuME 1 023 octets pour un programme, mGBA 128 lignes / 4 096 octets,
PPSSPP 4 096 octets, Mupen64Plus Next 128 paires / 1 791 octets, et les autres
limites explicites du code. Un programme trop long est rejeté en entier, jamais
tronqué pour le faire passer. Les dépendances doivent tenir ensemble dans les
limites du cœur.

Le programme complet est prévalidé avant tout regroupement d'appels. Les
écritures indépendantes PS1 ou PCE peuvent être réparties en appels bornés
lorsque l'append et l'ordre des écritures ont été démontrés ; le choix reste un
seul interrupteur. Les programmes PS1 conditionnels restent atomiques à
255 octets. PCE est borné à 8 192 octets au total et 255 octets par appel ;
WonderSwan à 128 écritures RAM / 1 023 octets dans un seul appel. PicoDrive
conserve sa limite de 8 192 octets et de 99 appels. Les groupes de dépendances
doivent eux aussi respecter ces bornes, sans tronquer une instruction ou une
routine pour tenir dans un tampon.

### ARMSX2

Le navigateur commun ne propose à l'import que le PNACH compris par le parseur
natif. Les programmes et leurs dépendances forment un seul groupe activable.
`NeoPnachImport` écrit un fichier CRC-spécifique et des noms de groupes uniques
qui ne peuvent pas hériter d'une ancienne sélection active. Le pont recharge
les cheats avec `reload_cheats`. Seule l'action explicite de l'utilisateur
appelle ensuite `set_patch_state` ou le réglage maître existant.

Les paramètres Hardcore existants restent respectés. Les programmes RAW
CheatDevice et les formats chiffrés non convertis ne deviennent pas des PNACH
par changement d'extension.

### Dolphin iOS

Gecko et Action Replay sont interprétés avec leur vrai dialecte. Une fermeture
de dépendances mêlant des dialectes ou modes de chiffrement incompatibles est
refusée ; elle n'est pas répartie en interrupteurs incomplets.
`NeoDolphinImport` préserve les réglages INI existants et place les nouveaux
programmes dans les listes `_Disabled`. Le snapshot natif relit les listes du
jeu. L'activation utilise les primitives Dolphin déjà présentes, avec le
contrôle Hardcore.

Le bouton de catalogue du menu ouvre désormais le navigateur commun. Les
anciens fournisseurs natifs sont conservés pour les autres chemins existants ;
leur présence ne constitue pas un second téléchargement requis dans ce flux.

### RPCS3

Les quatre exports nécessaires existent déjà dans le Core ABI 30 épinglé :

- `rpcs3_ios_install_patch_repository` : vérifie SHA-256, version 1.2 et contenu
  avec le véritable parseur YAML du Core ; installation atomique de `patch.yml`.
- `rpcs3_ios_enumerate_runtime_patches` : expose les métadonnées, sans renvoyer
  les lignes des programmes.
- `rpcs3_ios_set_runtime_patch_enabled` : persiste la configuration ; effet au
  prochain lancement, uniquement lorsque l'émulation est arrêtée.
- `rpcs3_ios_enumerate_games` : fournit notamment le serial et l'APP_VER installés.

Ils sont résolus avec `dlsym` comme extensions facultatives ; la structure de
l'API principale et l'ABI 30 ne changent pas. Aucun nouveau Core RPCS3 n'est
requis par cette intégration.

Le programme source contient `native_document`, un document YAML autonome
préalablement parsé lors de la génération. Le pont le sérialise en JSON, qui est
du YAML valide, puis le fait contrôler par le Core. Il ne réécrit pas du YAML
avec des substitutions textuelles et ne rebaptise aucun NCL Artemis en YAML.
Une portée de version `All` explicitement publiée peut être restreinte à
l'APP_VER réellement installée, après confirmation du candidat ; le PPU reste
obligatoire. Les paramètres configurables non résolus restent exclus.

Pendant une partie, l'import écrit une sélection désactivée dans
`NeoStationUnifiedCheats/state.json`. Les interrupteurs représentent les choix
pour le prochain lancement, pas une écriture immédiate dans la RAM. Après
l'arrêt ou avant le boot suivant, le pont valide les programmes et publie le
fichier `<serial>_patch.yml`, que le boot charge effectivement. Les noms uniques
empêchent l'héritage d'une ancienne activation ; les groupes exclusifs sont
conservés.

Le validateur existant écrit temporairement `patch.yml`. Un journal récupérable
sauvegarde puis restaure exactement `patch.yml` et `patch.yml.old` avant la
publication du fichier propre au jeu. Un fichier `<serial>_patch.yml` personnel,
inconnu ou modifié n'est pas remplacé : son conflit est affiché. Les autres jeux
restent utilisables. Une fusion arbitraire de YAML personnel n'est pas affirmée,
car les exports existants ne renvoient pas ses instructions.

Un catalogue invalide, un conflit ou une API facultative absente ne bloque pas
le lancement normal lorsque les fichiers globaux sont restaurés. Le menu
signale alors l'échec de préparation. Seule une restauration matérielle
incomplète de la transaction interdit le boot jusqu'à récupération ; ce cas
est distingué par `bootSafe`.

## Doublons, variantes et provenance

Les programmes sont normalisés et comparés avec leur identité de jeu, dialecte,
ordre des lignes et dépendances. Deux variantes régionales ne sont pas fusionnées
par ressemblance de titre. Les paramètres non résolus et les valeurs de cellules
ambiguës restent marqués, sans correction inventée.

Pour les imports natifs, deux corps différents portant le même nom reçoivent
des variantes lisibles `(2)`, `(3)`, etc. Un corps déjà importé est retrouvé avec
son nom existant, y compris lorsqu'un ordinal précédent a été supprimé ; il
n'est pas activé de nouveau. Le nom d'origine, les identifiants, les auteurs,
les URL et les licences restent dans le catalogue et les reçus structurés.
Les dépendances d'un choix sont réunies dans un seul interrupteur natif.

## Téléchargement et reproductibilité

Le générateur est `tools/cheats/unified_catalogue.py`, avec les adaptateurs de
`unified_formats.py`, les compléments vérifiés de `unified_curated.py`, et les
réserves explicitement séparées. Les URL, révisions, SHA-256, licences et
`import_scope` sont dans `unified-sources.json`. Les fichiers de publication
sont `native/cheats/catalogue/manifest.json.gz` et les packs gzip référencés.

Le consommateur partagé est `packages/neo_cheat_catalog`. Il vérifie tailles et
SHA-256 des packs puis des chunks de jeu avant écriture atomique. Les plafonds
actuels sont 12 Mio compressés / 64 Mio décompressés pour l'index, 8 Mio compressés / 16 Mio décompressés par pack
et 2 Mio par chunk. Un grand jeu est réparti en parties complètes ; une routine
n'est pas coupée au milieu. L'installation est bornée en concurrence, les
échecs restent isolés et la recherche ne charge pas tous les codes en mémoire.

Exemples de publications épinglées, sans remplacer le fichier de lock complet :

| Publication | Révision |
|---|---|
| Libretro Database | `12c21cf79f1e20eff6ac68b80875816c717d0a7a` |
| DuckStation chtdb | `8b2f1dd257ab9130d16b72e0caeb5a07af8bcbdc` |
| Collection PNACH | `6cb57b55939f47dd91a157bfb6cdc7fd157a780c` |
| Dolphin GameSettings | `38d619b07691231f54e6f037fcf30a3b64fdd5a5` |
| Artemis RPCS3 | `21fc0ee86578f1452e42da01187eb852ab034b28` |

Pour régénérer puis vérifier :

```sh
python3 tools/cheats/unified_catalogue.py build --sources tools/cheats/unified-sources.json --output native/cheats/catalogue --cache /chemin/cache
python3 tools/cheats/unified_catalogue.py validate --input native/cheats/catalogue
```

## Métriques et validation

Données figées à la révision
`bf10b1c3314e951c810a2e786c67a10bc388fe34530badb45ebfe3565881bcb4`.
Le manifeste et son exemplaire embarqué sont identiques. L'index référence
34 attributions de sources, dont ArtemisPS3 comme provenance seule,
2 341 355 programmes dédupliqués dans leurs groupes d'identité,
43 813 groupes et 44 955 fiches de transport, parties comprises.
Ces comptes ne sont ni un nombre d'effets uniques ni un nombre de jeux
commerciaux uniques. Les contributions des sources se recouvrent et ne
s'additionnent pas. `totals.cheats` compte 2 341 355 enregistrements de
programmes dans les packs, duplications éventuelles de dépendances comprises.

| Élément figé | Taille ou quantité |
|---|---:|
| Index gzip embarqué et distant | 6 574 067 octets (6,27 Mio) |
| Index JSON décompressé | 29 376 532 octets (28,02 Mio) |
| Packs référencés | 851 |
| Packs compressés, somme | 274 318 367 octets (261,61 Mio) |
| Réseau initial, index + packs | 280 892 434 octets (267,88 Mio) |
| Packs décompressés, somme des enveloppes temporaires | 3 226 101 652 octets (3076,65 Mio) |
| Chunks de jeux installables, hors index et métadonnées locales | 2 417 589 667 octets (2305,59 Mio) |

Les tailles décompressées sont des sommes sur le catalogue ; les packs sont
traités dans les limites de concurrence et de mémoire du service partagé.
L'IPA embarque l'index, pas les 851 packs.

SHA256 de `manifest.json.gz` :
`cf8959bfd6b20b4ef2516e1e235723b1a5048b2fc2c98033d05ad0d48cf84e57`.
Le scan indépendant de `native/cheats/catalogue/VALIDATION.json` a parcouru les
851 packs et les 2 341 355 programmes sans anomalie réelle. Ce
contrôle de données reste distinct des résultats Apple ci-dessous et ne
constitue pas une vérification gameplay de chaque programme. L'inventaire des
70 références, leurs contributions et les 14 compléments 53–66 est dans
[la liste des sources](unified-cheats-sources.md).

La CI ciblée est `.github/workflows/unified-cheats.yml`. Les nouveaux contrôles
incluent les adaptateurs de données, la persistance/hors-ligne du service,
l'identité régionale, le navigateur UIKit, le véritable SDK iPhone des menus et
plugins, et les tests de stockage natif avec transport Core simulé. Les sondes
PPSSPP/N64 vérifient séparément leurs effets RAM avec les cœurs existants.

Résultats déjà obtenus dans le conteneur de cette session :

- `test/unified_native_ios_test.py` : programmes natifs C++ complets, ordre des
  lignes et rejet des placeholders/dialectes incorrects — réussite Linux.
  Compilation Apple et exécution Foundation explicitement ignorées sur Linux.
- `test/unified_native_exports_test.py` : réussite sur le vrai binaire RPCS3
  téléchargé de l'artefact `11717558908`, run `38178247609`. ZIP SHA-256
  `7e435c21b61d905c5aeabd90dae8449f420fcc2e3f8d915d6303dc604dece48a` ; Core
  de 75 407 672 octets, SHA-256
  `19718c30d3055dea049c5807e7ce0d5c7663fab4968362d2426562e9f85ba93d`.
  Les quatre symboles sont des exports externes définis lus dans `LC_SYMTAB`,
  pas de simples chaînes trouvées dans le fichier. Preuve réexécutable et
  identité détaillée : `test/unified_native_rpcs3_exports.json`.

**Validation Apple encore à renseigner :** SHA exact, run, jobs, résultats SDK,
Foundation, UIKit et effets des sondes. Les tests avec transport simulé ne
prouvent pas un effet dans un jeu commercial PS2, GameCube/Wii ou PS3.
Les résultats historiques des skins, de NeoSwap et des composants inchangés
sont réutilisés conformément à `AGENTS.md` ; ils ne sont pas présentés comme
réexécutés pour ce catalogue.

## Limites conservées

- Les 70 références ne signifient pas 70 sources intégralement récupérées ni
  70 bases de données indépendantes. `import_scope` reste l'autorité par source.
- Le miroir DS historique ne devient pas la publication courante de l'auteur.
- L'absence d'un PPU courant ou d'une révision source exacte n'est pas masquée
  par un faux résultat exact ; les candidats demandent confirmation.
- Les formats réservés à des plugins de console réelle, les NCL non convertis,
  les programmes dépassant les limites et les paramètres non résolus restent
  indisponibles pour l'activation tant qu'un adaptateur réel ne les couvre pas.
- Le support futur Switch, Vita, Wii U ou MAME XML ne découle pas de la présence
  de leurs données dans l'inventaire. La voie arcade FBNeo INI déjà raccordée
  n'est pas un interpréteur universel des autres formats arcade.
- Aucun test sur iPhone physique, aucune IPA de ce chantier et aucune
  publication publique ne sont affirmés ici.

## Contrôles intermédiaires et réutilisation

| Révision | Résultat acquis | Échec conservé dans l’historique |
|---|---|---|
| `2dec00b8` | Premier raccordement de code, sans données publiées ni IPA. | Le compilateur Apple a révélé une collision entre le validateur `Size` et le type système homonyme. |
| `b60d1af2` | Le package compile avec le vrai SDK iPhone. Les cinq contrôles mémoire PPSSPP passent avec le vrai cœur. | La fixture Foundation révèle le refus du lien système `/var` ; le scénario N64 demande un contexte OpenGL indisponible. Le workflow global échoue. |
| `095ca745` | SDK iPhone, comportement Foundation, identités et compilation du bridge Libretro réussissent. | Le callback RPCS3 a une signature de nullabilité incompatible ; les tests UIKit ont une erreur de macro et ne s’exécutent pas. Ces deux défauts sont corrigés dans le lot suivant. |

La preuve PPSSPP est consignée dans
`docs/evidence/unified-cheats-psp.json`, avec révision, empreintes du cœur,
fixture et rapport, et identifiant de l’artefact. Elle reste une preuve de cette révision. Le nouveau garde agrégé
de l’hôte touche aussi PSP : le prochain essai revérifie donc PSP et N64,
avec les options logicielles N64 de la sonde, et les fonctions natives FBNeo
du binaire livré. Aucun moteur produit n’est changé pour contourner une limite du
Simulateur. Les contrôles du manifeste final sont distincts : aucune absence
de données dans le commit de code ne vaut validation du catalogue complet.
