# RPCS3 — relecture des journaux iPhone 586 et de l'historique 581–585

| Jeu | Build et Core | Problème observé | Preuves et comparaison historique | Cause et confiance | Correction | Validation restante |
| --- | --- | --- | --- | --- | --- | --- |
| Black Ops II, BLES01717 | IPA 586, marqueur du Core 587 ; profil relâché appliqué | Pauses de plusieurs secondes, cadence variable, pression mémoire | 50 fenêtres complètes : `wl_putllc=0:0.000:0.000`. En 583/585, ces acquisitions et les attentes PPU étaient importantes. En 586 : compilations SPU à froid et pipelines Metal bloquants | L'ancienne contention ciblée est absente : confiance forte. Compilation pendant les pauses : forte. Coût causal de la pression mémoire et limitation résiduelle à chaud : non établis | Conserver le profil 587. Aucun nouveau correctif moteur implémenté par cette revue | Second passage dans le même mode et les mêmes zones, caches conservés ; vérifier le rendu et le fonctionnement avec les réservations relâchées |
| God of War III, BCES00510 | IPA 586, Core 587 attendu d'après le reçu de livraison | Démarrage puis restauration ; pas de mesures détaillées de gameplay conservées | `inherited=19 kept=0`, WCB actif, limite Auto, résolution 75 %, Mega, MT RSX. 40 puis 45 modules PPU en cache | Profil correctement hérité : forte. Effet du 587 en jeu et état de son canari : inconnus | Préserver 579/581/583/585/587, WCB et Auto. Aucun nouveau changement | Même savestate et scène que les références ; `OPT587` de ce jeu, rendement du worker et cadence invitée |
| Assassin's Creed, BLES00158 | Historique 585 / Core 585 ; 589 déjà dans les sources, absent de cette IPA | Historique : textures 14–45 ms/image et contention des réservations | [Revue 589](rpcs3-cell589.md). Le lot actuel n'apporte pas de mesure détaillée 586 de ce jeu | Signature justifiant les changements 589 : forte sur l'historique ; bénéfice sur appareil inconnu | Déjà implémentés avant cette revue : leviers 559/573 et profil à réservations relâchées. Pas de duplication | IPA contenant réellement le 589 et son profil, puis mêmes scènes avec caches conservés |
| Dragon Ball Z Budokai HD, BLES01658 | Historique 585 / Core 585, milestones ; pas de combat détaillé récent | Aucun nouveau problème quantifiable ici | Preuve A/B 563 conservée : +1,83 FPS médians et −1,67 ms d'attente de read-back/image, pour les scènes de cette preuve | Acquis documenté ; pas de nouvelle mesure comparable | Préserver la soumission anticipée permanente depuis 565 | Une scène de combat normale si un nouveau problème est signalé ; aucun nouvel A/B permanent |
| Bladestorm, BLES00113 | Historique 583/585 ; pas de nouvelle mesure détaillée 586 | Historique : 30 FPS stables, à-coup après sauvegarde d'état | [Revue 589](rpcs3-cell589.md) : 348 programmes SPU compilés après la sauvegarde, une image à 593 ms. Les milestones corroborent les boots/restaurations | Compilation et pause corrélées dans la preuve antérieure. Un plateau ne démontre pas à lui seul la limite interne du jeu ni une possibilité de 60 FPS | Préserver les leviers 575 ; pas de nouveau correctif attribué à ces fichiers | Seulement une nouvelle scène comparable en cas de régression |
| Two Worlds II GotY, BLES01484 | Lancement dans l'historique applicatif ; Build et Core de ce lancement non identifiables ici | Aucun nouveau problème mesurable | Pas de fenêtre détaillée attribuable à ce titre dans les fichiers conservés | Indéterminée | Aucune transposition de levier d'un autre jeu | Une session identifiable si ce titre doit être corrigé |

Revue du 28 octobre 2026, sources de `Claude` à `700db785608f3fb1b7d1489776a62ca9a3969371`.
La capture fournie par le mainteneur résume la revue 585 ; elle ne décrit pas les mesures 586. Les empreintes des cinq fichiers reçus, les références de lignes et les extraits numériques retenus sont dans [la preuve JSON](evidence/rpcs3-device586-review.json). Aucune donnée d'exécution n'a été ajoutée à l'application.

## Référence réellement disponible

Les milestones mélangent les processus 42414 (581), 43114 (583), 44032, 44754, 44952, 45096 (585), puis 45405 (586). L'app.log est lui aussi historique. En revanche, les deux journaux de performances détaillées conservés et NeoSwap portent le processus **45405 / build 586**. Le fichier performance commence au milieu de la fenêtre 3:3 ; ses compteurs incomplets ne sont pas ajoutés aux totaux des 50 rapports complets suivants.

Le reçu [rewind586-delivery.json](evidence/rewind586-delivery.json) lie l'IPA à :

- Livraison `ef909b8`, run `40774769488`, IPA SHA-256 `d0f86d93e2487a08cf5043f348a2ff5559b26eb7ba8b9b57195a59181ca43b25`.
- Core 587 `a8a7ce1072c189806f4ddf70552280b3e95a1e17`, run `40718679248`, SHA-256 `c638d4ce331afe1d0fbc5fe6695c0e65986ff43d5ec52f08c210651050c200e8`.
- Identités de codegen dans le reçu : PPU `a987639e9f838d1c`, SPU `d070cb361bdef607`.

Les lignes `OPT587` sont compatibles avec ce Core et excluent l'interprétation « Core 585 seulement ». **Le digest du binaire chargé n'est pas dans les logs** : son égalité exacte au reçu n'est donc pas authentifiée sur l'appareil. La version publique 0.0.10 n'est pas utilisée comme identité. Le reçu privé 586 porte lui-même 0.0.8.

Le GPU annoncé est Apple A18 Pro ; RAM physique 7 989 460 992 octets ; NeoSwap annonce iOS 27.0, build 24A5380h. Ces traces ne suffisent pas à distinguer le modèle d'iPhone. Les versions installées des jeux ne sont pas fournies. La restauration GoW3 annonce `applied_patches=0` ; l'état des patches de BO2 reste inconnu.

Dans le processus 45405 :

| Session | Titre / départ | État confirmé |
| --- | --- | --- |
| 1 | GoW3, lancement frais à 22:05:13 UTC | 40 modules PPU en cache, aucun compilé |
| 2 | GoW3, savestate | 45 modules PPU en cache, aucun compilé ; restauration finalisée |
| 3 | BO2, lancement frais à 22:07:33 UTC | 72 modules PPU en cache ; objets SPU à froid dans les fenêtres retenues |
| 4 | BO2, nouveau boot à 22:08:51 UTC | 86 modules PPU en cache ; objets SPU à froid dans les fenêtres retenues |

Les ensembles de modules BO2 diffèrent : ces deux boots ne constituent pas une preuve de second passage dans le même mode et la même scène. Le nom du mode, la sauvegarde ordinaire et la caméra sont inconnus. Ajouter une heure pour l'heure de Paris à ces dates.

`CONFIG_LAYERS` confirme :

- **GoW3** : base de données + ancien fichier complet, 19 valeurs héritées, aucune conservée contre le profil ; WCB true, WDB false, Auto, 75 %, Mega, LLVM PPU/SPU, réservations relâchées, MT RSX true, streaming asynchrone de textures false, MLAA bypass 1. Pas de nouvelle neutralisation du profil observée.
- **BO2** : base de données, pas d'ancien fichier personnalisé ; Safe, LLVM PPU/SPU, 100 %, Auto, WCB/WDB false, MT RSX false, streaming asynchrone false, **accurate_res=false**. Le profil 587 est donc réellement appliqué.
- Dans les fenêtres BO2 : `OPT559 texture_epoch=1`, worker 581/583 désactivé, soumission anticipée et write-back différé désactivés, MoltenVK asynchrone désactivé. Cela correspond au périmètre des leviers existants. `SHADERCFG536 configured=0 applied=0` indique le mode Legacy ; les compteurs différés SPU restent nuls.

## Symptômes, chemins de code et décision

### BO2 : ce que le profil 587 corrige effectivement

Chaîne : anciens à-coups avec des millions de PUTLLC à données modifiées → `RANGELOCKPROF wl_putllc` et attentes PPU élevées en 583/585 → `spu_thread::do_putllc` → acquisition exclusive en mode précis → profil `advanced.accurate_spu_reservations=false` déjà livré en 586.

Dans les **50 rapports complets conservés**, `wl_putllc=0:0.000:0.000` et `putllc_heavy=0`. Les attentes `vm_range_episode` sont nulles sauf un petit épisode à la fermeture. Le chemin relâché conserve les réservations ; les écritures ciblées n'ont plus besoin du verrou exclusif. Les millions de PUTLLC réussis ne sont pas pour autant des écritures sans effet. Les six SPU peuvent encore consommer environ quatre cœurs.

Conclusion limitée : **la contention ciblée est absente dans ces fenêtres**, conformément au mécanisme du correctif. Ce n'est ni une preuve que toutes les pauses ont disparu, ni un gain de FPS à scène identique, ni une validation complète du jeu avec les réservations relâchées.

### BO2 : pauses de compilation encore présentes

| Session:fenêtre | Intervalles invités terminés / durée du rapport | Objets SPU manqués ; temps cumulé de compilation SPU | Pipelines bloquants, nombre / total / maximum |
| --- | --- | --- | --- |
| 4:12 | 3 / 5,245 s | 1 210 ; 15,359 s sur plusieurs threads | 0 / 0 / 0 |
| 4:20 | 173 / 5,324 s | 27 ; 234 ms | 3 / 6,750 ms / 3,066 ms |
| 4:30 | 122 / 5,290 s | 99 ; 1,080 s | 1 / 552,397 ms / 552,397 ms |
| 4:36 | 32 / 5,139 s | 20 ; 244,926 ms | 11 / 4,110 s / 583,326 ms |
| 4:37 | 32 / 5,123 s | 0 ; 0 | 10 / 4,550 s / 779,234 ms |

Chaîne SPU : absence d'objets trouvés → `SPUPROF obj_hits=0`, milliers d'objets écrits → compilation LLVM synchrone des nouveaux blocs → pauses sur le premier passage. Les totaux des fenêtres complètes sont 9 668 objets manqués en session 3 et 14 641 en session 4. La fenêtre 3:3 partielle ajoute 451 manques observés, sans prétendre compléter le début de la session.

Chaîne Metal : nouveaux fragments/états → `SHADERSTALL538_EVENT`, `SHADERCOST534`, `PRESSURE547` → création de pipelines dans le backend Vulkan/MoltenVK → coût bloquant de compilation. Les compteurs de publication des shaders ne montrent pas d'échec ; les recompilations de fingerprints sont une borne sur les 64 derniers, pas une preuve d'absence de répétition sur toute la session.

Les premiers passages ont déjà cette signature dans les revues 575 et 583. Le changement de réservations du profil change aussi la clé du cache d'objets SPU : un premier passage à froid après 587 était prévu. **Il n'est pas encore démontré que le cache échoue au second passage.** La règle 5 d'AGENTS impose donc de conserver les caches et de rejouer le même mode avant de modifier ce chemin. Ni compilation SPU différée ni interpréteur de shaders ne sont réactivés.

Dans les fenêtres plus continues, BO2 conserve un coût RSX de textures : par exemple 6,773 ms/image en 4:20 et 8,741 en 4:30. Ses leviers 559/573 sont déjà actifs. Ce résidu ne justifie pas de lui imposer le worker de GoW3 : le 583 l'avait retiré de l'Automatique après un rendement faible et une charge SPU élevée. Aucune généralisation nouvelle n'est faite.

### Mémoire : pression confirmée, attribution incomplète

Six événements `ios_memory_warning` entre 22:10:46 et 22:10:57 UTC. NeoSwap mesure jusqu'à **6 455 912 016 octets d'empreinte**, **3 601 973 248 octets de ledger compressé**, et seulement **523 409 840 octets disponibles**. Le résumé de l'application, sur un échantillonnage différent, donne un pic de 6 464 136 760 octets et une marge minimale de 515 185 096 octets. Ces maxima ne sont pas additionnés.

La pression peut allonger les pauses, mais sa part n'est pas isolée. Les allocations de textures demandées observées restent au plus à 251 444 224 octets, sous le seuil de 768 MiB du levier de résidence. La hausse totale n'est donc pas une justification de ce levier pour BO2. La somme résident + compressé n'est pas l'empreinte ; les octets relais/donneurs ne doivent pas y être ajoutés une seconde fois.

Le cache de stockage des shaders de NeoSwap est inactif pour ce titre (`unsupported_title`). L'activer sans preuve d'attribution ne résoudrait pas automatiquement plusieurs gigaoctets d'empreinte et introduirait un changement non validé. Aucun paramètre de NeoSwap n'est modifié. `thermalState=1` dans ce fichier ne prouve ni throttling ni absence de contention.

La fin comporte `donation_session_end`, `rpcs3_memory_session_end` puis le résumé de performances et la désactivation audio. `jetsamConfirmed=false`, `terminationCause=null`. C'est une fermeture observée ; **aucun crash mémoire n'est démontré**.

## Portée des mesures et vérifications effectuées

Les intervalles sont ceux des flips invités, pas le rafraîchissement de l'écran. Le nombre terminé par seconde de fenêtre et la moyenne des seuls intervalles terminés sont distincts. Exemple 4:36 : 32 intervalles terminés dans 5,139 s (environ 6,23/s), tandis que `avg_fps=21.602` décrit les intervalles déjà terminés. La longue image encore en cours est comptée dans le rapport suivant. Les p99 peuvent ainsi traverser les limites des fenêtres ; ils ne sont pas additionnés. Une médiane proche de 20 ms ne signifie pas une progression continue à 50 FPS pendant les pauses.

`gpu_time_ms=-1` est indisponible. Les valeurs de texture avec zéro image échantillonnée le sont également. `texture_hash_*` ne couvre que `hybrid_ge4096` : zéro ne veut pas dire que BO2 ne hache pas. Les temps de compilation SPU couvrent des threads concurrents. Les coûts de pipelines, leurs callbacks et les attentes parentes se recouvrent : aucune somme n'est présentée comme du temps mural économisable. Le worker BO2 est désactivé ; son temps n'est pas ajouté au temps RSX. En asynchrone, le coût de `submit` ne représenterait plus tout l'encodage ; ce mode est off dans les mesures détaillées BO2, et aucune ligne GoW3 correspondante n'est conservée.

Contrôles de cette revue : cinq empreintes d'entrée, regroupement et déduplication des fenêtres, cohérence des phases, reçu de livraison, delta canonique vérifié par son SHA-256. Huit fichiers de source ont été matérialisés et comparés aux empreintes du manifeste, dont `do_putllc`, la politique expérimentale, le hachage/préhash de textures, les chemins Vulkan et le canari. Les résultats des CI antérieures restent historiques ; aucune suite inchangée n'est rejouée.

**Changement livré par cette revue : documentation et preuve uniquement. Aucun nouveau correctif moteur, nouveau diagnostic, réglage joueur, IPA ou release.** Le Core 589 et son profil Assassin's Creed étaient déjà présents avant le début de cette revue ; ils ne sont pas attribués à ce travail et n'ont pas été mesurés dans ce lot. La dernière base de livraison vérifiée demeure la 586. Une éventuelle livraison suivante doit en dériver uniquement par son delta, conformément à AGENTS.

La seule observation supplémentaire nécessaire pour départager les pauses de premier passage d'un défaut persistant est **un second lancement du même mode de BO2, dans les mêmes zones, sans effacer les caches ni changer les réglages**. Les journaux habituels suffisent. Cela permettra de vérifier les hits SPU et la diminution des compilations Metal, puis d'isoler la limitation restante et la pression mémoire ; ce n'est pas un nouveau cycle permanent d'A/B.
