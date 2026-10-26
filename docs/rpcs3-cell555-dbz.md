# RPCS3 — nouvel export DBZ et GoW3, observations du build 553

26 octobre 2026. Ce complément conserve le [premier bilan 555](rpcs3-cell555.md)
et ses preuves séparément. **Aucun chiffre ci-dessous n'est un gain 555.**
La cible DBZ est `BLES01658`, Dragon Ball Z Budokai HD Collection. Le titre
est fourni par les journaux ; les scènes restent non identifiées.

Le candidat de livraison porte désormais le numéro **555**, après intégration
du correctif d'import PS3 554 (`9f6892b9`) et de la branche jusqu'à `eefd945f`.
L'import des disques depuis la bibliothèque et MeloNX sont préservés. Les
expériences de hachage gardent leurs noms/run IDs **554** ; les nouveaux
processus de cet audit restent du build **553**, sans mesure 555.

## Pièces, périodes et intégrité

Le [reçu dédié](evidence/rpcs3-cell555-dbz-observed.json) contient SHA-256,
numéros de lignes, histogrammes, ancres d'horloge et portées détaillées.

| Fichier nouveau | Lignes | Octets | Contenu pertinent |
| --- | ---: | ---: | --- |
| `RPCS3-timeline(1).log` | 355 | 1 018 641 | Historique conservé, puis 114 fenêtres nouvelles |
| `RPCS3-performance(1).log` | 2 396 | 1 373 847 | Trois processus 553, détails partiels du premier |
| `RPCS3-restore-trace(1).log` | 1 954 | 862 534 | Identique octet pour octet au premier export |

La restauration est donc **une preuve historique répétée**, pas trois nouveaux
essais. Son SHA-256 est
`3b66e3270660678b48fbc46ece0664c0895fda9f8994c0ae361589c3367d4f64`.
Elle ne décrit aucun des nouveaux PID DBZ.

| PID 553 / titre | Sessions et fenêtres | Lignes timeline |
| --- | --- | --- |
| 34459 / DBZ | s1 : 1–2 ; s2 : 1–17 | 242–260 |
| 34576 / GoW3 `BCES00510` | s1 : préparation 1, puis invité 2–45 | 261–305 |
| 34675 / DBZ | s1 : 1 ; s2 : 1–49 | 306–355 |

DBZ 34675 comporte deux boots `fresh` : 11 modules PPU en cache/123,947 ms,
puis 23 en cache/291,604 ms, aucun compilé (performance lignes 1190 et 1219).
Ce sont deux ensembles différents. Ni la transition ni `guest_unclassified`
ne permettent d'étiqueter précisément menu, combat, cinématique ou chargement.

Les rapports DBZ s2 vont de 16:04:56,208 à 16:08:59,350 UTC. Ils terminent des
fenêtres ; le premier rapport n'est pas l'instant du premier frame. L'écart
Unix–monotone du PID 34675 varie de 17,476 ms, malgré un encadrement maximal
de 23 µs. Employer les ancres locales et les durées monotones, pas un décalage
constant pour toute la capture. Les autres PID ont leurs propres ancres.

Le premier PID n'a des histogrammes détaillés que pour s2/fenêtres 14–17 :
834 intervalles sur les 4 014 de cette session. Ses p95/p99 partiels ne sont
pas attribués à toute la session. Rotation performance signalée. Pour PID
34675, tous les histogrammes présents concordent avec la timeline ; pertes
shader longs et `LOG_BUDGET` à zéro, aucune rotation signalée. Cela ne prouve
pas une conservation infinie ni l'absence de pauses hors de la capture.

## DBZ : une cadence limitée avec des attentes GPU répétées

| Portée PID 34675/s2 | Intervalles | Durée des fenêtres | p50 / p95 / p99, bornes ms | Maximum | >50 / >100 / >500 ms |
| --- | ---: | ---: | --- | ---: | --- |
| 1–49 | 11 263 | 248,194 s | 21–21,999 / 28–28,999 / 30–30,999 | 84,936 ms | 5 / 0 / 0 |
| 2–49 | 11 020 | 243,115 s | 21–21,999 / 28–28,999 / 30–30,999 | 71,451 ms | 4 / 0 / 0 |
| 12–49 | 8 444 | 192,520 s | 22–22,999 / 28–28,999 / 30–30,999 | 46,413 ms | 0 / 0 / 0 |
| 40–49 | 2 182 | 50,705 s | 22–22,999 / 29–29,999 / 30–30,999 | 39,058 ms | 0 / 0 / 0 |

Les histogrammes sont fusionnés, pas leurs percentiles. Les sous-périodes
se recouvrent et ne s'additionnent pas. La fenêtre 49 rapporte 42,565 FPS,
23,493 ms/image, p95 29,556 ms et p99 30,968 ms dans FRAMEPROF. Ce point n'est
ni un FPS moyen universel ni une comparaison avant/après.

Les fenêtres 2–10 comptent environ une attente texture/image et 27 dessins/image.
Les fenêtres 12–49 en comptent **exactement deux/image**, 185,473 dessins/image :
16 888 attentes totalisant 69 399,787 ms, soit **8,2188 ms/image**. La charge
change dans la capture ; aucune scène n'est inventée pour expliquer ce changement.

Les dernières dix fenêtres comptent 4 364 attentes texture, 18 121,759 ms,
soit **8,3051 ms/image**. CPU RSX pondéré : 13,9264 ms/image ; CPU PPU :
4,9804 ms/image ; CPU SPU cumulé entre threads : 36,1641 ms/image. Ces CPU
et attentes se recouvrent entre composants et ne forment pas une somme
séquentielle de temps d'image. Le temps GPU réel est indisponible (`-1`).

Lignes performance 2384/2386 : `cpu_gpu_fence` et `RSXSYNC texture` décrivent
le même appel instrumenté à `vk::wait_for_fence`. Leurs nombres diffèrent
occasionnellement aux frontières de collecte : ne pas les additionner.
`frame_latency`, enregistré à la soumission puis au cleanup observé dans
`VKPresent.cpp`, mesure l'âge de la soumission, **pas une autre attente CPU**.

## Chemin de code et limite de l'attribution

Dans les sources de référence 553 :

1. `Common/texture_cache.h`, `flush_set`, sélectionne les surfaces non
   synchronisées, effectue `copy_texture`, puis `cleanup_after_dma_transfers`.
2. `VKTextureCache.cpp`, `cleanup_after_dma_transfers`, soumet le buffer de
   commandes primaire `flush_only`, attend sa fence, puis le réinitialise.
   C'est l'unique portée `SiteScope(texture, true)` du cœur.
3. Le même appel alimente le compteur CPU fence dans `vkutils/sync.cpp`.
   Le cache textures est verrouillé pendant `flush_set`.

Les invalidations précédant un repli texture vers le CPU, une source blit ou
une destination blit avec limites strictes peuvent emprunter ce chemin.
Les fautes mémoire CPU passent normalement par le buffer secondaire `all`
et une attente DMA différente : ne pas attribuer ce compteur à toutes les
fautes mémoire. Il faut départager l'origine, les octets et la raison du
repli avant d'affirmer qu'un transfert est inutile.

Le faible `RSXFRAME texture_ms` — 0,5705 ms/image échantillonnés dans les dix
dernières fenêtres — couvre les textures lors des dessins, pas tous les blits.
Il ne contredit donc pas les 8,305 ms d'attente. **Retirer la fence sans
garantir la disponibilité GPU→CPU corromprait les lectures.** Les journaux
ne démontrent ni réveil perdu ni interblocage ; ils confirment un poste
d'attente fréquent à cibler et un verrou englobant, sans mesurer sa contention.

## Pourquoi shader, hachage et NeoSwap ne suffisent pas ici

Configuration effective DBZ, performance lignes 1216/1218 : Legacy demandé et
appliqué, aucun repli ; résolution 100 %, limite Auto, WCB/WDB désactivés,
SPU Safe/LLVM, réservations exactes actives, MT RSX et textures asynchrones
désactivés. `database=0`, `legacy_custom=0`, `sparse_overrides=1` ne reproduisent
pas l'ancienne configuration legacy GoW3 qui bloquait un profil. Préserver
les préférences utilisateur et valider le rendu avant toute modification.

Sur s2 entière : 56 compilations source/197,014 ms, maximum 39,283 ms ;
101 pipelines graphiques/71,769 ms, maximum 2,310 ms. Après la fenêtre 11 :
aucune compilation source/module/compute, un seul pipeline de **648 µs**
en fenêtre 30. Les dernières dix fenêtres sont entièrement à zéro. Un mode
shader asynchrone ne peut expliquer ni supprimer leurs attentes répétées.

Le JIT est aussi nul dans les dernières dix fenêtres. Les deux boots
réutilisent leurs objets PPU. Le hachage hybride ≥4 KiB est à zéro pendant
toute la session ; une accélération NEON de ce chemin GoW3 ne constitue donc
pas une explication d'un futur gain DBZ. Les autres chemins de hash ne sont
pas tous couverts par ce compteur.

Les dernières dix fenêtres contiennent 101 129 857 PUTLLC réussis et
53 749 752 échoués, dont 1 030 023 passages lourds. Ce sont des occurrences,
pas une mesure de coût de l'instrumentation. `event_wait` totalise 71,136 s
entre SPU sur 50,705 s murales ; GETLLAR poll/sleep reste nul. Les garanties
de réservation et événements invités restent nécessaires.

Empreinte maximale échantillonnée : **1 736,77 MiB** ; pression maximale 0,
état thermique maximal 1, sans température ni fréquence mesurée. Les demandes,
préchargements et attentes VDEC restent nuls. Aucun journal d'opérations
NeoSwap nouveau n'est fourni : les compteurs du processus ne permettent pas
de diagnostiquer les restaurations, leurs cycles ou les pages sales après
retrait des `fsync`. Pas de hausse de réserve mémoire justifiée par ces traces.

## Delta 555 retenu : rendre l'attribution vérifiable

Les nouvelles mesures `READBACK555` répondent précisément à la dépendance
encore non départagée. Quatre points d'appel marquent `texture_cpu`,
`blit_source_cpu`, `blit_destination_dma` ou `presentation_cpu` ; la cinquième
origine `unknown` conserve les autres lots, sur tous les threads. L'origine
est locale au thread, restaurée à la sortie d'une portée imbriquée.

`IOSReadbackProfile` utilise **200 octets de compteurs fixes**. Deux lectures
d'horloge sont effectuées par lot DMA non vide ; aucune par dessin ordinaire
ou hit du cache, aucune allocation par événement. Une ligne par fenêtre
exporte lots, sections, octets demandés confirmés, total et maximum par origine.
Les octets ne mesurent pas exactement le trafic DMA. La durée encadre le lot,
fence et traitements enfants compris : elle ne s'ajoute pas au compteur de
fence et les totaux entre threads peuvent se recouvrir. Transferts, verrous,
barrières et durées de vie des surfaces restent nécessaires et inchangés.

Le complément GoW3 ajoute **32 octets** de compteurs `trim_sections` et la
fréquence TSC dans `JITMEM`. Aucun nouveau compteur atomique par hash n'est
retenu. Le suivi des empreintes pipeline garde 64 entrées récentes et rend
ses pertes explicites ; il ne change ni le cache graphique ni la compilation.

**Ces changements sont des diagnostics, pas des accélérations de jeu ou de
shaders.** Aucun candidat NEON n'est intégré : les essais avec LLVM 22 et
les options du cœur n'ont pas montré de gain robuste. Le hachage 551 de
production reste inchangé. Les essais d'équivalence et microtests ne prouvent
aucune baisse du coût sur iPhone, aucun gain FPS DBZ, ni amélioration p95/p99.
L'instrumentation SPU existante n'est pas présentée comme une nouveauté 555.

## GoW3 dans le même export et validation requise

PID 34576 reste séparé : 44 fenêtres invitées, 6 426 intervalles, p50 33–33,999,
p95 34–34,999, p99 77–77,999 ms, maximum 223,587 ms ; 97 intervalles >50 ms,
37 >100 ms, aucun >500 ms. La fin descend à 11,685 FPS avec 24,526 ms de
traitement texture échantillonné et 13 950 988 240 octets hachés dans la dernière
fenêtre. L'agrégat masque donc un changement de charge. Le boot frais, la
reprise précédente et les scènes ne sont pas interchangeables.

Aucun message de sauvegarde du cache Vulkan ni arrêt propre ne relie les
PID 34342 et 34576 dans les pièces fournies. La baisse des durées de pipeline
est une observation avec caches/scènes différents, pas un gain 555 mesuré.

La validation 553/555 doit reprendre les mêmes scènes DBZ **identifiées**, en
trois passages caches froids dédiés puis chauds, conditions thermiques et
réglages conservés. Relever p50/p95/p99, maxima et >50/100/500 ms, origine et
volume des readbacks, fences/image, temps CPU/GPU disponible, rendu et mémoire.
Tester aussi GoW3 et une copie de save state, conserver les originaux et
prolonger 30 minutes. Les essais appareil, le gain de FPS et le reçu final
de l'IPA restent à compléter ; aucun 60 FPS n'est promis.

Reproduction, depuis la racine du dépôt :

```sh
python3 build-utils/analyze_rpcs3_cell555_logs.py --logs <dossier> \
  --suffix '(1)' --title BLES01658 \
  --reference-report docs/evidence/rpcs3-cell555-observed.json \
  --window-scope 553:34675:2:2:49 --window-scope 553:34675:2:40:49 \
  --window-scope 553:34675:2:12:49 \
  --output docs/evidence/rpcs3-cell555-dbz-observed.json
```
