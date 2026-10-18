# Bilan final des adaptations de catalogues NeoStation

État documentaire au 18 octobre 2026. Ce bilan décrit les essais de compatibilité, leurs résultats et les exclusions factuelles. Il ne modifie ni le verrou des sources ni le catalogue actif.

**70 références constituent un inventaire de recherche. Cela ne signifie pas que 70 sites ou portails ont été aspirés intégralement.** Les archives structurées épinglées ont une portée déclarée ; les sites et forums retenus ne fournissent que les extraits complets explicitement sélectionnés. L’entrée directe GameHacking.org apporte **un seul extrait** ; la distribution MiSTer issue de GameHacking n’est pas un crawl exhaustif du portail.

Les nombres des audits sont des programmes sources avant fusion/déduplication. Ils ne s’additionnent pas au total publié. Les décomptes du manifeste et de SOURCES.md générés par le builder font autorité pour le pack final. Un programme admissible signifie une syntaxe et une voie d’activation revues, pas une efficacité de jeu vérifiée sur chaque ROM. Aucun téléchargement n’active un cheat automatiquement.

## Tableau actif / exclu / motif

| Famille ou essai | Décision | Résultat quantifié | Motif ou borne factuelle |
|---|---|---|---|
| MiSTer NES | Actif dans le profil | 27 283 programmes sources | Adresse CPU ROM 8000..FFFF, read-override et comparateur préservés ; pas de conversion RAM en écriture périodique. |
| MiSTer PSX | Actif dans le profil | 381 392 programmes sources | RAM 2 MiB, masques10/20/30, branches EQ/GT/NE immédiates ; contrôle compact entier<=255 ; writes30/80 seuls<=8192 et lots ordonnés. |
| MiSTer GBA | Actif dans le profil | 148 072 programmes sources | Writer RAM réel à vblank, EWRAM/IWRAM physiques, masques byte développés dans l’ordre vers gba-vba-raw ; pas de crypto ni IO/ROM convertis. |
| FBNeo INI | Actif dans le profil | 59 087 programmes publiés après déduplication et filtre des pilotes | Canal fichiers/options natifs associé au driver ; callbacks Libretro eux-mêmes sans effet. Les choix restent complets, import off. |
| GBA AUTO Delta | Actif et isolé | 873 programmes acceptés par le vrai décodeur sur 948 examinés | `mgba_auto_isolated:true` ; état crypto partagé : aucun mélange libre avec un autre record GBA non VBA. Pas 873 effets uniques testés. |
| GBA AUTO XoEVOoX / EventIslands | Actif et isolé, sous-ensemble | 6 XoEVOoX ; 1 EventIslands | Masters USA/Japon conservés ; 4 variantes EventIslands paramétrées exclues. Le programme EventIslands seul ne prouve pas l’effet des téléporteurs. |
| Tyler Shiny VBA | Actif dans le profil | 1 programme complet de 49 patches ROM | Syntaxe à deux-points, vraie entrée mGBA, aucune conversion GS/AR ni coupure. |
| PCE / PC Engine-CD, source Libretro | Actif dans le profil RAW | 1 452 programmes sur 1 454 ; 387 jeux candidats | RAW6hex:2hex dans RAM attestée ; entrée<=8192 caractères, appels<=255 ; alias démontré seulement. Deux adresses malformées1f0000f:0c exclues sans réparation. |
| WonderSwan, source Libretro | Actif dans le profil RAM | 1 programme sur 32 examinés | Makaimura : 001E24:09 devient1E24:09, même valeur numérique en RAM principale. Les 31 programmes ROM/Genie/paramètres restent exclus ; plafond 128 écritures/1023 caractères en un appel. |
| PicoDrive 32X, source Libretro | Actif dans le profil | 523 programmes sur 658 | MD Game Genie/RAW mots pairs, ROM/bus principal 68000 ; 121 adresses impaires, 12 vides/paramétrés et 2 sentinelles FFFF exclus. Aucun mapping SH2 ; entrée<=8192 caractères, sans quota artificiel de 1024 patches. |
| Dolphin AR chiffré | Actif,4 blocs déchiffrés réellement | GTEP01 :4 programmes entiers | Vraie fonction Dolphin, parité et CRC vérifiés ; dialecte Action Replay conservé, conditions intactes. |
| Artemis NCL vers RPCS3 | Provenance rattachée ; NCL direct exclu | 1 083 blocs associés à 713 documents existants ; 0 nouveau programme unique | Nom, serial, APP_VER et écritures complètes reliés à un PPU publié par l’auteur. Le reste NCL demande son interpréteur mémoire. |
| CheatDevice PS2 | Exclu du pack actif | 131 174 conversions techniques ; 0 édition sûre | 1 483 titres sans serial ni région attestée. Le test GameIndex : 1 035 titres égaux, 806 multiserials, 229 uniques sans région ; 0 association éligible. |
| RetroArch handler=1 | Exclu comme write gameplay | 892 entrées :715 SNES +177 MD | Toutes `cheat_type=0`,`CHEAT_TYPE_DISABLED` : observateurs de mémoire et vibration. Les convertir en PAR inventerait une écriture. |
| Pugsy MAME XML/JSON | Exclu du pack actif | 277 370 programmes XML +155 JSON natifs examinés | Cycle on/off/run/change, Lua, expressions et espaces device requièrent le vrai interpréteur. 155 JSON sont réels, dont 153 diagnostics ; pas du GameShark. |
| Azahar 3DS | Exclu du pack actif | Sharkive et CTRPF lus, aucun chemin exécutant raccordé | Callbacks retro_cheat_set/reset du binaire examiné sans effet. API internes présentes mais pas d’accès hôte sûr au moteur actif ; un parseur ne suffit pas. |
| MAME2003 Plus / Flycast | Exclu du pack actif | Absents des 34 cœurs livrés examinés | Pas de conversion de leurs adresses, conditions et répétitions vers le moteur d’une autre console. |
| Switch / Vita / Wii U Cemu | Exclu du pack actif | Publications conservées dans l’inventaire | Interpréteur/console correspondant absent du périmètre ; TitleID/BuildID ou rules/module PowerPC ne sont pas des codes RetroArch/PS2/PS3. |

## Les 14 familles présentes dans MiSTer

Les 14 familles ci-dessous sont des systèmes de la publication MiSTer. Elles sont distinctes des 14 compléments de sources numérotés53 à 66 dans l’inventaire. L’archive contient14 826 ZIP,1 041 648 programmes et1 568 371 tuples. Les trois sous-ensembles NES / PSX / GBA ci-dessous totalisent **556 747 programmes admissibles avant déduplication**.

| Famille MiSTer | ZIP | Programmes natifs | Admissibles dans cette adaptation | Exclus / raison |
|---|---:|---:|---:|---|
| AtariLynx | 24 | 112 | 0 | 112 exclus :pas d’adaptateur natif Lynx raccordé. |
| GBA | 1 450 | 170 631 | 148 072 | 2 009 paramètres d’export non attestés ; 20 550 hors profil |
| GameBoy | 1 457 | 41 343 | 0 | 41 343 exclus :équivalence du read-override, du comparateur et des banques ROM non établie pour ce format binaire. |
| Jaguar | 7 | 26 | 0 | 26 exclus :pas d’adaptateur natif Jaguar raccordé. |
| MegaCD | 35 | 284 | 0 | 284 exclus :read-override et banque de programme MegaCD non assimilables à une écriture PAR 68000. |
| MegaDrive | 1 746 | 40 657 | 0 | 40 657 exclus :mapping cartouche/lecture conditionnelle non démontré vers les codes natifs. |
| N64 | 814 | 217 971 | 0 | 217 971 exclus :opérations, masques d’octets et endian ne sont pas des opcodes GameShark. |
| NES | 1 996 | 46 272 | 27 283 | 369 paramètres d’export non attestés ; 18 620 hors profil |
| PSX | 4 542 | 452 234 | 381 392 | 63 756 paramètres d’export non attestés ; 7 086 hors profil |
| SMS | 859 | 9 131 | 0 | 9 131 exclus :lecture dans une banque contre écriture Action Replay ; équivalence non démontrée. |
| SNES | 1 448 | 60 660 | 0 | 60 660 exclus :read-override matériel contre write RAM périodique ; mapping ROM/comparateur non démontré. |
| TGFX16-CD | 153 | 844 | 0 | 844 exclus :même distinction entre tuples MiSTer et nouveau profil RAW PCE-CD ; espace et comparaison non attestés. |
| TGFX16 | 283 | 1 455 | 0 | 1 455 exclus :le nouveau profil RAW PCE Libretro ne démontre pas la correspondance bus/adresses des tuples MiSTer. |
| VirtualBoy | 12 | 28 | 0 | 28 exclus :pas d’adaptateur natif VirtualBoy raccordé. |

Le mot«Modifier» sans sélection attestée reste un paramètre d’export inconnu. Ce motif n’est pas une absence de moteur. Le programme natif complet reste traçable ; aucune valeur d’option n’a été devinée. Les autres exclusions gardent aussi toutes leurs instructions :pas de réduction à la seule partie convertible.

### Preuves de sémantique et de borne

- NES :RTL MiSTer49a0a662 distingue adresse CPU et adresse physique PRG ; le comparateur agit après le mapper. Nestopia135dfa6d accepte exactementAAAA?CC:VV ; exemple réelBoogerman II:C446?C6:A5. Flags0/1, ROM8000..FFFF, octets et adresses distinctes seulement.
- PSX :RTL cd17b5a0 distingue opération et byte-enable ; le canal SDRAM3 utilise addr[25:1]. Exemple A-TrainZ:mask20, base80092ED8, valeurFF00→30092ED9 00FF. Seules branchesEQ1, GT2, NE6 suivies d’une unique write sont converties ; deux conditions consécutives ont une sémantique différente. Operations3/4/5 exclues car noms et inégalités du RTL divergent.
- PSX :contrôleD/E/50 compact12hex+<=255 caractères,19 instructions admises, un seul appel ; écritures30/80 seules en entrée paire+<=8192 caractères, segments contigus ordonnés dans le runtime. Les 20 instructions contrôlées et les 586 writes dépassant la borne restent entières et non actives.
- GBA :RTL93790a02 fait un RMW RAM à vblank avec CPU bloqué. Les masques1..15 deviennent des bytes little-endian dans l’ordre, avec<=128 lignes/4096 caractères. La vraie boucle mGBA7a12d6d et son parseur VBA ont validé bytes/shorts/words après seedCodeBreaker ; le padding de 2espaces des bytes se fait à l’appel natif, pas dans le catalogue.
- PCE/WS :les parseurs primaires et writers périodiques ont été comparés au contrat des binaires livrés. Pour PCE, la correspondance au commit source est une corrélation contrôlée, pas un hash Git embarqué dans le binaire. La canonisation WS retire seulement des zéros sans changer l’adresse numérique.
- PicoDrive :source1890c293 et vrai callback, writer et reset testés ; 523/65832X admissibles. Les plafonds natifs de 255 octets/appel et 99 appels agrégés sont respectés ; le dernier patch et la restauration au reset sont vérifiés.

## Les 14 compléments de sources53 à 66

| N° | Source | Décision | Contenu effectivement retenu ou motif |
|---:|---|---|---|
| 53 | [Mighty Mo's Cheat Code Pack](https://github.com/mightymo77/MightyMos-Cheat-Code-Pack) | Actif, publication XML structurée | MightyMo :programmes multiparts regroupés dans leur ordre numérique ; encodages alternatifs non comptés comme plusieurs effets. |
| 54 | [dillonhafer OpenEmu cheats-database.xml](https://gist.github.com/dillonhafer/8399eb1926e2af9164470ad45da67a57) | Actif, publication XML structurée | Source OpenEmu complète ; 9 programmes Sonic Mega Drive récupérés grâce à l’alias officiel openemu.system.sg=Genesis, attesté par OpenEmu-Update/oecores-experimental.xml. Les 16 entrées AR4-4 GG/SMS ne sont pas comptées dans cet apport. |
| 55 | [FF7.fr — codes Action Replay français](https://www.ff7.fr/action_replay.php) | Actif,8 extraits | FF7France disque1 SCES-00868 ; 8 programmes30/80 complets, disc/hash explicitement sourcés ; aucune identité étendue aux autres disques. |
| 56 | [Ethereal Games](https://etherealgames.com/) | Actif,2 extraits | McDonaldland (Europe),2 codesGB complets ; candidat de titre/édition avec confirmation, aucun hash inventé. |
| 57 | [PSX Data Center — rubriques Action Replay](https://www.psxdatacenter.com/) | Actif,2 extraits | Digimon World (Japon) SLPS-01797 ; HP et argent en programmes complets. |
| 58 | [Pokébip — contributions Action Replay](https://www.pokebip.com/espace-membre/blogs/129214/article/84411) | Actif,3 extraits | Platine (France) CPUF+D8380D9F conjoints ; seulement la première sectionFR ; aucun héritage sur les sections japonaises ultérieures. |
| 59 | [Square Palace — codes Secret of Mana](https://squarepalace.com/encyclopedies/secretofmana/cheat-codes-action-replay) | Actif, 8 candidats à confirmer | Huit programmes SNES PAR complets, sans paramètre ni dépendance manquante. Région, langue et hash restent non renseignés ; confirmation manuelle de l’édition, sans supposer une ROM française. |
| 60 | [Weed Sheet — Sly Cooper](https://github.com/zzamizz/weed-sheet) | Actif, sous-ensemble PNACH | WeedSheet, SlyCooper :PNACH complets et identités présentes ; programmes non conformes exclus entiers. |
| 61 | [XoEVOoX Pokémon FireRed codes](https://github.com/xoevoox/pokemon-fire-red-codes) | Actif,6 programmes vérifiés | FireRed USA/Japon séparés, masters conservés ; canal AUTO isolé réellement testé ; aucune réparation d’un mot hexadécimal trop long. |
| 62 | [TylerD007 — The Shiny Pokémon Code Repository](https://github.com/TylerD007/The_Shiny_Pokemon_Code_Repository) | Actif,1programme | Shiny Emerald USA :49 patchesROM VBA ; source brute et largeur préservées. |
| 63 | [Cemu Community Graphic Packs — sous-ensembles Cheats](https://github.com/cemu-project/cemu_graphic_packs) | Exclu du pack actif | Cemu :rules/patches PowerPC et TitleIDs/modules sont réels, mais exigent le moteurWii U correspondant. |
| 64 | [Kodewerx — contributions de codes](https://www.kodewerx.org/forum/viewtopic.php?f=18&t=2763&view=print) | Actif,3 extraits | Mario Kart 64 (USA), N64GameShark81 ; les anciens statuts requires_engine obsolètes ont été levés après raccordement réel. |
| 65 | [r/Gameshark — îles événementielles Pokémon Emerald, 12 chiffres](https://www.reddit.com/r/Gameshark/comments/1804kz6/all_the_event_islands_for_pokemon_emerald_have/) | Actif,1programme admissible | EventIslands France :1programme non paramétré passe le décodeur ; 4 variantes/téléporteurs paramétrés exclus. Ne pas présenter1master comme4 effets de jeu validés. |
| 66 | [DeltaCore — tableur public All Cheat Codes](https://github.com/rileytestut/DeltaCore/wiki/Cheats) | Actif, sous-ensemble du tableur complet | Delta :873 programmes acceptés au vrai décodeur AUTO sur 948 ; 75refusés, aucune conversion de cellule numérique/formule ni valeur manquante inventée. Déduplication distincte du comptage d’audit. |

## Inventaire des 70 références et portée réellement acquise

«Actif» ci-dessous signifie que le sous-ensemble autorisé passe par les filtres du builder ; il ne signifie pas que tout le contenu du site est compatible. «Référence exclue» signifie qu’aucune collecte complète et validée n’est revendiquée. Les sources qui ne fournissent que des correspondances de provenance ne deviennent pas des programmes nouveaux.

| N° | Référence | Traitement | Portée ou raison factuelle |
|---:|---|---|---|
| 1 | [Libretro Database](https://github.com/libretro/libretro-database) | Actif, avec filtrage | Publication structurée épinglée acquise (retroarch-cht) ; seuls programmes complets compatibles avec les moteurs/éditions admis. |
| 2 | [GameHacking.org](https://gamehacking.org/) | Actif, avec filtrage | Un seul extrait complet Pokémon Rouge (France) ; portail et forum non aspirés intégralement. |
| 3 | [DeadSkullzJr NDS(i) Cheat Databases](https://gbatemp.net/threads/deadskullzjrs-nds-i-cheat-databases.488711/) | Actif, avec filtrage | Miroir historique vérifié, dernière mise à jour29avril2022 ; pas prétendu édition actuelle2026 de l’auteur. |
| 4 | [FlagBrew Sharkive](https://github.com/FlagBrew/Sharkive) | Exclu après essai | Azahar livré :callbacks cheats sans application réelle ; normaliser la syntaxe ne crée pas le chemin d’exécution. |
| 5 | [iSharingan CTRPF-AR-CHEAT-CODES](https://github.com/iSharingan/CTRPF-AR-CHEAT-CODES) | Exclu après essai | Même blocage Azahar ; pas d’interpréteur CTRPF raccordé au système actif. |
| 6 | [CWCheat Database Plus](https://github.com/Saramagrean/CWCheat-Database-Plus-) | Actif, avec filtrage | Publication structurée épinglée acquise (XML OpenEmu) ; seuls programmes complets compatibles avec les moteurs/éditions admis. |
| 7 | [DuckStation chtdb](https://github.com/duckstation/chtdb) | Actif, avec filtrage | Publication structurée épinglée acquise (duckstation-cht) ; seuls programmes complets compatibles avec les moteurs/éditions admis. |
| 8 | [CheatDevicePS2](https://github.com/root670/CheatDevicePS2) | Exclu après essai | RAW0/1/2 techniquement convertible ; 0 association GameIndex sûre, faute de région/serial de source. |
| 9 | [pcsx2_cheats_collection](https://github.com/xs1l3n7x/pcsx2_cheats_collection) | Actif, avec filtrage | Publication structurée épinglée acquise (pnach) ; seuls programmes complets compatibles avec les moteurs/éditions admis. |
| 10 | [PCSX2 patches](https://github.com/PCSX2/pcsx2_patches) | Référence exclue | Patches graphiques widescreen/no-interlace :référence, pas comptés comme nouveaux cheats gameplay. |
| 11 | [Dolphin GameSettings](https://github.com/dolphin-emu/dolphin/tree/master/Data/Sys/GameSettings) | Actif, avec filtrage | Publication structurée épinglée acquise (dolphin-ini) ; seuls programmes complets compatibles avec les moteurs/éditions admis. |
| 12 | [RiiConnect24 GeckoCodes mirror](https://codes.rc24.xyz/) | Référence exclue | EndpointGC6P01 testé en404 ; pas de catalogue autonome importé depuis cet endpoint. |
| 13 | [GeckoArchive](https://github.com/SpaceXCheeseWheel/GeckoArchive) | Actif, avec filtrage | Publication structurée épinglée acquise (gecko-txt) ; seuls programmes complets compatibles avec les moteurs/éditions admis. |
| 14 | [Pugsy MAME Cheats](https://www.mamecheat.co.uk/) | Exclu après essai | XML/JSON natifs réels, mais cycle/scripts/device-space sans interpréteur compatible raccordé. |
| 15 | [FBNeo cheats](https://github.com/finalburnneo/FBNeo-cheats) | Actif, avec filtrage | Publication structurée épinglée acquise (fbneo-ini) ; seuls programmes complets compatibles avec les moteurs/éditions admis. |
| 16 | [Project64 Cheats](https://github.com/project64/project64/tree/develop/Config/Cheats) | Actif, avec filtrage | Publication structurée épinglée acquise (project64-cht) ; seuls programmes complets compatibles avec les moteurs/éditions admis. |
| 17 | [Mupen64Plus database](https://github.com/mupen64plus/mupen64plus-core/blob/master/data/mupencheat.txt) | Actif, avec filtrage | Publication structurée épinglée acquise (XML OpenEmu) ; seuls programmes complets compatibles avec les moteurs/éditions admis. |
| 18 | [Mesen2 CheatDb](https://github.com/SourMesen/Mesen2/tree/master/UI/Dependencies/Internal) | Actif, avec filtrage | Publication structurée épinglée acquise (mesen-json) ; seuls programmes complets compatibles avec les moteurs/éditions admis. |
| 19 | [Snes9x cheats.bml](https://github.com/snes9xgit/snes9x/blob/master/data/cheats.bml) | Actif, avec filtrage | Publication structurée épinglée acquise (XML OpenEmu) ; seuls programmes complets compatibles avec les moteurs/éditions admis. |
| 20 | [ArtemisPS3](https://github.com/bucanero/ArtemisPS3/tree/master/docs/codes) | Provenance uniquement | NCL direct exclu ; 1083 blocs rattachés à 713 documents RPCS3 déjà existants ; 0 nouveau programme unique. |
| 21 | [Artemis Patch Collection RPCS3](https://github.com/chidreams/Artemis-Patch-Collection-RPCS3) | Actif, avec filtrage | Publication structurée épinglée acquise (rpcs3-yaml) ; seuls programmes complets compatibles avec les moteurs/éditions admis. |
| 22 | [r0ah VitaCheat](https://github.com/r0ah/vitacheat) | Exclu après essai | Publication PSV acquise ; runtime/plugin Vita absent, aucune conversion vers une autreconsole. |
| 23 | [ShumnoT VitaCheatDatabase](https://github.com/ShumnoT/VitaCheatDatabase) | Exclu après essai | Publication PSV acquise ; runtime/plugin Vita absent, aucune conversion vers une autreconsole. |
| 24 | [HamletDuFromage switch-cheats-db](https://github.com/HamletDuFromage/switch-cheats-db) | Exclu après essai | Publication Switch acquise ; exige moteur Switch et contraintesTitleID/BuildID ; pas de conversion inter-console. |
| 25 | [EdiZon CheatsConfigsAndScripts](https://github.com/WerWolv/EdiZon_CheatsConfigsAndScripts) | Exclu après essai | Publication Switch acquise ; exige moteur Switch et contraintesTitleID/BuildID ; pas de conversion inter-console. |
| 26 | [ibnux switch-cheat](https://github.com/ibnux/switch-cheat) | Exclu après essai | Publication Switch acquise ; exige moteur Switch et contraintesTitleID/BuildID ; pas de conversion inter-console. |
| 27 | [GBAtemp Matias3ds / exefer mirror](https://github.com/exefer/gbatemp-matias3ds-cheats) | Exclu après essai | Publication Switch acquise ; exige moteur Switch et contraintesTitleID/BuildID ; pas de conversion inter-console. |
| 28 | [Chansey NX 60FPS RES GFX](https://github.com/ChanseyIsTheBest/NX-60FPS-RES-GFX-Cheats) | Exclu après essai | Publication Switch acquise ; exige moteur Switch et contraintesTitleID/BuildID ; pas de conversion inter-console. |
| 29 | [Pokémon France / PokéLord](https://www.pokemon-france.com/jeux/gen1/bleu_rouge/actionreplay/) | Actif, avec filtrage | Extraits seulement ; 8 programmesRouge/Bleu (France) vérifiés retenus,4autres à région/révision non explicites exclus. |
| 30 | [Pokémon Trash codes](https://www.pokemontrash.com/codes-pokemon) | Référence exclue | Pas d’export complet intégré ; masters/anti-DMA/région non généralisables. |
| 31 | [Project Pokémon RAM cheats](https://projectpokemon.org/home/forums/) | Référence exclue | Pas de catalogue complet intégré ; adaptationsFR/US propres à chaque programme, pas offset universel. |
| 32 | [PokémonCoders](https://www.pokemoncoders.com/all-pokemon-cheats-compilation/) | Référence exclue | Pas de collecte complète validée ; codes de hacks et ROMoriginales non assimilés. |
| 33 | [GameGenie.com](https://gamegenie.com/cheats/) | Référence exclue | Portail mélangeant codes exécutables, astuces et séquences de boutons ; pas de collecte complète intégrée. |
| 34 | [CodeTwink](https://codetwink.com/) | Référence exclue | Pas de publication intégrée avec décodeur/édition attestés ; aucun chiffrementPS2 deviné. |
| 35 | [Datel Codejunkies](https://us.codejunkies.com/search/codes_search.aspx) | Référence exclue | Pas d’export complet acquis et validé dans ce travail. |
| 36 | [PSX Emulation Cheater PEC](https://pec.duttke.de/download.php) | Référence exclue | Base historique annoncée18novembre2002 ; publication autonome complète non intégrée. |
| 37 | [MiSTer Cheats](https://github.com/MiSTer-devel/Cheats_MiSTer) | Actif, avec filtrage | Archive épinglée ; conversion active limitée aux famillesNES / PSX / GBA ; 14 familles auditées, catalogue portail non revendiqué. |
| 38 | [Serebii Red Blue GameShark](https://www.serebii.net/rb/gamesharkrb.shtml) | Référence exclue | Pages et variantes paramétrées non intégrées exhaustivement ; langue du site ne prouve pas la région ROM. |
| 39 | [Glitch City Wiki GameShark](https://glitchcity.wiki/wiki/Pok%C3%A9mon_Red%2C_Blue_and_Yellow_GameShark_codes) | Référence exclue | Référence technique ; pas de publication complète importée ni conversion régionale globale. |
| 40 | [EZ-Flash Omega Cheat Library](https://www.ezflash.cn/download/) | Référence exclue | Bibliothèque/convertisseur distincts repérés ; publication autonome et provenance non établies ici. |
| 41 | [PPSSPP CWCheat forum](https://forums.ppsspp.org/forumdisplay.php?fid=31) | Référence exclue | Forum non collecté intégralement ; recoupement avecCWCheat+ sans nouveau décompte démontré. |
| 42 | [LunaMoo PPSSPP workarounds](https://github.com/LunaMoo/PPSSPP_workarounds) | Actif, avec filtrage | Publication structurée épinglée acquise (cwcheat-db) ; seuls programmes complets compatibles avec les moteurs/éditions admis. |
| 43 | [TAbdiukov PPSSPP patches](https://github.com/TAbdiukov/PPSSPP-patches) | Actif, avec filtrage | Publication structurée épinglée acquise (cwcheat-db) ; seuls programmes complets compatibles avec les moteurs/éditions admis. |
| 44 | [Flycast Widescreen and Cheat Chart](https://github.com/nexus382/Flycast-Widescreen-Compatability-And-Cheat-Chart) | Exclu après essai | Flycast absent des 34 cœurs livrés ; pas de conversion générique des adresses/dialects du tableau Markdown. |
| 45 | [Admentus Enhancement Codes](https://github.com/Admentus64/Enhancement-Codes) | Actif, avec filtrage | Publication structurée épinglée acquise (dolphin-ini) ; seuls programmes complets compatibles avec les moteurs/éditions admis. |
| 46 | [skyzyx OpenEmu cheat database](https://github.com/skyzyx/openemu-cheat-database) | Actif, avec filtrage | Publication structurée épinglée acquise (XML OpenEmu) ; seuls programmes complets compatibles avec les moteurs/éditions admis. |
| 47 | [CheatSlips](https://www.cheatslips.com/) | Référence exclue | Pas de collecte complète validée, accès compte/token non fourni au pipeline. |
| 48 | [SuperCheats GameShark](https://www.supercheats.com/gameboy/pokemonredcodes.htm) | Référence exclue | Pas d’export complet intégré ; titres/régions insuffisants pour une attribution automatique. |
| 49 | [GameFAQs guides auteurs](https://gamefaqs.gamespot.com/gameboy/367023-pokemon-red-version/faqs/5750) | Référence exclue | Guides d’auteurs, aucun catalogue complet exécuté/importé revendiqué. |
| 50 | [JeuxMangas cheats](https://www.jeuxmangas.com/cheat-codes/) | Référence exclue | Pas d’apport nouveau démontré par rapport àLibretro ; pas de collecte complète intégrée. |
| 51 | [BSFree/GSCentral historiques](https://gamehacking.org/download) | Référence exclue | Publication autonome courante non établie ; miroir historique non compté comme nouvelle base. |
| 52 | [GC-Forever, codes auteurs PAL/NTSC](https://www.gc-forever.com/forums/viewtopic.php?t=2007) | Référence exclue | Sujet GameID ciblé seulement ; aucun crawl complet des codes PAL/NTSC du forum. |
| 53 | [Mighty Mo's Cheat Code Pack](https://github.com/mightymo77/MightyMos-Cheat-Code-Pack) | Actif, avec filtrage | Publication structurée épinglée acquise (nestopia-xml) ; seuls programmes complets compatibles avec les moteurs/éditions admis. |
| 54 | [dillonhafer OpenEmu cheats-database.xml](https://gist.github.com/dillonhafer/8399eb1926e2af9164470ad45da67a57) | Actif, avec filtrage | XML OpenEmu acquis ; alias officiel openemu.system.sg=Genesis appliqué, récupérant 9 programmes Sonic Mega Drive avant déduplication. Aucun ajout AR4-4 GG/SMS promis. |
| 55 | [FF7.fr — codes Action Replay français](https://www.ff7.fr/action_replay.php) | Actif, avec filtrage | 8 extraits français complets et disque1identifié ; site non collecté intégralement. |
| 56 | [Ethereal Games](https://etherealgames.com/) | Actif, avec filtrage | 2 extraitsMcDonaldland (Europe) ; site non collecté intégralement. |
| 57 | [PSX Data Center — rubriques Action Replay](https://www.psxdatacenter.com/) | Actif, avec filtrage | 2 extraitsDigimon World (Japon) ; site non collecté intégralement. |
| 58 | [Pokébip — contributions Action Replay](https://www.pokebip.com/espace-membre/blogs/129214/article/84411) | Actif, avec filtrage | 3 extraits bornés àCPUF-D8380D9F ; blog non collecté intégralement. |
| 59 | [Square Palace — codes Secret of Mana](https://squarepalace.com/encyclopedies/secretofmana/cheat-codes-action-replay) | Actif, candidats à confirmer | Huit programmes SNES PAR complets ; absence de région ou de hash conservée explicitement. Aucun match automatique d’édition, aucune région/langue/empreinte inventée. |
| 60 | [Weed Sheet — Sly Cooper](https://github.com/zzamizz/weed-sheet) | Actif, avec filtrage | Publication structurée épinglée acquise (pnach) ; seuls programmes complets compatibles avec les moteurs/éditions admis. |
| 61 | [XoEVOoX Pokémon FireRed codes](https://github.com/xoevoox/pokemon-fire-red-codes) | Actif, avec filtrage | 6 programmes sélectionnés avec leurs masters, USA/Japon séparés ; AUTO vérifié et isolé. |
| 62 | [TylerD007 — The Shiny Pokémon Code Repository](https://github.com/TylerD007/The_Shiny_Pokemon_Code_Repository) | Actif, avec filtrage | 1programme brut complet de 49 lignesROM ; VBA natif, pas de réétiquetageGS/AR. |
| 63 | [Cemu Community Graphic Packs — sous-ensembles Cheats](https://github.com/cemu-project/cemu_graphic_packs) | Exclu après essai | Sous-ensemblesCheats réels de rules/PowerPC ; moteurWii U absent du périmètre. |
| 64 | [Kodewerx — contributions de codes](https://www.kodewerx.org/forum/viewtopic.php?f=18&t=2763&view=print) | Actif, avec filtrage | 3 extraitsMario Kart 64 (USA) complets ; forum non collecté intégralement. |
| 65 | [r/Gameshark — îles événementielles Pokémon Emerald, 12 chiffres](https://www.reddit.com/r/Gameshark/comments/1804kz6/all_the_event_islands_for_pokemon_emerald_have/) | Actif, avec filtrage | 1programme admissible,4 variantes paramétrées exclues ; fil Reddit non présenté comme catalogue complet. |
| 66 | [DeltaCore — tableur public All Cheat Codes](https://github.com/rileytestut/DeltaCore/wiki/Cheats) | Actif, avec filtrage | Tableur complet acquis ; 873acceptés au décodeur sur 948 ; AUTO isolé, cellules/code incomplets exclus. |
| 67 | [ShadeTrees / marbonmb — codes Rubis/Saphir](https://wiki.shadetrees.studio/fr/public/GameShark/Rubis-Codes) | Référence exclue | Catalogue cible non examiné ; aucun programme ajouté à partir de la seule annonce. |
| 68 | [KH-Vids Code Vault](https://kh-vids.net/threads/digimon-world-2003-digimon-world-3-pal.93558/) | Référence exclue | Pas de récupération intégrale ni validation des programmes ; aucun nouveau décompte revendiqué. |
| 69 | [StrategyWiki — rubriques PAR/Game Genie](https://strategywiki.org/wiki/E.V.O.%3A_Search_for_Eden/Cheats) | Référence exclue | Table PAR/Genie repérée, données complètes non contrôlées ; astuces textuelles non assimilées à des programmes. |
| 70 | [Zelda Central — pages Game Genie/GameShark](https://zeldacentral.com/games/a-link-to-the-past/game-genie-codes/) | Référence exclue | ARV3/GS-SP ambigu sur certaines pages ; pas de collecte complète valide ni régionFR déduite du site. |

## Provenance et limites de comptage

- Les identités gardent leur schéma :hashROM, CRC d’en-têteDS, CRC exécutablePCSX2, serial, PPU etBuildID ne sont pas interchangeables. Les titres proposent des candidats d’édition à confirmer ; aucun basculement silencieuxFrance/USA/Japon/World.
- Auteurs, URL, revision/SHA256, programme original et dépendances restent liés aux données. Les sources recoupées enrichissent la provenance ; elles ne multiplient pas le nombre d’effets uniques.
- NCL 1083→713 est une correspondance vers des documents déjà portés ; GameHacking 1 est un extrait ; Delta 873 est une réussite au décodeur ; MiSTer 556747 est un comptage avant déduplication. Aucun de ces nombres ne prétend mesurer des effets Pokémon ou des ROM testés individuellement.
- L’essai PS2GameIndex ne produit aucune identité ; les 229 titres à serialunique sans région ne sont pas transformés en229 jeux compatibles. LesPNACH déjà identifiés restent actifs par leur provenance propre.
- Les 892 handlers 1 SNES / MD sont de la vibration/lecture mémoire avec`CHEAT_TYPE_DISABLED` ; leur exclusion n’est ni un retrait de 892cheats gameplay fonctionnels, ni une absence des moteursSNES / MD.
- Les appels simples respectent la limite agrégée de 99appels. Les tests de parseurs/writers réels et tests portables ne sont pas une nouvelleIPA ni une preuve de gameplay sur appareil. Aucun programme incomplet, long ou paramétré n’est amputé pour augmenter un compteur.

## Vérifications reproductibles dans le dépôt

- [Verrou des 70 références](../../../tools/cheats/unified-sources.json) : portée, versions, empreintes, imports et décisions.
- [Rapport des adaptations natives](../../../docs/unified-cheats-compatibility.md).
- [Preuve des canaux mGBA](../../../tools/cheats/unified-gba-proof.json), [vecteurs natifs](../../../test/unified_native_mgba_vectors.json) et [test reproductible](../../../test/unified_native_mgba_test.py).
- [Vecteurs PicoDrive](../../../test/unified_native_picodrive_vectors.json) et [test reproductible](../../../test/unified_native_picodrive_test.py).
- [Preuves PCE/WonderSwan](../../../test/fixtures/unified_cheats/pce-wswan-primary-memory.json) et [test reproductible](../../../test/unified_identity_pce_ws_source_test.py).
- [Preuve des codes Pokémon français](../../../test/fixtures/unified_cheats/pokered-fr-memory.json) et [validateur sans ROM](../../../tools/cheats/unified_pokered_fr_identity.py).

La table des drivers du binaire FBNeo livré a été jointe exactement aux 3 415 noms INI : zéro intersection avec les familles matérielles NES (2 946 drivers), FDS (207) et SNES (2 696), sur 29 173 drivers au total. Le masque matériel est `0x7FFF0000` ; les valeurs exclues sont `0x1E000000`, `0x1F000000` et `0x22000000`. Cette conclusion vient des valeurs matérielles réelles et des noms du binaire, sans hypothèse fondée sur un préfixe de fichier. Le host revérifie le matériel au moment d’importer.

Les validations de système OpenEmu sont épinglées dans le verrou : l’index officiel distingue `openemu.system.sg` (Genesis/Mega Drive) de `openemu.system.sg1000` (SG-1000). Cette jointure récupère les neuf programmes Sonic MD complets sans changer leurs octets. Les seize Action Replay SMS/GG à quatre chiffres, tiret, quatre chiffres restent dans l’audit ; aucune équivalence vers le canal natif revu n’est revendiquée.

Les 107 noms INI absents de la table exacte du binaire FBNeo sont retirés sans hypothèse d’alias ou de parent. Le filtre retire exactement 1 344 programmes du total publié ; 25 autres étaient déjà bloqués. Le premier audit du format comptait 61 192 blocs, devenus 60 431 programmes après déduplication, puis 59 087 après le filtre des pilotes. Les contributions publiées après déduplication sont mesurées dans SOURCES.md. Les MD5 XML non attestés restent conservés sous `openemu-md5-unspecified` et imposent une confirmation d’édition ; aucune correspondance automatique avec un MD5 brut ou normalisé n’est créée.
