# Récupération des dépendances MeloNX — 13 novembre 2026

Le Core745 échouait avant compilation : son archive de référence engine82 avait expiré. Le correctif récupère les éléments encore nécessaires dans les copies déjà authentifiées et republiées par les livraisons615 et732. Il ne modifie aucun adaptateur ni comportement du moteur.

## Provenance et portée

| Entrée | Copie utilisée | SHA-256 des octets originaux |
| --- | --- | --- |
| Core743, historique engine82 et LibHac | Artifact13976632507, livraison732, run43289133482 | `a5848a399d6736286b0371a023ce2d2aa32e025c86e3d5d48a86d893b0e69f52` |
| Core614, référence DMA | Artifact13150348411, livraison615, run41464449025 | `05009abfcfa45a5e5644491a52da2b08abeef8337451eb688c72a9f346f0abd5` |

Le même vérificateur de republication contrôle producteur, run, tentative, job, étape, taille et empreinte. Les75 fichiers historiques conservés sont recopiés à l'identique. La nouvelle attestation est séparée et liée au résultat final. Le paquet LibHac et les dix frameworks natifs restent vérifiés contre leurs empreintes historiques. L'archive engine82 originale et ses anciens binaires restent indisponibles : aucune reconstruction ni nouvelle validation de ces anciens binaires n'est revendiquée.

Les seules différences du contrat DMA sont ses entrées de vérification (`inputs`). Les sources préparées, contrôles, inventaires et104 gates restent identiques. Les contrats historiques et pins de livraison sont conservés.

## Vérifications exécutées

- Test de récupération :108 contrôles, avec ZIP réels et métadonnées GitHub capturées, transport simulé hors ligne ; chemins de production de préparation, LibHac, dépendances natives et référence614.
- Contrat DMA avec l'archive614 réelle :515 contrôles.
- Refus d'altération de contenu/provenance, doublons et chemins dangereux ; compilation Python et `git diff --check` réussis.
- Relecture indépendante : aucun défaut bloquant ; comparaison des archives réelles et de toutes les empreintes du contrat.

Aucune compilation Apple ni observation iPhone nouvelle. Ces contrôles ne remplacent pas l'exécution de la CI du Core745. Les copies republiées ont90 jours de rétention, elles ne constituent pas un archivage permanent.

## Remise

Intégrer le SHA exact remis dans l'issue179, vérifier/regeler le contrat courant, lancer une seule CI du Core745, épingler son résultat vérifié puis reprendre l'IPA733. Le propriétaire principal garde la livraison. Ne pas relancer les104 tests de préparation uniquement à cause du transport si leurs sources, paramètres et reçus restent identiques ; refaire les vérifications affectées et le contrat complet.
