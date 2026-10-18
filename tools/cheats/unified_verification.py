"""Promote only exact complete programs accepted by pinned native decoders."""
from __future__ import annotations

import hashlib

SUPERSEDED = {
    "missing-explicit-identity", "gba-dialect-not-attested", "unreviewed-dialect",
    "action-replay-version-and-rom-revision-not-attested",
    "vba-m-unbounded-raw-rom-patch-engine-required",
    "french-effect-and-core-dialect-not-executed",
}


def digest(code):
    return hashlib.sha256(code.encode("utf-8")).hexdigest()


def apply_gba_proof(games, source_id, proof, proof_sha256):
    """No code repair, dialect-version guess, or inferred ROM identity.

    A native AUTO/VBA-channel proof applies only to the same source, title,
    label, bytes and dependency closure. Edition confirmation remains required
    when the source has no exact ROM identity. All other blockers survive.
    """
    lookup = {(p.get("source_id"), p.get("title"), p.get("name"), p.get("program_sha256")): p
              for p in proof.get("programs", []) if p.get("eligible")}
    for game in games:
        if game.get("system") != "gba" or game.get("status") == "invalid":
            continue
        if set(filter(None, game.get("reason", "").split(";"))) - SUPERSEDED:
            continue
        by_id = {p["id"]: p for p in game.get("cheats", []) if p.get("id")}
        promoted = False
        for program in game.get("cheats", []):
            if program.get("status") == "invalid" or program.get("parameters"):
                continue
            if set(filter(None, program.get("reason", "").split(";"))) - SUPERSEDED:
                continue
            record = lookup.get((source_id, game["title"], program["name"], digest(program["code"])))
            if not record or record.get("program_code") != program["code"] or record.get("dependency_ids", []) != program.get("dependencies", []):
                continue
            ordered, visiting, seen = [], set(), set()
            def visit(item):
                key = id(item)
                if key in visiting:
                    raise ValueError("cyclic dependency")
                if key in seen:
                    return
                if item.get("parameters") or item.get("status") == "invalid":
                    raise ValueError("unresolved source program")
                visiting.add(key)
                for dependency in item.get("dependencies", []):
                    visit(by_id[dependency])
                visiting.remove(key); seen.add(key); ordered.append(item)
            try:
                visit(program)
            except (KeyError, ValueError):
                continue
            if digest("\n".join(p["code"] for p in ordered)) != record.get("complete_program_sha256"):
                continue
            trace = record.get("trace", {})
            if (record.get("parameters_present") or not trace.get("total")
                    or trace.get("accepted") != trace["total"] or trace.get("incomplete")
                    or trace.get("remaining_addresses") != 0):
                continue
            dialect = {"gba-auto": "gba-auto", "vba-colon": "gba-vba-raw"}.get(record.get("native_channel"))
            if not dialect:
                continue
            program.update(dialect=dialect, status="available", reason="")
            if dialect == "gba-auto":
                program["mgba_auto_isolated"] = True
            program["decoder_validation"] = {
                "proof_sha256": proof_sha256, "engine_revision": proof["engine_revision"],
                "program_sha256": record["program_sha256"], "complete_program_sha256": record["complete_program_sha256"],
                "native_channel": dialect, "gameplay_tested": False,
                "method": "Exact whole-program and dependency-closure acceptance by the pinned native decoder; AUTO retains the engine heuristic, not a claimed v1/v3 dialect",
            }
            program.setdefault("provenance", []).append({
                "url": proof["engine_repository"], "revision": proof["engine_revision"],
                "validation": "Pinned native decoder accepted every instruction and complete dependency closure",
                "proof_sha256": proof_sha256,
            })
            promoted = True
        if promoted:
            game.update(status="available", reason="")
            game.setdefault("edition_confirmation_required", not bool(game.get("identities")))
    return games
