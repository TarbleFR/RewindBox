#!/usr/bin/env python3
"""Generate the French review inventory; remain provisional until --final.

No network access, catalogue mutation, commit, or application build occurs.
The final mode reads the frozen manifest and audit; source contributions are
not added together, and provenance crosswalks are not counted as new programs.
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CURATED = {
    "gamehacking", "pokemonfrance", "ff7_fr", "ethereal", "psxdatacenter",
    "pokebip_contributions", "squarepalace", "xoevoox_firered", "tyler_shiny",
    "kodewerx_codes", "gameshark_event_islands",
}
FAMILIES = {
    "libretro": "CHT multiconsoles ; profils réellement exécutables des cores livrés, y compris les sous-ensembles PicoDrive, PCE Fast et WonderSwan audités.",
    "dsj": "Base DS/DSi : miroir historique complet vérifié de 2022, distinct de l’édition courante de l’auteur ; programmes Action Replay complets conservés.",
    "cwcheat": "Base PSP CWCheat ; programmes et conditions conservés ensemble dans le canal natif PPSSPP.",
    "duckstation": "Base PS1 CHT ; écritures GameShark et sous-ensemble conditionnel compatible avec les cores Beetle livrés.",
    "ps2device": "Archive CheatDevicePS2 analysée ; conversion RAW vers PNACH examinée, sans identité de jeu reconstruite par titre.",
    "ps2pnach": "Fichiers PS2 PNACH complets, liés au CRC exécutable ; import natif ARMSX2.",
    "pcsx2patch": "Piste PS2 de correctifs, notamment affichage et désentrelacement ; aucun export intégré à ce lot.",
    "dolphin": "GameINI GameCube/Wii : blocs Gecko et Action Replay complets ; GameID et révision restent distincts.",
    "rc24": "Ancien fournisseur GeckoCodes ; l’endpoint GameID essayé est indisponible, sans export de remplacement inventé.",
    "geckoarchive": "Archive de programmes Gecko GameCube/Wii, indexés par identifiant de jeu.",
    "pugsy": "Archive MAME XML ; son cycle d’activation et ses espaces CPU ne sont pas assimilés à ceux de FBNeo.",
    "fbneo": "INI natifs FBNeo : driver, CPU, adresses et choix préservés ; import désactivé par défaut dans la voie INI du core.",
    "pj64": "Base Project64 N64 ; paramètres, conditions et répétitions soumis au profil Mupen livré.",
    "mupen": "Base Mupen64Plus N64 ; mêmes contraintes de programme complet et d’opcodes que le moteur livré.",
    "mesen": "JSON NES/SNES ; empreintes et schémas propres à chaque système, sans rapprochement par titre seul.",
    "snes9x": "BML multiconsoles : seules les entrées reliées à la base primaire SNES par SHA256 et schéma exact sont publiables.",
    "artemis": "Provenance de blocs NCL rapprochés exactement de portages auteurs RPCS3 déjà présents ; aucun interpréteur NCL général ajouté.",
    "artemisrpcs3": "Documents YAML natifs RPCS3 ; PPU, titre, version et dépendances statiques préservés.",
    "vita1": "Archive PSV VitaCheat récupérée et épinglée ; moteur Vita absent.",
    "vita2": "Archive PSV VitaCheat récupérée et épinglée ; moteur Vita absent.",
    "switchhamlet": "Archive Switch/Atmosphère épinglée ; BuildID et moteur Switch nécessaires.",
    "edizon": "Configurations et scripts EdiZon/Atmosphère ; moteur Switch nécessaire.",
    "ibnux": "Programmes Switch/Atmosphère ; moteur Switch nécessaire.",
    "gbatemp_switch": "Miroir de contributions GBAtemp Switch ; ne constitue pas un moteur Switch dans NeoStation.",
    "switchgfx": "Correctifs Switch de performances et d’affichage ; moteur et BuildID correspondants nécessaires.",
    "sharkive": "Base GateShark 3DS récupérée ; le callback cheats du core Azahar livré est une fonction sans effet.",
    "ctrpf": "Base CTRPF/GateShark 3DS récupérée ; interpréteur CTRPF et voie d’exécution Azahar absents.",
    "mister": "Archive MiSTer auditée par famille ; seules les conversions démontrées NES, PS1 et GBA sont retenues, avec les tuples originaux préservés.",
    "lunamoo": "Programmes PSP CWCheat, dont contournements et correctifs ; nature du programme conservée.",
    "tabdiukov": "Correctifs PSP CWCheat complets ; aucune conversion en simple écriture supposée.",
    "dreamcast": "Table Flycast Dreamcast examinée : type, taille, adresse, répétitions et conditions ; aucune voie Dreamcast livrée compatible.",
    "enhancement": "Blocs Gecko/Action Replay d’amélioration GameCube/Wii ; ils restent identifiés comme correctifs ou améliorations.",
    "openemu_personal": "XML OpenEmu multiconsoles épinglé ; MD5 de domaine non établi conservé comme opaque, avec confirmation d’édition requise, sans l’assimiler au MD5 d’une ROM complète.",
    "mighty_mo": "Pack NES/Nestopia XML ; parties d’un même programme réunies seulement lorsque leur ordre et leur complétude sont attestés.",
    "dillonhafer_xml": "XML OpenEmu ; alias officiel sg/Mega Drive vérifié, MD5 opaque et édition à confirmer. La provenance peut recouper les autres bases.",
    "squarepalace": "Extraits PAR Secret of Mana ; édition non attestée : candidats à confirmer, sans région, langue ou révision inventée.",
    "weed_sheet": "PNACH Sly Cooper PS2 complets ; catégories gameplay, correctifs et modifications conservées.",
    "delta_workbook": "Tableur public complet épinglé ; programmes mGBA AUTO/VBA vérifiés, lignes malformées et variantes non résolues exclues.",
    "cemu_gameplay_packs": "Packs Cemu Wii U récupérés ; règles et correctifs PowerPC nécessitant un moteur Wii U absent.",
}
EXCLUSIONS = {
    "sharkive": "Adaptation examinée : callbacks Azahar set/reset immédiatement RET, sans API CheatEngine exploitable. Renommer GateShark ne permet pas son exécution.",
    "ctrpf": "Adaptation examinée : même absence de voie cheats Azahar, avec en plus des opcodes CTRPF exigeant leur interpréteur propre.",
    "ps2device": "Conversion RAW 0/1/2 vers PNACH possible structurellement, mais aucun rapprochement sûr CRC exécutable + série + région n’a été établi avec le GameIndex ARMSX2. Aucun identifiant inventé.",
    "pcsx2patch": "Export structuré non récupéré pour cette intégration ; correctifs grand écran ou désentrelacement non présentés comme des cheats gameplay supplémentaires.",
    "pugsy": "MAME2003 Plus absent des cores livrés ; cycle de vie, périphériques et espaces CPU du XML non transposables au parseur INI FBNeo par simple renommage.",
    "vita1": "Pas de moteur Vita ni de plugin VitaCheat et de modèle mémoire correspondant dans NeoStation.",
    "vita2": "Pas de moteur Vita ni de plugin VitaCheat et de modèle mémoire correspondant dans NeoStation.",
    "switchhamlet": "Pas de moteur Switch ; interpréteur Atmosphère et BuildID exact nécessaires.",
    "edizon": "Pas de moteur Switch ; scripts et programmes mémoire EdiZon/Atmosphère non exécutables par les moteurs présents.",
    "ibnux": "Pas de moteur Switch ; programmes mémoire Atmosphère exclus des packs actifs.",
    "gbatemp_switch": "Pas de moteur Switch ; un miroir de programmes ne fournit pas l’interpréteur nécessaire.",
    "switchgfx": "Pas de moteur Switch ; correctifs liés à un BuildID et à un moteur absents.",
    "dreamcast": "Adaptation examinée : Flycast absent des cores livrés et aucune transposition préservant les conditions, tailles et répétitions n’est attestée.",
    "cemu_gameplay_packs": "Pas de moteur Wii U/Cemu ; règles et patches PowerPC non exécutables par Dolphin.",
    "rc24": "L’endpoint précis essayé répond HTTP 404 ; aucun export structuré récupéré. Les sources Dolphin et GeckoArchive servent de voies distinctes.",
}
REJECT_LABELS = {
    "dialect-not-implemented": "Dialecte ou système sans profil natif compatible",
    "malformed-instruction": "Instruction malformée",
    "memory-handler-not-enabled": "Handler mémoire RetroArch distinct du canal de codes natifs",
    "n64-program-ends-with-orphaned-condition-or-slide": "Condition ou répétition N64 sans instruction suivante",
    "program-exceeds-1023-byte-ds-core-boundary": "Programme DS complet dépassant le tampon natif",
    "program-exceeds-n64-adapter-boundary-or-opcodes": "Limite ou opcode du profil N64 non respecté",
    "ps1-atomic-program-exceeds-255-byte-core-boundary": "Programme PS1 conditionnel complet trop long pour un appel atomique",
    "ps1-opcode-or-control-grammar-not-in-reviewed-adapter": "Opcode ou enchaînement PS1 hors sous-ensemble démontré",
    "unresolved-parameter-or-program-reference": "Paramètre ou référence de programme non résolu",
    "unterminated-or-duplicate-retroarch-field": "Champ CHT non fermé ou dupliqué dans le programme concerné",
    "malformed-cwcheat-instruction": "Instruction CWCheat malformée",
    "program-exceeds-psp-core-boundary": "Programme PSP complet hors limites du core",
    "program-exceeds-shared-native-boundary": "Programme complet dépassant la limite native commune",
    "fbneo-native-disabled-import-contract-not-established": "Bloc FBNeo sans contrat d’import natif désactivé attesté",
    "fbneo-romset-absent-from-delivered-driver-table": "Romset absent de la table de drivers du binaire FBNeo livré",
    "rpcs3-configurable-values-require-selection": "Valeurs configurables RPCS3 non choisies",
    "source-region-and-revision-not-explicit": "Région et révision de la source non établies",
    "source-region-revision-and-identity-not-explicit;missing-explicit-identity": "Région, révision et identité explicite absentes",
    "mister-modifier-selection-not-attested": "Choix ou modificateur MiSTer non attesté",
    "program-exceeds-8192-byte-ps1-adapter-boundary": "Programme PS1 complet dépassant la limite de l’adaptateur",
    "program-exceeds-gba-vba-core-boundary": "Programme GBA VBA complet hors limites du profil",
    "duplicate-multipart-index": "Index de partie dupliqué",
    "incomplete-or-mixed-multipart-program": "Programme multipartie incomplet ou mélangeant plusieurs groupes",
    "program-exceeds-core-boundary": "Programme complet hors limites du core",
    "program-exceeds-gba-core-boundary": "Programme GBA complet hors limites du core",
    "gba-dialect-version-not-established": "Version du dialecte GBA non établie",
    "french-effect-and-core-dialect-not-executed;parameters-require-resolution": "Variante française non attestée et paramètres non résolus",
    "program-outside-reviewed-picodrive-md-profile": "Programme Mega Drive hors sous-ensemble PicoDrive démontré",
    "program-exceeds-99-native-call-boundary": "Plus de 99 appels natifs nécessaires au programme complet",
    "malformed-pce-raw-instruction": "Instruction RAM PCE malformée",
    "program-exceeds-pce-batched-input-boundary": "Programme PCE complet dépassant la borne des entrées regroupées",
    "pce-address-outside-reviewed-main-or-cd-ram-profile": "Adresse PCE hors RAM principale ou RAM CD démontrée",
    "wswan-address-or-value-outside-reviewed-physical-ram-profile": "Adresse ou valeur WonderSwan hors profil RAM physique démontré",
    "program-exceeds-wswan-128-write-single-call-boundary": "Programme WonderSwan dépassant 128 écritures dans un même appel",
    "malformed-vba-address-value-program": "Programme VBA adresse/valeur malformé",
    "vba-address-width-not-in-reviewed-ram-or-rom-profile": "Adresse ou largeur VBA hors profil RAM/ROM démontré",
    "malformed-pnach-program": "Programme PNACH malformé",
    "missing-validated-native-rpcs3-document": "Document natif RPCS3 validé manquant",
    "rpcs3-document-must-contain-one-complete-patch": "Document RPCS3 ne contenant pas un patch complet autonome",
    "rpcs3-incomplete-patch-or-game-scope": "Patch RPCS3 incomplet ou portée de jeu insuffisante",
    "sega8-actionreplay-mapping-to-reviewed-native-channel-not-proved": "Transposition Action Replay Sega 8 bits non démontrée",
    "activation-adapter-not-yet-reviewed": "Adaptateur d’activation non démontré",
    "parameter-selection-required": "Valeur d’un paramètre restant à choisir",
    "missing-or-ambiguous-program-dependency": "Dépendance manquante ou ambiguë",
    "cyclic-program-dependency": "Cycle dans les dépendances de programmes",
    "complete-dependency-group-exceeds-reviewed-adapter-boundary": "Groupe complet de dépendances dépassant les limites du profil",
    "unavailable-program-dependency": "Dépendance non publiable dans son état actuel",
}


def cell(value):
    return str(value).replace("|", "\\|").replace("\r", " ").replace("\n", " ")


def number(value):
    return f"{int(value):,}".replace(",", " ")


def read_json(path):
    data = path.read_bytes()
    return json.loads(gzip.decompress(data) if path.suffix == ".gz" else data)


def provenance_only(source):
    return source["id"] == "artemis" or "provenance-only" in source.get("publication", {}).get("adaptation_status", "")


def scope(source):
    key = source["id"]
    if key in FAMILIES:
        return FAMILIES[key]
    if key == "pokemonfrance":
        return "Extraits Rouge/Bleu français ; adresses et empreintes contrôlées sur la source primaire du désassemblage FR. Le site complet n’a pas été aspiré."
    if key in CURATED:
        return "Extraits complets sélectionnés, avec attribution d’origine ; collecte intégrale du site ou du forum non réalisée."
    if source.get("import_scope", "").startswith("reference-only"):
        return "Piste documentaire ; aucun export structuré intégré à ce lot."
    return "Instantané structuré épinglé ; seuls les programmes complets acceptés par les profils livrés sont publiables."


def reason(source, published):
    key = source["id"]
    publication = source.get("publication", {})
    if provenance_only(source):
        return "Rapprochement exact avec des documents RPCS3 déjà portés par leurs auteurs : attribution enrichie, aucun programme nouveau ajouté par ce rapprochement."
    if key in EXCLUSIONS and not published:
        return EXCLUSIONS[key]
    if publication.get("adaptation_status") == "unavailable-input":
        original = publication.get("reason", "")
        prefix = "Structured executable export not retrieved for this integration; no program bytes are invented."
        detail = original.removeprefix(prefix).strip()
        return "Export structuré non récupéré pour cette intégration ; aucun code ajouté par supposition." + (" " + detail if detail else "")
    if published:
        rejected = source.get("rejected_programs", {})
        return "Programme complet, dialecte et dépendances validés." + (" Publication partielle ; motifs de rejet détaillés ci-dessous." if rejected else "")
    if publication.get("enabled"):
        return "Aucun programme publiable dans l’instantané examiné ; les diagnostics de l’audit font foi."
    return publication.get("reason") or source.get("reason") or "Aucun programme compatible récupéré."


def status(source, active, final):
    if provenance_only(source):
        return "Provenance seule" + (" — à confirmer au gel" if not final else "")
    if not final:
        if source.get("publication", {}).get("enabled"):
            return "Publication prévue — à confirmer"
        return "Piste sans export" if source.get("publication", {}).get("adaptation_status") == "unavailable-input" else "Exclue du lot prévu"
    if source["id"] in active:
        return "Active — extraits" if source["id"] in CURATED else ("Active — partielle" if source.get("rejected_programs") else "Active")
    return "Sans export intégré" if source.get("publication", {}).get("adaptation_status") == "unavailable-input" else "Non publiée"


def contribution(source, active, final):
    if not final:
        return "Décompte attendu au gel"
    row = active.get(source["id"])
    if provenance_only(source):
        return f"{number((row or source).get('available_programs', 0))} correspondances de provenance ; 0 programme nouveau"
    return f"{number((row or {}).get('available_programs', 0))} programmes attribués" if row else "0 programme dans les packs"


def generate(root=ROOT, final=False):
    lock_path = root / "tools/cheats/unified-sources.json"
    directory = root / "native/cheats/catalogue"
    lock = read_json(lock_path)
    audit = read_json(directory / "audit.json.gz")
    rows = {row["id"]: row for row in audit["sources"]}
    assert len(lock["sources"]) == 70 and len(rows) == 70
    assert {row["research_id"] for row in lock["sources"]} == set(range(1, 71))
    assert set(rows) == {row["id"] for row in lock["sources"]}
    # A provisional document deliberately avoids reading or publishing old totals.
    manifest = read_json(directory / "manifest.json.gz") if final else None
    active = {row["id"]: row for row in manifest["sources"]} if final else {}
    assert set(active) <= set(rows)
    sources = []
    for locked in sorted(lock["sources"], key=lambda row: row["research_id"]):
        observed = rows[locked["id"]]
        assert observed["research_id"] == locked["research_id"]
        # Current publication decisions come from the lock; final observations
        # and contribution counters come from the frozen audit and manifest.
        merged = {**locked, **observed, "publication": locked.get("publication", {})}
        sources.append(merged)
    lines = ["# Sources de cheats NeoStation — inventaire avant IPA", ""]
    if final:
        totals = manifest["totals"]
        for field in ("programs", "identity_groups", "games", "cheats"):
            assert isinstance(totals.get(field), int) and totals[field] >= 0, f"Missing or invalid publication total: {field}"
        lines += [f"**Version figée du catalogue : `{manifest['revision']}`.**", "",
                  f"70 pistes documentées ; {number(len(active))} attributions de sources présentes dans le manifeste actif, provenance seule comprise.", "",
                  f"La publication contient **{number(totals['programs'])} programmes dédupliqués dans leurs groupes d’identité**, "
                  f"{number(totals['identity_groups'])} groupes d’identité, {number(totals['games'])} fiches de transport "
                  f"et {number(totals['cheats'])} enregistrements de programmes dans les packs, duplications éventuelles de dépendances entre parties comprises.", ""]
    else:
        lines += ["**Version provisoire : le gel final des données n’a pas encore été annoncé.**", "",
                  "Les 70 références et les décisions d’adaptation sont inventoriées. Les statuts de publication restent indicatifs ; "
                  "les contributions et totaux seront calculés à partir du manifeste figé. Aucun ancien total n’est repris dans cette version.", ""]
    lines += [
        "Un programme est un ensemble complet d’instructions et de dépendances activable comme un même choix. "
        "Les contributions d’une source peuvent recouper celles d’autres sources : **elles ne s’additionnent pas pour obtenir un nombre de cheats uniques**. "
        "Les groupes d’identité ne sont pas un décompte de jeux commerciaux uniques ; plusieurs régions, révisions et schémas d’empreinte restent distincts. "
        "Les fiches de transport peuvent être des parties d’un même groupe.", "",
        "Les packs proposés au téléchargement contiennent les programmes compatibles retenus. Les pistes non récupérées, les formats sans moteur "
        "et les programmes rejetés restent dans cet inventaire et dans l’audit. Le téléchargement n’active aucun cheat.", "",
        "L’action globale « Télécharger tous les catalogues » utilise [l’index unifié NeoStation](https://raw.githubusercontent.com/TarbleFR/neostation-ios/Claude/native/cheats/catalogue/manifest.json.gz). "
        "Les packs sont vérifiés avant installation ; une reprise conserve les packs déjà installés et retente ceux qui manquent."
        + ("" if final else " Dans cette version provisoire, l’URL désigne la destination de publication ; elle n’atteste pas le gel des données distantes."), "",
        "## Portée du téléchargement et reconnaissance du jeu", "",
        "La même source de téléchargement dessert les consoles RetroArch, ARMSX2, Dolphin et RPCS3, par leurs adaptateurs respectifs. "
        "La présence d’une console ou d’un core dans NeoStation n’implique pas que son callback cheats soit utilisable. "
        "Les profils exécutables et leurs limites sont détaillés dans [la matrice de compatibilité](unified-cheats-compatibility.md).", "",
        "Les éditions Europe, USA, World, langues et révisions sont conservées telles que documentées. L’empreinte, son schéma et les identifiants natifs "
        "commandent la correspondance. Un titre ressemblant ou la langue française d’un site propose au mieux un candidat ; il ne transforme pas un code USA "
        "en code FR. Une contradiction connue de région, de révision ou d’empreinte bloque l’import.", "",
        "Pour Pokémon Rouge/Bleu FR, les extraits vérifiés sont reliés aux empreintes originales du désassemblage français et à ses déclarations mémoire. "
        "Cette vérification statique ne constitue pas un test de chaque effet en jeu et ne s’étend pas automatiquement à Jaune ou à une ROM modifiée."
        + (" Chaque empreinte originale Rouge ou Bleu FR dispose de cinq programmes : quatre programmes Pokémon France nouvellement attestés pour ces éditions, plus un programme Libretro déjà existant. Ce sont cinq programmes par édition, pas cinq nouveautés ni dix effets nouveaux." if final else ""), "",
        "## Inventaire des 70 pistes", "",
        "Les numéros sont ceux de l’inventaire de recherche. « Active » signifie qu’une contribution figure dans le manifeste figé, "
        "pas que le site entier a été téléchargé ni que toutes ses entrées sont utilisables.", "",
        "| N° | Source et URL | Statut | Portée réelle ; adaptation ou exclusion |",
        "|---:|---|---|---|",
    ]
    for source in sources:
        published = source["id"] in active if final else bool(source.get("publication", {}).get("enabled"))
        linked = f"[{cell(source['name'])}]({source['url']})"
        detail = scope(source) + " " + reason(source, published)
        lines.append(f"| {source['research_id']} | {linked} | {status(source, active, final)} | {cell(detail)} |")
    lines += ["", "## Contributions effectivement présentes", ""]
    if not final:
        lines += ["Le tableau chiffré sera rempli après le signal de gel. Les compteurs d’une ancienne génération ne sont pas utilisés.", ""]
    else:
        lines += ["Chaque ligne indique une attribution de programmes à une source ; un même programme peut conserver plusieurs provenances. "
                  "ArtemisPS3 enrichit la provenance de documents RPCS3 existants et ne leur ajoute pas un second exemplaire.", "",
                  "| N° | Source | Contribution publiée | Révision de la source |",
                  "|---:|---|---|---|",
        ]
        for source in sources:
            if source["id"] not in active:
                continue
            revision = source.get("revision") or source.get("sha256") or "non fournie"
            lines.append(f"| {source['research_id']} | [{cell(source['name'])}]({source['url']}) | {contribution(source, active, final)} | `{cell(revision)}` |")
        lines.append("")
    lines += ["## Les 14 compléments : références 53 à 66", "",
              "Ces références sont une série précisément identifiée de l’inventaire ; leur présence ici n’affirme pas que les quatorze sont toutes publiées.", "",
              "| N° | Complément | Statut | Contribution |", "|---:|---|---|---|"]
    for source in sources:
        if 53 <= source["research_id"] <= 66:
            lines.append(f"| {source['research_id']} | [{cell(source['name'])}]({source['url']}) | {status(source, active, final)} | {contribution(source, active, final)} |")
    lines += ["", "## Adaptations examinées avant de retenir ou d’exclure", "",
        "| Famille | Travail effectué et limite conservée |", "|---|---|",
        "| RetroArch CHT | Descriptions multiligne reconnues ; une erreur de champ invalide le programme concerné sans faire perdre ses voisins complets. Aucun code ou guillemet manquant reconstitué par supposition. Les handlers mémoire/rumble restent distincts des codes natifs. |",
        "| PS1 / Beetle | Écritures simples conservées dans l’ordre ; conditions et répétitions limitées à la grammaire démontrée et gardées atomiques. Les appels bornés n’autorisent pas à couper une condition de son écriture. |",
        "| MiSTer | Analyse des familles de l’archive ; conversions NES de substitutions de lecture ROM, PS1 de RAM et branches limitées, GBA d’écritures RAM démontrées. Pas d’équivalence générale offset RAM = adresse CPU, ni de conversion des autres familles par simple renommage. |",
        "| GBA / mGBA | Vrais parseurs AUTO/VBA et boucle d’entrée vérifiés. La syntaxe VBA RAM évite l’état de chiffrement CodeBreaker ; les programmes AUTO marqués `mgba_auto_isolated` imposent l’isolation documentée. Les masters et paramètres ne sont pas retirés pour faire accepter un programme. |",
        "| NES / Mighty Mo | Groupes multiparties reconstitués uniquement si ordre et indices sont complets ; doublons d’indices ou groupes mélangés exclus. |",
        "| SNES BML | Jointure à la base primaire par SHA256 dans le schéma exact de cartouche ; aucune déduction du système par l’adresse seule. |",
        "| XML OpenEmu | Alias de système vérifiés dans la source primaire ; MD5 conservé dans le schéma `openemu-md5-unspecified`, sans substitution par une empreinte ROM supposée. Les éditions restent des candidats à confirmer. |",
        "| FBNeo | Voie INI native, préservant driver et choix CPU/adresse/valeur, importée désactivée. Le callback libretro vide n’est pas présenté comme un moteur de codes. |",
        "| RPCS3 / Artemis | Portages YAML auteurs, PPU répétés, ancres et chargements statiques examinés ; rapprochements NCL exacts ajoutés comme provenance seulement. Valeurs configurables non choisies exclues. |",
        "| Dolphin | Programmes Gecko et Action Replay complets ; blocs AR chiffrés retenus uniquement après déchiffrement avec le décodeur épinglé et validation des dépendances. |",
        "| PicoDrive / PCE / WonderSwan | Parseurs livrés et écritures réelles audités ; programmes complets prévalidés. Les écritures indépendantes peuvent être regroupées en appels bornés lorsque l’append et leur ordre sont démontrés. Aucune adresse ROM ambiguë convertie en RAM. |",
        "| CheatDevicePS2 | Conversion structurelle RAW vers PNACH étudiée ; absence de correspondance suffisamment précise entre titre source, CRC, série et région : pas d’identité inventée. |",
        "| 3DS / Dreamcast / MAME XML | Voies réellement livrées examinées : Azahar sans callback utilisable, Flycast/MAME requis absents ou interprétation manquante. Un nouveau nom de format ne rend pas ces données exécutables. |", "",
        "Ces vérifications portent sur les données, les parseurs, les adaptateurs, la mémoire et les limites documentées. "
        "Elles ne revendiquent pas une validation physique de chaque cheat dans chaque jeu ni de toutes les combinaisons de programmes.", "",
        "## Motifs détaillés de non-publication dans les sources partielles", "",
        "Les codes de diagnostic permettent de retrouver la décision exacte dans l’audit. Ils peuvent compter plusieurs motifs pour un même programme ; "
        "leurs compteurs ne s’additionnent pas en un nombre de programmes uniques.", "",
        "| Source | Motif de rejet | Diagnostic |" + (" Occurrences |" if final else ""),
        "|---|---|---|" + ("---:|" if final else ""),
    ]
    if final:
        fbneo = next(source for source in sources if source["id"] == "fbneo")
        absent = fbneo.get("publication", {}).get("hardware_validation", {}).get("source_absent_driver_count")
        removed = fbneo.get("rejected_programs", {}).get("fbneo-romset-absent-from-delivered-driver-table")
        if absent is not None and removed is not None:
            insertion = lines.index("## Motifs détaillés de non-publication dans les sources partielles")
            lines[insertion:insertion] = [f"FBNeo : la table réelle du core livré exclut {number(absent)} romsets absents et leurs {number(removed)} programmes. "
                f"{number(active['fbneo']['available_programs'])} programmes FBNeo restent publiés ; aucun alias de driver n’est déduit d’une ressemblance de nom.", ""]
    for source in sources:
        for diagnostic, count in sorted(source.get("rejected_programs", {}).items()):
            label = REJECT_LABELS.get(diagnostic, "Contrat de format, d’identité ou d’activation non rempli ; voir le diagnostic exact")
            row = f"| {source['research_id']} — {cell(source['name'])} | {label} | `{cell(diagnostic)}` |"
            lines.append(row + (f" {number(count)} |" if final else ""))
        for rejected in source.get("rejected_members", []):
            # File-level diagnostics are meaningful evidence, including a bad
            # archive member; no program count is invented from their count.
            lines.append(f"| {source['research_id']} — {cell(source['name'])} | Fichier exclu : {cell(rejected.get('reason', 'entrée illisible'))} | `{cell(rejected.get('path', ''))}` |" + (" — |" if final else ""))
    lines += ["", "## Traçabilité et régénération", "",
        "Les URL d’origine sont cliquables dans l’inventaire. Les révisions complètes, SHA256, licences déclarées, portées et décisions de publication "
        "restent dans [le verrou des sources](../tools/cheats/unified-sources.json) et [l’audit généré](../native/cheats/catalogue/audit.json.gz). "
        "Les notices et droits des auteurs d’origine sont conservés ; une licence non précisée dans une source n’est pas présentée comme une autorisation générale.", "",
        "Les programmes conservent leur provenance, leurs dépendances et les données originales utiles à l’audit. "
        "`provenance.import_source_id` identifie le producteur de normalisation, distinct de l’attribution `source_id`. "
        "Un CRC de domaine inconnu conservé dans `source_identities` n’est pas promu en identité utilisée pour la correspondance.", "",
        "Génération sans recherche réseau et sans modification des packs :", "", "```sh",
        "python3 tools/cheats/unified_sources_document.py" + (" --final" if final else ""), "```", "",
    ]
    if final:
        manifest_path = directory / "manifest.json.gz"
        lines += [f"SHA256 du manifeste compressé figé : `{hashlib.sha256(manifest_path.read_bytes()).hexdigest()}`.", ""]
    else:
        lines += ["Le passage à `--final` doit suivre le signal de gel des données ; il remplit les contributions et les compteurs à partir de cette publication.", ""]
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--output", type=Path, default=Path("docs/unified-cheats-sources.md"))
    parser.add_argument("--final", action="store_true", help="Use only after the catalogue owner has frozen the data")
    args = parser.parse_args()
    output = args.output if args.output.is_absolute() else args.root / args.output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(generate(args.root, args.final), encoding="utf-8")
    print(output)


if __name__ == "__main__":
    main()
