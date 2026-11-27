# Contre-expertise S2Arm · 0513–0516

Base `198a69989`, moteur `6b6a5715` et patches appliqués jusqu’à 0512. Cas revus autour du gouverneur, de la présentation Metal 4 et de l’index RomFS.

| Patch | Oubli reproduit ou identifié | Correction et contrôle |
|---|---|---|
| 0513 | Après une charge intense, un menu dont la sonde reste lente maintient le plafond facultatif. Le témoin reste plafonné sur 118 relevés légers consécutifs. Une transition système sans nouvelle sonde laisse aussi subsister l’ancienne décision. | Deux relevés réellement légers rendent les places après le maintien minimal. Les mesures manquantes restent inconnues. Le mode économie, la pression mémoire et les régimes OS inéligibles invalident aussitôt la décision lors du relevé, même sans nouvelle sonde. 3 000 cycles reproduits. |
| 0514 | L’âge était celui du callback Metal. Un résultat retardé pouvait rafraîchir artificiellement un ancien état de charge. | Utilise l’heure de soumission dans la même horloge monotone. Un résultat vieux de plus de 25 s est écarté. Le [banc](s2arm-thermal-0502-0505/thermal_bench.c) vérifie le retard et les répétitions, puis 120 000 observations bruitées. |
| 0515 | Si le GPU s’arrête pendant l’encodage, le chemin Metal 4 pouvait encore réserver un slot et transmettre le command buffer. | Vérifie la garde après encodage, avant la réservation et le couple attente/soumission du drawable. L’ordre Metal 4 attente → soumission → signal est conservé pour les images admises. [Contrat Apple](https://developer.apple.com/documentation/metal/mtl4commandqueue/waitfordrawable%28_%3A%29). |
| 0516 | Des offsets compacts pouvaient dépasser la zone des chemins et étaient acceptés à l’ouverture. | Vérifie les deux bornes à la construction de l’index, sans vérification supplémentaire dans les lectures valides. NativeAOT Linux, 0 → 4 rejets attendus sur 4 dossiers, et les 24 contrôles RomFS existants passent. |

Le contrôle Metal 4 exerce la garde C extraite du moteur et vérifie l’ordre des appels dans la fonction de présentation. Dans le modèle, 0 → 10 000 refus sur 10 000 arrêts tardifs, et 10 000 soumissions saines dans les deux versions. Il n’exécute aucun drawable réel. Metal 3 continue de traiter le refus dans son wrapper de soumission.

ASan et UBSan réussissent pour le banc thermique. La simulation à 60 intervalles admet 76 travaux facultatifs avec les correctifs, contre 102 pour le témoin. Les 51 demandes prioritaires restent admises dans les deux bras. Le changement 75 → 76 par rapport au premier garde vient de l’abandon de son état après le régime inéligible. Les mesures de l’ancien lot restent datées dans son rapport.

La ligne `direct backend: Metal 4` dans le journal identifie le backend réel sur appareil. Les résultats de cette contre-expertise n’établissent aucun changement de FPS, de chauffe ou de consommation sur A18 Pro.
