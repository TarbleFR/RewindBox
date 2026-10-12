# Skins iPhone et tactile du moteur libretro intégré — audit, corrections et bilan

Cycle du 11 octobre 2026, branche `Claude`. Les révisions et les runs CI sont
listés au § 9. Ce document sépare quatre choses :

- les défauts confirmés dans les sources ;
- les changements apportés ;
- les tests automatisés réellement exécutés ;
- ce qui reste à vérifier sur iPhone.

Aucune IPA n'a été produite pour ce cycle. Rien de ce qui suit n'a encore été
validé sur un iPhone.

Périmètre : le moteur libretro intégré (`packages/libretro_internal_bridge`),
avec ses skins, son tactile, ses catalogues et leur interface Flutter.
DolphiniOS, ARMSX2, RPCS3, les cœurs, les helpers JIT et la bibliothèque
(fichiers verrouillés sur la Build 419) ne sont pas modifiés.

## 1. Audit — pourquoi un bouton s'allume sans envoyer d'entrée

La chaîne tactile, de bout en bout :

1. UIKit délivre les touches (`UITouch`) à `LibretroTouchOverlay`.
2. Le test de zone trouve les éléments du skin sous le doigt (`LibretroSkinLayout`).
3. Les noms d'entrée deviennent des commandes logiques, puis des boutons
   RetroPad (`LibretroInputMap`, réglages de remappage).
4. L'état partagé (`LibretroInputState`, verrou `os_unfair_lock`) reçoit ces commandes.
5. Le cœur lit cet état par `input_poll` / `input_state` (`LibretroCoreHost`), à chaque image émulée.

Défauts confirmés dans les sources de départ (`dcf0df6`) :

| # | Défaut | Effet visible |
|---|--------|---------------|
| 1 | L'overlay allumait tout élément sous un doigt, même quand aucune de ses entrées n'atteignait le cœur. Trois cas : nom inconnu de la console, bouton RetroPad bloqué, remappage vide. | Halo sans action : l'animation ne prouvait rien. |
| 2 | L'état tactile n'était lu qu'au moment où le cœur interroge l'entrée. Un appui commencé et relâché entre deux lectures n'était jamais vu. C'est le cas d'un tap rapide, ou d'une touche livrée en retard avec son relâchement. | Taps courts perdus, surtout sur les jeux à 30 images/s ou en accéléré. |
| 3 | Un cœur qui lit l'entrée sans appeler `input_poll` lisait l'instantané précédent. RetroArch, dans ce cas, fait un poll tardif. | Entrées en retard d'une image ou perdues sur ces cœurs. |
| 4 | Les orthographes Provenance / Manic n'étaient pas reconnues : `upLeft` et variantes diagonales, `run`/`play`, `zl`/`zr`, `c up`, `rightAnalog*`, stick sur une console sans stick. | Boutons dessinés inertes dans des skins installés. |
| 5 | Les `extendedEdges` d'un voisin ajoutaient un second appui à un doigt posé sur un bouton dessiné. | Appuis parasites (A+B au lieu de A). |

Hypothèse non démontrée : un retard de livraison des touches par iOS sur les
bords d'écran (gestes système). Ce point n'est pas corrigé à l'aveugle : il est
mesuré par le diagnostic (§ 6), qui affiche le délai entre l'horodatage
`UITouch` et la réception.

Constat sans lien établi avec le défaut : `retro_set_controller_port_device`
n'est jamais appelé. Les cœurs gardent leur périphérique par défaut (RetroPad),
qui correspond au mappage utilisé. Ce point n'est pas modifié.

## 2. Moteur tactile — couches séparées et testables

Révision `4da3154`.

- **Couche visuelle.** `LibretroTouchOverlay` (UIKit) ne fait plus que
  transmettre les événements `UITouch` (began / moved / ended / cancelled) et
  publier le résultat. Il dessine l'appui seulement pour les éléments qui
  envoient réellement une entrée.
- **Couche interactive.** `LibretroTouchTracker` est portable (Foundation
  seulement) et testé sur macOS sans UIKit. Il gère :
  - le test de zone et les modes de doigt (bouton, croix, stick, écran tactile) ;
  - les diagonales et le glissement d'un bouton à l'autre ;
  - les remappages, les actions du menu, et le pointeur DS / 3DS.

  Il publie `coreInput` (RetroPad), les éléments effectivement pressés, les
  éléments inertes avec leurs entrées sans effet, les vecteurs de stick, et le
  détail de chaque doigt.
- **Verrou d'appui `LibretroInputLatch`** (C pur, sans allocation). Il compte
  en images émulées (`frameSerial`) :
  - chaque front d'appui reste visible du cœur 3 images (2 pour les directions) ;
  - un relâchement entre deux appuis est montré 1 image ;
  - une direction maintenue seulement par le verrou ne s'affiche jamais avec
    sa direction opposée réellement tenue ;
  - même traitement pour le pointeur DS / 3DS.
- **Hôte.** `LibretroCoreHost` compte les images et fait un poll tardif à la
  première lecture d'une image sans `input_poll`, comme RetroArch.
- **Noms d'entrée.** `LibretroInputMap` accepte les orthographes ci-dessus. La
  diagonale envoie ses deux directions. Sur une console sans stick, un stick
  devient la croix (entrée « adaptée », signalée). Le stick droit de la N64
  pilote les axes C.
- **Zones.** Un doigt posé dans le cadre dessiné d'une commande ne presse que
  les commandes dessinées à cet endroit. Les bords étendus ne servent qu'aux
  doigts hors de toute commande.

Chemin critique : `LibretroInputLatch` et la lecture par le cœur
n'allouent rien et ne bloquent pas. Le verrou `os_unfair_lock` de l'état
partagé n'est pris que le temps de copier l'instantané. Les conversions de skins (analyse, filtre,
téléchargement, conversion d'overlay) se font hors session, à l'import ou dans
les catalogues.

## 3. Filtre iPhone central

Révision `194d427`. `LibretroSkinCompatibility` (natif, portable) rend un
verdict par console sur le skin réellement analysé par le parseur de NeoStation.
Chaque disposition est posée avec `LibretroSkinLayout` sur le plus petit iPhone
qui l'afficherait : 375×667 en standard, 390×844 bord à bord ; les deux pour
une disposition iPad.

- **Compatible iPhone** : disposition iPhone, commandes essentielles
  présentes, noms Delta.
- **Adaptable** (« Adapté à l'iPhone ») : noms convertis, stick sur console à
  croix, boutons dessinés sans effet en plus des essentiels, ou disposition iPad
  dont les zones essentielles gardent au moins 36 pt sur iPhone. Dans ce dernier
  cas, l'iPhone utilise la disposition iPad (`phoneUsesTabletLayouts`).
- **Incompatible** : aucune disposition iPhone utilisable, commande essentielle
  manquante, aucune commande tactile (skin d'écran pour manette), aucune image,
  autre console. Les catalogues ajoutent leurs propres refus :
  - lien qui n'est pas un fichier de skin ;
  - fichier invalide ;
  - overlay clavier/souris, décoratif ou propre à un appareil Android ;
  - overlay non reproductible fidèlement ;
  - console sans émulateur intégré.

Les commandes essentielles par console sont documentées dans
`LibretroSkinCompatibility.h`. Les codes de raison `SKIN_COMPAT_*` sont
traduits dans les douze langues.

Le filtre est utilisé partout :

- **Import depuis Fichiers et catalogues.** Sur iPhone, un skin qu'aucune
  console visée ne peut jouer au tactile est refusé, avec ses raisons.
- **Page des skins.** Elle montre le verdict et les raisons de chaque skin
  installé, y compris ceux installés avant ce cycle. Leur verdict est calculé
  en mémoire ; leurs fichiers ne sont pas modifiés.
- **Session.** Si l'orientation choisie n'est pas jouable au tactile, les
  commandes NeoStation par défaut la remplacent. Ce remplacement est annoncé
  une fois et noté au journal. Il n'a lieu ni si le tactile est désactivé, ni
  si une manette est branchée.

## 4. Catalogues

Révision `6639e7a`, puis la révision de ce document. Une seule page,
« Catalogues de skins », pour toutes les sources.

| Source | Accès vérifié | Licence / conditions | Intégration |
|--------|---------------|----------------------|-------------|
| Provenance (`provenance-emu.com/skins/catalog.json`, repli GitHub) | oui (catalogue en cache 24 h) | index communautaire ; chaque skin reste à son auteur | conservé ; ses entrées DeltaStyles et Delta Skins sont attribuées à ces sites |
| DeltaStyles | **non vérifiable ici** (site hors des hôtes autorisés de l'environnement) | **non vérifiées — à revoir par le mainteneur** | uniquement les entrées que Provenance référence déjà, aucun fichier livré |
| Delta Skins (`delta-skins/delta-skins.github.io`, `61dad28`) | oui (pages `gba`, `gbc`, `nds`, `n64`, `nes`, `snes`, `unofficial`) | **aucune licence** ; README : « I do not own any skins uploaded » | lecture des pages au moment de la consultation, téléchargement à la demande seulement |
| PocketArch (`stunrelay/PocketArch` @ `33dc23be`) | oui | MIT (© 2025 stunrelay) | 28 overlays « Phone Taller (9x20) » indexés ; convertis sur l'appareil |
| Libretro common-overlays (`libretro/common-overlays` @ `42c21b99`) | oui | CC BY 4.0 (attribution conservée : source, auteur, licence) | 129 overlays candidats, 101 exclus par chemin (clavier 14, décoratifs 86, Xperia Play 1) |

L'index des overlays est `assets/data/libretro_skin_overlays.json` : 160 665
octets, la seule donnée ajoutée à l'IPA. Il est produit par
`tools/build_skin_overlay_catalog.py` à partir des deux dépôts aux commits
épinglés. Aucune image de skin tierce n'est livrée avec l'application.

Fonctionnement :

- **Dédoublonnage.** Un même lien de téléchargement normalisé
  (`github.com/…/raw|blob/…` = `raw.githubusercontent.com/…`, hôte et
  encodage ignorés) n'apparaît qu'une fois. La première source gagne :
  Provenance, puis le site Delta Skins, puis les overlays. Un même nom, auteur
  et consoles garde l'entrée la plus téléchargée.
- **Analyse sans téléchargement complet.** Pour une archive Delta, NeoStation
  lit par requêtes HTTP Range la fin du ZIP (répertoire central), puis
  `info.json` seul. Des fichiers de signature (PNG, JPEG, `%PDF-`) remplacent
  les images. Le parseur et le filtre natifs jugent ensuite cette disposition
  réelle. Un hôte qui ignore les plages envoie le fichier entier, lu jusqu'à la
  limite d'import (50 Mo). Un ZIP qui enveloppe un seul `.deltaskin` est ouvert.
- **Cache des verdicts.** `Caches/Libretro/skin-verdicts.json`, 30 jours ;
  6 heures quand le fichier était injoignable. Il est invalidé par un
  changement de règles (`rulesVersion`).
- **Affichage.**
  - Les entrées s'affichent tout de suite et sont vérifiées en arrière-plan,
    4 à la fois, les plus téléchargées d'abord.
  - Une entrée refusée est masquée. Le compteur « Skins masqués… » et le
    bouton « Afficher pourquoi ils sont masqués » montrent les raisons
    traduites, sans bouton d'installation.
  - Une entrée qu'on n'a pas pu vérifier reste affichée ; l'installation la
    vérifie de nouveau.
  - Sur iPad, seuls les refus indépendants de l'écran de l'iPhone masquent
    une entrée.
- **Filtres.** Source, orientation (selon le verdict par orientation),
  favoris (`Documents/Libretro/SkinFavorites.json`), recherche par nom,
  auteur ou source. La page affiche aussi :
  - les aperçus : vignette du catalogue, ou première image de l'overlay ;
  - la progression de la vérification ;
  - les sources indisponibles, avec un bouton « Réessayer ».
- **Installation.** Elle passe par l'import de Fichiers, avec ses mêmes
  limites, le même parseur, le même filtre et le même remplacement. La console
  parcourue est la cible. Le verdict est enregistré avec le skin
  (`neostation-skin.json`). Un overlay s'installe avec ses images, son lien
  source, son auteur et sa licence.
- **Hors ligne.** Le catalogue n'est en échec que si aucune source en ligne ne
  répond (ni Provenance, même en cache, ni le site Delta Skins). L'index des
  overlays, livré avec l'application, ne prouve pas l'accès au réseau.

**Correctif Build 446 (12 octobre 2026).** Les catalogues de la 444/445 ne se
chargeaient plus du tout sur l'iPhone : `normalizeDownloadURL` décodait deux
fois les segments d'URL et levait une exception sur deux liens DeltaStyles
réels à caractères non ASCII, ce qui interrompait tout `load()`. Le double
décodage est supprimé et une entrée inutilisable est désormais ignorée sans
bloquer les autres entrées ni les autres sources. Détails : `docs/build446-plan.md`.

## 5. Conversion des formats

- **Delta / Manic / Provenance (`info.json`).** Le parseur natif existant lit
  ces skins, complété par les noms adaptés du § 2 et l'adaptation des
  dispositions iPad du § 3. Les skins Provenance déjà installés en profitent
  au prochain lancement, sans réinstallation et sans modification de leurs
  fichiers.
- **Overlays RetroArch (`.cfg`).** `LibretroOverlayConverter` (Dart) suit la
  sémantique de `tasks/task_overlay.c` / `input/input_driver.c` et produit un
  `info.json` Delta, que le parseur et le filtre natifs jugent comme tout skin
  importé :
  - **Pages.** Une page par orientation : nommée `portrait`/`landscape`, sinon
    choisie par son rapport d'aspect, sinon la première page (celle que
    RetroArch affiche) dans l'orientation que nomme le chemin du `.cfg`. Les
    pages pause, menu et masquées sont écartées. La page doit être
    `full_screen` et `normalized`.
  - **Commandes.** Les descripteurs donnent des boutons. `reach_*` donne les
    bords étendus. Un `reach` nul (jamais pressé dans RetroArch) donne une
    décoration. `dpad_area` devient une croix. `abxy_area` devient X/B/Y/A,
    redéfinitions `*_up`… comprises. `analog_left`/`analog_right` deviennent
    des sticks, `l_x_minus`… des directions de stick, et pour la N64 `r_*`
    devient les boutons C. Les noms RetroPad sont traduits par l'identifiant
    RetroPad qu'ils pressent (sur Mega Drive, `a` devient C).
  - **Actions.** `menu_toggle` et `overlay_next` vers une page pause ouvrent le
    menu NeoStation. `hold_fast_forward`, `toggle_fast_forward`, `save_state`
    et `load_state` deviennent les actions NeoStation. `rewind`, `osk_toggle`
    et les touches clavier sont retirés et listés.
  - **Écran.** En portrait, le jeu occupe la place au-dessus de la commande la
    plus haute. En paysage, il remplit la vue derrière les commandes
    translucides. Pour la DS, deux écrans empilés et l'écran tactile.
  - **iPad.** Un overlay iPad devient une disposition iPad, que le filtre
    adapte à l'iPhone seulement si ses commandes restent assez grandes.
- **Étude sur les overlays réels** (convertisseur de ce cycle, commits épinglés) :
  - PocketArch : **28 / 28** convertis (41 / 41 couples overlay-console) ;
  - common-overlays : **90 / 129** convertis (239 / 543 couples). Les échecs :
    - 297 couples : pages en coordonnées pixels, non `normalized`, dont la
      géométrie dépend de la taille des images ; ce sont surtout les anciens
      overlays RetroPad génériques, listés pour 10 consoles chacun ;
    - 6 : portrait sans place pour le jeu ;
    - 1 : 3DS, sans disposition convertie.
  - Commandes retirées : `osk_toggle` (40), `rewind` (16).

  Un overlay converti peut encore être jugé incompatible ou adaptable par le
  filtre natif : ces chiffres mesurent la conversion, pas le verdict iPhone.
- **Autres moteurs (Dolphin, ARMSX2, RPCS3).** L'architecture séparant
  verdict, conversion et contrôleur s'y appliquerait. Elle n'y est pas
  appliquée : ces moteurs stables n'ont pas de lien établi avec le défaut
  traité.

## 6. Diagnostic développeur

Le diagnostic s'active depuis le menu en jeu : interrupteur « Diagnostic
tactile », désactivé par défaut, mémorisé dans `libretro.touchDiagnostics`. La
vue de diagnostic ne reçoit aucune touche. Elle dessine :

- les zones de touche (pointillés) et les cadres : vert pour une commande
  active, rouge pour une commande sans effet, bleu pour l'écran tactile ;
- un cercle par doigt.

Un panneau indique :

- le RetroPad tactile envoyé ;
- l'image du cœur et le RetroPad, l'analogique et le pointeur réellement lus
  par le cœur à sa dernière image ;
- le délai de livraison iOS (dernier et pire, en ms) ;
- une ligne par doigt : éléments touchés, entrées envoyées, entrées inertes.

Le halo seul ne prouve rien. L'état « lu par le cœur » est celui que le cœur
a réellement obtenu.

## 7. Tests automatisés

| Étape de la chaîne | Test | Exécution |
|--------------------|------|-----------|
| verrou d'appui (appuis courts, longs, relâchement entre appuis, opposés, pointeur) | `test/libretro_host/frontend/input_latch_test.m` (17 vérifications) | CI macOS ; localement gcc + ASan/UBSan |
| doigt → zone → commande | `touch_tracker_test.m` | CI macOS |
| commande → RetroPad (noms adaptés, diagonales, N64) | `input_map_test.m` | CI macOS |
| état → cœur (poll tardif, double poll, images) | `test/libretro_host_test.py` (`host_test.m`, `test_core.c`, `neotest_poll=late\|twice`) | CI macOS |
| filtre iPhone | `skin_compatibility_test.m` | CI macOS |
| syntaxe iPhone de tout le pont | `test/libretro_ios_syntax_test.py` | CI macOS |
| conversion d'overlays | `test/libretro_skin_catalogs_test.dart` | CI Linux ; local |
| inspection distante (plages, hôte sans plages, ZIP enveloppant, dossier unique, erreurs réseau / fichier, signatures) | `test/libretro_skin_catalogs_test.dart` | CI Linux ; local |
| catalogues (attribution, normalisation, site Delta Skins, index livré, fusion sans doublons, sources injoignables, verdicts et cache, installation d'un overlay, favoris) | `test/libretro_skin_catalogs_test.dart` | CI Linux ; local |
| écran des catalogues (masquage avec raison, verdict, installation, favoris, échec hors ligne, navigation manette) | `test/libretro_skin_manager_test.dart` | CI Linux ; local |
| import, refus « non jouable », codes traduits | `test/libretro_skin_service_test.dart` | CI Linux ; local |
| douze langues | `test/libretro_locale_test.dart`, `test/localization_12_locale_coverage_test.py` | CI Linux ; local |
| contrat d'interface | `test/libretro_frontend_ui_contract_test.py` | CI Linux ; local |

Détail de `touch_tracker_test.m` :

- balayage de tous les skins par défaut : 17 consoles × 4 tailles d'appareil
  × 2 orientations, soit 920 boutons, 128 croix, 32 sticks et 16 écrans
  tactiles ;
- A/B/X/Y, A+B multitouch, appuis longs, diagonales, gâchettes, sticks ;
- glissements, rotation, annulation sans bouton coincé ;
- skin importé adapté, pointeur DS.

Contrats remplacés, et pourquoi :

- **N64 `rightStick*`.** `input_map_test.m` refusait ce nom ; il pilote
  désormais les axes C.
- **Entrée de catalogue qui n'est pas un fichier de skin.** Elle était
  affichée avec un bouton désactivé. Elle est maintenant masquée avec la
  raison `catalogNotDirect` (contrat d'interface mis à jour).
- **Skin du catalogue déclarant une autre console.** Il n'est plus proposé
  pour la console parcourue : il est masqué avec la raison « Conçu pour une
  autre console ». Son installation pour l'autre console reste couverte par
  le test d'import depuis Fichiers.

Aucun test n'a été supprimé ni affaibli pour obtenir un résultat vert.

## 8. À valider sur iPhone

Aucun de ces points n'est démontré par la CI :

1. Skin GBA Provenance installé : A, B, L, R, Start, Select et la croix agissent
   immédiatement dans le jeu. Le diagnostic montre « lu par le cœur ».
2. Taps très courts répétés, appuis longs, A+B, diagonales, sur un jeu à 60
   et un à 30 images/s, et en accéléré.
3. Glisser d'un bouton à l'autre, puis sortir de l'écran. Interruptions :
   appel, centre de contrôle, mise en arrière-plan, rotation pendant un appui.
   Aucun bouton ne doit rester coincé.
4. Sticks (N64, PSP, PSX analogique) et gâchettes (PSX L2/R2).
5. Écran tactile DS et 3DS après rotation et changement de skin.
6. Bords d'écran : délai iOS mesuré par le diagnostic près des gestes système.
7. Catalogues sur réseau mobile :
   - temps de vérification d'une console de plus de 200 entrées ;
   - volume de données réellement consommé ;
   - comportement hors ligne.
8. Un overlay PocketArch et un overlay common-overlays installés et joués, en
   portrait et en paysage.
9. Disposition iPad adaptée sur le plus petit iPhone en service (taille des
   zones).
10. Remplacement automatique par les commandes par défaut d'une orientation
    non jouable, et retour quand une manette est branchée puis débranchée.
11. Installation habituelle par SideStore (signature Apple et provisioning
    appliqués par SideStore), sans perte des réglages ni des skins installés.

## 9. Révisions, runs et limites

Révisions de ce cycle, toutes sur `Claude` :

- `4da3154` : audit et moteur tactile ;
- `194d427` : filtre central, diagnostic, commandes par défaut ;
- `6639e7a` : catalogues unifiés et conversion d'overlays ;
- `e4a485f` : ce document et le repli « première page » du convertisseur ;
- `f28525f` : vérifications interrompues par la fermeture des catalogues non
  mises en cache. C'est la dernière révision testée en CI.

Runs CI « Libretro engine checks » (aucun résultat n'est réutilisé d'une
révision à l'autre) :

| Révision | Run | Natif (macOS) | Dart : analyse + tests | Dart : contrats source |
|----------|-----|---------------|------------------------|------------------------|
| `4da3154` | `38178625448` | échec : `touch_tracker_test` (« finger key reused »), cause : disposition portrait laissée par le test de rotation, test corrigé dans `194d427` | succès | échec : épinglage NeoSwap (voir ci-dessous) |
| `194d427` | `38180063348` | succès | succès | échec : épinglage NeoSwap |
| `6639e7a` | `38181805736` | succès | succès (avec `libretro_skin_catalogs_test.dart`) | échec : épinglage NeoSwap, tous les contrats précédents réussis |
| `e4a485f` | `38182159300` | annulé (remplacé par le run suivant, même branche) | annulé | annulé |
| `f28525f` | `38182221976` | succès | succès | échec : épinglage NeoSwap, tous les contrats précédents réussis (dont le contrat d'interface et les douze langues) |

Le job Dart de `libretro-checks` échoue sur `retroarch_baseline_scope_test.py`
à cause de l'épinglage NeoSwap (`native/neoswap-relay/Backend.cpp` et `.h`).
Ces fichiers ont été modifiés par le commit `7ec94a8` de la Build 444. Ce
défaut est indépendant de ce cycle et n'est pas modifié ici. Le script suivant
de la même étape, `game_audio_handoff_test.py`, ne s'exécute donc pas en CI ;
il a été exécuté localement avec succès.

La Build 444 a été livrée depuis `a221ae0c` (run `38182831110`, voir
`docs/build444-delivery.md`). Ce commit descend de toutes les révisions de ce
cycle : la 444 contient donc tout le travail tactile/skins. L'autre session y
a aussi ré-épinglé le garde-fou NeoSwap. La Build 445 (`docs/build445-plan.md`)
reprend ce produit à l'identique.

Sonde simulateur (`libretro-simulator.yml`), non signalée au moment de ces
runs. Il s'agit d'un constat ouvert, sans correction (décision du mainteneur
du 12 octobre 2026) :

- **Échecs.** `38178625368` (`4da3154`) et `38180063457` (`194d427`) ont
  échoué uniquement sur l'assertion « PPSSPP's memory at the reserved base »
  des scénarios encombrés. `ppsspp-crowded-prx` a échoué dans les deux runs,
  `ppsspp-crowded` dans le second. Tous les lancements PSP ont réussi, se sont
  fermés dans l'ordre et ont repris la réservation.
- **Mécanisme probable.** La sonde n'encombre la fenêtre qu'une fois, avant le
  lancement. De la mémoire libérée pendant le démarrage de PPSSPP a laissé
  libre une base plus basse (0x109800000, 0x10c000000, 0x105000000), que
  PPSSPP a prise.
- **Attribution indéterminée.**
  - Les commits tactile/skins n'appellent directement ni `vm_allocate` ni
    `mmap`. Leurs allocations ordinaires peuvent toutefois être placées puis
    libérées dans cette fenêtre.
  - Le second run avait un exécuteur dégradé : « no progress in 120 s », sonde
    de 354,8 s contre 99,3 s, 117,2 s et 145,3 s pour `38116309132`,
    `38178625368` et `38046114507`.
  - Les sources immédiatement antérieures (`54147b97`, `0ff20bbd`) ont réussi
    les 4 contrôles encombrés de leurs deux runs (`38046114507`,
    `38116309132`). L'échantillon reste petit.

`docs/LEGAL_AND_CREDITS.md` est épinglé octet pour octet par
`test/import_memory_candidate_scope_test.py`. Les crédits des nouvelles
sources sont donc dans `docs/SKINS.md` et dans ce document. Leur ajout aux
mentions légales embarquées attend un ré-épinglage approuvé par le mainteneur.

Limites connues :

- **Overlays.**
  - Les overlays en coordonnées pixels, ceux à plusieurs pages actives à la
    fois et les `#include` ne sont pas convertis.
  - `rewind`, le clavier à l'écran et les touches clavier n'ont pas
    d'équivalent.
  - Les overlays 3DS ne sont pas convertis.
- **Vérification des catalogues.** Elle consomme quelques kilo-octets par
  entrée lors de la première ouverture. Un hôte sans HTTP Range envoie le
  fichier entier.
- **Délai iOS en bord d'écran.** Il est mesuré par le diagnostic, pas corrigé.
- **Licences à revoir avant diffusion.** DeltaStyles : conditions non
  vérifiées. Site Delta Skins : aucune licence. Les skins restent à leurs
  auteurs ; NeoStation ne les redistribue pas.
- **Sélection par jeu.** Elle existe déjà dans le menu en jeu (« Enregistrer
  pour : ce jeu seulement »). La page des catalogues installe pour la console.
