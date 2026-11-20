# Capture 801 — analyse indépendante

## Identité et couverture

- `engine/0400C3F00006E000/host.log`, SHA-256 `1d2ecdce7386560e71ff36f594f837050942d5430bdff4972ad72dc4309c561e`.
- Session `CB7024BD-BE35-4264-BFBF-5A6D8417ECD9`, PID 12393, journal lignes 5889–5928 : préparation réutilisée 12:45:05.964 UTC, lancement passé 12:45:08.592, fermeture 12:49:57.757 le 20/11/2026. Journal lignes 5889 et 5902 : moteur run44729718541, identité graphique conservée.
- Export `preparation/CB7024BD…/identity.json` : **appBuild801**, jeu `9e244438c3d8ef1c703a6a85ef99c4f0`, génération `4b04cdfef06457bc9de63ca5901a68369d7316dfbdb147e5b15ae298bfcdbdaa.AE7674F6-5A93-4687-996B-3CF53396B51A`, graphicsRevision3. UUID ci-dessus = session/génération, pas UUID Mach-O du moteur.
- Reçu dépôt `docs/evidence/rewind801/s2arm-identity801.json` associe ce run au producteur `71ea69e8173db4db3795c8092d74f552a8e89d90`, amont `6b6a571553f7a687af46e03e2cdbf8ef4d77f335`, 165 patches. Binaire moteur signé SHA256 `635d303d296ebca38afc863f452df57d17e4af4cb7e20834866e1180c6cfb5f7`.
- UUID Mach-O du moteur relevé dans l’IPA801 : `6DEE29BF-B432-3EE8-AEB8-4E43A0448152`, distinct de la session et de la génération de préparation.
- Mario Kart World sélectionné explicitement par le journal; version1.0.0 et modèle iPhone16 Pro Max proviennent du périmètre utilisateur ; Apple A18 Pro GPU est identifié dans host:252. Host: 7619MiB RAM, écran2868×1320, OS27.0 (puce imprimée `?`), mode portable, pas de plafond S2A_FPS, FPS60 activé, écran16:9, AA None et filtre Nearest. Cache192MiB/900images confirmé host:5533. Signatures de scène1248×700/704 et parfois1920×1080; plus grande cible6144² n'est pas la résolution finale. Le multiplicateur1× n'est pas attesté continûment par l'export.
- 8 254 intervalles1..8254, aucun trou ni abandon, 273.950s. Tout le jeu est au premier plan jusqu'à la fermeture; perte de focus seulement après arrêt (host:18072). Aucun enregistrement écran dans la session (heartbeat screen captured0).
- `race_sequence_asset` =5812 intervalles2443..8254 /222.654s. Ce sont des candidats de conduite, pas des segments de circuits confirmés; aucun nom/150cc/course ne peut être déduit d'un asset seul. Les fenêtres3000..8100 évitent les premières transitions de sélection/chargement mais restent sans annotation vidéo.

## Méthode

Analyseur existant exécuté avec host exact, `--session CB7024BD-BE35-4264-BFBF-5A6D8417ECD9 --journal s2arm-journal(2).jsonl` : `metrics801.json`. Aucun profil historique fourni à cet appel. Quantiles supplémentaires au rang supérieur depuis chaque ligne cup, dans `supplement801.json`; petites différences avec les quantiles arrondis du moteur et sa fenêtre glissante sont conservées, non mélangées.

Ensemble:30.130FPS moteur; p50/p95/p99=27.674/58.943/101.904ms;92>100ms,7>200ms,1>500ms. Indice race:26.103FPS;31.297/60.130/109.917ms;79>100ms,2>200ms,0>500ms.

**Zéro compilation MSL, traduction, attente PSO ou bibliothèque dans les8254intervalles**. Préparation:5661archives réutilisées,0compilation (host:4878–4879),1171pipelines utilisés pour la première fois et0promotions/publiés (fin). Les compteurs ne montrent donc pas de compilation concurrente expliquant la conduite lente.

| Images Cup (indice de course, non annoté) | s moteur | FPS moteur | FPS affichés¹ | image p50/p95/p99 ms | CPU soumission ms/image | GPU p50/p95 ms | retards / intervalles écran connus¹ |
|---|---:|---:|---:|---|---:|---|---:|
| 3301–3600 | 10.029 | 29.912 | 29.454 | 28.642 / 56.426 / 129.573 | 7.589 | 12.22 / 20.19 | 173/298 |
| 4501–4800 | 9.598 | 31.256 | 30.719 | 29.650 / 39.891 / 122.174 | 9.891 | 12.40 / 17.95 | 202/298 |
| 5701–6000 | 7.680 | 39.062 | 39.252 | 24.075 / 30.742 / 60.313 | 5.739 | 10.84 / 15.49 | 144/300 |
| 6001–6300 | 7.691 | 39.006 | 38.614 | 24.242 / 31.456 / 47.649 | 6.429 | 11.34 / 15.21 | 143/298 |
| 6601–6900 | 16.180 | 18.542 | 18.503 | 53.698 / 62.526 / 70.469 | 9.360 | 38.43 / 41.71 | 297/300 |
| 6901–7200 | 15.685 | 19.126 | 19.144 | 52.376 / 57.638 / 101.929 | 8.079 | 36.02 / 38.36 | 287/300 |
| 7501–7800 | 17.025 | 17.621 | 17.678 | 55.023 / 65.295 / 99.909 | 10.819 | 36.71 / 42.28 | 298/300 |
| 7801–8100 | 16.876 | 17.777 | 17.730 | 56.633 / 63.050 / 72.033 | 9.902 | 39.41 / 41.72 | 299/300 |

¹ Fenêtres voisines, pas comparaison image à image : `tsummary()` précède la lecture des callbacks retardés de huit présents. Avec une présentation valide par image et une seule fenêtre, le résumé écran F3600 porte sur les intervalles rattachés à F3291..3590, tandis que Cup3301..3600 fournit le temps moteur ci-dessus. Décalage de dix images pour les autres résumés aussi. Ne pas employer la durée Cup comme durée écran connue.

CPU/GPU peuvent se chevaucher: ne pas les additionner. Les durées GPU ne sont pas des horodatages de fin avant une échéance. Plusieurs fenêtres précoces ont un GPU autour10–12ms mais une image24–32ms; les derniers passages ont GPU36–39ms. À8100,8.0pièces/image,125.8passes,1611draws; à3600,124.2passes/1188draws/7.589msCPU (799:127.8passes/2216draws/17.311ms). La charge de dessin diffère: aucune réduction799→801 attribuable à une correction sur ces seules fenêtres.

GPU fixed probe:0.243ms à3600,0.304 à6000,0.302 à6300,0.181 à6600 (transition),~0.8 à6900+; GPUbusy≈39.2%/44.3%/68–70%; thermal0 tout du long. Hypothèses concurrentes: variation de scène, contention GPU, baisse fréquence/puissance. Cette montée du probe renforce la piste fréquence/contention, mais thermal0 interdit d'affirmer une surchauffe iOS établie. Il manque les passes et une mesure fréquence/Metal corrélée. ChargeCPU d'autres processus jusqu'à41% de6cœurs à3600: association, pas preuve de cause de chaque pause.

## À-coups attribuables et limites

75/79images>100ms de l'indice race passent plus de la moitié de leur intervalle dans les SVC suivis du thread présentant;53dépassent100msSVC.62/79n'ont aucun appelRomFS terminé;59/79zéro upload. Les75cas sont compatibles avec une chaîne de dépendances invitée, pas avec une attente drawable directe.

- F5304:114.494ms, GPU9.8ms, submit+present7.7ms, attenteSVC0x34=106.842ms; clé0x76cd8df0d0, thread83, dernier réveil181.0upload/0RomFS,0.109MiBprocessus. Host:14086,14110–14112. F5835:107.265ms, GPU9.1ms, submit5.5ms, attente101.728ms, même clé/thread/waker;1faute avec lecture,0upload/RomFS. Host:14854,14865–14867. Le GPU n'explique pas à lui seul le trou; l'événement producteur et le délai réveillé→exécuté restent manquants. guest_pc=0.
- F2762:200.647ms, attente185.553ms, GPU25.6ms,0upload/RomFS mais98.062MiB lus par le processus et5977page-ins; le temps de faute du producteur n'est pas mesuré. Host:10049,10065–10067.
- F4370:189.015ms,140premiers uploads,49.7MiB,81.356msCPUupload,3480page-ins/66.922MiB disque;0reupload. F6540:138.572ms,146premiers/50.7MiB/34.525msCPU/2740page-ins. F7716:132.329ms,136premiers/49.4MiB/36.997msCPU/1310page-ins. Flushs boundary8/4/3; isolés/capacité/limite=0. Coût de transfert encore réel, patch0163 medium grouped reste0 et ne traite pas ces cas. Ne pas supprimer les dépendances ou fusionner arbitrairement les passes.
- Plus petits à-coups F3313=73.4ms:GPU19.2,59.6ms hors submit,488page-ins; F3324=56.4ms:5premiers uploads2.6MiB/8.5msCPU,496page-ins; F3354=50.1ms:17premiers4.3MiB/11.1msCPU,1039page-ins. Les détailsSVC ne sont émis que>100ms: cause exacte sous ce seuil non identifiable. Exemples complets dans `examples801.json`.
- Toutes ces lignes longframe montrent0attente display-link, present queue, drawable, submit lock et fenceGPU direct. Le GPU peut pourtant avoir retardé le producteur invité via événement; aucune preuve de suppression légitime d'une attenteSVC.

## Affichage, mémoire, audio, profils

Fenêtres écran:27,8061timestamps,0timestampindisponible signalé,8035intervalles adjacents connus,26manquants à cause notamment des29présentations écartées,4187retards. Les premiers/derniers samples ne couvrent pas tout1..8254.18fenêtres entièrement sous indice race (intervalles rattachés à2691..8090):5389timestamps,5379intervalles connus,3792retards,10manquants/11écartés; pas une course annotée. Les p50/p95 écran ne sont pas exportés; p99 seulement. Les comptes sont par délai demandé par le jeu (16.67/33.33ms), avec0.1mstolérance, le plus grand des délais des2images adjacentes.

Le temps moteur des2691..8090 vaut204.521516167s, donc1112.450retards/minute moteur correspondante. Le total des étendues écran premier→dernier horodatage reconstituées par `(timestampCount-1)/observedFPS` vaut≈203.901523s, donc≈1115.833retards/minute de cette étendue. Cette approximation utilise des FPS arrondis, inclut potentiellement des trous et exclut les raccords entre fenêtres. Aucun de ces dénominateurs n'est la somme exacte des durées d'intervalles écran connus, non exportée en801 : taux exact par minute écran connue indisponible. Résumés3600/6000/7200/8100 : p99écran150.01/83.34/100.01/83.34ms. Calculs complets privés dans`display_rates801.json`.

Dernières fenêtres entièrement à33.33msdemandées:8100=299/300tardives; sans ordre exact on peut prouver **au moins150retards consécutifs**,7800≥100,7500≥50,7200≥21,6900≥75. Aucun historique exact des séries; collecter compteur longueur courante/max et séries2+/3+ en temps constant sans écriture par image. Ne pas convertir les58msmoteur directement en nombre de vblanks ratés.

Empreinte échantillonnée pic4841MiB à3600; dernier4439 à8100; retour menu1747MiB,headroom4908,thermal0 (journal5927); départ536MiB. Aucune relance après fermeture dans cet export. Staging216MiB à3942 descend32MiB à6336. Retransferts712 depuis1500 et toujours712 en fin: aucun nouveau retransfert détecté pendant la portion race. Ne pas confondre GPUallocated≈10GiB et empreintephysique. Audio:0vrai trou dans22rapports10s adjacents à la portion race; quelques trous pendant démarrage/sélection. Cela ne valide pas subjectivement l'audio ni la vitesse de simulation/effets graphiques.

65dossiers de profils tous associés par le nom exact au host qui les a émis: **aucun de la801**. Dernier`20261120-073507-rec`:799,sessionB3AD3E7A-D036-482F-A86B-BA7B069F0316,host-20261120-073420.log:6758,signature0..582 de démarrage. Timestamp dossierEurope/Paris correspond journal06:34UTC; les noms des profils sont datés à l'export. Analyseur séparé avec session799/journal/profile exécuté dans`metrics799_startup_profile.json`; aucune validité pour coûts801. Le mainBuild/génération compatibles servent à vérifier le contexte, pas à reprendre les taux de cache ouFPS. TroisderniersCPUprofilés19nov14:00/14:01 appartiennent à04007EF01F8AE000,autrejeu. Tous les appariements dans`supplement801.json`.

**Recommandation de mesure avant gain prétendu**: captures de la même session ciblées sur une fenêtreGPU<16msavecFPS<40, sur le passageGPU36–39ms sans compilation, et sur unSVC0x34>50ms (producteur/wake→run/PC). Ajouter coût par catégorieCPU/passGPU, horodatages completsprésentation et séries d'échéances. ANE reconstruction ne peut être validé ici: aucune expérience pixels A/B et aucune passe dominante isolée. Une résolution réduite ne traite niSVC ni coûtCPU, et masquerait la qualité1× sans preuve.


## Implémentation et revue 0166–0168

Trois réutilisations exactes, chacune désactivable séparément : métadonnées d'adresses UBO résidentes (6×16 entrées, génération des pools, adresse normalisée), identifiant Metal déjà enregistré de la même vue, constantes push comparées lors du rejeu avant invalidation des arguments. Données invitées, shadows, bornes et générations d'arène restent contrôlées. Aucun gain en millisecondes extrapolé du nombre de recherches : les 5,7–10,8 ms de CPU total par image sont un plafond, pas le gain. La résidence, au plus 0,09–0,28 ms/image dans les fenêtres examinées, est secondaire.

Contre-revue : invalidation, durée de vie, contenu différé, horloges, réinitialisation entre sessions. Les compteurs sont publiés hors chemin chaud et l'état de capture est réinitialisé après drainage. Une durée GPU courte n'est pas une preuve de fin avant échéance. Les compteurs sont cumulatifs individuellement cohérents, pas un snapshot groupé ; la première fenêtre après relance peut inclure le reliquat antérieur.

L’analyseur conserve conditionnellement les nouvelles distributions écran, durées couvertes, séries, échéances déduites et compteurs de binding/push. Les traces de fin GPU sont comparées au précédent affichage plus le plus grand hold invité adjacent/60 : **pas à l’échéance drawable réellement demandée**. Au plus huit traces tardives par fenêtre ; aucune complétude supposée. Le nouvel analyseur exécuté sur le host801 avec session/journal identiques produit un JSON identique octet pour octet à l’ancien. Aucun champ168 absent n’est reconstruit artificiellement.

Le poste dominant suivant nécessite une mesure physique : passe GPU devenue lente contre variation de fréquence/puissance ou contention ; producteur du SVC 0x34 contre délai de reprise. La prochaine IPA capture au plus trois images GPU de fenêtres 3D durablement lentes, sans profiler CPU ni signatures lourdes. Les images capturées peuvent être perturbées et ne prouvent pas un gain. Les attentes >=50 ms rapportent le producteur et les étapes de reprise, quatre par dix secondes / 512 par session. La sonde GPU n'écrit plus 16 384 threads dans 1 024 cellules : son niveau absolu après correction n'est pas comparable à 801, sa variation interne à une session reste exploitable.

Les 0163–0165 sont déjà présents. Aucun retransfert supplémentaire après l'image 1500. Cache de 192 Mio, historique personnel et caches compatibles conservés. Aucune barrière supprimée sans preuve des lectures invitées. Pas de nouveau test ni suite profonde : patches réappliqués, analyseur existant, revue indépendante, compilation iOS et contrat de livraison existants.

## Neural Engine et mesure suivante

Aucun opérateur Core ML coûteux n'est établi dans le chemin observé. Les dernières fenêtres ont un coût GPU réel ; il manque une expérience de sensibilité aux pixels et la passe dominante pour justifier une reconstruction ANE. Aucun chemin de reconstruction activé. Après cette identification, comparer A=1× actuel, B=résolution interne réduite + agrandissement Metal, C=résolution de B + Core ML. B/C isolent l'ANE. Vérifier les opérateurs réellement affectés à l'ANE et les replis CPU, conversions/copies/synchronisations, temps jusqu'à l'affichage, mémoire/énergie/chauffe, détail/HUD en mouvement. cpuAndNeuralEngine autorise ANE et CPU, sans garantir chaque opération sur ANE.

Sources primaires : https://developer.apple.com/documentation/coreml/mlcomputeunits/cpuandneuralengine ; https://developer.apple.com/documentation/coreml/analyzing-a-core-ml-model-s-performance-in-xcode ; https://developer.apple.com/videos/play/wwdc2022/10027/ .

Protocole : installer par-dessus avec la même identité de signature, garder jeu/réglages/sauvegarde/caches ; Coupe Champignon 150 cc à 1× en notant départ/fin de chaque circuit ; répéter avec caches réutilisés, puis après environ 20 minutes. Exporter journal, engine et profiles de la même session. Comparer seulement les portions annotées : FPS moteur/écran, p50/p95/p99, retards par minute couverte et séries, trous audio, vitesse/effets/HUD, empreinte et thermique. Aucune mesure physique après correction disponible ici.

## Contre-expertise mesurée et chemin court 0169 — 20 novembre 2026

Bancs source `2372080f`, [run 44744537924](https://github.com/TarbleFR/RewindBox/actions/runs/44744537924), job 136316319338, [artefact 14631934749](https://github.com/TarbleFR/RewindBox/actions/runs/44744537924/artifacts/14631934749), SHA-256 `6533298e4226556ad1ef6e4533e8479783f2b140bae8fedbd583546cb2b5b6e2`. Les [CSV, environnement, rapports Core ML et empreintes](s2arm-802-benchmarks/provenance.json) sont conservés. Machine macOS 26.7.2 arm64, Apple clang 21 / Xcode 26.6 ; Metal **Apple Paravirtual device**, aucun iPhone physique. Entrées synthétiques contrôlées, chemins alternés, états réinitialisés, sorties comparées hors chronométrage ; aucun rejeu du jeu ni conversion de ces coûts en FPS.

| Chemin | Initial → candidat (médianes ns/appel) | Rapport apparié médian | Décision |
| --- | ---: | ---: | --- |
| Second cache UBO, 100 % de réutilisation | 7,289 → 8,457 | 1,193 | Rejeté. |
| Second cache UBO, 50 % de réutilisation | 8,397 → 19,222 | 2,360 | Rejeté, plus lent dans 9/9 passages. |
| Second cache UBO, 0 % de réutilisation | 8,676 → 21,225 | 2,447 | Rejeté. |
| Garde inline, adresses natives répétées | 8,285 → 6,580 | 0,861 | Conservée ; dispersion importante, 5/9 passages gagnants. |
| Garde inline, adresses natives renouvelées | 6,979 → 6,046 | 0,851 | Conservée ; 7/9 passages gagnants. |
| Garde inline, collisions du cache existant | 7,680 → 7,354 | 0,995 | Effet environ neutre. |
| Garde inline, vraie traduction GVA | 16,630 → 15,111 | 0,923 | Résolveur et verrou conservés ; 8/9 passages gagnants. |
| Identifiant de vue avec activation dynamique 0166 | 3,706 → 8,040 | 2,108 | Rejeté, plus lent dans 11/11 passages. |

Les rapports appariés sont calculés passage par passage, puis médiannés ; ils ne sont pas le quotient des deux médianes indépendantes. Le runner virtuel et les coûts de quelques nanosecondes limitent leur portée. Les bancs CPU/RID sont compilés en `-O3` sur macOS, avec des enveloppes `noinline` ; la couche NVN du moteur iOS utilise `-Os -g -fobjc-arc`, SDK iPhoneOS, sans LTO dans cette route. `ios-guest` relie les mêmes objets et `libnvn.a` issus de `make ios`. Les décisions d'inlining et le placement des instructions peuvent donc modifier le coût exact : les pourcentages du banc ne mesurent pas le binaire iOS livré. La garde partage les bornes immuables avec l'allocateur : seule une adresse déjà native évite l'appel externe. Le cache de pools existant, sa génération, les bornes, les copies sparse et les morceaux de soumission restent inchangés. `addr_cpu` et `nvn_be_addr` utilisent également cette garde identique ; leur coût individuel n'a pas été mesuré séparément.

Le push sélectif n'améliore que 6/30 scénarios avec consommation, tous avec 100 % de constantes identiques. À 50 % identiques et premier octet changé, son coût vaut 1,33–1,61 fois l'original selon la taille. La distribution réelle des mises à jour du jeu manque : la comparaison n'est donc pas activée dans le moteur livré. Le chemin initial copie, incrémente la version et invalide les arguments. Les expériences rejetées restent dans les bancs pour comparaison, pas dans le chemin normal.

0169 retire entièrement le second cache UBO, son wrapper, ses lectures d'horloge et ses compteurs. Il retire aussi la comparaison des constantes et ses compteurs. Les anciennes lignes de diagnostic sont supprimées, plutôt que de publier des zéros qui sembleraient mesurés. Les captures GPU bornées, les échéances visibles et la chronologie producteur/réveil des patches 0166–0168 restent présentes. Ni résolution, ni vitesse invitée, ni cache de textures de 192 Mio, ni sauvegarde/historique graphique ne sont modifiés.

### Identifiant Metal direct : mesure décisive retenue

Le suffixe court relit directement le RID de la vue que `tex_by_id` vient de valider sous le même verrou `g_rmu`. Audit de toutes ses sorties : un résultat non nul implique une entrée valide, la même vue et son RID déjà rempli, y compris le repli sur la texture de base lorsqu'une création de vue échoue. Le pointeur fort local et la sortie `out` sont conservés. Il n'ajoute ni comparaison de titre, ni lecture atomique de configuration, ni compteur par appel.

[Second banc, source fc0017a9](https://github.com/TarbleFR/RewindBox/actions/runs/44745877482), job 136320916653 : **3,2866 → 1,1816 ns/appel**, rapport apparié médian **0,359521**, candidat plus rapide dans **11/11 passages**, sommes de contrôle identiques. Le suffixe est donc environ 64 % moins coûteux dans ce microbanc. Cela ne mesure ni le reste de `tex_by_id`, ni une image complète, ni l'A18 Pro. [CSV et provenance](s2arm-802-benchmarks/short-provenance.json). La garde d'échec numérique du banc Core ML est aussi compilée/exécutée avec succès ; rapports complets conservés séparément de la première mesure.

### Neural Engine : expérience réalisée, accès matériel manquant

Le modèle analytique authored (filtre 3×3 et interpolation ×2, pas de poids entraînés) a été réellement exécuté. Les sorties du même traitement Metal B et Core ML C concordent : écart maximal 1/255 et moyen 0,029–0,034/255, zéro erreur de prédiction. Le code iOS du banc passe le typecheck SDK. Le runner expose seulement CPU/GPU ; **zéro opération ANE**, C est un **repli CPU**. `cpuAndNeuralEngine` autorise les deux processeurs sans promettre un passage sur l'ANE ; le plan Core ML est une affectation anticipée, pas une trace d'exécution physique.

| Entrée → sortie | Échantillons mesurés | Metal B p50 / p95 | Core ML C, repli CPU, p50 / p95 |
| --- | ---: | ---: | ---: |
| 320×180 → 640×360 | 90 | 0,497 / 1,185 ms | 1,338 / 4,531 ms |
| 960×540 → 1920×1080 | 30 | 1,634 / 3,135 ms | 6,517 / 9,833 ms |

Le temps englobe conversions, attente de l'entrée GPU et production jusqu'à la fin GPU ; il exclut rendu du jeu et affichage réel (zéro horodatage de présentation). Les BGRA synthétiques natifs A contre B donnent MAE≈26/255 et PSNR≈15,7 dB sur les motifs fins : la concordance B/C ne prouve pas la qualité native. Aucune reconstruction n'est activée dans RewindBox. Le runner iOS portable est conservé pour mesurer l'ANE d'un A18 réel ; aucune cadence, chauffe ou qualité en jeu après ces changements n'est encore mesurée. Le programme du banc conserve désormais son rapport complet et échoue explicitement si l'équivalence numérique ou les prédictions échouent.

Références Apple : [cpuAndNeuralEngine](https://developer.apple.com/documentation/coreml/mlcomputeunits/cpuandneuralengine), [MLComputePlan](https://developer.apple.com/documentation/coreml/mlcomputeplan-1w21n).

## Compilation et identité du moteur 0169

[Run 44746620489](https://github.com/TarbleFR/RewindBox/actions/runs/44746620489), source `355273cc089ad414dedb0e6b0628999851bdf012`, tentative 1 : compilation iOS arm64 réussie sur macOS 15 et 26, inventaire et contrôles des entrées invitées validés. L’artefact framework `14633558337` contient 24 991 234 octets, SHA-256 `b9a4b641f604d2136ed2385e4cbdc1af54e15f1fc35c841bc2195c585db9e6ad`. Ses 169 patches correspondent exactement aux sources du dépôt.

Le [pin 1849ad68](https://github.com/TarbleFR/RewindBox/commit/1849ad681b78285ab15662b1186e6395c6fbdde6) authentifie ce moteur : empreinte de charge utile `d179339f144913f263315265e8084dab2116ea6a51970a80c766227a0cdd5fcf`. NS2Pro, les producteurs de préparation et de données système, les patches de préparation et la chaîne de shaders sont identiques à la 801. Le SHA-256 du binaire signé dans la 802 est relevé séparément ci-dessous ; cette compilation ne mesure ni FPS, ni chauffe, ni fidélité sur iPhone.

## Livraison privée 802 vérifiée

[Run 44749830555](https://github.com/TarbleFR/RewindBox/actions/runs/44749830555), source `ffdb82c37d6dd8e1763a1263fca28eb424fb5e30`, tentative 1 : contrôle préalable, republication des composants conservés et application réussis. Groupes Flutter/native déclarés `not-run` ; contrat de livraison frais, compilations, contrôles ABI et signature maintenus. Les quatre parties chiffrées finales ont été téléchargées, comparées aux tailles/empreintes de l’API, déchiffrées puis vérifiées hors ligne. Les six validateurs ont réussi ; aucun changement binaire non déclaré.

`RewindBox-802.ipa` : **333 507 064 octets**, SHA-256 `d81aa29bf2045727dc568ecade3874c2407ff9f685bf0ed7353858570e1bf8c2`. Les [reçus de livraison](rewind802/delivery.json) et la [synthèse du moteur](rewind802/s2arm-identity802.json) conservent la chaîne d’identité. L’IPA possède 97 images binaires et les 10 identifiants d’application/extensions de la 801, toutes les versions à 802. Les 169 patches correspondent au pin authentifié. Le binaire S2Arm signé a pour SHA-256 `0af43c7e52cb33634aa0463f952cac974d10d15b90a65c79e47e40cf3b93239e` et UUID Mach-O `1DA393F7-2281-391F-9B24-590F3535733C` ; ces identifiants sont distincts de l’empreinte de charge utile et d’un UUID de session.

Signature ad hoc vérifiée par la CI, installation par re-signature SideStore avec la même identité que la 801. NS2Pro, préparation, données système, chaîne graphique, budget textures de 192 Mio et identités de caches sont conservés. Les correctifs Nextendo de la 801 restent intégrés. Aucun résultat physique de la 802 n’est disponible : ni gain FPS, ni qualité native, ni chauffe, ni stabilité prolongée ne sont déclarés validés. Les captures bornées et chronologies de la 802 préparent cette mesure.
