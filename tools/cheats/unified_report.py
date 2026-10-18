#!/usr/bin/env python3
"""Write a human-readable, deterministic inventory from the published audit."""
import argparse
import gzip
import json
from pathlib import Path


def cell(value):
    return str(value).replace("|", "\\|").replace("\r", " ").replace("\n", " ")


def report(directory):
    manifest = json.loads(gzip.decompress((directory / "manifest.json.gz").read_bytes()))
    audit = json.loads(gzip.decompress((directory / "audit.json.gz").read_bytes()))
    totals = manifest["totals"]
    active = {s["id"] for s in manifest["sources"]}
    lines = ["# Inventaire des sources de cheats NeoStation", "",
        f"Révision du catalogue : `{manifest['revision']}`.", "",
        f"{len(audit['sources'])} références documentées ; {len(active)} sources contribuent au téléchargement actif.", "",
        f"{totals.get('programs', totals['cheats']):,} programmes dédupliqués dans leurs groupes d’identité ; "
        f"{totals.get('identity_groups', 0):,} groupes d’identité ; {totals['games']:,} fiches de transport, parties comprises. "
        "Les groupes utilisent les identités typées et leurs schémas : ils ne sont pas présentés comme autant de jeux commerciaux uniques.", "",
        "Seuls les programmes complets acceptés par un adaptateur actuel, sans paramètre non résolu, sont publiés. "
        "Les dépendances restent entières et doivent tenir ensemble dans les limites du moteur. Les titres sans empreinte précise restent des candidats à confirmer. "
        "Aucun code n’est activé par le téléchargement.", "",
        "Une référence de portail ne signifie pas que tout son site a été aspiré. Les extraits GameHacking, forums et pages web sont indiqués comme tels. "
        "L’inventaire historique et les diagnostics restent séparés des packs téléchargés.", "",
        "| Source | Publication | Programmes actifs¹ | Version / empreinte | Portée documentée | Adaptation ou motif |",
        "|---|---|---:|---|---|---|",
    ]
    for source in audit["sources"]:
        publication = source.get("publication", {})
        status = "Active" if source["id"] in active else ("Indisponible / export non récupéré" if publication.get("adaptation_status") == "unavailable-input" else "Non publiée")
        name = f"[{cell(source['name'])}]({source.get('url','')})"
        revision = source.get("revision") or source.get("sha256") or "—"
        reason = publication.get("reason") or source.get("reason", "")
        if source["id"] not in active and publication.get("enabled") is not False:
            rejected = source.get("rejected_programs", {})
            reason = "Aucun programme actif après validation" + (" : " + ", ".join(f"{k} ({v})" for k,v in sorted(rejected.items())) if rejected else " ; aucune donnée exécutable récupérée")
        if source["id"] == "mister":
            scope = "Archive épinglée et 14 familles auditées ; sous-ensembles NES/PSX/GBA convertis, programmes entiers"
        else:
            scope = source.get("import_scope", "Référence auditée, sans export de codes inventé")
        lines.append("| " + " | ".join((name, status, str(source.get("available_programs", 0)), cell(revision), cell(scope), cell(reason))) + " |")
    lines.extend(["", "¹ Contribution d’une source aux programmes distincts dans chaque groupe d’identité ; les contributions peuvent se recouvrir et ne doivent pas être additionnées.", "",
        "Les conversions validées couvrent notamment MiSTer NES/PSX/GBA, le format natif FBNeo, les ancres/PPU répétés et chargements statiques RPCS3, "
        "quatre blocs Action Replay Dolphin décryptés avec le décodeur épinglé, la jointure SHA256 SNES primaire, les canaux AUTO/VBA réels de mGBA, "
        "les formats natifs PicoDrive 32X/MD, les écritures RAM PCEFast et la RAM physique WonderSwan. "
        "Les preuves AUTO individuelles imposent l’isolation indiquée par `mgba_auto_isolated` ; elles ne prouvent pas toutes les combinaisons de codes.", "",
        "Validation : parseurs, limites, intégrité SHA256, programmes complets et adaptateurs documentés. "
        "Aucun test physique de chaque effet en jeu n’est revendiqué. Les versions des sources et les diagnostics détaillés sont dans `audit.json.gz` et le verrou `tools/cheats/unified-sources.json`.", ""])
    path = directory / "SOURCES.md"
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    print(report(parser.parse_args().directory))
