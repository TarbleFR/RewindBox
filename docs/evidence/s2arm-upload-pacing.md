# Textures et cadence de présentation sur A18 Pro

Titre `04007EF01F8AE000`, exécutable principal `db93b0125f4850601d61c3edde012f8e`. Les chiffres ci-dessous proviennent des captures antérieures du titre. Les numéros de trame se répètent entre sessions.

| Capture et trame | Trame | Premiers uploads | Volume et temps total d’upload | Fautes majeures du processus | Pages absentes aux sondes textures | Compilation |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 18 novembre, 20 h 16 min 37 s, T2079 | 140,7 ms | 145 | 128,9 Mio / 42,5 ms | 1 573 | 40 | 0,0 ms |
| 18 novembre, 20 h 20 min 58 s, T855 | 172,8 ms | 145 | 128,9 Mio / 44,1 ms | 346 | 23 | 0,0 ms |
| 19 novembre, 06 h 54 min 22 s, T1051 | 178,9 ms | 153 | 201,0 Mio / 80,5 ms | 2 372 | 51 | 0,0 ms |
| Même capture, T2722 | 178,3 ms | 297 | 164,6 Mio / 59,6 ms | 1 238 | 216 | 10,9 ms |
| 18 novembre, 20 h 17 min 51 s, T7 | 293,3 ms | 5 | < 0,1 Mio / 0,1 ms | 5 233 | 0 | 0,0 ms |

`vawin.c` réserve l’espace d’adressage et crée des fichiers temporaires clairsemés, immédiatement détachés de leur nom. Les mappings `MAP_SHARED` gardent leurs descripteurs. Au lancement de la session T2079, le moteur mesure 6 014 Mio disponibles, sous son seuil de 7 168 Mio pour sortir la région du mode fichier. Il annonce 59 segments de 1 024 Mio. La RAM disponible au processus autorise une croissance future. La résidence de chaque page dépend du cache de fichiers du noyau.

`getrusage(RUSAGE_SELF).ru_majflt` couvre tous les threads et tous les mappings durant l’intervalle. `mincore` échantillonne les pages des spans textures sondés. Une page absente peut ensuite arriver par lecture anticipée. T7 compte 255,3 ms de CPU sur le thread de présentation. Les traces historiques ne ventilent pas les 42,5–80,5 ms entre hachage, préparation CPU, encodage et attente de pages.

## Premier usage des textures

`rec_bind_tex1` → `nvn_be_record_texture_pages` ou `nvn_be_record_texture_hint` → préparation facultative. À la demande, `tex_mtl_` et `pkg_upload_` valident le stockage et les marques de pages. Le chemin GPU direct désentrelace la mémoire invitée puis regroupe les copies de sous-ressources dans l’encodeur de copie. Le chemin CPU prépare un buffer de staging. `up_flush_cause` encode les copies, garde les ressources vivantes jusqu’à la fin de la commande et conserve la dépendance avant consommation.

La lecture anticipée optionnelle vérifie le serial de la texture enregistrée, la résidence et la marge iOS. Elle conseille au noyau des plages absentes avec `F_RDADVISE` en découpant à la frontière de chaque fichier. Limites de conseil de 2 Mio par texture, réserve de 2 Gio au processus, rafale de 4 Mio et recharge de 8 Mio/s. La pression, la fermeture, une adresse réutilisée ou l’épuisement du budget peuvent faire abandonner ce travail facultatif. Le noyau peut récupérer les pages.

Le budget de lissage couvre au plus 1 Mio par trame, 256 Kio par texture, huit instantanés en cache et une seule préparation en cours. Le worker utilitaire lit uniquement les pages repérées en mémoire. Le premier usage compare tous les octets avant de réutiliser leurs hachages. Après 8 Mio de demande sur une trame, seuls les travaux nécessaires continuent. Le regroupement des copies CPU accepte jusqu’à 1 Mio par texture et 2 Mio de staging retenu dans un lot admissible. Les gros uploads immédiatement visibles restent ordonnés avant leur draw. Ces limites portent sur le travail facultatif et les copies regroupées, sans plafonner le débit d’un upload obligatoire.

## Charger un profil de cadence sur iPhone

Le chargeur intégré lit le fichier préparé sous `Library/S2Arm/<GID>/pack/shaders/direct/game.tsv` lors de l’initialisation NVN. La préparation standard sur iPhone produit un squelette sans profil. Le moteur lit maintenant présence et valeur explicites en une seule ouverture et rejette les lectures incomplètes. Pour un lancement hébergé, une cadence dérivée exige `present_interval_derived<TAB>display` et la valeur `ok` sur la ligne du programme dans le fichier voisin `fps_l3_results.tsv`. Une cadence explicite du profil fourni demeure prioritaire sur la dérivation. Le simple `fps60_display=1` d’un manifeste générique ne confirme aucune correction de vitesse.

Pour activer un profil personnel après avoir vérifié la vitesse sur **ce build**, mettre le fichier suivant dans RewindBox, accessible via Fichiers. Chaque ligne contient une véritable tabulation entre clé et valeur.

`Documents/S2Arm/profiles/04007EF01F8AE000/db93b0125f4850601d61c3edde012f8e/game.tsv`

```tsv
program_id	04007EF01F8AE000
present_interval	display
```

Le profil personnel est consulté à la première configuration de présentation, après chargement du programme et de son build. Le chemin sélectionne l’exécutable. Le contenu doit fournir le `program_id` correspondant et la valeur explicite `display` ou `game`. UTF-8 sans BOM, LF ou CRLF, une clé par ligne, commentaires sur lignes commençant par `#`, première occurrence d’une clé retenue. Une ligne vide est admise. La limite est de 1 Mio. Un profil mal formé revient à `game`. L’absence du fichier conserve la décision du paquet. Aucun profil personnel actif n’est livré.

`S2A_FPS60=0` désactive la libération de l’intervalle par profil. Les commandes explicites historiques `DM_PRESENT_INTERVAL` et les correctifs de pas de simulation restent distincts. Pour comparer les profils, laisser `DM_PRESENT_INTERVAL` non renseigné et redémarrer le processus entre les essais. Suivre le temps d’un événement de jeu reproductible pendant la même durée réelle, en mode `game` puis `display`. Inclure gameplay, menus et transitions. Une fréquence d’affichage de 60 Hz seule ne valide pas la vitesse logique.

## Comparaison sur iPhone

Utiliser `Documents/env.txt`, une affectation `NOM=VALEUR` par ligne et un relancement complet par essai. Garder la même sauvegarde, suivre le même trajet, séparer cache froid/chaud et états thermiques. Augmenter un seul facteur à la fois.

| Variable | Effet |
| --- | --- |
| `S2A_RB_TEXTURE_PAGER=1` | Conseils de lecture par fichier sur les binds retenus. Désactivé par défaut. |
| `S2A_RB_UPLOAD_BATCH=1` | Regroupement de premières copies CPU admissibles. Désactivé par défaut. |
| `S2A_RB_UPLOAD_SMOOTH=1` | Préparation bornée des métadonnées pour les binds réutilisables. Désactivé par défaut. |
| `S2A_RB_UPLOAD_TRACE=1`, `S2A_RB_PAGER_TRACE=1` | Ventilation des trames lentes. Garder ces valeurs identiques en A et B. |
| `S2A_RB_PROMOTION_PACING=0` | Témoin de cadence. La nouvelle cadence est active par défaut sur le chemin direct Metal 4 du titre. |
| `S2A_RB_CADENCE_PROFILE=0` | Ignore le profil personnel. Par défaut, le moteur le recherche au lancement hébergé iOS. |

Dans `host.log`, contrôler le build, `cadence profile ... result=explicit` et `present tick ... interval mode`. Relever `[RB-UPLOAD]` (CPU hachage, staging/swizzle, encodage, volumes), `[RB-TEX-PAGER]` (fautes du processus, pages absentes, sonde et temps CPU/mural de l’upload froid), `[RB-FILE-HINT]` (octets conseillés, refus et `process_peak_footprint_bytes`). Le temps hors CPU donne une borne supérieure incluant les attentes et la désélection du thread. L’instrumentation ne mesure pas directement la durée de service du pager noyau.

La présentation active utilise `CAMetalDisplayLink` sur le `CAMetalLayer`, le drawable fourni par le callback, la soumission puis `present`. Le mode physique 30 ou 60 suit la période autorisée. Le moteur conserve les limites en vol et la dépendance de complétion Metal avant réemploi. Apple réserve la présentation temporisée au système pour ce drawable. [Contrat du délégué](https://developer.apple.com/documentation/quartzcore/cametaldisplaylinkdelegate/metaldisplaylink(_:needsupdate:))

Suivre `[rb-link]` pour les callbacks, les holds, les ticks filtrés, la file vide, les slots occupés et les échéances de soumission. Pour accepter le 60 Hz, exploiter les fenêtres stables 60 avec timestamps disponibles, `displayed deadlines`, `displayed streaks` et `on-screen ... dropped ... p99`. Cibles de zéro perte et de p99 ≤ 16,8 ms. Consigner séparément le maximum et le nombre de trames > 100 ms aux changements de zone, qui peuvent échapper au p99. Dans la capture du 19 novembre, la ligne à 3 001 présentations cumulées indique 354 callbacks, 300 présentations et 54 ticks vides. Le compteur des anciennes images fusionnées y vaut zéro.
