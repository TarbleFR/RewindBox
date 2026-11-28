# Décisions issues de la contre-expertise

| Série | Relecture du code livré et interactions | Décision |
| --- | --- | --- |
| 0471 | Preuve de couverture avant suppression du load ; métadonnées du traducteur changées | Conserver. Ne pas retirer l’empreinte nécessaire ni extrapoler les bancs Apple à A18 Pro. |
| 0472–0476, 0480, 0484, 0490–0494 | Mappage, handles, quotas et instantanés sous verrou ; 0480/0490 gardent la vérification à l’insertion | Aucun défaut nouveau démontré ; conserver les corrections de concurrence et les témoins existants. |
| 0477–0478 | Optimisations des bindings Metal 3 | Pas de gain physique attribuable au backend Metal 4 observé. |
| 0479, 0495–0497, 0501, 0516 | Session scan et métadonnées RomFS ; ownership, bornes et reprise sur échec conservés | Aucun défaut démontré. Pas d’attribution du volume disque global à RomFS seul. |
| 0481–0485 | Rectangles GOB et admission mono-sous-ressource, masques DS et barrières mesh/task | Conserver les gardes ; exécution mesh Metal 4 non démontrée sur runner. |
| 0498–0500 | Remise à zéro différée par bit, tables bornées par compteurs actifs, déplacement all-far chevauchant | Pas de matérialisation anticipée nouvelle ni de motif de réversion. Plages mixtes gardent le tampon. |
| 0502–0505, 0513–0514, 0517, 0524–0529 | Gouverneur facultatif, récupération corroborée, génération et échec d’allocation des sondes | Protections conservées ; principales options prédictives/adaptatives restent opt-in. |
| 0506–0512 | Rejeu anticipé et slot libre opt-in, fin des lectures avant réemploi | Ne pas accuser des chemins désactivés par défaut. Pas de changement de synchro invitée justifié. |
| 0515 | Arrêt Metal 4 couvert sur la présentation normale | FI retournait avant cette garde ; défaut de couverture confirmé, corrigé par 0532. Aucun lien causal démontré avec FE 976. |
| 0518–0523 | Copies profondeur, plans DS, invalidation des producteurs en attente ; cache disjoint 0519 opt-in | Pas de donnée périmée démontrée, conserver les copies nécessaires et les bornes. |

## Mémoire et diagnostics

Les 39 fichiers sparse de 1 Gio et 39 936 Mio de VA ne sont pas de la RAM résidente. Le relevé « résident backend » est un proxy borné par l’empreinte processus, pas une mesure indépendante de résidence GPU. Ne pas additionner les 9 882 Mio déclarés par Metal à l’empreinte physique de 4 149 Mio.

La fenêtre MKW de lectures 2 080 Mio / 227 898 page-ins comporte 2 364 Mio d’écritures logiques mais 16 Mio d’écritures disque physiques. Compression, décompression et page-outs sont des compteurs système. Leur ventilation backing/RomFS/cache manque encore ; une corrélation n’identifie pas un propriétaire.

Le gouverneur a réellement reçu un avertissement mémoire avant son retour au tier 0. Il possède déjà une récupération temporisée. Les métriques présentes ne justifient pas un seuil d’éviction fondé sur la compression seule. Les cohortes de prélecture mesurent déjà leur utilité. Quotas, cache de textures et synchronisation sont conservés ; pas de réactivation de la perforation de fichiers pendant le rendu, historiquement sujette à un blocage Metal.

Un seul des trois diagnostics MKW cités chevauche un grand gel, d’environ 402,5 ms ; les deux autres ne chevauchent aucun événement >50 ms. 0530 réduit le travail d’observation, sans prétendre que les durées de diagnostic sont toutes des pauses du jeu.

## GPU, caches et attentes

`fb_report` donne des deltas, normalement sur 300 images, en Mio : MKW 1 394 snapshots / 3 562,9 Mio = 4,647 / 11,876 Mio par image ; Zelda 2 311 / 2 295,2 = 7,703 / 7,651 Mio. Ce compteur concerne le feedback couleur ; il ne mesure pas toutes les ombres ni le trafic DRAM réel.

Les 2 048 reconstructions MKW depuis archive décrivent le préchauffage, pas toutes les premières utilisations ultérieures. Une archive PSO ne fournit pas nécessairement une bibliothèque MSL exécutable. Les trois sessions n’ont aucun répertoire AIR statique ; chaque clé de base chargée est unique dans ces journaux (MKW 2 452, Zelda 1 791, FE 520). Aucune recompilation répétitive d’une même clé démontrée. Pour FE, 37,3 s de compilation cumulée se chevauchent avec le travail en fond ; seulement 0,6 ms est imputé à une compilation sur soumission dans le relevé concerné.

Les attentes MKW 8434–8436 surviennent après perte de focus ; la sélection du réveil précède un retour d’implémentation de quelques microsecondes. Aucun réveil forcé ni suppression de fence justifié. À mesurer ensuite : nouvelle scène après préchauffage, attribution de pagination, file FI, GPU et chauffe, sur trois fenêtres appariées avec cadence native et FI séparées.
