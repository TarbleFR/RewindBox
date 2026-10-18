# Sources de cheats NeoStation — inventaire avant IPA

**Version figée du catalogue : `bf10b1c3314e951c810a2e786c67a10bc388fe34530badb45ebfe3565881bcb4`.**

70 pistes documentées ; 34 attributions de sources présentes dans le manifeste actif, provenance seule comprise.

La publication contient **2 341 355 programmes dédupliqués dans leurs groupes d’identité**, 43 813 groupes d’identité, 44 955 fiches de transport et 2 341 355 enregistrements de programmes dans les packs, duplications éventuelles de dépendances entre parties comprises.

Un programme est un ensemble complet d’instructions et de dépendances activable comme un même choix. Les contributions d’une source peuvent recouper celles d’autres sources : **elles ne s’additionnent pas pour obtenir un nombre de cheats uniques**. Les groupes d’identité ne sont pas un décompte de jeux commerciaux uniques ; plusieurs régions, révisions et schémas d’empreinte restent distincts. Les fiches de transport peuvent être des parties d’un même groupe.

Les packs proposés au téléchargement contiennent les programmes compatibles retenus. Les pistes non récupérées, les formats sans moteur et les programmes rejetés restent dans cet inventaire et dans l’audit. Le téléchargement n’active aucun cheat.

L’action globale « Télécharger tous les catalogues » utilise [l’index unifié NeoStation](https://raw.githubusercontent.com/TarbleFR/neostation-ios/Claude/native/cheats/catalogue/manifest.json.gz). Les packs sont vérifiés avant installation ; une reprise conserve les packs déjà installés et retente ceux qui manquent.

## Portée du téléchargement et reconnaissance du jeu

La même source de téléchargement dessert les consoles RetroArch, ARMSX2, Dolphin et RPCS3, par leurs adaptateurs respectifs. La présence d’une console ou d’un core dans NeoStation n’implique pas que son callback cheats soit utilisable. Les profils exécutables et leurs limites sont détaillés dans [la matrice de compatibilité](unified-cheats-compatibility.md).

Les éditions Europe, USA, World, langues et révisions sont conservées telles que documentées. L’empreinte, son schéma et les identifiants natifs commandent la correspondance. Un titre ressemblant ou la langue française d’un site propose au mieux un candidat ; il ne transforme pas un code USA en code FR. Une contradiction connue de région, de révision ou d’empreinte bloque l’import.

Pour Pokémon Rouge/Bleu FR, les extraits vérifiés sont reliés aux empreintes originales du désassemblage français et à ses déclarations mémoire. Cette vérification statique ne constitue pas un test de chaque effet en jeu et ne s’étend pas automatiquement à Jaune ou à une ROM modifiée. Chaque empreinte originale Rouge ou Bleu FR dispose de cinq programmes : quatre programmes Pokémon France nouvellement attestés pour ces éditions, plus un programme Libretro déjà existant. Ce sont cinq programmes par édition, pas cinq nouveautés ni dix effets nouveaux.

## Inventaire des 70 pistes

Les numéros sont ceux de l’inventaire de recherche. « Active » signifie qu’une contribution figure dans le manifeste figé, pas que le site entier a été téléchargé ni que toutes ses entrées sont utilisables.

| N° | Source et URL | Statut | Portée réelle ; adaptation ou exclusion |
|---:|---|---|---|
| 1 | [Libretro Database](https://github.com/libretro/libretro-database) | Active — partielle | CHT multiconsoles ; profils réellement exécutables des cores livrés, y compris les sous-ensembles PicoDrive, PCE Fast et WonderSwan audités. Programme complet, dialecte et dépendances validés. Publication partielle ; motifs de rejet détaillés ci-dessous. |
| 2 | [GameHacking.org](https://gamehacking.org/) | Active — extraits | Extraits complets sélectionnés, avec attribution d’origine ; collecte intégrale du site ou du forum non réalisée. Programme complet, dialecte et dépendances validés. |
| 3 | [DeadSkullzJr NDS(i) Cheat Databases](https://gbatemp.net/threads/deadskullzjrs-nds-i-cheat-databases.488711/) | Active — partielle | Base DS/DSi : miroir historique complet vérifié de 2022, distinct de l’édition courante de l’auteur ; programmes Action Replay complets conservés. Programme complet, dialecte et dépendances validés. Publication partielle ; motifs de rejet détaillés ci-dessous. |
| 4 | [FlagBrew Sharkive](https://github.com/FlagBrew/Sharkive) | Non publiée | Base GateShark 3DS récupérée ; le callback cheats du core Azahar livré est une fonction sans effet. Adaptation examinée : callbacks Azahar set/reset immédiatement RET, sans API CheatEngine exploitable. Renommer GateShark ne permet pas son exécution. |
| 5 | [iSharingan CTRPF-AR-CHEAT-CODES](https://github.com/iSharingan/CTRPF-AR-CHEAT-CODES) | Non publiée | Base CTRPF/GateShark 3DS récupérée ; interpréteur CTRPF et voie d’exécution Azahar absents. Adaptation examinée : même absence de voie cheats Azahar, avec en plus des opcodes CTRPF exigeant leur interpréteur propre. |
| 6 | [CWCheat Database Plus](https://github.com/Saramagrean/CWCheat-Database-Plus-) | Active — partielle | Base PSP CWCheat ; programmes et conditions conservés ensemble dans le canal natif PPSSPP. Programme complet, dialecte et dépendances validés. Publication partielle ; motifs de rejet détaillés ci-dessous. |
| 7 | [DuckStation chtdb](https://github.com/duckstation/chtdb) | Active — partielle | Base PS1 CHT ; écritures GameShark et sous-ensemble conditionnel compatible avec les cores Beetle livrés. Programme complet, dialecte et dépendances validés. Publication partielle ; motifs de rejet détaillés ci-dessous. |
| 8 | [CheatDevicePS2](https://github.com/root670/CheatDevicePS2) | Non publiée | Archive CheatDevicePS2 analysée ; conversion RAW vers PNACH examinée, sans identité de jeu reconstruite par titre. Conversion RAW 0/1/2 vers PNACH possible structurellement, mais aucun rapprochement sûr CRC exécutable + série + région n’a été établi avec le GameIndex ARMSX2. Aucun identifiant inventé. |
| 9 | [pcsx2_cheats_collection](https://github.com/xs1l3n7x/pcsx2_cheats_collection) | Active — partielle | Fichiers PS2 PNACH complets, liés au CRC exécutable ; import natif ARMSX2. Programme complet, dialecte et dépendances validés. Publication partielle ; motifs de rejet détaillés ci-dessous. |
| 10 | [PCSX2 patches](https://github.com/PCSX2/pcsx2_patches) | Sans export intégré | Piste PS2 de correctifs, notamment affichage et désentrelacement ; aucun export intégré à ce lot. Export structuré non récupéré pour cette intégration ; correctifs grand écran ou désentrelacement non présentés comme des cheats gameplay supplémentaires. |
| 11 | [Dolphin GameSettings](https://github.com/dolphin-emu/dolphin/tree/master/Data/Sys/GameSettings) | Active — partielle | GameINI GameCube/Wii : blocs Gecko et Action Replay complets ; GameID et révision restent distincts. Programme complet, dialecte et dépendances validés. Publication partielle ; motifs de rejet détaillés ci-dessous. |
| 12 | [RiiConnect24 GeckoCodes mirror](https://codes.rc24.xyz/) | Sans export intégré | Ancien fournisseur GeckoCodes ; l’endpoint GameID essayé est indisponible, sans export de remplacement inventé. L’endpoint précis essayé répond HTTP 404 ; aucun export structuré récupéré. Les sources Dolphin et GeckoArchive servent de voies distinctes. |
| 13 | [GeckoArchive](https://github.com/SpaceXCheeseWheel/GeckoArchive) | Active — partielle | Archive de programmes Gecko GameCube/Wii, indexés par identifiant de jeu. Programme complet, dialecte et dépendances validés. Publication partielle ; motifs de rejet détaillés ci-dessous. |
| 14 | [Pugsy MAME Cheats](https://www.mamecheat.co.uk/) | Non publiée | Archive MAME XML ; son cycle d’activation et ses espaces CPU ne sont pas assimilés à ceux de FBNeo. MAME2003 Plus absent des cores livrés ; cycle de vie, périphériques et espaces CPU du XML non transposables au parseur INI FBNeo par simple renommage. |
| 15 | [FBNeo cheats](https://github.com/finalburnneo/FBNeo-cheats) | Active — partielle | INI natifs FBNeo : driver, CPU, adresses et choix préservés ; import désactivé par défaut dans la voie INI du core. Programme complet, dialecte et dépendances validés. Publication partielle ; motifs de rejet détaillés ci-dessous. |
| 16 | [Project64 Cheats](https://github.com/project64/project64/tree/develop/Config/Cheats) | Active — partielle | Base Project64 N64 ; paramètres, conditions et répétitions soumis au profil Mupen livré. Programme complet, dialecte et dépendances validés. Publication partielle ; motifs de rejet détaillés ci-dessous. |
| 17 | [Mupen64Plus database](https://github.com/mupen64plus/mupen64plus-core/blob/master/data/mupencheat.txt) | Active — partielle | Base Mupen64Plus N64 ; mêmes contraintes de programme complet et d’opcodes que le moteur livré. Programme complet, dialecte et dépendances validés. Publication partielle ; motifs de rejet détaillés ci-dessous. |
| 18 | [Mesen2 CheatDb](https://github.com/SourMesen/Mesen2/tree/master/UI/Dependencies/Internal) | Active — partielle | JSON NES/SNES ; empreintes et schémas propres à chaque système, sans rapprochement par titre seul. Programme complet, dialecte et dépendances validés. Publication partielle ; motifs de rejet détaillés ci-dessous. |
| 19 | [Snes9x cheats.bml](https://github.com/snes9xgit/snes9x/blob/master/data/cheats.bml) | Active — partielle | BML multiconsoles : seules les entrées reliées à la base primaire SNES par SHA256 et schéma exact sont publiables. Programme complet, dialecte et dépendances validés. Publication partielle ; motifs de rejet détaillés ci-dessous. |
| 20 | [ArtemisPS3](https://github.com/bucanero/ArtemisPS3/tree/master/docs/codes) | Provenance seule | Provenance de blocs NCL rapprochés exactement de portages auteurs RPCS3 déjà présents ; aucun interpréteur NCL général ajouté. Rapprochement exact avec des documents RPCS3 déjà portés par leurs auteurs : attribution enrichie, aucun programme nouveau ajouté par ce rapprochement. |
| 21 | [Artemis Patch Collection RPCS3](https://github.com/chidreams/Artemis-Patch-Collection-RPCS3) | Active — partielle | Documents YAML natifs RPCS3 ; PPU, titre, version et dépendances statiques préservés. Programme complet, dialecte et dépendances validés. Publication partielle ; motifs de rejet détaillés ci-dessous. |
| 22 | [r0ah VitaCheat](https://github.com/r0ah/vitacheat) | Non publiée | Archive PSV VitaCheat récupérée et épinglée ; moteur Vita absent. Pas de moteur Vita ni de plugin VitaCheat et de modèle mémoire correspondant dans NeoStation. |
| 23 | [ShumnoT VitaCheatDatabase](https://github.com/ShumnoT/VitaCheatDatabase) | Non publiée | Archive PSV VitaCheat récupérée et épinglée ; moteur Vita absent. Pas de moteur Vita ni de plugin VitaCheat et de modèle mémoire correspondant dans NeoStation. |
| 24 | [HamletDuFromage switch-cheats-db](https://github.com/HamletDuFromage/switch-cheats-db) | Non publiée | Archive Switch/Atmosphère épinglée ; BuildID et moteur Switch nécessaires. Pas de moteur Switch ; interpréteur Atmosphère et BuildID exact nécessaires. |
| 25 | [EdiZon CheatsConfigsAndScripts](https://github.com/WerWolv/EdiZon_CheatsConfigsAndScripts) | Non publiée | Configurations et scripts EdiZon/Atmosphère ; moteur Switch nécessaire. Pas de moteur Switch ; scripts et programmes mémoire EdiZon/Atmosphère non exécutables par les moteurs présents. |
| 26 | [ibnux switch-cheat](https://github.com/ibnux/switch-cheat) | Non publiée | Programmes Switch/Atmosphère ; moteur Switch nécessaire. Pas de moteur Switch ; programmes mémoire Atmosphère exclus des packs actifs. |
| 27 | [GBAtemp Matias3ds / exefer mirror](https://github.com/exefer/gbatemp-matias3ds-cheats) | Non publiée | Miroir de contributions GBAtemp Switch ; ne constitue pas un moteur Switch dans NeoStation. Pas de moteur Switch ; un miroir de programmes ne fournit pas l’interpréteur nécessaire. |
| 28 | [Chansey NX 60FPS RES GFX](https://github.com/ChanseyIsTheBest/NX-60FPS-RES-GFX-Cheats) | Non publiée | Correctifs Switch de performances et d’affichage ; moteur et BuildID correspondants nécessaires. Pas de moteur Switch ; correctifs liés à un BuildID et à un moteur absents. |
| 29 | [Pokémon France / PokéLord](https://www.pokemon-france.com/jeux/gen1/bleu_rouge/actionreplay/) | Active — extraits | Extraits Rouge/Bleu français ; adresses et empreintes contrôlées sur la source primaire du désassemblage FR. Le site complet n’a pas été aspiré. Programme complet, dialecte et dépendances validés. Publication partielle ; motifs de rejet détaillés ci-dessous. |
| 30 | [Pokémon Trash codes](https://www.pokemontrash.com/codes-pokemon) | Sans export intégré | Piste documentaire ; aucun export structuré intégré à ce lot. Export structuré non récupéré pour cette intégration ; aucun code ajouté par supposition. Conserver mastercodes, anti-DMA, conditions de boutons et région. |
| 31 | [Project Pokémon RAM cheats](https://projectpokemon.org/home/forums/) | Sans export intégré | Piste documentaire ; aucun export structuré intégré à ce lot. Export structuré non récupéré pour cette intégration ; aucun code ajouté par supposition. Les adaptations FR/US publiées sont propres au code; pas de règle universelle d'offset. |
| 32 | [PokémonCoders](https://www.pokemoncoders.com/all-pokemon-cheats-compilation/) | Sans export intégré | Piste documentaire ; aucun export structuré intégré à ce lot. Export structuré non récupéré pour cette intégration ; aucun code ajouté par supposition. Code d'un hack incompatible avec l'original par défaut. Tests revendiqués par l'éditeur, non reproduits ici. |
| 33 | [GameGenie.com](https://gamegenie.com/cheats/) | Sans export intégré | Piste documentaire ; aucun export structuré intégré à ce lot. Export structuré non récupéré pour cette intégration ; aucun code ajouté par supposition. Le site comprend aussi des astuces et séquences de boutons. |
| 34 | [CodeTwink](https://codetwink.com/) | Sans export intégré | Piste documentaire ; aucun export structuré intégré à ce lot. Export structuré non récupéré pour cette intégration ; aucun code ajouté par supposition. Chiffrement et opcodes PS2 à vérifier. Ne pas présenter tout le site comme exécutable directement. |
| 35 | [Datel Codejunkies](https://us.codejunkies.com/search/codes_search.aspx) | Sans export intégré | Piste documentaire ; aucun export structuré intégré à ce lot. Export structuré non récupéré pour cette intégration ; aucun code ajouté par supposition. disponibilité accès automatisé et conditions non vérifiés |
| 36 | [PSX Emulation Cheater PEC](https://pec.duttke.de/download.php) | Sans export intégré | Piste documentaire ; aucun export structuré intégré à ce lot. Export structuré non récupéré pour cette intégration ; aucun code ajouté par supposition. page téléchargement annonce base18/11/2002; recoupe sources historiques et droits auteurs |
| 37 | [MiSTer Cheats](https://github.com/MiSTer-devel/Cheats_MiSTer) | Active — partielle | Archive MiSTer auditée par famille ; seules les conversions démontrées NES, PS1 et GBA sont retenues, avec les tuples originaux préservés. Programme complet, dialecte et dépendances validés. Publication partielle ; motifs de rejet détaillés ci-dessous. |
| 38 | [Serebii Red Blue GameShark](https://www.serebii.net/rb/gamesharkrb.shtml) | Sans export intégré | Piste documentaire ; aucun export structuré intégré à ce lot. Export structuré non récupéré pour cette intégration ; aucun code ajouté par supposition. Variantes paramétrées à résoudre. Compatibilité FR non déduite de la langue du site. |
| 39 | [Glitch City Wiki GameShark](https://glitchcity.wiki/wiki/Pok%C3%A9mon_Red%2C_Blue_and_Yellow_GameShark_codes) | Sans export intégré | Piste documentaire ; aucun export structuré intégré à ce lot. Export structuré non récupéré pour cette intégration ; aucun code ajouté par supposition. Source technique de complément; n'appliquer aucune conversion régionale globale. |
| 40 | [EZ-Flash Omega Cheat Library](https://www.ezflash.cn/download/) | Sans export intégré | Piste documentaire ; aucun export structuré intégré à ce lot. Export structuré non récupéré pour cette intégration ; aucun code ajouté par supposition. distinct de libretro, convertisseur jer-irl fait fusion; format et provenance à confirmer |
| 41 | [PPSSPP CWCheat forum](https://forums.ppsspp.org/forumdisplay.php?fid=31) | Sans export intégré | Piste documentaire ; aucun export structuré intégré à ce lot. Export structuré non récupéré pour cette intégration ; aucun code ajouté par supposition. recoupe déjà CWCheat+, pas collecte intégrale effectuée |
| 42 | [LunaMoo PPSSPP workarounds](https://github.com/LunaMoo/PPSSPP_workarounds) | Active — partielle | Programmes PSP CWCheat, dont contournements et correctifs ; nature du programme conservée. Programme complet, dialecte et dépendances validés. Publication partielle ; motifs de rejet détaillés ci-dessous. |
| 43 | [TAbdiukov PPSSPP patches](https://github.com/TAbdiukov/PPSSPP-patches) | Active — partielle | Correctifs PSP CWCheat complets ; aucune conversion en simple écriture supposée. Programme complet, dialecte et dépendances validés. Publication partielle ; motifs de rejet détaillés ci-dessous. |
| 44 | [Flycast Widescreen and Cheat Chart](https://github.com/nexus382/Flycast-Widescreen-Compatability-And-Cheat-Chart) | Non publiée | Table Flycast Dreamcast examinée : type, taille, adresse, répétitions et conditions ; aucune voie Dreamcast livrée compatible. Adaptation examinée : Flycast absent des cores livrés et aucune transposition préservant les conditions, tailles et répétitions n’est attestée. |
| 45 | [Admentus Enhancement Codes](https://github.com/Admentus64/Enhancement-Codes) | Active | Blocs Gecko/Action Replay d’amélioration GameCube/Wii ; ils restent identifiés comme correctifs ou améliorations. Programme complet, dialecte et dépendances validés. |
| 46 | [skyzyx OpenEmu cheat database](https://github.com/skyzyx/openemu-cheat-database) | Active — partielle | XML OpenEmu multiconsoles épinglé ; MD5 de domaine non établi conservé comme opaque, avec confirmation d’édition requise, sans l’assimiler au MD5 d’une ROM complète. Programme complet, dialecte et dépendances validés. Publication partielle ; motifs de rejet détaillés ci-dessous. |
| 47 | [CheatSlips](https://www.cheatslips.com/) | Sans export intégré | Piste documentaire ; aucun export structuré intégré à ce lot. Export structuré non récupéré pour cette intégration ; aucun code ajouté par supposition. compte/token personnel; accès et fiabilité à valider; pas retenu automatiquement |
| 48 | [SuperCheats GameShark](https://www.supercheats.com/gameboy/pokemonredcodes.htm) | Sans export intégré | Piste documentaire ; aucun export structuré intégré à ce lot. Export structuré non récupéré pour cette intégration ; aucun code ajouté par supposition. Titres et régions parfois insuffisants. Validation par code nécessaire avant automatisation. |
| 49 | [GameFAQs guides auteurs](https://gamefaqs.gamespot.com/gameboy/367023-pokemon-red-version/faqs/5750) | Sans export intégré | Piste documentaire ; aucun export structuré intégré à ce lot. Export structuré non récupéré pour cette intégration ; aucun code ajouté par supposition. conditions et droits auteurs à respecter, pas moteur de catalogues |
| 50 | [JeuxMangas cheats](https://www.jeuxmangas.com/cheat-codes/) | Sans export intégré | Piste documentaire ; aucun export structuré intégré à ce lot. Export structuré non récupéré pour cette intégration ; aucun code ajouté par supposition. compteurs proches Libretro, apport nouveau non démontré |
| 51 | [BSFree/GSCentral historiques](https://gamehacking.org/download) | Sans export intégré | Piste documentaire ; aucun export structuré intégré à ce lot. Export structuré non récupéré pour cette intégration ; aucun code ajouté par supposition. source courante autonome non établie; éviter compter ancien mirror comme nouveau catalogue |
| 52 | [GC-Forever, codes auteurs PAL/NTSC](https://www.gc-forever.com/forums/viewtopic.php?t=2007) | Sans export intégré | Piste documentaire ; aucun export structuré intégré à ce lot. Export structuré non récupéré pour cette intégration ; aucun code ajouté par supposition. Le code actuel ne couvre qu'un sujet GameID ciblé. Étendre l'index et conserver PAL/NTSC/langues et auteurs. |
| 53 | [Mighty Mo's Cheat Code Pack](https://github.com/mightymo77/MightyMos-Cheat-Code-Pack) | Active — partielle | Pack NES/Nestopia XML ; parties d’un même programme réunies seulement lorsque leur ordre et leur complétude sont attestés. Programme complet, dialecte et dépendances validés. Publication partielle ; motifs de rejet détaillés ci-dessous. |
| 54 | [dillonhafer OpenEmu cheats-database.xml](https://gist.github.com/dillonhafer/8399eb1926e2af9164470ad45da67a57) | Active — partielle | XML OpenEmu ; alias officiel sg/Mega Drive vérifié, MD5 opaque et édition à confirmer. La provenance peut recouper les autres bases. Programme complet, dialecte et dépendances validés. Publication partielle ; motifs de rejet détaillés ci-dessous. |
| 55 | [FF7.fr — codes Action Replay français](https://www.ff7.fr/action_replay.php) | Active — extraits | Extraits complets sélectionnés, avec attribution d’origine ; collecte intégrale du site ou du forum non réalisée. Programme complet, dialecte et dépendances validés. |
| 56 | [Ethereal Games](https://etherealgames.com/) | Active — extraits | Extraits complets sélectionnés, avec attribution d’origine ; collecte intégrale du site ou du forum non réalisée. Programme complet, dialecte et dépendances validés. |
| 57 | [PSX Data Center — rubriques Action Replay](https://www.psxdatacenter.com/) | Active — extraits | Extraits complets sélectionnés, avec attribution d’origine ; collecte intégrale du site ou du forum non réalisée. Programme complet, dialecte et dépendances validés. |
| 58 | [Pokébip — contributions Action Replay](https://www.pokebip.com/espace-membre/blogs/129214/article/84411) | Active — extraits | Extraits complets sélectionnés, avec attribution d’origine ; collecte intégrale du site ou du forum non réalisée. Programme complet, dialecte et dépendances validés. |
| 59 | [Square Palace — codes Secret of Mana](https://squarepalace.com/encyclopedies/secretofmana/cheat-codes-action-replay) | Active — extraits | Extraits PAR Secret of Mana ; édition non attestée : candidats à confirmer, sans région, langue ou révision inventée. Programme complet, dialecte et dépendances validés. |
| 60 | [Weed Sheet — Sly Cooper](https://github.com/zzamizz/weed-sheet) | Active — partielle | PNACH Sly Cooper PS2 complets ; catégories gameplay, correctifs et modifications conservées. Programme complet, dialecte et dépendances validés. Publication partielle ; motifs de rejet détaillés ci-dessous. |
| 61 | [XoEVOoX Pokémon FireRed codes](https://github.com/xoevoox/pokemon-fire-red-codes) | Active — extraits | Extraits complets sélectionnés, avec attribution d’origine ; collecte intégrale du site ou du forum non réalisée. Programme complet, dialecte et dépendances validés. |
| 62 | [TylerD007 — The Shiny Pokémon Code Repository](https://github.com/TylerD007/The_Shiny_Pokemon_Code_Repository) | Active — extraits | Extraits complets sélectionnés, avec attribution d’origine ; collecte intégrale du site ou du forum non réalisée. Programme complet, dialecte et dépendances validés. |
| 63 | [Cemu Community Graphic Packs — sous-ensembles Cheats](https://github.com/cemu-project/cemu_graphic_packs) | Non publiée | Packs Cemu Wii U récupérés ; règles et correctifs PowerPC nécessitant un moteur Wii U absent. Pas de moteur Wii U/Cemu ; règles et patches PowerPC non exécutables par Dolphin. |
| 64 | [Kodewerx — contributions de codes](https://www.kodewerx.org/forum/viewtopic.php?f=18&t=2763&view=print) | Active — extraits | Extraits complets sélectionnés, avec attribution d’origine ; collecte intégrale du site ou du forum non réalisée. Programme complet, dialecte et dépendances validés. |
| 65 | [r/Gameshark — îles événementielles Pokémon Emerald, 12 chiffres](https://www.reddit.com/r/Gameshark/comments/1804kz6/all_the_event_islands_for_pokemon_emerald_have/) | Active — extraits | Extraits complets sélectionnés, avec attribution d’origine ; collecte intégrale du site ou du forum non réalisée. Programme complet, dialecte et dépendances validés. Publication partielle ; motifs de rejet détaillés ci-dessous. |
| 66 | [DeltaCore — tableur public All Cheat Codes](https://github.com/rileytestut/DeltaCore/wiki/Cheats) | Active — partielle | Tableur public complet épinglé ; programmes mGBA AUTO/VBA vérifiés, lignes malformées et variantes non résolues exclues. Programme complet, dialecte et dépendances validés. Publication partielle ; motifs de rejet détaillés ci-dessous. |
| 67 | [ShadeTrees / marbonmb — codes Rubis/Saphir](https://wiki.shadetrees.studio/fr/public/GameShark/Rubis-Codes) | Sans export intégré | Piste documentaire ; aucun export structuré intégré à ce lot. Export structuré non récupéré pour cette intégration ; aucun code ajouté par supposition. La publication annonce des conversions et quelques ajouts; le catalogue cible n'a pas pu être examiné. Ne pas inclure dans le téléchargement fonctionnel par défaut. |
| 68 | [KH-Vids Code Vault](https://kh-vids.net/threads/digimon-world-2003-digimon-world-3-pal.93558/) | Sans export intégré | Piste documentaire ; aucun export structuré intégré à ce lot. Export structuré non récupéré pour cette intégration ; aucun code ajouté par supposition. Pas de récupération intégrale ni de validation des programmes. Aucun décompte de nouveaux codes. |
| 69 | [StrategyWiki — rubriques PAR/Game Genie](https://strategywiki.org/wiki/E.V.O.%3A_Search_for_Eden/Cheats) | Sans export intégré | Piste documentaire ; aucun export structuré intégré à ce lot. Export structuré non récupéré pour cette intégration ; aucun code ajouté par supposition. La page annonce une table PAR/Game Genie; données complètes non contrôlées. Ne pas confondre cheats textuels et programmes exécutables. |
| 70 | [Zelda Central — pages Game Genie/GameShark](https://zeldacentral.com/games/a-link-to-the-past/game-genie-codes/) | Sans export intégré | Piste documentaire ; aucun export structuré intégré à ce lot. Export structuré non récupéré pour cette intégration ; aucun code ajouté par supposition. Certains codes à 12 chiffres sont désignés AR V3/GS SP de manière ambiguë. Ne pas sélectionner le moteur d'après cette seule étiquette. La version française du site ne prouve pas la région FR du jeu. |

## Contributions effectivement présentes

Chaque ligne indique une attribution de programmes à une source ; un même programme peut conserver plusieurs provenances. ArtemisPS3 enrichit la provenance de documents RPCS3 existants et ne leur ajoute pas un second exemplaire.

| N° | Source | Contribution publiée | Révision de la source |
|---:|---|---|---|
| 1 | [Libretro Database](https://github.com/libretro/libretro-database) | 1 007 827 programmes attribués | `12c21cf79f1e20eff6ac68b80875816c717d0a7a` |
| 2 | [GameHacking.org](https://gamehacking.org/) | 1 programmes attribués | `e22387704e9643f72160b84bb1809089e8fbd0a10f8e28aa56a45c47f594908e` |
| 3 | [DeadSkullzJr NDS(i) Cheat Databases](https://gbatemp.net/threads/deadskullzjrs-nds-i-cheat-databases.488711/) | 590 953 programmes attribués | `28ad3272d3578ba2f493e78990a3d6defe9dfebe37d9f53501679be9498eafae` |
| 6 | [CWCheat Database Plus](https://github.com/Saramagrean/CWCheat-Database-Plus-) | 77 010 programmes attribués | `8290de1a8498f2efdce6d4d86d71dae78f92aa579c79bd43803a40f97f9ec502` |
| 7 | [DuckStation chtdb](https://github.com/duckstation/chtdb) | 44 029 programmes attribués | `8b2f1dd257ab9130d16b72e0caeb5a07af8bcbdc` |
| 9 | [pcsx2_cheats_collection](https://github.com/xs1l3n7x/pcsx2_cheats_collection) | 561 programmes attribués | `6cb57b55939f47dd91a157bfb6cdc7fd157a780c` |
| 11 | [Dolphin GameSettings](https://github.com/dolphin-emu/dolphin/tree/master/Data/Sys/GameSettings) | 4 119 programmes attribués | `38d619b07691231f54e6f037fcf30a3b64fdd5a5` |
| 13 | [GeckoArchive](https://github.com/SpaceXCheeseWheel/GeckoArchive) | 44 293 programmes attribués | `d465c2190d32f954056dd1e6ba68a2ec3fc588ff` |
| 15 | [FBNeo cheats](https://github.com/finalburnneo/FBNeo-cheats) | 59 087 programmes attribués | `084b13ed7a4d437614a2bf47664cc567ac9dcdef` |
| 16 | [Project64 Cheats](https://github.com/project64/project64/tree/develop/Config/Cheats) | 8 516 programmes attribués | `24376e868350792a181d2121fec20d37354559d6` |
| 17 | [Mupen64Plus database](https://github.com/mupen64plus/mupen64plus-core/blob/master/data/mupencheat.txt) | 7 567 programmes attribués | `d3206c3f5cf57a8ebcc29729837fb9f5c1645a6c571e68aa08a178db2e950b36` |
| 18 | [Mesen2 CheatDb](https://github.com/SourMesen/Mesen2/tree/master/UI/Dependencies/Internal) | 22 615 programmes attribués | `b9fa69ddc6d0a331fb103fdb5eef6904305703c2` |
| 19 | [Snes9x cheats.bml](https://github.com/snes9xgit/snes9x/blob/master/data/cheats.bml) | 13 121 programmes attribués | `7c49c481697d6d79e2100912b9784a1b4c8f5a88a74c0c970e83afbebb7f7e22` |
| 20 | [ArtemisPS3](https://github.com/bucanero/ArtemisPS3/tree/master/docs/codes) | 713 correspondances de provenance ; 0 programme nouveau | `d79b41e525e20251bd0d919100039ac0a6433956` |
| 21 | [Artemis Patch Collection RPCS3](https://github.com/chidreams/Artemis-Patch-Collection-RPCS3) | 1 829 programmes attribués | `21fc0ee86578f1452e42da01187eb852ab034b28` |
| 29 | [Pokémon France / PokéLord](https://www.pokemon-france.com/jeux/gen1/bleu_rouge/actionreplay/) | 8 programmes attribués | `e22387704e9643f72160b84bb1809089e8fbd0a10f8e28aa56a45c47f594908e` |
| 37 | [MiSTer Cheats](https://github.com/MiSTer-devel/Cheats_MiSTer) | 455 353 programmes attribués | `56eb5194c6a6c4a718ac0f67a93c498a7a7a4760` |
| 42 | [LunaMoo PPSSPP workarounds](https://github.com/LunaMoo/PPSSPP_workarounds) | 191 programmes attribués | `1355bb338d4a1985aae043f674a070ef99c49524` |
| 43 | [TAbdiukov PPSSPP patches](https://github.com/TAbdiukov/PPSSPP-patches) | 236 programmes attribués | `a38b2aba3e0e24935392d2617b14b35d73ab0f27` |
| 45 | [Admentus Enhancement Codes](https://github.com/Admentus64/Enhancement-Codes) | 848 programmes attribués | `f8e9ad12d90460e316b552fdf73052eb308e9ab9` |
| 46 | [skyzyx OpenEmu cheat database](https://github.com/skyzyx/openemu-cheat-database) | 241 programmes attribués | `5f1af6161ee30fddccc3942dfbcc20b253bcb152` |
| 53 | [Mighty Mo's Cheat Code Pack](https://github.com/mightymo77/MightyMos-Cheat-Code-Pack) | 10 244 programmes attribués | `v2025-08-08` |
| 54 | [dillonhafer OpenEmu cheats-database.xml](https://gist.github.com/dillonhafer/8399eb1926e2af9164470ad45da67a57) | 477 programmes attribués | `aa9e0b356dbf24c102b8b0794b108af80afefe4804fb65c365d2e78dd878e797` |
| 55 | [FF7.fr — codes Action Replay français](https://www.ff7.fr/action_replay.php) | 8 programmes attribués | `e22387704e9643f72160b84bb1809089e8fbd0a10f8e28aa56a45c47f594908e` |
| 56 | [Ethereal Games](https://etherealgames.com/) | 2 programmes attribués | `e22387704e9643f72160b84bb1809089e8fbd0a10f8e28aa56a45c47f594908e` |
| 57 | [PSX Data Center — rubriques Action Replay](https://www.psxdatacenter.com/) | 2 programmes attribués | `e22387704e9643f72160b84bb1809089e8fbd0a10f8e28aa56a45c47f594908e` |
| 58 | [Pokébip — contributions Action Replay](https://www.pokebip.com/espace-membre/blogs/129214/article/84411) | 3 programmes attribués | `e22387704e9643f72160b84bb1809089e8fbd0a10f8e28aa56a45c47f594908e` |
| 59 | [Square Palace — codes Secret of Mana](https://squarepalace.com/encyclopedies/secretofmana/cheat-codes-action-replay) | 8 programmes attribués | `e22387704e9643f72160b84bb1809089e8fbd0a10f8e28aa56a45c47f594908e` |
| 60 | [Weed Sheet — Sly Cooper](https://github.com/zzamizz/weed-sheet) | 255 programmes attribués | `7dedab5f6ca43beff14a0f5fac6d353337d62b06` |
| 61 | [XoEVOoX Pokémon FireRed codes](https://github.com/xoevoox/pokemon-fire-red-codes) | 6 programmes attribués | `e22387704e9643f72160b84bb1809089e8fbd0a10f8e28aa56a45c47f594908e` |
| 62 | [TylerD007 — The Shiny Pokémon Code Repository](https://github.com/TylerD007/The_Shiny_Pokemon_Code_Repository) | 1 programmes attribués | `e22387704e9643f72160b84bb1809089e8fbd0a10f8e28aa56a45c47f594908e` |
| 64 | [Kodewerx — contributions de codes](https://www.kodewerx.org/forum/viewtopic.php?f=18&t=2763&view=print) | 3 programmes attribués | `e22387704e9643f72160b84bb1809089e8fbd0a10f8e28aa56a45c47f594908e` |
| 65 | [r/Gameshark — îles événementielles Pokémon Emerald, 12 chiffres](https://www.reddit.com/r/Gameshark/comments/1804kz6/all_the_event_islands_for_pokemon_emerald_have/) | 1 programmes attribués | `e22387704e9643f72160b84bb1809089e8fbd0a10f8e28aa56a45c47f594908e` |
| 66 | [DeltaCore — tableur public All Cheat Codes](https://github.com/rileytestut/DeltaCore/wiki/Cheats) | 871 programmes attribués | `12f8cd5859570e3e8b03b9847ff0d32273f9ae912dca3d7b700b24e77cad5787` |

## Les 14 compléments : références 53 à 66

Ces références sont une série précisément identifiée de l’inventaire ; leur présence ici n’affirme pas que les quatorze sont toutes publiées.

| N° | Complément | Statut | Contribution |
|---:|---|---|---|
| 53 | [Mighty Mo's Cheat Code Pack](https://github.com/mightymo77/MightyMos-Cheat-Code-Pack) | Active — partielle | 10 244 programmes attribués |
| 54 | [dillonhafer OpenEmu cheats-database.xml](https://gist.github.com/dillonhafer/8399eb1926e2af9164470ad45da67a57) | Active — partielle | 477 programmes attribués |
| 55 | [FF7.fr — codes Action Replay français](https://www.ff7.fr/action_replay.php) | Active — extraits | 8 programmes attribués |
| 56 | [Ethereal Games](https://etherealgames.com/) | Active — extraits | 2 programmes attribués |
| 57 | [PSX Data Center — rubriques Action Replay](https://www.psxdatacenter.com/) | Active — extraits | 2 programmes attribués |
| 58 | [Pokébip — contributions Action Replay](https://www.pokebip.com/espace-membre/blogs/129214/article/84411) | Active — extraits | 3 programmes attribués |
| 59 | [Square Palace — codes Secret of Mana](https://squarepalace.com/encyclopedies/secretofmana/cheat-codes-action-replay) | Active — extraits | 8 programmes attribués |
| 60 | [Weed Sheet — Sly Cooper](https://github.com/zzamizz/weed-sheet) | Active — partielle | 255 programmes attribués |
| 61 | [XoEVOoX Pokémon FireRed codes](https://github.com/xoevoox/pokemon-fire-red-codes) | Active — extraits | 6 programmes attribués |
| 62 | [TylerD007 — The Shiny Pokémon Code Repository](https://github.com/TylerD007/The_Shiny_Pokemon_Code_Repository) | Active — extraits | 1 programmes attribués |
| 63 | [Cemu Community Graphic Packs — sous-ensembles Cheats](https://github.com/cemu-project/cemu_graphic_packs) | Non publiée | 0 programme dans les packs |
| 64 | [Kodewerx — contributions de codes](https://www.kodewerx.org/forum/viewtopic.php?f=18&t=2763&view=print) | Active — extraits | 3 programmes attribués |
| 65 | [r/Gameshark — îles événementielles Pokémon Emerald, 12 chiffres](https://www.reddit.com/r/Gameshark/comments/1804kz6/all_the_event_islands_for_pokemon_emerald_have/) | Active — extraits | 1 programmes attribués |
| 66 | [DeltaCore — tableur public All Cheat Codes](https://github.com/rileytestut/DeltaCore/wiki/Cheats) | Active — partielle | 871 programmes attribués |

## Adaptations examinées avant de retenir ou d’exclure

| Famille | Travail effectué et limite conservée |
|---|---|
| RetroArch CHT | Descriptions multiligne reconnues ; une erreur de champ invalide le programme concerné sans faire perdre ses voisins complets. Aucun code ou guillemet manquant reconstitué par supposition. Les handlers mémoire/rumble restent distincts des codes natifs. |
| PS1 / Beetle | Écritures simples conservées dans l’ordre ; conditions et répétitions limitées à la grammaire démontrée et gardées atomiques. Les appels bornés n’autorisent pas à couper une condition de son écriture. |
| MiSTer | Analyse des familles de l’archive ; conversions NES de substitutions de lecture ROM, PS1 de RAM et branches limitées, GBA d’écritures RAM démontrées. Pas d’équivalence générale offset RAM = adresse CPU, ni de conversion des autres familles par simple renommage. |
| GBA / mGBA | Vrais parseurs AUTO/VBA et boucle d’entrée vérifiés. La syntaxe VBA RAM évite l’état de chiffrement CodeBreaker ; les programmes AUTO marqués `mgba_auto_isolated` imposent l’isolation documentée. Les masters et paramètres ne sont pas retirés pour faire accepter un programme. |
| NES / Mighty Mo | Groupes multiparties reconstitués uniquement si ordre et indices sont complets ; doublons d’indices ou groupes mélangés exclus. |
| SNES BML | Jointure à la base primaire par SHA256 dans le schéma exact de cartouche ; aucune déduction du système par l’adresse seule. |
| XML OpenEmu | Alias de système vérifiés dans la source primaire ; MD5 conservé dans le schéma `openemu-md5-unspecified`, sans substitution par une empreinte ROM supposée. Les éditions restent des candidats à confirmer. |
| FBNeo | Voie INI native, préservant driver et choix CPU/adresse/valeur, importée désactivée. Le callback libretro vide n’est pas présenté comme un moteur de codes. |
| RPCS3 / Artemis | Portages YAML auteurs, PPU répétés, ancres et chargements statiques examinés ; rapprochements NCL exacts ajoutés comme provenance seulement. Valeurs configurables non choisies exclues. |
| Dolphin | Programmes Gecko et Action Replay complets ; blocs AR chiffrés retenus uniquement après déchiffrement avec le décodeur épinglé et validation des dépendances. |
| PicoDrive / PCE / WonderSwan | Parseurs livrés et écritures réelles audités ; programmes complets prévalidés. Les écritures indépendantes peuvent être regroupées en appels bornés lorsque l’append et leur ordre sont démontrés. Aucune adresse ROM ambiguë convertie en RAM. |
| CheatDevicePS2 | Conversion structurelle RAW vers PNACH étudiée ; absence de correspondance suffisamment précise entre titre source, CRC, série et région : pas d’identité inventée. |
| 3DS / Dreamcast / MAME XML | Voies réellement livrées examinées : Azahar sans callback utilisable, Flycast/MAME requis absents ou interprétation manquante. Un nouveau nom de format ne rend pas ces données exécutables. |

Ces vérifications portent sur les données, les parseurs, les adaptateurs, la mémoire et les limites documentées. Elles ne revendiquent pas une validation physique de chaque cheat dans chaque jeu ni de toutes les combinaisons de programmes.

FBNeo : la table réelle du core livré exclut 107 romsets absents et leurs 1 344 programmes. 59 087 programmes FBNeo restent publiés ; aucun alias de driver n’est déduit d’une ressemblance de nom.

## Motifs détaillés de non-publication dans les sources partielles

Les codes de diagnostic permettent de retrouver la décision exacte dans l’audit. Ils peuvent compter plusieurs motifs pour un même programme ; leurs compteurs ne s’additionnent pas en un nombre de programmes uniques.

| Source | Motif de rejet | Diagnostic | Occurrences |
|---|---|---|---:|
| 1 — Libretro Database | Dialecte ou système sans profil natif compatible | `dialect-not-implemented` | 242 |
| 1 — Libretro Database | Instruction malformée | `malformed-instruction` | 99 001 |
| 1 — Libretro Database | Instruction RAM PCE malformée | `malformed-pce-raw-instruction` | 2 |
| 1 — Libretro Database | Handler mémoire RetroArch distinct du canal de codes natifs | `memory-handler-not-enabled` | 2 142 |
| 1 — Libretro Database | Condition ou répétition N64 sans instruction suivante | `n64-program-ends-with-orphaned-condition-or-slide` | 20 158 |
| 1 — Libretro Database | Programme DS complet dépassant le tampon natif | `program-exceeds-1023-byte-ds-core-boundary` | 477 |
| 1 — Libretro Database | Limite ou opcode du profil N64 non respecté | `program-exceeds-n64-adapter-boundary-or-opcodes` | 3 643 |
| 1 — Libretro Database | Programme Mega Drive hors sous-ensemble PicoDrive démontré | `program-outside-reviewed-picodrive-md-profile` | 123 |
| 1 — Libretro Database | Programme PS1 conditionnel complet trop long pour un appel atomique | `ps1-atomic-program-exceeds-255-byte-core-boundary` | 25 |
| 1 — Libretro Database | Opcode ou enchaînement PS1 hors sous-ensemble démontré | `ps1-opcode-or-control-grammar-not-in-reviewed-adapter` | 753 |
| 1 — Libretro Database | Paramètre ou référence de programme non résolu | `unresolved-parameter-or-program-reference` | 5 246 |
| 1 — Libretro Database | Champ CHT non fermé ou dupliqué dans le programme concerné | `unterminated-or-duplicate-retroarch-field` | 603 |
| 1 — Libretro Database | Adresse ou valeur WonderSwan hors profil RAM physique démontré | `wswan-address-or-value-outside-reviewed-physical-ram-profile` | 31 |
| 3 — DeadSkullzJr NDS(i) Cheat Databases | Instruction malformée | `malformed-instruction` | 13 |
| 3 — DeadSkullzJr NDS(i) Cheat Databases | Programme DS complet dépassant le tampon natif | `program-exceeds-1023-byte-ds-core-boundary` | 1 456 |
| 6 — CWCheat Database Plus | Instruction CWCheat malformée | `malformed-cwcheat-instruction` | 1 |
| 6 — CWCheat Database Plus | Instruction malformée | `malformed-instruction` | 306 |
| 6 — CWCheat Database Plus | Programme PSP complet hors limites du core | `program-exceeds-psp-core-boundary` | 33 |
| 6 — CWCheat Database Plus | Paramètre ou référence de programme non résolu | `unresolved-parameter-or-program-reference` | 116 |
| 7 — DuckStation chtdb | Instruction malformée | `malformed-instruction` | 7 618 |
| 7 — DuckStation chtdb | Programme PS1 conditionnel complet trop long pour un appel atomique | `ps1-atomic-program-exceeds-255-byte-core-boundary` | 13 |
| 7 — DuckStation chtdb | Opcode ou enchaînement PS1 hors sous-ensemble démontré | `ps1-opcode-or-control-grammar-not-in-reviewed-adapter` | 463 |
| 7 — DuckStation chtdb | Paramètre ou référence de programme non résolu | `unresolved-parameter-or-program-reference` | 10 360 |
| 9 — pcsx2_cheats_collection | Programme complet dépassant la limite native commune | `program-exceeds-shared-native-boundary` | 16 |
| 9 — pcsx2_cheats_collection | Fichier exclu : oversized or non-text program | `pcsx2_cheats_collection-6cb57b55939f47dd91a157bfb6cdc7fd157a780c/cheats/SLUS-20888_EB3AC800.pnach` | — |
| 9 — pcsx2_cheats_collection | Fichier exclu : oversized or non-text program | `pcsx2_cheats_collection-6cb57b55939f47dd91a157bfb6cdc7fd157a780c/cheats/SLUS-21263_239CF68A.pnach` | — |
| 11 — Dolphin GameSettings | Instruction malformée | `malformed-instruction` | 13 |
| 13 — GeckoArchive | Instruction malformée | `malformed-instruction` | 1 825 |
| 13 — GeckoArchive | Paramètre ou référence de programme non résolu | `unresolved-parameter-or-program-reference` | 29 468 |
| 13 — GeckoArchive | Fichier exclu : 'charmap' codec can't decode byte 0x81 in position 13: character maps to <undefined> | `GeckoArchive-d465c2190d32f954056dd1e6ba68a2ec3fc588ff/codes/WFGJ.txt` | — |
| 15 — FBNeo cheats | Bloc FBNeo sans contrat d’import natif désactivé attesté | `fbneo-native-disabled-import-contract-not-established` | 394 |
| 15 — FBNeo cheats | Romset absent de la table de drivers du binaire FBNeo livré | `fbneo-romset-absent-from-delivered-driver-table` | 1 344 |
| 16 — Project64 Cheats | Dialecte ou système sans profil natif compatible | `dialect-not-implemented` | 1 |
| 16 — Project64 Cheats | Condition ou répétition N64 sans instruction suivante | `n64-program-ends-with-orphaned-condition-or-slide` | 3 |
| 16 — Project64 Cheats | Limite ou opcode du profil N64 non respecté | `program-exceeds-n64-adapter-boundary-or-opcodes` | 56 |
| 16 — Project64 Cheats | Paramètre ou référence de programme non résolu | `unresolved-parameter-or-program-reference` | 2 163 |
| 17 — Mupen64Plus database | Condition ou répétition N64 sans instruction suivante | `n64-program-ends-with-orphaned-condition-or-slide` | 3 |
| 17 — Mupen64Plus database | Limite ou opcode du profil N64 non respecté | `program-exceeds-n64-adapter-boundary-or-opcodes` | 38 |
| 17 — Mupen64Plus database | Paramètre ou référence de programme non résolu | `unresolved-parameter-or-program-reference` | 1 560 |
| 18 — Mesen2 CheatDb | Instruction malformée | `malformed-instruction` | 1 253 |
| 19 — Snes9x cheats.bml | Dialecte ou système sans profil natif compatible | `dialect-not-implemented` | 13 945 |
| 21 — Artemis Patch Collection RPCS3 | Valeurs configurables RPCS3 non choisies | `rpcs3-configurable-values-require-selection` | 13 |
| 29 — Pokémon France / PokéLord | Région et révision de la source non établies | `source-region-and-revision-not-explicit` | 4 |
| 37 — MiSTer Cheats | Dialecte ou système sans profil natif compatible | `dialect-not-implemented` | 45 981 |
| 37 — MiSTer Cheats | Choix ou modificateur MiSTer non attesté | `mister-modifier-selection-not-attested` | 66 131 |
| 37 — MiSTer Cheats | Programme PS1 complet dépassant la limite de l’adaptateur | `program-exceeds-8192-byte-ps1-adapter-boundary` | 3 |
| 37 — MiSTer Cheats | Programme GBA VBA complet hors limites du profil | `program-exceeds-gba-vba-core-boundary` | 2 |
| 37 — MiSTer Cheats | Programme PS1 conditionnel complet trop long pour un appel atomique | `ps1-atomic-program-exceeds-255-byte-core-boundary` | 273 |
| 42 — LunaMoo PPSSPP workarounds | Instruction CWCheat malformée | `malformed-cwcheat-instruction` | 1 |
| 42 — LunaMoo PPSSPP workarounds | Instruction malformée | `malformed-instruction` | 5 |
| 43 — TAbdiukov PPSSPP patches | Instruction malformée | `malformed-instruction` | 216 |
| 46 — skyzyx OpenEmu cheat database | Instruction malformée | `malformed-instruction` | 381 |
| 46 — skyzyx OpenEmu cheat database | Programme GBA complet hors limites du core | `program-exceeds-gba-core-boundary` | 1 |
| 46 — skyzyx OpenEmu cheat database | Limite ou opcode du profil N64 non respecté | `program-exceeds-n64-adapter-boundary-or-opcodes` | 2 |
| 53 — Mighty Mo's Cheat Code Pack | Index de partie dupliqué | `duplicate-multipart-index` | 110 |
| 53 — Mighty Mo's Cheat Code Pack | Programme multipartie incomplet ou mélangeant plusieurs groupes | `incomplete-or-mixed-multipart-program` | 462 |
| 53 — Mighty Mo's Cheat Code Pack | Instruction malformée | `malformed-instruction` | 2 |
| 53 — Mighty Mo's Cheat Code Pack | Programme complet hors limites du core | `program-exceeds-core-boundary` | 1 |
| 54 — dillonhafer OpenEmu cheats-database.xml | Instruction malformée | `malformed-instruction` | 1 |
| 54 — dillonhafer OpenEmu cheats-database.xml | Transposition Action Replay Sega 8 bits non démontrée | `sega8-actionreplay-mapping-to-reviewed-native-channel-not-proved` | 16 |
| 54 — dillonhafer OpenEmu cheats-database.xml | Paramètre ou référence de programme non résolu | `unresolved-parameter-or-program-reference` | 10 |
| 60 — Weed Sheet — Sly Cooper | Programme complet dépassant la limite native commune | `program-exceeds-shared-native-boundary` | 2 |
| 60 — Weed Sheet — Sly Cooper | Fichier exclu : oversized or non-text program | `weed-sheet-7dedab5f6ca43beff14a0f5fac6d353337d62b06/mods/advantage/sly2/put_down_the_popcorn/07652DD9.put_down_the_popcorn.pnach` | — |
| 60 — Weed Sheet — Sly Cooper | Fichier exclu : oversized or non-text program | `weed-sheet-7dedab5f6ca43beff14a0f5fac6d353337d62b06/mods/cosmetic/sly2/darkness_mod/07652DD9.darkness_mod.pnach` | — |
| 60 — Weed Sheet — Sly Cooper | Fichier exclu : oversized or non-text program | `weed-sheet-7dedab5f6ca43beff14a0f5fac6d353337d62b06/mods/maps/sly2/subway_coopers/15DD1F6F.subway_coopers.pnach` | — |
| 65 — r/Gameshark — îles événementielles Pokémon Emerald, 12 chiffres | Variante française non attestée et paramètres non résolus | `french-effect-and-core-dialect-not-executed;parameters-require-resolution` | 4 |
| 66 — DeltaCore — tableur public All Cheat Codes | Version du dialecte GBA non établie | `gba-dialect-version-not-established` | 70 |
| 66 — DeltaCore — tableur public All Cheat Codes | Instruction malformée | `malformed-instruction` | 2 |
| 66 — DeltaCore — tableur public All Cheat Codes | Paramètre ou référence de programme non résolu | `unresolved-parameter-or-program-reference` | 3 |

## Traçabilité et régénération

Les URL d’origine sont cliquables dans l’inventaire. Les révisions complètes, SHA256, licences déclarées, portées et décisions de publication restent dans [le verrou des sources](../tools/cheats/unified-sources.json) et [l’audit généré](../native/cheats/catalogue/audit.json.gz). Les notices et droits des auteurs d’origine sont conservés ; une licence non précisée dans une source n’est pas présentée comme une autorisation générale.

Les programmes conservent leur provenance, leurs dépendances et les données originales utiles à l’audit. `provenance.import_source_id` identifie le producteur de normalisation, distinct de l’attribution `source_id`. Un CRC de domaine inconnu conservé dans `source_identities` n’est pas promu en identité utilisée pour la correspondance.

Génération sans recherche réseau et sans modification des packs :

```sh
python3 tools/cheats/unified_sources_document.py --final
```

SHA256 du manifeste compressé figé : `cf8959bfd6b20b4ef2516e1e235723b1a5048b2fc2c98033d05ad0d48cf84e57`.
