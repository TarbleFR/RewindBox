# Capture 801 — analyse indépendante

## Identité et couverture

- `engine/0400C3F00006E000/host.log`, SHA-256 `1d2ecdce7386560e71ff36f594f837050942d5430bdff4972ad72dc4309c561e`.
- Session `CB7024BD-BE35-4264-BFBF-5A6D8417ECD9`, PID 12393, journal lignes 5889–5928 : préparation réutilisée 12:45:05.964 UTC, lancement passé 12:45:08.592, fermeture 12:49:57.757 le 20/11/2026. Journal lignes 5889 et 5902 : moteur run44729718541, identité graphique conservée.
- Export `preparation/CB7024BD…/identity.json` : **appBuild801**, jeu `9e244438c3d8ef1c703a6a85ef99c4f0`, génération `4b04cdfef06457bc9de63ca5901a68369d7316dfbdb147e5b15ae298bfcdbdaa.AE7674F6-5A93-4687-996B-3CF53396B51A`, graphicsRevision3. UUID ci-dessus = session/génération, pas UUID Mach-O du moteur.
- Reçu dépôt `docs/evidence/rewind801/s2arm-identity801.json` associe ce run au producteur `71ea69e8173db4db3795c8092d74f552a8e89d90`, amont `6b6a571553f7a687af46e03e2cdbf8ef4d77f335`, 165 patches. Binaire moteur signé SHA256 `635d303d296ebca38afc863f452df57d17e4af4cb7e20834866e1180c6cfb5f7`.
- Mario Kart World sélectionné explicitement par le journal; version1.0.0 et modèle iPhone16 Pro Max proviennent du périmètre utilisateur ; Apple A18 Pro GPU est identifié dans host:252. Host: 7619MiB RAM, écran2868×1320, OS27.0 (puce imprimée `?`), mode portable, pas de plafond S2A_FPS, FPS60 activé, écran16:9, AA None et filtre Nearest. Cache192MiB/900images confirmé host:5533. Signatures de scène1248×700/704 et parfois1920×1080; plus grande cible6144² n'est pas la résolution finale. Le multiplicateur1× n'est pas attesté continûment par l'export.
- 8 254 intervalles1..8254, aucun trou ni abandon, 273.950s. Tout le jeu est au premier plan jusqu'à la fermeture; perte de focus seulement après arrêt (host:18072). Aucun enregistrement écran dans la session (heartbeat screen captured0).
- `race_sequence_asset` =5812 intervalles2443..8254 /222.654s. Ce sont des candidats de conduite, pas des segments de circuits confirmés; aucun nom/150cc/course ne peut être déduit d'un asset seul. Les fenêtres3000..8100 évitent les premières transitions de sélection/chargement mais restent sans annotation vidéo.

## Méthode

Analyseur existant exécuté avec host exact, `--session CB7024BD-BE35-4264-BFBF-5A6D8417ECD9 --journal s2arm-journal(2).jsonl` : `metrics801.json`. Aucun profil historique fourni à cet appel. Quantiles supplémentaires au rang supérieur depuis chaque ligne cup, dans `supplement801.json`; petites différences avec les quantiles arrondis du moteur et sa fenêtre glissante sont conservées, non mélangées.

Ensemble:30.130FPS moteur; p50/p95/p99=27.674/58.943/101.904ms;92>100ms,7>200ms,1>500ms. Indice race:26.103FPS;31.297/60.130/109.917ms;79>100ms,2>200ms,0>500ms.

**Zéro compilation MSL, traduction, attente PSO ou bibliothèque dans les8254intervalles**. Préparation:5661archives réutilisées,0compilation (host:4878–4879),1171pipelines utilisés pour la première fois et0promotions/publiés (fin). Les compteurs ne montrent donc pas de compilation concurrente expliquant la conduite lente.

| Images (indice de course, non annoté) | s | FPS moteur | FPS affichés | image p50/p95/p99 ms | CPU soumission ms/image | GPU p50/p95 ms | retards / intervalles écran connus |
|---|---:|---:|---:|---|---:|---|---:|
| 3301–3600 | 10.029 | 29.912 | 29.454 | 28.642 / 56.426 / 129.573 | 7.589 | 12.22 / 20.19 | 173/298 |
| 4501–4800 | 9.598 | 31.256 | 30.719 | 29.650 / 39.891 / 122.174 | 9.891 | 12.40 / 17.95 | 202/298 |
| 5701–6000 | 7.680 | 39.062 | 39.252 | 24.075 / 30.742 / 60.313 | 5.739 | 10.84 / 15.49 | 144/300 |
| 6001–6300 | 7.691 | 39.006 | 38.614 | 24.242 / 31.456 / 47.649 | 6.429 | 11.34 / 15.21 | 143/298 |
| 6601–6900 | 16.180 | 18.542 | 18.503 | 53.698 / 62.526 / 70.469 | 9.360 | 38.43 / 41.71 | 297/300 |
| 6901–7200 | 15.685 | 19.126 | 19.144 | 52.376 / 57.638 / 101.929 | 8.079 | 36.02 / 38.36 | 287/300 |
| 7501–7800 | 17.025 | 17.621 | 17.678 | 55.023 / 65.295 / 99.909 | 10.819 | 36.71 / 42.28 | 298/300 |
| 7801–8100 | 16.876 | 17.777 | 17.730 | 56.633 / 63.050 / 72.033 | 9.902 | 39.41 / 41.72 | 299/300 |

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

Fenêtres écran:27,8061timestamps,0timestampindisponible signalé,8035intervalles adjacents connus,26manquants à cause notamment des29présentations écartées,4187retards. Les premiers/derniers samples ne couvrent pas tout1..8254.18fenêtres entièrement sous indice race (2701..8100):5389timestamps,5379intervalles connus,3792retards,10manquants/11écartés;~204s, pas une course annotée. Les p50/p95 écran ne sont pas exportés; p99 seulement. Les comptes sont par délai demandé par le jeu (16.67/33.33ms), avec0.1mstolérance, le plus grand des délais des2images adjacentes.

Dernières fenêtres entièrement à33.33msdemandées:8100=299/300tardives; sans ordre exact on peut prouver **au moins150retards consécutifs**,7800≥100,7500≥50,7200≥21,6900≥75. Aucun historique exact des séries; collecter compteur longueur courante/max et séries2+/3+ en temps constant sans écriture par image. Ne pas convertir les58msmoteur directement en nombre de vblanks ratés.

Empreinte échantillonnée pic4841MiB à3600; dernier4439 à8100; retour menu1747MiB,headroom4908,thermal0 (journal5927); départ536MiB. Aucune relance après fermeture dans cet export. Staging216MiB à3942 descend32MiB à6336. Retransferts712 depuis1500 et toujours712 en fin: aucun nouveau retransfert détecté pendant la portion race. Ne pas confondre GPUallocated≈10GiB et empreintephysique. Audio:0vrai trou dans22rapports10s adjacents à la portion race; quelques trous pendant démarrage/sélection. Cela ne valide pas subjectivement l'audio ni la vitesse de simulation/effets graphiques.

65dossiers de profils tous associés par le nom exact au host qui les a émis: **aucun de la801**. Dernier`20261120-073507-rec`:799,sessionB3AD3E7A-D036-482F-A86B-BA7B069F0316,host-20261120-073420.log:6758,signature0..582 de démarrage. Timestamp dossierEurope/Paris correspond journal06:34UTC; les noms des profils sont datés à l'export. Analyseur séparé avec session799/journal/profile exécuté dans`metrics799_startup_profile.json`; aucune validité pour coûts801. Le mainBuild/génération compatibles servent à vérifier le contexte, pas à reprendre les taux de cache ouFPS. TroisderniersCPUprofilés19nov14:00/14:01 appartiennent à04007EF01F8AE000,autrejeu. Tous les appariements dans`supplement801.json`.

**Recommandation de mesure avant gain prétendu**: captures de la même session ciblées sur une fenêtreGPU<16msavecFPS<40, sur le passageGPU36–39ms sans compilation, et sur unSVC0x34>50ms (producteur/wake→run/PC). Ajouter coût par catégorieCPU/passGPU, horodatages completsprésentation et séries d'échéances. ANE reconstruction ne peut être validé ici: aucune expérience pixels A/B et aucune passe dominante isolée. Une résolution réduite ne traite niSVC ni coûtCPU, et masquerait la qualité1× sans preuve.


## Implémentation et revue 0166–0168

Trois réutilisations exactes, chacune désactivable séparément : métadonnées d'adresses UBO résidentes (6×16 entrées, génération des pools, adresse normalisée), identifiant Metal déjà enregistré de la même vue, constantes push comparées lors du rejeu avant invalidation des arguments. Données invitées, shadows, bornes et générations d'arène restent contrôlées. Aucun gain en millisecondes extrapolé du nombre de recherches : les 5,7–10,8 ms de CPU total par image sont un plafond, pas le gain. La résidence, au plus 0,09–0,28 ms/image dans les fenêtres examinées, est secondaire.

Contre-revue : invalidation, durée de vie, contenu différé, horloges, réinitialisation entre sessions. Les compteurs sont publiés hors chemin chaud et l'état de capture est réinitialisé après drainage. Une durée GPU courte n'est pas une preuve de fin avant échéance. Les compteurs sont cumulatifs individuellement cohérents, pas un snapshot groupé ; la première fenêtre après relance peut inclure le reliquat antérieur.

Le poste dominant suivant nécessite une mesure physique : passe GPU devenue lente contre variation de fréquence/puissance ou contention ; producteur du SVC 0x34 contre délai de reprise. La prochaine IPA capture au plus trois images GPU de fenêtres 3D durablement lentes, sans profiler CPU ni signatures lourdes. Les images capturées peuvent être perturbées et ne prouvent pas un gain. Les attentes >=50 ms rapportent le producteur et les étapes de reprise, quatre par dix secondes / 512 par session. La sonde GPU n'écrit plus 16 384 threads dans 1 024 cellules : son niveau absolu après correction n'est pas comparable à 801, sa variation interne à une session reste exploitable.

Les 0163–0165 sont déjà présents. Aucun retransfert supplémentaire après l'image 1500. Cache de 192 Mio, historique personnel et caches compatibles conservés. Aucune barrière supprimée sans preuve des lectures invitées. Pas de nouveau test ni suite profonde : patches réappliqués, analyseur existant, revue indépendante, compilation iOS et contrat de livraison existants.

## Neural Engine et mesure suivante

Aucun opérateur Core ML coûteux n'est établi dans le chemin observé. Les dernières fenêtres ont un coût GPU réel ; il manque une expérience de sensibilité aux pixels et la passe dominante pour justifier une reconstruction ANE. Aucun chemin de reconstruction activé. Après cette identification, comparer A=1× actuel, B=résolution interne réduite + agrandissement Metal, C=résolution de B + Core ML. B/C isolent l'ANE. Vérifier les opérateurs réellement affectés à l'ANE et les replis CPU, conversions/copies/synchronisations, temps jusqu'à l'affichage, mémoire/énergie/chauffe, détail/HUD en mouvement. cpuAndNeuralEngine autorise ANE et CPU, sans garantir chaque opération sur ANE.

Sources primaires : https://developer.apple.com/documentation/coreml/mlcomputeunits/cpuandneuralengine ; https://developer.apple.com/documentation/coreml/analyzing-a-core-ml-model-s-performance-in-xcode ; https://developer.apple.com/videos/play/wwdc2022/10027/ .

Protocole : installer par-dessus avec la même identité de signature, garder jeu/réglages/sauvegarde/caches ; Coupe Champignon 150 cc à 1× en notant départ/fin de chaque circuit ; répéter avec caches réutilisés, puis après environ 20 minutes. Exporter journal, engine et profiles de la même session. Comparer seulement les portions annotées : FPS moteur/écran, p50/p95/p99, retards par minute couverte et séries, trous audio, vitesse/effets/HUD, empreinte et thermique. Aucune mesure physique après correction disponible ici.
