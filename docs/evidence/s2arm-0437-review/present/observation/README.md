# Mesurer les images intermédiaires de S2Arm

La compilation standard garde les callbacks de présentation du moteur de référence. Les libellés décrivent désormais le compteur historique comme un nombre de *drawables intermédiaires confirmés*. Ce nombre peut inclure un résultat MetalFX, une répétition de l’image courante, une copie de l’image précédente ou un remplacement lors d’une coupure de scène.

Le diagnostic demande deux options distinctes. `make -C graphics/nvn S2A_RB_COMPILE_FI_STATS=1 …` ajoute le code à la bibliothèque Mac ou iOS. La variable est incluse dans l’empreinte de compilation et une compilation ordinaire ultérieure rebâtit la bibliothèque sans ce code. Dans un moteur ainsi compilé, `S2A_RB_FI_PRESENT_STATS=1` au lancement de la session arme le capteur. La compilation standard ignore ce réglage d’exécution. Le parseur reconnaît les deux formulations historiques et actuelles. Ses colonnes `midpoint_drawables_shown` et `midpoint_fps_approx` désignent bien tous les intermédiaires confirmés.

## Quatre mesures distinctes

| Mesure | Événement et dénominateur |
| --- | --- |
| Rythme invité | La ligne `rb-speed` donne les secondes invitées par seconde murale et les présentations du jeu par seconde murale. Leur quotient donne les présentations par seconde **invitée** dans cette même fenêtre si l’horloge invitée avance. Le jeu peut avoir une cadence de simulation distincte de ses demandes de présentation. |
| HUD de S2Arm | Nombre de ticks de présentation du jeu dans la dernière seconde murale. Ce ring garde un écrivain. L’affichage ou l’abandon d’un drawable n’ajoute aucun tick. |
| Présentations originales effectivement affichées | Le banc iOS existant reçoit `present_note` pour le drawable du jeu, également sur le chemin classique. Le compteur historique `real frames shown on FI path` porte uniquement sur la voie FI. |
| Insertions effectivement affichées par chemin | Dans `[rb-fi-present-v1]`, seule la colonne `displayed_metalfx` exige à la fois le succès GPU de la commande ayant sélectionné la sortie MetalFX et la confirmation d’affichage du drawable. Les répétitions `displayed_duplicate`, `displayed_previous` et `displayed_cut` sont comptées séparément. |

L’observateur réutilise le feedback de la commande et le callback d’affichage de ce même drawable. Il associe leurs résultats grâce à un identifiant unique, attribué avant la soumission. La lecture du drapeau de coupure intervient avant la réutilisation du slot 1. Le callback tardif d’une ancienne session ou d’une entrée remplacée ne peut pas modifier la ligne d’un nouveau drawable. La table de 64 entrées est allouée une seule fois pour une session armée. Un débordement compte dans `overwritten` sans bloquer la présentation.

`wall_ns` est la durée murale monotone depuis l’armement de cette génération. `confirmed_midpoint_span_s` est la distance entre le plus ancien et le plus récent `presentedTime` positif et fini effectivement classés. Ce span n'est pas la durée du capteur. Il est nul pour zéro ou un instant distinct. Le contrôle synthétique de `clock-fields.txt` couvre 10 s de capteur et 0,250 s entre les deux présentations confirmées. Un troisième drawable sans son feedback GPU rend ensuite le classement incomplet.

Les lignes sont cumulatives par génération. Pour une cadence sur la durée du capteur, utiliser les différences de compteurs et de `wall_ns` de cette même capture, avec des bornes complètes. Lorsque `classification_complete=0`, la cadence exacte des images générées est **inconnue**. `pending`, `overwritten`, `invalid_time` et `displayed_unknown_gpu_error` en donnent la raison. les cas classés restent des observations partielles. `failed_submit` compte les échecs avant soumission et `discarded` les drawables confirmés comme non affichés. Une capture sans drawable enregistré n’offre aucun intervalle de présentation mesuré. La fréquence du HUD, la fenêtre historique de 300 présentations et la durée du capteur peuvent avoir des bornes différentes. Le parseur ne combine aucune d’elles pour fabriquer un nombre de FPS MetalFX.

## Vérifications

Les corps de `fi_commit`, `fi_job`, `fi_count_on`, le hook faible du moteur, le compteur de ticks et le formatteur du HUD viennent de l’arbre préparé. Le harnais simule la livraison des callbacks, le statut GPU et l’horloge du HUD. Les tests vérifient des décisions et une comptabilité, sans lancer MetalFX ni produire des images de jeu.

- Clang 18.1.3, Linux x86-64, `-O2`. Les 8 558 octets de la section `.text` du harnais entier, le LLVM IR optimisé et les relocations de cette section sont identiques entre la référence et la compilation ordinaire. L’objet ordinaire ne comporte aucun symbole de l’observateur. Les libellés de production sont modifiés. Le journal du harnais ordinaire est inactif et cette comparaison ne couvre pas le binaire Apple complet. Voir `objects.txt`.
- 220 comparaisons de la référence et de l’ordinaire sur 11 scénarios, deux ordres de callbacks, les deux valeurs du réglage d’exécution et cinq passages. Le contrôle de libération existant a également passé ses 1 920 cas avec sa recette inchangée. Voir `ordinary-checks.txt` et `previous-check.txt`.
- 400 exécutions ASan et UBSan sur 20 scénarios, deux ordres, deux réglages d’exécution et cinq passages. Le corpus vérifie également le feedback GPU en erreur ou absent, l’échec d’encodage, le drawable manquant, la réutilisation d’entrées, la fin de session, les notifications simultanées et un timestamp invalide. La vérification de fuites de GNU libobjc est désactivée dans ce harnais. La libération de la table à la clôture est contrôlée explicitement. Voir `diagnostic-checks.txt` et `checks.json`.
- Six changements de réglage Make vérifient l’activation et l’invalidation de l’empreinte, y compris le retour à la compilation ordinaire. Deux lignes de journal entièrement construites vérifient l’analyse de l’ancien et du nouveau format. La fréquence par seconde invitée reste vide si le journal ne contient pas le dénominateur. Voir `make-gate.txt` et `parser-check.txt`.

Le banc de coût alterne six bras dans un ordre équilibré avec 150 000 tâches synthétiques par passage. `A` et `A2` sont la même référence. `I0` et `I1` sont la compilation ordinaire avec le réglage d’exécution coupé ou demandé. `F0` et `F1` sont la compilation diagnostic désarmée ou armée. Les durées murales et CPU du thread incluent l’exécution du code hôte et des faux callbacks. Elles excluent les calculs GPU et les sorties du journal sur disque. `timing.csv` contient les mesures par bras et `timing.txt` les médianes et comparaisons appariées. L’identité des instructions de l’ordinaire apporte une preuve plus directe de l’absence de code de l’observateur sur cette voie qu’une petite variation chronométrée. L’impact sur iPhone reste non mesuré.

Sur 24 blocs équilibrés, la médiane CPU du job synthétique vaut 723 ns pour la référence, 728 ns pour la compilation ordinaire, 735 ns pour le moteur diagnostic désarmé et 788 ns pour le moteur diagnostic armé. La comparaison appariée de l’ordinaire à la référence donne −0,18 % (intervalle bootstrap à 95 % de −0,65 à +2,76 %). Dans le moteur diagnostic, l’activation ajoute +7,21 % à cette simulation CPU (de +5,15 à +8,08 %). Les mesures murales sont sensibles aux préemptions de cette machine partagée. Aucun de ces écarts ne mesure le coût sur GPU Apple.

## Reproduction

Prérequis Linux x86-64 : Python 3, Clang avec ASan/UBSan, GCC et ses headers Objective-C, GNU libobjc, BlocksRuntime, pthread et les binutils GNU. Si BlocksRuntime est installé hors des chemins habituels, `BLOCKS_PREFIX` indique le préfixe contenant `include` et `lib/x86_64-linux-gnu/libBlocksRuntime.a`. Utiliser les arbres moteur préparés avant et après le correctif. Le script accepte un arbre distinct pour les sources du HUD, si ces fichiers ne figurent pas dans la copie de travail du moteur.

```sh
python3 build.py "$REWINDBOX" "$REFERENCE" "$REFERENCE" a --objects
python3 build.py "$REWINDBOX" "$CANDIDAT" "$CANDIDAT" ordinaire --objects
python3 build.py "$REWINDBOX" "$CANDIDAT" "$CANDIDAT" diagnostic --objects --compile-stats 1
python3 verify_objects.py a ordinaire diagnostic
python3 ordinary.py a/probe ordinaire/probe
python3 cases.py diagnostic/probe diagnostic.json
python3 paired_cpu.py a/bench ordinaire/bench diagnostic/bench temps.csv --rounds 24
python3 make_gate.py "$CANDIDAT/graphics/nvn/Makefile" "$CANDIDAT"
clang -std=gnu11 -O2 -Wall -Wextra -Werror -fsanitize=address,undefined -fno-sanitize-recover=all -I"$CANDIDAT/graphics/nvn/gfx/nvn" clock_fields.c -pthread -o clock-fields
./clock-fields
python3 archive-parser-check.py "$REWINDBOX/docs/evidence/s2arm-0428/windows.py"
```
