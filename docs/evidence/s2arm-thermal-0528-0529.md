# Contre-expertise S2Arm · 0528–0529

Base `4e3125b5`, moteur amont `6b6a5715`, Metal 3/4.

- **0528** exige deux sondes de charge corroborées à ≤1,25× la référence avant de passer du régime lent à la récupération. Le banc reproduit la sortie prématurée de 0527 après une seule sonde rapide. La hausse qui suit cette lecture isolée conserve maintenant le quota d’un worker. Deux lectures admissibles le rouvrent. Les règles pour charge légère répétée, état OS et données périmées restent celles de la politique existante.
- **0529** rend la publication de la durée GPU atomique par rapport au changement de génération de session, pour les deux chemins de mesure. Dans l’ancien chemin, un callback qui avait franchi le premier contrôle pouvait écrire après la remise à zéro de la session. Une reproduction déterministe à partir du chemin C extrait du moteur retrouve 10 000 → 0 publications d’une ancienne durée sur 10 000 interclassements. Les deux chemins rejettent aussi une mesure Metal sans début valide ou datée dans le futur.

Le rejeu différentiel Linux termine avec 98/120 admissions facultatives en montée progressive et 103/120 sur une chute brusque avec v2 actif. Les 120/120 admissions prioritaires sont conservées sur ces deux séquences. L’avance simulée reste de 4 s sur la montée. Ces scénarios restent les mêmes que pour 0527 et ne mesurent aucun gain sur téléphone.

Les réglages publiés dans le [protocole 30 minutes](../../tools/s2arm_a18pro/thermal/README.md) gardent la prédiction et la cadence adaptative en opt-in. La correction de propriété s’applique aussi à la sonde historique.

Le [producteur iPhoneOS](https://github.com/TarbleFR/RewindBox/actions/runs/46043966034) de `491008cf` a livré le framework `15222360547`. Les trois archives moteur, préparation et données système passent le vérificateur de pin. NS2Pro a la même empreinte Mach-O que dans l’IPA 848. Observation sur iPhone à faire.
