# Reprise manuelle · Thermique S2Arm · A18 Pro

- Base `5a4b9ef24`, patches 0502–0505. [Audit, banc hôte et protocole 30 min](../../docs/evidence/s2arm-thermal-0502-0505.md). Les fichiers de suivi CPU, GPU et RAM gardent leurs propres résultats.
- La politique existante garde la priorité en Fair, Serious, Critical, Low Power Mode et sous pression mémoire. Les voies d’archives et de PSO enregistrés conservent leurs règles de persistance. Le garde à partir de la sonde est optionnel, `S2A_RB_ENERGY_SPEC_GUARD=1`. L’observation seule utilise `S2A_RB_ENERGY_DIAG=1`.
- Valider la CI du moteur et les réglages individuels. Vérifier qu’un chargement utile ne se déplace pas sur le premier dessin. Sur iPhone17,2, mesurer le délai avant le régime lent et les p95/p99 à cadence native, avec et sans garde. Si la qualité, la cadence native ou une latence utile régresse, conserver le témoin pendant l’ajustement.
- Relever les réveils des travaux facultatifs, y compris la sonde et les délais de secours, puis distinguer le coût des archives, la prélecture et les workers déjà enregistrés. Toute modification du GPU, de l’ordonnancement invité ou des ressources mémoire se coordonne avec leur responsable.
- Vérifier la tête distante de `Claude` et la numérotation avant la prochaine intervention. Ne générer aucune IPA pour ce chantier.
